# Viagran (District 3) — council conveyor, member 3 of 10

Same conveyor as KAUR_PLAN.md (the template); this doc records only the
member-specific facts and deltas.

- Slug `viagran`, Phyllis Viagran, D3 (South Side).
- Disambiguation: her sister Rebecca Viagran held the D3 seat 2013–2021
  (term-limited). The portal filer filter is first+last name, so
  `filer_first_name='Phyllis'` keeps Rebecca's filings out.
- Election history (Ballotpedia/KSAT/SA-Report-verified): won the
  June 5, 2021 runoff over Tomas Uresti (led the May general 22.0%–14.8%);
  re-elected May 6, 2023 outright over three challengers; re-elected
  May 3, 2025 outright (57.3%, Kendra Wilkerson second at 18.2%).
- CANDIDATE_CYCLES: three tabs, same mid-year boundaries as McKee —
  2021 Run (≤2021-06-30), 2023 Re-election (2021-07-01..2023-06-30),
  2025 Re-election (2023-07-01..2025-06-30).
- Scrub: `viagran_research/` ported from mckee_research; prep globs all
  `*_research` dirs so donors already scrubbed for Jones/Kaur/McKee are
  skipped.
- NEW this member (user-requested): TEC state-filings crosswalk port from
  the Austin repo (`texas_contributions_raw` pipeline) lands on this branch
  — profile queries already guard on table existence, so once the table is
  populated every SA member benefits at their next rebuild.
- Everything else: identical steps, then PR (user merges), then publish per
  PUBLISH_TO_AUSTIN.md after merge.
