# Frontend Hub Plan (`frontend-hub` branch)

Phase 3 of the SA section build (issue #1; after PRs #2 etl-revival and #3
mayor). This branch makes San Antonio **visible on decodepolitics.org** and is
the first branch that touches the Austin repo.

## A. Objective

`/sanantonio/` landing live with Jones's (and Galvan's) real cards + pending
cards for the other nine members, official headshots, the `publish_site.py`
deploy bridge, and a nav link from the Austin side. After this merges and
publishes, decodepolitics.org/sanantonio/ serves the hub and
/sanantonio/jones/ serves the mayor profile.

## B. Landing page (`sanantonio/index.html` + `sanantonio/sanantonio_landing.json`)

Cloned from `austin/index.html`'s data-driven pattern (flip cards, sections
from JSON, no HTML edits to add a member):

- One section — **City Hall** — seat order Mayor, District 1..10.
- Card states: `status: 'current'` with a built profile → live card (raised /
  donors / employer-affiliated + industry bars, links to `/sanantonio/<slug>/`);
  `soon: true` → non-clickable pending card ("Data coming soon") that flips
  live in the council-roster phase by a pure JSON change.
- Live at launch: **jones** (built) and **galvan** (data complete; his card can
  go live with the modern profile built here or flip in the council phase —
  judgment call §F). Pending: the other nine.
- **shaikh appears nowhere** (unlisted, user decision).
- Landing JSON lives INSIDE `sanantonio/` (`/sanantonio/sanantonio_landing.json`)
  so the publish copy carries everything the pages fetch.
- Photos: `/sanantonio/assets/photos/sa-<slug>.webp`, official city headshots
  (sourced + converted by agent; provenance in `sa_manifest.json`).

## C. `publish_site.py` (the deploy bridge — option B from issue #1)

- Copies the repo's built `sanantonio/` folder (landing, profiles, JSONs,
  assets) into a sibling checkout of `austin-finance-data` at `sanantonio/`,
  **deleting removed files** (rsync-style mirror) so the deploy target never
  drifts from the build.
- Commits there as `Publish San Antonio section (generated from
  san-antonio-finance-data@<sha>)` and pushes to master (= live on GitHub
  Pages). `--dry-run` shows the file diff; `--no-push` commits without pushing.
- Guardrails: refuses to run with a dirty SA worktree (untracked build output
  would publish silently); touches ONLY the `sanantonio/` subtree of the
  Austin repo; the Austin-side folder stays generated-never-hand-edited.

## D. Austin-side nav

One small hand-edit in the Austin repo (not generated): the Austin landing
gains a San Antonio link, and the SA landing links back. Committed directly to
Austin master alongside the first publish (precedent: the photos commit).

## E. Verification

- Local http.server: `/sanantonio/` renders cards (live + pending), photos
  load, Jones card → profile works, zero console errors.
- `publish_site.py --dry-run` file list reviewed before the real run.
- After publish: decodepolitics.org/sanantonio/ + /sanantonio/jones/ checked
  live, and the Austin landing still renders untouched.

## F. Judgment calls

1. **Galvan's card ships live from this branch** if his modern profile builds
   clean here (his data is complete; the rebuild is one command) — an
   11-card launch with 2 live beats 1. His D6 cycle labels need verification
   (he ran in 2021 too), so his profile ships with all-time view only and
   cycle tabs arrive with the council phase's per-member verification.
2. Pending cards show the member's name + seat + photo (not a blank) — the
   roster is public fact; only the money data is pending.
3. The races section of the Austin landing has no SA equivalent yet (next SA
   city election: 2027 D4/D6 specials) — omitted, not stubbed.

## G. Results log

(filled as the branch progresses)
