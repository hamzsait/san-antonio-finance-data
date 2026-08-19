"""Build the two UNLISTED share-by-link focus pages (user request 2026-08-19):

    sanantonio/arena-money/index.html    arena_venue vs arena_opposition
    sanantonio/school-money/index.html   charter_school vs public_school_advocacy

Each page ranks the mayor + 10 council members by contributions received from
donors with documented affiliations on each side of the spectrum, with
expandable per-donor receipts (org, role, source link, dollars to that
member). Data is inlined at build time — no JSON fetch, fully static.

Unlisted like shaikh: robots noindex/nofollow, not in the landing, nav, or
sitemap. Anyone with the link can view; nothing on the site points to them.
publish_site.py mirrors the whole sanantonio/ tree, so a normal publish
ships them.

Money definition matches the profiles: txn_type='contribution',
amount_real>0, superseded restatements excluded, recipient restricted to the
member's own campaign (RECIPIENT_ALIASES), donors joined on canonical_name.

Usage: python build_focus_pages.py
"""
import html
import os
import sqlite3
from datetime import date

import generate_profile_data as gpd
from build_candidate import ROSTER

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "san_antonio_finance.db")
SITE = os.path.join(ROOT, "sanantonio")

PAGES = [
    {
        "slug": "arena-money",
        "title": "Arena Money on San Antonio's Council",
        "h1": "The Arena Money Scoreboard",
        "sub": "Mayor and council, ranked by campaign money from donors with a documented "
               "stake in the downtown Spurs arena — and from its documented opposition.",
        "context": (
            "Project Marvel is the multi-billion-dollar downtown district anchored by a "
            "~$1.3B Spurs arena at Hemisfair. Bexar County voters approved the venue tax "
            "(Prop B) 52.1%–47.9% in November 2025, and in August 2026 City Council "
            "declined to put the city's ~$489M share to a public vote — making every "
            "member's donor ties to the arena's beneficiaries and opponents a live "
            "transparency question. This page counts only contributions from donors with "
            "a <em>documented</em> role on one side or the other: Spurs Sports &amp; "
            "Entertainment ownership and staff, firms on the arena project team, and "
            "documented boosters on one side; organized venue-tax/subsidy opposition "
            "(COPS/Metro-aligned groups, union opposition) on the other."),
        "pro": {"cats": ("arena_venue", "arena_marvel", "spurs_arena"),
                "label": "Arena-affiliated", "color": "#c2410c",
                "desc": "Donors with a documented stake in the arena / Project Marvel district"},
        "anti": {"cats": ("arena_opposition",),
                 "label": "Arena opposition", "color": "#4d7c0f",
                 "desc": "Donors with documented roles in organized opposition to the arena subsidy"},
    },
    {
        "slug": "school-money",
        "title": "Charter vs Public-School Money on San Antonio's Council",
        "h1": "The School Money Scoreboard",
        "sub": "Mayor and council, ranked by campaign money from the charter-school sector "
               "versus teacher unions and public-school advocacy.",
        "context": (
            "San Antonio is one of the most charter-saturated cities in Texas, and "
            "education money moves through its city races: Futuro San Antonio (whose PAC "
            "is funded largely by national school-choice donors), Charter Schools Now PAC "
            "(the Texas charter association's committee), and charter-network leadership "
            "on one side; the San Antonio Alliance of Teachers and Support Personnel, AFT "
            "locals, and public-school advocacy on the other. This page counts only "
            "contributions from donors with a <em>documented</em> role on one side or the "
            "other — network executives, board members, staff, advocacy organizations, and "
            "the PACs themselves where they gave directly."),
        "pro": {"cats": ("charter_school", "school_choice"),
                "label": "Charter-school sector", "color": "#9333ea",
                "desc": "Donors employed by or leading charter networks and school-choice advocacy/funding orgs"},
        "anti": {"cats": ("public_school_advocacy", "public_education_advocacy"),
                 "label": "Public-school advocacy", "color": "#0369a1",
                 "desc": "Donors with documented teacher-union or public-school advocacy roles"},
    },
]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()


def side_donors(slug, cats):
    """Donors to this member's own campaign holding an affiliation in cats.
    Returns [{name, total, gifts, orgs: [(org, role, source_url)]}] sorted by total desc."""
    aliases = gpd.RECIPIENT_ALIASES.get(slug)
    ph_cat = ",".join("?" * len(cats))
    ph_al = ",".join("?" * len(aliases))
    rows = cur.execute(f"""
        SELECT di.canonical_name AS name,
               SUM(cf.amount_real) AS total,
               COUNT(*) AS gifts
        FROM campaign_finance cf
        JOIN donor_identities di ON di.donor_id = cf.donor_id
        WHERE cf.filer_slug = ?
          AND cf.recipient IN ({ph_al})
          AND cf.txn_type = 'contribution'
          AND cf.amount_real > 0
          AND COALESCE(cf.superseded_by, '') = ''
          AND di.canonical_name IN (
              SELECT canonical_name FROM civic_affiliations WHERE category IN ({ph_cat}))
        GROUP BY di.canonical_name
        ORDER BY total DESC
    """, (slug, *aliases, *cats)).fetchall()
    out = []
    for r in rows:
        orgs = cur.execute(f"""
            SELECT organization, role, source_url FROM civic_affiliations
            WHERE canonical_name = ? AND category IN ({ph_cat})
            ORDER BY organization
        """, (r["name"], *cats)).fetchall()
        out.append({"name": r["name"], "total": r["total"], "gifts": r["gifts"],
                    "orgs": [(o["organization"], o["role"], o["source_url"]) for o in orgs]})
    return out


def money(n):
    return f"${n:,.0f}"


def esc(s):
    return html.escape(str(s or ""))


def donor_li(d):
    orgs = "".join(
        f'<li>{esc(o)}' + (f' — <span class="role">{esc(r)}</span>' if r else "")
        + (f' <a class="src" href="{esc(u)}" target="_blank" rel="noopener nofollow">source ↗</a>' if u else "")
        + "</li>"
        for o, r, u in d["orgs"])
    gifts = "1 gift" if d["gifts"] == 1 else f'{d["gifts"]} gifts'
    return (f'<div class="donor"><div class="donor-head"><span class="donor-name">{esc(d["name"])}</span>'
            f'<span class="donor-amt">{money(d["total"])} · {gifts}</span></div>'
            f'<ul class="orgs">{orgs}</ul></div>')


def build_page(cfg):
    members = []
    for e in ROSTER:
        pro = side_donors(e["slug"], cfg["pro"]["cats"])
        anti = side_donors(e["slug"], cfg["anti"]["cats"])
        members.append({
            "e": e,
            "pro": pro, "anti": anti,
            "pro_total": sum(d["total"] for d in pro),
            "anti_total": sum(d["total"] for d in anti),
        })
    # Rank: pro-side money desc, then anti-side desc so opposition-only members
    # sort above members with nothing on either side.
    members.sort(key=lambda m: (-m["pro_total"], -m["anti_total"]))
    max_bar = max([m["pro_total"] for m in members] + [m["anti_total"] for m in members] + [1])

    pro_all = sum(m["pro_total"] for m in members)
    anti_all = sum(m["anti_total"] for m in members)
    pc, ac = cfg["pro"]["color"], cfg["anti"]["color"]

    rows_html = []
    for i, m in enumerate(members, 1):
        e = m["e"]
        pro_w = max(0.6, 100 * m["pro_total"] / max_bar) if m["pro_total"] else 0
        anti_w = max(0.6, 100 * m["anti_total"] / max_bar) if m["anti_total"] else 0
        detail = ""
        if m["pro"] or m["anti"]:
            blocks = ""
            if m["pro"]:
                blocks += (f'<div class="side-h" style="color:{pc}">{cfg["pro"]["label"]} donors</div>'
                           + "".join(donor_li(d) for d in m["pro"]))
            if m["anti"]:
                blocks += (f'<div class="side-h" style="color:{ac}">{cfg["anti"]["label"]} donors</div>'
                           + "".join(donor_li(d) for d in m["anti"]))
            n = len(m["pro"]) + len(m["anti"])
            detail = (f'<details><summary>{n} documented donor{"s" if n != 1 else ""} — receipts</summary>'
                      f'{blocks}</details>')
        else:
            detail = '<div class="none">No donors with a documented role on either side.</div>'
        rows_html.append(f"""
  <section class="member">
    <div class="rank">{i}</div>
    <div class="body">
      <div class="who"><a href="/sanantonio/{e["slug"]}/">{esc(e["display"])}</a>
        <span class="dist">{esc(e["district"])}</span></div>
      <div class="bars">
        <div class="barrow"><span class="side-label" style="color:{pc}">{cfg["pro"]["label"]}</span>
          <div class="track"><div class="fill" style="width:{pro_w:.1f}%;background:{pc}"></div></div>
          <span class="amt">{money(m["pro_total"])}</span></div>
        <div class="barrow"><span class="side-label" style="color:{ac}">{cfg["anti"]["label"]}</span>
          <div class="track"><div class="fill" style="width:{anti_w:.1f}%;background:{ac}"></div></div>
          <span class="amt">{money(m["anti_total"])}</span></div>
      </div>
      {detail}
    </div>
  </section>""")

    url = f"https://decodepolitics.org/sanantonio/{cfg['slug']}/"
    desc = (f'{cfg["pro"]["label"]}: {money(pro_all)} · {cfg["anti"]["label"]}: {money(anti_all)} '
            f'across the mayor and all ten council districts, donor by donor with receipts.')

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<link rel="canonical" href="{url}">
<title>{esc(cfg["title"])} — decode(politics):</title>
<meta name="description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="decode(politics):">
<meta property="og:title" content="{esc(cfg["title"])} — decode(politics):">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="https://decodepolitics.org/assets/og/og-home.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(cfg["title"])} — decode(politics):">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="https://decodepolitics.org/assets/og/og-home.png">
<link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Ccircle%20cx='50'%20cy='50'%20r='50'%20fill='%2318314f'/%3E%3Cpath%20d='M43%2031%20L36%2031%20Q31%2031%2031%2036%20L31%2064%20Q31%2069%2036%2069%20L43%2069'%20fill='none'%20stroke='%23cfe3f5'%20stroke-width='7'%20stroke-linecap='round'%20stroke-linejoin='round'/%3E%3Cpath%20d='M57%2031%20L64%2031%20Q69%2031%2069%2036%20L69%2064%20Q69%2069%2064%2069%20L57%2069'%20fill='none'%20stroke='%23cfe3f5'%20stroke-width='7'%20stroke-linecap='round'%20stroke-linejoin='round'/%3E%3Ccircle%20cx='50'%20cy='42'%20r='5.5'%20fill='%23bf1a13'/%3E%3Ccircle%20cx='50'%20cy='58'%20r='5.5'%20fill='%23bf1a13'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ --page:#fff; --ink:#0c1a2c; --muted:#5b6b7a; --navy:#18314f;
          --line:rgba(24,49,79,.12); --soft:rgba(24,49,79,.045); --fn:#cc1f3c; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--page); color:var(--ink); font-family:'Inter',system-ui,sans-serif; }}
  .wrap {{ max-width:880px; margin:0 auto; padding:0 20px 80px; }}
  header.top {{ padding:26px 0 8px; }}
  .wordmark {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:19px;
              letter-spacing:-.015em; text-decoration:none; color:var(--navy); }}
  .wordmark .fn {{ color:var(--fn); }}
  h1 {{ font-family:'Space Grotesk',sans-serif; font-size:clamp(26px,5vw,38px); color:var(--navy);
       letter-spacing:-.02em; margin:26px 0 10px; }}
  .sub {{ color:var(--muted); font-size:16px; line-height:1.55; max-width:64ch; }}
  .context {{ margin:22px 0 6px; padding:16px 18px; background:var(--soft); border:1px solid var(--line);
             border-radius:14px; font-size:14.5px; line-height:1.6; color:var(--ink); }}
  .totals {{ display:flex; gap:14px; flex-wrap:wrap; margin:20px 0 8px; }}
  .tot {{ flex:1 1 220px; border:1px solid var(--line); border-radius:14px; padding:14px 16px; }}
  .tot .v {{ font-family:'Space Grotesk',sans-serif; font-size:26px; font-weight:700; }}
  .tot .l {{ font-size:13px; color:var(--muted); margin-top:2px; }}
  .member {{ display:flex; gap:14px; padding:20px 0; border-bottom:1px solid var(--line); }}
  .rank {{ flex:none; width:34px; height:34px; border-radius:50%; background:var(--navy); color:#fff;
          display:flex; align-items:center; justify-content:center; font-weight:700; font-size:15px;
          font-family:'Space Grotesk',sans-serif; margin-top:2px; }}
  .body {{ flex:1; min-width:0; }}
  .who {{ font-size:17px; font-weight:600; }}
  .who a {{ color:var(--ink); text-decoration:none; border-bottom:1px solid var(--line); }}
  .who a:hover {{ color:var(--fn); border-color:var(--fn); }}
  .dist {{ color:var(--muted); font-weight:500; font-size:13.5px; margin-left:8px; }}
  .bars {{ margin:10px 0 4px; display:grid; gap:6px; }}
  .barrow {{ display:grid; grid-template-columns:150px 1fr 84px; gap:10px; align-items:center; }}
  .side-label {{ font-size:12.5px; font-weight:600; }}
  .track {{ height:14px; background:var(--soft); border-radius:7px; overflow:hidden; }}
  .fill {{ height:100%; border-radius:7px; }}
  .amt {{ font-size:13px; font-weight:600; text-align:right; font-variant-numeric:tabular-nums; }}
  details {{ margin-top:8px; }}
  summary {{ cursor:pointer; font-size:13.5px; color:var(--muted); }}
  summary:hover {{ color:var(--fn); }}
  .side-h {{ font-size:12.5px; font-weight:700; text-transform:uppercase; letter-spacing:.04em;
            margin:12px 0 4px; }}
  .donor {{ border-left:3px solid var(--line); padding:7px 12px; margin:6px 0; background:var(--soft);
           border-radius:0 10px 10px 0; }}
  .donor-head {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
  .donor-name {{ font-weight:600; font-size:14px; }}
  .donor-amt {{ font-size:13px; color:var(--muted); font-variant-numeric:tabular-nums; }}
  .orgs {{ list-style:none; margin-top:3px; }}
  .orgs li {{ font-size:13px; color:var(--ink); line-height:1.5; }}
  .role {{ color:var(--muted); }}
  .src {{ font-size:12px; color:var(--fn); text-decoration:none; white-space:nowrap; }}
  .none {{ font-size:13.5px; color:var(--muted); margin-top:8px; }}
  .method {{ margin-top:34px; padding:16px 18px; border:1px solid var(--line); border-radius:14px;
            font-size:13.5px; line-height:1.65; color:var(--muted); }}
  .method strong {{ color:var(--ink); }}
  footer {{ margin-top:26px; font-size:12.5px; color:var(--muted); }}
  footer a {{ color:var(--muted); }}
  @media (max-width:560px) {{ .barrow {{ grid-template-columns:110px 1fr 74px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="top"><a class="wordmark" href="/sanantonio/">decode<span class="fn">(</span>politics<span class="fn">)</span>:</a></header>
  <h1>{cfg["h1"]}</h1>
  <p class="sub">{cfg["sub"]}</p>
  <div class="context">{cfg["context"]}</div>
  <div class="totals">
    <div class="tot"><div class="v" style="color:{pc}">{money(pro_all)}</div>
      <div class="l">{cfg["pro"]["label"]} — {cfg["pro"]["desc"]}</div></div>
    <div class="tot"><div class="v" style="color:{ac}">{money(anti_all)}</div>
      <div class="l">{cfg["anti"]["label"]} — {cfg["anti"]["desc"]}</div></div>
  </div>
  {"".join(rows_html)}
  <div class="method"><strong>How to read this:</strong> Every dollar above is a contribution to the
    member's own city campaign from a donor with a <strong>documented organizational role</strong> —
    ownership, board, leadership, staff, or a PAC giving directly — sourced from public records
    (filings, org leadership pages, news coverage, or the donor's filer-reported employer). Nothing
    is inferred from a name, a zip code, or fandom. <strong>Both sides were searched with equal
    depth</strong> — a $0 side is an absence in the record, not an unsearched category. San Antonio
    caps contributions per cycle ($1,000 mayor / $500 council), so influence shows up as many capped
    gifts across a family or firm, not single large checks. Click any member for their full donor
    profile; expand the receipts to see each donor's documented role and source.</div>
  <footer>Generated {date.today().isoformat()} from San Antonio campaign-finance filings ·
    <a href="/sanantonio/">all San Antonio profiles</a></footer>
</div>
</body>
</html>
"""
    out_dir = os.path.join(SITE, cfg["slug"])
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print(f"{cfg['slug']}: {cfg['pro']['label']} {money(pro_all)} vs {cfg['anti']['label']} "
          f"{money(anti_all)} — {out}")
    for m in members[:3]:
        print(f"   #{members.index(m)+1} {m['e']['display']}: {money(m['pro_total'])} / {money(m['anti_total'])}")


for cfg in PAGES:
    build_page(cfg)
