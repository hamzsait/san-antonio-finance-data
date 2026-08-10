"""
generate_profile_data.py
Generate {slug}_data.json and {slug}_all_donations.json for any tracked filer
in the San Antonio campaign finance database. Ported from the Austin repo
2026-07-20 (see MAYOR_PLAN.md §E); reads only the normalized columns
(amount_real / date_iso / txn_type) and selects filers by council_members
slug rather than recipient-name fragment.

Usage:
    python generate_profile_data.py --candidate jones
"""

import argparse
import json
import re
import sqlite3
import sys
import io
import os
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Repo-relative so builds work from any checkout/worktree of the repo.
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_REPO_ROOT, "san_antonio_finance.db")

INDUSTRY_COLORS = {
    "Real Estate":              "#f59e0b",
    "Technology":               "#4f8ef7",
    "Legal":                    "#a78bfa",
    "Nonprofit / Advocacy":     "#34d399",
    "Healthcare":               "#f472b6",
    "Consulting / PR":          "#94a3b8",
    "Government":               "#818cf8",
    "Finance":                  "#fbbf24",
    "Education":                "#22d3ee",
    "Engineering":              "#6b7280",
    "Hospitality / Events":     "#fb923c",
    "Construction":             "#d97706",
    "Energy / Environment":     "#ef4444",
    "Media":                    "#60a5fa",
    "Retail":                   "#a3e635",
    "Architecture":             "#e879f9",
    "Transportation":           "#34d399",
    "Entertainment":            "#f97316",
    "Labor":                    "#14b8a6",
    "Venture Capital":          "#8b5cf6",
    "Retail / Media / Other":   "#374151",
    "Not Employed":             "#6b7280",
    "Self-Employed":            "#78716c",
    "Student":                  "#38bdf8",
    "Family":                   "#f43f5e",
    "Unknown / Unclassified":   "#1f2937",
    "Unknown":                  "#1f2937",
}

NOISE_INDUSTRIES = {"Not Employed", "Self-Employed", "Student", "Unknown", "Unknown / Unclassified", "Family"}
NO_DONUT = {"Not Employed", "Self-Employed", "Student", "Unknown / Unclassified", "Family"}

# Industries that roll up into "Retail / Media / Other" in the profile.
# 2026-07-16: rollup disabled (user request) — Retail, Media, Architecture,
# Transportation, Entertainment, Labor, and Venture Capital now display as
# their own categories. Only the literal legacy label still maps to itself.
OTHER_INDS = {"Retail / Media / Other"}

# Employer-display strings that are not firms (occupation titles, self-flags,
# disclosure boilerplate). Compared UPPERCASE in the two "firms with 3+
# donors" queries; anything resolved via an occupation-only rule
# (confidence LIKE '%-noemp') is excluded there as well.
FIRM_NOISE_SQL = """('NOT EMPLOYED','SELF-EMPLOYED','SELF EMPLOYED','SELFEMPLOYED',
    'SELF','STUDENT','UNKNOWN','RETIRED','HOMEMAKER','HOUSEWIFE','N/A','NA','NONE',
    'UNEMPLOYED','INFORMATION REQUESTED','BEST EFFORTS','REALTOR','REAL ESTATE',
    'ATTORNEY','LAWYER','CONSULTANT','PHYSICIAN','UNION','PAC')"""

# Election cycle definitions per filer slug.
# Each cycle: label, start_year (None = beginning of time), end_year (None = present).
# SA context: 2-year terms through the May/June 2025 election (charter Prop F,
# Nov 2024, moved the city to 4-year terms after that). The profile's default
# view is ALL-TIME (user decision 2026-07-20); these windows drive the
# historical cycle tabs. Verify each member's actual election history against
# Ballotpedia before adding them here (council-batch phases).
CANDIDATE_CYCLES = {
    # Gina Ortiz Jones: first SA city campaign; won the June 7, 2025 runoff.
    # Her 2018/2020 TX-23 congressional runs are federal (FEC) and stay out of
    # city charts by design.
    'jones':  [{'label': '2025 Mayoral Run', 'election_year': 2025, 'start_year': None, 'end_year': None}],
    # Sakib Shaikh: lost the 2025 D8 general; unlisted profile ships later.
    'shaikh': [{'label': '2025 Run', 'election_year': 2025, 'start_year': None, 'end_year': None}],
    # Sukh Kaur (D1): won the June 10, 2023 runoff over incumbent Mario Bravo;
    # re-elected in the June 7, 2025 runoff over Patty Gibbons. Mid-year date
    # bounds split at the runoffs; post-June-2025 money (next-cycle) appears
    # only in the all-time default view.
    'kaur': [
        {'label': '2023 Run', 'election_year': 2023,
         'start_year': None, 'end_year': None, 'end_date': '2023-06-30'},
        {'label': '2025 Re-election', 'election_year': 2025,
         'start_year': None, 'end_year': None,
         'start_date': '2023-07-01', 'end_date': '2025-06-30'},
    ],
    # Jalen McKee-Rodriguez (D2): won the June 5, 2021 runoff over incumbent
    # Jada Andrews-Sullivan; re-elected outright May 2023 and May 3, 2025.
    # First 3-tab profile (elected under the old 2-year terms).
    'mckeerodriguez': [
        {'label': '2021 Run', 'election_year': 2021,
         'start_year': None, 'end_year': None, 'end_date': '2021-06-30'},
        {'label': '2023 Re-election', 'election_year': 2023,
         'start_year': None, 'end_year': None,
         'start_date': '2021-07-01', 'end_date': '2023-06-30'},
        {'label': '2025 Re-election', 'election_year': 2025,
         'start_year': None, 'end_year': None,
         'start_date': '2023-07-01', 'end_date': '2025-06-30'},
    ],
    # Phyllis Viagran (D3): won the June 5, 2021 runoff over Tomas Uresti;
    # re-elected outright May 6, 2023 and May 3, 2025. Same 3-tab shape as
    # McKee-Rodriguez (2021 class, old 2-year terms).
    'viagran': [
        {'label': '2021 Run', 'election_year': 2021,
         'start_year': None, 'end_year': None, 'end_date': '2021-06-30'},
        {'label': '2023 Re-election', 'election_year': 2023,
         'start_year': None, 'end_year': None,
         'start_date': '2021-07-01', 'end_date': '2023-06-30'},
        {'label': '2025 Re-election', 'election_year': 2025,
         'start_year': None, 'end_year': None,
         'start_date': '2023-07-01', 'end_date': '2025-06-30'},
    ],
    # Teri Castillo (D5): won the June 5, 2021 runoff over Rudy Lopez;
    # re-elected outright May 6, 2023 and May 3, 2025. Same 3-tab shape as
    # McKee-Rodriguez/Viagran (2021 class, old 2-year terms).
    'castillo': [
        {'label': '2021 Run', 'election_year': 2021,
         'start_year': None, 'end_year': None, 'end_date': '2021-06-30'},
        {'label': '2023 Re-election', 'election_year': 2023,
         'start_year': None, 'end_year': None,
         'start_date': '2021-07-01', 'end_date': '2023-06-30'},
        {'label': '2025 Re-election', 'election_year': 2025,
         'start_year': None, 'end_year': None,
         'start_date': '2023-07-01', 'end_date': '2025-06-30'},
    ],
    # Marina Alderete Gavito (D7): won the June 10, 2023 runoff over Dan
    # Rossiter; re-elected outright May 3, 2025. Two-tab 2023 class, same shape
    # as Kaur (the other 2023-class member) rather than the 2021 three-tab
    # members. Files as 'Marina Gavito' despite the compound display surname.
    'gavito': [
        {'label': '2023 Run', 'election_year': 2023,
         'start_year': None, 'end_year': None, 'end_date': '2023-06-30'},
        {'label': '2025 Re-election', 'election_year': 2025,
         'start_year': None, 'end_year': None,
         'start_date': '2023-07-01', 'end_date': '2025-06-30'},
    ],
    # Marc Whyte (D10): won the open seat outright May 6, 2023 (57.8%, no
    # runoff); re-elected outright May 3, 2025 (69.1%). Two-tab 2023 class,
    # same shape as Gavito and Kaur.
    'whyte': [
        {'label': '2023 Run', 'election_year': 2023,
         'start_year': None, 'end_year': None, 'end_date': '2023-06-30'},
        {'label': '2025 Re-election', 'election_year': 2025,
         'start_year': None, 'end_year': None,
         'start_date': '2023-07-01', 'end_date': '2025-06-30'},
    ],
}

# Earliest contribution_year included in a profile (default 2018 = start of
# clean city data). County officials have clean county filings back to 2016.
# Patterns for the political-card dedup rule; see is_donation_restatement().
_GIVING_LEAD = re.compile(
    r'^\s*(major|recurring|consistent|significant|large|small|individual|federal|political|repeat|frequent|long-?time)?\s*'
    r'(individual|federal|political)?\s*'
    r'(donor|contributor|contribution|donation|giving|gave|donated|contributed)\b', re.I)
_POLITICAL_ROLE = re.compile(
    r'\b(chair|co-?chair|co-?founder|founder|president of|vice[- ]president of|director|board member|board of|'
    r'trustee|treasurer|business manager|precinct|delegate|staff|senior advisor|advisor|adviser|judge|mayor|'
    r'council ?member|commissioner|commission|candidate|organizer|lobbyist|lobby client|lobby registration|'
    r'endorsed|endorsement|campaign manager|finance committee|leadership council|elected|appointed|incumbent|'
    r'member;|spousal)\b', re.I)

# ── Affiliation buckets ──────────────────────────────────────────────────────
# One entry per rendered bucket. `categories` is an exact-match list; `prefix`
# matches any category starting with that string (used for the oil_gas_* family,
# which has six legacy variants predating the v3 taxonomy).
#
# `spectrum` pairs opposing policy positions so the template can render them
# side by side. A bucket with zero findings still emits an empty list and its
# total, so the template can show an explicit zero rather than omitting the
# column -- a blank pro-Palestine slot next to a populated pro-Israel one would
# otherwise read as selective reporting. The v3 mandatory checklist ran the FEC
# PAC search on 606/606 D1 donors, so these zeros are absences in the data, not
# categories that went unsearched.
#
# `card` groups buckets into profile-page cards. Phase order per
# AFFILIATION_TEMPLATE_EXPANSION_PLAN.md: policy first, then business,
# political, civic.
AFFILIATION_BUCKETS = [
    # ── Policy & Advocacy ────────────────────────────────────────────────────
    {"key": "pro_israel_advocacy", "label": "Pro-Israel advocacy",
     "categories": ["aipac_direct", "pro_israel"], "card": "policy",
     "spectrum": "israel_palestine"},
    {"key": "palestine_advocacy", "label": "Palestinian-rights advocacy",
     "categories": ["palestine_solidarity", "pro_palestine_advocacy"], "card": "policy",
     "spectrum": "israel_palestine"},
    {"key": "liberal_zionist", "label": "Liberal Zionist organizations",
     "categories": ["liberal_zionist"], "card": "policy"},
    {"key": "jewish_civic", "label": "Jewish communal organizations",
     "categories": ["jewish_civic", "jewish_political"], "card": "policy"},
    {"key": "gun_control", "label": "Gun-violence prevention",
     "categories": ["gun_control"], "card": "policy", "spectrum": "guns"},
    {"key": "gun_rights", "label": "Gun rights & firearms industry",
     "categories": ["gun_rights"], "card": "policy", "spectrum": "guns"},
    {"key": "oil_gas", "label": "Oil, gas & energy",
     "categories": [], "prefix": "oil_gas", "card": "policy"},
    {"key": "military_defense", "label": "Defense contracting",
     "categories": ["military_defense"], "card": "policy"},
    {"key": "healthcare", "label": "Healthcare institutions",
     "categories": ["healthcare"], "card": "policy"},
    # ── Later phases: emitted now, rendered when their card ships ────────────
    {"key": "business", "label": "Business ownership & leadership",
     "categories": ["business", "industry"], "card": "business"},
    {"key": "political", "label": "Political & campaign roles",
     "categories": ["political"], "card": "political",
     "drop_donation_restatements": True},
    # Alphabetical, not dollar-sorted: ranking community volunteering by
    # donation size would imply "biggest donor is most connected", which the
    # data does not support. Every other bucket sorts by dollar because there
    # the money is the point.
    {"key": "civic", "label": "Community & civic roles",
     "categories": ["civic"], "card": "civic", "sort": "alpha"},
]

# Hero badge text per slug. The profile template reads meta.office at runtime and
# overwrites whatever is in the HTML, so candidate framing has to be set here --
# a string substitution in build_candidate.py gets clobbered by renderHero().
OFFICE_OVERRIDE = {
    'jones':  'Mayor of San Antonio',
    'galvan': 'San Antonio City Council · District 6',
    'kaur':   'San Antonio City Council · District 1',
    'mckeerodriguez': 'San Antonio City Council · District 2',
    'viagran': 'San Antonio City Council · District 3',
    'mungia': 'San Antonio City Council · District 4',
    'castillo': 'San Antonio City Council · District 5',
    'gavito': 'San Antonio City Council · District 7',
    'gonzalez': 'San Antonio City Council · District 8',
    'spears': 'San Antonio City Council · District 9',
    'whyte':  'San Antonio City Council · District 10',
    'shaikh': 'San Antonio City Council · 2025 District 8 Candidate',
}

CANDIDATE_MIN_YEAR = {}

# Contribution rows carry the `filer_slug` of whichever member's name was
# searched at ingest — which includes money that member *gave to other
# candidates* (D18/D19 in ADD_COUNCIL_MEMBER.md). Unfiltered, those rows are
# counted as money the member raised: Gavito's five pre-2023 gifts to Nirenberg,
# Landin, Johnson and Garcia rendered four phantom year-bars for a candidate
# whose first race was 2023.
#
# `recipient` separates them, but NOT by simple equality against the member's
# name: a member's own money can span several recipient strings (Jones files
# under both 'Gina Jones' and 'Gina Ortiz Jones'), so an equality test would
# delete legitimate rows. Register every string that IS this member's own
# campaign; everything else is excluded from the profile.
RECIPIENT_ALIASES = {
    'jones':          {'Gina Jones', 'Gina Ortiz Jones'},
    'galvan':         {'Ric Galvan'},
    'kaur':           {'Sukh Kaur'},
    'mckeerodriguez': {'Jalen McKee-Rodriguez'},
    'viagran':        {'Phyllis Viagran'},
    'mungia':         {'Edward Mungia'},
    'castillo':       {'Teri Castillo'},
    'gavito':         {'Marina Gavito'},
    'gonzalez':       {'Ivalis Gonzalez'},
    'spears':         {'Misty Spears'},
    'whyte':          {'Marc Whyte'},
    'shaikh':         {'Sakib Shaikh'},
}


def recipient_filter(cur, slug):
    """(sql_fragment, params) restricting rows to the member's own campaign.

    An unregistered slug is deliberately NOT filtered — silently dropping rows
    would be worse than the noise — but extra recipient strings are reported
    loudly so the next member's author registers the real ones.
    """
    names = RECIPIENT_ALIASES.get(slug)
    if not names:
        found = [r[0] for r in cur.execute(
            "SELECT DISTINCT recipient FROM campaign_finance "
            "WHERE filer_slug=? AND txn_type='contribution' AND recipient IS NOT NULL",
            (slug,)).fetchall()]
        if len(found) > 1:
            print(f"  WARNING: slug '{slug}' has {len(found)} recipient strings and no "
                  f"RECIPIENT_ALIASES entry, so money this member gave to other "
                  f"candidates is being counted as money raised. Register the "
                  f"member's own string(s): {found}")
        return "", []
    ordered = sorted(names)
    placeholders = ",".join("?" for _ in ordered)
    return f" AND cf.recipient IN ({placeholders})", ordered


def slugify(name: str) -> str:
    """Simple slug: lowercase, alphanumeric only."""
    return "".join(c.lower() for c in name if c.isalnum() or c == "_")


def find_filer(cur, slug: str):
    """Resolve a council_members slug to (display_name, row_count)."""
    row = cur.execute(
        "SELECT full_name FROM council_members WHERE slug=?", (slug,)
    ).fetchone()
    if not row:
        return None, 0
    rec_sql, rec_params = recipient_filter(cur, slug)
    n = cur.execute(
        "SELECT COUNT(*) FROM campaign_finance cf "
        "WHERE cf.filer_slug=? AND cf.txn_type='contribution'" + rec_sql,
        (slug, *rec_params),
    ).fetchone()[0]
    return row[0], n


def build_year_clause(cycle):
    """Return (extra_sql, extra_params) for filtering by cycle start/end year.

    Optional 'start_date'/'end_date' ('YYYY-MM-DD') take precedence over the
    year bound on that side — SA cycle boundaries fall mid-year (May/June
    elections; the cap cycle restarts after the runoff), and a whole-year
    split would bucket post-runoff money into the finished campaign.
    date_iso is ISO text so lexicographic compare is date compare.
    """
    clauses = []
    params = []
    # CAST is load-bearing: contribution_year has TEXT affinity, and SQLite
    # ranks any TEXT above every number, so an uncast comparison silently
    # passes/fails whole cycles.
    if cycle.get('start_date') is not None:
        clauses.append("cf.date_iso >= ?")
        params.append(cycle['start_date'])
    elif cycle['start_year'] is not None:
        clauses.append("CAST(cf.contribution_year AS INTEGER) >= ?")
        params.append(cycle['start_year'])
    if cycle.get('end_date') is not None:
        clauses.append("cf.date_iso <= ?")
        params.append(cycle['end_date'])
    elif cycle['end_year'] is not None:
        clauses.append("CAST(cf.contribution_year AS INTEGER) <= ?")
        params.append(cycle['end_year'])
    return clauses, params


def build_cycle_data(cur, candidate_fragment, cycle, by_year_data):
    """Run the same queries as the main profile but filtered to a cycle's year range.
    Returns dict with hero, interest_groups, notable_firms, top_donors."""

    year_clauses, year_params = build_year_clause(cycle)

    # Build WHERE clause
    where_parts = [
        "cf.filer_slug = ?",
        "cf.txn_type = 'contribution'",
        "COALESCE(cf.balanced_amount, cf.amount_real) > 0",
    ]
    base_params = [candidate_fragment]

    # Same own-campaign restriction as the main profile, or the cycle heroes
    # would disagree with the all-time hero.
    rec_sql, rec_params = recipient_filter(cur, candidate_fragment)
    if rec_sql:
        where_parts.append(rec_sql.replace(" AND ", "", 1).strip())
        base_params.extend(rec_params)

    if year_clauses:
        where_parts.extend(year_clauses)
        base_params.extend(year_params)

    WHERE = " AND ".join(where_parts)
    params = tuple(base_params)

    # ── Hero stats ────────────────────────────────────────────────────────────
    hero_row = cur.execute(f"""
        SELECT
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as total_raised,
            COUNT(DISTINCT cf.donor_id) as unique_donors,
            COUNT(*) as total_contributions
        FROM campaign_finance cf
        WHERE {WHERE}
    """, params).fetchone()

    total_raised = int(hero_row[0] or 0)
    unique_donors = int(hero_row[1] or 0)
    total_contributions = int(hero_row[2] or 0)

    # Employer-affiliated %
    noise_total = cur.execute(f"""
        SELECT ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0)
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {WHERE}
          AND COALESCE(di.resolved_industry, ei.industry, 'Unknown') IN
              ('Not Employed','Self-Employed','Student','Unknown','Unknown / Unclassified')
    """, params).fetchone()[0] or 0

    employer_affiliated_pct = round((total_raised - noise_total) / total_raised * 100, 1) if total_raised else 0.0

    # Top industry
    top_industry_row = cur.execute(f"""
        SELECT COALESCE(di.resolved_industry, ei.industry, 'Unknown') as ind,
               ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as tot
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {WHERE}
          AND COALESCE(di.resolved_industry, ei.industry, 'Unknown') NOT IN
              ('Not Employed','Self-Employed','Student','Unknown','Unknown / Unclassified')
        GROUP BY 1 ORDER BY 2 DESC LIMIT 1
    """, params).fetchone()
    top_industry = top_industry_row[0] if top_industry_row else "Unknown"

    hero = {
        "total_raised": total_raised,
        "unique_donors": unique_donors,
        "total_contributions": total_contributions,
        "employer_affiliated_pct": employer_affiliated_pct,
        "top_industry": top_industry,
    }

    # ── Interest groups ───────────────────────────────────────────────────────
    ig_rows = cur.execute(f"""
        SELECT
            COALESCE(di.resolved_industry, ei.industry, 'Unknown') as industry,
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as total,
            COUNT(DISTINCT cf.donor_id) as donors
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {WHERE}
        GROUP BY 1 ORDER BY 2 DESC
    """, params).fetchall()

    other_total = 0
    main_groups = []
    for ind, total, donors in ig_rows:
        if ind in OTHER_INDS and ind != "Retail / Media / Other":
            other_total += int(total)
        elif ind == "Retail / Media / Other":
            other_total += int(total)
        else:
            main_groups.append((ind, int(total), int(donors)))

    if other_total > 0:
        other_donors_count = cur.execute(f"""
            SELECT COUNT(DISTINCT cf.donor_id)
            FROM campaign_finance cf
            LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
            LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
            WHERE {WHERE}
              AND COALESCE(di.resolved_industry, ei.industry, 'Unknown') IN
                  ('Retail','Media','Architecture','Transportation','Entertainment',
                   'Labor','Venture Capital','Retail / Media / Other')
        """, params).fetchone()[0] or 0
        main_groups.append(("Retail / Media / Other", other_total, other_donors_count))

    main_groups.sort(key=lambda x: -x[1])

    interest_groups = []
    for ind, total, donors in main_groups:
        entry = {
            "label": ind,
            "donors": donors,
            "total": total,
            "color": INDUSTRY_COLORS.get(ind, "#94a3b8"),
        }
        if ind in NO_DONUT:
            entry["noDonut"] = True
        interest_groups.append(entry)

    # ── Notable firms ─────────────────────────────────────────────────────────
    notable_rows = cur.execute(f"""
        SELECT
            COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, '') as firm,
            COALESCE(di.resolved_industry, ei.industry, 'Unknown') as industry,
            COALESCE(ei.interest_tags, '') as tags,
            COUNT(DISTINCT cf.donor_id) as donors,
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as total
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {WHERE}
          AND COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, '') != ''
          AND UPPER(COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, ''))
              NOT IN {FIRM_NOISE_SQL}
          AND COALESCE(di.resolved_confidence, '') NOT LIKE '%-noemp'
        GROUP BY firm
        HAVING COUNT(DISTINCT cf.donor_id) >= 3
        ORDER BY total DESC
        LIMIT 20
    """, params).fetchall()

    notable_firms = []
    for firm, industry, tags, donors, total in notable_rows:
        notable_firms.append({
            "firm": firm,
            "industry": industry,
            "tags": tags or "",
            "donors": int(donors),
            "total": int(total),
            "color": INDUSTRY_COLORS.get(industry, "#94a3b8"),
        })

    # ── Top donors ────────────────────────────────────────────────────────────
    top_donor_rows = cur.execute(f"""
        SELECT
            di.canonical_name as name,
            COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, '') as employer,
            COALESCE(di.resolved_industry, ei.industry, 'Unknown') as industry,
            COALESCE(ei.interest_tags, '') as tags,
            COUNT(*) as cnt,
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as total
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {WHERE}
          AND cf.donor_type = 'INDIVIDUAL'
          AND di.canonical_name IS NOT NULL
          AND di.canonical_name != ''
        GROUP BY cf.donor_id
        ORDER BY total DESC
        LIMIT 10
    """, params).fetchall()

    top_donors = []
    for name, employer, industry, tags, cnt, total in top_donor_rows:
        top_donors.append({
            "name": name or "",
            "employer": employer or "",
            "industry": industry or "",
            "tags": tags or "",
            "total": int(total),
            "count": int(cnt),
        })

    # ── Build year_range string ───────────────────────────────────────────────
    if cycle.get('start_date') is not None:
        start_str = cycle['start_date'][:4]
    elif cycle['start_year'] is None:
        # Use earliest year from by_year data
        years = [int(y['year']) for y in by_year_data if y['total'] > 0]
        start_str = str(min(years)) if years else "?"
    else:
        start_str = str(cycle['start_year'])

    if cycle.get('end_date') is not None:
        end_str = cycle['end_date'][:4]
    elif cycle['end_year'] is None:
        end_str = "present"
    else:
        end_str = str(cycle['end_year'])

    year_range = f"{start_str}\u2013{end_str}"

    return {
        "label": cycle['label'],
        "election_year": cycle['election_year'],
        "year_range": year_range,
        "hero": hero,
        "interest_groups": interest_groups,
        "notable_firms": notable_firms,
        "top_donors": top_donors,
    }


def generate(candidate_fragment: str, output_dir: str = ".", slug_override: str = None):
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # ── Identify filer ────────────────────────────────────────────────────────
    # SA rows carry a clean filer_slug from ingest, so the candidate argument
    # IS the slug — no recipient-fragment matching needed.
    slug = slug_override if slug_override else slugify(candidate_fragment)
    candidate_name, count = find_filer(cur, slug)
    if not candidate_name:
        print(f"ERROR: no council_members row for slug '{slug}' (run fetch_roster.py)")
        conn.close()
        return
    if not count:
        print(f"ERROR: no contribution rows for filer_slug '{slug}' (run fetch_data.py --slug {slug})")
        conn.close()
        return
    print(f"Found filer: '{candidate_name}' ({count:,} contribution records)")

    # ── Base filter ───────────────────────────────────────────────────────────
    # All queries use this same WHERE clause. Portal year floor is 2016.
    min_year = CANDIDATE_MIN_YEAR.get(slug, 2016)
    rec_sql, rec_params = recipient_filter(cur, slug)
    BASE_WHERE = f"""
        cf.filer_slug = ?
        AND cf.txn_type = 'contribution'
        AND CAST(cf.contribution_year AS INTEGER) >= {min_year}
        AND COALESCE(cf.balanced_amount, cf.amount_real) > 0
        {rec_sql}
    """
    base_params = (slug, *rec_params)

    # ── Hero stats ────────────────────────────────────────────────────────────
    hero_row = cur.execute(f"""
        SELECT
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as total_raised,
            COUNT(DISTINCT cf.donor_id) as unique_donors,
            COUNT(*) as total_contributions
        FROM campaign_finance cf
        WHERE {BASE_WHERE}
    """, base_params).fetchone()

    total_raised = int(hero_row[0] or 0)
    unique_donors = int(hero_row[1] or 0)
    total_contributions = int(hero_row[2] or 0)

    # Employer-affiliated % (exclude noise industries)
    noise_total = cur.execute(f"""
        SELECT ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0)
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {BASE_WHERE}
          AND COALESCE(di.resolved_industry, ei.industry, 'Unknown') IN
              ('Not Employed','Self-Employed','Student','Unknown','Unknown / Unclassified')
    """, base_params).fetchone()[0] or 0

    employer_affiliated_pct = round((total_raised - noise_total) / total_raised * 100, 1) if total_raised else 0.0

    # Top industry (by total, excluding noise)
    top_industry_row = cur.execute(f"""
        SELECT COALESCE(di.resolved_industry, ei.industry, 'Unknown') as ind,
               ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as tot
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {BASE_WHERE}
          AND COALESCE(di.resolved_industry, ei.industry, 'Unknown') NOT IN
              ('Not Employed','Self-Employed','Student','Unknown','Unknown / Unclassified')
        GROUP BY 1 ORDER BY 2 DESC LIMIT 1
    """, base_params).fetchone()
    top_industry = top_industry_row[0] if top_industry_row else "Unknown"

    hero = {
        "total_raised": total_raised,
        "unique_donors": unique_donors,
        "total_contributions": total_contributions,
        "employer_affiliated_pct": employer_affiliated_pct,
        "top_industry": top_industry,
    }

    # ── By year ───────────────────────────────────────────────────────────────
    by_year_rows = cur.execute(f"""
        SELECT
            CAST(cf.contribution_year AS TEXT) as yr,
            COUNT(*) as cnt,
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as tot
        FROM campaign_finance cf
        WHERE {BASE_WHERE}
        GROUP BY cf.contribution_year ORDER BY cf.contribution_year
    """, base_params).fetchall()

    by_year = [{"year": r[0], "count": int(r[1]), "total": int(r[2])} for r in by_year_rows]

    # ── Interest groups ───────────────────────────────────────────────────────
    ig_rows = cur.execute(f"""
        SELECT
            COALESCE(di.resolved_industry, ei.industry, 'Unknown') as industry,
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as total,
            COUNT(DISTINCT cf.donor_id) as donors
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {BASE_WHERE}
        GROUP BY 1 ORDER BY 2 DESC
    """, base_params).fetchall()

    # Collapse "Other" industries into Retail / Media / Other
    other_total = 0
    other_donors = set()
    main_groups = []
    for ind, total, donors in ig_rows:
        if ind in OTHER_INDS and ind != "Retail / Media / Other":
            other_total += int(total)
            # donors here is COUNT(DISTINCT donor_id) per industry — we can't sum these
            # so we'll re-query for combined donors below
        elif ind == "Retail / Media / Other":
            other_total += int(total)
        else:
            main_groups.append((ind, int(total), int(donors)))

    # Re-query combined donor count for Other bucket
    if other_total > 0:
        other_donors_count = cur.execute(f"""
            SELECT COUNT(DISTINCT cf.donor_id)
            FROM campaign_finance cf
            LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
            LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
            WHERE {BASE_WHERE}
              AND COALESCE(di.resolved_industry, ei.industry, 'Unknown') IN
                  ('Retail','Media','Architecture','Transportation','Entertainment',
                   'Labor','Venture Capital','Retail / Media / Other')
        """, base_params).fetchone()[0] or 0
        main_groups.append(("Retail / Media / Other", other_total, other_donors_count))

    # Sort by total descending, build final list
    main_groups.sort(key=lambda x: -x[1])

    interest_groups = []
    for ind, total, donors in main_groups:
        entry = {
            "label": ind,
            "donors": donors,
            "total": total,
            "color": INDUSTRY_COLORS.get(ind, "#94a3b8"),
        }
        if ind in NO_DONUT:
            entry["noDonut"] = True
        interest_groups.append(entry)

    # ── Notable firms (employers with 3+ distinct donors, excluding noise labels) ──
    notable_rows = cur.execute(f"""
        SELECT
            COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, '') as firm,
            COALESCE(di.resolved_industry, ei.industry, 'Unknown') as industry,
            COALESCE(ei.interest_tags, '') as tags,
            COUNT(DISTINCT cf.donor_id) as donors,
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as total
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {BASE_WHERE}
          AND COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, '') != ''
          AND UPPER(COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, ''))
              NOT IN {FIRM_NOISE_SQL}
          AND COALESCE(di.resolved_confidence, '') NOT LIKE '%-noemp'
        GROUP BY firm
        HAVING COUNT(DISTINCT cf.donor_id) >= 3
        ORDER BY total DESC
        LIMIT 20
    """, base_params).fetchall()

    notable_firms = []
    for firm, industry, tags, donors, total in notable_rows:
        notable_firms.append({
            "firm": firm,
            "industry": industry,
            "tags": tags or "",
            "donors": int(donors),
            "total": int(total),
            "color": INDUSTRY_COLORS.get(industry, "#94a3b8"),
        })

    # ── Top donors ────────────────────────────────────────────────────────────
    # Only INDIVIDUAL donors with a resolved canonical name
    top_donor_rows = cur.execute(f"""
        SELECT
            di.canonical_name as name,
            COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, '') as employer,
            COALESCE(di.resolved_industry, ei.industry, 'Unknown') as industry,
            COALESCE(ei.interest_tags, '') as tags,
            COUNT(*) as cnt,
            ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as total
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {BASE_WHERE}
          AND cf.donor_type = 'INDIVIDUAL'
          AND di.canonical_name IS NOT NULL
          AND di.canonical_name != ''
        GROUP BY cf.donor_id
        ORDER BY total DESC
        LIMIT 10
    """, base_params).fetchall()

    top_donors = []
    for name, employer, industry, tags, cnt, total in top_donor_rows:
        top_donors.append({
            "name": name or "",
            "employer": employer or "",
            "industry": industry or "",
            "tags": tags or "",
            "total": int(total),
            "count": int(cnt),
        })

    # ── All donations ──────────────────────────────────────────────────────────
    all_donation_rows = cur.execute(f"""
        SELECT
            di.canonical_name,
            cf.date_iso,
            ROUND(COALESCE(cf.balanced_amount, cf.amount_real), 2),
            COALESCE(di.resolved_employer_display, ei.canonical_name, cf.donor_reported_employer, ''),
            COALESCE(di.resolved_industry, ei.industry, 'Unknown'),
            TRIM(COALESCE(cf.city_state_zip, ''))
        FROM campaign_finance cf
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        LEFT JOIN donor_identities di ON cf.donor_id = di.donor_id
        WHERE {BASE_WHERE}
        ORDER BY cf.date_iso DESC
    """, base_params).fetchall()

    all_donations = [list(r) for r in all_donation_rows]

    # ── Partisan lean (FEC + TEC combined) ───────────────────────────────────
    # Pulls per-donor dem/rep/other totals from both the FEC donor history and
    # the Texas Ethics Commission tracked-PAC giving. Combined lean =
    # (fec_dem + tec_dem) / (fec_dem + fec_rep + tec_dem + tec_rep).
    donor_rows = cur.execute(f"""
        SELECT di.donor_id, di.canonical_name,
               COALESCE(di.fec_total_dem, 0)   AS fec_dem,
               COALESCE(di.fec_total_rep, 0)   AS fec_rep,
               COALESCE(di.fec_total_other, 0) AS fec_other,
               COALESCE(di.fec_total_donations, 0) AS fec_n,
               COALESCE(di.tec_total_dem, 0)   AS tec_dem,
               COALESCE(di.tec_total_rep, 0)   AS tec_rep,
               COALESCE(di.tec_total_other, 0) AS tec_other,
               COALESCE(di.tec_total_donations, 0) AS tec_n,
               SUM(cf.amount_real) as local_total
        FROM donor_identities di
        JOIN campaign_finance cf ON cf.donor_id = di.donor_id
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        WHERE {BASE_WHERE}
          AND (di.fec_partisan_lean IS NOT NULL OR COALESCE(di.tec_matched, 0) = 1)
        GROUP BY di.donor_id
    """, base_params).fetchall()

    partisan_lean = None
    if donor_rows:
        buckets = [
            {"label": "Strong D",  "min": 0.9, "max": 1.01, "donors": 0, "total": 0},
            {"label": "Lean D",    "min": 0.6, "max": 0.9,  "donors": 0, "total": 0},
            {"label": "Mixed",     "min": 0.4, "max": 0.6,  "donors": 0, "total": 0},
            {"label": "Lean R",    "min": 0.1, "max": 0.4,  "donors": 0, "total": 0},
            {"label": "Strong R",  "min": -0.01, "max": 0.1, "donors": 0, "total": 0},
        ]
        total_dem_donors = 0
        total_rep_donors = 0
        total_mixed_donors = 0
        total_lean_amount = 0
        weighted_lean_sum = 0

        donors_list = []
        donor_ids_matched = []
        fec_only_count = 0
        tec_only_count = 0
        both_count = 0

        for r in donor_rows:
            did, name, fec_dem, fec_rep, fec_other, fec_n, \
                tec_dem, tec_rep, tec_other, tec_n, local = r
            combined_dem   = (fec_dem or 0)   + (tec_dem or 0)
            combined_rep   = (fec_rep or 0)   + (tec_rep or 0)
            combined_other = (fec_other or 0) + (tec_other or 0)
            partisan_amount = combined_dem + combined_rep
            if partisan_amount <= 0:
                # Donor only gave to non-partisan (Other) PACs — skip from lean.
                continue
            lean = combined_dem / partisan_amount

            if fec_n and tec_n:
                both_count += 1
            elif fec_n:
                fec_only_count += 1
            else:
                tec_only_count += 1

            amt = local or 0
            for b in buckets:
                if b["min"] <= lean < b["max"]:
                    b["donors"] += 1
                    b["total"] += round(amt, 2)
                    break
            if lean >= 0.6:
                total_dem_donors += 1
            elif lean <= 0.4:
                total_rep_donors += 1
            else:
                total_mixed_donors += 1
            if amt > 0:
                weighted_lean_sum += lean * amt
                total_lean_amount += amt

            donors_list.append({
                "id": did, "name": name, "lean": round(lean, 3),
                "dem": round(combined_dem, 0),
                "rep": round(combined_rep, 0),
                "other": round(combined_other, 0),
                "fec_n": fec_n or 0,
                "tec_n": tec_n or 0,
                "fec_dem": round(fec_dem or 0, 0),
                "fec_rep": round(fec_rep or 0, 0),
                "tec_dem": round(tec_dem or 0, 0),
                "tec_rep": round(tec_rep or 0, 0),
                "local": round(amt, 0),
            })
            donor_ids_matched.append(did)

        donors_list.sort(key=lambda d: -(d["dem"] + d["rep"]))
        weighted_avg = round(weighted_lean_sum / total_lean_amount, 3) if total_lean_amount > 0 else None

        # Committee-level aggregates per donor (FEC + TEC)
        donor_committees = {}
        if donor_ids_matched:
            placeholders = ",".join("?" * len(donor_ids_matched))
            # FEC side
            fec_comm_rows = cur.execute(f"""
                SELECT fcr.donor_id, fcc.committee_name, fcc.classification,
                       SUM(fcr.contribution_amount) as total, COUNT(*) as n,
                       fcr.committee_id,
                       MIN(fcr.contribution_date), MAX(fcr.contribution_date)
                FROM fec_contributions_raw fcr
                LEFT JOIN fec_committee_cache fcc ON fcc.committee_id = fcr.committee_id
                WHERE fcr.donor_id IN ({placeholders})
                  AND fcr.contribution_amount > 0
                GROUP BY fcr.donor_id, fcr.committee_id
                ORDER BY total DESC
            """, donor_ids_matched).fetchall()
            for row in fec_comm_rows:
                did = row[0]
                donor_committees.setdefault(did, []).append({
                    "name": row[1] or "Unknown Committee",
                    "party": row[2] or "Other",
                    "total": round(row[3], 0),
                    "n": row[4],
                    "source": "FEC",
                    "committee_id": row[5],
                    "first": row[6],
                    "last": row[7],
                })
            # TEC side (state PACs)
            TEC_LEAN = {
                "00028135": "Rep", "00015555": "Rep", "00089881": "Rep",
                "00061927": "Rep", "00015666": "Dem",
                "00070864": "Other", "00015487": "Other", "00017303": "Other",
                "00015700": "Other", "00035370": "Other",
            }
            has_tec = cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='texas_contributions_raw'"
            ).fetchone()
            tec_comm_rows = [] if not has_tec else cur.execute(f"""
                SELECT austin_donor_id, filer_name, filer_ident,
                       SUM(CAST(contribution_amount AS REAL)) as total, COUNT(*) as n
                FROM texas_contributions_raw
                WHERE austin_donor_id IN ({placeholders})
                  AND contribution_amount > 0
                GROUP BY austin_donor_id, filer_ident
                ORDER BY total DESC
            """, donor_ids_matched).fetchall()
            for row in tec_comm_rows:
                did = row[0]
                donor_committees.setdefault(did, []).append({
                    "name": row[1] or "Unknown TX Committee",
                    "party": TEC_LEAN.get(row[2], "Other"),
                    "total": round(row[3], 0),
                    "n": row[4],
                    "source": "TEC",
                })

        # Most-common FEC spelling of each matched donor's name (for deep links to
        # the FEC receipts search)
        donor_fec_names = {}
        if donor_ids_matched:
            placeholders = ",".join("?" * len(donor_ids_matched))
            for did, fname, _cnt in cur.execute(f"""
                SELECT donor_id, fec_contributor_name, COUNT(*) as c
                FROM fec_contributions_raw
                WHERE donor_id IN ({placeholders}) AND fec_contributor_name IS NOT NULL
                GROUP BY donor_id, fec_contributor_name
                ORDER BY c ASC
            """, donor_ids_matched).fetchall():
                donor_fec_names[did] = fname  # last row per donor = most common

        partisan_lean = {
            "matched_donors": len(donors_list),
            "total_donors": unique_donors,
            "dem_donors": total_dem_donors,
            "rep_donors": total_rep_donors,
            "mixed_donors": total_mixed_donors,
            "fec_only": fec_only_count,
            "tec_only": tec_only_count,
            "both_sources": both_count,
            "weighted_lean": weighted_avg,
            "buckets": buckets,
            "donors": donors_list,
            "donor_committees": donor_committees,
            "donor_fec_names": donor_fec_names,
        }
        print(f"  Partisan lean (FEC+TEC): {len(donors_list)} donors, "
              f"D={total_dem_donors} R={total_rep_donors} M={total_mixed_donors}, "
              f"FEC-only={fec_only_count} TEC-only={tec_only_count} both={both_count}, "
              f"weighted={weighted_avg}")

    # ── Israel/Palestine donor spectrum ──────────────────────────────────────
    ip_spectrum = None
    ip_rows = cur.execute(f"""
        SELECT di.donor_id, di.canonical_name, di.ip_spectrum, di.ip_tier,
               di.ip_total, di.ip_committees,
               SUM(cf.amount_real) as local_total,
               di.fec_partisan_lean
        FROM donor_identities di
        JOIN campaign_finance cf ON cf.donor_id = di.donor_id
        LEFT JOIN employer_identities ei ON cf.employer_id = ei.employer_id
        WHERE {BASE_WHERE} AND di.ip_spectrum IS NOT NULL
        GROUP BY di.donor_id
        ORDER BY di.ip_total DESC
    """, base_params).fetchall()

    if ip_rows:
        # Build committee name lookup
        comm_names = {}
        for cid, cname in cur.execute("SELECT committee_id, committee_name FROM fec_committee_cache WHERE ip_category IS NOT NULL").fetchall():
            comm_names[cid] = cname

        # Itemized FEC receipts to IP-flagged committees, per donor (dates + amounts
        # for the profile page's drill-down panel)
        ip_donor_ids = [row[0] for row in ip_rows]
        ip_tx_by_donor = {}
        ip_fec_names = {}
        if ip_donor_ids:
            ph = ",".join("?" * len(ip_donor_ids))
            tx_rows = cur.execute(f"""
                SELECT fcr.donor_id, fcc.committee_name, fcc.ip_category,
                       fcr.contribution_date, fcr.contribution_amount,
                       fcr.committee_id
                FROM fec_contributions_raw fcr
                JOIN fec_committee_cache fcc ON fcc.committee_id = fcr.committee_id
                WHERE fcr.donor_id IN ({ph}) AND fcc.ip_category IS NOT NULL
                ORDER BY fcr.contribution_date DESC
            """, ip_donor_ids).fetchall()
            for r in tx_rows:
                ip_tx_by_donor.setdefault(r[0], []).append({
                    "committee": r[1] or "Unknown Committee",
                    "category": r[2],
                    "date": r[3],
                    "amount": round(r[4] or 0, 0),
                    "committee_id": r[5],
                })
            # Most-common FEC spelling of each IP donor's name (for FEC deep links)
            ip_fec_names = {}
            for did, fname, _cnt in cur.execute(f"""
                SELECT donor_id, fec_contributor_name, COUNT(*) as c
                FROM fec_contributions_raw
                WHERE donor_id IN ({ph}) AND fec_contributor_name IS NOT NULL
                GROUP BY donor_id, fec_contributor_name
                ORDER BY c ASC
            """, ip_donor_ids).fetchall():
                ip_fec_names[did] = fname

        categories = {}
        donors_by_cat = {}
        for row in ip_rows:
            cat = row[2]
            if cat not in categories:
                categories[cat] = {"donors": 0, "ip_total": 0, "local_total": 0}
                donors_by_cat[cat] = []
            categories[cat]["donors"] += 1
            categories[cat]["ip_total"] += row[4] or 0
            categories[cat]["local_total"] += row[6] or 0
            comm_list = []
            if row[5]:
                for cid in row[5].split(","):
                    comm_list.append({"id": cid.strip(), "name": comm_names.get(cid.strip(), cid.strip())})
            donors_by_cat[cat].append({
                "name": row[1], "tier": row[3],
                "ip_total": round(row[4] or 0, 0),
                "local_total": round(row[6] or 0, 0),
                "partisan_lean": round(row[7], 3) if row[7] is not None else None,
                "committees": comm_list,
                "transactions": ip_tx_by_donor.get(row[0], []),
                "fec_name": ip_fec_names.get(row[0]),
            })

        # Order: hawkish first, then liberal zionist, then pro-palestine
        cat_order = ["hawkish_proisrael", "liberal_zionist", "pro_palestine"]
        cat_labels = {
            "hawkish_proisrael": "Pro-Israel (AIPAC-aligned)",
            "liberal_zionist": "Liberal Zionist",
            "pro_palestine": "Pro-Palestine",
        }

        spectrum_list = []
        for cat in cat_order:
            if cat in categories:
                spectrum_list.append({
                    "key": cat,
                    "label": cat_labels.get(cat, cat),
                    "donors": categories[cat]["donors"],
                    "ip_total": round(categories[cat]["ip_total"], 0),
                    "local_total": round(categories[cat]["local_total"], 0),
                    "donor_list": donors_by_cat[cat],
                })

        ip_spectrum = {
            "total_flagged": len(ip_rows),
            "categories": spectrum_list,
        }
        for s in spectrum_list:
            print(f"  IP spectrum: {s['label']}: {s['donors']} donors, "
                  f"${s['ip_total']:,.0f} federal, ${s['local_total']:,.0f} local")

    # ── Verified civic affiliations ──────────────────────────────────────────
    # Pulls organizational roles (board memberships, honors, employer ties)
    # from the civic_affiliations table for donors to THIS candidate.
    # Matches on last-name + first-name (with common nickname aliases).
    civic_affiliations_payload = None
    # Only proceed if the civic_affiliations table exists
    has_civic_table = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='civic_affiliations'"
    ).fetchone() is not None

    if has_civic_table:
        # Common nicknames → canonical first names for matching
        NICKNAME_ALIASES = {
            "jeff": "jeffrey", "jeffrey": "jeff",
            "rick": "richard", "richard": "rick", "ricky": "richard",
            "dave": "david", "david": "dave",
            "mike": "michael", "michael": "mike",
            "bob": "robert", "robert": "bob", "rob": "robert",
            "bill": "william", "william": "bill",
            "chris": "christopher", "christopher": "chris",
            "steve": "steven", "steven": "steve", "stephen": "steve",
            "dan": "daniel", "daniel": "dan",
            "tom": "thomas", "thomas": "tom",
            "ed": "edward", "edward": "ed", "eddie": "edward",
            "andy": "andrew", "andrew": "andy",
            "val": "valerie", "valerie": "val",
            "lil": "lily", "lily": "lillian",
            "kim": "kimberly", "kimberly": "kim",
            "laurie": "laura", "laura": "laurie",
            "lauren": "laurence",
        }

        def name_key(canon_name):
            """Return a comparable (last, first_normalized) tuple."""
            if not canon_name or "," not in canon_name:
                return None
            last, first = canon_name.split(",", 1)
            last = last.strip().lower()
            first = first.strip().lower()
            # Strip middle initial/name
            first = first.split()[0] if first else ""
            # Remove trailing period
            first = first.rstrip(".")
            return (last, first)

        # Pull all Qadri donors with local totals
        donor_rows = cur.execute(f"""
            SELECT di.canonical_name,
                   ROUND(SUM(COALESCE(cf.balanced_amount, cf.amount_real)), 0) as local_total,
                   COUNT(*) as gift_count
            FROM campaign_finance cf
            JOIN donor_identities di ON cf.donor_id = di.donor_id
            WHERE {BASE_WHERE}
              AND di.canonical_name IS NOT NULL
              AND di.canonical_name != ''
            GROUP BY di.canonical_name
        """, base_params).fetchall()

        # Aggregate local totals per name_key
        donor_totals = {}  # {(last, first): {name, total, gifts}}
        for cname, total, gifts in donor_rows:
            key = name_key(cname)
            if not key:
                continue
            if key not in donor_totals or (total or 0) > donor_totals[key]["total"]:
                donor_totals[key] = {"name": cname, "total": int(total or 0), "gifts": int(gifts or 0)}

        # Also index by last-name + nickname-normalized-first for alias matching
        donor_alias_index = {}  # {(last, alias_first): donor_key}
        for key in donor_totals.keys():
            last, first = key
            donor_alias_index[(last, first)] = key
            if first in NICKNAME_ALIASES:
                donor_alias_index[(last, NICKNAME_ALIASES[first])] = key
            # First initial fallback (only if first name has 2+ chars)
            if len(first) >= 1:
                donor_alias_index.setdefault((last, first[0]), key)

        # Pull all civic_affiliations rows
        ca_rows = cur.execute("""
            SELECT canonical_name, organization, role, category, source_url, notes
            FROM civic_affiliations
            ORDER BY canonical_name
        """).fetchall()

        # Group by matched donor_key
        donor_affils = {}  # {donor_key: {name, total, gifts, rows: [...]}}
        for ca_name, org, role, category, source_url, notes in ca_rows:
            ca_key = name_key(ca_name)
            if not ca_key:
                continue
            # Try exact match first
            matched = None
            if ca_key in donor_totals:
                matched = ca_key
            else:
                # Alias match
                if ca_key in donor_alias_index:
                    matched = donor_alias_index[ca_key]
                else:
                    last, first = ca_key
                    # Nickname alias reverse lookup
                    if first in NICKNAME_ALIASES:
                        alt_first = NICKNAME_ALIASES[first]
                        if (last, alt_first) in donor_totals:
                            matched = (last, alt_first)
                        elif (last, alt_first) in donor_alias_index:
                            matched = donor_alias_index[(last, alt_first)]

            if not matched:
                continue

            if matched not in donor_affils:
                donor_affils[matched] = {
                    "donor_name": donor_totals[matched]["name"],
                    "local_total": donor_totals[matched]["total"],
                    "gifts": donor_totals[matched]["gifts"],
                    "categories": set(),
                    "rows": [],
                    "has_aipac_direct": False,
                    "has_jewish_civic": False,
                    "has_oil_gas": False,
                    "has_pro_israel": False,
                    "has_liberal_zionist": False,
                    "has_adl": False,
                }
            cat = category or ""
            donor_affils[matched]["categories"].add(cat)
            donor_affils[matched]["rows"].append({
                "org": org,
                "role": role or "",
                "category": cat,
                "source": source_url or "",
                "notes": notes or "",
            })
            if cat == "aipac_direct":
                donor_affils[matched]["has_aipac_direct"] = True
            if cat == "jewish_civic":
                donor_affils[matched]["has_jewish_civic"] = True
            if cat == "pro_israel":
                donor_affils[matched]["has_pro_israel"] = True
            if cat == "liberal_zionist":
                donor_affils[matched]["has_liberal_zionist"] = True
            if cat.startswith("oil_gas"):
                donor_affils[matched]["has_oil_gas"] = True
            # ADL detection via organization name (no dedicated ADL category)
            if org and ("anti-defamation league" in org.lower() or "adl" in org.lower()):
                donor_affils[matched]["has_adl"] = True

        # Build bucket lists. A donor can appear in multiple buckets if they
        # have roles in multiple categories — but each row only attaches to
        # its own category inside that bucket.
        def bucket_entry(d, row_filter):
            """Build a donor entry with only rows matching row_filter()."""
            rows = [r for r in d["rows"] if row_filter(r)]
            if not rows:
                return None
            # Sort: primary/direct roles first (board member, chair, founder), then alphabetical
            PRIORITY_KEYWORDS = ["chair", "founder", "president", "board", "director",
                                 "trustee", "national", "namesake", "honoree"]
            def row_priority(r):
                role_lower = (r["role"] or "").lower()
                for i, kw in enumerate(PRIORITY_KEYWORDS):
                    if kw in role_lower:
                        return (0, i, r["org"])
                return (1, 99, r["org"])
            rows.sort(key=row_priority)
            return {
                "donor_name": d["donor_name"],
                "local_total": d["local_total"],
                "gifts": d["gifts"],
                "organizations": rows,
            }

        def sort_donors(entries):
            """Sort donors by local_total desc, then name."""
            return sorted(entries, key=lambda e: (-e["local_total"], e["donor_name"]))

        # ── Bucket assembly (config-driven) ──────────────────────────────────
        # Previously this filtered to four hard-coded buckets and dropped every
        # other category BEFORE serializing, so civic/political/business/
        # gun_control/military_defense/gun_rights/healthcare/industry rows never
        # reached any *_data.json at all -- 95-100% of D1 findings and 70% of
        # Watson's were invisible. Buckets are now declared in AFFILIATION_BUCKETS
        # and every category is emitted; the template decides what to display.
        def matches(bucket, row_category):
            if bucket.get("prefix"):
                return row_category.startswith(bucket["prefix"])
            return row_category in bucket["categories"]

        def is_donation_restatement(row):
            """True when a `political` row only restates that someone gave money.

            Dedup rule for the Political & Campaign Roles card. The Federal
            Partisan Lean section already renders every donor's giving history
            from structured FEC + Texas PAC data, dollar-weighted and
            classified. A prose row reading "Donor ($2,500, 2012)" duplicates
            that less rigorously and adds nothing a reader can act on.

            KEEP anything describing a ROLE the chart cannot show -- party
            chair, campaign treasurer, finance-committee member, endorsement,
            lobby registration, elected or appointed office, union political
            director. DROP anything whose role text leads with giving and names
            no such role.

            Judgment call: donations to state and city PACs (Save Austin Now,
            Aqui Estamos) are dropped too, even though the partisan chart is
            FEC/TEC-based and may not cover every local committee. They are
            still donations rather than roles, which is the line this card
            draws. Roughly 23 of 372 political rows drop under this rule.
            """
            role = row.get("role") or ""
            return bool(_GIVING_LEAD.match(role)) and not _POLITICAL_ROLE.search(role)

        by_category = {}
        totals = {}
        dropped_restatements = 0
        for bucket in AFFILIATION_BUCKETS:
            key = bucket["key"]
            drop_dupes = bucket.get("drop_donation_restatements")

            def row_ok(r, b=bucket, dd=drop_dupes):
                if not matches(b, r["category"]):
                    return False
                if dd and is_donation_restatement(r):
                    return False
                return True

            if drop_dupes:
                for d in donor_affils.values():
                    for r in d["rows"]:
                        if matches(bucket, r["category"]) and is_donation_restatement(r):
                            dropped_restatements += 1

            entries = []
            for d in donor_affils.values():
                entry = bucket_entry(d, row_ok)
                if entry:
                    entries.append(entry)
            if bucket.get("sort") == "alpha":
                entries.sort(key=lambda e: e["donor_name"].lower())
            else:
                entries = sort_donors(entries)
            by_category[key] = entries
            totals[key] = len(entries)

        civic_affiliations_payload = {
            "total_donors_with_affiliations": len(donor_affils),
            "totals": totals,
            # Legacy keys kept so older cached payloads / any external consumer
            # keep working. jewish_civic replaces the old ADL org-name string
            # match, which surfaced only orgs literally named "ADL" and dropped
            # the other ~85 jewish_civic names while every other community's
            # civic ties were dropped entirely -- see Phase 2 of
            # AFFILIATION_TEMPLATE_EXPANSION_PLAN.md.
            "total_adl": totals.get("jewish_civic", 0),
            "total_aipac_direct": totals.get("pro_israel_advocacy", 0),
            "total_liberal_zionist": totals.get("liberal_zionist", 0),
            "total_oil_gas": totals.get("oil_gas", 0),
            "by_category": by_category,
        }
        print(f"  Civic affiliations: {len(donor_affils)} donors matched")
        for bucket in AFFILIATION_BUCKETS:
            n = totals.get(bucket["key"], 0)
            if n:
                print(f"    {bucket['label']:34} {n}")
        if dropped_restatements:
            print(f"    (dropped {dropped_restatements} donation-restatement rows "
                  f"already covered by the partisan-lean chart)")

    # ── Election cycles ───────────────────────────────────────────────────────
    cycles = []
    if slug in CANDIDATE_CYCLES:
        for cycle_def in CANDIDATE_CYCLES[slug]:
            cycle_data = build_cycle_data(cur, slug, cycle_def, by_year)
            cycles.append(cycle_data)
        print(f"  Built {len(cycles)} election cycles for '{slug}'")
    else:
        print(f"  No cycle definitions found for slug '{slug}' — cycles will be empty")

    conn.close()

    # ── Assemble meta ─────────────────────────────────────────────────────────
    generated_at = datetime.now(timezone.utc).isoformat()
    meta = {
        "candidate_name": candidate_name,
        "candidate_slug": slug,
        "office": OFFICE_OVERRIDE.get(slug, "San Antonio City Council"),
        "generated_at": generated_at,
    }

    # ── Write {slug}_data.json (everything except all_donations) ──────────────
    data_payload = {
        "meta": meta,
        "hero": hero,
        "by_year": by_year,
        "interest_groups": interest_groups,
        "notable_firms": notable_firms,
        "top_donors": top_donors,
        "cycles": cycles,
        "partisan_lean": partisan_lean,
        "ip_spectrum": ip_spectrum,
        "civic_affiliations": civic_affiliations_payload,
    }
    os.makedirs(output_dir, exist_ok=True)
    data_path = os.path.join(output_dir, f"{slug}_data.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data_payload, f, separators=(",", ":"), ensure_ascii=False)
    print(f"Written: {data_path}  ({os.path.getsize(data_path):,} bytes)")

    # ── Write {slug}_all_donations.json ───────────────────────────────────────
    donations_path = os.path.join(output_dir, f"{slug}_all_donations.json")
    donations_json = json.dumps(all_donations, separators=(",", ":"), ensure_ascii=False)
    with open(donations_path, "w", encoding="utf-8") as f:
        f.write(donations_json)
    print(f"Written: {donations_path}  ({os.path.getsize(donations_path):,} bytes, {len(all_donations):,} records)")

    # ── Verification summary ───────────────────────────────────────────────────
    print(f"\n=== Verification: {candidate_name} ===")
    print(f"  Total raised:          ${total_raised:,}")
    print(f"  Unique donors:         {unique_donors:,}")
    print(f"  Total contributions:   {total_contributions:,}")
    print(f"  Employer-affiliated:   {employer_affiliated_pct}%")
    print(f"  Top industry:          {top_industry}")
    print(f"  Interest groups:       {len(interest_groups)}")
    print(f"  Notable firms (3+):    {len(notable_firms)}")
    print(f"  Top donors (10):       {len(top_donors)}")
    print(f"  All donations rows:    {len(all_donations):,}")
    print(f"\n  By year:")
    for y in by_year:
        print(f"    {y['year']}: {y['count']:,} gifts, ${y['total']:,}")
    print(f"\n  Interest groups (top 5):")
    for g in interest_groups[:5]:
        print(f"    {g['label']}: ${g['total']:,} ({g['donors']} donors)")
    print(f"\n  Top donors (3):")
    for d in top_donors[:3]:
        print(f"    {d['name']}: ${d['total']:,} ({d['count']} gifts) @ {d['employer']}")

    # ── Cycle verification ────────────────────────────────────────────────────
    if cycles:
        print(f"\n  Election cycles ({len(cycles)}):")
        for c in cycles:
            h = c['hero']
            print(f"\n    [{c['label']}] {c['year_range']} (election {c['election_year']})")
            print(f"      Total raised:        ${h['total_raised']:,}")
            print(f"      Unique donors:       {h['unique_donors']:,}")
            print(f"      Employer-affiliated: {h['employer_affiliated_pct']}%")
            print(f"      Top industry:        {h['top_industry']}")
            print(f"      Top 3 industries:")
            for ig in c['interest_groups'][:3]:
                pct = round(ig['total'] / h['total_raised'] * 100, 1) if h['total_raised'] else 0
                print(f"        {ig['label']}: ${ig['total']:,} ({pct}%)")

        if len(cycles) >= 2:
            c0 = cycles[0]
            c1 = cycles[1]
            delta = round(c1['hero']['employer_affiliated_pct'] - c0['hero']['employer_affiliated_pct'], 1)
            sign = "+" if delta >= 0 else ""
            print(f"\n  Employer-affiliated delta ({c0['label']} → {c1['label']}): {sign}{delta} pts")

    return data_payload, all_donations


def main():
    parser = argparse.ArgumentParser(description="Generate profile JSON for a campaign finance candidate")
    parser.add_argument("--candidate", required=True, help="Candidate name fragment (e.g. 'Qadri'). "
                        "Pass an exact recipient string to disambiguate (e.g. 'Alter, Ryan').")
    parser.add_argument("--slug", default=None, help="Override the output slug (e.g. 'alter'). "
                        "Defaults to a slugified candidate fragment.")
    parser.add_argument("--output-dir", default=_REPO_ROOT,
                        help="Output directory for JSON files")
    args = parser.parse_args()

    generate(args.candidate, args.output_dir, slug_override=args.slug)


if __name__ == "__main__":
    main()
