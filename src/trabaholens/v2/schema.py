"""Canonical v2 schema: controlled vocabularies and table definitions.

Everything the release publishes is validated against this module. The
vocabularies are deliberately small and closed — an unrecognised value is a
build failure, not a pass-through.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "2.0.0"

# --------------------------------------------------------------------------
# Evidence classification — TWO INDEPENDENT AXES
# --------------------------------------------------------------------------
# The previous version had one axis and put `official_statistic` on LFS, OWS and
# SOF figures. That conflated two unrelated questions:
#
#   * WHO produced it        -> source_authority
#   * HOW it was produced    -> derivation_class
#
# PSA publishing a number makes it an official statistic. It does not make it
# directly observed: LFS, OWS and SOF are sample surveys, so their figures are
# *estimates* with sampling error, published by an official authority. Both
# facts are true at once and neither implies the other, so they are separate
# fields and the interface shows both.

DERIVATION_CLASSES = {
    "directly_observed": (
        "Directly observed",
        "A complete enumeration or administrative record of the population "
        "concerned — every unit counted, not a sample. Census and register "
        "counts qualify; sample surveys do not.",
    ),
    "calculated": (
        "Calculated",
        "Arithmetic we performed on published figures — a share, a rate, a sum. "
        "The calculation is ours and is documented; it inherits the uncertainty "
        "of its inputs.",
    ),
    "estimated": (
        "Estimated",
        "Produced from a sample and generalised to a population, so it carries "
        "sampling error. Reported with an interval wherever the source "
        "publishes one. Most official labour statistics are of this kind.",
    ),
    "proxy_derived": (
        "Proxy-derived",
        "Measured on a different population, place or unit than the one shown, "
        "and carried across by a documented mapping. An indication, not a "
        "measurement of this occupation in the Philippines.",
    ),
    "model_derived": (
        "Model-derived",
        "Produced by a model following a published rubric. A research signal, "
        "not an observation.",
    ),
}

SOURCE_AUTHORITIES = {
    "ph_official_statistical_authority": (
        "Philippine official statistical authority",
        "The Philippine Statistics Authority or another body designated to "
        "produce official Philippine statistics.",
    ),
    "ph_government_other": (
        "Other Philippine government source",
        "A Philippine government body publishing administrative or programme "
        "data that is not an official statistical series.",
    ),
    "international_official_occupational": (
        "International official occupational source",
        "An official occupational database maintained by a government outside "
        "the Philippines, or by an international organisation.",
    ),
    "industry_administrative": (
        "Industry or administrative source",
        "An industry association or private administrative dataset.",
    ),
    "project_generated": (
        "Project-generated research output",
        "Produced by this project. Not an external source, and not independent "
        "of the project's own assumptions.",
    ),
}

# Retained only to describe what v1 and the pre-remediation v2 published, so the
# audit can name the old class. Never written to a new row.
LEGACY_ESTIMATE_TYPES = {
    "official_statistic",
    "calculated_statistic",
    "estimate",
    "proxy",
    "experimental_model_score",
}

# Availability is orthogonal to estimate type. A metric can be well specified
# and still have no value, which is the normal state of this release.
AVAILABILITY = {
    "published",
    "blocked_pending_source",
    "suppressed_low_sample",
    "not_applicable",
    "withdrawn_unsupported",
}

CONFIDENCE_GRADES = {
    "A": "Official source, matching granularity, sampling error published.",
    "B": "Official source, matching granularity, uncertainty not published.",
    "C": "Official source, but published coarser than displayed, or a "
         "non-trivial transformation stands between source and display.",
    "D": "Non-official or proxy source, or a source we have specified but not "
         "yet retrieved and verified.",
    "E": "Model-derived, experimental. No observational backing.",
}

GRANULARITIES = [
    "national",
    "psoc_major_group",
    "psoc_sub_major_group",
    "psoc_minor_group",
    "psoc_unit_group",
    "occupation",
]

SUPPRESSION_STATUS = {
    "not_suppressed",
    "suppressed_low_sample",
    "suppressed_by_publisher",
    "no_value_yet",
}

VERIFICATION_STATUS = {
    # Checked line-by-line against a retrieved authoritative source file.
    "verified_against_source",
    # Entered from classification documentation; the authoritative file has not
    # been retrieved in this environment. Publishable only while carrying this
    # marker.
    "unverified_pending_source",
}

# --------------------------------------------------------------------------
# Crosswalk vocabulary
# --------------------------------------------------------------------------

MATCH_TYPES = {
    "exact",
    "close",
    "broader",
    "narrower",
    "composite",
    "no_defensible_match",
}

MATCH_QUALITY = {"high", "medium", "low", "none"}

MAPPING_BASIS = {
    # The classifications are documented as corresponding.
    "published_correspondence",
    # Structural derivation: PSOC 2012 is built on ISCO-08, so the major and
    # sub-major group skeletons correspond by construction.
    "structural_derivation",
    # A human read both definitions and judged the relationship.
    "definition_review",
    # Explicitly recorded so it can be rejected by a validator.
    "title_similarity_only",
    # An undocumented hand-tuned mapping, e.g. inherited from v1. Recorded so
    # it stays reviewable, never so it can be used.
    "undocumented_heuristic",
}

REVIEW_STATUS = {"unreviewed", "machine_proposed", "human_reviewed", "rejected"}

# --------------------------------------------------------------------------
# Table column orders
# --------------------------------------------------------------------------

CLASSIFICATIONS_COLUMNS = [
    "psoc_code",
    "psoc_version",
    "level",
    "title",
    "parent_psoc_code",
    "psoc_major",
    "psoc_major_label",
    "isco08_code",
    "source_organization",
    "source_dataset",
    "source_url",
    "verification_status",
    "notes",
]

OCCUPATIONS_COLUMNS = [
    "occupation_id",
    "psoc_code",
    "psoc_version",
    "occupation_title",
    "occupation_level",
    "parent_psoc_code",
    "psoc_major",
    "psoc_major_label",
    "is_aggregate",
    "verification_status",
    "notes",
]

METRIC_OBSERVATIONS_COLUMNS = [
    "observation_id",
    "occupation_id",
    "psoc_code",
    "metric_id",
    "metric_name",
    "metric_value",
    "unit",
    "reference_period",
    "geography",
    "population_scope",
    # Two independent axes; see DERIVATION_CLASSES / SOURCE_AUTHORITIES.
    "derivation_class",
    "source_authority",
    "availability",
    "source_granularity",
    "display_granularity",
    "source_id",
    "source_organization",
    "source_dataset",
    "source_table",
    "source_url",
    "source_file_hash",
    "retrieved_at",
    "parser_id",
    "parser_version",
    "normalised_row_id",
    "transformation_id",
    "crosswalk_id",
    "confidence_grade",
    "confidence_reasons",
    "pipeline_status",
    "uncertainty_lower",
    "uncertainty_upper",
    "suppression_status",
    "notes",
]

# Cardinality flag semantics, shared by the builder and the validator:
#   is_one_to_many - this psoc_code maps to more than one source_code
#   is_many_to_one - this source_code is mapped to by more than one psoc_code
# Both are derived from the table, never hand-set.
CROSSWALK_COLUMNS = [
    "crosswalk_id",
    "psoc_code",
    "psoc_version",
    "source_code",
    "source_classification",
    "match_type",
    "match_quality",
    "mapping_basis",
    "review_status",
    "is_one_to_many",
    "is_many_to_one",
    "notes",
]

TRANSFORMATIONS_COLUMNS = [
    "transformation_id",
    "name",
    "description",
    "inputs",
    "outputs",
    "code_reference",
    "reversible",
    "notes",
]

MODEL_SCORES_COLUMNS = [
    "score_id",
    "occupation_id",
    "psoc_code",
    "dimension",
    "rubric_version",
    "prompt_version",
    "model_provider",
    "model_id",
    "model_release_or_snapshot",
    "scoring_date",
    "temperature",
    "run_count",
    # Attempt accounting: what was tried versus what actually succeeded. The
    # previous schema recorded only the requested count, so one success out of
    # three attempts published as "3 runs".
    "attempted_attempts",
    "successful_attempts",
    "aggregation_method",
    "task_source",
    "task_weighting",
    "tasks_included",
    "tasks_total_for_occupation",
    "partial_coverage",
    "crosswalk_quality",
    "score",
    "score_scale_min",
    "score_scale_max",
    "score_iqr_lower",
    "score_iqr_upper",
    "score_distribution",
    "share_at_or_above_threshold",
    "experimental_arithmetic_mean",
    "evidence_confidence",
    "uncertainty_or_stability",
    "run_disagreement_range",
    "human_review_status",
    "limitations",
    "raw_response_reference",
]


@dataclass(frozen=True)
class MetricDefinition:
    """A metric the project intends to publish, defined before it has a value.

    Defining metrics up front is what lets the release say "this is blocked"
    instead of quietly omitting it. Each definition names the source that could
    satisfy it and the granularity that source actually publishes.
    """

    metric_id: str
    metric_name: str
    unit: str
    definition: str
    required_source_id: str
    expected_source_granularity: str
    # Two axes, never one. See DERIVATION_CLASSES / SOURCE_AUTHORITIES.
    expected_derivation_class: str
    expected_source_authority: str
    denominator: str
    common_misreading: str
    # Which parser would turn the retrieved file into normalised rows. Empty
    # means no parser exists yet, which is itself publishable information.
    parser_id: str = ""


METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "employment_count": MetricDefinition(
        metric_id="employment_count",
        metric_name="Employed persons",
        unit="persons",
        definition=(
            "Number of employed persons whose primary occupation falls in this "
            "PSOC group, from the PSA Labor Force Survey."
        ),
        required_source_id="psa_lfs",
        expected_source_granularity="psoc_major_group",
        # A sample survey generalised to the population: estimated, not
        # observed, however official the publisher.
        expected_derivation_class="estimated",
        expected_source_authority="ph_official_statistical_authority",
        denominator="n/a (a count)",
        parser_id="psa_lfs_occupation_table",
        common_misreading=(
            "Not the number of jobs, and not additive with any finer occupation "
            "list drawn from a different classification."
        ),
    ),
    "wage_basic_pay": MetricDefinition(
        metric_id="wage_basic_pay",
        metric_name="Average monthly basic pay, OWS establishments",
        unit="PHP per month",
        definition=(
            "Average monthly basic pay of time-rated workers on full-time basis "
            "in establishments covered by the PSA Occupational Wages Survey."
        ),
        required_source_id="psa_ows",
        expected_source_granularity="occupation",
        expected_derivation_class="estimated",
        expected_source_authority="ph_official_statistical_authority",
        denominator="workers in covered establishments only",
        parser_id="psa_ows_occupation_table",
        common_misreading=(
            "Not the average earnings of all Filipino workers in the occupation. "
            "OWS covers non-agricultural establishments above an employment "
            "threshold and excludes informal and own-account workers."
        ),
    ),
    "ofw_distribution_share": MetricDefinition(
        metric_id="ofw_distribution_share",
        metric_name="Distribution of OFWs by major occupation group",
        unit="share of all OFWs",
        definition=(
            "Of all overseas Filipino workers counted by the PSA Survey on "
            "Overseas Filipinos, the proportion whose occupation abroad falls in "
            "this major group. The denominator is all OFWs."
        ),
        required_source_id="psa_sof",
        expected_source_granularity="psoc_major_group",
        expected_derivation_class="estimated",
        expected_source_authority="ph_official_statistical_authority",
        denominator="all OFWs",
        parser_id="psa_sof_occupation_table",
        common_misreading=(
            "This is P(occupation | OFW). It is NOT the share of workers in an "
            "occupation who are OFWs, P(OFW | occupation) — that needs domestic "
            "employment in the same occupation as its denominator and a "
            "compatible universe. The two are not interchangeable."
        ),
    ),
    "informal_employment_share": MetricDefinition(
        metric_id="informal_employment_share",
        metric_name="Informal employment share",
        unit="share of employed persons",
        definition=(
            "Share of employed persons in the group holding informal employment, "
            "under the definition used by the publishing PSA release."
        ),
        required_source_id="psa_informal",
        expected_source_granularity="psoc_major_group",
        expected_derivation_class="estimated",
        expected_source_authority="ph_official_statistical_authority",
        denominator="employed persons in the group",
        parser_id="",
        common_misreading=(
            "'Informal sector' and 'informal employment' are different concepts "
            "with different counts. The definition used must be quoted from the "
            "release, not assumed."
        ),
    ),
    "onet_job_zone": MetricDefinition(
        metric_id="onet_job_zone",
        metric_name="O*NET Job Zone (US)",
        unit="ordinal 1-5",
        definition=(
            "O*NET's five-level summary of the preparation a US occupation "
            "typically requires."
        ),
        required_source_id="onet",
        expected_source_granularity="occupation",
        # A real O*NET rating, but measured on US occupations and carried across
        # by a crosswalk: proxy-derived, from an international official source.
        expected_derivation_class="proxy_derived",
        expected_source_authority="international_official_occupational",
        denominator="n/a",
        parser_id="onet_job_zones",
        common_misreading=(
            "Describes United States entry requirements. It is a proxy for the "
            "Philippine occupation only to the extent the crosswalk holds."
        ),
    ),
    "gen_ai_task_exposure": MetricDefinition(
        metric_id="gen_ai_task_exposure",
        metric_name="Generative-AI technical task exposure",
        unit="0-5 rubric score",
        definition=(
            "How much of the task content associated with an occupation current "
            "or plausibly near-term generative-AI systems could assist with or "
            "perform, under the published rubric."
        ),
        required_source_id="llm_scoring",
        expected_source_granularity="occupation",
        expected_derivation_class="model_derived",
        expected_source_authority="project_generated",
        denominator="n/a",
        parser_id="exposure_run_manifest",
        common_misreading=(
            "Not automation probability, replacement probability, displacement, "
            "job loss, or any forecast of employment change."
        ),
    ),
}

# Language that must never appear in published data or the interface when
# describing the exposure measure. Enforced by tests.
BANNED_EXPOSURE_TERMS = [
    "jobs at risk",
    "at risk",
    "job loss",
    "job-loss",
    "risk score",
    "risk vector",
    "replaceable",
    "will be replaced",
    "most likely to be automated",
    "automation probability",
    "replacement probability",
    "displacement risk",
    "displaced",
    "layoff",
    "redundant",
]
