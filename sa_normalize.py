"""
sa_normalize.py
Idempotent schema migration + backfill for the normalized columns downstream
code reads (raw portal-text columns are kept as provenance, never as API):

    amount_real  REAL   from contribution_amount  "$1,000.00" -> 1000.0
    date_iso     TEXT   from contribution_date    "6/30/2025 12:00:00 AM" -> "2025-06-30"
    txn_type     TEXT   from contribution_type    kind -> contribution|expenditure|report

Safe to re-run any time: adds columns if missing, then (re)derives every row
whose derived value is NULL or stale relative to its raw value. Unknown
contribution_type kinds are left NULL and reported loudly -- extend KIND_MAP
deliberately rather than guessing.

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

    for txn, n, total in conn.execute(
        """SELECT txn_type, COUNT(*), ROUND(SUM(amount_real), 2)
           FROM campaign_finance GROUP BY txn_type ORDER BY 2 DESC"""
    ):
        print(f"[normalize] {txn or 'NULL':14} rows={n:6,}  sum=${total or 0:,.2f}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
