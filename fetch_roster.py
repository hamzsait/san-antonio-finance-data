"""
fetch_roster.py
Maintain the candidate roster in `council_members`.

Two modes:
  1. (default) Pull the current SA city council from sa.gov, cross-check
     against Wikipedia, and upsert each district's incumbent.
  2. `--add-candidate ...` adds a non-incumbent candidate (past loser, primary
     challenger, etc.) — anyone whose contributions we want to track but who
     isn't currently sitting on council.

Naming note:
  The table is called `council_members` for historical reasons; it really
  tracks any candidate the project follows. The `is_incumbent` flag (1 = on
  council today, 0 = not) is the discriminator. Rather than rename the table
  and churn fetch_data.py / generate_profile_data.py / build_identities.py,
  the misnomer is documented here and the column is the source of truth.

Idempotent: re-running updates names/districts/source_url + last_updated.

Usage:
    # refresh sitting council from sa.gov
    python fetch_roster.py
    python fetch_roster.py --dry-run

    # add a non-incumbent (e.g. a past candidate)
    python fetch_roster.py --add-candidate \\
        --slug shaikh --first Sakib --last Shaikh \\
        --office-sought "Council District 8" \\
        --notes "Lost 2025 D8 general election to Ivalis Meza Gonzalez"

Notes:
- sa.gov pages are JS-light enough to parse from the static HTML.
- Wikipedia is the cross-check; if the two disagree on a district, we keep
  sa.gov as authoritative and log the disagreement.
- The `filer_first_name` / `filer_last_name` columns are what the campfinsearch
  scraper will use; they default to a parse of the display name and can be
  hand-edited per row (UPDATE ... WHERE slug=...) when the official portal
  uses a different form (e.g. "Ricardo" vs "Ric").
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "san_antonio_finance.db"

SAGOV_COUNCIL_URL = "https://www.sa.gov/Directory/Departments/Mayor-Council/City-Council"
WIKIPEDIA_URL     = "https://en.wikipedia.org/wiki/San_Antonio_City_Council"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Districts we expect to find. Mayor uses district label "Mayor" (no number).
EXPECTED_DISTRICTS = ["Mayor"] + [f"District {i}" for i in range(1, 11)]


@dataclass
class Member:
    district: str            # "Mayor" or "District 1".."District 10"
    full_name: str           # display name as published
    source_url: str
    photo_url: str = ""

    @property
    def slug(self) -> str:
        # last name lowercased, alnum-only; "McKee-Rodriguez" -> "mckeerodriguez"
        # If you want a different slug (e.g. multi-part surname disambiguation),
        # you can UPDATE the row after the script runs.
        last = self.full_name.split()[-1]
        return re.sub(r"[^a-z0-9]", "", last.lower())

    @property
    def first(self) -> str:
        return self.full_name.split()[0]

    @property
    def last(self) -> str:
        return self.full_name.split()[-1]


# ── HTTP ────────────────────────────────────────────────────────────────────
# sa.gov rejects bare urllib AND python-requests clients (403) — likely TLS
# fingerprinting via a CDN/WAF. curl works with browser-style headers, so we
# shell out to curl. Wikipedia is permissive and works with either, but using
# curl uniformly keeps the fetch path simple.
def http_get(url: str, timeout: int = 30) -> str:
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise RuntimeError(
            "curl not found on PATH; install curl (Win10+ ships with it at "
            "C:\\Windows\\System32\\curl.exe) or run from Git Bash."
        )
    cmd = [
        curl, "-sSL", "--compressed", "--max-time", str(timeout),
        "-A", USER_AGENT,
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-H", "Upgrade-Insecure-Requests: 1",
        "-H", "Sec-Fetch-Dest: document",
        "-H", "Sec-Fetch-Mode: navigate",
        "-H", "Sec-Fetch-Site: none",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    if proc.returncode != 0:
        raise RuntimeError(f"curl failed (exit {proc.returncode}): {proc.stderr.decode('utf-8', 'replace')[:500]}")
    return proc.stdout.decode("utf-8", errors="replace")


# ── sa.gov scrape ──────────────────────────────────────────────────────────
# Two parsing strategies; we accept whichever finds the most distinct
# districts, and we cross-check that the strategies agree.
#
# Strategy A — the "Learn more about District N's councilmember, NAME" body
# copy that appears on the council landing page.
SAGOV_BODY_RE = re.compile(
    r"District\s+(\d{1,2})'s\s+councilmember,\s+"
    r"([^.<]+?)\.",
    re.IGNORECASE,
)

# Strategy B — the navigation menu: each district has a Biography sub-link
# whose anchor text is the member's name.
SAGOV_NAV_RE = re.compile(
    r'href="https://www\.sa\.gov/Directory/Departments/Mayor-Council/City-Council/D(\d{1,2})/Biography"\s*>'
    r'([A-Z][A-Za-z\'\.\- ]+?)<',
    re.IGNORECASE,
)


def parse_sagov_council(html: str) -> list[Member]:
    """Returns one Member per district. Combines both strategies and warns on
    disagreement.
    """
    body: dict[str, str] = {}
    for m in SAGOV_BODY_RE.finditer(html):
        d = f"District {int(m.group(1))}"
        name = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(".")
        body.setdefault(d, name)

    nav: dict[str, str] = {}
    for m in SAGOV_NAV_RE.finditer(html):
        d = f"District {int(m.group(1))}"
        name = re.sub(r"\s+", " ", m.group(2)).strip()
        nav.setdefault(d, name)

    members: list[Member] = []
    for d in [f"District {i}" for i in range(1, 11)]:
        b = body.get(d)
        n = nav.get(d)
        if b and n and b.lower() != n.lower():
            print(f"[roster] WARN: sa.gov body/nav disagreement for {d}: body={b!r} nav={n!r}; using body")
        chosen = b or n
        if chosen:
            members.append(Member(district=d, full_name=chosen, source_url=SAGOV_COUNCIL_URL))
    return members


def parse_sagov_mayor(html: str) -> Member | None:
    """The mayor's name is in the Council page's left-nav, under
    .../Mayor-Council/Mayor/Biography. We grab the anchor text."""
    m = re.search(
        r'href="https://www\.sa\.gov/Directory/Departments/Mayor-Council/Mayor/Biography"\s*[^>]*>'
        r'([A-Z][A-Za-z\'\.\- ]+?)<',
        html, re.IGNORECASE,
    )
    if not m:
        return None
    name = re.sub(r"\s+", " ", m.group(1)).strip()
    if " " not in name:
        return None
    return Member(district="Mayor", full_name=name, source_url=SAGOV_COUNCIL_URL)


# ── Wikipedia cross-check ─────────────────────────────────────────────────
WIKI_ROW_RE = re.compile(
    r"<tr>\s*<td>\s*(\d{1,2})\s*</td>\s*<td>\s*([^\n<]+?)\s*\n",
    re.IGNORECASE,
)
WIKI_MAYOR_RE = re.compile(
    r'<a[^>]*href="/wiki/Gina_Ortiz_Jones"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)


def parse_wikipedia(html: str) -> dict[str, str]:
    """Return {district_label -> full_name}. Wikipedia formats the council
    table as <tr><td>N</td>\n<td>NAME\n</td>...; a separate hard-coded match
    handles the Mayor row in the infobox."""
    out: dict[str, str] = {}
    for m in WIKI_ROW_RE.finditer(html):
        n = int(m.group(1))
        if 1 <= n <= 10:
            name = re.sub(r"\s+", " ", m.group(2)).strip()
            out[f"District {n}"] = name
    m = WIKI_MAYOR_RE.search(html)
    if m:
        out["Mayor"] = re.sub(r"\s+", " ", m.group(1)).strip()
    return out


def _norm(s: str) -> str:
    """Lowercase, strip accents, drop non-alpha — for fuzzy comparison only."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", s.lower())


# ── DB ─────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS council_members (
    slug              TEXT PRIMARY KEY,
    district          TEXT NOT NULL,           -- 'Mayor', 'District 1'..'District 10', or '' for non-district candidates
    full_name         TEXT NOT NULL,
    filer_first_name  TEXT NOT NULL,           -- for campfinsearch scraping
    filer_last_name   TEXT NOT NULL,
    source_url        TEXT,
    wikipedia_match   INTEGER DEFAULT 0,       -- 1 if Wikipedia agreed on the (district,name)
    photo_url         TEXT,
    is_incumbent      INTEGER NOT NULL DEFAULT 1,  -- 1 = currently on council, 0 = past/challenger
    office_sought     TEXT,                    -- e.g. 'Council District 8' (for non-incumbents)
    notes             TEXT,                    -- free-text context (election outcome, etc.)
    last_updated      TEXT NOT NULL
);
"""

# Columns added after the original schema was defined; ALTER guarded so
# pre-existing DBs upgrade in place.
LATE_ADDED_COLUMNS = [
    ("is_incumbent",  "INTEGER NOT NULL DEFAULT 1"),
    ("office_sought", "TEXT"),
    ("notes",         "TEXT"),
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Backfill any newly-added columns onto pre-existing DBs.
    cur = conn.cursor()
    existing = {row[1] for row in cur.execute("PRAGMA table_info(council_members)").fetchall()}
    for col, ddl in LATE_ADDED_COLUMNS:
        if col not in existing:
            cur.execute(f"ALTER TABLE council_members ADD COLUMN {col} {ddl}")
    # The old schema had a UNIQUE index on (district). That breaks for
    # non-incumbents who share a district (e.g. Sakib + Mungia both in
    # 'Council District 8'). Drop it if present; uniqueness lives on slug.
    cur.execute("DROP INDEX IF EXISTS idx_council_district")
    conn.commit()


def upsert_member(conn: sqlite3.Connection, m: Member, wikipedia_match: bool) -> None:
    conn.execute(
        """
        INSERT INTO council_members
            (slug, district, full_name, filer_first_name, filer_last_name,
             source_url, wikipedia_match, photo_url, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            district = excluded.district,
            full_name = excluded.full_name,
            filer_first_name = excluded.filer_first_name,
            filer_last_name = excluded.filer_last_name,
            source_url = excluded.source_url,
            wikipedia_match = excluded.wikipedia_match,
            photo_url = excluded.photo_url,
            last_updated = excluded.last_updated
        """,
        (
            m.slug, m.district, m.full_name, m.first, m.last,
            m.source_url, 1 if wikipedia_match else 0, m.photo_url,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


# ── Main ───────────────────────────────────────────────────────────────────
def add_candidate(
    conn: sqlite3.Connection,
    slug: str,
    first: str,
    last: str,
    full_name: str,
    office_sought: str,
    notes: str,
    source_url: str,
) -> None:
    """Insert/upsert a non-incumbent candidate (is_incumbent=0)."""
    conn.execute(
        """
        INSERT INTO council_members
            (slug, district, full_name, filer_first_name, filer_last_name,
             source_url, wikipedia_match, photo_url,
             is_incumbent, office_sought, notes, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, 0, '', 0, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            full_name = excluded.full_name,
            filer_first_name = excluded.filer_first_name,
            filer_last_name = excluded.filer_last_name,
            source_url = excluded.source_url,
            office_sought = excluded.office_sought,
            notes = excluded.notes,
            is_incumbent = 0,
            last_updated = excluded.last_updated
        """,
        (
            slug, office_sought or "", full_name, first, last,
            source_url, office_sought or "", notes or "",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Maintain SA candidate roster.")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path")
    p.add_argument("--dry-run", action="store_true", help="Print discovered roster but do not write to DB")
    # Non-incumbent candidate insertion
    p.add_argument("--add-candidate", action="store_true",
                   help="Add a non-incumbent (past/challenger) candidate. "
                        "Requires --slug, --first, --last, --office-sought.")
    p.add_argument("--slug", help="Slug for --add-candidate (lowercase alnum)")
    p.add_argument("--first", help="First name for --add-candidate")
    p.add_argument("--last", help="Last name for --add-candidate")
    p.add_argument("--office-sought", default="",
                   help="Office the non-incumbent ran for, e.g. 'Council District 8'")
    p.add_argument("--notes", default="", help="Free-text context for --add-candidate")
    p.add_argument("--source-url", default="",
                   help="Provenance URL for --add-candidate (campaign site, news article, ballotpedia)")
    args = p.parse_args()

    # ── --add-candidate path ──────────────────────────────────────────────────
    if args.add_candidate:
        for required in ("slug", "first", "last"):
            if not getattr(args, required):
                print(f"ERROR: --add-candidate requires --{required}", file=sys.stderr)
                return 2
        full_name = f"{args.first} {args.last}".strip()
        slug = re.sub(r"[^a-z0-9]", "", args.slug.lower())
        conn = sqlite3.connect(args.db)
        try:
            ensure_schema(conn)
            add_candidate(
                conn, slug, args.first, args.last, full_name,
                args.office_sought, args.notes, args.source_url,
            )
            conn.commit()
            row = conn.execute(
                "SELECT slug, full_name, office_sought, is_incumbent, notes "
                "FROM council_members WHERE slug=?", (slug,)
            ).fetchone()
            print(f"[roster] candidate upserted:")
            print(f"  slug={row[0]!r}  name={row[1]!r}  office={row[2]!r}  "
                  f"incumbent={row[3]}  notes={row[4]!r}")
        finally:
            conn.close()
        return 0


    print(f"[roster] fetching sa.gov council page: {SAGOV_COUNCIL_URL}", flush=True)
    try:
        sagov_html = http_get(SAGOV_COUNCIL_URL)
    except Exception as e:
        print(f"[roster] FATAL: sa.gov fetch failed: {e}", file=sys.stderr)
        return 2

    print(f"[roster] fetching Wikipedia cross-check: {WIKIPEDIA_URL}", flush=True)
    try:
        wiki_html = http_get(WIKIPEDIA_URL)
    except Exception as e:
        print(f"[roster] WARN: Wikipedia fetch failed (no cross-check): {e}", file=sys.stderr)
        wiki_html = ""

    sagov_members = parse_sagov_council(sagov_html)
    sagov_mayor = parse_sagov_mayor(sagov_html)
    wiki = parse_wikipedia(wiki_html) if wiki_html else {}

    # Build the unified roster, preferring sa.gov; fall back to Wikipedia for
    # any missing slot.
    by_district: dict[str, Member] = {}
    if sagov_mayor:
        by_district["Mayor"] = sagov_mayor
    for m in sagov_members:
        by_district[m.district] = m

    for d in EXPECTED_DISTRICTS:
        if d in by_district:
            continue
        if d in wiki:
            by_district[d] = Member(district=d, full_name=wiki[d], source_url=WIKIPEDIA_URL)
            print(f"[roster] WARN: filled {d} from Wikipedia (sa.gov did not yield a name)")

    # Cross-check (accent-folded last-name compare)
    missing = [d for d in EXPECTED_DISTRICTS if d not in by_district]
    disagreements = []
    for d, m in by_district.items():
        if d in wiki and _norm(m.last) != _norm(wiki[d].split()[-1]):
            disagreements.append((d, m.full_name, wiki[d]))

    print()
    print("--- Roster -------------------------------")
    print(f"{'District':14} {'Name':30} {'WP-ok':6} Source")
    print("-" * 80)
    for d in EXPECTED_DISTRICTS:
        m = by_district.get(d)
        if not m:
            print(f"{d:14} {'<missing>':30}")
            continue
        wp_ok = (d in wiki and _norm(m.last) == _norm(wiki[d].split()[-1]))
        flag = "yes" if wp_ok else ("no" if d in wiki else "n/a")
        src = m.source_url.split("//")[-1][:40]
        print(f"{d:14} {m.full_name:30} {flag:6} {src}")
    print()
    if missing:
        print(f"[roster] WARN: {len(missing)} district(s) missing: {missing}")
    if disagreements:
        print(f"[roster] WARN: {len(disagreements)} sa.gov/Wikipedia name mismatches:")
        for d, sa, wp in disagreements:
            print(f"  {d}: sa.gov={sa!r} vs wikipedia={wp!r}")
    print()

    if args.dry_run:
        print("[roster] --dry-run: no DB writes")
        return 0

    db_path = args.db
    print(f"[roster] writing DB: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        for d in EXPECTED_DISTRICTS:
            m = by_district.get(d)
            if not m:
                continue
            wp_ok = (d in wiki and _norm(m.last) == _norm(wiki[d].split()[-1]))
            upsert_member(conn, m, wp_ok)
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM council_members").fetchone()[0]
        print(f"[roster] done. {n} council_members rows in DB.")
    finally:
        conn.close()

    if missing:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
