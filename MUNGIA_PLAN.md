# Mungia (District 4) — council conveyor, member 4 of 10

Same conveyor as KAUR_PLAN.md (the template); this doc records only the
member-specific facts and deltas.

- Slug `mungia`, Edward Mungia, D4 (Southwest Side).
- Election history (KSAT/SA-Report/TPR-verified): first-time candidate,
  won the open D4 seat outright on May 3, 2025 with 56.78% (Jose Martinez
  second at 15.25%) — the only newcomer in an open seat to avoid a runoff
  that cycle. Succeeded his mentor Adriana Rocha Garcia (termed out);
  assumed office June 18, 2025.
- Background (for the scrub prompt): lifelong Southside/D4 resident, nine
  years on the D4 council office staff (intern → full-time under Rey
  Saldaña, then director of special projects under Rocha Garcia), former
  South San ISD school board trustee, former MOVE Texas board member.
- CANDIDATE_CYCLES: single-cycle first-termer, like Galvan today — the
  all-time default IS his 2025 campaign, so no cycle-tab entry is needed.
- Scrub: `mungia_research/` ported from viagran_research; prep globs all
  `*_research` dirs so donors already scrubbed for Jones/Kaur/McKee/Viagran
  are skipped.
- TEC crosswalk already in master (landed with Viagran): after
  build_identities, run `sa_tec_crosswalk.py --link-only` to link + re-aggregate
  the new donor pool against the already-ingested 1.81M-row table.
- Everything else: identical steps, then PR (user merges), then publish per
  PUBLISH_TO_AUSTIN.md after merge.
