# Adding a San Antonio council member to decodepolitics.org

**This document is the template for every new San Antonio member profile.** It
supersedes `KAUR_PLAN.md` in that role — Kaur's plan is now a historical
record of member 1, and two of its steps are actively wrong today (see
[§18 Gotchas](#18-gotchas--traps), D1 and D2). Per-member docs
(`MCKEE_PLAN.md`, `VIAGRAN_PLAN.md`, `MUNGIA_PLAN.md`, and every future
`<SLUG>_PLAN.md`) should record **only member-specific deltas**: slug,
verified election history, cycle-tab shape, scrub-pool size, and anything
genuinely new that lands on that branch. They should point here for the
conveyor itself.

Everything below is written against the **actual code in this checkout**, not
the plan docs. Where a plan doc and the code disagree, the code wins and the
disagreement is called out in §18.

Throughout, `<slug>` is the member's `council_members.slug` — lowercase,
alphanumeric only, derived from the surname (`McKee-Rodriguez` →
`mckeerodriguez`). It is the join key for the entire pipeline
(`campaign_finance.filer_slug`, output filenames, URL path, landing card).

---

## 0. Conventions and prerequisites

- **Work in a git worktree**, one per member, branch named `<slug>`
  (precedent: `kaur`, `mckee`, `viagran`, `mungia`, `castillo`).
  The main checkout is
  `decode-politics/san-antonio-finance-data`; `decode-politics/austin-finance-data`
  must exist as its sibling (that is the only GitHub Pages source).
- **STOP AT THE PR.** The agent opens the PR and stops. The **user merges**.
  Never self-merge. Publishing (§16) happens only after the user's merge, and
  only from the main checkout.
- **The canonical DB is `san_antonio_finance.db` in the MAIN checkout only.**
  It is gitignored (`*.db` in `.gitignore`), so merges never move it. Read §17
  before you touch it. **Back it up before any ingest.**
- **Never commit** `san_antonio_finance.db`, `*.db-wal`, `*.db-shm`, or `.env`
  (`.env` holds `FEC_API_KEY_1` / `FEC_API_KEY_2`).
- `.env` must be present in the working directory for `fec_enrich.py` **and for
  `sa_industry_rules.py`** (which imports `fec_enrich` at pass 4 — see D16).
- Python deps in use: `requests`, `rapidfuzz`, `jellyfish`, `python-dotenv`.
  The scrub driver needs `node` and the `claude` CLI on PATH.
- Run every script **from the repo root** (`_update_landing.py` in particular
  uses relative paths).

**Verify before moving on:** `git worktree list` shows your new worktree;
`git branch --show-current` is `<slug>`; `.env` exists; the main-checkout DB is
backed up.

---

## 1. Establish the member's facts

Before any code runs, pin down and source these:

1. **Slug + legal filer name.** The portal's filer filter is
   **first name + last name**, so the exact registered form matters. Two live
   traps: a nickname/legal-name mismatch (`Ric` vs `Ricardo`), and a
   same-surname relative who held the same seat — Viagran's sister Rebecca
   held D3 2013–2021, and only `filer_first_name='Phyllis'` keeps her filings
   out of the pull.
2. **Election history**, cross-verified (Ballotpedia + local press: KSAT,
   San Antonio Report, TPR, Express-News). You need the date and mode of every
   win: outright vs runoff, and the month.
3. **Term structure.** SA ran 2-year terms through the May/June 2025 election;
   charter Prop F (Nov 2024) moved the city to 4-year terms after that. A
   2021-class member gets three cycle tabs; a 2025 first-termer gets none.
4. **Neutral finance-lane bio** for the scrub prompt and profile intro:
   career path, fundraising shape, no non-finance controversies
   (MAYOR_PLAN.md §G.1 precedent).
5. **Contribution limits** for the methodology block: $1,000 per person per
   cycle for mayor, $500 for council. General and runoff are **separate
   elections**, so a $1,000 council donor total is legitimate, not an error.

Write `<SLUG>_PLAN.md` now with just these deltas plus a line pointing at this
document. Fill its results log as the branch progresses.

**Verify before moving on:** every election date has a citation; you can state
the cycle-tab shape (0, 2, or 3 tabs) and justify it from filing dates you will
confirm in §5.

---

## 2. Register the filer in the roster (`council_members`)

`fetch_data.py --slug <slug>` resolves the portal search terms from
`council_members.filer_first_name` / `filer_last_name`
(`fetch_data.py:resolve_filer`, and it raises `SystemExit` if the row is
missing). `generate_profile_data.py:find_filer` reads `full_name` from the same
table.

- **Sitting incumbents** are already there: `python fetch_roster.py` scrapes
  sa.gov (Wikipedia cross-check) and upserts Mayor + District 1..10. Run
  `python fetch_roster.py --dry-run` to see the roster without writing.
- **Non-incumbents** (past candidates, challengers) need an explicit add:

```bash
python fetch_roster.py --add-candidate \
  --slug <slug> --first <First> --last <Last> \
  --office-sought "Council District N" \
  --notes "..." --source-url "..."
```

- **If the portal name differs from the display name**, hand-edit the row —
  this is the documented escape hatch (`fetch_roster.py` docstring):

```sql
UPDATE council_members SET filer_first_name='Phyllis' WHERE slug='<slug>';
```

**Verify before moving on:**
`SELECT slug, full_name, filer_first_name, filer_last_name, is_incumbent FROM council_members WHERE slug='<slug>';`
returns exactly one row with the portal-correct name form.

---

## 3. ETL — pull the portal record

```bash
python fetch_data.py --slug <slug> --start-year 2016
```

Real flags (verified in `fetch_data.py` argparse): `--db`, `--slug`,
`--filer-first`, `--filer-last`, `--start-year` (**default 2018 — you must
pass 2016**), `--end-year` (default 2026), `--office`
(`any|na|mayor|d1..d10`, default `any`), `--filer-type` (`C|S|U|All Types`,
default `C`), `--max-pages` (default 50), `--no-details`, `--detail-pace`
(default 0.4s), `--max-details` (default 0 = no cap), `--dry-run`,
`--save-html`.

Notes that matter:

- **Leave `--office` at `any`.** Narrowing it drops expenditure rows.
- **Detail harvest is ON by default.** Each grid row's transaction-kind link is
  a `DataGrid1$_ctlN$_ctl0` postback to a schedule-detail page carrying
  filer-reported **employer + occupation** (+ out-of-state-PAC flag). This is
  the single biggest lever on the profile's employer-affiliated %: Jones went
  23.6% → 43.7% when details landed. Kill-safe and resumable —
  `details_fetched_at` marks harvested rows, so a rerun pays only for new ones.
  Only pass `--no-details` for a deliberate cheap probe.
- **Ingest is append-only** by `row_hash`, so re-running is idempotent and
  amended-report re-listings collapse. Expect the stored row count to be
  **lower** than the portal's on-screen row count for that reason (Jones:
  5,003 display rows → 4,577 stored).
- **Pagination is fixed but bounded.** The DataGrid renders 500 rows/page with
  10 numbered links plus a trailing `...` next-window link; the May-vintage
  scraper only matched numeric links and silently truncated at 5,000 rows.
  `fetch_data.py` now follows the `...`, proven on Jones (11 pages, 5,003
  rows). `--max-pages 50` is still a hard stop — if a filer approaches it,
  narrow the query per report period rather than raising it blindly.
- **Veteran filers may file under a committee name.** An exact-name search for
  Nirenberg returns only ~$258K / 439 rows because his mayoral-era money lives
  under a committee filer string. For anyone with a long history, resolve the
  filer string before trusting the pull.

**Verify before moving on:** cross-check the run's contribution count and
`SUM(amount_real)` against the portal's on-screen Grand Total (note: the
portal's Grand Total spans contributions **plus** expenditures — Jones's
$1,386,125.74 total = $697,369.75 contributions + expenditures). Also
cross-check the raw row count against the results page's **Export To Excel**
POST, which returns the whole result set unpaginated. If a later refresh is all
you need, `python sa_append.py --only <slug>` (hardcodes `START_YEAR = 2016`)
does the same thing roster-driven; `--dry-run`, `--extra <slug>`, `--end-year`
also exist.

If normalized columns look wrong or NULL:
`python sa_normalize.py [--db PATH] [--dry-run]` backfills
`amount_real` / `date_iso` / `txn_type` idempotently and reports any unmapped
transaction kind loudly. Downstream code reads **only** those three derived
columns; the raw text columns are provenance.

---

## 4. Rebuild donor identities

```bash
python build_identities.py
```

**No arguments at all** — this script has no argparse (D4). The DB path is
hardcoded to `san_antonio_finance.db` next to the script, so it always hits
the DB in whatever checkout you run it from.

What it does and why you must not skip it: it blocks on (last, zip5) and
(soundex(last), zip5), scores pairs, union-finds clusters, and writes
`donor_identities` + `review_queue` + `campaign_finance.donor_id`. Two
protections are load-bearing:

- **Stable donor_id reclaim.** Each cluster reclaims the `donor_id` its member
  rows carried on the previous run (largest overlap wins, ties break on id).
  Only genuinely new clusters mint a uuid. Without this, every donor_id-keyed
  table (FEC caches, TEC links, scrub results, affiliations) is orphaned.
- **Enrichment-column preservation.** The script does `DROP TABLE
  donor_identities`, so before dropping it snapshots every column outside its
  10 base columns (`resolved_*`, `fec_*`, `tec_*`, `ip_*`) and restores them
  for surviving donor_ids. A rebuild once silently wiped hours of FEC quota
  before this existed.

Scope: only `donor_type IN ('INDIVIDUAL','Individual')`, names containing a
comma, and `txn_type='contribution'`. Expenditure payees (vendors) are
deliberately not donors.

**Verify before moving on:** the printed summary shows a plausible split of
reclaimed vs minted ids (Mungia: 220 new, 6,647 reclaimed) and
`Restored enrichment data for N donors` where N ≈ your previously enriched
population. If "reclaimed" collapses toward zero, **stop** — something broke
identity stability and you are about to orphan the whole enrichment layer.

---

## 5. TEC state-filings crosswalk — **MANDATORY**

```bash
python sa_tec_crosswalk.py --link-only
```

This step is **not optional and not out of scope** (KAUR_PLAN.md says
"Out of scope"; that is stale — the crosswalk landed in master with Viagran,
commit `5a5edb7`). The ~1.81M-row `texas_contributions_raw` table is already
ingested in the canonical DB; `--link-only` skips the 7 GB shard ingest and
runs just the two passes you need after new donor_ids appear:

1. `link_to_sa_donors()` — matches `(canonical_name, canonical_zip5)`, falling
   back to unique-name-only, and fills `austin_donor_id`
   (the column is named for template compatibility; it holds SA donor_ids).
2. `aggregate()` — resets `tec_total_dem/rep/other`, `tec_total_donations`,
   `tec_matched` to zero for **all** donors, then rewrites them from the
   linked rows using the 10 tracked committees' lean map.

Mechanics to know: `--link-only` is a raw `"--link-only" in sys.argv` check,
**not argparse** (D5) — there is no `--help`, no `--db`, and a typo'd flag is
silently ignored, which would trigger a full shard ingest attempt. Shard
location comes from `$TEC_DIR`, defaulting to a hardcoded absolute path into
the Austin checkout's `tec_data/`. Omitting `--link-only` when the shards are
absent is harmless (99 "MISSING … skip" lines) but wastes the scan.

`generate_profile_data.py` guards on the table's existence
(`sqlite_master` check at line 841), so a missing table degrades gracefully —
which is exactly why skipping this step fails **silently** with a thinner
partisan panel instead of erroring.

**Verify before moving on:** the `[aggregate]` line reports a matched-donor
count in the expected range (Mungia's run: 704 SA donors TEC-matched, 46 of
them Mungia's) with non-zero D/R/Other dollars.

---

## 6. FEC enrichment (federal partisan lean + employer strings)

```bash
python fec_enrich.py --workers 8 --limit <N>
```

Real flags: `--dry-run`, `--limit` (default `TOP_N` = **2000**), `--reset`
(re-process already-matched donors), `--workers` (default 8). There is **no
`--db` and no `--slug`** (D6).

**There is no per-member scoping.** The selection is
`SELECT ... FROM donor_identities WHERE fec_matched = 0 OR fec_matched IS NULL
ORDER BY total_donated DESC LIMIT ?` — globally top-N unmatched donors by
lifetime total. Size `--limit` so the new member's unmatched donors are
comfortably inside it; accept that you will also enrich unrelated donors.

Practical shape: 8× throughput measured over serial; the real ceiling is the
FEC key quota (~6–11 donors/min with two keys, rate-limited to 1,600 calls per
10 minutes). It is **quota-bound, interruptible, and resumable** — Mungia's run
was quota-killed at 83.1% dollar coverage with a 41-donor tail left for later,
and that is an acceptable outcome. Target dollar coverage, not donor count:
Jones's top-1,600 run covered ~95% of his dollars.

**Verify before moving on:** print dollar-weighted coverage for the new
member's donors and record it in `<SLUG>_PLAN.md`. If the run died on quota,
note the tail size — do not silently pretend it finished.

---

## 7. Industry rules, then **every** apply script

```bash
python sa_industry_rules.py            # optionally --db PATH / --dry-run
python jones_research/_apply_jones_results.py
python kaur_research/_apply_kaur_results.py
python mckee_research/_apply_mckee_results.py
python viagran_research/_apply_viagran_results.py
python mungia_research/_apply_mungia_results.py
# ... and every other <x>_research/_apply_<x>_results.py that exists
```

**Order is mandatory and the rule generalizes** (KAUR_PLAN step 3 names only
`_apply_jones_results.py`, which was correct when Jones was the only research
dir — D2):

- `sa_industry_rules.py` **resets every non-manual resolution** first:
  `UPDATE donor_identities SET resolved_* = NULL WHERE resolved_confidence IS
  NOT NULL AND resolved_confidence != 'manual'`, so it can re-derive in strict
  priority order.
- The apply scripts write `resolved_confidence = 'llm-research-high'` /
  `'llm-research-medium'` — **not** `'manual'` — so the reset wipes them.
- Apply scripts only fill NULLs
  (`WHERE donor_id=? AND resolved_industry IS NULL`), so they cannot clobber
  rules output.

Therefore: **rules first, then every apply, in any order among themselves.**
Enumerate the apply scripts with a glob rather than a hardcoded list, so the
next member's dir is picked up automatically:

```bash
for f in *_research/_apply_*_results.py; do python "$f"; done
```

Each apply supports `--dry-run` (raw `sys.argv` check, not argparse).

Resolution priority inside `sa_industry_rules.py` (first hit wins):
`local-employer` → `local-employer-rules` → `local-occupation-rules` →
`fec-employer` → `sa-employer-rules` → `fec-occupation-rules`. A `-noemp`
suffix means the display string is a bare occupation title with no real
employer; the profile's "Firms with 3+ donors" panel excludes those, because
"Attorney" is not a firm.

**Verify before moving on:** the `[rules]` per-confidence table shows
`llm-research-*` rows restored at their prior magnitude. If those rows are
missing, an apply did not run and you have just silently deleted every scrub
result on the site.

---

## 8. The scrub phase (`<prefix>_research/`)

This is the expensive, member-specific research pass: headless Opus jobs that
research each significant donor against public records and write back an
industry plus sourced civic/policy affiliations.

### 8.1 Port the directory

Copy the **most recent** member's research dir (each is a refinement of the
last: `jones_research` → `kaur_research` → `mckee_research` →
`viagran_research` → `mungia_research`) and keep only the five scripts:

```
<prefix>_research/
  _prep_<prefix>_batches.py
  _run_<prefix>_research.js
  _apply_<prefix>_results.py
  _research_instructions_v3_sa.md
  _<prefix>_usage_log.jsonl        (created by the driver)
```

Then edit:

- `_prep`: `SLUG = "<slug>"` — this **must** be the real `filer_slug`. Batch
  output filename prefix and the docstring's member description.
- `_run`: the `pendingBatches()` regex `/^<prefix>batch_\d+\.json$/`,
  `USAGE_LOG`, the error-log filename, and the **member paragraph inside
  `prompt()`** — district, seat history, role, and the reminder that
  `site_total` means dollars to *this* campaign.
- `_apply`: the `glob` pattern `<prefix>batch_*_results.json`.

**The directory prefix need not equal the slug** (D9): `mckee_research` /
`mckeebatch_*` serve slug `mckeerodriguez`. Keep the prefix short and
consistent across all three scripts.

Leave `_research_instructions_v3_sa.md` alone — it is identical across
members and carries the taxonomy, the mandatory three-search checklist, the
balanced-spectrum category set, and the output schema.

### 8.2 Prep — build the batches

```bash
python <prefix>_research/_prep_<prefix>_batches.py
```

Pool definition, straight from the SQL:

- donors with `filer_slug = '<slug>'`, `txn_type='contribution'`,
  `donor_id IS NOT NULL`, `amount_real > 0`,
- grouped by `donor_id` with `HAVING SUM(amount_real) >= 100` — i.e.
  **≥ $100 to this campaign** (the docstring's "lifetime" wording is wrong —
  D8),
- **minus every donor already covered**: the prep globs
  `../*_research/*batch_*.json` (excluding `*_results.json`) across **all**
  sibling research dirs and drops any donor_id already submitted, plus any
  donor whose `canonical_name` already has a `civic_affiliations` row.

That cross-dir glob is why later members get progressively cheaper — Mungia's
prep found 148 to scrub and skipped 54 cross-over donors already researched
for Jones/Kaur/McKee/Viagran. It also means **prep must run after
`build_identities.py`**, so donor_ids are current.

Output: `<prefix>batch_NN.json`, 20 donors per batch, each donor carrying
name, zip, `site_total`, recipients, filer-reported occupations and employer
strings, locations, first/last gift, and FEC lean/count. The SA prep's
advantage over Austin's: occupations and employers are real filer-reported
schedule data, not blanks, so researchers start with genuine identity anchors.

### 8.3 Driver — run the research

```bash
node <prefix>_research/_run_<prefix>_research.js
```

Worker pool of 4 spawning `claude -p --model claude-opus-4-8` with
`--allowedTools Read,Write,WebSearch,WebFetch,ToolSearch`,
`--output-format json`, `--max-budget-usd 25` per job, a 20-minute job
timeout, 3 tries per batch, and usage-limit-aware global backoff (probes with
sonnet, doubling pause up to an hour). Resumable by construction:
`pendingBatches()` skips any batch whose `_results.json` already exists, so
you can kill and restart it freely. Output is validated
(`goodOutput()`: JSON array, ≥ half the input donor_ids present) and a bad
file is deleted rather than kept.

**Cost signal** (from the committed `_*_usage_log.jsonl` files — real spend,
not estimates):

| member  | batches | total    | per batch of 20 |
|---------|--------:|---------:|----------------:|
| jones   |      58 | $245.56  | $4.23 |
| kaur    |      35 | $155.93  | $4.46 |
| mckee   |      26 | $99.77   | $3.84 |
| viagran |      11 | $46.30   | $4.21 |
| mungia  |       8 | $29.78   | $3.72 |

Budget **≈ $3.70–$4.50 per batch of 20**, i.e. roughly $0.19–$0.22 per donor.
Report the pool size and projected cost to the user before spending.

### 8.4 Apply

```bash
python <prefix>_research/_apply_<prefix>_results.py --dry-run   # inspect first
python <prefix>_research/_apply_<prefix>_results.py
```

Only `high` / `medium` confidence verdicts are applied; `low` stays
unclassified by design. Affiliations are deduped on
`(canonical_name, organization)` and every one requires a source URL plus a
snippet. Then **re-run the §7 sequence** (rules, then every apply) so the new
verdicts sit in the right priority order alongside the deterministic rules.

**Verify before moving on:** the apply summary reports a sane
`resolved / left null` split and an affiliation count (Mungia: 26 resolved, 65
affiliations added from 148 donors). Zero failures in the driver's `ALL DONE`
line. Spot-check two or three affiliation rows against their `source_url`.

---

## 9. Register the member in code

Four to six edits, all hand-edits to module-level literals. Copy an existing
entry exactly.

### 9.1 `build_candidate.py` → `ROSTER`

```python
ROSTER = [
    ...
    {"slug": "mungia", "display": "Edward Mungia", "district": "District 4", "race": "Elected May 2025"},
]
```

`--slug` builds fine **without** a ROSTER entry — it falls back to
`{"slug": ..., "display": slug.title(), "district": "?", "race": "?"}` (D11).
So a missing entry does not fail; it silently produces a wrong printed card and
generic OG meta. Add it.

### 9.2 `generate_profile_data.py` → `OFFICE_OVERRIDE`

```python
OFFICE_OVERRIDE = {
    ...
    'mungia': 'San Antonio City Council · District 4',
}
```

Required. The profile template's `renderHero()` overwrites the HTML badge from
`meta.office` at runtime, so a string substitution in `build_candidate.py`
would be clobbered. Without an entry you get the bare fallback
`"San Antonio City Council"` with no district.

### 9.3 `generate_profile_data.py` → `CANDIDATE_CYCLES`

Only if the member has more than one campaign in the data. A single-cycle
first-termer gets **no entry** — the all-time default view *is* their campaign
(Mungia's case; the generator prints
`No cycle definitions found for slug '<slug>' — cycles will be empty`, which is
the correct outcome, not a warning to fix).

Three-tab 2021-class shape, verbatim from Viagran:

```python
'viagran': [
    {'label': '2021 Run', 'election_year': 2021,
     'start_year': None, 'end_year': None, 'end_date': '2021-06-30'},
    {'label': '2023 Re-election', 'election_year': 2023,
     'start_year': None, 'end_year': None,
     'start_date': '2021-07-01', 'end_date': '2023-06-30'},
    {'label': '2025 Re-election', 'election_year': 2025,
     'start_year': None, 'end_year': None,
     'start_date': '2023-07-01', 'end_date': '2025-06-30'},
],
```

`start_date` / `end_date` (`YYYY-MM-DD`, compared against `date_iso`) take
precedence over `start_year` / `end_year` on their side. **Use dates, not
years.** SA elections land in May/June and the contribution cap restarts after
the runoff, so a whole-year split buckets post-runoff money into the finished
campaign. Money after the last cycle's `end_date` appears only in the all-time
default view — that is intended.

### 9.4 `sanantonio/sanantonio_landing.json` → the card

Every one of the 11 seats is already present. A pending card looks like:

```json
{
 "slug": "castillo",
 "photo": "sa-castillo",
 "name": "Teri Castillo",
 "district": "District 5",
 "race": "Elected June 2025",
 "section": "council",
 "seat": "District 5",
 "status": "current",
 "soon": true
}
```

Going live = **drop `soon`, add `href` + `raised` + `donors` + `empPct` +
`topGroups`**. Do this with the script in §11, not by hand.

### 9.5 Photo registration (usually already done)

`sanantonio/assets/photos/sa-<slug>.webp` plus a provenance entry in
`sanantonio/assets/photos/sa_manifest.json`, plus the slug's photo key in the
`PHOTOS` set at `sanantonio/index.html:289`:

```js
const PHOTOS = new Set(['sa-jones','sa-kaur','sa-mckeerodriguez','sa-viagran','sa-mungia','sa-castillo','sa-galvan','sa-gavito','sa-gonzalez','sa-spears','sa-whyte']);
```

All 11 sitting members are already registered, so this is a no-op for the
remaining five — but required for any new non-roster filer. A slug not in
`PHOTOS` degrades to initials in a `.noimg` box.

### 9.6 Unlisted / candidate framing (rare)

`build_candidate.py` has `CANDIDATE_SLUGS` and `UNLISTED_SLUGS`
(both `{"shaikh"}`). An unlisted page gets
`<meta name="robots" content="noindex, nofollow">` and must not appear in the
landing JSON at all.

**Verify before moving on:** `git diff` shows exactly the edits above and
nothing else. For a multi-cycle member, the cycle date bounds match the
election dates you sourced in §1.

---

## 10. Build the profile

```bash
python build_candidate.py --slug <slug>
```

That is the whole build. `build_candidate.py` imports
`generate_profile_data` and calls `gpd.generate(slug, SITE_DIR,
slug_override=slug)` itself, then renders
`sanantonio/<slug>/index.html` from `profile_template.html` (injecting
`PROFILE_SLUG`, OG title/desc/slug). Outputs:

- `sanantonio/<slug>_data.json`
- `sanantonio/<slug>_all_donations.json`
- `sanantonio/<slug>/index.html`

Flags: `--slug`, `--all-remaining` (every ROSTER entry), `--html-only`
(re-render HTML from the current template, skip the JSON export — use this
after a template change).

**Do not run `generate_profile_data.py --slug <slug>`.** That command, as
written in KAUR_PLAN step 7, PUBLISH_TO_AUSTIN step 3 and MAYOR_PLAN's
post-merge block, **fails**: `--candidate` is `required=True` (D3). If you ever
need it standalone, the correct invocation is:

```bash
python generate_profile_data.py --candidate <slug> --slug <slug> --output-dir sanantonio
```

`--output-dir` defaults to the **repo root**, not `sanantonio/`, so omitting it
scatters JSON next to the scripts.

**Verify before moving on:** the generator's verification block prints a total,
donor count, employer-affiliated %, top industry, by-year table, and — for
multi-cycle members — per-cycle heroes plus the employer-affiliated delta
between the first two cycles. Sanity-check the total against §3's portal
cross-check. Confirm `Built N election cycles` matches your intended tab count.

---

## 11. Flip the landing card

```bash
python _update_landing.py <slug>
```

Reads `sanantonio/<slug>_data.json`, drops `soon`, sets `href`, and writes
`raised` / `donors` / `empPct` / `topGroups` (top 4 non-`Unknown` interest
groups with bar widths) back into `sanantonio/sanantonio_landing.json`.

Three traps (this script is undocumented in every plan doc — D7):

1. **Always pass slugs explicitly.** With no arguments it defaults to
   `["jones", "galvan", "kaur"]` and will silently not touch your new member.
2. **Run it from the repo root** — the paths are relative.
3. It only **updates existing** `candidates[]` entries. It will not create a
   card for a slug missing from the JSON.

Pass every slug you rebuilt, so stale stats refresh together:

```bash
python _update_landing.py jones galvan kaur mckeerodriguez viagran mungia <slug>
```

**Verify before moving on:** the script prints one
`<slug>: $X / N donors / P% affiliated` line per slug; the new member's entry
in the JSON has no `soon` key and has `href`, `raised`, `donors`, `empPct`,
and 4 `topGroups`.

---

## 12. Rebuild every other profile

Enrichment in §5–§8 is **global**: TEC re-aggregation, FEC matches, rules
re-derivation and the applies all touch shared `donor_identities` rows. Every
previously built profile's numbers have moved. Rebuild them all so the
committed JSON matches the DB:

```bash
python build_candidate.py --all-remaining
```

This is normal and expected — Mungia's PR touched all five prior members'
`*_data.json` and `*_all_donations.json` files, as did Viagran's.

**Verify before moving on:** `git status` shows a modified `_data.json` for
every prior member (a one-line diff each, since the JSON is minified). If a
prior profile is *unchanged*, ask why — it usually means an enrichment step
did not actually run.

---

## 13. Local verification

```bash
python -m http.server 8000    # from the repo root
```

- `/sanantonio/` — the new card is LIVE (not SOON), photo loads, flip side
  shows Top Industries with four bars, "See More" links to
  `/sanantonio/<slug>/`.
- `/sanantonio/<slug>/` — hero badge reads the right district, all-time view is
  the default, cycle tabs appear if and only if you defined them, top donors
  and firms panels populate, partisan-lean and affiliation cards render.
- Browser console: zero errors.
- **Byte-identical rebuild:** re-run `build_candidate.py --slug <slug>` and
  confirm the only diff is `generated_at`.

**Verify before moving on:** all of the above, plus the `<SLUG>_PLAN.md`
results log is filled in with real numbers (row counts, identity split, FEC
coverage, TEC matches, scrub batches/cost/resolutions, final headline stats).

---

## 14. Open the PR — then **STOP**

Commit on the `<slug>` branch, following the established two-commit shape:

1. `<Member> (DN) conveyor plan` — `<SLUG>_PLAN.md` alone.
2. `<Member> (DN) cycles, office override, roster entry` — the code
   registration edits (§9.1–9.3).
3. `<Member> (DN) live: profile build, scrub results, landing flip` — the
   research dir (batches, results, usage log), `sanantonio/<slug>/index.html`,
   the new and rebuilt `*_data.json` / `*_all_donations.json`, and
   `sanantonio_landing.json`.

Confirm the DB and `.env` are not staged:

```bash
git status --porcelain | grep -E '\.db|\.env'   # must be empty
```

PR body: the numbers from your results log — rows/contributions/dollars,
identity reclaim split, FEC coverage %, TEC matched count, scrub batch count
and spend, resolutions and affiliations added, final headline stats, and how
many of 11 cards are now live.

**STOP HERE. The user merges. Never self-merge.** Post-merge publishing is
§15–§16 and happens only in the main checkout.

---

## 15. Post-merge: sync the DB and republish

This is `PUBLISH_TO_AUSTIN.md`'s runbook, corrected against the code. Run
everything from the **main checkout**.

1. `git pull origin master`
2. **Sync the canonical DB.** Two options — see §17 for how to choose.
   - *Copy* (**preferred for a member branch**): copy the worktree DB over the
     canonical one. A member branch embodies thousands of detail postbacks,
     hours of FEC quota, and real scrub dollars that a replay cannot cheaply
     reproduce. Only safe if the worktree DB is a strict superset — it was
     copied from canonical at branch start and nothing else has touched
     canonical since.
   - *Replay*: run the branch's idempotent DB scripts against the canonical DB
     in pipeline order. `PUBLISH_TO_AUSTIN.md`'s list is **incomplete** (D14) —
     the correct order is:

     ```bash
     python fetch_data.py --slug <slug> --start-year 2016
     python build_identities.py
     python sa_tec_crosswalk.py --link-only
     python fec_enrich.py --workers 8 --limit <N>
     python sa_industry_rules.py
     for f in *_research/_apply_*_results.py; do python "$f"; done
     ```

     Confirm the printed counts match the PR's. FEC- and scrub-dependent
     fields will only match if enrichment reaches the same coverage.
3. **Rebuild from the canonical DB:** `python build_candidate.py --slug <slug>`
   (or `--all-remaining`). Diff the rebuilt JSON against what the PR merged —
   **only `generated_at` should differ.** If clean,
   `git checkout -- sanantonio/` so the tree is clean; publishes must be
   reproducible from a sha.
4. **Dry run:** `python publish_site.py --dry-run`. Verify the file list is
   exactly what you expect: profile JSONs, `<slug>/index.html`, the landing
   JSON, photos. Flags: `--austin-repo`, `--dry-run`, `--no-push`, `--force`.
5. **Publish:** `python publish_site.py`. It mirrors `sanantonio/` into the
   Austin checkout (rsync-style: files removed from the build are **deleted**
   from deploy), commits there as
   `Publish San Antonio section (generated from san-antonio-finance-data@<sha>)`,
   and pushes — which is live. `--no-push` stops before the push.
6. **If the push is rejected** (Austin repo moved): in the Austin checkout,
   `git pull --rebase origin master`, then `git push`. The publish commit
   touches only `sanantonio/`, so it rebases over Austin-side work cleanly.

Guardrails already enforced by `publish_site.py`: it refuses a dirty SA tree
(`--force` exists; prefer fixing), it touches **only** the `sanantonio/`
subtree of the Austin repo, and it reports Austin-side dirty files outside that
subtree while leaving them alone. `austin-finance-data/sanantonio/` is
generated output — **never hand-edit it**; fix things here and republish. If
the Austin side needs a non-generated change (nav links, for example), that is
a separate hand-authored commit in `austin-finance-data`, kept out of the
publish commit.

**Verify before moving on:** the publish output lists the expected files and
the commit sha is recorded.

---

## 16. Live verification

GitHub Pages takes roughly 1–2 minutes.

```bash
curl -s https://decodepolitics.org/sanantonio/<slug>_data.json | head -c 400
```

- Check a **number the PR changed** — `hero.total_raised`,
  `hero.unique_donors`, or `hero.employer_affiliated_pct` — against your build
  output. Also confirm `meta.candidate_slug` and `meta.office`.
- Load `https://decodepolitics.org/sanantonio/` — the new card shows LIVE with
  the right stats, and no previously live card regressed.
- Load `https://decodepolitics.org/sanantonio/<slug>/` — hero, charts, cycle
  tabs, top donors, affiliations all render; console clean.
- Spot-check one prior member's page, since §12 rebuilt them all.

**Verify before moving on:** the served JSON's numbers equal your local build's
(not the pre-PR values — a stale number means Pages hasn't rebuilt or the
mirror didn't include the file). Report the live URLs and the confirmed numbers
back to the user.

---

## 17. DB discipline (the most dangerous part)

1. **One canonical DB, in the main checkout only.**
   `decode-politics/san-antonio-finance-data/san_antonio_finance.db` (~850 MB).
   `*.db`, `*.db-shm`, `*.db-wal` are gitignored, so **merging a PR never
   updates the DB**. Every worktree has its own separate copy. This is why §15
   step 2 exists at all.
2. **Back up before any ingest.** Re-ingest can **duplicate donor identities**:
   `build_identities.py` reclaims donor_ids by member-row overlap, and a
   changed row population can split or merge clusters, minting new ids and
   orphaning every donor_id-keyed row (FEC caches, TEC links, scrub results,
   affiliations). Copy the DB aside first; it is the only rollback you have.
3. **Choosing replay vs copy:**
   - **Copy** when the branch spent money or quota that replay cannot cheaply
     reproduce — any branch with a scrub run, a large detail harvest, or a long
     `fec_enrich` run. That is essentially every member branch. Copy is only
     safe when the worktree DB is a **strict superset** of canonical: it was
     copied from canonical at branch start and nothing else wrote to canonical
     in the meantime. If two member branches were in flight at once, copy is
     **not** safe — one will silently discard the other's work.
   - **Replay** when the branch's DB work is cheap and deterministic (a schema
     migration, a normalization backfill, a small append) or when canonical has
     moved since the branch started. Replay is also the honest choice when you
     cannot prove the superset property.
4. **Never commit** `san_antonio_finance.db` or `.env`. `.env` holds the FEC
   API keys; `.env.example` documents the variable names
   (`FEC_API_KEY_1`, `FEC_API_KEY_2`).
5. **Do not open the DB from two writers at once.** Several scripts set
   `PRAGMA journal_mode=WAL` and 60–120s busy timeouts, but a scrub apply
   racing a rebuild will still block or fail. Serialize the pipeline.

---

## 18. Gotchas / traps

### Plan-doc drift (fix these expectations first)

**D1 — TEC crosswalk is no longer out of scope.** `KAUR_PLAN.md` §"Out of
scope" says the TEC crosswalk "is not yet ported to SA". It landed in master
with Viagran (`sa_tec_crosswalk.py`, commit `5a5edb7`) and
`MUNGIA_PLAN.md` correctly makes `sa_tec_crosswalk.py --link-only` a required
post-`build_identities` step against the already-ingested ~1.81M-row table.
Following KAUR_PLAN verbatim today skips it — and because
`generate_profile_data.py` guards on the table's existence, the failure is
**silent**: you just ship a thinner partisan panel.

**D2 — "re-run `_apply_jones_results.py`" is now wrong.** KAUR_PLAN step 3
names one apply script because Jones was the only research dir. There are now
five (`jones`, `kaur`, `mckee`, `viagran`, `mungia`). The correct rule, per
`PUBLISH_TO_AUSTIN.md` step 2 and verified in code: **`sa_industry_rules.py`
first, then EVERY `*_research/_apply_*_results.py`.** Rules resets all
non-manual resolutions (`resolved_confidence != 'manual'`), the applies write
`llm-research-high|medium` (not `manual`), and the applies only fill NULLs.
Use a glob, never a hardcoded list.

### Documented commands that don't exist as documented

**D3 — `generate_profile_data.py --slug <x>` fails.** `--candidate` is
`required=True`. The command appears in KAUR_PLAN step 7,
`PUBLISH_TO_AUSTIN.md` step 3, and `MAYOR_PLAN.md`'s post-merge replay. Use
`build_candidate.py --slug <x>` (which calls `generate()` internally with the
right output dir) or, standalone,
`--candidate <slug> --slug <slug> --output-dir sanantonio`. Note also that
`--output-dir` defaults to the repo root, not `sanantonio/`.

**D4 — `build_identities.py` takes no arguments.** No argparse at all: no
`--db`, no `--dry-run`. The DB path is a module constant resolved relative to
the script. Plan docs list it alongside `--db`-capable scripts; you cannot
point it at another database.

**D5 — `sa_tec_crosswalk.py --link-only` is a `sys.argv` string check, not
argparse.** So there is no `--help` and no `--db`, and an unrecognized or
typo'd flag is **silently ignored** — `--linkonly` would trigger a full 99-shard
ingest attempt. Shard directory comes from `$TEC_DIR`, defaulting to a
hardcoded absolute path into the Austin checkout.

**D6 — `fec_enrich.py` cannot be scoped to a member.** KAUR_PLAN step 4 says
"for the new (unmatched) donors", but the query is global: top-N unmatched
donors DB-wide by `total_donated`, `--limit` default 2000. No `--slug`, no
`--db`. Size `--limit` deliberately and expect to enrich unrelated donors.

**D7 — `_update_landing.py` is undocumented and has a dangerous default.** No
plan doc mentions it; KAUR_PLAN step 7 describes the landing flip as if it were
a hand-edit. The script exists and does the job, but with no arguments it
defaults to `SLUGS = ["jones", "galvan", "kaur"]` and silently skips your new
member. It also uses relative paths (repo root only) and only updates entries
already present in the JSON.

**D8 — the scrub pool is per-campaign, not lifetime.** `_prep_*_batches.py`'s
docstring says donors who "gave >= $100 lifetime"; the SQL is
`SUM(cf.amount_real) ... WHERE cf.filer_slug = SLUG ... HAVING >= 100`. KAUR_PLAN's
phrasing ("≥ $100 to the Kaur campaign") is the accurate one.

**D9 — the research-dir prefix is not the slug.** `mckee_research` /
`mckeebatch_*` serve slug `mckeerodriguez`. Only `SLUG` inside `_prep` must be
the real `filer_slug`; the dir and batch prefix are a free short handle, and
the cross-dir coverage glob (`../*_research/*batch_*.json`) doesn't care.

**D10 — three registration points, not two.** Plan docs name ROSTER,
CANDIDATE_CYCLES and the landing JSON. `OFFICE_OVERRIDE` in
`generate_profile_data.py` is equally required (Viagran's registration commit
`e2ff5ed` touched exactly `CANDIDATE_CYCLES` + `OFFICE_OVERRIDE` + ROSTER),
and `PHOTOS` in `sanantonio/index.html:289` plus
`sanantonio/assets/photos/sa_manifest.json` are two more (already populated for
all 11 sitting members).

**D11 — a missing ROSTER entry does not fail the build.**
`build_candidate.py --slug <x>` falls back to a synthetic entry with
`district: "?"`, `race: "?"`, `display: slug.title()`. The build succeeds and
silently prints a wrong landing card. KAUR_PLAN's "(adds kaur to ROSTER)"
reads as if the script does the adding; it is a hand-edit.

**D13 — `fetch_data.py --start-year` defaults to 2018, not 2016.**
`ETL_REVIVAL_PLAN.md` §G.3 establishes "start-year 2016 everywhere"; the flag
default contradicts it. `sa_append.py` hardcodes `START_YEAR = 2016`, so the
append path is safe, but a direct `fetch_data.py` call without the flag
silently loses 2016–2017.

**D14 — `PUBLISH_TO_AUSTIN.md`'s replay list is incomplete.** It gives
`fetch_data.py → build_identities.py → sa_industry_rules.py → each apply`,
omitting `sa_tec_crosswalk.py --link-only` and `fec_enrich.py`. A replay as
written leaves the TEC aggregates and FEC coverage out of step with the PR's
build, and the JSON diff in step 3 will show more than `generated_at`.

**D17 — `fetch_data.py --dry-run` is NOT a cheap probe.** It skips only the DB
writes. The detail harvest still runs, and because `details_done` is populated
only when *not* dry-running, it re-fetches **every** schedule-detail postback at
`--detail-pace` and throws the results away — so a dry run is strictly *slower*
than the real ingest. For a filer-name or row-count probe always pair it:
`--no-details --dry-run`. (Cost of learning this on Gavito: a 10-minute run that
produced nothing.)

**D18 — the initial search response is not the grid's page 1.** Fixed on the
`gavito` branch; the note stays because the shape is worth knowing. The search
POST returns rows ordered by **contributor name**, while the DataGrid's own
paging is ordered by **amount**. `fetch_data.py` used to keep the search
response's 500 rows as "page 1" and then postback to pages 2..N, and since the
walk only moves forward (`p > current_page`) it never revisited page 1 — so on
every multi-page filer the true page 1 was silently never fetched. Gavito stored
1,334 of 1,676 rows and $484,056 of $668,610 before the fix, losing whole
transaction classes (expenditures 127 → 549, plus `Lender` and
`Candidate / Committee` rows).

The fix steps to the first linkable page — which makes page 1 a target — fetches
the true page 1, then resumes the forward walk; `row_hash` dedup makes the
overlap free. **The failure was data-dependent** (it only bites when the two
sort orders diverge for that result set), which is why five of seven members
were affected and Jones and McKee-Rodriguez were not. If you ever touch the
pager, re-verify against the portal Grand Total, not against row counts.

**D19 — `filer_slug` is the searched member, not the recipient.** *(Fixed on
the `gavito` branch via `RECIPIENT_ALIASES`; the note stays because the shape
recurs for every new member — register their recipient string or the generator
will warn.)* A portal
search returns every row where the name appears, including contributions the
member *made to other candidates*. Those rows land under their `filer_slug` and
are counted as money they raised. The `recipient` column is the discriminator —
but it is **not** simply "recipient == member": Jones's own money is split
across two recipient strings (`Gina Jones`, 4,482 rows, and `Gina Ortiz Jones`,
3 rows / $510), so a naive filter would drop legitimate rows. Genuinely foreign
rows found across the eight built members total roughly $2,700 — small in
dollars, but on Gavito it rendered four phantom year-bars (2019–2022) for a
candidate whose first race was 2023. Watch for it whenever the by-year table
predates the member's first campaign; Viagran's includes $275 to her sister
Rebecca, the same-surname relative §1 warns about.

### Code-level traps nothing documents

**D15 — stale TEC links are never repaired.** `link_to_sa_donors()` only fills
`austin_donor_id IS NULL`, while `aggregate()` resets and rewrites `tec_*` for
**all** donors from the linked rows. If `build_identities.py` retires a
donor_id (a cluster split or merge), the stale non-NULL FK is never relinked
and those TEC rows silently drop out of the aggregate. A full relink would
require nulling `austin_donor_id` first — do that deliberately, not by
accident.

**D16 — `sa_industry_rules.py` needs `.env`.** At pass 4 it does
`import fec_enrich`, and `fec_enrich` raises `SystemExit` at import time if
`FEC_API_KEY_1` is missing. It makes no API calls, but it will not run without
the key file. `--dry-run` skips the import, which masks the failure.

**Non-individual donors get no donor_id.** `build_identities.py` scopes to
`donor_type IN ('INDIVIDUAL','Individual')` and names containing a comma, and
resets `campaign_finance.donor_id` to NULL for everything else on rerun. PAC
and entity donors are therefore invisible to identity-keyed enrichment — that
is why Shaikh's employer coverage (401/572) trails Jones's (4,418/4,485): his
gap is entity donors reporting "Union"/"PAC".

**Stored row count < portal row count is correct.** `row_hash` dedup collapses
amended-report re-listings (Jones: 5,003 → 4,577). Don't "fix" it.

**The portal Grand Total spans all transaction types.** Compare contributions
against contributions, not against the Grand Total (Jones: $1,386,125.74 total
= $697,369.75 contributions + expenditures).

**`--max-pages 50` is a real ceiling.** The `...` next-window pager fix means
big result sets are reachable, but 50 pages × 500 rows = 25,000 rows is the
hard stop. Narrow per report period rather than raising it.

**Veteran filers may not be findable by exact name.** Nirenberg's exact-name
search returns ~$258K / 439 rows because his mayoral money lives under a
committee filer string. Resolve the filer string before trusting any long-history
pull. Pre-2016 reachability (the year-dropdown floor) is still untested.

**`-noemp` confidence tags and `FIRM_NOISE_SQL` exist for a reason.** An
occupation-only resolution ("Attorney") is not a firm; the firms panel excludes
those. Don't remove the filter to make the panel look fuller.

**"Not Employed" legitimately tops some cards.** `_update_landing.py` filters
only the literal label `Unknown` from `topGroups`, so retirees can be the
largest bucket (Jones's card leads with Not Employed at $182K). That is honest
output, not a bug.

**Do not guess industries to fill coverage.** MAYOR_PLAN §G.4: if employer data
is thin, render honest coverage and say so. The scrub instructions say the same
thing three different ways — `industry: null` at low confidence is a correct
answer, and "a quiet outcome is a valid, expected, and common result".

**Affiliations need a source URL and a snippet, always.** No inference of
political or religious affiliation from a name, a zip code, or an employer
alone. Both sides of every tracked spectrum get searched at equal depth
(Israel/Palestine, guns, oil & gas, defense) — an empty bucket still emits its
zero so the template can show an explicit absence rather than omitting the
column, which would read as selective reporting.

**Federal money stays out of city charts.** Finance-lane convention: FEC
history is intro-mention only. FEC data's job here is partisan lean and
employer gap-fill, not dollars.

**Loans and self-funding** get disclosed in the intro and stay out of the
contribution charts (Austin convention, MAYOR_PLAN §G.3).

### Known open opportunity

The **Schedule A1 PDF extractor** is still unbuilt. Jones's April 2025 30-day
report is a fully digital PDF whose Schedule A1 entries carry filled Principal
Occupation + Employer for *every* itemized contribution, cleanly extractable
with `pypdf`. That would close the employer gap for all donors, not just
FEC-matched ones. It is a candidate for its own branch — not something to
attempt inside a member conveyor.

---

## Appendix A — verified command reference

Flags below were read from each script's argparse (or `sys.argv` handling) in
this checkout. Where a plan doc disagrees, the entry here is authoritative.

| script | invocation | flags (verified) |
|---|---|---|
| `fetch_roster.py` | `python fetch_roster.py` | `--db`, `--dry-run`, `--add-candidate`, `--slug`, `--first`, `--last`, `--office-sought`, `--notes`, `--source-url` |
| `fetch_data.py` | `python fetch_data.py --slug <slug> --start-year 2016` | `--db`, `--slug`, `--filer-first`, `--filer-last`, `--start-year` (def **2018**), `--end-year` (def 2026), `--office` (`any`\|`na`\|`mayor`\|`d1`..`d10`), `--filer-type` (`C`\|`S`\|`U`\|`All Types`), `--max-pages` (def 50), `--no-details`, `--detail-pace` (def 0.4), `--max-details` (def 0), `--dry-run`, `--save-html` |
| `sa_append.py` | `python sa_append.py --only <slug>` | `--db`, `--only`, `--extra` (repeatable), `--end-year` (def 2026), `--dry-run` |
| `sa_normalize.py` | `python sa_normalize.py` | `--db`, `--dry-run` |
| `sa_employer_seed.py` | `python sa_employer_seed.py` | `--db`, `--export`, `--austin-db` |
| `build_identities.py` | `python build_identities.py` | **none** (no argparse) |
| `sa_tec_crosswalk.py` | `python sa_tec_crosswalk.py --link-only` | `--link-only` only (raw `sys.argv` check); shard dir via `$TEC_DIR` |
| `fec_enrich.py` | `python fec_enrich.py --workers 8 --limit <N>` | `--dry-run`, `--limit` (def 2000), `--reset`, `--workers` (def 8); needs `.env` |
| `sa_industry_rules.py` | `python sa_industry_rules.py` | `--db`, `--dry-run`; needs `.env` (imports `fec_enrich`) |
| `*_research/_prep_*_batches.py` | `python <prefix>_research/_prep_<prefix>_batches.py` | **none**; edit `SLUG`, `BATCH`, `MIN_TOTAL` in-file |
| `*_research/_run_*_research.js` | `node <prefix>_research/_run_<prefix>_research.js` | **none**; edit `POOL`, `MODEL`, `MAX_BUDGET_USD` in-file |
| `*_research/_apply_*_results.py` | `python <prefix>_research/_apply_<prefix>_results.py` | `--dry-run` (raw `sys.argv` check) |
| `generate_profile_data.py` | `python generate_profile_data.py --candidate <slug> --slug <slug> --output-dir sanantonio` | `--candidate` (**required**), `--slug`, `--output-dir` (def **repo root**) |
| `build_candidate.py` | `python build_candidate.py --slug <slug>` | `--slug`, `--all-remaining`, `--html-only` |
| `_update_landing.py` | `python _update_landing.py <slug> [<slug>...]` | positional slugs; **defaults to `jones galvan kaur`** if none |
| `publish_site.py` | `python publish_site.py --dry-run` | `--austin-repo`, `--dry-run`, `--no-push`, `--force` |

## Appendix B — registration checklist

| # | file | symbol | required? |
|---|---|---|---|
| 1 | DB `council_members` | row keyed on `slug`, with `filer_first_name` / `filer_last_name` / `full_name` | **yes** — `fetch_data.py` and `generate_profile_data.py` both hard-fail without it |
| 2 | `build_candidate.py` | `ROSTER` list entry | yes in practice (build silently degrades without it) |
| 3 | `generate_profile_data.py` | `OFFICE_OVERRIDE[slug]` | **yes** — hero badge falls back to a district-less string |
| 4 | `generate_profile_data.py` | `CANDIDATE_CYCLES[slug]` | only for multi-campaign members |
| 5 | `sanantonio/sanantonio_landing.json` | `candidates[]` entry: drop `soon`, add `href`/`raised`/`donors`/`empPct`/`topGroups` | **yes** — via `_update_landing.py <slug>` |
| 6 | `sanantonio/index.html` | `PHOTOS` set (line ~289) | already covers all 11 seats; needed for any new filer |
| 7 | `sanantonio/assets/photos/` | `sa-<slug>.webp` + `sa_manifest.json` provenance entry | same as above |
| 8 | `build_candidate.py` | `CANDIDATE_SLUGS` / `UNLISTED_SLUGS` | only for non-officeholders / unlisted pages |
