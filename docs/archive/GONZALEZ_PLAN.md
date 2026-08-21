# Gonzalez (District 8) — council conveyor, member 9 of 11

Conveyor: `ADD_COUNCIL_MEMBER.md` (the current template; `KAUR_PLAN.md` is a
historical record only). This doc records member-specific facts and deltas.

## Member facts (§1)

- Slug `gonzalez`; roster `full_name` "Ivalis Meza Gonzalez",
  `filer_first_name` "Ivalis", `filer_last_name` "Gonzalez".
  **Name trap resolved before ingest:** her display surname is the compound
  "Meza Gonzalez", so the portal's first+last filer filter was probed both
  ways (§3, `--no-details --dry-run`). `Ivalis` + `Meza Gonzalez` returns
  **0 rows**; `Ivalis` + `Gonzalez` returns the full record. The pre-existing
  roster row was already the portal-correct form — no `UPDATE` needed.
  Note she is also styled "Ivalis Gonzalez Meza" in older coverage (the 2021
  chief-of-staff announcement), which is a third form the portal does not use.
- District 8 (Northwest side). Succeeds term-limited Manny Pelaez.
- **Election history** (Ballotpedia + San Antonio Report + TPR + KSAT +
  Community Impact):
  - **May 3, 2025 general** — led a six-way field with 4,981 votes (40.4%),
    short of a majority: Paula McGee 2,739 (22.2%), Sakib Shaikh 2,664
    (21.6%), Cesario Garcia 1,111 (9.0%), Cindy Onyekwelu 475 (3.9%),
    Rodney "Rod" Kidd 368 (3.0%).
  - **June 7, 2025 runoff** — defeated Paula McGee, 57.4% / 42.6%.
    Assumed office June 18, 2025.
  - Sakib Shaikh, third in the May general, is already on the site as an
    unlisted 2025 D8 candidate page (`UNLISTED_SLUGS`), so this branch adds
    the winner of a race the repo already covers from one side.
- **Term structure / cycle tabs: none.** She is a 2025-class first-termer, so
  the all-time default view *is* her campaign. Precedent: **Mungia** (D4, also
  first elected 2025) has no `CANDIDATE_CYCLES` entry, and the generator's
  `No cycle definitions found for slug 'gonzalez'` line is the correct
  outcome, not a warning to fix. Prop F (Nov 2024) put her on a 4-year term,
  so the next cycle boundary is 2029 — nothing to define now.
  Her one prior candidacy, the 2022 Democratic primary for Bexar County
  Judge, was a **county** race and does not file with the city portal; no
  pre-2025 campaign of hers is in scope.
- **Neutral finance-lane bio** (for the scrub prompt and intro): B.A.
  sociology, UTSA; J.D., St. Mary's University School of Law (never
  practiced). Intergovernmental and community relations for the San Antonio
  River Authority; educational programming for Spurs Sports & Entertainment;
  joined Mayor Ron Nirenberg's office in 2018 as director of policy and
  public engagement and rose to **chief of staff**, the role she held until
  running for D8. Ran third in the 2022 Democratic primary for Bexar County
  Judge. Board service: Healthy Futures of Texas, Martinez Street Women's
  Center, Mayor's Commission on the Status of Women. San Antonio Business
  Journal 40 Under 40 "2021 Woman of the Year".
- **Contribution limits** for the methodology block: $500 per person per
  cycle (council). General and runoff are **separate elections**, and her
  2025 race went to a June runoff, so a $1,000 donor total is legitimate
  here, not an error.

## Results log

- **ETL (§3):** 1,097 true grid rows → **1,088 stored**; the walk's raw sum
  **$443,186.27 matches the portal Grand Total to the cent**. Contributions
  $230,068.04 / 786 rows; expenditures $207,751.61 / 259 rows; 16 report rows;
  27 rows left unmapped by `sa_normalize` ($3,341.51 — credit-card and
  personal-funds expenditures plus $211.51 of refunds/interest), correctly
  excluded from contribution totals.
  Details harvested for 1,072 of 1,088 rows.
  The $2,025.11 gap between the grid sum and the stored sum is **9
  same-date/same-amount rows that `row_hash` collapses by design** — 7
  expenditures (Facebook ad buys ×4/×2/×2 and a $1,917.11 Prestige Printing
  re-listing), 2 zero-dollar committee/treasurer rows, and exactly **one
  contribution** (Lawrence Romo, $50, 2025-02-22, listed twice). Same shape as
  Gavito's $950 residual.
  Verified with a read-only replay probe of the grid walk, not by assertion.
- **Identities (§4):** 8,495 clusters — **8,166 reclaimed, 329 new**;
  enrichment restored for 8,166 of the 8,167 donors that carried it (one
  donor_id retired). 17,331 individual records, 3,425 merged identities,
  3,851 review-queue pairs.
- **TEC crosswalk (§5):** **849 SA donors matched** (up from Gavito's 816),
  D $1,205,641 / R $600,304 / Other $371,141. D15 caveat recurs, as expected:
  the link pass reported `name+zip5=0, unique-name-only=216`, because
  `link_to_sa_donors()` only fills NULL FKs and never repairs stale ones.
- **FEC enrichment (§6):** `--workers 8 --limit 400`. Only **336 donors were
  unmatched DB-wide and 329 of them were hers** (the eight prior branches had
  already enriched everything else), and her worst-ranked unmatched donor sat
  at global rank 332 — so a 400 limit covered her tail completely with no
  guesswork. Result: matched 215, no_history 114, errors 7.
  **Gonzalez's 546 donors: 99.8% dollar-weighted coverage**
  ($210,060 of $210,560 from identified donors); **1 donor left in the tail**.
  397 of her donors carry an FEC partisan lean.
  A follow-on FEC employer pass resolved 46 more donor_ids.
- **Rules + applies (§7):** rules re-derived in priority order
  (`local-occupation-rules-noemp` 2,826, `local-employer` 1,368,
  `local-occupation-rules` 1,154, `fec-employer` 643, `fec-occupation-rules`
  289, `fec-occupation-rules-noemp` 201, `local-employer-rules` 96,
  `sa-employer-rules` 39); all **8** apply scripts re-run via the glob,
  including the new empty `gonzalez_research` one (0 result files, handled
  gracefully). Restored: `llm-research-high` **502**,
  `llm-research-medium` **184** — at Gavito's magnitude (499/186), so nothing
  was silently wiped. civic_affiliations 1,805.
- **Scrub (§8):** 482 donors ≥$100 to her campaign; **194 already covered** by
  the eight prior members' research (the cross-dir glob paying off again);
  **pool 288 → 15 batches**. User approved the ~$55–$68 projected spend before
  the driver ran. Spend **$58.94** across 15 batches (**$3.93/batch**, inside
  the guide's $3.70–$4.50 band), **0 failures**, 15/15 result files.
  Applied: **51 resolved**, 99 left null, **115 civic_affiliations added**
  (civic 49, business 35, political 28, jewish_civic 1, oil_gas 1,
  military_defense 1). The apply's dry run counted 189 high/medium verdicts;
  only 51 landed because the deterministic rules had already resolved the
  other 138 and the apply fills NULLs only — expected, not a loss.
  §7 re-run afterwards: `llm-research-high` 535, `llm-research-medium` 202,
  civic_affiliations 1,920.
- **Build (§10):** **$229,318 raised, 546 donors, 63.4% employer-affiliated**,
  783 contributions, 10 firms with 3+ donors, 24 interest groups,
  76% Dem FEC lean, 14.3% legal money.
  By year: 2024 $67,655 (268 gifts), 2025 $147,663 (479), 2026 $14,000 (36) —
  **no phantom pre-2024 bar**, because `RECIPIENT_ALIASES['gonzalez'] =
  {'Ivalis Gonzalez'}` filters the three 2023 rows ($750) that are gifts she
  *made* to Nirenberg, Whyte and Pelaez (D19).
  `No cycle definitions found for slug 'gonzalez'` — the intended zero-tab
  outcome. Rebuild is byte-identical apart from `generated_at`.
  Top donors: Frank Burney $2,000 (Martin & Drought), Gilberto Ocanas $1,750
  (Ocanas Group), John Montford $1,500 (JTM Consulting).
- **Landing flip (§11):** live card $229K / 546 / 63.4%, 4 topGroups
  (Not Employed $34K, Legal $33K, Self-Employed $22K, Consulting/PR $19K).
  The pre-existing placeholder's `"race": "Elected June 2025"` is correct for
  her (June 7 runoff), so no hand-correction was needed — unlike Gavito.
  D20 re-render done **after** the flip, so her page ships real numbers in its
  meta description instead of the generic fallback that Castillo and Gavito
  shipped with. Re-render verified idempotent on a second run.
- **Verification (§13):** landing shows "9 of 11 profiles live · $2.7M
  decoded", her card is LIVE with photo, flip side shows four bars and
  "See More". Profile: hero badge "SAN ANTONIO CITY COUNCIL · DISTRICT 8",
  no cycle selector, timeline 2024–2026, industry funding donut, both sides of
  every tracked spectrum rendered (Pro-Israel 2 donors / Palestinian-Rights an
  explicit 0), 10 firm rows. **Zero console errors** on her page; Gavito's page
  spot-checked and unregressed (still 2 cycle tabs, clean console).
- **Cards live after this branch:** 9 of 11. Remaining `soon`: spears, whyte.

## Spot-check notes (§8.4)

Two affiliation rows were checked against their `source_url`, as the conveyor
requires:

- **Joseph Alderete** → Alamo Colleges District Board of Trustees. The cited
  trustee profile confirms both stored claims: "served on the San Antonio City
  Council for eight years, from 1977-1985" and first elected trustee June 2010.
  Clean citation.
- **Maria Luisa Cesar** → The Gas Leaks Project. The cited page (gasleaks.org)
  confirms the organization and its Rockefeller Philanthropy Advisors fiscal
  sponsorship, but **does not name her**. The person→org link is sound anyway
  because it comes from her own filer-reported schedule data
  (`donor_reported_employer` = "The Gas Leaks Project", occupation
  "Communication"); it is the *role title* ("Senior Communications Director")
  that the cited URL does not independently support. Worth knowing that a
  homepage citation can corroborate the org while leaving the role unsourced.

## Known issues left alone (pre-existing, not introduced here)

- **Near-duplicate affiliation rows survive the dedup.** Sonia Gonzalez — a
  Gonzalez donor who was also researched for Kaur and Viagran — carries two
  rows for the same body under two spellings: "South Texas Business
  Partnership (SoTx, formerly South San Antonio Chamber of Commerce)"
  (category `business`) and "South Texas Business Partnership (formerly South
  San Antonio Chamber of Commerce)" (category `civic`). `_apply_*` dedupes on
  exact `(canonical_name, organization)`, so the two spellings both insert, and
  the entry renders twice on her page. The source rows live in
  `kaur_research/kaurbatch_{09,11,25}_results.json` and
  `viagran_research/viagranbatch_01_results.json` — **committed on master, not
  produced by this branch** — so fixing it here would mean editing another
  member's research results and moving their pages. It is the only such pair in
  the 1,920-row table. A normalize-then-dedup pass on `organization` would be
  its own small branch.
- The stat-card row under the cycle selector still does not follow the selected
  cycle (carried over from Gavito's notes; not reachable on this page anyway,
  since she has no cycles).
- `fec_enrich.py` still prints the full request URL on error, embedding
  `api_key=` in cleartext in stdout. This run's log was written outside the
  repo and is not committed.
