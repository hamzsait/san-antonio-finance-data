"""
sa_industry_rules.py
Rules-based industry resolution from FEC occupation/employer strings.

Runs AFTER fec_enrich.py. That script's resolve_from_fec_employers() only
matches FEC employer strings against known employer_identities names; this
pass covers the two big remainders:

  1. Occupation keywords ("ATTORNEY", "PHYSICIAN", "RETIRED"...) — high-signal
     titles that map cleanly onto the site's industry taxonomy regardless of
     employer.
  2. SA-anchor employers (USAA, H-E-B, CPS Energy...) that Austin's seeded
     employer list doesn't carry.

Order matters: employer anchors run first (more specific), then occupations.
Only fills donors whose resolved_industry IS NULL; never overwrites a prior
resolution (manual > fec-employer > these rules). Idempotent.
Confidence tags: 'sa-employer-rules' / 'fec-occupation-rules'.

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
    ("SPURS",                   "Entertainment"),
    ("TOYOTA",                  "Transportation"),
    ("SOUTHWEST RESEARCH",      "Engineering"),
    ("PORT SAN ANTONIO",        "Government"),
    ("SAN ANTONIO WATER SYSTEM", "Government"),
    ("SAWS",                    "Government"),
]

# Occupation keyword -> industry. Checked in order; first hit wins. Word-ish
# boundaries via regex to keep "RN" from matching inside other words.
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    # Best FEC employer+occupation per unresolved donor (highest FEC total)
    rows = cur.execute("""
        SELECT fcr.donor_id,
               MAX(COALESCE(fcr.fec_employer, ''))   AS emp,
               MAX(COALESCE(fcr.fec_occupation, '')) AS occ
        FROM fec_contributions_raw fcr
        JOIN donor_identities di ON di.donor_id = fcr.donor_id
        WHERE di.resolved_industry IS NULL
          AND (fcr.fec_employer IS NOT NULL OR fcr.fec_occupation IS NOT NULL)
        GROUP BY fcr.donor_id
    """).fetchall()

    updates = []   # (industry, display, confidence, donor_id)
    counts = {"sa-employer-rules": 0, "fec-occupation-rules": 0}

    for donor_id, emp, occ in rows:
        emp_u, occ_u = emp.upper().strip(), occ.upper().strip()
        hit = None
        if emp_u:
            for anchor, industry in SA_EMPLOYERS:
                if anchor in emp_u:
                    hit = (industry, emp.title(), "sa-employer-rules")
                    break
        if hit is None and occ_u:
            NOISE_EMP = ("SELF", "NONE", "N/A", "RETIRED", "NOT EMPLOYED", "UNEMPLOYED", "HOMEMAKER")
            for pat, industry in OCCUPATION_RULES:
                if re.search(pat, occ_u):
                    # A noise employer string ("Self Employed") is a worse
                    # display than the occupation that actually matched.
                    emp_is_noise = any(emp_u.startswith(nz) for nz in NOISE_EMP)
                    display = emp.title() if emp_u and not emp_is_noise else occ.title()
                    hit = (industry, display, "fec-occupation-rules")
                    break
        if hit:
            updates.append((*hit, donor_id))
            counts[hit[2]] += 1

    print(f"[rules] {len(rows):,} unresolved donors with FEC strings; "
          f"{len(updates):,} resolvable "
          f"(employer-anchors {counts['sa-employer-rules']}, occupations {counts['fec-occupation-rules']})")

    if args.dry_run:
        for ind, disp, conf, _ in updates[:20]:
            print(f"  {conf:22} {ind:22} {disp[:40]}")
        print("[rules] --dry-run: no writes")
        return 0

    cur.executemany("""
        UPDATE donor_identities
        SET resolved_industry=?, resolved_employer_display=?, resolved_confidence=?
        WHERE donor_id=? AND resolved_industry IS NULL
    """, updates)
    conn.commit()

    for conf, n, tot in cur.execute("""
        SELECT resolved_confidence, COUNT(*), ROUND(SUM(total_donated))
        FROM donor_identities WHERE resolved_industry IS NOT NULL GROUP BY 1
    """):
        print(f"[rules] resolved via {conf or '?':24} {n:5,} donors  (${tot or 0:,.0f} lifetime)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
