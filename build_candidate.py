"""
build_candidate.py
Repeatable driver that turns an already-enriched filer in san_antonio_finance.db
into a publishable static profile (ported from the Austin repo 2026-07-20):

    1. Exports {slug}_data.json + {slug}_all_donations.json into sanantonio/
       (via generate_profile_data)
    2. Materializes sanantonio/{slug}/index.html from profile_template.html
    3. Prints the stats needed for the filer's landing card (phase 3)

Everything builds into the local sanantonio/ folder, which is shaped exactly
like the deploy target (austin-finance-data/sanantonio/) so dev-server paths
match production paths. publish_site.py (phase 3) copies it across.

It does NOT re-run enrichment (identity, employer seed, FEC) — that is a
global pass already applied across the DB.

Usage:
    python build_candidate.py --slug jones
    python build_candidate.py --slug jones --html-only   # re-render HTML only
    python build_candidate.py --all-remaining            # every ROSTER entry
"""

import argparse
import json
import os
import re

# generate_profile_data reconfigures sys.stdout to UTF-8 on import; importing it
# once here is enough (re-wrapping stdout again closes the shared buffer under GC).
import generate_profile_data as gpd

# Repo-relative so builds work from any checkout/worktree of the repo.
ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(ROOT, "profile_template.html")
SITE_DIR = os.path.join(ROOT, "sanantonio")   # deploy-shaped output folder

# Built profiles. district / race are used only for the printed card snippet.
# Council members join this list phase by phase (see issue #1).
ROSTER = [
    {"slug": "jones", "display": "Gina Ortiz Jones", "district": "Mayor", "race": "Elected June 2025"},
    {"slug": "galvan", "display": "Ric Galvan", "district": "District 6", "race": "Elected June 2025"},
    {"slug": "kaur", "display": "Sukh Kaur", "district": "District 1", "race": "Re-elected June 2025"},
    {"slug": "mckeerodriguez", "display": "Jalen McKee-Rodriguez", "district": "District 2", "race": "Re-elected May 2025"},
    {"slug": "viagran", "display": "Phyllis Viagran", "district": "District 3", "race": "Re-elected May 2025"},
    {"slug": "mungia", "display": "Edward Mungia", "district": "District 4", "race": "Elected May 2025"},
    {"slug": "castillo", "display": "Teri Castillo", "district": "District 5", "race": "Re-elected May 2025"},
    {"slug": "gavito", "display": "Marina Alderete Gavito", "district": "District 7", "race": "Re-elected May 2025"},
]

# Non-officeholders rendered with candidate framing instead of incumbent
# framing. Shaikh (lost the 2025 D8 general) ships as a live-but-unlisted
# page — built and reachable by URL, never linked from the landing or nav
# (user decision 2026-07-20).
CANDIDATE_SLUGS = {"shaikh"}
UNLISTED_SLUGS = {"shaikh"}


def og_meta_for(slug: str) -> dict:
    """Social-preview strings for a slug, from the sanantonio_landing.json
    snapshot (generic fallback for unlisted profiles and roster entries the
    landing lists without stats yet)."""
    landing_path = os.path.join(SITE_DIR, "sanantonio_landing.json")
    c = None
    if os.path.exists(landing_path):
        with open(landing_path, "r", encoding="utf-8") as f:
            landing = json.load(f)
        c = next((c for c in landing["candidates"] if c["slug"] == slug), None)

    if c is None or not c.get("raised") or len(c.get("topGroups") or []) < 2:
        meta = {
            "title": "Candidate Profile — San Antonio Campaign Finance — decode(politics):",
            "desc": "San Antonio city campaign money, decoded donor by donor.",
        }
        if c is not None:
            meta["title"] = f"{c['name']} — San Antonio Campaign Finance — decode(politics):"
        return meta
    g = c["topGroups"]
    return {
        "title": f"{c['name']} — San Antonio Campaign Finance — decode(politics):",
        "desc": (
            f"{c['name']} ({c['district']}) raised {c['raised']} from {c['donors']} donors. "
            f"Top donor interests: {g[0]['label']} ({g[0]['amt']}) and {g[1]['label']} ({g[1]['amt']}). "
            "Every dollar decoded, donor by donor."
        ),
    }


CANDIDATE_TEMPLATE_SUBS = [
    # NOTE: the hero badge is NOT set here -- renderHero() overwrites it from
    # meta.office at runtime. See OFFICE_OVERRIDE in generate_profile_data.py.
    ('<div class="lbl">Raised 2022+</div>',
     '<div class="lbl">Total Raised</div>'),
    ('<span class="hint">2022+</span>',
     '<span class="hint">all filings</span>'),
]

# Officeholder profiles show the same neutral all-filings framing — SA's
# portal floor is 2016 and the default view is all-time (user decision).
OFFICEHOLDER_TEMPLATE_SUBS = CANDIDATE_TEMPLATE_SUBS


def make_profile_html(slug: str) -> str:
    """Render profile_template.html to sanantonio/{slug}/index.html with
    PROFILE_SLUG injected. Pages live at clean URLs (/sanantonio/<slug>/);
    the template uses root-absolute paths, so it renders correctly from any
    directory."""
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    new_html, n = re.subn(
        r"const PROFILE_SLUG = '[^']*';",
        f"const PROFILE_SLUG = '{slug}';",
        html,
        count=1,
    )
    if n != 1:
        raise RuntimeError("PROFILE_SLUG line not found in profile_template.html")

    og = og_meta_for(slug)
    new_html = (
        new_html.replace("__OG_SLUG__", slug)
        .replace("__OG_TITLE__", og["title"])
        .replace("__OG_DESC__", og["desc"])
    )

    subs = CANDIDATE_TEMPLATE_SUBS if slug in CANDIDATE_SLUGS else OFFICEHOLDER_TEMPLATE_SUBS
    for old, new in subs:
        new_html = new_html.replace(old, new)

    if slug in UNLISTED_SLUGS:
        # Unlisted pages must not leak into search results.
        new_html = new_html.replace(
            "<head>", '<head>\n<meta name="robots" content="noindex, nofollow">', 1)

    out_dir = os.path.join(SITE_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_html)
    return out_path


def fmt_money(n: int) -> str:
    """$3,203,912 -> $3.2M ; $357,094 -> $357K (matches existing card style)."""
    if n >= 1_000_000:
        return f"${n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"${round(n/1_000)}K"
    return f"${n}"


def build_one(entry: dict, html_only: bool = False):
    slug = entry["slug"]
    print("=" * 78)
    print(f"{'RENDER' if html_only else 'BUILD '}  {entry['display']}  ({entry['district']})  slug={slug}")
    print("=" * 78)

    if html_only:
        # Re-render HTML from the current template only; JSON already exported.
        html_path = make_profile_html(slug)
        print(f"Rendered: {html_path}")
        return entry, None

    data_payload, _ = gpd.generate(slug, SITE_DIR, slug_override=slug)
    html_path = make_profile_html(slug)
    print(f"Rendered: {html_path}")

    hero = data_payload["hero"]
    raised = fmt_money(hero["total_raised"])
    donors = f"{hero['unique_donors']:,}"
    empct = f"{hero['employer_affiliated_pct']}%"

    card = (
        f'    <a class="card" href="/sanantonio/{slug}/">\n'
        f'      <div class="card-name">{entry["display"]} <span class="badge badge-live">Live</span></div>\n'
        f'      <div class="card-meta">{entry["district"]} · {entry["race"]}</div>\n'
        f'      <div class="card-stats">\n'
        f'        <div><div class="stat-val">{raised}</div><div class="stat-lbl">Raised</div></div>\n'
        f'        <div><div class="stat-val">{donors}</div><div class="stat-lbl">Donors</div></div>\n'
        f'        <div><div class="stat-val">{empct}</div><div class="stat-lbl">Employer-affiliated</div></div>\n'
        f'      </div>\n'
        f'    </a>'
    )
    print("\n--- landing card (phase 3) -----------------------------------------------")
    print(card)
    print("--------------------------------------------------------------------------\n")
    return entry, hero


def main():
    p = argparse.ArgumentParser(description="Build a static profile for an enriched filer")
    p.add_argument("--all-remaining", action="store_true", help="Build every filer in ROSTER")
    p.add_argument("--slug", help="Build one filer by slug (ROSTER entry not required)")
    p.add_argument("--html-only", action="store_true",
                   help="Re-render profile HTML from the template only; skip JSON export")
    args = p.parse_args()

    if args.slug:
        entry = next((e for e in ROSTER if e["slug"] == args.slug), None)
        if not entry:
            entry = {"slug": args.slug, "display": args.slug.title(), "district": "?", "race": "?"}
        build_one(entry, args.html_only)
        return

    if args.all_remaining:
        results = [build_one(e, args.html_only) for e in ROSTER]
        print("\n\n#### SUMMARY ####")
        for entry, hero in results:
            if hero is None:
                print(f"  {entry['display']:20} {entry['district']:12}  (HTML re-rendered)")
            else:
                print(f"  {entry['display']:20} {entry['district']:12} "
                      f"${hero['total_raised']:>10,}  {hero['unique_donors']:>5} donors  "
                      f"{hero['employer_affiliated_pct']}% empl")
        return

    p.error("nothing to do: pass --all-remaining or --slug")


if __name__ == "__main__":
    main()
