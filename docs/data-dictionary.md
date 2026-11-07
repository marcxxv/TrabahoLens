# Data dictionary

Every field in every published table and in the site payload.

**Plain-language summary.** Each row of data carries not just a number but the
story of that number: which agency published it, which table it came from, what
period it covers, how sure we are, and whether it describes exactly the
occupation shown or something broader. The columns below are that story.

---

## Controlled vocabularies

### `derivation_class` — how the number was produced

This is one of **two independent axes**. It answers *how*, never *who*.

| Value | Label shown | Meaning |
| --- | --- | --- |
| `directly_observed` | Directly observed | A complete enumeration or administrative record — every unit counted, not a sample. Census and register counts qualify; sample surveys do not. |
| `calculated` | Calculated | Arithmetic we performed on published figures. Documented, and inherits its inputs' uncertainty. |
| `estimated` | Estimated | Produced from a sample and generalised to a population, so it carries sampling error. **Most official labour statistics are of this kind.** |
| `proxy_derived` | Proxy-derived | Measured on a different population, place or unit than the one shown, carried across by a documented mapping. |
| `model_derived` | Model-derived | Produced by a model following a published rubric. A research signal, not an observation. |

### `source_authority` — who produced it

The second axis. It answers *who*, never *how*.

| Value | Label shown | Meaning |
| --- | --- | --- |
| `ph_official_statistical_authority` | Philippine official statistical authority | PSA or another body designated to produce official Philippine statistics. |
| `ph_government_other` | Other Philippine government source | A Philippine government body publishing administrative or programme data. |
| `international_official_occupational` | International official occupational source | An official occupational database from a government outside the Philippines, or an international organisation. |
| `industry_administrative` | Industry or administrative source | An industry association or private administrative dataset. |
| `project_generated` | Project-generated research output | Produced by this project; not independent of its own assumptions. |

**Why two axes.** The pre-remediation schema had one field, `estimate_type`,
and put `official_statistic` on the LFS, OWS and SOF metrics. That conflated
two unrelated questions. PSA publishing a figure makes it an official
statistic; it does not make it directly observed, because LFS, OWS and SOF are
sample surveys whose figures carry sampling error. Both facts are true at once
and neither implies the other, so they are separate fields and the interface
shows both.

Under the current classification **no metric is `directly_observed`**, and that
is the correct state rather than a gap to be filled.

### `availability` — whether there is a value at all

| Value | Meaning |
| --- | --- |
| `published` | A value is available and shown. |
| `blocked_pending_source` | The metric is defined and its source identified, but the source has not been retrieved. No value exists to show. |
| `suppressed_low_sample` | Withheld because the sample behind it is too small to publish. |
| `not_applicable` | The metric does not apply to this occupation. |
| `withdrawn_unsupported` | Published in a previous version and withdrawn because no evidence supported it. |

### `confidence_grade`

| Grade | Meaning |
| --- | --- |
| A | Official source, matching granularity, sampling error published. |
| B | Official source, matching granularity, uncertainty not published. |
| C | Official source published coarser than displayed, or a non-trivial transformation stands between source and display. |
| D | Non-official or proxy source, or a source specified but not yet retrieved and verified. |
| E | Model-derived, experimental. No observational backing. |

### `source_granularity` / `display_granularity`

Ordered coarse to fine: `national`, `psoc_major_group`,
`psoc_sub_major_group`, `psoc_minor_group`, `psoc_unit_group`, `occupation`.

When source is coarser than display, `granularity_mismatch` is true in the
payload and the interface says so. Such a row cannot be an `official_statistic`
and cannot hold grade A or B.

### `suppression_status`

`not_suppressed` · `suppressed_low_sample` · `suppressed_by_publisher` ·
`no_value_yet`

### `verification_status` (classifications and occupations)

| Value | Meaning |
| --- | --- |
| `verified_against_source` | Checked line by line against a retrieved authoritative source file. |
| `unverified_pending_source` | Entered from classification documentation; the authoritative file has not been retrieved. Publishable only while carrying this marker. |

### Crosswalk vocabularies

`match_type` — `exact` · `close` · `broader` · `narrower` · `composite` ·
`no_defensible_match`

`match_quality` — `high` · `medium` · `low` · `none`

`mapping_basis` — `published_correspondence` · `structural_derivation` ·
`definition_review` · `title_similarity_only` · `undocumented_heuristic`

`review_status` — `unreviewed` · `machine_proposed` · `human_reviewed` ·
`rejected`

Impossible combinations rejected by validation: `no_defensible_match` with any
quality other than `none`; `exact` with quality `low`; `title_similarity_only`
with any status other than `rejected`.

---

## `data/canonical/classifications.csv`

| Column | Description |
| --- | --- |
| `psoc_code` | PSOC code. 1 digit = major group, 2 digits = sub-major group. |
| `psoc_version` | Classification version, e.g. `PSOC 2012`. |
| `level` | `psoc_major_group` or `psoc_sub_major_group`. |
| `title` | Official group title. |
| `parent_psoc_code` | Parent code; empty for a major group. |
| `psoc_major` | Major group digit this row sits under. |
| `psoc_major_label` | Major group title. |
| `isco08_code` | Corresponding ISCO-08 code. |
| `source_organization` / `source_dataset` / `source_url` | Where the list should come from. |
| `verification_status` | See above. Official-workbook imports are `verified_against_source`; unavailable-source fallback rows remain unverified. |
| `notes` | Why, and what must be done to change it. |

## `data/canonical/occupations.csv`

| Column | Description |
| --- | --- |
| `occupation_id` | Canonical key, `PSOC-<code>`. |
| `psoc_code`, `psoc_version`, `parent_psoc_code`, `psoc_major`, `psoc_major_label` | As above. |
| `occupation_title` | Title of the unit. |
| `occupation_level` | Granularity of this unit. |
| `is_aggregate` | `true` when the unit is a group rather than a detailed occupation. Every unit in this release is an aggregate. |
| `verification_status` | See above. |
| `notes` | Free text. |

## `data/canonical/metric_observations.csv`

One row per (occupation unit, metric, reference period).

| Column | Description |
| --- | --- |
| `observation_id` | `<metric_id>:<psoc_code>`. Unique. |
| `occupation_id`, `psoc_code` | The unit this describes. |
| `metric_id`, `metric_name` | Which metric. |
| `metric_value` | The value, **or empty**. Never zero-filled, never a midpoint. |
| `unit` | e.g. `persons`, `PHP per month`, `share of all OFWs`. |
| `reference_period` | Survey round or year. Required for any published value. |
| `geography` | Coverage. |
| `population_scope` | The denominator or universe. |
| `derivation_class`, `source_authority` | Independent axes describing how the value was produced and who published its source. |
| `availability` | See above. |
| `source_granularity` / `display_granularity` | See above. |
| `source_id` | Must exist in the source registry. |
| `source_organization`, `source_dataset`, `source_table`, `source_url` | Attribution and locator. |
| `source_file_hash` | SHA-256 of the retrieved file. Required for any published value. |
| `retrieved_at` | Retrieval timestamp. Required for any published value. |
| `transformation_id` | Which transformation produced the value. |
| `crosswalk_id` | Which mapping it resolved through, if any. May not reference a rejected crosswalk. |
| `confidence_grade` | See above. |
| `uncertainty_lower` / `uncertainty_upper` | Interval bounds where the source supports them. |
| `standard_error` | Publisher's standard error in the same unit as the metric; null when absent. |
| `coefficient_of_variation` | Publisher's CV in percent, not a 0–1 share. Above 10% requires grade D and a caution. |
| `suppression_status` | See above. |
| `notes` | Including, for a blocked row, why it is blocked and the reading to avoid. |

## Metric ids

| `metric_id` | Name | Unit | Source | Published at |
| --- | --- | --- | --- | --- |
| `employment_count` | Employed persons | persons | PSA LFS | PSOC major group |
| `wage_basic_pay` | Average monthly basic pay, OWS establishments | PHP/month | PSA OWS | occupation |
| `ofw_distribution_share` | Distribution of OFWs by major occupation group | share of all OFWs | PSA SOF | PSOC major group |
| `onet_job_zone` | O\*NET Job Zone (US) | ordinal 1–5 | O\*NET | occupation |
| `gen_ai_task_exposure` | Generative-AI technical task exposure | 0–5 rubric score | LLM scoring | occupation |

`gen_ai_task_exposure` is the only metric that is not an observation. It is an
`experimental_model_score` produced under a versioned rubric and prompt, and it
is stored in `model_scores.csv` with separate dimensions and provenance rather
than as a single value. **It is not automation probability, replacement
probability, displacement, job loss, or any forecast of employment change.**

The full definition of each metric — including its denominator and the reading
it is most often confused with — lives in `v2/schema.py` and is carried into the
site payload under `metrics`.

### Source-native wage references

`data/reference/ows_wage_benchmarks.csv` and payload `wage_references` retain
OWS job-position × industry observations outside canonical PSOC. Each row has
the standard provenance axes plus `source_code`, `industry_code`, `industry`,
`source_occupation`, `population_scope`, table/cell reference, 90% interval,
SE, CV and `classification_reconciliation=unmapped_source_native`.
`blocked_source_inconsistency` rows carry null values and an explanation.
`value` is a mean monthly wage rate including regular cash allowances, not the
unavailable `wage_basic_pay` metric. No cross-industry mean is published.

---

## `data/canonical/crosswalk_psoc_isco_soc.csv`

| Column | Description |
| --- | --- |
| `crosswalk_id` | Unique id. |
| `psoc_code`, `psoc_version` | Philippine side. |
| `source_code`, `source_classification` | Other side, e.g. ISCO-08 or US SOC. |
| `match_type`, `match_quality`, `mapping_basis`, `review_status` | See above. |
| `is_one_to_many` | This PSOC code maps to more than one source code. **Derived.** |
| `is_many_to_one` | This source code is mapped to by more than one PSOC code. **Derived.** |
| `notes` | Reasoning, caveats, or why the row is rejected. |

## `data/canonical/transformations.csv`

| Column | Description |
| --- | --- |
| `transformation_id` | Stable id; `T-9xx` ids are **removed** transformations, recorded so their removal is explicit. |
| `name`, `description` | What it does. |
| `inputs`, `outputs` | What it consumes and produces. |
| `code_reference` | Where it is implemented. |
| `reversible` | Whether the original value can be recovered. |
| `notes` | Constraints and prohibitions. |

## `data/canonical/model_scores.csv`

| Column | Description |
| --- | --- |
| `score_id` | `<run_id>:<psoc_code>:<dimension>:<aggregation>`. |
| `occupation_id`, `psoc_code` | The unit scored. |
| `dimension` | `A`, `B`, `C` or `D`. Never combined. |
| `rubric_version`, `prompt_version` | Versioned artifacts under `data/exposure/`. |
| `model_provider`, `model_id`, `model_release_or_snapshot` | Exactly which model. |
| `scoring_date`, `temperature`, `run_count` | Run parameters. `run_count` must be ≥ 2. |
| `aggregation_method` | Ordinal median across tasks, with category distribution and IQR. |
| `task_source`, `task_weighting` | Where the tasks came from and how they were weighted. |
| `crosswalk_quality` | Quality of the mapping that brought the tasks across. |
| `score`, `score_scale_min`, `score_scale_max` | The value and its scale. |
| `uncertainty_or_stability` | Cross-run standard deviation. |
| `run_disagreement_range` | Widest disagreement between repeated attempts. Retained, not smoothed. |
| `human_review_status` | Whether a person has reviewed it. |
| `limitations` | Including the no-independent-validation statement. |
| `raw_response_reference` | Path to the run record holding the raw responses. |

---

## Site payload — `site/data.json`

Top level: `schema`, `release`, `disclaimers`, `derivation_class_legend`,
`source_authority_legend`, `confidence_grade_legend`, `availability_legend`, `metrics`, `counts`,
`occupations`.

`counts` is **derived at build time** — `occupations`, `psoc_major_groups`,
`psoc_sub_major_groups`, `metrics_defined`, `metric_observations`,
`published_values`, `exposure_scores`. The interface reads these; no count is
hard-coded anywhere, and a validator rejects any literal occupation count in
the markup.

Each `occupations[]` entry carries `occupation_id`, `psoc_code`,
`psoc_version`, `title`, `level`, `parent_psoc_code`, `psoc_major`,
`psoc_major_label`, `is_aggregate`, `verification_status`, a `metrics` object
and an `exposure` array.

Each `metrics` entry contains `value` (**`null` when unavailable**), `unit`,
`derivation_class`, `derivation_class_label`, `source_authority`,
`source_authority_label`, `availability`, `confidence_grade`,
`reference_period`, `geography`, `population_scope`, `source_granularity`,
`display_granularity`, `granularity_mismatch`, `source_id`,
`source_organization`, `source_dataset`, `source_url`, `source_file_hash`,
`retrieved_at`, `uncertainty_lower`, `uncertainty_upper`,
`suppression_status`, `common_misreading` and `notes`.

Provenance is in the same object as the value by design: the interface cannot
render a number without having been handed what qualifies it.

---

## Fields that existed in v1 and no longer exist

| v1 field | Status | Why |
| --- | --- | --- |
| `jobs` / `employment_estimate` | **Removed** | Hard-coded group total split by English title keywords; 43 distinct values across 173 rows. |
| `pay` / `avg_monthly_wage_php` | **Removed** | Constant per internal category; 11 distinct values across 173 rows. |
| `outlook` / `hiring_intensity` | **Removed** | Literal `50` on every row, attributed to PhilJobNet, which the repository never touched. |
| `informal_share` | **Removed** | Constant per internal category; no source, no definition. |
| `ofw_share` | **Replaced** | Was P(occupation\|OFW) published as P(OFW\|occupation). Replaced by `ofw_distribution_share`. |
| `exposure` (0–10) | **Replaced** | Single unreplicated run under a distribution-anchoring prompt. Replaced by two separate model-scored 0–5 dimensions plus computed provenance confidence. |
| `exposure_rationale` | **Removed as published fact** | Model text shown as explanation. Returns only under a model-derived badge and "the scoring model judged" framing. |
| `primary_risk_vector` | **Removed** | Hazard vocabulary. Replaced by `ai_can_assist_with` / `remains_human_dependent`. |
| `category` | **Removed** | An internal 22-bucket string that drove the wage and informality constants; not a classification. |
| `source` (`onet`/`ph_native`) | **Removed** | Described which code branch ran, not where a number came from. |
| `education` (O\*NET Job Zone) | **Retained, relabelled** | Real and citable, but a US construct. Now `onet_job_zone`, explicitly a US-derived proxy, with no silent default. |

The withdrawn values remain readable in `data/legacy/v1/` as evidence about v1.
