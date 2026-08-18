"""
sa_normalize.py
Idempotent schema migration + backfill for the normalized columns downstream
code reads (raw portal-text columns are kept as provenance, never as API):

    amount_real   REAL   from contribution_amount  "$1,000.00" -> 1000.0
    date_iso      TEXT   from contribution_date    "6/30/2025 12:00:00 AM" -> "2025-06-30"
    txn_type      TEXT   from contribution_type    kind -> contribution|expenditure|report
    superseded_by TEXT   row_hash of the kept twin when this row is a
                         cross-report restatement (see mark_restatements)

Safe to re-run any time: adds columns if missing, then (re)derives every row
whose derived value is NULL or stale relative to its raw value. Unknown
contribution_type kinds are left NULL and reported loudly -- extend KIND_MAP
deliberately rather than guessing.

Restatement marking: SA report periods overlap (30th/8th-day pre-election
reports cover a slice of the same half-year the next semi-annual re-lists, and
amended filings re-list whole reports), so the portal shows the same
transaction once per report it appears on. row_hash includes report_filed, so
ingest keeps every copy. mark_restatements() groups rows on
(filer, donor, recipient, amount, date, kind) and, when a group spans more
than one report, keeps one report's rows and points the rest at the kept twin
via superseded_by. Downstream queries filter superseded_by IS NULL. Repeat
same-day gifts inside a single report are never marked.

Usage:
    python sa_normalize.py [--db PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "san_antonio_finance.db"

KIND_MAP = {
    "monetary political contributions": "contribution",
    "non-monetary (in-kind) political contributions": "contribution",
    "pledged contributions": "contribution",
    "political expenditures made from political contributions": "expenditure",
    "unpaid incurred obligations": "expenditure",
    "report": "report",
}

DERIVED_COLS = {
    "amount_real": "REAL",
    "date_iso": "TEXT",
    "txn_type": "TEXT",
    "superseded_by": "TEXT",
}

DATE_RE = re.compile(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})")


def parse_amount(raw: str | None) -> float | None:
    if not raw:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", raw)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date_iso(raw: str | None) -> str | None:
    if not raw:
        return None
    m = DATE_RE.match(raw)
    if not m:
        return None
    mm, dd, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    return f"{yyyy:04d}-{mm:02d}-{dd:02d}"


def classify_kind(raw: str | None) -> str | None:
    if not raw:
        return None
    return KIND_MAP.get(raw.strip().lower())


def ensure_columns(conn: sqlite3.Connection) -> list[str]:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(campaign_finance)")}
    added = []
    for col, typ in DERIVED_COLS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE campaign_finance ADD COLUMN {col} {typ}")
            added.append(col)
    conn.commit()
    return added


def mark_restatements(conn: sqlite3.Connection, filer_slug: str | None = None) -> int:
    """(Re)compute superseded_by for cross-report restatement rows.

    Recomputed from scratch on every call, so it is safe after any ingest.
    'report' placeholder rows and rows missing amount_real/date_iso are out of
    scope. Within a duplicate group the kept report is the one listing the
    most rows (ties: most enriched donor_ids, then most fetched details, then
    lexicographic report name, for determinism); a group whose reports list
    different row counts keeps the larger count, so a genuine second same-day
    gift that only one report itemizes survives. Returns rows marked.
    """
    scope_sql = ("COALESCE(txn_type,'') != 'report' "
                 "AND amount_real IS NOT NULL AND date_iso IS NOT NULL")
    params: tuple = ()
    if filer_slug:
        scope_sql += " AND filer_slug = ?"
        params = (filer_slug,)

    conn.execute(
        f"UPDATE campaign_finance SET superseded_by = NULL "
        f"WHERE superseded_by IS NOT NULL AND {scope_sql}", params)

    groups: dict[tuple, dict[str, list]] = {}
    for (rh, slug, donor, recipient, amt, diso, txn, ctype, report,
         donor_id, details_at) in conn.execute(
            f"""SELECT row_hash, COALESCE(filer_slug,''), donor,
                       COALESCE(recipient,''), amount_real, date_iso,
                       COALESCE(txn_type,''), COALESCE(contribution_type,''),
                       COALESCE(report_filed,''), donor_id, details_fetched_at
                FROM campaign_finance WHERE {scope_sql}""", params):
        key = (slug, donor, recipient, amt, diso, txn, ctype)
        groups.setdefault(key, {}).setdefault(report, []).append(
            (rh, donor_id, details_at))

    marks = []          # (kept_row_hash, superseded_row_hash)
    rescues = []        # (donor_id_source_hash, keeper_hash) — enrichment copy
    for key, by_report in groups.items():
        if len(by_report) < 2:
            continue
        kept_report = max(by_report, key=lambda rep: (
            len(by_report[rep]),
            sum(1 for r in by_report[rep] if r[1]),
            sum(1 for r in by_report[rep] if r[2]),
            rep,
        ))
        keepers = sorted(by_report[kept_report])
        marked = [r for rep, rows in by_report.items() if rep != kept_report
                  for r in rows]
        for rh, _, _ in marked:
            marks.append((keepers[0][0], rh))
        # A keeper without a donor_id whose marked twin has one would silently
        # drop that donor's identity from every profile query; copy it over.
        unenriched = [k for k in keepers if not k[1]]
        sources = [m for m in marked if m[1]]
        for k, m in zip(unenriched, sources):
            rescues.append((m[0], k[0]))

    conn.executemany(
        "UPDATE campaign_finance SET superseded_by=? WHERE row_hash=?", marks)
    for src, dst in rescues:
        conn.execute(
            """UPDATE campaign_finance SET
                   donor_id = (SELECT donor_id FROM campaign_finance WHERE row_hash=?),
                   match_confidence = (SELECT match_confidence FROM campaign_finance WHERE row_hash=?),
                   employer_id = COALESCE(employer_id,
                       (SELECT employer_id FROM campaign_finance WHERE row_hash=?)),
                   employer_match_confidence = COALESCE(employer_match_confidence,
                       (SELECT employer_match_confidence FROM campaign_finance WHERE row_hash=?))
               WHERE row_hash=?""", (src, src, src, src, dst))
    conn.commit()
    print(f"[normalize] restatements: {len(marks):,} rows marked superseded "
          f"across {sum(1 for g in groups.values() if len(g) > 1):,} groups"
          + (f", {len(rescues)} enrichment rescues" if rescues else ""))
    return len(marks)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    added = ensure_columns(conn)
    if added:
        print(f"[normalize] added columns: {', '.join(added)}")

    rows = conn.execute(
        """SELECT row_hash, contribution_amount, contribution_date,
                  contribution_type, amount_real, date_iso, txn_type,
                  contribution_year
           FROM campaign_finance"""
    ).fetchall()

    updates = []
    unknown_kinds: dict[str, int] = {}
    for rh, amt_raw, date_raw, kind_raw, amt_cur, date_cur, txn_cur, yr_cur in rows:
        amt_new = parse_amount(amt_raw)
        date_new = parse_date_iso(date_raw)
        txn_new = classify_kind(kind_raw)
        # Rederived from date_iso for consistency. NOTE the column keeps TEXT
        # affinity (SQLite coerces these ints back to text on storage), so any
        # numeric comparison against it must CAST(contribution_year AS INTEGER).
        yr_new = int(date_new[:4]) if date_new else None
        yr_cur_int = int(yr_cur) if yr_cur not in (None, "") else None
        if txn_new is None and kind_raw:
            unknown_kinds[kind_raw] = unknown_kinds.get(kind_raw, 0) + 1
        if (amt_new, date_new, txn_new, yr_new) != (amt_cur, date_cur, txn_cur, yr_cur_int):
            updates.append((amt_new, date_new, txn_new, yr_new, rh))

    print(f"[normalize] {len(rows):,} rows scanned, {len(updates):,} need (re)derivation")
    for kind, n in sorted(unknown_kinds.items()):
        print(f"[normalize] WARNING: unmapped contribution_type ({n} rows): {kind!r}")

    if args.dry_run:
        print("[normalize] --dry-run: no writes")
        return 0

    conn.executemany(
        "UPDATE campaign_finance SET amount_real=?, date_iso=?, txn_type=?, contribution_year=? WHERE row_hash=?",
        updates,
    )
    conn.commit()

    mark_restatements(conn)

    for txn, n, total in conn.execute(
        """SELECT txn_type, COUNT(*), ROUND(SUM(amount_real), 2)
           FROM campaign_finance GROUP BY txn_type ORDER BY 2 DESC"""
    ):
        print(f"[normalize] {txn or 'NULL':14} rows={n:6,}  sum=${total or 0:,.2f}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
