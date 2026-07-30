"""
Texas Ethics Commission (TEC) crosswalk for San Antonio donors.

Port of the Austin repo's texas_finance_scraper.py + tec_partisan_aggregate.py,
collapsed into one script. Ingests the 10 tracked state PACs from the TEC bulk
CSV shards, links contributors to SA donor_identities via (canonical_name,
canonical_zip5), and aggregates per-donor dem/rep/other totals into the
tec_total_* columns that generate_profile_data.py already reads.

The bulk shards (contribs_01..99.csv, ~7 GB) are NOT copied into this repo —
we reuse the Austin checkout's tec_data directory (override with TEC_DIR env
var). Source: https://prd.tecprd.ethicsefile.com/public/cf/public/TEC_CF_CSV.zip
(nightly regenerate, no API key, public domain).

The donor FK column is named austin_donor_id for template compatibility —
generate_profile_data.py (shared between cities) queries it by that name; here
it holds SA donor_identities.donor_id values.

Run AFTER build_identities.py (donor_ids must exist to link). Re-running is
idempotent: ingest is INSERT OR IGNORE on contributionInfoId, the link pass
only fills NULL FKs, and the aggregate pass resets then rewrites.

Usage:
    python sa_tec_crosswalk.py              # ingest all shards + link + aggregate
    python sa_tec_crosswalk.py --link-only  # skip ingest (shards already loaded)
"""
from __future__ import annotations

import csv
import os
import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "san_antonio_finance.db"
TEC_DIR = Path(os.environ.get(
    "TEC_DIR",
    r"C:\Users\Hamza Sait\Electoral\decode-politics\austin-finance-data\tec_data",
))

# Same 10 tracked committees as the Austin side (keep the lists in sync —
# generate_profile_data.py hardcodes the same filerIdent → lean map).
TARGET_COMMITTEES = {
    "00070864": "Texas Oil and Gas Association Good Government Committee (TXOGA)",
    "00028135": "Texans for Lawsuit Reform PAC",
    "00015555": "Associated Republicans of Texas Campaign Fund",
    "00089881": "Defend Texas Liberty",
    "00061927": "Empower Texans PAC (terminated)",
    "00015666": "Texas Trial Lawyers Association PAC",
    "00015487": "Texas REALTORS Political Action Committee (TREPAC)",
    "00017303": "Texas Apartment Association PAC",
    "00015700": "GHBA HOME-PAC",
    "00035370": "Austin Board of REALTORS Political Action Committee",
}

TEC_COMMITTEE_LEAN = {
    "00028135": "Rep", "00015555": "Rep", "00089881": "Rep", "00061927": "Rep",
    "00015666": "Dem",
    "00070864": "Other", "00015487": "Other", "00017303": "Other",
    "00015700": "Other", "00035370": "Other",
}


def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS texas_committees (
        filer_ident        TEXT PRIMARY KEY,
        filer_type_cd      TEXT,
        filer_name         TEXT,
        committee_status   TEXT,
        committee_class    TEXT,
        fetched_at         TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS texas_contributions_raw (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        contribution_info_id     TEXT UNIQUE,
        report_info_ident        TEXT,
        received_dt              TEXT,
        filer_ident              TEXT NOT NULL,
        filer_type_cd            TEXT,
        filer_name               TEXT,
        contribution_dt          TEXT,
        contribution_amount      REAL,
        contribution_descr       TEXT,
        itemize_flag             TEXT,
        contributor_type         TEXT,
        contributor_org          TEXT,
        contributor_last         TEXT,
        contributor_first        TEXT,
        contributor_suffix       TEXT,
        contributor_city         TEXT,
        contributor_state        TEXT,
        contributor_zip          TEXT,
        contributor_country      TEXT,
        contributor_employer     TEXT,
        contributor_occupation   TEXT,
        contributor_pac_fein     TEXT,
        oos_pac_flag             TEXT,
        canonical_name           TEXT,
        canonical_zip5           TEXT,
        austin_donor_id          TEXT,   -- SA donor_identities.donor_id (name kept for template compat)
        match_confidence         TEXT,
        source                   TEXT DEFAULT 'texas_state',
        ingested_at              TEXT DEFAULT (datetime('now'))
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_contrib_filer ON texas_contributions_raw(filer_ident)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_contrib_canon ON texas_contributions_raw(canonical_name, canonical_zip5)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_contrib_austin ON texas_contributions_raw(austin_donor_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tx_contrib_date ON texas_contributions_raw(contribution_dt)")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for fid, name in TARGET_COMMITTEES.items():
        cur.execute("""
            INSERT INTO texas_committees(filer_ident, filer_name, committee_class, fetched_at)
            VALUES (?, ?, 'target', ?)
            ON CONFLICT(filer_ident) DO UPDATE SET
                filer_name=excluded.filer_name,
                committee_class='target',
                fetched_at=excluded.fetched_at
        """, (fid, name, now))
    conn.commit()


def _canonical_name(row: dict) -> str | None:
    if (row.get("contributorPersentTypeCd") or "").upper() != "INDIVIDUAL":
        return None
    last = (row.get("contributorNameLast") or "").strip()
    first = (row.get("contributorNameFirst") or "").strip()
    if not last:
        return None
    return f"{last}, {first}".strip(", ").strip()


def _zip5(raw: str | None) -> str | None:
    if not raw:
        return None
    s = "".join(ch for ch in raw if ch.isdigit())
    return s[:5] if len(s) >= 5 else (s or None)


def ingest_shard(conn: sqlite3.Connection, shard: str) -> tuple[int, int]:
    shard_path = TEC_DIR / shard
    if not shard_path.exists():
        print(f"[ingest] MISSING {shard} (not extracted in {TEC_DIR}) -- skip")
        return 0, 0
    targets = set(TARGET_COMMITTEES)
    cur = conn.cursor()
    sql = """
        INSERT OR IGNORE INTO texas_contributions_raw (
            contribution_info_id, report_info_ident, received_dt,
            filer_ident, filer_type_cd, filer_name,
            contribution_dt, contribution_amount, contribution_descr, itemize_flag,
            contributor_type, contributor_org,
            contributor_last, contributor_first, contributor_suffix,
            contributor_city, contributor_state, contributor_zip, contributor_country,
            contributor_employer, contributor_occupation,
            contributor_pac_fein, oos_pac_flag,
            canonical_name, canonical_zip5
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    scanned = inserted = 0
    batch: list[tuple] = []
    with open(shard_path, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            scanned += 1
            if row.get("filerIdent") not in targets:
                continue
            try:
                amt = float(row.get("contributionAmount") or 0)
            except ValueError:
                amt = 0.0
            batch.append((
                row.get("contributionInfoId"), row.get("reportInfoIdent"),
                row.get("receivedDt"), row.get("filerIdent"),
                row.get("filerTypeCd"), row.get("filerName"),
                row.get("contributionDt"), amt,
                row.get("contributionDescr"), row.get("itemizeFlag"),
                row.get("contributorPersentTypeCd"),
                row.get("contributorNameOrganization"),
                row.get("contributorNameLast"), row.get("contributorNameFirst"),
                row.get("contributorNameSuffixCd"),
                row.get("contributorStreetCity"), row.get("contributorStreetStateCd"),
                row.get("contributorStreetPostalCode"), row.get("contributorStreetCountryCd"),
                row.get("contributorEmployer"), row.get("contributorOccupation"),
                row.get("contributorPacFein"), row.get("contributorOosPacFlag"),
                _canonical_name(row), _zip5(row.get("contributorStreetPostalCode")),
            ))
            if len(batch) >= 2000:
                before = conn.total_changes
                cur.executemany(sql, batch)
                inserted += conn.total_changes - before
                batch.clear()
                conn.commit()
    if batch:
        before = conn.total_changes
        cur.executemany(sql, batch)
        inserted += conn.total_changes - before
        conn.commit()
    return scanned, inserted


def link_to_sa_donors(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    by_name_zip: dict[tuple[str, str], str] = {}
    by_name: dict[str, list[str]] = {}
    for donor_id, name, zipc in cur.execute(
        "SELECT donor_id, canonical_name, canonical_zip FROM donor_identities"
    ):
        if not name:
            continue
        name_n = name.strip()
        if zipc:
            by_name_zip[(name_n, zipc.strip())] = donor_id
        by_name.setdefault(name_n, []).append(donor_id)
    print(f"[link] {len(by_name):,} SA donor names, {len(by_name_zip):,} name+zip keys")

    exact = name_only = 0
    updates: list[tuple[str, str, int]] = []
    for rid, cname, czip in cur.execute(
        "SELECT id, canonical_name, canonical_zip5 FROM texas_contributions_raw "
        "WHERE canonical_name IS NOT NULL AND austin_donor_id IS NULL"
    ):
        hit = by_name_zip.get((cname, czip)) if czip else None
        if hit:
            updates.append((hit, "name+zip5", rid))
            exact += 1
            continue
        candidates = by_name.get(cname)
        if candidates and len(candidates) == 1:
            updates.append((candidates[0], "name_only", rid))
            name_only += 1
    cur.executemany(
        "UPDATE texas_contributions_raw SET austin_donor_id=?, match_confidence=? WHERE id=?",
        updates,
    )
    conn.commit()
    print(f"[link] name+zip5={exact}  unique-name-only={name_only}")
    return exact + name_only


def aggregate(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("""
        UPDATE donor_identities
        SET tec_total_dem=0, tec_total_rep=0, tec_total_other=0,
            tec_total_donations=0, tec_matched=0
    """)
    per_donor: dict[str, dict] = {}
    for donor_id, filer_ident, total, n in cur.execute("""
        SELECT austin_donor_id, filer_ident,
               SUM(CAST(contribution_amount AS REAL)), COUNT(*)
        FROM texas_contributions_raw
        WHERE austin_donor_id IS NOT NULL AND austin_donor_id != ''
        GROUP BY austin_donor_id, filer_ident
    """):
        lean = TEC_COMMITTEE_LEAN.get(filer_ident)
        if not lean:
            continue
        d = per_donor.setdefault(donor_id, {"dem": 0.0, "rep": 0.0, "other": 0.0, "n": 0})
        d[{"Dem": "dem", "Rep": "rep"}.get(lean, "other")] += total or 0
        d["n"] += n or 0
    for donor_id, t in per_donor.items():
        cur.execute("""
            UPDATE donor_identities
            SET tec_total_dem=?, tec_total_rep=?, tec_total_other=?,
                tec_total_donations=?, tec_matched=1
            WHERE donor_id=?
        """, (round(t["dem"], 2), round(t["rep"], 2), round(t["other"], 2),
              t["n"], donor_id))
    conn.commit()
    dem, rep, other = cur.execute("""
        SELECT COALESCE(SUM(tec_total_dem),0), COALESCE(SUM(tec_total_rep),0),
               COALESCE(SUM(tec_total_other),0)
        FROM donor_identities WHERE tec_matched=1
    """).fetchone()
    print(f"[aggregate] {len(per_donor):,} SA donors TEC-matched  "
          f"D=${dem:,.0f} R=${rep:,.0f} Other=${other:,.0f}")


def main() -> int:
    link_only = "--link-only" in sys.argv
    print(f"db: {DB_PATH}\ntec_data: {TEC_DIR}")
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_schema(conn)

    if not link_only:
        t0 = time.time()
        tot_scanned = tot_inserted = 0
        for i in range(1, 100):
            shard = f"contribs_{i:02d}.csv"
            scanned, inserted = ingest_shard(conn, shard)
            tot_scanned += scanned
            tot_inserted += inserted
            if i % 10 == 0 or inserted:
                print(f"[ingest] {shard}: scanned {scanned:,} inserted {inserted:,} "
                      f"(cum {tot_inserted:,}, {time.time()-t0:.0f}s)")
        print(f"[ingest] TOTAL scanned {tot_scanned:,} inserted {tot_inserted:,} "
              f"in {time.time()-t0:.0f}s")

    link_to_sa_donors(conn)
    aggregate(conn)

    cur = conn.cursor()
    print("\n=== per-committee rows in san_antonio_finance.db ===")
    for r in cur.execute("""
        SELECT t.filer_name, COUNT(r.id), ROUND(SUM(r.contribution_amount),0)
        FROM texas_committees t
        LEFT JOIN texas_contributions_raw r ON r.filer_ident = t.filer_ident
        GROUP BY t.filer_ident ORDER BY 3 DESC
    """):
        print("  ", r)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
