# Claude Code handoff — TrabahoLens evidence and deployed-dashboard restoration

Date: 2026-09-28. This is the current handoff. The previous
`docs/claude-code-handoff.md` is historical and must not be used as current
status. The user wants the deployed TrabahoLens dashboard's actual bento-style
layout and small interactions, with accurate source-backed data. The user
rejected the earlier redesigned interface in commit `1d652a7`. They have now
asked to hand this work to Claude Code.

## Start here

- Local repository: `/Users/marc/Documents/Personal/Projects/TrabahoLens`.
- Branch: `codex/rebuild-v2-final-remediation`, HEAD `1d652a7`; it is four
  commits ahead of `origin/audit/rebuild-v2-remediation` (`79cc362`).
- **The most recent data and deployed-shell changes are uncommitted.** Inspect
  `git status` and preserve all modified and untracked files. Do not assume a
  cloud checkout or the remote branch includes this state. If working in cloud,
  obtain an explicit transfer of this local state before doing implementation.
- Read the full `AGENTS.md`, then `docs/readiness-report.md`,
  `docs/limitations.md`, `docs/methodology.md`,
  `docs/data-completion-requests.md`, `docs/validation-2026-09-28.md`, and
  `data/sources/source-registry.yaml`.
- The original deployment is `https://trabaho-lens.vercel.app/`; compare it
  directly. The local preview is `http://127.0.0.1:8000/` when
  `scripts/serve.py` is running. The user currently has the local URL open in
  the in-app browser, but automated visual verification has not succeeded.

## User's actual acceptance criterion

Restore the deployed design itself: compact dark header, layer strip, group
filter, gradient legend, eight summary blocks, canvas squarified bento
treemap, hover tooltip, slide-out details panel, pan, zoom, touch and keyboard
interactions. Necessary copy and disabled-state changes should expose data
limits. Do not replace this with another design system or generic cards.
Compare desktop and mobile against the deployment and test every interaction.
Do not claim parity on the basis of CSS or static tests alone. The map cannot
honestly have the original dense set of employment-sized occupation boxes
until detailed employment estimates are obtained and validated.

The currently uncommitted `site/index.html`, `site/dashboard.css`, and
`site/dashboard.js` restore the deployed CSS and main structural hooks and add
a source-aware adapter. The original CSS is SHA-256 pinned by
`tests/test_dashboard_shell.py`. **Update (Claude Code, same day):** the
interaction layer was rewritten against the deployed script and verified with
`make browser-qa` (61/61 headless-Chrome checks, screenshots in `.browser-qa/`);
see `docs/validation-2026-09-28.md`. The user has not yet accepted it on real
devices. Its default employment
layer should use real major-group counts; source-native OWS wage records must
not be visually passed off as employed persons or nationwide occupation pay.
Unavailable metrics should have explicit explanations, not invented colours.

## Data now sourced and validated

1. **PSOC:** the official PSA 2022-updates XLSX is retained at
   `data/raw/psa_psoc/psoc_2022_updates.xlsx`; SHA-256
   `666e276e061efcf6939a4839420ddb0a9a30d3786ab41c5892a81a915858941c`.
   The importer now feeds the normal canonical build. It yielded 649
   classification units, including 466 four-digit unit groups. The PSA web
   page says 456; the discrepancy remains unresolved. These classification
   rows are not occupation-level measured employment records.
2. **LFS:** the PSA OpenSTAT 2024 annual JSON-stat table is retained at
   `data/raw/psa_lfs/lfs_employment_by_major_occupation_2024_annual.json`;
   SHA-256 `9cb88db30ecab0520cf5e8678f046b1cdb62a20ce834fa4db5c8abf856292b86`.
   Ten major-group employed-person estimates publish with explicit PSOC
   2012-to-2022 major-group correspondence. The rounded groups sum one person
   above the source total; retain source cells unchanged. No detailed counts
   may be allocated from them. Precision is not supplied by that table.
3. **SOF:** the official 2024 Table 2 precision workbook is retained at
   `data/raw/psa_sof/sof_2024_table_2_major_occupation.xlsx`; SHA-256
   `f2ee9ecd9f2231fe235d29841dac09a4fc978a9dfe29c6b92d9a17330bc8be80`.
   Nine major-group percentages publish as distribution *among OFWs* who
   worked abroad in the specified period. Armed forces is blank in the source,
   therefore missing, not zero. Source SE/CV are carried and high CV flagged.
   These values cannot be called OFW share *of domestic occupations*.
4. **OWS:** the official 2024 wage/precision workbook is retained at
   `data/raw/psa_ows/ows_2024_wage_estimates_precision.xlsx`; SHA-256
   `78823a5d60b625398ce97cebfde9e5dd0df7d412c6862d2e1b4bd245ea91eef2`.
   There are 693 occupation-by-industry records, 684 released as source-native
   references and nine quarantined for inconsistent confidence intervals.
   The survey covers full-time time-rated workers in formal establishments
   with at least ten workers, including agriculture. The value is monthly
   wage rate including regular cash allowances, not basic pay. Occupational
   code version is unconfirmed; there is no accepted PSOC join.
5. **O*NET 31.0:** original ZIP retained at
   `data/raw/onet/db_31_0_text.zip`; SHA-256
   `6883548adf5fde64cf6f801b35d15519c9225f2732c3cab0e281c652d16b23a9`.
   No accepted Philippine task/occupation crosswalk or published AI score.

Current release: 20 canonical metric observations, **19 published** (ten LFS,
nine SOF), plus the separate 684 available source-native OWS wage references
and nine withheld. Classification: 649 units. Model exposure scores: zero.
Education, posting demand and informality are unavailable. These are 2024
historical survey estimates, not live counts or all detailed occupations.

Important code: `src/trabaholens/v2/sources/psoc_importer.py`, `psa.py`,
`src/trabaholens/v2/wage_benchmarks.py`, `build_canonical.py`,
`build_release.py`, `validate.py`; source registry and retrieval manifest;
`data/reference/ows_wage_benchmarks.csv`; tests in
`tests/test_real_psa_workbooks.py` and `tests/test_dashboard_shell.py`.

## Exact source and method gaps

- Detailed boxes: find official PSA annual employment by detailed PSOC code,
  with population, weighting, year, classification version, sample design,
  standard errors/CV, suppression guidance and licence. Check current PSA
  published tables/APIs before asking the user to request a custom tabulation.
  If the official detailed data cannot be obtained or is unreliable, keep the
  map at published granularity. Never split a major-group total.
- OWS: confirm occupational code version and obtain a documented PSOC
  correspondence; ask whether the conflicting CIs in workbook rows 588–596
  have been corrected. A code match alone does not make wage and employment
  populations comparable.
- PSOC: clarify 466 workbook unit groups versus 456 on the PSA webpage.
- AI exposure: obtain reviewed PSOC-to-task correspondence. No English-title
  similarity mapping. Then use a versioned prompt and at least two successful
  repeated runs, preserve disagreement and uncertainty, and arrange independent
  Philippine occupational/statistical review. Model scoring must never receive
  employment, wages, OFW share or informality as inputs. Do not call these
  scores probabilities of automation or employment loss.
- Education, posting demand and informality each need compatible real sources
  and their own denominator/method. A posting dataset is a platform demand
  signal, not nationwide hiring intensity.
- Philippine AI Report's public practitioner survey documentation is at
  `https://philippineaireport.com/llms.txt` and `/survey.md`. Its documented
  REST `/meta` endpoint returned HTTP 402 `exceed_db_size_quota` on this date;
  the owner must restore service. No installed Philippine AI Report MCP tool
  was available, and the advertised MCP endpoint was not verified. The survey
  has 179 practitioner/leader respondents and question-specific denominators;
  it cannot supply national occupation employment or exposure values. If later
  usable, it could only support carefully labelled adoption context.

`docs/data-completion-requests.md` gives the full manual PSA requests and the
optional Philippine AI Report request. No request has been sent. Ask the user
only for the specific official file/access, expert review, or model credential
and spending decision that truly cannot be obtained through authorized public
sources. Do not ask them to pay for an API before assessing scope/licence.

## Verification and delivery

The last local record reports `make check`, `make test` (200 passing),
`make determinism`, `make check-stale`, `git diff --check` and JavaScript syntax
check passing; see `docs/validation-2026-09-28.md`. Rerun these on the actual
checkout, plus `make test-populated-pipeline`, and report exact results. The
SOF workbook has a malformed publisher print-area warning that did not affect
tested cell extraction. Browser QA remains incomplete. A prior desktop check
was for the user-rejected redesign and must not count as acceptance for the
current shell. Verify desktop, tablet and mobile, drawer, hover, pan/pinch,
filters, unavailable tabs, keyboard, CSV and error states; compare to live
deployment. The user currently has the local preview open; use a fresh browser
state rather than relying on any stale `file:` or browser error tab history.

Do not run retired v1 modules, read `data/legacy/v1/` in v2 code, fabricate
values, push/merge/deploy, or modify Philippine AI Report. Preserve this local
working tree. If you commit later, first include the allowlisted raw source
files, updated canonical tables, generated release, tests and documentation;
do not stage unrelated files blindly. Report commit, push, PR and deployment
as distinct states. Current work is local and production is not approved.

Return: the actual visual parity result; source-by-source data validation;
specific code changes and tests; exact unresolved manual requests; a clear
phase/readiness verdict; and whether production would display any value beyond
its valid population or granularity. Never label partial scaffolding as a
complete pipeline.
