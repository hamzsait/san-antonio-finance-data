"""
affiliations_partisan.py
Build findings_fec_partisan.json and findings_tec_partisan.json from
existing data in the SA + Austin DBs.

FEC partisan
    Source: SA donor_identities.fec_partisan_lean / fec_total_dem / etc.
            (already populated by fec_enrich.py).
    Each donor with fec_total_donations >= 1 gets one finding. Evidence rows
    are the per-committee aggregations from fec_contributions_raw +
    fec_committee_cache.

TEC partisan
    Source: Austin DB texas_contributions_raw (~1.8M Texas state-level
            contributions). Matching is by (last, first_initial, zip5) since
            SA donors aren't pre-mapped to Austin's identity space.
    Each SA donor that matches one or more Texas contribution gets a finding.
    Lean classification uses the same TEC_COMMITTEE_LEAN dict as Austin's
    tec_partisan_aggregate.py.

Outputs:
    findings_fec_partisan.json
    findings_tec_partisan.json
"""

from __future__ import annotations
import json
import pathlib
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict

ROOT      = pathlib.Path(__file__).parent
SA_DB     = ROOT / "san_antonio_finance.db"
AUSTIN_DB = pathlib.Path(r"C:\Users\Hamza Sait\Electoral\austin-finance-data\austin_finance.db")

# Mirrors austin-finance-data/tec_partisan_aggregate.py
TEC_COMMITTEE_LEAN = {
    "00028135": ("Rep",   "Texans for Lawsuit Reform PAC"),
    "00015555": ("Rep",   "Associated Republicans of Texas Campaign Fund"),
    "00089881": ("Rep",   "Defend Texas Liberty"),
    "00061927": ("Rep",   "Empower Texans PAC (terminated)"),
    "00015666": ("Dem",   "Texas Trial Lawyers Association PAC"),
    "00070864": ("Other", "Texas Oil and Gas Association GGC"),
    "00015487": ("Other", "Texas REALTORS PAC (TREPAC)"),
    "00017303": ("Other", "Texas Apartment Association PAC"),
    "00015700": ("Other", "GHBA HOME-PAC"),
    "00035370": ("Other", "Austin Board of Realtors PAC"),
}


# ── Helpers ────────────────────────────────────────────────────────────────
def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")


def normalize_donor_name(canonical_name: str) -> tuple[str, str]:
    """donor_identities canonical_name is e.g. 'Aguilar, Fernando' or
    'Smith, John A.'. Return (last_lower, first_initial_lower)."""
    s = _ascii(canonical_name).lower().strip()
    s = re.sub(r"[^a-z, ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if "," in s:
        last, _, first_part = s.partition(",")
        last = last.strip()
        first_tokens = first_part.strip().split()
        first_init = first_tokens[0][:1] if first_tokens else ""
    else:
        toks = s.split()
        last = toks[-1] if toks else ""
        first_init = toks[0][:1] if len(toks) > 1 else ""
    return last, first_init


def lean_label(weighted: float) -> str:
    if weighted is None:
        return "FEC: No partisan committees"
    if weighted >= 0.9:
        return "FEC Partisan Lean: Strong Democrat"
    if weighted >= 0.6:
        return "FEC Partisan Lean: Lean Democrat"
    if weighted >= 0.4:
        return "FEC Partisan Lean: Mixed"
    if weighted >= 0.1:
        return "FEC Partisan Lean: Lean Republican"
    return "FEC Partisan Lean: Strong Republican"


# ── FEC partisan ───────────────────────────────────────────────────────────
def build_fec_partisan() -> dict:
    """Read SA donor_identities + fec_contributions_raw + fec_committee_cache
    and emit a findings record per donor with evidence per (donor, committee)."""
    conn = sqlite3.connect(str(SA_DB))
    conn.row_factory = sqlite3.Row
    findings = []

    # All matched donors with at least one FEC contribution
    donors = conn.execute("""
        SELECT donor_id, canonical_name,
               fec_partisan_lean, fec_total_dem, fec_total_rep, fec_total_other,
               fec_total_donations
        FROM donor_identities
        WHERE COALESCE(fec_total_donations, 0) > 0
    """).fetchall()

    for d in donors:
        donor_id = d["donor_id"]
        # Aggregate per committee for evidence
        rows = conn.execute("""
            SELECT fcr.committee_id,
                   fcc.committee_name,
                   fcc.classification,
                   COUNT(*)                        AS n,
                   ROUND(SUM(fcr.contribution_amount), 2) AS total,
                   MIN(fcr.contribution_date)      AS first_dt,
                   MAX(fcr.contribution_date)      AS last_dt
            FROM fec_contributions_raw fcr
            LEFT JOIN fec_committee_cache fcc ON fcc.committee_id = fcr.committee_id
            WHERE fcr.donor_id = ?
              AND fcr.contribution_amount > 0
            GROUP BY fcr.committee_id
            ORDER BY total DESC
        """, (donor_id,)).fetchall()

        if not rows:
            continue

        evidence = []
        first_seen = None
        last_seen = None
        for r in rows:
            cls = r["classification"] or "Other"
            cname = r["committee_name"] or r["committee_id"]
            evidence.append({
                "source": "FEC schedule_a",
                "source_url": f"https://www.fec.gov/data/committee/{r['committee_id']}/",
                "evidence_text": f"Gave ${r['total']:,.0f} across {r['n']} contributions to {cname} (FEC class: {cls})",
                "contribution_id": None,
                "committee_id": r["committee_id"],
                "committee_name": cname,
                "amount": float(r["total"] or 0),
                "date": r["last_dt"],
                "raw_data": None,
                "rule": f"fec_committee_classification:{cls}",
            })
            if r["first_dt"]:
                first_seen = r["first_dt"] if first_seen is None or r["first_dt"] < first_seen else first_seen
            if r["last_dt"]:
                last_seen = r["last_dt"] if last_seen is None or r["last_dt"] > last_seen else last_seen

        weighted = d["fec_partisan_lean"]
        notes = (
            f"D=${d['fec_total_dem'] or 0:,.0f}  "
            f"R=${d['fec_total_rep'] or 0:,.0f}  "
            f"Other=${d['fec_total_other'] or 0:,.0f}  "
            f"({d['fec_total_donations']} contributions)"
        )

        # Pick label by weighted lean
        partisan_amt = (d["fec_total_dem"] or 0) + (d["fec_total_rep"] or 0)
        if partisan_amt > 0:
            wl = (d["fec_total_dem"] or 0) / partisan_amt
        else:
            wl = None
        label = lean_label(wl)

        # Total amount = D+R partisan amount (excluding Other)
        total_amount = partisan_amt or float(
            (d["fec_total_dem"] or 0) + (d["fec_total_rep"] or 0) + (d["fec_total_other"] or 0)
        )

        findings.append({
            "donor_id": donor_id,
            "label": label,
            "total_amount": round(total_amount, 2),
            "confidence": "high",
            "first_seen": first_seen,
            "last_seen": last_seen,
            "notes": notes,
            "sensitive": False,
            "evidence": evidence,
        })

    conn.close()
    return {
        "category": "fec_partisan",
        "rules": [
            {"name": "fec_committee_classification:Dem",
             "description": "FEC committee classified as Dem in fec_committee_cache (party_code=DEM/D, or matches DEM_PATTERNS regex on committee name)"},
            {"name": "fec_committee_classification:Rep",
             "description": "FEC committee classified as Rep in fec_committee_cache"},
            {"name": "fec_committee_classification:Other",
             "description": "Non-partisan or unclassifiable committee"},
        ],
        "findings": findings,
    }


# ── TEC partisan ───────────────────────────────────────────────────────────
def build_tec_partisan() -> dict:
    """Match SA donors against the Texas state-level contributions in
    Austin's texas_contributions_raw via (last, first_initial, zip5)."""
    if not AUSTIN_DB.exists():
        print(f"[tec] WARN: Austin DB not found at {AUSTIN_DB}; skipping TEC pass")
        return {"category": "tec_partisan", "rules": [], "findings": []}

    sa = sqlite3.connect(str(SA_DB))
    sa.row_factory = sqlite3.Row
    sa_donors = sa.execute("""
        SELECT donor_id, canonical_name, canonical_zip
        FROM donor_identities
    """).fetchall()
    sa.close()

    # Build name lookup: (last, first_init, zip5) -> donor_id
    by_key: dict[tuple, str] = {}
    for d in sa_donors:
        last, fi = normalize_donor_name(d["canonical_name"] or "")
        zip5 = (d["canonical_zip"] or "")[:5]
        if not last or not fi or not zip5:
            continue
        by_key.setdefault((last, fi, zip5), d["donor_id"])

    if not by_key:
        return {"category": "tec_partisan", "rules": [], "findings": []}

    # For each tracked TEC committee, pull all Texas contributions and match
    aus = sqlite3.connect(str(AUSTIN_DB))
    aus.row_factory = sqlite3.Row
    cid_list = list(TEC_COMMITTEE_LEAN.keys())
    placeholders = ",".join("?" for _ in cid_list)
    rows = aus.execute(f"""
        SELECT contributor_last, contributor_first, contributor_zip,
               contributor_city, contributor_employer, contributor_occupation,
               filer_ident, filer_name, contribution_amount, contribution_dt,
               id AS tec_id
        FROM texas_contributions_raw
        WHERE filer_ident IN ({placeholders})
          AND contribution_amount > 0
    """, cid_list).fetchall()
    aus.close()

    # Group matches by donor_id, then by committee
    per_donor: dict[str, dict] = {}
    for r in rows:
        last = (r["contributor_last"] or "").lower().strip()
        first_init = ((r["contributor_first"] or "").lower().strip() + " ")[:1]
        zip5 = (r["contributor_zip"] or "")[:5]
        donor_id = by_key.get((last, first_init, zip5))
        if not donor_id:
            continue
        cid = r["filer_ident"]
        lean, cname = TEC_COMMITTEE_LEAN[cid]
        bucket = per_donor.setdefault(donor_id, {
            "totals": {"Dem": 0.0, "Rep": 0.0, "Other": 0.0},
            "evidence": [],
            "first_seen": None,
            "last_seen": None,
        })
        amt = float(r["contribution_amount"] or 0)
        bucket["totals"][lean] += amt
        date = r["contribution_dt"]
        # TEC dates are YYYYMMDD strings — convert to YYYY-MM-DD
        if date and len(date) == 8 and date.isdigit():
            date_iso = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        else:
            date_iso = date
        if date_iso:
            if bucket["first_seen"] is None or date_iso < bucket["first_seen"]:
                bucket["first_seen"] = date_iso
            if bucket["last_seen"] is None or date_iso > bucket["last_seen"]:
                bucket["last_seen"] = date_iso
        bucket["evidence"].append({
            "source": "Texas Ethics Commission bulk CSV (austin DB)",
            "source_url": f"https://www.ethics.state.tx.us/searchcf2/CFFilerSearch.aspx?ident={cid}",
            "evidence_text": f"Gave ${amt:,.2f} to {cname} (TEC filer {cid}, classified {lean})",
            "contribution_id": f"texas_contributions_raw.id={r['tec_id']}",
            "committee_id": cid,
            "committee_name": cname,
            "amount": amt,
            "date": date_iso,
            "raw_data": None,
            "rule": f"tec_committee_classification:{lean}",
        })

    findings = []
    for donor_id, b in per_donor.items():
        d = b["totals"]["Dem"]; r = b["totals"]["Rep"]; o = b["totals"]["Other"]
        partisan = d + r
        wl = d / partisan if partisan > 0 else None
        label_prefix = lean_label(wl).replace("FEC Partisan Lean", "TEC Partisan Lean")
        notes = f"D=${d:,.0f}  R=${r:,.0f}  Other=${o:,.0f}  ({len(b['evidence'])} contributions)"
        # Confidence: high since the (last, first_init, zip5) match is fairly strict
        findings.append({
            "donor_id": donor_id,
            "label": label_prefix if partisan > 0 else "TEC: Non-partisan giving only",
            "total_amount": round(d + r + o, 2),
            "confidence": "high",
            "first_seen": b["first_seen"],
            "last_seen": b["last_seen"],
            "notes": notes,
            "sensitive": False,
            "evidence": b["evidence"],
        })

    return {
        "category": "tec_partisan",
        "rules": [
            {"name": "tec_committee_classification:Dem",
             "description": "Texas Trial Lawyers Association PAC (state-level Dem-aligned)"},
            {"name": "tec_committee_classification:Rep",
             "description": "Texans for Lawsuit Reform / Associated Republicans of Texas / Defend Texas Liberty / Empower Texans"},
            {"name": "tec_committee_classification:Other",
             "description": "Trade-association PACs (TXOGA, Texas REALTORS, TAA, GHBA HOME, ABoR Realtors); industry rather than party"},
            {"name": "match_key",
             "description": "SA donor matched to TEC contributor on (last_name, first_initial, zip5). Exact zip required to avoid name collisions."},
        ],
        "findings": findings,
    }


# ── Main ───────────────────────────────────────────────────────────────────
def main() -> int:
    print("[fec] building findings_fec_partisan.json …")
    fec = build_fec_partisan()
    fec_path = ROOT / "findings_fec_partisan.json"
    fec_path.write_text(json.dumps(fec, separators=(",", ":")), encoding="utf-8")
    print(f"  {fec_path.name}: {len(fec['findings'])} findings, "
          f"{sum(len(f['evidence']) for f in fec['findings'])} evidence rows, "
          f"{fec_path.stat().st_size:,} bytes")

    print("[tec] building findings_tec_partisan.json …")
    tec = build_tec_partisan()
    tec_path = ROOT / "findings_tec_partisan.json"
    tec_path.write_text(json.dumps(tec, separators=(",", ":")), encoding="utf-8")
    print(f"  {tec_path.name}: {len(tec['findings'])} findings, "
          f"{sum(len(f['evidence']) for f in tec['findings'])} evidence rows, "
          f"{tec_path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
