# Spears (District 9) — council conveyor, member 10 of 11

Conveyor: `ADD_COUNCIL_MEMBER.md` (the current template; `KAUR_PLAN.md` is a
historical record only). This doc records member-specific facts and deltas.

## Member facts (§1)

- Slug `spears`; roster `full_name` "Misty Spears",
  `filer_first_name` "Misty", `filer_last_name` "Spears".
  She is styled "Misty D. Spears" in some official contexts (her council
  Facebook page); the portal filer form will be probed with
  `--no-details --dry-run` before the real ingest (§3).
- District 9 (Far North Side). Succeeds term-limited John Courage.
- **Election history** (KSAT + TPR + San Antonio Report + Community Impact +
  Bexar County official canvass):
  - **May 3, 2025 general** — led a seven-way field with 6,244 votes (38.01%),
    short of a majority: Angi Taylor Aramburu 5,845 (35.58%), April Chang
    1,484 (9.03%), Daniel Mezza 1,419 (8.64%), Emily Joy Garza 883 (5.38%),
    Tristen Hoffman 308 (1.87%), Celeste N. Tidwell 245 (1.49%).
    (KSAT 2025-05-01 results page; Bexar County May Summary Official.)
  - **June 7, 2025 runoff** — defeated Angi Taylor Aramburu,
    13,852 votes (56.74%) to 10,563 (43.26%). Assumed office June 2025.
    (KSAT 2025-06-06 results page; TPR 2025-06-07; San Antonio Report.)
- **Term structure / cycle tabs: none.** 2025-class first-termer, so the
  all-time default view *is* her campaign. Precedent: Mungia (D4) and
  Gonzalez (D8), both first elected 2025, have no `CANDIDATE_CYCLES` entry;
  the generator's `No cycle definitions found for slug 'spears'` line is the
  correct outcome. Prop F (Nov 2024) put her on a 4-year term, so the next
  cycle boundary is 2029 — nothing to define now.
  Her one prior candidacy, the 2022 Republican run for **Bexar County
  District Clerk**, was a county race that does not file with the city
  portal; no pre-2025 campaign of hers is in scope (same shape as Gonzalez's
  2022 county-judge primary).
- **Neutral finance-lane bio** (for the scrub prompt and intro): B.B.A.
  accounting, Texas Tech University. Accountant at Clear Channel
  Communications and Pioneer Drilling in San Antonio; senior/lead paralegal
  specializing in municipal law for Texas cities and government entities;
  Director of Constituent Services for Bexar County Commissioner Grant
  Moody until running for D9. Community service: precinct chair, HOA
  secretary, PTO member. Ran unsuccessfully for Bexar County District Clerk
  as a Republican in 2022. GOP-backed in the nonpartisan 2025 D9 race
  (San Antonio Report headline framing); campaign emphasized fiscal
  restraint, property-tax relief, and permitting reform. Married to Justice
  Adrian A. Spears II of the Fourth Court of Appeals.
- **Contribution limits** for the methodology block: $500 per person per
  cycle (council). General and runoff are **separate elections**, and her
  2025 race went to a June runoff, so a $1,000 donor total is legitimate
  here, not an error.
- **D19 watch:** register her recipient string(s) in `RECIPIENT_ALIASES`
  once the ETL lands; watch for by-year bars predating 2024.

## Results log

- **ETL (§3):** portal probe confirmed `Misty` + `Spears` is the correct
  filer form (no name trap). 629 true grid rows → **629 stored**; stored
  total **$320,659.10 matches the portal Grand Total to the cent**
  ($157,645.21 contributions / 445 rows + $144,896.47 expenditures / 164
  rows + $18,117.42 unmapped / 6 rows + 14 report rows at $0).
  The 6 unmapped rows are the usual `sa_normalize` classes: 3 × $0.00
  "Notice From Political Committees" and **3 "Loans" rows totaling
  $18,117.42 — all self-loans from Misty Spears, Dec 2024** (disclose in
  the intro, out of the contribution charts, per convention).
  Details harvested for all 609 eligible contribution/expenditure rows;
  441 rows carry a filer-reported employer.
  **D19 live on this member:** contributions span 3 recipient strings —
  `Misty Spears` (442 rows, $157,046.48, her own campaign), plus $500 to
  Erika Moe (2021) and $98.73 to IRNA Rudolph (2022), gifts she *made*
  that would render phantom 2021/2022 year-bars.
  `RECIPIENT_ALIASES['spears'] = {'Misty Spears'}` registered.
  (Ops note: background shells in this environment killed the long ingest
  silently; the harvest was completed with chunked foreground
  `--max-details 400` runs — per-page commits made that safe.)
- **Identities (§4):** 8,755 clusters — **8,495 reclaimed, 260 new**;
  enrichment restored for all 8,495 donors that carried it. 17,761
  individual records, 3,496 merged identities, 3,980 review-queue pairs.
- **TEC crosswalk (§5):** **893 SA donors matched** (up from Gonzalez's
  849), 58 of them Spears donors; D $1,205,791 / R $625,671 /
  Other $379,603.
- **FEC enrichment (§6):** `--workers 8 --limit 300` (267 donors were
  unmatched DB-wide, 260 of them hers, worst rank 264 — the limit covered
  her tail with margin), finished with a second `--limit 100` pass.
  **99.93% dollar-weighted coverage** ($149,982 of $150,082 identity-linked
  campaign dollars); **1 donor left in the tail**; 225 of her donors carry
  an FEC partisan lean.
- **Rules + applies (§7):** rules re-derived in priority order
  (`local-occupation-rules-noemp` 2,895, `local-employer` 1,415,
  `local-occupation-rules` 1,203, `fec-employer` 664, `fec-occupation-rules`
  291, `fec-occupation-rules-noemp` 209, `local-employer-rules` 96,
  `sa-employer-rules` 44); all **9** apply scripts re-run via the glob
  (incl. the new empty spears one). Restored: `llm-research-high` **533**,
  `llm-research-medium` **203** — at Gonzalez's magnitude (535/202; the
  ±2 drift is identity-recluster churn, nothing wiped).
  civic_affiliations 1,929.
- **Scrub prep (§8.2):** 275 donors ≥$100 to her campaign; **60 already
  covered** by the nine prior members' research; **pool 215 → 11 batches**.
  Projected driver cost at the guide's $3.70–$4.50/batch band: **$41–$50**.
- **Self-funding delta (new on this branch):** her Dec 2024 self-loans
  ($9,000 + $8,500 + $617.42 = $18,117.42) are double-listed by the portal —
  once as `Loans` rows (unmapped, excluded from charts) and once as
  `Monetary Political Contributions` rows (mapped as contributions,
  donor_id'd). Left unhandled they put $18,117.42 of loan money in her
  contribution charts and make her her own top "donor". Prior members'
  genuine small self-gifts ($179–$4,520) are counted as contributions and
  none had loan re-listings, so this is a new shape.
  **User decision (2026-08-09): leave them in** — the rows stay in her
  contribution totals/charts as filed, and she renders as her own top
  donor at $18,117.42. No exclusion code was added. The intro/methodology
  note should still disclose that the top "donor" is the candidate's own
  loan-derived self-funding, double-listed by the portal.
  Her own two scrub-pool entries (herself as donor, $18,117.42 and
  $598.73) were left in the batches as prep produced them — the
  researcher will trivially resolve the candidate herself.
- **Scrub (§8.3–8.4):** pool 215 → 11 batches. User approved the
  projected $41–$50 before the driver ran. Spend **$45.52** across 11
  batches (**$4.14/batch**, inside the guide's $3.70–$4.50 band),
  **0 failures**, 11/11 result files, `ALL DONE` clean.
  Dry run counted 157 high/medium verdicts; **40 landed** (the
  deterministic rules had already resolved the other 117 — expected),
  58 left null, **132 civic_affiliations added** (political 50,
  business 38, civic 36, oil_gas 4, government 3, military_defense 1;
  1 already present). §7 re-run afterwards: `llm-research-high` 566,
  `llm-research-medium` 210, civic_affiliations 2,061.
  Spot-checks: Stephen Raub (investmentrealty.com bio confirms TAR
  Director + ICSC membership) and Gutting/Richardson (bexargopwomen.org
  officers/committees page names both) — clean citations.
- **Build (§10):** **$157,046 raised, 318 donors, 72.4%
  employer-affiliated** (highest on the site), 442 contributions,
  5 firms with 3+ donors, 20 interest groups, 13.8% real-estate money.
  **First Republican-leaning profile: dollar-weighted lean 29.9% Dem**
  (230 of 318 donors matched; 172 Rep-leaning / 47 Dem-leaning / 11
  mixed). By year: 2024 $31,682 (53 gifts), 2025 $113,357 (361),
  2026 $12,007 (28) — no phantom 2021/2022 bars, because
  `RECIPIENT_ALIASES['spears']` filters her $598.73 of gifts to Erika
  Moe and IRNA Rudolph (D19). `No cycle definitions found for slug
  'spears'` — intended zero-tab outcome. Rebuild byte-identical apart
  from `generated_at`. Top donors: Spears herself $18,117 (the loan
  double-listing, kept per user decision), Fernando Reyes $2,500
  (Reyes Automotive Group), Jonathan Starr $2,000 (RPSA Law).
- **Landing flip (§11):** live card $157K / 318 / 72.4%, 4 topGroups
  (Not Employed $24K, Real Estate $22K, Government $21K, Legal $18K).
  The placeholder's `"race": "Elected June 2025"` was already correct.
  D20 re-render done after the flip (and repeated after §12's full
  rebuild moved shared-donor stats); verified idempotent by md5 across
  a final re-render.
- **Verification (§13):** landing shows "10 of 11 profiles live ·
  $2.9M decoded", her card LIVE with photo and four flip-side bars.
  Profile: hero badge "SAN ANTONIO CITY COUNCIL · DISTRICT 9", no cycle
  selector, timeline 2024–2026, both sides of every tracked spectrum
  rendered (Pro-Israel 2 donors / Palestinian-Rights an explicit 0,
  Oil & Gas 4, Defense 1), 5 firm rows. **Zero console errors** on her
  page; Gonzalez's page spot-checked and unregressed ($229K / 546 /
  64.2%, clean console).
- **Cards live after this branch:** 10 of 11. Remaining `soon`: whyte.
