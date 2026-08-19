"""
sa_identity_merge.py
Collapse fragmented donor identities: same person, same street, many donor_ids.

build_identities.py blocks candidate pairs on (last, zip5) and skips any block
larger than 50 members. A recurring small-dollar donor's own records can fill
a block by themselves (a monthly ActBlue-style donor accrues 50+ rows), so the
whole block was skipped and the donor shattered into one donor_id per record —
as of 2026-08: Salazar/73 ids, MacGuire/58, Cramer/52, Bravenec/40. That
inflated unique-donor counts (Castillo ~7%) and hid genuine top donors, whose
totals were split across dozens of ids. build_identities.py now collapses
exact-duplicate records before blocking so fresh runs don't regress; THIS
script repairs an existing DB in place without re-running the (rapidfuzz-
dependent, id-churning) full pipeline.

Merge key — deliberately conservative, precision over recall:
    (normalized last name, nickname-normalized first name, normalized street)
Street comes from the leading segment of city_state_zip, which the SA portal
fills with the full street address. Requiring the street to match keeps
distinct people apart even when names collide: the two "Salazar, Amador"
profiles (a UT grad student at 6503 Arrid Pass and a COSA D5 comms director
at 2234 Fresno) stay separate, as does Katy Bravenec's single record at
1906 S Flores. Each donor_id is keyed by the most common key across its rows,
so an already-clustered id is never torn apart, only joined.

Within a merge group the surviving donor_id is the most enriched member
(FEC/TEC/industry/IP data), then the one with the most rows, then the lowest
id — and enrichment columns on the survivor are backfilled from members via
COALESCE semantics (never summed: two ids for the same person matched the
same federal records, so adding fec_* aggregates would double-count).

Everything that references a merged id is remapped: campaign_finance
(donor_id, donor_id_2), fec_contributions_raw.donor_id,
texas_contributions_raw.austin_donor_id, donor_affiliations.donor_id. The
survivor's donor_identities row is recomputed from campaign_finance; loser
rows are deleted. Every merge is recorded in the identity_merges table.
Idempotent: a second run finds only singleton groups and does nothing.

Usage:
    python sa_identity_merge.py [--db PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from build_identities import normalize_name, to_ascii

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "san_antonio_finance.db"

STREET_ABBR = {
    "avenue": "ave", "av": "ave", "street": "st", "str": "st", "drive": "dr",
    "road": "rd", "boulevard": "blvd", "lane": "ln", "court": "ct",
    "place": "pl", "circle": "cir", "parkway": "pkwy", "highway": "hwy",
    "terrace": "ter", "trail": "trl", "expressway": "expy",
    "north": "n", "south": "s", "east": "e", "west": "w",
}
UNIT_WORDS = {"apt", "unit", "ste", "suite", "fl", "floor"}

# Enrichment fields that make a member the preferred survivor of a merge.
ENRICHED_FIELDS = ("resolved_industry", "resolved_employer_display",
                   "fec_partisan_lean", "fec_matched", "tec_matched",
                   "ip_spectrum")


def norm_street(city_state_zip: str | None) -> str:
    """Street-line key: '501 501 Shook Avenue #4C, San Antonio…' -> '501 shook ave'."""
    s = to_ascii(city_state_zip or "").lower().split(",")[0]
    s = re.sub(r"[^a-z0-9# ]", " ", s)
    toks = s.split()
    while len(toks) >= 2 and toks[0] == toks[1]:      # doubled house number
        toks.pop(0)
    out: list[str] = []
    skip = False
    for t in toks:
        if skip:
            skip = False
            continue
        if t.startswith("#"):
            continue
        if t in UNIT_WORDS:
            skip = True
            continue
        out.append(STREET_ABBR.get(t, t))
    # trailing bare unit ("… ave 4c") — digits+letter only, never the street number
    if len(out) > 2 and re.fullmatch(r"\d+[a-z]", out[-1]):
        out.pop()
    return " ".join(out)


def person_key(donor: str, city_state_zip: str | None) -> tuple | None:
    last, first = normalize_name(donor)
    street = norm_street(city_state_zip)
    if not last or not first or not street:
        return None
    return (last, first, street)


def merge_identities(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    cur = conn.cursor()

    # Dominant person key per donor_id, over the same record scope
    # build_identities clusters (named individuals' contribution rows).
    key_votes: dict[str, Counter] = defaultdict(Counter)
    for did, donor, csz in cur.execute(
            """SELECT donor_id, donor, city_state_zip FROM campaign_finance
               WHERE donor_id IS NOT NULL AND txn_type = 'contribution'
                 AND donor_type IN ('INDIVIDUAL','Individual') AND donor LIKE '%,%'"""):
        key = person_key(donor, csz)
        if key:
            key_votes[did][key] += 1

    by_key: dict[tuple, list[str]] = defaultdict(list)
    for did, votes in key_votes.items():
        by_key[votes.most_common(1)[0][0]].append(did)

    # Unify keys that differ only by a trailing street-type token — donors
    # self-report '2234 Fresno' and '2234 Fresno St' interchangeably. Only a
    # suffixed key whose bare form also exists is folded in; distinct suffixes
    # ('oak dr' vs 'oak ln') never touch.
    suffixes = set(STREET_ABBR.values()) - {"n", "s", "e", "w"}
    for key in [k for k in by_key]:
        last, first, street = key
        toks = street.split()
        if len(toks) > 1 and toks[-1] in suffixes:
            base = (last, first, " ".join(toks[:-1]))
            if base in by_key:
                by_key[base].extend(by_key.pop(key))

    groups = {k: sorted(ids) for k, ids in by_key.items() if len(ids) > 1}
    if not groups:
        print("[identity-merge] no fragmented identities — nothing to do")
        return 0

    ident_cols = [r[1] for r in cur.execute("PRAGMA table_info(donor_identities)")]
    base_cols = {"donor_id", "canonical_name", "canonical_zip", "canonical_employer",
                 "total_donated", "campaign_count", "campaigns", "record_count",
                 "first_seen", "last_seen"}
    extra_cols = [c for c in ident_cols if c not in base_cols]

    def ident_row(did: str) -> dict:
        row = cur.execute(
            f"SELECT {', '.join(ident_cols)} FROM donor_identities WHERE donor_id=?",
            (did,)).fetchone()
        return dict(zip(ident_cols, row)) if row else {}

    merges = []          # (loser, winner, key)
    planned = 0
    for key, ids in sorted(groups.items()):
        rows = {did: ident_row(did) for did in ids}
        def rank(did):
            r = rows[did]
            enriched = sum(1 for f in ENRICHED_FIELDS if r.get(f))
            return (-enriched, -(r.get("record_count") or 0), did)
        winner = min(ids, key=rank)
        losers = [d for d in ids if d != winner]
        planned += len(losers)
        print(f"[identity-merge] {key}: {len(ids)} ids -> "
              f"{winner[:8]} ({rows[winner].get('canonical_name')!r})")
        for l in losers:
            merges.append((l, winner, repr(key)))

    if dry_run:
        print(f"[identity-merge] --dry-run: {planned} ids would merge "
              f"across {len(groups)} people")
        return planned

    cur.execute("""CREATE TABLE IF NOT EXISTS identity_merges (
                       merged_donor_id TEXT PRIMARY KEY,
                       into_donor_id   TEXT NOT NULL,
                       person_key      TEXT,
                       merged_at       TEXT)""")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    winner_of = {l: w for l, w, _ in merges}

    # Remap every table that references a merged id.
    remaps = [("campaign_finance", "donor_id"),
              ("campaign_finance", "donor_id_2"),
              ("fec_contributions_raw", "donor_id"),
              ("texas_contributions_raw", "austin_donor_id"),
              ("donor_affiliations", "donor_id")]
    cur.execute("CREATE TEMP TABLE _idmap (old TEXT PRIMARY KEY, new TEXT)")
    cur.executemany("INSERT INTO _idmap VALUES (?,?)", sorted(winner_of.items()))
    for table, col in remaps:
        if not cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (table,)).fetchone():
            continue
        # Single pass per table — per-loser UPDATEs would full-scan the two
        # million-row federal/state tables once per merged id. OR REPLACE:
        # when two ids for the same person both matched the same federal/state
        # record (fec_contributions_raw is UNIQUE(donor_id, fec_sub_id)), the
        # remap would collide — the colliding rows are duplicates of one real
        # transaction, so keeping a single copy is the correct outcome.
        pre = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        n = cur.execute(
            f"""UPDATE OR REPLACE {table}
                SET {col} = (SELECT new FROM _idmap WHERE old = {col})
                WHERE {col} IN (SELECT old FROM _idmap)""").rowcount
        absorbed = pre - cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if n:
            print(f"[identity-merge] remapped {n:,} rows in {table}.{col}"
                  + (f" ({absorbed:,} duplicate rows absorbed)" if absorbed else ""))
    cur.execute("DROP TABLE _idmap")

    # Fold loser identity rows into the winner, then recompute its aggregates
    # straight from campaign_finance (post-remap, so they are exact).
    for key, ids in sorted(groups.items()):
        winner = winner_of[next(d for d in ids if d in winner_of)]
        rows = {did: ident_row(did) for did in ids}
        ordered = [winner] + sorted((d for d in ids if d != winner),
                                    key=lambda d: (-(rows[d].get("record_count") or 0), d))
        for col in extra_cols:
            val = next((rows[d].get(col) for d in ordered if rows[d].get(col) is not None),
                       None)
            cur.execute(f"UPDATE donor_identities SET {col}=? WHERE donor_id=?",
                        (val, winner))

        stats = cur.execute(
            """SELECT COUNT(*), ROUND(SUM(amount_real), 2),
                      MIN(date_iso), MAX(date_iso)
               FROM campaign_finance
               WHERE donor_id=? AND txn_type='contribution'""", (winner,)).fetchone()
        names = Counter(r[0] for r in cur.execute(
            "SELECT donor FROM campaign_finance WHERE donor_id=? AND txn_type='contribution'",
            (winner,)))
        recipients = sorted(r[0] for r in cur.execute(
            """SELECT DISTINCT recipient FROM campaign_finance
               WHERE donor_id=? AND txn_type='contribution' AND recipient IS NOT NULL""",
            (winner,)))
        canonical_emp = next((rows[d].get("canonical_employer") for d in ordered
                              if rows[d].get("canonical_employer")), "")
        canonical_zip = next((rows[d].get("canonical_zip") for d in ordered
                              if rows[d].get("canonical_zip")), "")
        cur.execute(
            """UPDATE donor_identities SET canonical_name=?, canonical_zip=?,
                   canonical_employer=?, total_donated=?, campaign_count=?,
                   campaigns=?, record_count=?, first_seen=?, last_seen=?
               WHERE donor_id=?""",
            (names.most_common(1)[0][0] if names else rows[winner].get("canonical_name"),
             canonical_zip, canonical_emp, stats[1] or 0.0, len(recipients),
             "|".join(recipients), stats[0], stats[2] or "", stats[3] or "", winner))

    cur.executemany(
        "DELETE FROM donor_identities WHERE donor_id=?",
        [(l,) for l in winner_of])
    cur.executemany(
        """INSERT OR REPLACE INTO identity_merges
           (merged_donor_id, into_donor_id, person_key, merged_at)
           VALUES (?,?,?,?)""",
        [(l, w, k, now) for l, w, k in merges])
    conn.commit()
    print(f"[identity-merge] merged {len(winner_of)} donor_ids into "
          f"{len(groups)} people; mapping recorded in identity_merges")
    return len(winner_of)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    conn = sqlite3.connect(args.db)
    merge_identities(conn, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
