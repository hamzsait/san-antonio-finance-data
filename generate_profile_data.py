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

    # ── Affiliations + receipts ───────────────────────────────────────────────
    # For each donor who gave to THIS candidate, pull every affiliation row
    # (and its evidence). We build two structures:
    #   donor_affiliations: { donor_id: [ {category, label, ...}, ... ] }
    #   affiliations_summary: per-category roll-up across this candidate's donors
    candidate_donor_ids = {
        r[0] for r in cur.execute(
            "SELECT DISTINCT donor_id FROM campaign_finance "
            "WHERE filer_slug=? AND donor_id IS NOT NULL", (slug,)
        ).fetchall()
    }

    has_affil = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='donor_affiliations'"
    ).fetchone() is not None

    donor_affiliations: dict[str, list] = {}
    affiliations_summary: dict = {"categories": []}

    if has_affil and candidate_donor_ids:
        ph = ",".join("?" for _ in candidate_donor_ids)
        aff_rows = cur.execute(f"""
            SELECT a.affiliation_id, a.donor_id, a.category, a.label,
                   a.total_amount, a.confidence, a.first_seen, a.last_seen,
                   a.notes, a.sensitive,
                   di.canonical_name
            FROM donor_affiliations a
            JOIN donor_identities di ON di.donor_id = a.donor_id
            WHERE a.donor_id IN ({ph})
        """, list(candidate_donor_ids)).fetchall()

        if aff_rows:
            aff_ids = [r["affiliation_id"] for r in aff_rows]
            evp = ",".join("?" for _ in aff_ids)
            ev_rows = cur.execute(f"""
                SELECT affiliation_id, source, source_url, evidence_text,
                       contribution_id, committee_id, committee_name,
                       amount, date, raw_data, rule
                FROM donor_affiliation_evidence
                WHERE affiliation_id IN ({evp})
                ORDER BY date DESC, amount DESC
            """, aff_ids).fetchall()
            ev_by_aff: dict[int, list] = {}
            for er in ev_rows:
                ev_by_aff.setdefault(er["affiliation_id"], []).append({
                    "source":          er["source"],
                    "source_url":      er["source_url"],
                    "evidence_text":   er["evidence_text"],
                    "contribution_id": er["contribution_id"],
                    "committee_id":    er["committee_id"],
                    "committee_name":  er["committee_name"],
                    "amount":          er["amount"],
                    "date":            er["date"],
                    "rule":            er["rule"],
                })

            CAT_LABELS = {
                "aipac":            "AIPAC",
                "adl":              "ADL",
                "zionist_general":  "Israel-aligned giving (non-AIPAC)",
                "oil_gas":          "Oil & Gas",
                "real_estate":      "Real Estate",
                "mic":              "Military Industrial Complex",
                "fec_partisan":     "Federal partisan giving (FEC)",
                "tec_partisan":     "Texas state partisan giving (TEC)",
            }
            cat_buckets: dict[str, dict] = {}

            for ar in aff_rows:
                cat = ar["category"]
                entry = {
                    "category":     cat,
                    "category_label": CAT_LABELS.get(cat, cat),
                    "label":        ar["label"],
                    "total_amount": ar["total_amount"],
                    "confidence":   ar["confidence"],
                    "first_seen":   ar["first_seen"],
                    "last_seen":    ar["last_seen"],
                    "notes":        ar["notes"],
                    "sensitive":    bool(ar["sensitive"]),
                    "evidence":     ev_by_aff.get(ar["affiliation_id"], []),
                }
                donor_affiliations.setdefault(ar["donor_id"], []).append(entry)

                b = cat_buckets.setdefault(cat, {
                    "category":      cat,
                    "category_label": CAT_LABELS.get(cat, cat),
                    "donor_count":   0,
                    "total_amount":  0.0,
                    "confidence_breakdown": {"high": 0, "medium": 0, "low": 0},
                    "sensitive_count": 0,
                    "top_donors":    [],
                })
                b["donor_count"] += 1
                if ar["total_amount"]:
                    b["total_amount"] += float(ar["total_amount"])
                conf = (ar["confidence"] or "medium").lower()
                if conf in b["confidence_breakdown"]:
                    b["confidence_breakdown"][conf] += 1
                if ar["sensitive"]:
                    b["sensitive_count"] += 1
                b["top_donors"].append({
                    "donor_id":     ar["donor_id"],
                    "name":         ar["canonical_name"],
                    "label":        ar["label"],
                    "total_amount": ar["total_amount"],
                    "confidence":   ar["confidence"],
                })

            for cat, b in cat_buckets.items():
                b["top_donors"].sort(
                    key=lambda d: (-(d["total_amount"] or 0), d["name"] or "")
                )
                b["top_donors"] = b["top_donors"][:10]
                b["total_amount"] = round(b["total_amount"], 2)
            # Sort categories by donor_count desc; partisan categories come first
            CAT_ORDER = ["fec_partisan", "tec_partisan", "aipac", "adl",
                         "zionist_general", "oil_gas", "real_estate", "mic"]
            ordered = sorted(
                cat_buckets.values(),
                key=lambda b: (CAT_ORDER.index(b["category"]) if b["category"] in CAT_ORDER else 99,)
            )
            affiliations_summary["categories"] = ordered

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
        # Per-donor affiliations + per-candidate roll-up. The new affiliations
        # pipeline (donor_affiliations table) populates these. If the table
        # doesn't exist yet, both fields are empty and the frontend hides the
        # corresponding sections.
        "affiliations_summary": affiliations_summary,
        "donor_affiliations": donor_affiliations,
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
