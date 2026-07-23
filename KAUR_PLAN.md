# Kaur (District 1) — council conveyor, member 1 of 10

First seat of the council rollout after Mayor Jones. This branch runs the full
per-member conveyor and doubles as the template plan for every later member
(swap the slug): the same steps, in the same order, produce a live profile.

## Conveyor steps

1. **ETL** — `fetch_data.py --slug kaur --start-year 2016` (detail harvest on
   by default: per-row transaction-kind postbacks fill donor occupation /
   employer / OOS-PAC flags; kill-safe, resumable via `details_fetched_at`).
   Cross-check row count against the portal's Export-To-Excel total.
2. **Identities** — `build_identities.py` (stable donor_id reclaim keeps
   existing Jones/Galvan enrichment; preservation block keeps the 19
   enrichment columns through the rebuild).
3. **Industry rules** — `sa_industry_rules.py` (local filer-reported employer
   first, then FEC-derived; re-run `jones_research/_apply_jones_results.py`
   after, since rules reset non-manual resolutions and apply only fills NULLs).
4. **FEC enrichment** — `fec_enrich.py --workers 8` for the new (unmatched)
   donors; partisan lean + employer strings. Quota-bound, resumable.
5. **Scrub** — `kaur_research/` ported from `jones_research/` (prep → Opus
   driver → apply). Pool = donors ≥ $100 to the Kaur campaign not already
   covered. Jones ran $4.23/batch of 20; Kaur's pool is far smaller.
6. **Cycle verification** — Kaur first elected June 2023 (D1 runoff), so
   CANDIDATE_CYCLES gets a 2023 run + 2025 re-elect breakout; verify against
   filing dates in the data before wiring the tabs.
7. **Profile build** — `generate_profile_data.py --slug kaur` +
   `build_candidate.py --slug kaur` (adds kaur to ROSTER), landing card flips
   live in `sanantonio/sanantonio_landing.json` (drop `soon`, add stats).
8. **PR** — plan doc + code + built site on this branch; STOP at the PR.
9. **Publish** — after merge: replay DB steps on the canonical checkout, then
   `publish_site.py` per `PUBLISH_TO_AUSTIN.md` (new runbook, this PR).

## Out of scope (tracked, not here)

- TEC state-filings crosswalk (Austin's `texas_contributions_raw` pipeline)
  is not yet ported to SA; profile queries already guard on the table's
  existence. Port planned as its own branch so every member gets it at once.
- Remaining 9 council members: same conveyor, one branch each.
