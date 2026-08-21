# Whyte (District 10) — council conveyor, member 11 of 11

Conveyor: `ADD_COUNCIL_MEMBER.md` (the current template; `KAUR_PLAN.md` is a
historical record only). This doc records member-specific facts and deltas.

## Member facts (§1)

- Slug `whyte`; roster `full_name` "Marc Whyte",
  `filer_first_name` "Marc", `filer_last_name` "Whyte" (already present,
  `is_incumbent=1`). Portal filer form to be probed with
  `--no-details --dry-run` before the real ingest (§3) — watch for a
  `Marcus`-style legal-name trap (Ric/Ricardo precedent).
- District 10 (Northeast Side). Succeeds Clayton Perry, who did not seek
  re-election.
- **Election history** (KENS5 + TPR + San Antonio Report + KSAT +
  Bexar County summary results):
  - **May 6, 2023 general** — won the open seat **outright, no runoff**
    (rare for an open seat), 11,101 votes (57.84%) over a seven-way field:
    Joel Solis 2,446 (12.75%), Robert Flores 1,619 (8.44%), Bryan R.
    Martin 1,347 (7.02%), Madison Gutierrez 1,159 (6.04%), Margaret
    Sherwood 850 (4.43%), Rick Otley 669 (3.49%).
    (KENS5 2023-05-06; TPR 2023-05-06 "lopsided"; Bexar May 2023 summary.)
  - **May 3, 2025 general** — re-elected **outright, 69.13%**, over four
    challengers; closest was Roy Anthony II at 12.4% (also Eric Litaker,
    Clint Norton, Mark O'Donnell). (KSAT 2025-05-01 results page;
    San Antonio Report; Community Impact 2025-05-04.)
- **Term structure / cycle tabs: two-tab 2023 class**, same shape as
  Gavito and Kaur (not the 2021 three-tab members):
  - `2023 Run` — `end_date 2023-06-30`
  - `2025 Re-election` — `2023-07-01` → `2025-06-30`
  Prop F (Nov 2024) put the 2025 win on a 4-year term; money after
  2025-06-30 appears only in the all-time default view, as intended.
  His 2018 run was a **Texas House (HD-121) Republican primary** loss
  (Straus's open seat) — a state race filed with the TEC, not the city
  portal; out of scope for the city ETL (same shape as Spears's 2022
  county race).
- **Neutral finance-lane bio** (for the scrub prompt and intro): business
  attorney in San Antonio; before election served on city boards
  including the Zoning Commission and Ethics Review Board. Ran in the
  2018 Republican primary for Texas House District 121 (unsuccessful).
  Self-described "common-sense conservative"; 2023 campaign backed by
  the San Antonio Police Officers Association, the Republican Party of
  Bexar County, and eight former D10 councilmen (several of whom donated).
  Was the top fundraiser among 2023 city council candidates (only
  Nirenberg raised more citywide). Campaign themes: small business,
  lower taxes, public safety, streets/infrastructure. D10 is the
  council's most conservative-leaning district.
- **Contribution limits** for the methodology block: $500 per person per
  cycle (council). General and runoff are separate elections, but
  **neither of his races went to a runoff**, so per-cycle donor totals
  above $500 are flags here (across-cycle totals of $1,000 spanning 2023
  and 2025 are legitimate).
- **D19 watch:** a GOP activist with a fundraising network — likely made
  contributions to other candidates that the portal search will sweep in.
  Register `RECIPIENT_ALIASES['whyte']` once the ETL lands; watch for
  by-year bars predating 2022 (his D10 filing period).

## Results log

- **ETL (§3):** portal probe confirmed `Marc` + `Whyte` is the correct
  filer form (no name trap). 2,055 display rows (incl. the fake
  name-ordered page 1; 1,555 true grid rows) → **1,552 stored**; stored
  total **$1,048,960.80 vs portal Grand Total $1,049,460.80 — $500 gap,
  fully explained** (below). Breakdown: contributions **$487,988.23 /
  1,224 rows**, expenditures $510,972.57 / 297 rows, 24 report rows at
  $0, 7 unmapped rows $50,000 (incl. a `Loans` row — check §10 intro
  disclosure). Detail harvest complete for all 1,524 detail-linked rows
  (chunked foreground `--max-details 400` passes, per Spears ops note).
  - **$500 gap (new shape — same-report suffix collision):** the Jan 15
    2026 semi-annual (rpt0000003492) lists Christian Hummel **Sr** and
    Christian Hummel **Jr** (same address), $500 each on 8/1/2025. The
    portal grid drops the suffix, so both render identically and
    `row_hash` collapses them to one row. Verified against the report
    PDF. Left as-is per the guide's dedup doctrine (a hand-inserted raw
    row is unprecedented); cost is $500 (0.08%) off the contribution
    total and nothing else — identity clustering would merge the two
    Christians regardless. Also two $0 Report-row collapses (harmless).
  - The pre-ingest classification scrape lives at
    `scratchpad/whyte_dupe_check.py` (session scratch, not committed).
  - **Self-funding:** one **$50,000 self-loan, 2023-02-14** (kickoff),
    portal-listed once as `Loans` (unmapped → already out of the
    contribution charts; no Spears-style double-listing). Disclose in
    the intro per convention. Remaining unmapped rows are six $0
    committee notices.
  - **D19 live:** contributions span 2 recipient strings — `Marc Whyte`
    (his campaign) plus **$100 to Melissa Cabello Havrda (2019-04-12)**,
    a gift he made that would render a phantom 2019 year-bar.
    `RECIPIENT_ALIASES['whyte'] = {'Marc Whyte'}` to be registered (§9).
- **Identities (§4):** 9,350 clusters — **8,755 reclaimed (100% of the
  prior population), 595 new**; enrichment restored for all 8,755
  carriers. 18,962 individual records, 3,731 merged identities, 4,714
  review-queue pairs.
- **TEC crosswalk (§5):** **970 SA donors matched** (up from Spears's
  893), **114 of them Whyte donors** — the largest per-member TEC count
  yet, consistent with his GOP-network fundraising; D $1,245,846 /
  R $694,257 / Other $408,018.
- **FEC enrichment (§6):** `--workers 8 --limit 650` (601 unmatched
  DB-wide, 595 his, worst rank 599) + two small retry passes.
  **100.00% dollar-weighted coverage** ($477,488.23 of $477,488.23
  identity-linked own-campaign dollars); all 810 of his donors
  processed; **511 carry an FEC partisan lean**. DB-wide tail: 5
  degenerate name forms ("D, Rick", "Griffith, JR", …) whose malformed
  FEC queries permanently 504 — none of them his.
- **Rules + applies (§7):** rules re-derived in priority order
  (`local-occupation-rules-noemp` 3,016, `local-employer` 1,487,
  `local-occupation-rules` 1,340, `fec-employer` 691,
  `fec-occupation-rules` 313, `fec-occupation-rules-noemp` 237,
  `local-employer-rules` 102, `sa-employer-rules` 46); all **10** apply
  scripts re-run via the glob (incl. the new empty whyte one).
  Restored pre-scrub: `llm-research-high` **563**, `llm-research-medium`
  **210** (Spears's 566/210 ± recluster churn). civic_affiliations 2,068.
- **Scrub prep (§8.2):** 798 donors ≥$100 to his campaign; **228
  already covered** by the ten prior members' research; **pool 570 →
  29 batches** — the biggest scrub yet (he out-raised everyone but the
  mayor). Projected $107–$131 at the $3.70–$4.50/batch band.
- **Scrub (§8.3–8.4):** user approved the projected spend before the
  driver ran. Spend **$129.20** across 29 batches (**$4.46/batch**,
  inside the band), **0 failures**, 29/29 result files, `ALL DONE`
  clean. Apply: **144 resolved, 128 left null, 270 civic_affiliations
  added** (business 107, civic 76, political 61, oil_gas 11,
  military_defense 5, pro_israel 3, labor 2, government 2,
  jewish_civic 2, aipac_direct 1). §7 re-run afterwards:
  `llm-research-high` 669, `llm-research-medium` 248,
  civic_affiliations 2,338. Spot-checks: Straus/Wentworth/Novak
  political rows carry independently verifiable citations
  (Wikipedia/Ballotpedia/firm bio); Whyte's own row cites the same
  San Antonio Report reelection piece used in §1 — clean.
- **Build (§10):** **$487,888 raised, 810 donors, 72.0%
  employer-affiliated**, 1,223 contributions, 8 firms with 3+ donors,
  17.8% real-estate money. **Two cycle tabs built**: 2023 Run $167,420 /
  393 donors / 72.4%, 2025 Re-election $216,033 / 368 donors / 73.1%
  (+0.7 pt delta). By year: 2023 $180,970 (470), 2024 $93,964 (221),
  2025 $144,569 (377), 2026 $68,385 (155) — **no phantom 2019 bar**
  (D19 alias filters the $100 Cabello Havrda gift). **Second
  Republican-leaning profile: dollar-weighted lean 40.1% Dem** (517 of
  810 matched; 301 Rep-leaning / 186 Dem-leaning / 30 mixed). Top
  donors: Jack Hebdon $3K, Paul Basaldua $3K — the $50K self-loan
  correctly absent from the charts. Rebuild byte-identical apart from
  `generated_at`.
- **Landing flip (§11):** live card $488K / 810 / 72.0%, 4 topGroups
  (Real Estate $87K, Legal $86K, Not Employed $84K, Consulting / PR
  $25K). Placeholder race string corrected `Elected June 2025` →
  `Re-elected May 2025`. D20 re-render done after the flip and repeated
  after §12's full rebuild; verified idempotent by md5.
- **Verification (§13):** landing shows **"11 of 11 profiles live ·
  $3.4M decoded"** — the section is complete. His card LIVE with photo;
  profile hero badge "SAN ANTONIO CITY COUNCIL · DISTRICT 10", cycle
  selector with exactly the two defined tabs, timeline 2023–2026, both
  sides of every tracked spectrum rendered (Pro-Israel 2 /
  Palestinian-Rights an explicit 0, Oil & Gas 14, Defense 7), 167
  business-leadership donors, 84 political-role donors (incl. Joe
  Straus, Jeff Wentworth, former D10 councilmen Clamp and Gallagher —
  consistent with the §1 endorsement record). **Zero console errors**;
  Spears's page spot-checked and unregressed ($157,046 / 318 / 72.4%).
- **Cards live after this branch: 11 of 11. The San Antonio section is
  complete.**
