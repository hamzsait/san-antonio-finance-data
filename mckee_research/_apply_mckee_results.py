"""Apply Sukh McKee-Rodriguez (D1) donor research results to the DB.

Ported from austin-finance-data/d3_research/_apply_d3_results.py -- same
columns, same confidence gate, same dedup rule -- globs
mckeebatch_*_results.json in this directory. Creates civic_affiliations on
first run (second SA scrub after Jones; the profile template renders the
affiliation cards from it automatically).

  mckeebatch_*_results.json -> donor_identities.resolved_industry /
  resolved_employer_display / resolved_confidence, plus civic_affiliations rows

Only high/medium confidence verdicts are applied; low stays unclassified.
Idempotent: re-applying overwrites the same fields; affiliations are deduped
on (canonical_name, organization). This must be re-run against the canonical
DB after the branch merges (worktree DBs are separate copies).

NOTE ordering: sa_industry_rules.py resets every non-manual resolution when it
runs, so re-run THIS apply after any rules re-derivation (llm-research beats
rules for the donors it covers because apply only fills NULLs — run rules
first, then apply).

Usage:
    python _apply_mckee_results.py            # apply
    python _apply_mckee_results.py --dry-run  # report only, no writes
"""
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "..", "san_antonio_finance.db")
DRY = "--dry-run" in sys.argv

conn = sqlite3.connect(DB, timeout=120)
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS civic_affiliations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    organization TEXT NOT NULL,
    role TEXT,
    category TEXT,
    source_url TEXT,
    notes TEXT,
    added_at TEXT DEFAULT (datetime('now')),
    UNIQUE(canonical_name, organization))""")

d_applied = d_skipped = aff_added = aff_dup = no_name = 0
cat_counts = {}
files = sorted(glob.glob(os.path.join(ROOT, "mckeebatch_*_results.json")))

for f in files:
    for v in json.load(open(f, encoding="utf-8-sig")):
        if v.get("industry") and v.get("confidence") in ("high", "medium"):
            if not DRY:
                cur.execute("""UPDATE donor_identities SET resolved_industry=?,
                               resolved_employer_display=?, resolved_confidence=?
                               WHERE donor_id=? AND resolved_industry IS NULL""",
                            (v["industry"], v.get("resolved_employer"),
                             f"llm-research-{v['confidence']}", v["donor_id"]))
                d_applied += cur.rowcount
            else:
                d_applied += 1
        else:
            d_skipped += 1

        name = cur.execute("SELECT canonical_name FROM donor_identities WHERE donor_id=?",
                           (v["donor_id"],)).fetchone()
        for a in v.get("affiliations") or []:
            if not name or not a.get("org"):
                no_name += 1
                continue
            dup = cur.execute("""SELECT 1 FROM civic_affiliations
                                 WHERE canonical_name=? AND organization=?""",
                              (name[0], a["org"])).fetchone()
            if dup:
                aff_dup += 1
                continue
            cat_counts[a.get("category") or "(uncategorized)"] = \
                cat_counts.get(a.get("category") or "(uncategorized)", 0) + 1
            if not DRY:
                cur.execute("""INSERT INTO civic_affiliations
                               (canonical_name, organization, role, category, source_url, notes, added_at)
                               VALUES (?,?,?,?,?,?,?)""",
                            (name[0], a["org"], a.get("role"), a.get("category"),
                             a.get("source_url"), v.get("evidence"),
                             datetime.now(timezone.utc).isoformat()))
            aff_added += 1

if not DRY:
    conn.commit()

print(f"{'DRY RUN — no writes' if DRY else 'APPLIED'}  ({len(files)} result files)")
print(f"donors: {d_applied} resolved, {d_skipped} left null (low/no confidence)")
print(f"civic_affiliations: {aff_added} added, {aff_dup} already present, {no_name} skipped (no name/org)")
if cat_counts:
    print("by category:")
    for k, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"   {k:34} {n}")
