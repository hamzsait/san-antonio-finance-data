# ETL Revival Plan (`etl-revival` branch)

Phase 1 of the SA section build (issue #1; overall orientation settled with the user
2026-07-20: incumbent-profiles-first, mayor + council cards/pages mirroring the Austin
site). This phase makes the data layer trustworthy before any frontend work.

## A. Objective

Leave the repo with: a verified scraper, a normalized schema the ported Austin
generator can read, current data (through the July 15 Semi-Annual 2026) for the two
existing filers, an incremental refresher, and a documented answer to the pagination
question.

## B. Verified state (2026-07-20)

- **`fetch_data.py` still works — no Playwright port needed.** Live dry-run against
  the portal returned Galvan page 1: 500 rows, grand_total $173,615.57, pager intact.
  The July scoping session's raw-curl failures were about not replaying the full
  rendered form; the script's `harvest_form_fields` round-trip is what the WAF/event
  validation accepts. Keep the requests-based approach; revisit Playwright only if
  this breaks.
- DB has 1,420 rows: galvan (850, through Sep 2025) + shaikh (570). Roster table
  already holds all 11 incumbents with filer-name columns.

## C. Schema normalization (`sa_normalize.py`, idempotent, committed)

The May scraper stored portal-raw values. Add derived columns (raw columns are kept
untouched as provenance):

| column | from | rule |
|---|---|---|
| `amount_real` REAL | `contribution_amount` ("$1,000.00") | strip `$`/commas → REAL |
| `date_iso` TEXT | `contribution_date` ("6/30/2025 12:00:00 AM") | → `2025-06-30` |
| `txn_type` TEXT | `contribution_type` | kind → `contribution` \| `expenditure` \| `report` |

Kind mapping (all four observed values): "Monetary Political Contributions" and
"Non-Monetary (In-Kind) Political Contributions" → `contribution`; "Political
Expenditures Made From Political Contributions" → `expenditure`; "Report" (the
Candidate/Committee summary rows) → `report`. Unknown kinds → NULL + warning, never
guess. `txn_type` fixes a May design gap: the row-level Contributor/Expenditure
discriminator was parsed but never stored.

`fetch_data.py` is patched to populate all three on insert going forward;
`sa_normalize.py` backfills/repairs (safe to re-run any time — it only fills NULLs
and rows whose raw values changed).

## D. Data refresh

- Re-run galvan + shaikh with `--start-year 2016` (portal year floor; May runs used
  2018) through 2026, catching the January 15 and July 15 Semi-Annual 2026 filings.
  `row_hash` idempotency means this is append-only.
- Sanity check per filer: sum of `amount_real` where `txn_type='contribution'` vs
  the portal's on-screen Grand Total (note: Grand Total spans all txn types).
- New donors then flow through `build_identities.py` (verify it still runs; fix
  stale assumptions only as needed — deep enrichment is the mayor/council phases'
  job).

## E. `sa_append.py` (incremental refresher)

Austin's `austin_append.py` lesson (never drop/rebuild) applies, but SA's scraper is
already append-only by `row_hash`, so this is a thin roster-driven loop: for each
`council_members` row with `is_incumbent=1` (plus explicit `--slug` extras like
shaikh), run the fetch_data flow, insert, and report per-filer new-row counts and
new-donor counts. `--dry-run` supported. Reporting cadence note: SA files
semiannually + 30/8-day pre-election windows, so most runs will find nothing —
that's expected, not a failure.

## F. Pagination proof

The pager renders 500 rows/page with 10 visible page links; whether results past
~5,000 rows are reachable is UNRESOLVED (issue #1 known-unknown). Prove it with a
dry-run on a big filer (Nirenberg 2016–2026, two mayoral terms) and record the
answer here. Until proven safe, all ingest queries stay narrowed (per-filer, and
per-report-period if a filer ever approaches 5,000 rows).

**Finding (filled in during the branch):** see §H.

## G. Judgment calls

1. **Raw columns stay.** Downstream code must read `amount_real`/`date_iso`/
   `txn_type` only; raw text columns are provenance, not API.
2. **Expenditure and `report` rows stay in the table** (they're already there and
   are cheap); profile generation filters `txn_type='contribution'`. No deletes.
3. **Start-year 2016 everywhere** so veterans' history is complete from the portal
   floor; the profile layer decides what to display (all-time default + 2-year
   cycle breakouts, per user).
4. **Shaikh keeps flowing through ETL** — his profile ships later as a live-but-
   unlisted page (user decision; he is excluded from the landing/nav only).

## H. Results log

(filled in as the branch progresses)

## Post-merge DB sync

After this branch merges: in the main checkout, run `sa_normalize.py`, then the
galvan/shaikh refresh (`sa_append.py --slug galvan --slug shaikh`), and verify row
counts match the worktree DB. Same idempotent-scripts convention as Austin's
district cycle.
