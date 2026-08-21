# Castillo (District 5) — council conveyor, member 5 of 10

Same conveyor as KAUR_PLAN.md (the template); this doc records only the
member-specific facts and deltas.

- Slug `castillo`, Teri Castillo, D5 (near West Side).
- Election history (Ballotpedia/KSAT/SA-Report-verified): led a 10-candidate
  field in May 2021, won the June 5, 2021 runoff over Rudy Lopez (58%);
  re-elected May 6, 2023 outright (62%, over Rudy Lopez and Arturo
  Espinosa); re-elected May 3, 2025 outright (77%, over Pablo Arriaga III
  and Raymond Zavala). Assumed office June 15, 2021 — she is the original
  reference case for the pre-Prop-F 2-year-cycle breakout (user decision
  2026-07-20).
- Background (for the scrub prompt): housing organizer and former public
  historian/educator; came up through Historic Westside neighborhood
  organizing before winning the seat.
- CANDIDATE_CYCLES: three tabs, same mid-year boundaries as McKee/Viagran —
  2021 Run (≤2021-06-30), 2023 Re-election (2021-07-01..2023-06-30),
  2025 Re-election (2023-07-01..2025-06-30).
- Scrub: `castillo_research/` ported from mungia_research; prep globs all
  `*_research` dirs so donors already scrubbed for Jones/Kaur/McKee/Viagran/
  Mungia are skipped.
- TEC crosswalk in master: after build_identities, run
  `sa_tec_crosswalk.py --link-only` to re-link + re-aggregate.
- Delegation delta (user-requested this member): heavy pipeline stages run
  as subagent batches; conveyor steps and gates unchanged.
- Everything else: identical steps, then PR (user merges), then publish per
  PUBLISH_TO_AUSTIN.md after merge.
