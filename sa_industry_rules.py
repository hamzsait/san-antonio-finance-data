"""
sa_industry_rules.py
Deterministic donor -> industry resolution driver for SA.

Sources, in priority order (first hit wins; 'manual' resolutions are never
touched):

  1. local-employer          portal-reported employer matched to a known
                             employer_identities name (SA reports employer +
                             occupation per itemized contribution via the
                             schedule-detail postback — fetch_data.py fills
                             donor_reported_employer / _occupation)
  2. local-employer-rules    portal-reported employer hit an SA-anchor
  3. local-occupation-rules  portal-reported occupation keyword
  4. fec-employer            FEC-reported employer matched to a known name
                             (fec_enrich.resolve_from_fec_employers)
  5. sa-employer-rules       FEC-reported employer hit an SA-anchor
  6. fec-occupation-rules    FEC-reported occupation keyword

'-noemp' suffix on occupation-rule tags means the display string is just the
occupation title (no real employer) — the profile's "Firms with 3+ donors"
panel excludes those ("Attorney" is not a firm).

Each run RE-DERIVES every non-manual resolution from scratch (reset first),
so the priority order holds no matter what ran before. Idempotent.

Usage:
    python sa_industry_rules.py [--db PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "san_antonio_finance.db"

NOISE_INDUSTRIES = {"Not Employed", "Self-Employed", "Student", "Unknown",
                    "Unknown / Unclassified", None}
NOISE_EMP = ("SELF", "NONE", "N/A", "RETIRED", "NOT EMPLOYED", "UNEMPLOYED",
             "HOMEMAKER", "UNION", "PAC")

# SA-anchor employers (substring match, uppercase). Industry labels must come
# from the site taxonomy (INDUSTRY_COLORS in generate_profile_data.py).
SA_EMPLOYERS = [
    ("USAA",                    "Finance"),
    ("H-E-B",                   "Retail"),
    ("HEB ",                    "Retail"),
    ("FROST BANK",              "Finance"),
    ("CPS ENERGY",              "Energy / Environment"),
    ("VALERO",                  "Energy / Environment"),
    ("NUSTAR",                  "Energy / Environment"),
    ("RACKSPACE",               "Technology"),
    ("UT HEALTH",               "Healthcare"),
    ("UNIV OF TEXAS HEALTH",    "Healthcare"),
    ("UNIVERSITY HEALTH",       "Healthcare"),
    ("METHODIST HEALTHCARE",    "Healthcare"),
    ("BAPTIST HEALTH",          "Healthcare"),
    ("UTSA",                    "Education"),
    ("UNIVERSITY OF TEXAS AT SAN ANTONIO", "Education"),
    ("TRINITY UNIVERSITY",      "Education"),
    ("ALAMO COLLEGES",          "Education"),
    ("NORTHSIDE ISD",           "Education"),
    ("NORTH EAST ISD",          "Education"),
    ("SAN ANTONIO ISD",         "Education"),
    ("CITY OF SAN ANTONIO",     "Government"),
    ("BEXAR COUNTY",            "Government"),
    ("US AIR FORCE",            "Government"),
    ("U.S. AIR FORCE",          "Government"),
    ("USAF",                    "Government"),
    ("HOUSE OF REPRESENTATIVES", "Government"),
    ("SPURS",                   "Entertainment"),
    ("TOYOTA",                  "Transportation"),
    ("SOUTHWEST RESEARCH",      "Engineering"),
    ("PORT SAN ANTONIO",        "Government"),
    ("SAN ANTONIO WATER SYSTEM", "Government"),
    ("SAWS",                    "Government"),
]

# Occupation keyword -> industry. Checked in order; first hit wins.
OCCUPATION_RULES = [
    (r"\b(RETIRED|NOT EMPLOYED|UNEMPLOYED|HOMEMAKER|HOUSEWIFE|NONE)\b", "Not Employed"),
    (r"\b(STUDENT)\b",                                        "Student"),
    (r"\b(SELF[- ]?EMPLOYED)\b",                              "Self-Employed"),
    (r"\b(ATTORNEY|LAWYER|PARALEGAL|LEGAL ASSISTANT|JUDGE)\b", "Legal"),
    (r"\b(PHYSICIAN|DOCTOR|SURGEON|DENTIST|NURSE|RN|PSYCHIATRIST|PSYCHOLOGIST|PEDIATRICIAN|PHARMACIST|VETERINARIAN|THERAPIST|OPTOMETRIST|CHIROPRACTOR|MD)\b", "Healthcare"),
    (r"\b(REALTOR|REAL ESTATE|PROPERTY MANAGER|BROKER OF RECORD|LANDLORD)\b", "Real Estate"),
    (r"\b(PROFESSOR|TEACHER|EDUCATOR|LIBRARIAN|LECTURER|ACADEMIC|SCHOOL COUNSELOR)\b", "Education"),  # not PRINCIPAL: "Principal Engineer"
    (r"\b(SOFTWARE|PROGRAMMER|DATA SCIENTIST|WEB DEVELOPER|TECHNOLOGIST)\b", "Technology"),
    (r"\b(ENGINEER|ARCHITECT(?!URE))\b",                      "Engineering"),
    (r"\b(BANKER|FINANCIAL ADVISOR|FINANCIAL PLANNER|INVESTMENT|ACCOUNTANT|CPA|ACTUARY|WEALTH|UNDERWRITER)\b", "Finance"),
    (r"\b(CONSULTANT|PUBLIC RELATIONS|LOBBYIST|STRATEGIST)\b", "Consulting / PR"),
    (r"\b(CIVIL SERVANT|GOVERNMENT|FEDERAL AGENT|CITY EMPLOYEE|MILITARY|ARMY|NAVY|AIR FORCE|VETERAN|POSTAL)\b", "Government"),
    (r"\b(NONPROFIT|NON-PROFIT|ORGANIZER|ADVOCATE|SOCIAL WORKER|CLERGY|PASTOR|MINISTER|RABBI)\b", "Nonprofit / Advocacy"),
    (r"\b(JOURNALIST|REPORTER|EDITOR|WRITER|AUTHOR|PRODUCER|FILMMAKER)\b", "Media"),
    (r"\b(ARTIST|MUSICIAN|ACTOR|DESIGNER GRAPHIC)\b",          "Entertainment"),
    (r"\b(CONTRACTOR|BUILDER|CONSTRUCTION|ELECTRICIAN|PLUMBER|CARPENTER)\b", "Construction"),
    (r"\b(RESTAURATEUR|CHEF|HOTELIER|BARTENDER|CATERER)\b",    "Hospitality / Events"),
]


def load_employer_index(cur) -> dict[str, str]:
    """UPPER(canonical_name) -> industry for every non-noise classified employer."""
    out = {}
    for name, industry in cur.execute(
        "SELECT canonical_name, industry FROM employer_identities WHERE industry IS NOT NULL"
    ):
        if industry not in NOISE_INDUSTRIES and name and name.strip():
            out[name.upper().strip()] = industry
    return out


def match_employer_index(emp_u: str, emp_index: dict[str, str]) -> str | None:
    """Exact, then one-directional substring (known name inside the reported
    string, >= 6 chars — prevents short noise tokens matching long names)."""
    if emp_u in emp_index:
        return emp_index[emp_u]
    for known, industry in emp_index.items():
        if len(known) >= 6 and known in emp_u:
            return industry
    return None


def match_rules(emp: str, occ: str, prefix: str):
    """(industry, display, confidence) via SA anchors then occupation rules,
    or None. `prefix` is 'local' or the legacy FEC tag pair."""
    emp_u, occ_u = emp.upper().strip(), occ.upper().strip()
    if emp_u:
        for anchor, industry in SA_EMPLOYERS:
            if anchor in emp_u:
                tag = "local-employer-rules" if prefix == "local" else "sa-employer-rules"
                return industry, emp.title(), tag
    if occ_u:
        for pat, industry in OCCUPATION_RULES:
            if re.search(pat, occ_u):
                base = "local-occupation-rules" if prefix == "local" else "fec-occupation-rules"
                emp_is_noise = any(emp_u.startswith(nz) for nz in NOISE_EMP)
                if emp_u and not emp_is_noise:
                    return industry, emp.title(), base
                return industry, occ.title(), base + "-noemp"
    return None


def unresolved_ids(cur) -> set[str]:
    return {r[0] for r in cur.execute(
        "SELECT donor_id FROM donor_identities WHERE resolved_industry IS NULL")}


def apply(cur, updates, dry):
    if dry or not updates:
        return
    cur.executemany(
        """UPDATE donor_identities
           SET resolved_industry=?, resolved_employer_display=?, resolved_confidence=?
           WHERE donor_id=? AND resolved_industry IS NULL""",
        updates)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    conn = sqlite3.connect(args.db, timeout=120)
    cur = conn.cursor()

    # Re-derive everything non-manual so priority order always holds.
    if not args.dry_run:
        n = cur.execute(
            """UPDATE donor_identities
               SET resolved_industry=NULL, resolved_employer_display=NULL, resolved_confidence=NULL
               WHERE resolved_confidence IS NOT NULL AND resolved_confidence != 'manual'"""
        ).rowcount
        conn.commit()
        print(f"[rules] reset {n:,} non-manual resolutions for re-derivation")

    emp_index = load_employer_index(cur)
    print(f"[rules] employer index: {len(emp_index):,} classified names")

    # ── Passes 1-3: portal-reported strings (latest non-empty per donor) ──────
    local = {}
    for donor_id, emp, occ in cur.execute("""
        SELECT donor_id, donor_reported_employer, donor_reported_occupation
        FROM campaign_finance
        WHERE donor_id IS NOT NULL AND txn_type = 'contribution'
          AND (COALESCE(donor_reported_employer,'') != '' OR COALESCE(donor_reported_occupation,'') != '')
        ORDER BY date_iso ASC"""):   # ascending: later rows overwrite -> latest wins
        local[donor_id] = (emp or "", occ or "")

    todo = unresolved_ids(cur)
    updates = []
    deferred = []   # local occupation-title-only hits: a REAL employer name
                    # from FEC (next pass) makes a better display than a bare
                    # title, so these apply only if FEC finds nothing.
    for donor_id, (emp, occ) in local.items():
        if donor_id not in todo:
            continue
        emp_u = emp.upper().strip()
        if emp_u and not any(emp_u.startswith(nz) for nz in NOISE_EMP):
            ind = match_employer_index(emp_u, emp_index)
            if ind:
                updates.append((ind, emp.title(), "local-employer", donor_id))
                continue
        hit = match_rules(emp, occ, "local")
        if hit:
            (deferred if hit[2].endswith("-noemp") else updates).append((*hit, donor_id))
    apply(cur, updates, args.dry_run)
    conn.commit()
    print(f"[rules] local passes: {len(local):,} donors with portal strings, "
          f"{len(updates):,} resolved, {len(deferred):,} deferred behind FEC employer match")

    # ── Pass 4: FEC employer match (reuses the enrichment module's pass) ──────
    if not args.dry_run:
        import fec_enrich
        fec_enrich.resolve_from_fec_employers(conn)

    # Deferred local occupation-only hits fill whatever FEC couldn't
    apply(cur, deferred, args.dry_run)
    conn.commit()

    # ── Passes 5-6: FEC-string rules for the remainder ────────────────────────
    todo = unresolved_ids(cur)
    updates = []
    for donor_id, emp, occ in cur.execute("""
        SELECT fcr.donor_id,
               MAX(COALESCE(fcr.fec_employer, ''))   AS emp,
               MAX(COALESCE(fcr.fec_occupation, '')) AS occ
        FROM fec_contributions_raw fcr
        WHERE fcr.fec_employer IS NOT NULL OR fcr.fec_occupation IS NOT NULL
        GROUP BY fcr.donor_id"""):
        if donor_id not in todo:
            continue
        hit = match_rules(emp, occ, "fec")
        if hit:
            updates.append((*hit, donor_id))
    apply(cur, updates, args.dry_run)
    conn.commit()
    print(f"[rules] fec passes: {len(updates):,} resolved")

    for conf, n, tot in cur.execute("""
        SELECT resolved_confidence, COUNT(*), ROUND(SUM(total_donated))
        FROM donor_identities WHERE resolved_industry IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"""):
        print(f"[rules] {conf or '?':28} {n:5,} donors  (${tot or 0:,.0f} lifetime)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
