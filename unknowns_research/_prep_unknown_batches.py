"""Build research batch inputs for the site-wide UNKNOWNS re-scrub.

Pool = every contribution-making donor identity with resolved_industry IS
NULL — the "Unknown" slice of every SA profile. Unlike the per-member preps
this intentionally does NOT exclude donors covered by prior research batches:
the point of this pass is to re-scrub the donors earlier passes could not
resolve (their results were low-confidence, which leaves resolved_industry
NULL), plus the small-dollar donors who fell under earlier $100 thresholds
and were never researched at all.

No dollar threshold. Batches are ordered by site-wide total descending, so
if the run is stopped early the highest-dollar unknowns are already done.

Output format matches the proven donorbatch format; "site_total" here means
total given across ALL tracked SA campaigns, and "gave_to" lists every
recipient. Runs with the v4 instructions (adds arena/Project Marvel and
charter-school affiliation searches).

Outputs: unknowns_research/unkbatch_NN.json (20 donors each)
"""
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "..", "san_antonio_finance.db")
BATCH = 20

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

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
    WHERE cf.txn_type = 'contribution'
      AND cf.donor_id IS NOT NULL
      AND cf.amount_real > 0
      AND COALESCE(cf.superseded_by, '') = ''
      AND di.resolved_industry IS NULL
    GROUP BY di.donor_id
    ORDER BY site_total DESC
""").fetchall()

print(f"UNKNOWN POOL (resolved_industry IS NULL, contribution-making): {len(donors)}")
print(f"  >= $100 site-wide: {sum(1 for d in donors if d['site_total'] >= 100)}")
print(f"  <  $100 site-wide: {sum(1 for d in donors if d['site_total'] < 100)}")

for i in range(0, len(donors), BATCH):
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
    } for d in donors[i:i + BATCH]]
    out = os.path.join(ROOT, f"unkbatch_{i // BATCH + 1:02d}.json")
    json.dump(chunk, open(out, "w", encoding="utf-8"), indent=1)

print(f"wrote {(len(donors) + BATCH - 1) // BATCH} batches of {BATCH} to {ROOT}")
