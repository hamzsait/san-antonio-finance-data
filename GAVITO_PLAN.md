# Gavito (District 7) — council conveyor, member 8 of 11

Conveyor: `ADD_COUNCIL_MEMBER.md` (the current template; `KAUR_PLAN.md` is a
historical record only). This doc records member-specific facts and deltas.

## Member facts (§1)

- Slug `gavito`; roster `full_name` "Marina Alderete Gavito",
  `filer_first_name` "Marina", `filer_last_name` "Gavito".
  **Name trap to confirm at ETL:** her display surname is the compound
  "Alderete Gavito", so the portal's first+last filer filter may register her
  as `Alderete Gavito` rather than `Gavito`. Confirm against the portal before
  trusting the pull (§3), and note that her 2025 opponent Cynthia Lugo
  Alderete shares part of the surname.
- District 7 (Northwest side).
- **Election history** (Ballotpedia + TPR + San Antonio Report + KSAT):
  - May 6, 2023 general — no majority, forced a runoff.
  - **June 10, 2023 runoff** — defeated Dan Rossiter, 62.2% / 37.8%.
    Assumed office June 21, 2023.
  - **May 3, 2025** — re-elected **outright**, ~72%, over Cynthia Lugo
    Alderete (~21%) and Trinity Haddox.
- **Term structure / cycle tabs: two.** She is a 2023-class member, so she has
  one fewer tab than the 2021 class (McKee/Viagran/Castillo). Structural
  precedent is **Kaur**, the other 2023-class member — same two-tab shape and
  the same mid-year boundaries:
  - `2023 Run` — ≤ 2023-06-30
  - `2025 Re-election` — 2023-07-01 .. 2025-06-30

  Post-June-2025 money appears only in the all-time default view, as intended.
  (Difference from Kaur, immaterial to the date bounds: Kaur's 2025 win was a
  June 7 runoff, Gavito's was an outright May 3 win.)
- **Neutral finance-lane bio** (for the scrub prompt and intro): technology and
  civic-innovation background — BBA St. Mary's University, MBA DePaul;
  management roles at Rackspace and USAA; founding executive director of Tech
  Bloc; executive director of SA Digital Connects, a public-private partnership
  on the digital divide. Board service: VIA (vice chair), UTSA College of
  Engineering advisory board, Bexar County Child Welfare Board, Woodlawn Lake
  Neighborhood Association (vice president).
- **Contribution limits** for the methodology block: $500 per person per cycle
  (council). General and runoff are separate elections, so a $1,000 council
  donor total across 2023's general + runoff is legitimate, not an error — this
  applies to her 2023 cycle specifically, which went to a runoff.

## Results log

- **ETL (§3):** 1,676 portal rows → 1,672 stored; $667,660.46 vs the portal's
  $668,610.46 grand total. The $950 residual is 4 same-donor/same-date/
  same-amount gifts that `row_hash` collapses by design. Contributions
  $391,781.55 / 1,221 rows; expenditures $273,803.91 / 419 rows.
  **Required a scraper fix first — see "Pagination defect" below.**
- **Identities (§4):** 8,167 clusters — 8,072 reclaimed, 95 new; enrichment
  restored for all 8,072. (Two rebuilds: once after her ETL, once after the
  backfill re-pulls.)
- **TEC crosswalk (§5):** 816 SA donors matched, D $1,205,391 / R $600,304 /
  Other $362,752. Note the D15 caveat: the second pass reported
  `name+zip5=0, unique-name-only=22`, since `link_to_sa_donors()` only fills
  NULL FKs and never repairs stale ones.
- **FEC enrichment (§6):** 8,160 of 8,167 donors processed (7 left on
  persistent 504s). Gavito's 649 donors: **100% dollar-weighted coverage**.
- **Rules + applies (§7):** rules reset 6,642 non-manual resolutions;
  all 7 apply scripts re-run. Final: `llm-research-high` 499,
  `llm-research-medium` 186; civic_affiliations 1,798.
- **Scrub (§8):** 594 donors ≥$100; 189 already covered by prior research;
  **pool 405 → 21 batches**. Spend **$76.89** ($3.66/batch, under the
  $3.70–$4.50 guide band). 0 failures. Applied: 303 resolved, 102 left null,
  89 affiliations added (civic 44, business 28, political 17).
- **Build (§10):** $390,632 raised, 647 donors, 67.5% employer-affiliated,
  1,216 contributions, 9 firms with 3+ donors, 69% Dem FEC lean.
  (Pre-recipient-filter figures were $391,782 / 649 / 67.6%; see the
  recipient-misattribution section below.)
  `Built 2 election cycles` — matches the intended two-tab shape.
  Cycles: 2023 Run $150,717 / 398 donors; 2025 Re-election $170,914 /
  243 donors.
  Rebuild is byte-identical apart from `generated_at`.
- **Landing flip (§11):** live card $391K / 647 / 67.5%, 4 topGroups.
  The pre-existing placeholder card had `"race": "Elected June 2025"`, which is
  wrong for her — hand-corrected to `"Re-elected May 2025"` (`_update_landing.py`
  rewrites only the stats fields, never `race`).
- **Cards live after this branch:** 8 of 11. Remaining `soon`: gonzalez,
  spears, whyte.

## Pagination defect found and fixed on this branch

`fetch_data.py` treated the initial search response as the grid's page 1. It is
not: the search result is ordered by contributor name while the grid's own
paging is ordered by amount, so those 500 rows are a differently-ordered slice
that overlaps pages 2..N, and the forward-only walk (`p > current_page`) never
revisited page 1. **The true page 1 was never fetched on any multi-page filer.**

Gavito before the fix: 1,334 of 1,676 rows, $484,056.11 of $668,610.46.
The missing page also held whole transaction classes — expenditures 127 → 549,
plus `Lender`, `Candidate / Committee` and
`Treasurer for Candidate / Committee` rows.

Fix: step to the first linkable page (which makes page 1 a target), fetch the
true page 1, then resume the forward walk. Ingest is dedup-by-`row_hash`, so
the overlap with the search response costs nothing.

The bug is **data-dependent** — it depends on whether the two sort orders
happen to coincide for a given result set, which is why it survived seven
members. Contribution impact, measured by a read-only probe of all live
members:

| member | was | now | recovered |
|---|---:|---:|---:|
| mungia | $90,213.39 | $103,713.44 | +$13,500.05 (13.0%) |
| galvan | $81,108.39 | $91,926.15 | +$10,817.76 (11.9%) |
| castillo | $176,287.86 | $179,597.86 | +$3,310.00 (1.9%) |
| viagran | $231,126.00 | $231,547.00 | +$421.00 (0.2%) |
| kaur | $555,016.00 | $555,016.00 | $0 (added rows were all expenditures) |
| jones, mckeerodriguez | — | — | unaffected |

All five affected members were re-pulled on this branch. Every member now
reconciles to the portal exactly once refunds are accounted for: the residual
per-member gaps are entirely `Interest, Credits, Gains, Refunds, And
Contributions Returned To Filer` rows, which `sa_normalize` leaves unmapped and
therefore correctly excludes from contribution totals (viagran $54.56, kaur
$1,900.00, castillo $1,614.50, galvan $112.50, all matching to the cent).

## Recipient misattribution found and fixed on this branch

A portal name search returns every row the name appears on — including
contributions the member *made to other candidates*. Those rows carry the
searched member's `filer_slug`, so they were counted as money raised. Gavito
had five such rows ($1,150 to Nirenberg, Landin, Johnson and Garcia, all
pre-2023), which rendered four phantom year-bars for a candidate whose first
race was 2023.

`recipient` is the discriminator, but **not** by equality against the member's
name — Jones's own money spans `Gina Jones` (4,482 rows) and
`Gina Ortiz Jones` (3 rows / $510), so an equality test would have deleted
legitimate rows. `generate_profile_data.RECIPIENT_ALIASES` registers each
member's own campaign string(s); unregistered slugs are deliberately left
unfiltered but warn loudly.

Effect: gavito −$1,150, mckeerodriguez −$510, castillo −$425, viagran −$350
(including $275 to her sister Rebecca), kaur −$200, galvan −$179; jones and
mungia unchanged. Her timeline now runs 2023–2026.

## Known issues left alone (pre-existing, not introduced here)

- The stat-card row under the cycle selector does not follow the selected
  cycle — the hero does, the cards stay all-time. Verified identical on the
  live Castillo page, and this branch never touches `profile_template.html`.
- `fec_enrich.py` prints the full request URL on error, which embeds
  `api_key=` in cleartext, so a 504 storm writes live FEC keys into stdout.
  Keys are correctly kept out of git via `.env`; only the error output leaks.
- Six `contribution_type` values remain unmapped by `sa_normalize.py`
  (loans, credit-card expenditures, returned contributions, committee
  notices). All are correctly excluded from contribution totals, but they are
  invisible rather than explicitly categorised.
