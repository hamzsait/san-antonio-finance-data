# Mayor Plan (`mayor` branch)

Phase 2 of the SA section build (issue #1, after PR #2 `etl-revival`). The user's
requested starting vertical: Mayor **Gina Ortiz Jones** (won the June 7, 2025
runoff 54.3% over Rolando Pablos). This branch is also the **template-
modernization vehicle**: it ports Austin's current profile machinery into this
repo, and every later council profile reuses what lands here.

## A. Objective

Jones's complete portal record ingested and enriched, Austin's current profile
pipeline ported (not the May-vintage template), and her profile built at
`sanantonio/jones/` in the deploy-shaped output folder.

## B. Data work

1. `fetch_data.py --slug jones --start-year 2016` — sized in phase 1 at 5,003
   rows / 4,910 contributions / $697,369.75 (11 pages, exercises the fixed
   pager end-to-end on a real ingest).
2. `build_identities.py` rerun (stable-id reclaim from phase 1 protects the
   existing 616 identities).
3. `fec_enrich.py` for Jones's donors — see §C.

## C. Employer/occupation data (CORRECTED 2026-07-21)

**The original premise of this section was wrong.** The portal DOES publish
per-transaction donor employer and occupation — not in the result grid, but on
the schedule-detail page behind each grid row's transaction-kind link (a
`DataGrid1$_ctlN$_ctl0` postback the May scraper recorded and never followed).
The user caught this; an independent agent probe confirmed it live (exact
mechanics in its report: same `SearchResults2.aspx` postback as the pager,
grid page state stays valid across sequential detail fetches, one POST per
row, ~32 KB each). `fetch_data.py` now fetches details during ingest
(`--no-details` to skip; `details_fetched_at` marks harvested rows so appends
only pay for new rows) and fills `donor_reported_employer` /
`donor_reported_occupation` (+ out-of-state-PAC flag, and category/description
for expenditures) — the columns the May schema created and left NULL.

Resolution order becomes **local-first** (`sa_industry_rules.py` is the
driver): portal-reported employer/occupation → FEC-derived → scrub pipeline
(phase 5) for the tail. The FEC crosswalk keeps its real job — federal
partisan lean — and gap-fills donors whose filings omit employer.

Obsoleted by this correction: the planned Schedule A1 **PDF extractor branch**
(the detail pages carry the same fields, cheaper), and the methodology note's
"SA doesn't publish employers" framing (fixed). Bonus probe finding: the
results page has an **Export To Excel** POST returning the full result set in
one shot (no pagination, extra `Id`/`ReportId` columns, but no
employer/occupation) — useful later as a fast count cross-check for append
runs; not adopted in this branch since details require the paged grid anyway.

## D. Cycles (user-decided)

Default view = **all-time** contributions. Historical breakout by SA's 2-year
campaign cycles (pre-Prop-F terms; Castillo, on council since 2021, is the
reference case for later phases). For Jones: all-time default plus a "2025
Mayoral Campaign" cycle view; her contributions start 2024. Federal history
(2018/2020 TX-23) is intro-mention only — finance-lane convention, and FEC money
is a different regime from city money; no federal dollars in her charts.

## E. Template port (from the Austin repo, current versions)

- `profile_template.html` + `build_candidate.py` + `generate_profile_data.py`
  ported and adapted: SA schema reads `amount_real` / `date_iso` /
  `txn_type='contribution'` / `filer_slug` (never the raw text columns);
  identity join via `donor_id` as in Austin.
- Output goes to a local `sanantonio/` folder shaped exactly like the deploy
  target (`austin-finance-data/sanantonio/`), so dev-server paths match
  production paths. Data JSONs (`jones_data.json`, `jones_all_donations.json`)
  are tracked, same as Austin.
- The May-vintage `profile_template.html` / `profile_galvan.html` /
  `profile_shaikh.html` / old `index.html` move to `_deprecated/` (superseded;
  Galvan/Shaikh pages get rebuilt on the modern template in later phases).
- Landing page, photos, nav, and `publish_site.py` are **phase 3**
  (`frontend-hub`) — nothing publishes to decodepolitics.org from this branch.

## F. Verification

- Contribution total/count for Jones vs. the portal's on-screen numbers.
- Page renders locally (http.server) with all-time + cycle views, top donors,
  and whatever industry coverage FEC enrichment yields.
- Byte-identical rebuild convention: `generate_profile_data.py` then
  `build_candidate.py` re-run must be stable (ignoring `generated_at`).

## G. Judgment calls

1. **Neutral finance-lane bio** (Austin precedent): intro covers her path
   (Air Force intelligence officer → Air Force Under Secretary → two TX-23
   congressional runs → 2025 mayoral win), fundraising shape, and the SA
   contribution limits ($1,000/person/cycle for mayor, $500 for council —
   goes in the base SA methodology block per the user). Non-finance
   controversies omitted.
2. **No race page yet**: the 2025 mayoral was a 27-candidate field; a
   retrospective race page is a possible later branch, not this one.
3. **Loans/self-funding**: if her filings show loans (common in her federal
   runs), disclose in the intro, keep out of contribution charts — Austin
   convention.
4. **Donation-form employer data**: if FEC coverage is thin for her city-only
   donors, do NOT guess industries; render honest coverage and note it.

## H. Results log

- **Jones ingested** (2026-07-20): 4,577 unique rows → 4,485 contributions,
  $632,319, 3,038 donors, spanning 2024-11 → 2026-06. The scrape's 5,003
  display rows collapse by row_hash design (amended-report re-listings).
  Top-donor totals of $2,000–3,000 are consistent with the $1,000/election
  limit (general + runoff are separate elections).
- **Identity stability held**: 616 prior ids reused, 3,005 minted; 3,621 total.
- **Employer layer created**: `employer_identities` seeded with Austin's 4,703
  classified employers (`employer_seed.json`, taxonomy-identical), donor-level
  `resolved_*` columns added, plus Austin-parity tec_*/ip_* columns so the
  ported generator runs unmodified.
- **fec_enrich parallelized** (`--workers`, default 8): 8x throughput measured;
  effective ceiling is the FEC API key quota, ~6–11 donors/min with 2 keys.
  Top-1,600 run covers ~95% of Jones dollars.
- **PDF check (§C.2) — better than hoped**: Jones's April 2025 30-day report
  (179 pages, TEC C/OH form) is a fully digital PDF whose Schedule A1 entries
  include **filled Principal occupation + Employer for every itemized
  contribution**, cleanly text-extractable (verified with pypdf: "Executive /
  Keysight", "Not Employed / Not Employed"...). A Schedule A1 PDF extractor
  would close the employer gap for ALL donors, not just FEC-matched ones —
  strong candidate for its own branch after the frontend hub; the FEC
  crosswalk + rules built here remain the partisan-lean engine either way.
- **Template port**: the Austin template's default view is already all-time
  (`ACTIVE_CYCLE = -1`) with cycle tabs — matches the user decision verbatim.
  SA methodology block now carries the contribution limits and the
  employer-data-source difference.
- Unlisted pages (`shaikh`, later): rendered with `noindex,nofollow` and
  excluded from any landing JSON.

### Detail re-pull results (2026-07-21, after the §C correction)

- All three filers re-pulled with schedule details: **98.5% of Jones's
  contribution rows now carry filer-reported employer/occupation** (4,418 of
  4,485; galvan 838/859, shaikh 401/572 — his gap is entity donors reporting
  Union/PAC). ~5,900 detail postbacks, ~1s each, per-page commits (kill-safe;
  `details_fetched_at` makes reruns skip completed rows).
- Local-first re-resolution: **2,962 of 3,621 donors industry-resolved** (was
  761). Jones headline: employer-affiliated 23.6% → **43.7%**;
  industry-Unknown dollars 62% → **25%**; top industry Legal ($64K/146
  donors); firms panel now real institutions only (occupation-title and
  self-flag displays excluded via `-noemp` confidence tags + FIRM_NOISE list).
- `build_identities.py` gained enrichment-column preservation across rebuilds
  (its DROP TABLE was silently destroying resolved_*/fec_* data — caught when
  a rebuild wiped the FEC aggregates; they were recomputed offline from
  `fec_contributions_raw`, no API quota spent).
- Partisan-lean panel unchanged (that's FEC's job): 755 Jones donors matched,
  84.8% Dem dollar-weighted.

## Post-merge DB sync

**Copy the worktree DB over canonical** (recommended — it embodies ~5,900
detail postbacks and hours of FEC quota). The full replay alternative: `python sa_normalize.py` → `python
sa_employer_seed.py` → `python fetch_data.py --slug jones --start-year 2016`
→ `python build_identities.py` → `python fec_enrich.py --limit 1600` (long;
FEC-quota-bound; safe to interrupt/resume) → `python sa_industry_rules.py` →
`python build_candidate.py --slug jones`. All idempotent. Verify
sanantonio/jones_data.json matches the worktree build (ignoring
generated_at) — FEC-dependent fields will match only if enrichment ran to the
same coverage; the PR notes the authoritative option of copying the worktree
DB over the canonical one instead (worktree is a strict superset here).
