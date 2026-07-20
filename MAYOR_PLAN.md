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

## C. The employer/industry gap (structural, SA-wide)

The portal grid publishes **no donor employer/occupation** (0 of 1,262 existing
contribution rows have either; Austin gets both natively from Socrata). Austin's
cards/profiles lean on industry data, so SA needs substitutes, in order:

1. **FEC crosswalk** (`fec_enrich.py`, May pipeline, keys in `.env`): match SA
   donors to federal contribution records, which do carry employer/occupation.
   Jones is the best-case filer — two congressional runs (TX-23 2018/2020) mean
   her donor base is unusually FEC-visible.
2. **Report PDFs**: the grid links digitally-generated (text-layer) report PDFs;
   Texas C/OH Schedule A includes employer/occupation fields above disclosure
   thresholds. **In-branch check:** sample 2–3 Jones PDFs to establish whether a
   PDF-side extractor is worth a later branch; record the answer in §H. Not
   built in this branch.
3. **Scrub pipeline** (phase 5): per-donor LLM research fills the rest, as it
   did for Austin.

Profile/card consequence: industry charts render from whatever enrichment
coverage exists, and the SA methodology note must state the source difference
(FEC-matched + researched vs. filer-reported in Austin).

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

## Post-merge DB sync

In the main checkout after merge: `python sa_normalize.py` → `python
sa_employer_seed.py` → `python fetch_data.py --slug jones --start-year 2016`
→ `python build_identities.py` → `python fec_enrich.py --limit 1600` (long;
FEC-quota-bound; safe to interrupt/resume) → `python sa_industry_rules.py` →
`python build_candidate.py --slug jones`. All idempotent. Verify
sanantonio/jones_data.json matches the worktree build (ignoring
generated_at) — FEC-dependent fields will match only if enrichment ran to the
same coverage; the PR notes the authoritative option of copying the worktree
DB over the canonical one instead (worktree is a strict superset here).
