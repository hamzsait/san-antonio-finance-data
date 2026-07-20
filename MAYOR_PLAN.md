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

(filled in as the branch progresses)
