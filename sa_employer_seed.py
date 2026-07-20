"""
sa_employer_seed.py
Create SA's employer_identities table and seed it with the Austin project's
employer -> industry knowledge base, kept in the committed employer_seed.json.

Why: the SA portal publishes no donor employer/occupation, so industry
resolution runs off the FEC crosswalk (fec_enrich.py). fec_enrich's
resolve_from_fec_employers() matches FEC employer strings against
employer_identities — a table SA never had. Austin's classified employers
(USAA, H-E-B, law firms, national employers...) are generic knowledge and use
the same industry taxonomy the site renders, so they are the right seed.

Also adds the donor-level resolution columns to donor_identities
(resolved_industry / resolved_employer_display / resolved_confidence),
matching Austin's donor-first COALESCE convention.

Idempotent. Two modes:
    python sa_employer_seed.py                 # load employer_seed.json into the DB
    python sa_employer_seed.py --export --austin-db PATH   # regenerate the JSON
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "san_antonio_finance.db"
SEED_FILE = ROOT / "employer_seed.json"

DONOR_COLS = [
    "resolved_industry TEXT",
    "resolved_employer_display TEXT",
    "resolved_confidence TEXT",
    # Austin-parity columns so the ported generate_profile_data.py runs
    # unchanged. TEC (state PAC) enrichment and the IP-spectrum research
    # haven't been run for SA donors — these stay 0/NULL until they are.
    "tec_total_dem REAL DEFAULT 0",
    "tec_total_rep REAL DEFAULT 0",
    "tec_total_other REAL DEFAULT 0",
    "tec_total_donations INTEGER DEFAULT 0",
    "tec_matched INTEGER DEFAULT 0",
    "ip_spectrum TEXT",
    "ip_tier TEXT",
    "ip_total REAL",
    "ip_committees TEXT",
]


def export(austin_db: str) -> None:
    a = sqlite3.connect(austin_db)
    rows = a.execute(
        """SELECT employer_id, canonical_name, industry
           FROM employer_identities
           WHERE industry IS NOT NULL AND TRIM(canonical_name) <> ''
           ORDER BY canonical_name"""
    ).fetchall()
    SEED_FILE.write_text(
        json.dumps(
            {"source": "austin-finance-data employer_identities", "employers":
             [{"employer_id": e, "canonical_name": n, "industry": i} for e, n, i in rows]},
            indent=0, ensure_ascii=False),
        encoding="utf-8")
    print(f"[seed] exported {len(rows):,} classified employers -> {SEED_FILE.name}")


def load(db: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS employer_identities (
               employer_id    TEXT PRIMARY KEY,
               canonical_name TEXT,
               industry       TEXT,
               interest_tags  TEXT,
               seed_source    TEXT
           )"""
    )
    for table, cols in (("donor_identities", DONOR_COLS),
                        ("fec_committee_cache", ["ip_category TEXT"]),
                        ("employer_identities", ["interest_tags TEXT"])):
        for col_def in cols:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except sqlite3.OperationalError:
                pass  # already exists

    seed = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    conn.executemany(
        """INSERT INTO employer_identities (employer_id, canonical_name, industry, seed_source)
           VALUES (?, ?, ?, 'austin-seed')
           ON CONFLICT(employer_id) DO UPDATE SET
               canonical_name=excluded.canonical_name,
               industry=excluded.industry""",
        [(e["employer_id"], e["canonical_name"], e["industry"]) for e in seed["employers"]],
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM employer_identities").fetchone()[0]
    print(f"[seed] employer_identities now has {n:,} rows; donor_identities has resolved_* columns")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--export", action="store_true")
    p.add_argument("--austin-db",
                   default="C:/Users/Hamza Sait/Electoral/decode-politics/austin-finance-data/austin_finance.db")
    args = p.parse_args()
    if args.export:
        export(args.austin_db)
    load(args.db)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
