"""Build Opus research batch inputs for the Councilman Edward Mungia (D4) donor pool.

Pool = donors to Edward Mungia's District 4 campaign (elected outright May
2025, his first race) who gave >= $100 lifetime and aren't already covered
by a prior research batch or an existing civic_affiliations row. Ported from
austin-finance-data/d3_research (the proven district-scrub prep). Prior
coverage = every batch in every sibling *_research directory (cross-over
donors from earlier members' scrubs must not be re-scrubbed).

Output format matches the Austin donorbatch format exactly so the same v3
instructions and result-apply path work unchanged ("site_total" = total given
to the Mungia campaign). SA advantage over the Austin preps: occupations and
employer_strings are filer-reported schedule data, not blanks — researchers
start with real identity anchors.

Outputs: mungia_research/mungiabatch_NN.json (20 donors each)
"""
import glob
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "..", "san_antonio_finance.db")
BATCH = 20
MIN_TOTAL = 100
SLUG = "mungia"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# ── Prior coverage: every donor_id ever submitted to ANY research batch ──────
# (all *_research dirs — donors already covered by earlier members' scrubs must not be re-scrubbed)
covered_ids = set()
for f in sorted(glob.glob(os.path.join(ROOT, "..", "*_research", "*batch_*.json"))):
    if f.endswith("_results.json"):
        continue
    try:
        rows = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    if isinstance(rows, list):
        covered_ids.update(r["donor_id"] for r in rows
                           if isinstance(r, dict) and r.get("donor_id"))

# civic_affiliations keys on canonical_name (may not exist yet on SA)
aff_names = set()
if cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='civic_affiliations'").fetchone():
    aff_names = {r[0].strip().lower() for r in
                 cur.execute("SELECT canonical_name FROM civic_affiliations "
                             "WHERE canonical_name IS NOT NULL")}

# ── Pool ────────────────────────────────────────────────────────────────────
donors = cur.execute("""
    SELECT di.donor_id, di.canonical_name, di.canonical_zip,
           di.fec_partisan_lean, di.fec_total_donations,
           SUM(cf.amount_real) AS site_total,
           GROUP_CONCAT(DISTINCT cf.recipient) AS recipients,
           GROUP_CONCAT(DISTINCT cf.donor_reported_occupation) AS occupations,
           GROUP_CONCAT(DISTINCT cf.donor_reported_employer) AS employers,
           GROUP_CONCAT(DISTINCT cf.city_state_zip) AS locations,
           MIN(cf.date_iso) AS first_gift,
           MAX(cf.date_iso) AS last_gift
    FROM campaign_finance cf
    JOIN donor_identities di ON di.donor_id = cf.donor_id
    WHERE cf.filer_slug = ?
      AND cf.txn_type = 'contribution'
      AND cf.donor_id IS NOT NULL
      AND cf.amount_real > 0
    GROUP BY di.donor_id
    HAVING site_total >= ?
    ORDER BY site_total DESC
""", (SLUG, MIN_TOTAL)).fetchall()

pool = [d for d in donors
        if d["donor_id"] not in covered_ids
        and (d["canonical_name"] or "").strip().lower() not in aff_names]

print(f"donors >= ${MIN_TOTAL} to the Mungia campaign: {len(donors)}")
print(f"already covered by prior research:         {len(donors) - len(pool)}")
print(f"POOL TO SCRUB:                             {len(pool)}")

for i in range(0, len(pool), BATCH):
    chunk = [{
        "donor_id": d["donor_id"],
        "name": d["canonical_name"],
        "zip": d["canonical_zip"],
        "site_total": round(d["site_total"], 2),
        "gave_to": d["recipients"],
        "occupations": (d["occupations"] or "")[:150],
        "employer_strings": (d["employers"] or "")[:150],
        "locations": (d["locations"] or "")[:150],
        "first_gift": d["first_gift"],
        "last_gift": d["last_gift"],
        "fec_partisan_lean": d["fec_partisan_lean"],
        "fec_donation_count": d["fec_total_donations"] or 0,
    } for d in pool[i:i + BATCH]]
    out = os.path.join(ROOT, f"mungiabatch_{i // BATCH + 1:02d}.json")
    json.dump(chunk, open(out, "w", encoding="utf-8"), indent=1)

print(f"wrote {(len(pool) + BATCH - 1) // BATCH} batches of {BATCH} to {ROOT}")
