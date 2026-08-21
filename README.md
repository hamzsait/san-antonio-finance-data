# san-antonio-finance-data

Data pipeline + site builder for the San Antonio section of decodepolitics.org.
This repo is **not served directly**: it builds the site into `sanantonio/` and
`publish_site.py` mirrors that folder into the sibling `austin-finance-data`
repo (whose GitHub Pages deploy serves it at decodepolitics.org/sanantonio/).
Never hand-edit `austin-finance-data/sanantonio/` — it is generated output.

## Runbooks
- `ADD_COUNCIL_MEMBER.md` — canonical template for adding a member
  (supersedes the per-member plan docs, now in `docs/archive/`)
- `PUBLISH_TO_AUSTIN.md` — deploy flow: sync DB → `build_candidate.py --slug
  <x>` → `publish_site.py --dry-run` → `publish_site.py` → verify live

## Layout
- Root `.py` — the pipeline, roughly in order: `fetch_data.py` /
  `fetch_roster.py` → `sa_normalize.py` → `build_identities.py` /
  `sa_identity_merge.py` → `sa_tec_crosswalk.py` → `fec_enrich.py` /
  `sa_fec_dedup_pass.py` → `sa_industry_rules.py` / `sa_ip_spectrum_flag.py` →
  affiliations (`affiliations_*.py`, reading root `findings_*.json`) →
  `generate_profile_data.py` → `build_candidate.py` / `build_focus_pages.py` →
  `publish_site.py`
- `sanantonio/` — the built site output (mirrored to the Austin repo)
- `<member>_research/` — committed LLM scrub batch corpora (audit trail for
  industry/unknown resolutions; do not delete)
- `docs/archive/` — superseded per-member plan docs
- `san_antonio_finance.db` (gitignored, ~920 MB) — the pipeline SQLite DB

`generate_profile_data.py --output-dir` defaults to `sanantonio/`; don't write
profile JSONs to the repo root.
