"""
fetch_data.py
San Antonio campaign finance scraper, single-filer mode.

The City of San Antonio publishes campaign finance via an ASP.NET search UI at
    https://webapp1.sanantonio.gov/campfinsearch/search.aspx
There is no bulk export and no public API. Each search-results page is, however,
a full structured grid: every contribution and every expenditure is one <tr>
with stable column ordering. So we drive the form via standard ASP.NET POSTs
(carrying __VIEWSTATE / __EVENTVALIDATION through paged postbacks), and parse
each result row directly. No PDF parsing required.

Usage:
    python fetch_data.py --slug galvan
    python fetch_data.py --filer-first Ric --filer-last Galvan
    python fetch_data.py --slug galvan --start-year 2018 --end-year 2026
    python fetch_data.py --slug galvan --dry-run        # parse, print summary, no DB writes
    python fetch_data.py --slug galvan --max-pages 1    # only first page (debugging)

Idempotency:
    The campaign_finance table has a UNIQUE row_hash column. Re-running the
    scraper for the same filer produces no duplicate rows.

Schema:
    The campaign_finance table mirrors Austin's, with the columns SA actually
    fills and the rest left for downstream enrichment scripts (build_identities,
    fec_enrich, etc.). A `source = 'sa_campfinsearch'` column tags the origin.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from sa_normalize import classify_kind, ensure_columns, parse_amount, parse_date_iso

ROOT     = Path(__file__).resolve().parent
DB_PATH  = ROOT / "san_antonio_finance.db"
SEARCH_URL  = "https://webapp1.sanantonio.gov/campfinsearch/search.aspx"
RESULTS_URL = "https://webapp1.sanantonio.gov/campfinsearch/SearchResults2.aspx"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Office dropdown values supported by the form.
OFFICES = {
    "any": " ",
    "na": "NA",
    "mayor": "CD00",
    **{f"d{i}": f"CD{i:02d}" for i in range(1, 11)},
}


# ── DB schema ──────────────────────────────────────────────────────────────
# Mirrors Austin's campaign_finance table where possible. Columns SA actually
# populates: donor, recipient, contribution_amount, contribution_date,
# donor_type, city_state_zip, contribution_year, contribution_type,
# date_reported, report_filed, view_report. The rest are placeholders for
# downstream enrichment.
CAMPAIGN_FINANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_finance (
    row_hash                  TEXT PRIMARY KEY,        -- stable natural key
    source                    TEXT NOT NULL,           -- 'sa_campfinsearch'
    donor                     TEXT,                    -- "Last, First" or org name
    recipient                 TEXT,                    -- candidate name (filer)
    contribution_amount       TEXT,                    -- raw, e.g. "$500.00"
    contribution_date         TEXT,                    -- raw mm/dd/yyyy or with time
    donor_type                TEXT,                    -- INDIVIDUAL / ENTITY (heuristic)
    city_state_zip            TEXT,                    -- as displayed on the row
    contribution_year         TEXT,                    -- yyyy parsed from contribution_date
    contribution_type         TEXT,                    -- 'Monetary Political Contributions' etc.
    date_reported             TEXT,
    report_filed              TEXT,                    -- e.g. 'July 15: Semi-Annual 2025'
    view_report               TEXT,                    -- PDF URL on webapp5.sanantonio.gov
    transaction_id            TEXT,                    -- DataGrid postback id (e.g. _ctl3)
    donor_reported_occupation TEXT,
    donor_reported_employer   TEXT,
    in_kind_description       TEXT,
    out_of_state_pac          TEXT,
    correction                TEXT,
    -- enrichment columns (populated later)
    donor_id                  TEXT,
    match_confidence          TEXT,
    is_joint                  INTEGER DEFAULT 0,
    donor_id_2                TEXT,
    balanced_amount           REAL,
    employer_id               TEXT,
    employer_match_confidence TEXT,
    employer_id_2             TEXT,
    -- provenance
    scraped_at                TEXT NOT NULL,
    filer_slug                TEXT                     -- council_members.slug if known
);
CREATE INDEX IF NOT EXISTS idx_cf_recipient   ON campaign_finance(recipient);
CREATE INDEX IF NOT EXISTS idx_cf_filer_slug  ON campaign_finance(filer_slug);
CREATE INDEX IF NOT EXISTS idx_cf_donor       ON campaign_finance(donor);
CREATE INDEX IF NOT EXISTS idx_cf_year        ON campaign_finance(contribution_year);
"""


DETAIL_COLS = [
    "expense_category TEXT",      # Schedule F: txtPoECategory
    "expense_description TEXT",   # Schedule F: txtPoEDescription
    "details_fetched_at TEXT",    # when the schedule-detail postback was harvested
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CAMPAIGN_FINANCE_SCHEMA)
    # Normalized columns (amount_real, date_iso, txn_type) — see sa_normalize.py.
    ensure_columns(conn)
    for col_def in DETAIL_COLS:
        try:
            conn.execute(f"ALTER TABLE campaign_finance ADD COLUMN {col_def}")
        except sqlite3.OperationalError:
            pass  # already exists


# ── HTTP session ───────────────────────────────────────────────────────────
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


# ── ASP.NET state extraction ───────────────────────────────────────────────
HIDDEN_RE = re.compile(
    r'<input type="hidden"[^>]*\bname="(__VIEWSTATE|__VIEWSTATEGENERATOR|__EVENTVALIDATION)"[^>]*\bvalue="([^"]*)"',
    re.IGNORECASE,
)


def extract_aspnet_state(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in HIDDEN_RE.finditer(html):
        out[m.group(1)] = m.group(2)
    missing = {"__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"} - set(out)
    if missing:
        raise RuntimeError(f"missing ASP.NET hidden fields: {missing}")
    return out


# ── Result row parsing ─────────────────────────────────────────────────────
# Each data row is:
#   <tr style="color:#000066;">
#     <td><a target=_blank href="PDF_URL">View Report</a></td>      [0]
#     <td>NAME<br><font size=1>STREET<br>CITY, ST  ZIP</font></td>   [1]
#     <td>TYPE</td>                                                  [2] Contributor / Expenditure
#     <td>REPORT_PERIOD</td>                                         [3]
#     <td align="center">$AMOUNT</td>                                [4]
#     <td><a href="javascript:__doPostBack('DataGrid1$_ctlN$_ctl0','')">KIND</a></td>  [5]
#     <td>FILER</td>                                                 [6]
#     <td>DATE_REPORTED</td>                                         [7]
#     <td>CONTRIB_DATE</td>                                          [8]
#   </tr>
DATA_ROW_RE = re.compile(
    r'<tr style="color:#000066;">\s*'
    r'<td>(?P<view>(?:<a[^>]*>View Report</a>|&nbsp;|))</td>\s*'
    r'<td>(?P<contributor>.*?)</td>\s*'
    r'<td>(?P<txntype>[^<]*)</td>\s*'
    r'<td>(?P<report>[^<]*)</td>\s*'
    r'<td align="center">(?P<amount>[^<]*)</td>\s*'
    r'<td>(?:<a[^>]*?DataGrid1\$(?P<ctl>_ctl\d+)\$_ctl0[^>]*>)?(?P<kind>[^<]*)(?:</a>)?</td>\s*'
    r'<td>(?P<filer>[^<]*)</td>\s*'
    r'<td>(?P<reported>[^<]*)</td>\s*'
    r'<td>(?P<received>[^<]*)</td>\s*</tr>',
    re.DOTALL,
)
PDF_HREF_RE = re.compile(r'href="([^"]+\.pdf)"', re.IGNORECASE)
GRAND_TOTAL_RE = re.compile(r'Grand Total:</td>\s*<td[^>]*>([^<]+)</td>', re.IGNORECASE)
# The pager is a single <tr align="left" ...> at the bottom of DataGrid1
# containing <span>NUMBER</span> for the current page and <a>NUMBER</a>
# tags for the other pages. The postback target's inner ctl number is NOT
# stable across pages (page 1's pager and page 3's pager render different
# ctlN values), so we must track display page numbers, not raw targets.
#
# Per-row transaction-detail links share the same __doPostBack syntax as the
# pager links, so we scope the match to the pager row alone.
PAGER_BLOCK_RE = re.compile(
    r'<tr align="left"[^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL,
)
PAGER_LINK_RE = re.compile(
    r"<a [^>]*?href=(?:\"|')javascript:__doPostBack\((?:'|&#39;)"
    r"(?P<target>DataGrid1\$_ctl\d+\$_ctl\d+)(?:'|&#39;)[^>]*>"
    r"\s*(?P<num>\d+|\.\.\.)\s*</a>",
    re.IGNORECASE,
)
PAGER_CURRENT_RE = re.compile(r"<span>\s*(\d+)\s*</span>", re.IGNORECASE)


@dataclass
class Row:
    view_report: str          # PDF URL or ""
    contributor_name: str     # "Last, First" or org
    contributor_addr: str     # one-line "STREET, CITY, ST ZIP"
    txn_type: str             # "Contributor" / "Expenditure"
    report_period: str
    amount_raw: str           # "$500.00"
    transaction_kind: str     # "Monetary Political Contributions" etc.
    filer: str                # "Ric Galvan"
    date_reported: str
    contribution_date: str    # "9/1/2024 12:00:00 AM"
    transaction_id: str       # "_ctlN" postback id (per-page; unstable)
    # Schedule-detail fields (fetched via the per-row __doPostBack; see
    # fetch_row_detail). Empty until a detail pass runs.
    occupation: str = ""
    employer: str = ""
    oos_pac: str = ""
    expense_category: str = ""
    expense_description: str = ""
    detail_fetched: bool = False


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_lib.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def parse_contributor_cell(cell_html: str) -> tuple[str, str]:
    """The contributor cell is 'NAME<br><font size=1>STREET<br>CITY, ST  ZIP</font>'.
    We split on <br> and join address parts on a single line."""
    parts = re.split(r"<br\s*/?>", cell_html, flags=re.IGNORECASE)
    parts = [_strip_html(p) for p in parts]
    parts = [p for p in parts if p]
    if not parts:
        return "", ""
    name = parts[0]
    addr = ", ".join(parts[1:]) if len(parts) > 1 else ""
    return name, addr


def parse_rows(html: str) -> tuple[list[Row], str | None]:
    """Returns (rows, grand_total_str)."""
    rows: list[Row] = []
    for m in DATA_ROW_RE.finditer(html):
        d = m.groupdict()
        pdf_m = PDF_HREF_RE.search(d["view"])
        view_url = pdf_m.group(1) if pdf_m else ""
        name, addr = parse_contributor_cell(d["contributor"])
        rows.append(Row(
            view_report=view_url,
            contributor_name=name,
            contributor_addr=addr,
            txn_type=_strip_html(d["txntype"]),
            report_period=_strip_html(d["report"]),
            amount_raw=_strip_html(d["amount"]),
            transaction_kind=_strip_html(d["kind"]),
            filer=_strip_html(d["filer"]),
            date_reported=_strip_html(d["reported"]),
            contribution_date=_strip_html(d["received"]),
            transaction_id=d["ctl"] or "",
        ))
    gt_m = GRAND_TOTAL_RE.search(html)
    grand_total = _strip_html(gt_m.group(1)) if gt_m else None
    return rows, grand_total


def find_pager(html: str) -> tuple[int | None, dict[int, str], str | None]:
    """Returns (current_page_number, {page_number: postback_target},
    next_window_target) for the pager at the bottom of DataGrid1.

    The DataGrid pager renders at most 10 numbered links per window plus
    '...' links for the adjacent windows. The trailing '...' (the one after
    the current page's <span>) advances to the next window — without
    following it, any result set past 10 pages / 5,000 rows silently
    truncates (proven on the Jones 2016-2026 query, 2026-07-20). A leading
    '...' points at the previous window and is ignored.
    (None, {}, None) if no pager."""
    for block in PAGER_BLOCK_RE.finditer(html):
        body = block.group(1)
        if "<span>" not in body or "doPostBack" not in body:
            continue
        cur_m = PAGER_CURRENT_RE.search(body)
        if not cur_m:
            continue
        current = int(cur_m.group(1))
        targets: dict[int, str] = {}
        next_window: str | None = None
        for m in PAGER_LINK_RE.finditer(body):
            if m.group("num") == "...":
                if m.start() > cur_m.start():
                    next_window = m.group("target")
            else:
                targets[int(m.group("num"))] = m.group("target")
        return current, targets, next_window
    return None, {}, None


# ── Search request ─────────────────────────────────────────────────────────
def initial_search(
    sess: requests.Session,
    state: dict[str, str],
    first_name: str,
    last_name: str,
    start_year: int,
    end_year: int,
    office: str = " ",
    filer_type: str = "C",
) -> requests.Response:
    """Submit the search form and return the first results page response."""
    body = {
        "__EVENTTARGET":        "",
        "__EVENTARGUMENT":      "",
        "__VIEWSTATE":          state["__VIEWSTATE"],
        "__VIEWSTATEGENERATOR": state["__VIEWSTATEGENERATOR"],
        "__EVENTVALIDATION":    state["__EVENTVALIDATION"],
        "rdoSearchType":        "1",   # 1=Exact / 2=StartsWith / 3=Contains
        "txtLName":             last_name,
        "txtFName":             first_name,
        "txtAmount":            "",
        "TranType":             "",
        "ddlReportType":        " ",
        "ddlOfficeSought":      office,
        "FilerType":            filer_type,
        "SDateYYYY":            str(start_year),
        "EDateYYYY":            str(end_year),
        "btnSearch":            "Search",
    }
    r = sess.post(
        SEARCH_URL, data=body, timeout=60,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Referer": SEARCH_URL,
                 "Origin": "https://webapp1.sanantonio.gov"},
    )
    r.raise_for_status()
    return r


def harvest_form_fields(html: str) -> dict[str, str]:
    """Extract every <input>, <select selected option>, <textarea> on the
    page so we can faithfully replay the form for a pager postback. Browsers
    submit the rendered form values; ASP.NET event validation rejects
    anything that wasn't rendered on the same page, so we MUST round-trip
    the values that came back to us."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str] = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        itype = (inp.get("type") or "text").lower()
        # Skip submit buttons unless explicitly clicked; we never want btnSearch
        # in a pager postback (it would re-execute the search).
        if itype in ("submit", "button", "image", "reset"):
            continue
        if itype in ("checkbox", "radio"):
            if not inp.has_attr("checked"):
                continue
            out[name] = inp.get("value", "on")
            continue
        out[name] = inp.get("value", "")
    for sel in soup.find_all("select"):
        name = sel.get("name")
        if not name:
            continue
        chosen = sel.find("option", selected=True)
        if chosen is not None:
            out[name] = chosen.get("value", chosen.text or "")
        else:
            first = sel.find("option")
            out[name] = first.get("value", "") if first else ""
    for ta in soup.find_all("textarea"):
        name = ta.get("name")
        if name:
            out[name] = ta.text or ""
    return out


def page_postback(
    sess: requests.Session,
    target: str,
    prior_html: str,
) -> requests.Response:
    """Postback to navigate to a specific pager target. The results page form
    action is SearchResults2.aspx (NOT search.aspx) and the form contains
    only the 5 ASP.NET hidden fields — no visible search inputs. We mirror
    that exactly: round-trip the harvested fields, override __EVENTTARGET,
    and POST to the results URL."""
    body = harvest_form_fields(prior_html)
    body["__EVENTTARGET"]   = target
    body["__EVENTARGUMENT"] = ""
    r = sess.post(
        RESULTS_URL, data=body, timeout=60,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Referer": RESULTS_URL,
                 "Origin": "https://webapp1.sanantonio.gov"},
    )
    r.raise_for_status()
    return r


# ── Schedule-detail fetch ──────────────────────────────────────────────────
# Each grid row's transaction-kind cell links a __doPostBack to the row's full
# TEC schedule entry (A1 for contributions, F for expenditures). The detail
# page carries fields the grid omits — donor occupation + employer above all
# (the May scraper never followed these links, which is why those DB columns
# sat NULL). The grid page's harvested state stays valid across sequential
# detail postbacks, so one grid page funds all of its rows' detail fetches.
DETAIL_INPUT_RE = re.compile(
    r'<input[^>]*name="(?P<name>[^"]*(?:txtOccupation|txtEmployer|txtIDNo|'
    r'txtPoECategory|txtPoEDescription))"[^>]*value="(?P<value>[^"]*)"',
    re.IGNORECASE,
)
OOS_CHECKED_RE = re.compile(r'name="[^"]*chkOutOfStatePAC"[^>]*checked', re.IGNORECASE)


def fetch_row_detail(sess: requests.Session, row: Row, grid_html: str) -> None:
    """POST the row's schedule-detail postback and fill the Row's detail
    fields in place. Reuses the grid page's harvested state (not invalidated
    by prior detail fetches — verified live 2026-07-20)."""
    target = f"DataGrid1${row.transaction_id}$_ctl0"
    r = page_postback(sess, target, grid_html)
    fields = {}
    for m in DETAIL_INPUT_RE.finditer(r.text):
        # names may be container-prefixed ("ContactCtrl11:txtOccupation")
        short = m.group("name").split(":")[-1].split("$")[-1]
        fields[short] = html_lib.unescape(m.group("value")).strip()
    row.occupation = fields.get("txtOccupation", "")
    row.employer = fields.get("txtEmployer", "")
    if OOS_CHECKED_RE.search(r.text):
        row.oos_pac = "Y" + (f" ({fields['txtIDNo']})" if fields.get("txtIDNo") else "")
    row.expense_category = fields.get("txtPoECategory", "")
    row.expense_description = fields.get("txtPoEDescription", "")
    row.detail_fetched = True


# ── Row → DB record ────────────────────────────────────────────────────────
def row_hash(row: Row, filer_slug: str) -> str:
    """Stable natural key. Excludes transaction_id (per-page postback id is
    unstable across re-runs); excludes view_report URL because the same
    transaction can appear under multiple report PDFs as filings are amended.
    """
    payload = "|".join([
        filer_slug or "",
        row.contributor_name.lower(),
        row.contributor_addr.lower(),
        row.amount_raw,
        row.transaction_kind.lower(),
        row.contribution_date,
        row.report_period.lower(),
        row.txn_type.lower(),
    ])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def parse_amount_to_year(date_str: str) -> str:
    """Pull the year out of mm/dd/yyyy [hh:mm:ss [AM/PM]]."""
    m = re.match(r"\s*\d{1,2}/\d{1,2}/(\d{4})", date_str)
    return m.group(1) if m else ""


def heuristic_donor_type(name: str) -> str:
    """SA doesn't tag donor type. Heuristic: if the contributor name has a
    comma in it (Last, First) it's an INDIVIDUAL; otherwise ENTITY."""
    return "INDIVIDUAL" if "," in name else "ENTITY"


def insert_rows(
    conn: sqlite3.Connection,
    rows: list[Row],
    filer_slug: str | None,
) -> tuple[int, int]:
    """Returns (inserted, skipped_existing)."""
    cur = conn.cursor()
    inserted = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in rows:
        rh = row_hash(r, filer_slug or "")
        existing = cur.execute(
            "SELECT 1 FROM campaign_finance WHERE row_hash=?", (rh,)
        ).fetchone()
        if existing:
            if r.detail_fetched:
                # Detail refresh on a known row — update in place, never
                # touching row_hash / donor_id / downstream enrichment.
                cur.execute(
                    """UPDATE campaign_finance SET
                           donor_reported_occupation=?, donor_reported_employer=?,
                           out_of_state_pac=?, expense_category=?,
                           expense_description=?, details_fetched_at=?
                       WHERE row_hash=?""",
                    (r.occupation or None, r.employer or None,
                     r.oos_pac or None, r.expense_category or None,
                     r.expense_description or None, now, rh),
                )
            skipped += 1
            continue
        cur.execute(
            """
            INSERT INTO campaign_finance (
                row_hash, source, donor, recipient,
                contribution_amount, contribution_date, donor_type, city_state_zip,
                contribution_year, contribution_type, date_reported, report_filed,
                view_report, transaction_id, scraped_at, filer_slug,
                amount_real, date_iso, txn_type,
                donor_reported_occupation, donor_reported_employer,
                out_of_state_pac, expense_category, expense_description,
                details_fetched_at
            ) VALUES (?, 'sa_campfinsearch', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rh,
                r.contributor_name,
                r.filer,
                r.amount_raw,
                r.contribution_date,
                heuristic_donor_type(r.contributor_name),
                r.contributor_addr,
                parse_amount_to_year(r.contribution_date),
                r.transaction_kind,
                r.date_reported,
                r.report_period,
                r.view_report,
                r.transaction_id,
                now,
                filer_slug,
                parse_amount(r.amount_raw),
                parse_date_iso(r.contribution_date),
                classify_kind(r.transaction_kind),
                r.occupation or None,
                r.employer or None,
                r.oos_pac or None,
                r.expense_category or None,
                r.expense_description or None,
                now if r.detail_fetched else None,
            ),
        )
        inserted += 1
    conn.commit()
    return inserted, skipped


# ── Main ───────────────────────────────────────────────────────────────────
def resolve_filer(conn: sqlite3.Connection, slug: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT filer_first_name, filer_last_name FROM council_members WHERE slug=?",
        (slug,),
    ).fetchone()
    if not row:
        raise SystemExit(
            f"No council_members row for slug={slug!r}. "
            f"Run fetch_roster.py first, or pass --filer-first / --filer-last."
        )
    return row[0], row[1]


def main() -> int:
    p = argparse.ArgumentParser(description="Scrape SA campfinsearch for one filer.")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--slug", help="council_members.slug (e.g. 'galvan')")
    p.add_argument("--filer-first", help="first name as registered with SA")
    p.add_argument("--filer-last",  help="last name as registered with SA")
    p.add_argument("--start-year", type=int, default=2018)
    p.add_argument("--end-year",   type=int, default=2026)
    p.add_argument("--office", default="any",
                   help="any | na | mayor | d1..d10 (leave 'any' to catch expenditures too)")
    p.add_argument("--filer-type", default="C", choices=["C", "S", "U", "All Types"])
    p.add_argument("--max-pages", type=int, default=50, help="safety cap")
    p.add_argument("--no-details", action="store_true",
                   help="Skip the per-row schedule-detail fetch (occupation/employer)")
    p.add_argument("--detail-pace", type=float, default=0.4,
                   help="Seconds between detail postbacks")
    p.add_argument("--max-details", type=int, default=0,
                   help="Debug cap on detail fetches (0 = no cap)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--save-html", action="store_true",
                   help="Save each page's raw HTML to ./_debug_pageN.html")
    args = p.parse_args()

    # Resolve filer name
    conn = sqlite3.connect(args.db)
    ensure_schema(conn)
    if args.slug:
        first, last = resolve_filer(conn, args.slug)
        slug = args.slug
    else:
        if not (args.filer_first and args.filer_last):
            print("ERROR: pass --slug or both --filer-first and --filer-last", file=sys.stderr)
            return 2
        first, last = args.filer_first, args.filer_last
        slug = re.sub(r"[^a-z0-9]", "", last.lower())

    if args.office not in OFFICES:
        print(f"ERROR: unknown --office {args.office!r}; use one of {sorted(OFFICES)}", file=sys.stderr)
        return 2
    office = OFFICES[args.office]

    print(f"[scrape] filer = {first!r} {last!r}  slug={slug}")
    print(f"[scrape] years = {args.start_year}..{args.end_year}  office={args.office} ({office!r})  filer_type={args.filer_type}")

    sess = make_session()

    # Detail-fetch bookkeeping: rows whose schedule detail we already hold
    # keep their data (appends stay cheap — only new rows cost a postback).
    details_done: set[str] = set()
    if not args.no_details and not args.dry_run:
        details_done = {r0_[0] for r0_ in conn.execute(
            "SELECT row_hash FROM campaign_finance WHERE details_fetched_at IS NOT NULL")}
    detail_count = [0]

    def run_details(page_rows: list[Row], grid_html: str) -> None:
        if args.no_details:
            return
        todo = [r_ for r_ in page_rows
                if r_.transaction_id
                and r_.txn_type.lower() in ("contributor", "expenditure")
                and row_hash(r_, slug) not in details_done]
        for r_ in todo:
            if args.max_details and detail_count[0] >= args.max_details:
                return
            try:
                fetch_row_detail(sess, r_, grid_html)
            except Exception as e:
                print(f"[scrape]   detail {r_.transaction_id} FAILED: {e}")
                continue
            details_done.add(row_hash(r_, slug))
            detail_count[0] += 1
            if detail_count[0] % 100 == 0:
                print(f"[scrape]   details fetched: {detail_count[0]:,}", flush=True)
            time.sleep(args.detail_pace)

    # 1. GET the search form to seed __VIEWSTATE et al
    print(f"[scrape] GET {SEARCH_URL}")
    r0 = sess.get(SEARCH_URL, timeout=30,
                  headers={"Sec-Fetch-Dest": "document",
                           "Sec-Fetch-Mode": "navigate",
                           "Sec-Fetch-Site": "none"})
    r0.raise_for_status()
    state = extract_aspnet_state(r0.text)
    print(f"[scrape] viewstate={len(state['__VIEWSTATE'])}b eventvalidation={len(state['__EVENTVALIDATION'])}b")

    # 2. Initial search POST
    print(f"[scrape] POST search ...")
    r1 = initial_search(sess, state, first, last, args.start_year, args.end_year, office, args.filer_type)

    if args.save_html:
        Path("_debug_page1.html").write_text(r1.text, encoding="utf-8")

    rows1, grand_total = parse_rows(r1.text)
    print(f"[scrape] page 1: {len(rows1)} rows, grand_total={grand_total!r}")
    run_details(rows1, r1.text)
    all_rows: list[Row] = list(rows1)
    ins_total = skip_total = 0
    if not args.dry_run:
        ins, skp = insert_rows(conn, rows1, slug)   # per-page commit: kill-safe
        ins_total += ins; skip_total += skp

    # 3. Pagination — walk forward through display page numbers, following
    #    the trailing '...' link into the next 10-page window when needed
    last_html = r1.text
    current_page, targets, next_window = find_pager(last_html)
    visited_pages = {current_page} if current_page else set()
    print(f"[scrape] pager: current={current_page}  links={sorted(targets)}"
          + ("  +next-window" if next_window else ""))

    # 3a. Reclaim the TRUE page 1.
    #
    # The initial search response and the paginated postback views are sorted
    # DIFFERENTLY (the search result is ordered by contributor name; the grid's
    # own paging is ordered by amount). So r1's 500 rows are not the grid's page
    # 1 — they are a differently-ordered slice that partly overlaps pages 2..N,
    # and the forward-only walk below never revisits page 1. The rows that sit
    # on the true page 1 but not in the search response are silently lost.
    #
    # Proven on Gavito 2026-08-08: 1,334 of 1,676 rows stored, $484,056.11 of
    # the portal's $668,610.46 — 338 rows and $183,604.35 (27.5%) missing.
    # Page 1 is only linkable once we are on another page, so step off to the
    # first available page and come straight back. Ingest is dedup-by-row_hash,
    # so the overlap with r1's rows costs nothing.
    if current_page == 1 and targets:
        step = min(targets)
        print(f"[scrape] reclaiming true page 1 (via page {step})")
        r_step = page_postback(sess, targets[step], last_html)
        rows_step, _ = parse_rows(r_step.text)
        run_details(rows_step, r_step.text)
        all_rows.extend(rows_step)
        if not args.dry_run:
            ins, skp = insert_rows(conn, rows_step, slug)
            ins_total += ins; skip_total += skp
        visited_pages.add(step)
        print(f"[scrape]   page {step}: {len(rows_step)} rows")

        _, t_step, _ = find_pager(r_step.text)
        if 1 in t_step:
            r_true1 = page_postback(sess, t_step[1], r_step.text)
            rows_true1, _ = parse_rows(r_true1.text)
            run_details(rows_true1, r_true1.text)
            all_rows.extend(rows_true1)
            if not args.dry_run:
                ins, skp = insert_rows(conn, rows_true1, slug)
                ins_total += ins; skip_total += skp
            print(f"[scrape]   true page 1: {len(rows_true1)} rows")
            last_html = r_true1.text
            current_page, targets, next_window = find_pager(last_html)
        else:
            print("[scrape]   WARNING: no page-1 link from page "
                  f"{step}; true page 1 not reclaimed")
            last_html = r_step.text
            current_page, targets, next_window = find_pager(last_html)

    while True:
        next_page = min(
            (p for p in targets if p not in visited_pages and p > (current_page or 0)),
            default=None,
        )
        if next_page is not None:
            target = targets[next_page]
        elif next_window:
            next_page = (current_page or 0) + 1
            target = next_window
        else:
            break
        if len(visited_pages) >= args.max_pages:
            print(f"[scrape] hit --max-pages={args.max_pages}; stopping")
            break
        print(f"[scrape] POST page {next_page} target={target}")
        rN = page_postback(sess, target, last_html)
        if args.save_html:
            Path(f"_debug_page{next_page}.html").write_text(rN.text, encoding="utf-8")
        rows_n, _ = parse_rows(rN.text)
        print(f"[scrape] page {next_page}: {len(rows_n)} rows")
        run_details(rows_n, rN.text)
        all_rows.extend(rows_n)
        if not args.dry_run:
            ins, skp = insert_rows(conn, rows_n, slug)
            ins_total += ins; skip_total += skp
        last_html = rN.text
        visited_pages.add(next_page)
        current_page, targets, next_window = find_pager(last_html)
        time.sleep(0.6)   # polite pacing

    print(f"[scrape] total rows scraped: {len(all_rows):,}  (details fetched: {detail_count[0]:,})")

    # 4. Quick sanity summary
    types = {}
    for r in all_rows:
        types[r.txn_type] = types.get(r.txn_type, 0) + 1
    print(f"[scrape] txn type breakdown: {types}")
    contrib_amount_sum = 0.0
    for r in all_rows:
        if r.txn_type.lower() == "contributor":
            try:
                contrib_amount_sum += float(re.sub(r"[^0-9.\-]", "", r.amount_raw) or 0)
            except ValueError:
                pass
    print(f"[scrape] sum of contributor amounts: ${contrib_amount_sum:,.2f}")

    if args.dry_run:
        print("[scrape] --dry-run: no DB writes")
        if all_rows:
            print("\n[scrape] sample rows (first 3):")
            for r in all_rows[:3]:
                print(f"  {r.contribution_date}  {r.amount_raw:>10}  {r.contributor_name:30}  {r.txn_type:11}  {r.report_period}")
        return 0

    print(f"[scrape] DB: inserted={ins_total}  skipped_existing={skip_total}")
    total_in_db = conn.execute(
        "SELECT COUNT(*) FROM campaign_finance WHERE filer_slug=?", (slug,)
    ).fetchone()[0]
    print(f"[scrape] total rows in DB for filer_slug={slug!r}: {total_in_db:,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
