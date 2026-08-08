# Runbook: shipping a merged SA branch to decodepolitics.org

Audience: a Claude agent (or human) taking a just-merged PR in
`san-antonio-finance-data` and making it live on the site. The site is served
by GitHub Pages **from the `austin-finance-data` repo only** — nothing in this
repo is live until its built `sanantonio/` folder is mirrored over there
(option B, issue #1). `austin-finance-data/sanantonio/` is generated output:
never hand-edit it; fix things here and republish.

This runbook covers only the **publish** half. For the full end-to-end process
of adding a new member — research, ETL, enrichment, scrub, code registration,
build — see `ADD_COUNCIL_MEMBER.md`, which is the current template and
supersedes `KAUR_PLAN.md`. The pipeline order in step 2 below must stay in
sync with that guide.

## Prerequisites

- The PR is **merged to master** (convention: the agent stops at the PR, the
  user merges — never self-merge).
- You are in the **main checkout** `decode-politics/san-antonio-finance-data`
  (not a worktree), with `decode-politics/austin-finance-data` as its sibling.
- The canonical `san_antonio_finance.db` lives in the main checkout and is
  gitignored — merges do NOT update it. Worktree DBs are separate copies.

## Steps

1. **Pull the merge**: `git pull origin master` in the main checkout.
2. **Sync the canonical DB.** Two options:
   - *Replay* (default): run the branch's idempotent DB scripts against the
     canonical DB in **full** pipeline order:
     `fetch_data.py --slug <x> --start-year 2016` →
     `build_identities.py` →
     `sa_tec_crosswalk.py --link-only` →
     `fec_enrich.py` →
     `sa_industry_rules.py` →
     **every** `*_research/_apply_*_results.py` (glob the dirs, do not name
     one — rules reset every non-manual resolution and the applies only fill
     NULLs, so it is rules first, then *all* applies, or the members you skip
     silently lose their industry resolutions).
     The crosswalk and `fec_enrich` steps are mandatory and were missing from
     this list until 2026-08-08; a replay without them cannot reproduce the
     PR's numbers, which quietly breaks the step-3 check below. Skipping the
     crosswalk fails **silently** — `generate_profile_data.py` guards on the
     existence of `texas_contributions_raw`, so you get empty TEC data rather
     than an error.
     Confirm the replay's printed counts match the PR's.
   - *Copy* the worktree DB over the canonical one — preferred when the branch
     spent hours of FEC quota or scrub money that replay can't cheaply
     reproduce. Only safe if the worktree DB is a superset (was copied from
     canonical at branch start and nothing else touched canonical since).
3. **Rebuild the site** from the canonical DB:
   `python build_candidate.py --slug <x>` for each affected profile — it calls
   `generate_profile_data.generate()` internally with the correct output dir,
   so that is the whole step.
   Do **not** run `python generate_profile_data.py --slug <x>`: `--candidate`
   is `required=True`, so that command (printed here until 2026-08-08) exits
   without building anything. If you ever do need it standalone, the working
   form is
   `python generate_profile_data.py --candidate <x> --slug <x> --output-dir sanantonio`
   — `--output-dir` defaults to the **repo root**, and anything written there
   is outside the `sanantonio/` subtree that `publish_site.py` mirrors, so it
   never deploys.
   Diff the rebuilt JSON against what the PR merged (only `generated_at`
   should differ). If clean, `git checkout -- sanantonio/` so the tree is
   clean — publishes must be reproducible from a sha.
4. **Dry-run**: `python publish_site.py --dry-run` — verify the file list is
   exactly what you expect (profile JSONs, pages, landing JSON, photos).
5. **Publish**: `python publish_site.py`. It mirrors `sanantonio/` into the
   Austin checkout, commits there ("Publish San Antonio section (generated
   from san-antonio-finance-data@<sha>)"), and pushes = **live**.
6. **If the push is rejected** (Austin repo moved): in the Austin checkout run
   `git pull --rebase origin master`, then `git push`. The publish commit
   touches only `sanantonio/`, so rebases over Austin-side work cleanly.
7. **Verify live** (Pages takes ~1–2 min): fetch
   `https://decodepolitics.org/sanantonio/<slug>_data.json` and check a
   number that the PR changed (e.g. employer-affiliated % or donor count),
   plus eyeball `/sanantonio/` and `/sanantonio/<slug>/`.

## Guardrails

- `publish_site.py` refuses a dirty SA tree (`--force` exists; prefer fixing).
- It touches only the `sanantonio/` subtree in the Austin repo; unrelated
  dirty files there are reported and left alone.
- Mirror semantics: files deleted from the build are deleted from deploy.
- Never commit `san_antonio_finance.db` or `.env` (FEC keys) anywhere.
- If the Austin repo also needs a non-generated change (e.g. nav links),
  that's a separate hand-authored commit/PR in `austin-finance-data` — keep
  it out of the publish commit.
