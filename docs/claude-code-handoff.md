# Historical Claude Code handoff (2026-09-18)

This document describes an earlier repository state. It is **superseded** by
`docs/claude-code-current-handoff.md` and must not be used as the current task
brief. In particular, PSOC, SOF and OWS sources have since been imported and a
new dashboard pass has begun. The uncommitted local working tree contains the
current work; the remote branch alone does not.

Date: 2026-09-18
Repository: `marcxxv/TrabahoLens`
Working branch: `codex/rebuild-v2-final-remediation`

## User decision

The user rejected the dashboard produced in commit `1d652a7` and does **not**
want another dashboard pass yet. Treat that commit as useful implementation
history, not an approved design direction.

The immediate objective is to satisfy as much of the remaining data,
classification, crosswalk, and exposure work as can be satisfied with genuine
evidence. Do not rebuild the dashboard until the underlying phases are actually
ready. Never make the interface look complete by filling evidence gaps.

Do not modify `main`, merge, push, deploy, or integrate into Philippine AI
Report unless the user separately authorises it.

## Non-negotiable project rules

Read `AGENTS.md` in full before acting. In particular:

- Never invent, impute, redistribute, broadcast, or infer a value merely to
  populate a view.
- PSOC is canonical. O*NET and SOC are US-derived proxies.
- Never map occupations by English title similarity.
- A value may publish only with complete provenance and a verified source file.
- Generative-AI task exposure is not automation, replacement, displacement,
  layoffs, unemployment, job-loss risk, or a forecast.
- Exposure scoring must use task evidence, at least two successful attempts,
  preserve disagreement, and never receive employment, wages, OFW share, or
  informality as scoring inputs.
- Do not run or import the retired v1 pipeline.

## Current git state

Current commits above `origin/audit/rebuild-v2-remediation`:

1. `2e98991 fix: close final credibility pipeline gaps`
2. `ea8bad4 docs: align readiness with verified pipeline state`
3. `8aa62f7 feat: publish verified LFS major-group estimates`
4. `1d652a7 feat: restore evidence-first bento dashboard` — user-rejected UI

The last verified acceptance run before this handoff was:

- `make test`: 192 passed
- `make check`: passed
- `make check-stale`: passed
- `make determinism`: two builds byte-identical
- `git diff --check`: passed

The local preview may still be running at `http://127.0.0.1:8000`.

## What is genuinely complete

### Credibility reset

- Unsupported v1 employment, pay, informality, OFW, hiring, and exposure values
  are withdrawn.
- Derivation class and source authority are independent axes.
- Release validation rejects incomplete provenance, misleading vocabulary,
  rejected crosswalks, and stale artifacts.
- Counts are derived from the payload, not hard-coded.

### Real LFS source-to-release path

The official PSA OpenSTAT matrix is:

`https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/1B/LFS/0121B3FEMP4.px`

The pinned query uses 2024 Annual and all major occupation categories. The raw
file is gitignored and its verified SHA-256 is:

`9cb88db30ecab0520cf5e8678f046b1cdb62a20ce834fa4db5c8abf856292b86`

The pipeline now performs real retrieval, format validation, hashing,
JSON-stat 1.x/2 parsing, multidimensional indexing, explicit category mapping,
conversion from thousands of persons to persons, explicit PSOC 2012 to 2022
major-group correspondence, canonical observation construction, release
validation, and publication.

Exactly ten 2024 annual major-group employment estimates publish. They are
sample-survey estimates with confidence grade B because the selected table does
not provide sampling-error bounds. They must never be distributed to finer
occupations. The one-person difference between the sum of rounded group cells
and the source total is expected rounding and must not be silently corrected.

### O*NET acquisition

The exact O*NET 31.0 archive was retrieved from:

`https://www.onetcenter.org/dl_files/database/db_31_0_text.zip`

Verified SHA-256:

`6883548adf5fde64cf6f801b35d15519c9225f2732c3cab0e281c652d16b23a9`

O*NET values do not publish because there is no accepted Philippine
occupation-to-O*NET crosswalk.

### Acquisition hardening

`src/trabaholens/v2/acquire.py` is registry-driven and validates expected
formats before atomic replacement. It rejects HTML error pages posing as data,
empty responses, corrupt ZIPs, malformed XLSX files, and non-JSON-stat JSON.
The retrieval manifest is evidence; registry status is configuration only.

### Classification-version governance

`data/reference/psoc_2012_to_2022_major.csv` contains ten explicit,
source-backed major-group correspondences. Published observations reference
these edges, and validation now refuses unknown crosswalk IDs.

## Current release state

- Canonical classification units: 53
- Major groups: 10
- Sub-major groups: 43
- Detailed occupations: 0
- Metric observations: 20
- Published values: 10, all `employment_count`
- Exposure scores: 0
- Model score table: header only

The 53-code classification skeleton remains
`verification_status = unverified_pending_source` because it was derived from
ISCO-aligned documentation rather than imported from the official PSA PSOC
volume/API.

## Remaining work, in priority order

### Phase 2: Philippine-first data foundation

1. **Authoritative detailed PSOC classification**
   - Official API documentation: `https://classification.psa.gov.ph/psoc/swagger/`
   - Access guide: `https://psa.gov.ph/classifications-api/access-guide`
   - The API requires a personal token. No token may be invented, committed,
     logged, or requested through an insecure channel.
   - If the API remains inaccessible, search for an official downloadable PSOC
     2012/2022 volume or official machine-readable alternative. Verify every
     code against the official artifact.
   - Connect the existing importer to the normal build targets and replace the
     provisional ISCO-derived skeleton only after authoritative verification.

2. **SOF 2024 occupation distribution**
   - Exact official Table 2 has already been identified:
     `https://psa.gov.ph/system/files/iesd/TABLE%202.%20Percent%20Distribution%20of%20Overseas%20Filipino%20Workers%20and%20Overseas%20Contract%20Workers%20by%20Sex%2C%20Age%20Group%2C%20Major%20Occupation%2C%20and%20Region%20with%20Measures%20of%20Precision%202024.xlsx`
   - Automated retrieval currently receives a Cloudflare/CDN verification
     response. Use an official browser/manual acquisition path if available,
     then hash and validate the exact workbook.
   - Inspect the real workbook before finalising the parser. Select the all-OFW
     major-occupation slice and publish only the supported conditional:
     `P(occupation | OFW)`. Never relabel it as `P(OFW | occupation)`.
   - Preserve measures of precision where the workbook supplies them.

3. **Occupational wages**
   - Reachability is no longer the issue. The reviewed OWS tables do not supply
     average monthly basic pay by coded occupation at the scope promised by the
     registered metric.
   - Do not use industry pay or the three benchmark occupation categories as a
     substitute for coded occupation pay.
   - Search official PSA material for a genuinely matching table. If none
     exists, leave the metric unavailable and classify that as an evidence
     limitation, not an implementation failure.

4. **Informality**
   - No defensible occupation-level official source has been identified.
   - Do not reintroduce this metric without an exact source, compatible
     denominator, occupational coding, and provenance.

### Phase 3: task-exposure methodology and evidence

1. Obtain published correspondence artifacts for PSOC/ISCO/SOC/O*NET where
   possible. Every edge must identify its source and review status.
2. Do not use title similarity. No observation or task may resolve through a
   rejected or ambiguous edge.
3. Connect real O*NET task statements to canonical detailed PSOC units only
   after the detailed classification and accepted crosswalk exist.
4. Run the guarded scoring harness only when task evidence, model access, and
   required credentials exist. There is currently no usable OpenRouter key.
5. Use at least two successful repeated attempts, retain failures and
   disagreement, write a new immutable run directory, and run the complete
   sensitivity/validation protocol.
6. Independent labour-economist review cannot be simulated. If it has not
   occurred, the phase remains experimental/partially implemented and the
   release must say so.

### Phase 4: integration and final product UI

Do not begin Philippine AI Report integration or another dashboard redesign
until the preceding evidence gates are honestly satisfied or the user makes an
explicit scope decision to ship a narrower evidence product. The eventual UI
should recover the original polished bento interaction model, but it must be
driven exclusively by defensible values and explicit unavailable states.

## Important implementation details and prior defects already fixed

- The original remediation's JSON-stat parser ignored dimension strides.
- CSV parsing forward-filled missing period and classification metadata.
- PSOC 2012 and the 2022 update were silently treated as interchangeable.
- The PSOC importer was disconnected from production builds.
- O*NET codes could not reach canonical PSOC observations.
- Duplicate transformed rows could be overwritten by a dictionary.
- Provenance fields could be empty strings.
- Model run counts could overstate successful attempts.
- Exposure aggregation incorrectly used arithmetic means for ordinal scores.
- Adoption-friction scoring asked a model to invent Philippine conditions.

Do not regress any of these fixes. Relevant tests are in:

- `tests/test_final_remediation.py`
- `tests/test_acquisition_integrity.py`
- `tests/test_populated_pipeline.py`
- `tests/test_validation_suite.py`
- `tests/test_reproducibility.py`
- `tests/test_docs_match_implementation.py`

## Expected working method

1. Read `AGENTS.md`, this handoff, `docs/readiness-report.md`,
   `docs/limitations.md`, `docs/methodology.md`, and the source registry.
2. Reproduce the current release and tests before editing.
3. Research official primary sources before changing source definitions.
4. Prefer exact official files/APIs and record URLs, hashes, retrieval times,
   universes, exclusions, periods, classification versions, and licences.
5. Add real-source integration tests for every new parser and transformation.
6. Treat inaccessible credentials, unavailable official files, and absent
   expert review as explicit blockers. Do not manufacture completion.
7. Regenerate canonical/release artifacts when inputs change.
8. Before any commit run:
   - `make check`
   - `make test`
   - `make test-populated-pipeline`
   - `make check-stale`
   - `make determinism`
   - `git diff --check`
9. Return a phase-by-phase report separating:
   - completed and verified with real primary-source data;
   - implemented but fixture-tested only;
   - partially implemented;
   - externally blocked;
   - rejected as methodologically invalid.

The goal is the most accurate defensible product possible, not the largest
number of populated fields.
