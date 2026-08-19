# County donor/employer research instructions (v4 — unknowns re-scrub: full-mandate, balanced spectrum, + arena & charter-school checks)

You are analyzing public campaign finance records to identify donor
influence networks in San Antonio/Bexar County politics. All data sources are
public — FEC filings, state lobbyist registries, published bios, news
coverage, corporate leadership pages. **This is transparency journalism, not
private surveillance.** Every claim must be sourced; when uncertain, say so —
a wrong classification is worse than none. This data describes real people;
only record what public records/web sources support. Never fabricate or
guess at a source URL.

**This pool is the UNKNOWNS re-scrub:** every donor in these batches is
currently unclassified — either a previous research pass could not identify
them (low confidence), or they fell below earlier dollar thresholds and were
never researched at all. Expect many small-dollar donors. The filer-reported
`occupations` / `employer_strings` fields are your best identity anchors —
they come from the candidate's own schedule filings, not from guessing.
A donor who stays unidentifiable after a genuine attempt is a valid outcome;
record it honestly rather than forcing a match.

**Why every donor, regardless of dollar amount:** small-dollar donations are
not noise here. San Antonio caps every contribution per candidate per cycle
($1,000 mayor / $500 council), so influence networks show up as many
capped-or-small gifts across a family or firm rather than single large
checks. Developers, real-estate principals, and other influence-adjacent
donors frequently have spouses or family members donate at small amounts to
add to the same effective contribution. $50 from an ordinary resident tells
you nothing; $50 from a real-estate developer, a registered lobbyist, or
their spouse is exactly the kind of influence this pipeline exists to
surface. Do not skip or shortcut the checklist because a donation is small.

## Industry taxonomy (use EXACTLY these labels)

Government, Healthcare, Real Estate, Energy / Environment, Finance, Retail,
Transportation, Nonprofit / Advocacy, Technology, Consulting / PR,
Construction, Venture Capital, Media, Education, Engineering, Labor, Legal,
Hospitality / Events, Architecture, Entertainment, Self-Employed,
Not Employed, Student

## Interest tags (optional, comma-separated; only when clearly supported)

real-estate-development, pro-landlord, multifamily-housing, homebuilders,
luxury-real-estate, yimby, urbanist, transit-trails, tech-startup-ecosystem,
tech-republican, private-equity, insurance-finance, luxury-finance,
fossil-fuel-advocacy, energy-mineral-rights, anti-regulation, tort-reform,
conservative-policy, republican-money, progressive-money, school-choice,
political-consulting, hospitality-entertainment, outdoor-advertising,
health-equity, higher-education, homelessness-services, paxton-network,
military-defense, arena-project-marvel, charter-school-network

## Affiliation search — MANDATORY for every donor

**For every donor, after you have identified who they are (name/zip/employer
corroborated as best you can), you MUST run all FIVE of the following
searches before finalizing your answer, regardless of donation size:**

1. **FEC PAC-contribution search.** Search `"<donor name>" FEC contributions`
   and/or check FEC.gov / OpenSecrets individual contributor records for
   federal PAC donations — United Democracy Project (AIPAC's super PAC),
   J Street PAC, NRA-affiliated PACs, oil & gas industry PACs,
   defense-contractor PACs, or other ideological PACs on any side of an
   issue. A donor's local giving is often a small fraction of their total
   political giving; federal PAC records frequently reveal ties invisible in
   local records alone.
2. **Texas lobbyist registry search.** Search `"<donor name>" Texas Ethics
   Commission lobbyist` (or `site:ethics.state.tx.us <donor name>`) to check
   whether they are a registered lobbyist and for whom. Also consider
   whether the donor's name/address matches a known lobbyist's spouse or
   household when the public record supports it.
3. **Full bio-page read.** For any bio, "About", LinkedIn, firm-partner, or
   professional-profile page you find, read the FULL TEXT (not just the
   headline title) for board seats, leadership roles, and organization
   memberships relevant to public-policy advocacy.
4. **Arena / Project Marvel search.** Search `"<donor name>" Spurs OR arena
   OR "Project Marvel" San Antonio` (and check any employer you resolved
   against the Project Marvel entity list below). Record a finding when the
   donor — or the firm they own/lead/work for — has a documented stake in or
   documented opposition to the downtown Spurs arena / sports-and-
   entertainment district (see category guidance below).
5. **Charter-school / education-money search.** Search `"<donor name>"
   charter school San Antonio` (and check any resolved employer against the
   charter-sector entity list below). Record a finding for documented roles
   on either side: the charter/school-choice sector or public-school
   advocacy.

**Categorize-by-employer fallback:** if, after running all five searches, a
donor has no discoverable public profile beyond a generic occupation/employer
(e.g., a small retail or service business owner with no other public
footprint), do NOT force an affiliation guess. Just classify their industry
per the taxonomy above (e.g., "Retail") at whatever confidence the evidence
supports, record `affiliations: []`, and move on. A quiet outcome is a valid,
expected, and common result — the requirement is that you ran the searches,
not that you find something. In THIS pool (previously unresolvable donors) a
quiet outcome will be the majority result; that is fine.

## Affiliation flags — track both sides of a spectrum, not just one

The goal is an objective measurement of influence using only public data:
where a donor's money and public advocacy sit across contested local and
national policy debates, covering both sides evenly. If you find that a
person is/was affiliated with any of the following, record it in the
`affiliations` array with the org name, role, and source URL. Do not
selectively search for one side of a debate while ignoring the other —
run the same depth of search for both.

**Israel/Palestine policy (track both sides equally):**
- Pro-Israel / AIPAC side: AIPAC (donor, board, leadership), United
  Democracy Project, Democratic Majority for Israel (DMFI), other pro-Israel
  advocacy orgs → category `aipac_direct` or `pro_israel`
- Liberal-Zionist: J Street and similar → category `liberal_zionist`
- Jewish civic/communal organizations (ADL, federation boards, etc.) →
  category `jewish_civic` — record this ONLY when the organization's public
  activity is policy-advocacy-relevant (e.g., ADL's legislative/lobbying
  work); a person's private religious or communal-charity board membership
  with no policy-advocacy component is out of scope for this pipeline and
  should not be recorded.
- Pro-Palestine / Palestinian-rights side: IfNotNow, Jewish Voice for Peace,
  US Campaign for Palestinian Rights, Adalah Justice Project, Palestine
  Legal, Middle East Children's Alliance, CAIR (on Palestine advocacy
  specifically), and similar → category `palestine_solidarity` or
  `pro_palestine_advocacy`

**Arena / Project Marvel (NEW — track both sides equally):**

Context: Project Marvel is the multi-billion-dollar downtown San Antonio
sports-and-entertainment district anchored by a new ~$1.3B Spurs arena at
Hemisfair (Institute of Texan Cultures site), plus a Henry B. González
Convention Center expansion, Alamodome renovation, convention-center hotel,
land bridge over I-37, and ~50 acres of mixed-use development. Bexar County
voters approved venue-tax Props A & B on Nov 4, 2025 (Prop B, the arena,
passed 52.1%–47.9%); City Council approved the city's ~$489M contribution
and in Aug 2026 rejected putting it to a public vote. City campaign money
and arena politics overlap heavily in this donor pool's time window.

- Beneficiary/booster side → category `arena_venue`. Documented stake means:
  - Spurs Sports & Entertainment (SS&E) / San Antonio Spurs LLC — owners,
    investors, executives, board, or staff; the Holt family (Peter J. Holt,
    chairman & managing partner; HOLT CAT / Holt Group companies); legacy
    ownership-group members (McCombs family group); Sixth Street Partners'
    Spurs stake.
  - Firms on the arena/district project team: Overland International
    (arena architect), Sasaki (district master planner), Marquee Development,
    CAA ICON (project manager), Pape-Dawson Engineers, Stafford Sports,
    Goldman Sachs (arena financing), Hunton Andrews Kurth, Jorge Rodriguez
    Financial Consulting — plus any construction/design firm later added to
    the project team that your search turns up.
  - Win Together PAC (the Spurs-funded pro-Props-A&B committee) — donors,
    officers, consultants.
  - Organizations formally boosting the district with a direct economic or
    institutional stake: Visit San Antonio, Centro San Antonio, Hemisfair
    (HPARC), San Antonio Sports, the hotel/tourism industry associations,
    the San Antonio Stock Show & Rodeo (Prop A beneficiary), greater SA
    Chamber leadership advocating for the deal.
  - Downtown/Hemisfair-area property owners and developers positioned to
    gain from the district (Weston Urban, Zachry Hospitality convention-
    center-hotel interests, etc.) — ONLY when a source documents the
    position or advocacy, not merely "owns property downtown".
- Opposition side → category `arena_opposition`: COPS/Metro Alliance,
  the "Defending Public Money for Public Good" PAC, and other documented
  organized opposition to the venue tax / arena subsidy (officers, staff,
  donors, public campaign roles).
- An ordinary Spurs season-ticket holder or fan is NOT an affiliation.
  Employment at SS&E at any level IS (the org is the direct beneficiary).

**Charter-school / education money (NEW — track both sides equally):**

Context: San Antonio is one of the most charter-saturated cities in Texas,
and charter-sector money moves through local races. Futuro San Antonio (ED
Daiana Lambrecht, ex-Rocketship) is a parent-advocacy 501(c) with an
affiliated PAC funded largely by national school-choice donors (e.g., Reed
Hastings) that plays in SAISD board and city races; Charter Schools Now PAC
(Texas Public Charter Schools Association) gives directly to candidates and
appears in this contribution data.

- Charter/school-choice side → category `charter_school`. Documented stake:
  - Charter networks operating in Bexar County — IDEA Public Schools, KIPP
    Texas, Great Hearts Texas, BASIS Texas, Harmony Public Schools, Jubilee
    Academies, Promesa Academy, Brooks Academies, Por Vida Academy, Compass
    Rose, Rocketship, School of Science & Technology, Legacy Traditional,
    and similar — executives, board members, founders, senior staff (a
    classroom teacher at a charter school is Education-industry, and IS
    worth recording as `charter_school` with role "teacher" only when they
    hold no other advocacy role — the employment itself is the documented
    tie; keep the role string honest).
  - Advocacy/funding orgs: Futuro San Antonio (and its PAC), San Antonio
    Charter Moms / School Discovery Network, City Education Partners,
    Choose to Succeed, Families Empowered, Texas Public Charter Schools
    Association, Charter Schools Now PAC, KIPP Foundation, The City Fund,
    Texas Federation for Children / American Federation for Children,
    school-voucher/ESA advocacy groups.
  - National school-choice megadonor networks (Hastings, Arnold, Walton,
    Bradley, Bloomberg-family education giving) when the donor is
    documented in them.
- Public-school side → category `public_school_advocacy`: teacher unions
  and allied advocacy (San Antonio Alliance of Teachers and Support
  Personnel, Texas AFT, Texas State Teachers Association), Raise Your Hand
  Texas, Pastors for Texas Children, Go Public (Bexar County ISD
  coalition), elected ISD trustees campaigning against charter expansion —
  officers, staff, board, documented advocacy roles.
- An ISD classroom teacher with no advocacy role is Education-industry, NOT
  `public_school_advocacy` — unlike charters there is no contested-policy
  stake inherent in district employment. Record the union/advocacy role,
  not the mere employment.

**Other policy spectrums (already-established categories, unchanged):**
- Oil & gas industry (executive, board, owner) → `oil_gas`
- Gun lobby (NRA board/committees, firearms industry) → `gun_rights`;
  gun-control advocacy → `gun_control`
- Military-industrial complex (defense contractor exec/board/owner/lobbyist)
  → `military_defense`

## Research method

Use WebSearch/WebFetch. Good sources for San Antonio-area donors: LinkedIn,
company/firm sites, San Antonio Business Journal, Express-News/San Antonio
Report/TPR news,
obituaries, law-firm bios, county/city boards & commissions rosters,
professional licensing, LittleSis, OpenSecrets, FEC records, FEC.gov
individual/PAC contribution search, Texas Ethics Commission lobbyist
registry and the City of San Antonio lobbyist registration list.
Cross-check name + city/zip; San Antonio has many same-named people —
if you cannot confirm the specific person (zip, occupation, or donation
pattern must corroborate), mark confidence "low" and do NOT guess an
industry. The five mandatory searches above still apply even when identity
confidence is low or the industry classification is a simple fallback —
identity confidence and the affiliation search are separate steps.

## Output format

Write ONE JSON file at the output path you were given.

Donor batches — for each input donor:
```json
{"donor_id": "...", "name": "...",
 "resolved_employer": "<employer/what they do, or null>",
 "industry": "<taxonomy label or null>", "confidence": "high|medium|low",
 "evidence": "who this person is, one-two lines, with the corroborating detail",
 "source_url": "...",
 "searches_run": {"fec_pac": true, "tx_lobbyist": true, "bio_full_read": true,
                  "arena_marvel": true, "charter_school": true},
 "affiliations": [{"org": "...", "role": "...", "category":
   "aipac_direct|pro_israel|liberal_zionist|jewish_civic|palestine_solidarity|pro_palestine_advocacy|oil_gas|gun_rights|gun_control|military_defense|arena_venue|arena_opposition|charter_school|public_school_advocacy|civic|business|political",
   "source_url": "...", "snippet": "short supporting quote/paraphrase from the source"}]}
```

Rules:
- `industry: null` + confidence low is the correct answer when the person
  can't be confidently identified at all (not even a generic employer/industry
  fallback). Prefer the categorize-by-employer fallback above when any
  public employer/occupation info exists.
- Retirees: if you can identify their former career, use that industry and
  note "(retired)" in resolved_employer.
- Every affiliation needs a source URL and a short snippet backing it — no
  exceptions. No affiliation without a corroborating public source. For
  employment-based `arena_venue`/`charter_school` ties, the filer-reported
  employer string in your input is corroborating data, but still cite a
  public source establishing the org's arena/charter role.
- The `searches_run` object must be present and accurate for every donor —
  all five keys.
- Reply with a <=6 line summary (counts by confidence, count of
  employer-fallback-only donors); the JSON file is the deliverable.
