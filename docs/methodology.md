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

PSOC 2012 is built on ISCO-08. This release carries its 10 major groups and 43
sub-major groups. Major group 0 (Armed Forces Occupations) and major group 9
(Elementary Occupations) are both present; v1 omitted 0 entirely and could reach
9 only through three hand-written records.

**Minor (3-digit) and unit (4-digit) groups are deliberately absent.** The
authoritative PSA volume could not be retrieved in this environment, and PSOC
2012 departs from ISCO-08 at finer levels in ways this project cannot guess.
Guessing them would recreate the defect the rebuild exists to remove.

Every classification row is marked `verification_status =
unverified_pending_source`. A validator fails the build if any row loses that
marker before someone diffs the list against the PSA volume.

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
`source_file_hash`, `retrieved_at`, `reference_period`, `estimate_type`,
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

**Occupational Wages Survey.** An *establishment* survey covering
non-agricultural establishments at or above an employment threshold. It excludes
agriculture, small establishments, informal-sector workers, own-account and
self-employed workers, and unpaid family workers — exclusions that are large in
the Philippine context. An OWS wage may therefore **never** be described as the
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

| | Dimension | Scale |
| --- | --- | --- |
| A | Technical task exposure | 0–5 |
| B | Human-interaction and physical-presence intensity | 0–5 |
| C | Adoption-friction context | 0–5 |
| D | Evidence confidence | 0–5 |

The rubric **prohibits** combining them. Any weighted sum would read as a
job-loss probability, which is exactly what this measure refuses to produce.

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

Versioned prompt and rubric. Recorded provider, model id, snapshot, scoring
date, temperature, run count and aggregation method. **At least two
replicates** — a single run cannot report its own stability, and the harness
refuses `--runs 1`. Task order is randomised per replicate so ordering effects
surface as between-replicate disagreement instead of hiding inside one order.
Every raw response is retained. Each invocation writes a new run directory;
history is never overwritten.

Consensus is the median. **Disagreement is retained and published**, not
smoothed away.

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

## 8. What this release publishes

**No metric values.** Every PSA host, `www.onetcenter.org` and `openrouter.ai`
returned HTTP 403 at the build environment's egress proxy, and
`OPENROUTER_API_KEY` is unset. The dated attempts are in
`data/sources/retrieval-manifest.json`.

So the release contains the PSOC structure, the metric definitions, the source
registry, the crosswalk, the validation rules and the interface — and 30 metric
observations that each carry an empty value and an explicit
`blocked_pending_source`.

That is the honest state. The alternative — carrying v1's numbers forward while
the machinery around them improved — would have produced a more impressive
dashboard making the same false claims.
