"""
sa_append.py
Incremental refresher: re-scrape every tracked filer and append new rows.

SA's scraper is already append-only by row_hash (never drop/rebuild — the
Austin lesson), so this is a thin roster-driven loop over fetch_data.py.
Default filer set is every council_members row with is_incumbent=1; add
non-incumbents we track (e.g. shaikh) with --extra.

SA files semiannually plus 30/8-day pre-election windows, so most runs will
find nothing new for most filers — that is expected, not a failure.

Usage:
    python sa_append.py                      # all incumbents
    python sa_append.py --extra shaikh       # incumbents + shaikh
    python sa_append.py --only galvan,shaikh # exactly these slugs
    python sa_append.py --dry-run            # scrape + report, no DB writes
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "san_antonio_finance.db"
FETCH = ROOT / "fetch_data.py"
START_YEAR = 2016  # portal year floor; profile layer decides what to display

INSERTED_RE = re.compile(r"inserted=(\d+)\s+skipped_existing=(\d+)")


def filer_stats(conn: sqlite3.Connection, slug: str) -> tuple[int, int]:
    """(rows, distinct donors with contributions) for a filer."""
    rows = conn.execute(
        "SELECT COUNT(*) FROM campaign_finance WHERE filer_slug=?", (slug,)
    ).fetchone()[0]
    donors = conn.execute(
        """SELECT COUNT(DISTINCT donor) FROM campaign_finance
           WHERE filer_slug=? AND txn_type='contribution'""", (slug,)
    ).fetchone()[0]
    return rows, donors


def main() -> int:
    p = argparse.ArgumentParser(description="Append new portal rows for tracked filers.")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--only", help="comma-separated slugs (exactly these, no roster query)")
    p.add_argument("--extra", action="append", default=[],
                   help="non-incumbent slug to include (repeatable)")
    p.add_argument("--end-year", type=int, default=2026)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    if args.only:
        slugs = [s.strip() for s in args.only.split(",") if s.strip()]
    else:
        slugs = [r[0] for r in conn.execute(
            "SELECT slug FROM council_members WHERE is_incumbent=1 ORDER BY district"
        )]
        slugs += [s for s in args.extra if s not in slugs]

    print(f"[append] {len(slugs)} filers: {', '.join(slugs)}")
    totals = {"inserted": 0, "failed": []}
    for slug in slugs:
        before_rows, before_donors = filer_stats(conn, slug)
        cmd = [sys.executable, str(FETCH), "--db", args.db, "--slug", slug,
               "--start-year", str(START_YEAR), "--end-year", str(args.end_year)]
        if args.dry_run:
            cmd.append("--dry-run")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[append] {slug}: FAILED\n{r.stdout[-500:]}\n{r.stderr[-500:]}")
            totals["failed"].append(slug)
            continue
        m = INSERTED_RE.search(r.stdout)
        after_rows, after_donors = filer_stats(conn, slug)
        if args.dry_run:
            scraped = re.search(r"total rows scraped: ([\d,]+)", r.stdout)
            print(f"[append] {slug}: dry-run, scraped {scraped.group(1) if scraped else '?'} rows")
        else:
            inserted = int(m.group(1)) if m else after_rows - before_rows
            totals["inserted"] += inserted
            new_donors = after_donors - before_donors
            flag = "" if inserted == 0 else f"  <- +{inserted} rows, +{new_donors} donors"
            print(f"[append] {slug}: rows {before_rows}->{after_rows}{flag}")

    print(f"[append] done. total new rows: {totals['inserted']}"
          + (f"  FAILED: {', '.join(totals['failed'])}" if totals["failed"] else ""))
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
