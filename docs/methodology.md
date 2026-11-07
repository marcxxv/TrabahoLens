# Methodology

**For everyone.** TrabahoLens tries to describe Philippine occupations
honestly. That means two things. First, every number tells you what kind of
number it is — a government statistic, something we calculated, an estimate, a
stand-in, or a score produced by an AI model. Second, when there is no good
number, the tool says so instead of showing one anyway.

**For researchers.** This document specifies the canonical schema, the source
hierarchy, the crosswalk policy, the exposure rubric and the validation rules.
Where a decision was contestable, the decision and its reason are stated so you
can disagree with it specifically.

---

## 1. The problem this version exists to fix

The previous version of TrabahoLens published 173 occupations with employment,
wage, informality, overseas-worker, hiring and AI-exposure figures. The
[baseline audit](audit/baseline-audit.md) established that **none of its
published numeric fields was an observed Philippine statistic**. Employment was
a hard-coded group total split across occupations by English keyword matching;
wages and informality were constants per internal category; hiring intensity was
the literal number 50 on every row; the OFW figure was the wrong conditional
probability; and the exposure score came from a single unreplicated model run
under a prompt that stated its own expected average.

The rebuild's rule follows from that: **accuracy and traceability outrank
occupation count, visual impact and feature completeness.** Fewer metrics,
broader groups and more visible gaps are the correct outcome where that is what
the evidence supports.

---

## 2. Canonical data model

### 2.1 PSOC is the key

The canonical identifier is the **Philippine Standard Occupational
Classification (PSOC) 2012** code. v1 keyed on US O\*NET-SOC and attached a PSOC
label afterwards, which meant the *set of occupations that existed* was decided
by a US classification and a keyword-ranking heuristic.

The pinned official 2022 workbook supplies all four hierarchy levels, including
leading-zero armed-forces codes. Imported rows are `verified_against_source`.
The workbook has 466 unique unit codes, while PSA's technical-notes webpage
states 456. We preserve the workbook and disclose this unresolved discrepancy;
we neither guess extra codes nor delete codes to match the webpage count.
Only explicit source-version correspondences may attach statistics to this tree.

### 2.2 Normalised tables, not one wide CSV

Provenance survives only if it travels with the value, so the data is split
into entities rather than flattened:

| Table | What it holds |
| --- | --- |
| `classifications.csv` | The PSOC hierarchy: code, level, title, parent, ISCO equivalent |
| `occupations.csv` | Canonical analysis units keyed by `occupation_id` |
| `metric_observations.csv` | One row per (unit, metric, period), long format |
| `crosswalk_psoc_isco_soc.csv` | Explicit mappings with match type, quality, basis and review status |
| `transformations.csv` | Every transformation applied, by id, including the removed ones |
| `model_scores.csv` | Released exposure scores with full model provenance |

A metric observation carries its own `source_id`, `source_url`,
`source_file_hash`, `retrieved_at`, `reference_period`, `derivation_class`,
`source_authority`,
`confidence_grade`, `source_granularity`, `display_granularity` and
`suppression_status`. The interface receives all of that in the same object as
the value, so a front-end cannot render a number while forgetting its
qualifications.

### 2.3 Metrics are defined before they have values

Each metric is specified up front with its required source, the granularity
that source actually publishes at, its denominator, and the reading it is most
often confused with. Defining metrics first is what lets a release say *this is
blocked* rather than silently omitting it.

### 2.4 Missing is missing

A metric with no value has `metric_value` empty and an `availability` that says
why. It is never filled with zero, a category average, a neighbouring
occupation's figure, or a neutral midpoint. Two validators and one test enforce
this.

---

## 3. Source policy

### 3.1 Hierarchy

1. Philippine Statistics Authority
2. Other Philippine government agencies
3. Official international occupational databases
4. Documented industry administrative data
5. Transparent third-party datasets
6. Model-generated or manually curated inputs

Every source is registered in `data/sources/source-registry.yaml` with its
universe, exclusions, reference period, classification version, redistribution
status, licence and attribution. **A metric whose `source_id` is not in that
registry fails validation.**

### 3.2 Retrieval must be evidenced

`src/trabaholens/v2/acquire.py` records the URL, HTTP status, timestamp, byte
count and SHA-256 of every attempt into `data/sources/retrieval-manifest.json`.
Failures are recorded as failures. Raw files stay out of git; their hashes are
committed, so two people can confirm they hold the same bytes.

Scraping is not used where an official downloadable table or API exists.

### 3.3 What each PSA source can and cannot support

**Labor Force Survey.** A household survey of the population 15 and over. The
occupational granularity that is *publicly* available has not been verified — it
must be read off the tables on retrieval, not assumed. If only major-group
tables exist, employment is published at major-group level and finer
occupations are marked unavailable. **Splitting a group total across detailed
occupations is prohibited**, whatever the weighting scheme.

Where public microdata with survey weights does become available, estimates must
be weighted, standard errors or confidence intervals computed where variance
guidance permits, and cells with inadequate sample support suppressed or
aggregated.

**Occupational Wages Survey.** The 2024 *establishment* survey covers formal
establishments with 10 or more workers, including agriculture. It does not
represent informal-sector, own-account or unpaid family workers, or small
establishments. An OWS wage may therefore **never** be described as the
average earnings of all Filipino workers in an occupation. The wage concept
published (basic pay versus total earnings; average versus median) must be read
off the table and carried into the metric name.

A single wage may be shown against a broad group only when
`source_granularity` is recorded, the interface states the mismatch, and the
row is labelled a proxy with a downgraded confidence grade.

**Survey on Overseas Filipinos.** This is the correction that matters most.

> P(occupation | OFW) is not P(OFW | occupation).

SOF publishes how OFWs are *distributed across* occupation groups. That is
P(occupation | OFW), and it sums to 1. It is **not** the share of an
occupation's workers who are OFWs, P(OFW | occupation), which would need
domestic employment in the same occupation, on a compatible universe, as its
denominator.

v1 published the former under the latter's name. The audit proved it
arithmetically: v1's nine group constants sum to 1.02. v2 publishes only
**"distribution of OFWs by major occupation group"**, with the denominator
stated in the interface. If the compatible denominator ever becomes available,
a within-occupation share becomes a separate metric with its own definition.

**Informality.** "Informal sector" and "informal employment" are distinct
concepts with different counts. Whichever the release uses is quoted, not
paraphrased. If no occupational breakdown exists, the metric stays unavailable.

### 3.4 Sources that are cited but unused

PhilJobNet, IBPAP and POEA were cited in v1's interface and README. None had
any code, data file or URL. All three citations are removed.

They remain in the registry with `status: not_used` and a note on what would be
required to use them: for job postings, the access method, collection dates,
deduplication, occupation coding, regional coverage, expiry handling,
normalisation and the platform-selection bias — and the result would be a
**posting or platform demand signal**, never total hiring demand. For IBPAP,
industry projections stay labelled industry-level. For POEA, the functions moved
to the **Department of Migrant Workers** in 2022, so a current dataset would be
attributed to DMW; no generic attribution is re-added without a named table.

### 3.4a ILOSTAT: the occupation breakdowns PSA does not publish

PSA's public OpenSTAT tables give employment by the ten major groups only, with
no table of pay, education or informality by occupation. The International
Labour Organization re-tabulates the same Philippine Labor Force Survey
microdata (its record says "LFS - Labour Force Survey ... Micro data
processing") and publishes it through the open ILOSTAT SDMX API. The ILO states
its datasets are CC BY 4.0. Four pinned extracts are registered, each retrieved
by `make fetch-data`, hash-verified, and parsed by `v2/sources/ilo.py`:

* `employment_count_subgroup`: employed persons by the 43 sub-major groups
  (ISCO-08 level 2), 2024 annual.
* `earnings_monthly_mean` and `earnings_monthly_median`: monthly earnings of
  **employees only** by major group, 2024 annual, Philippine pesos.
* `education_advanced_share`: the share of employed persons with advanced
  (tertiary) attainment by major group. It is **calculated** here from published
  counts, after checking that the four education aggregates add to the total.

Rules that keep this honest:

* **It is not PSA's figure.** The ILO's 2024 employed total is 47,524 thousand;
  PSA's is 48,841 thousand (about 2.7% apart). The two are different processings
  of one survey. They are never added together or compared cell by cell, and the
  interface names the ILO as the source of these layers.
* **Classification.** ISCO-08 levels 1 and 2 map to the PSOC major and
  sub-major group with the same code. That is structural (PSOC 2012 is built on
  ISCO-08), and the build confirms it: a crosswalk row is marked
  `source_verified` only when its code appears in the hash-verified ILO file, and
  a test compares the code sets (10 major, 43 sub-major) with the PSA workbook.
* **Employees only.** Earnings exclude own-account workers and employers.
* `vulnerable_employment_share`: own-account plus contributing family workers
  over all employed persons by major group (the ILO's "vulnerable employment"),
  calculated after checking that the status categories add to the total.
* **No informal-employment layer.** ILOSTAT holds no Philippine series of
  informal employment by occupation (every such dataflow returns no data for the
  Philippines), and PSA publishes none. The layer stays unavailable. The
  own-account and family share above is **not** informal employment and is never
  presented as it: many own-account workers run registered businesses and many
  employees hold informal jobs.

### 3.5 O\*NET

O\*NET is used for occupational descriptions, task statements, task importance
and frequency, and Job Zones. It is a **US** product describing US occupations.

Every O\*NET-derived value is labelled a US-derived proxy and carries the
quality of the crosswalk that brought it across. Task profiles are not
transferred to a Philippine occupation without that label.

---

## 4. Crosswalks

Every mapping row records `crosswalk_id`, `psoc_code`, `source_code`,
`source_classification`, `match_type`, `match_quality`, `mapping_basis`,
`review_status` and both cardinality flags.

`match_type` ∈ {exact, close, broader, narrower, composite, no_defensible_match}.

**Mapping on title similarity alone is not permitted.** A row whose
`mapping_basis` is `title_similarity_only` must carry `review_status =
rejected`, enforced by a validator. Observations may not resolve through a
rejected crosswalk.

Cardinality flags are **derived from the table**, never hand-set, so they cannot
drift from what the table contains.

v1's SOC→PSOC mapping is preserved in the crosswalk table with
`mapping_basis = undocumented_heuristic` and `review_status = rejected`. It is
recorded so the break with it is auditable, not so anything can use it.

---

## 5. Generative-AI task exposure

### 5.1 What it is, and what it is not

> Generative-AI task exposure indicates how much an occupation's tasks may be
> affected or assisted by generative AI. It is not an estimate of automation,
> displacement, layoffs, or future employment.

That sentence is fixed beside the exposure layer in the interface. It is not in
a collapsible methodology section, because a caveat nobody opens is not a
caveat.

Exposure is **not** automation probability, replacement probability,
displacement, layoffs, unemployment, job-loss risk, occupational decline, or
future employment change. Employment outcomes depend on adoption, costs,
regulation, demand, productivity, task reorganisation, worker adaptation,
institutional capacity, and the creation of new work. None of that is measured
here.

### 5.2 Four dimensions, never combined

| | Dimension | Scale | Who scores it |
| --- | --- | --- | --- |
| A | Technical task exposure | 0–5 ordinal | the model |
| B | Human-interaction and physical-presence intensity | 0–5 ordinal | the model |
| ~~C~~ | ~~Adoption-friction context~~ | — | **removed in rubric v0.2.0** |
| ~~D~~ | ~~Evidence confidence~~ | 0–5 | **computed from provenance** |

The rubric **prohibits** combining them. Any weighted sum would read as a
job-loss probability, which is exactly what this measure refuses to produce.

**C was removed, not deferred.** v0.1.0 asked the model to judge Philippine
regulation, liability, connectivity, device access, employer scale and
informality while supplying no Philippine evidence for any of it. A model
inferring those conditions from an occupation title or a US task statement is
inventing them. Adoption friction is redefined as a future evidence-based
Philippine contextual layer and is unpublished until that evidence exists.

**D is computed, not asked.** Everything it depends on — task source, task
completeness, crosswalk quality and match type, Philippine specificity, human
review status, successful-attempt coverage — is metadata the pipeline holds.
Asking the scoring model to grade its own reliability conflates a measurement
with its evaluation. The component reasons are published alongside the grade.

B is not the inverse of A: a task can be both text-mediated and deeply
relational. C is contextual judgement, the most speculative dimension, and is
published as such. D is how much the scorer should be trusted given the task
evidence and the crosswalk behind it.

Dimension A tops out at "can perform most of the task content, subject to
verification, accountability and workflow integration" rather than at "fully
automated" — because verification and accountability are not optional in real
work, and a scale that ignored them would systematically overstate exposure.

### 5.3 Task-first

The unit of analysis is the **task statement**, not the occupation title. Task
scores aggregate to occupations two ways — unweighted, and weighted by task
importance where the source publishes importance ratings. Both are published
side by side. Neither is presented as *the* score, and they are never averaged
together.

Employment, wages, OFW share and informality are **prohibited inputs**. They are
not evidence of what a model can do with a task. The harness refuses at runtime
to send them, rather than merely documenting that it shouldn't.

### 5.4 Model procedure

Versioned prompt and rubric. Recorded provider, model id, resolved model id,
provider request id, scoring date, temperature and aggregation method.

**The unit of record is the attempt, not the run.** Every call produces a record
— status, timestamps, full request payload, raw response where one exists,
parser status, structured error — and all of them are written, successful or
not. Counts are derived from attempts that actually **succeeded**. A task below
the configured minimum number of successes is excluded from publication and
named. Before remediation the harness recorded the *requested* count and dropped
failures, so one success out of three published as three runs.

**These are repeated scoring attempts, not independent replicates.** Each task is
a separate chat request, so randomising task order cannot test within-prompt
ordering effects — there is no shared prompt to order, and that shuffle has been
removed rather than relabelled. At temperature 0 repeated calls measure
run-to-run reproducibility and provider variability. Genuine perturbation
testing would require paraphrased task statements, rubric-anchor reordering,
deterministic prompt variants, multiple models or multiple scoring dates; those
are specified as future work and are not claimed.

Each invocation writes a new run directory with a collision-resistant id;
history is never overwritten.

The prompt states no expected distribution. v1's `Expected average: ~3.5-4.5`
anchored its own output before the model saw an occupation; the harness now
**refuses to run** a prompt containing such an instruction.

### 5.5 Validation status

**This experimental score has not yet undergone independent labour-economist
validation.**

A model's rationale is not validation — it is an artifact of the same process
that produced the score, and the interface presents it as "the scoring model
judged", never as a finding.

The planned validation battery (face validity, prompt-wording sensitivity,
repeat-run stability, cross-model comparison, task-weighting sensitivity,
crosswalk-quality sensitivity, comparison with an established methodology, and
error analysis for Philippine-specific, physical and mixed occupations) is
specified in [`sensitivity-report.md`](sensitivity-report.md), which currently
reports that no run exists.

---

## 6. Evidence classification

Every published metric declares itself as exactly one of:

| Class | Meaning |
| --- | --- |
| Official statistic | Published by an official statistical agency, at the granularity that agency published it |
| Calculated statistic | Arithmetic we performed on official figures; inputs official, calculation ours and documented |
| Estimate | A modelled or survey-weighted value with sampling uncertainty, with an interval where the source supports one |
| Proxy | Measured on a different population, place or unit than the one shown |
| Experimental model-derived score | Produced by a language model under a published rubric |

Each has a plain-language tooltip in the interface. `confidence_grade` A–E runs
alongside and records *why* — matching granularity, published uncertainty,
transformation distance, or model-derived.

A value from a broader source shown at a finer level cannot be an official
statistic and cannot hold confidence grade A or B. It is a proxy, graded down,
with the mismatch shown.

---

## 7. Reproducibility

Builds are deterministic given fixed inputs; `make determinism` proves two
builds are byte-identical. Dependencies are locked. Canonical table checksums
are recorded in the release manifest, and `make check-stale` — run in CI — fails
if a committed artifact no longer matches what the committed inputs produce.

That check deliberately ignores four **build-time stamps**: `code_commit`,
`repository_commit`, `release_date` and `generated_at`. They record when and
where a build ran, not what it consumed. `code_commit` is also self-referential
— the manifest records HEAD, and committing the manifest moves HEAD — so a
plain `git diff` after a rebuild could never pass, and a check that cannot pass
is a check people learn to ignore. Everything else must match exactly, and a
test asserts the exclusion list stays limited to those four. No secret appears in the repository, and a test
scans tracked files for credential patterns.

The release manifest records the release id and date, code commit, schema,
methodology, crosswalk, rubric and prompt versions, per-source retrieval state
and hashes, canonical table checksums, model runs, and known limitations.

---

## 8. The pipeline, stage by stage

A value must pass through every stage below. It may not skip one, and a stage
that has only ever seen a fixture may not back a published number — that rule is
enforced by a validator, not by convention.

```
source registry (configuration)
  -> retrieval attempt            -> retrieval manifest entry + SHA-256
  -> immutable raw snapshot
  -> hash verification            (bytes still match what was recorded)
  -> format validation            (is this the shape the parser expects)
  -> source-specific parser       -> normalised source rows, in the SOURCE's codes
  -> classification reconciliation (version compatible? code known?)
  -> documented transformation
  -> canonical metric observation
  -> release validation
  -> site payload
```

**The registry is configuration; the manifest is evidence.** Publication state is
derived from a verified manifest entry, never from a hand-edited registry field.
Before remediation, flipping one word in the registry YAML produced rows marked
`availability=published` with an empty value, hash and reference period.

Per-stage status is machine-readable in `data/release/manifest.json` under
`pipeline_stages`, rendered in the interface, and classified as one of:
implemented and verified with a real source · implemented but fixture-tested
only · partially implemented · designed, not implemented · blocked by source
access · blocked by unresolved methodology · awaiting human review · rejected.

### Classification version safety

A source declares which PSOC version it used. If that version is not one this
project can reconcile, the rows are **refused** rather than renumbered. The
canonical version is the 2022 Updates to the 2012 PSOC; the architecture
decision behind choosing one canonical version over parallel versioned trees is
argued in `src/trabaholens/v2/sources/psoc_importer.py`.

## 9. What this release publishes

The release publishes ten 2024 annual LFS employment estimates, one for each
PSOC major group. PSA matrix 1B3FEMP4 is queried for one annual slice, stored as
a hash-verified JSON-stat snapshot, normalized from thousands to persons, and
reconciled through an explicit PSOC 2012-to-2022 major-group correspondence.

ILOSTAT adds 83 values from five pinned extracts (see 3.4a): 43 sub-major
employment counts, ten mean and ten median monthly earnings of employees, ten
advanced-education shares and ten own-account and family work shares. They are labelled as ILO-processed everywhere.

SOF Table 2 adds nine published occupation shares with their standard errors
and CVs. The blank armed-forces share remains missing. Percentages and standard
errors are divided by 100; there is no renormalisation or domestic denominator.

OWS Table 1 supplies 693 occupation-by-industry records in a separate source-native
reference table. Nine inconsistent confidence intervals are quarantined;
684 wage-rate estimates remain available with precision warnings. These include
regular cash allowances, are not basic pay alone, and are not reconciled to
canonical PSOC. Box areas are equal record weights, never inferred employment.
O*NET 31.0 produces no Philippine metric without an accepted correspondence. See
[`readiness-report.md`](readiness-report.md) for the per-phase classification.

That the pipeline works is demonstrated rather than asserted:
`make test-populated-pipeline` continues to drive controlled fixtures through
every stage, while the production LFS path now proves a real populated
observation reaches the payload with full provenance. Separate JSON-stat tests
exercise both official wrapper variants, positional categories and unit
normalization; mutation tests prove malformed inputs cannot publish.
