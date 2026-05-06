"""
generate_profile_data.py — San Antonio version
Generate {slug}_data.json and {slug}_all_donations.json for one council member.

This is the SA-stripped equivalent of Austin's generate_profile_data.py.
PoC scope: hero stats, by-year, top donors, partisan lean (FEC-only),
raw donations. Sections that need enrichment we haven't built for SA yet
(employer_identities → industry breakdown, TEC, IP/civic affiliations) are
emitted as empty arrays / null so the existing Austin profile_template.html
renders gracefully.

Usage:
    python generate_profile_data.py --slug galvan
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "san_antonio_finance.db"


def parse_amount(raw: str | None) -> float:
    if not raw:
        return 0.0
    try:
        return float(re.sub(r"[^0-9.\-]", "", raw))
    except ValueError:
        return 0.0


def parse_date_for_sort(raw: str | None) -> str:
    """mm/dd/yyyy [hh:mm:ss [AM/PM]] -> yyyy-mm-dd for sorting."""
    if not raw:
        return ""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if not m:
        return ""
    return f"{int(m.group(3)):04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--slug", required=True, help="council_members.slug")
    p.add_argument("--output-dir", default=str(ROOT))
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Resolve member
    member = cur.execute(
        "SELECT slug, district, full_name FROM council_members WHERE slug=?",
        (args.slug,),
    ).fetchone()
    if not member:
        print(f"ERROR: no council_members row for slug={args.slug!r}", file=sys.stderr)
        return 2

    slug = member["slug"]
    candidate_name = member["full_name"]
    district = member["district"]

    # Pull all rows for this filer (contributions only — exclude expenditures and report-type rows)
    rows = cur.execute(
        """
        SELECT donor, donor_id, contribution_amount, contribution_date,
               contribution_year, donor_type, city_state_zip,
               contribution_type, report_filed, view_report
        FROM campaign_finance
        WHERE filer_slug = ?
          AND contribution_type = 'Monetary Political Contributions'
        """,
        (slug,),
    ).fetchall()

    if not rows:
        print(f"ERROR: no contribution rows in DB for slug={slug!r}", file=sys.stderr)
        return 2

    print(f"[generate] {candidate_name} ({district}): {len(rows)} contribution rows")

    # ── Hero stats ────────────────────────────────────────────────────────────
    total_raised = sum(parse_amount(r["contribution_amount"]) for r in rows)
    unique_donors = len({r["donor_id"] for r in rows if r["donor_id"]})
    total_contributions = len(rows)

    # SA has no employer-industry classification yet; treat these as 0 for now.
    employer_affiliated_pct = 0.0
    top_industry = "Unknown"

    hero = {
        "total_raised": int(round(total_raised)),
        "unique_donors": unique_donors,
        "total_contributions": total_contributions,
        "employer_affiliated_pct": employer_affiliated_pct,
        "top_industry": top_industry,
    }

    # ── By year ───────────────────────────────────────────────────────────────
    year_buckets: dict[str, list[float]] = {}
    for r in rows:
        y = (r["contribution_year"] or "").strip()
        if not y:
            continue
        year_buckets.setdefault(y, []).append(parse_amount(r["contribution_amount"]))
    by_year = [
        {
            "year": y,
            "count": len(amounts),
            "total": int(round(sum(amounts))),
        }
        for y, amounts in sorted(year_buckets.items())
    ]

    # ── Top donors ────────────────────────────────────────────────────────────
    # Aggregate per donor_identity
    donor_rows = cur.execute(
        """
        SELECT
            di.donor_id,
            di.canonical_name,
            di.canonical_zip,
            di.canonical_employer,
            di.fec_partisan_lean,
            di.fec_total_dem,
            di.fec_total_rep,
            di.fec_total_other,
            di.fec_total_donations,
            di.fec_matched,
            COUNT(cf.row_hash) AS gift_count,
            SUM(CAST(REPLACE(REPLACE(cf.contribution_amount,'$',''),',','') AS REAL))
                AS local_total
        FROM donor_identities di
        JOIN campaign_finance cf ON cf.donor_id = di.donor_id
        WHERE cf.filer_slug = ?
          AND cf.contribution_type = 'Monetary Political Contributions'
          AND cf.donor_type = 'INDIVIDUAL'
        GROUP BY di.donor_id
        ORDER BY local_total DESC
        """,
        (slug,),
    ).fetchall()

    top_donors = []
    for d in donor_rows[:10]:
        top_donors.append({
            "name": d["canonical_name"] or "",
            "employer": (d["canonical_employer"] or "").title() if d["canonical_employer"] else "",
            "industry": "Unknown",
            "tags": "",
            "total": int(round(d["local_total"] or 0)),
            "count": d["gift_count"] or 0,
        })

    # ── Partisan lean (FEC only — SA has no TEC ingest yet) ───────────────────
    partisan_lean = None
    matched = [d for d in donor_rows if (d["fec_total_dem"] or 0) + (d["fec_total_rep"] or 0) > 0]
    if matched:
        buckets = [
            {"label": "Strong D", "min": 0.9,   "max": 1.01,  "donors": 0, "total": 0},
            {"label": "Lean D",   "min": 0.6,   "max": 0.9,   "donors": 0, "total": 0},
            {"label": "Mixed",    "min": 0.4,   "max": 0.6,   "donors": 0, "total": 0},
            {"label": "Lean R",   "min": 0.1,   "max": 0.4,   "donors": 0, "total": 0},
            {"label": "Strong R", "min": -0.01, "max": 0.1,   "donors": 0, "total": 0},
        ]
        donors_list = []
        weighted_lean_sum = 0.0
        weighted_amt = 0.0
        dem_donors = rep_donors = mixed_donors = 0
        for d in matched:
            dem = d["fec_total_dem"] or 0
            rep = d["fec_total_rep"] or 0
            other = d["fec_total_other"] or 0
            local = d["local_total"] or 0
            partisan_amount = dem + rep
            if partisan_amount <= 0:
                continue
            lean = dem / partisan_amount
            for b in buckets:
                if b["min"] <= lean < b["max"]:
                    b["donors"] += 1
                    b["total"] += round(local, 2)
                    break
            if lean >= 0.6:
                dem_donors += 1
            elif lean <= 0.4:
                rep_donors += 1
            else:
                mixed_donors += 1
            if local > 0:
                weighted_lean_sum += lean * local
                weighted_amt += local
            donors_list.append({
                "id": d["donor_id"],
                "name": d["canonical_name"],
                "lean": round(lean, 3),
                "dem": round(dem, 0),
                "rep": round(rep, 0),
                "other": round(other, 0),
                "fec_n": d["fec_total_donations"] or 0,
                "tec_n": 0,
                "fec_dem": round(dem, 0),
                "fec_rep": round(rep, 0),
                "tec_dem": 0,
                "tec_rep": 0,
                "local": round(local, 0),
            })
        donors_list.sort(key=lambda x: -(x["dem"] + x["rep"]))
        weighted_avg = round(weighted_lean_sum / weighted_amt, 3) if weighted_amt > 0 else None
        partisan_lean = {
            "matched_donors": len(donors_list),
            "total_donors": unique_donors,
            "dem_donors": dem_donors,
            "rep_donors": rep_donors,
            "mixed_donors": mixed_donors,
            "fec_only": len(donors_list),
            "tec_only": 0,
            "both_sources": 0,
            "weighted_lean": weighted_avg,
            "buckets": buckets,
            "donors": donors_list,
            "donor_committees": {},
        }
        print(f"[generate] partisan lean: {len(donors_list)} donors matched, "
              f"D={dem_donors} R={rep_donors} M={mixed_donors}, weighted={weighted_avg}")

    # ── Election cycles (for Galvan: just one — the 2025 race) ────────────────
    # If the candidate has multi-cycle history this will need to grow per-slug.
    cycles = [{
        "label": "This Cycle",
        "election_year": 2025,
        "year_range": (
            f"{by_year[0]['year']}-present" if by_year else "?"
        ),
        "hero": hero,
        "interest_groups": [],
        "notable_firms": [],
        "top_donors": top_donors,
    }]

    # ── All donations (one row per gift, for the table view) ──────────────────
    donations_rows = cur.execute(
        """
        SELECT di.canonical_name, cf.contribution_date, cf.contribution_amount,
               COALESCE(di.canonical_employer, '') AS employer,
               'Unknown' AS industry,
               cf.city_state_zip
        FROM campaign_finance cf
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE cf.filer_slug = ?
          AND cf.contribution_type = 'Monetary Political Contributions'
        ORDER BY cf.contribution_date DESC
        """,
        (slug,),
    ).fetchall()
    all_donations = [
        [
            r["canonical_name"] or "",
            r["contribution_date"] or "",
            round(parse_amount(r["contribution_amount"]), 2),
            r["employer"] or "",
            r["industry"] or "Unknown",
            (r["city_state_zip"] or "").strip(),
        ]
        for r in donations_rows
    ]

    # ── Assemble payload (mirroring Austin's shape; empty buckets where SA
    #    enrichment hasn't been built) ─────────────────────────────────────────
    meta = {
        "candidate_name": candidate_name,
        "candidate_slug": slug,
        "office": f"San Antonio City Council, {district}",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    payload = {
        "meta": meta,
        "hero": hero,
        "by_year": by_year,
        "interest_groups": [],
        "notable_firms": [],
        "top_donors": top_donors,
        "cycles": cycles,
        "partisan_lean": partisan_lean,
        "ip_spectrum": None,
        "civic_affiliations": None,
    }

    out_dir = Path(args.output_dir)
    data_path = out_dir / f"{slug}_data.json"
    don_path = out_dir / f"{slug}_all_donations.json"

    data_path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    don_path.write_text(json.dumps(all_donations, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    print(f"[generate] wrote {data_path.name}  ({data_path.stat().st_size:,} bytes)")
    print(f"[generate] wrote {don_path.name}  ({don_path.stat().st_size:,} bytes, {len(all_donations):,} records)")
    print()
    print(f"=== Verification ===")
    print(f"  Total raised:        ${hero['total_raised']:,}")
    print(f"  Unique donors:       {hero['unique_donors']:,}")
    print(f"  Total contributions: {hero['total_contributions']:,}")
    print(f"  By year:")
    for y in by_year:
        print(f"    {y['year']}: {y['count']:,} gifts, ${y['total']:,}")
    print(f"  Top 3 donors:")
    for d in top_donors[:3]:
        print(f"    {d['name']}: ${d['total']:,} ({d['count']} gifts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
