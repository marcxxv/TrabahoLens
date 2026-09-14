"""Canonical v2 schema: controlled vocabularies and table definitions.

Everything the release publishes is validated against this module. The
vocabularies are deliberately small and closed — an unrecognised value is a
build failure, not a pass-through.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "2.0.0"

# --------------------------------------------------------------------------
# Evidence classification
# --------------------------------------------------------------------------
# Exactly the five classes the interface is required to display. Every
# published numeric field carries one, and the badge shown in the UI is this
# value — not a separate editorial choice that could drift from the data.

ESTIMATE_TYPES = {
    "official_statistic": (
        "Official statistic",
        "A figure published by an official statistical agency, reproduced at the "
        "granularity that agency published it.",
    ),
    "calculated_statistic": (
        "Calculated statistic",
        "Arithmetic we performed on official figures — a share, a rate, a sum. "
        "The inputs are official; the calculation is ours and is documented.",
    ),
    "estimate": (
        "Estimate",
        "A modelled or survey-weighted value with sampling uncertainty. Reported "
        "with an interval wherever the source supports one.",
    ),
    "proxy": (
        "Proxy",
        "A stand-in measured on a different population, place or unit than the "
        "one shown. Useful as an indication, not as a measurement of this "
        "occupation in the Philippines.",
    ),
    "experimental_model_score": (
        "Experimental model-derived score",
        "Produced by a language model following a published rubric. It is a "
        "research signal, not an observation, and it has not been validated by "
        "independent labour economists.",
    ),
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
    "estimate_type",
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
    "transformation_id",
    "crosswalk_id",
    "confidence_grade",
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
    "aggregation_method",
    "task_source",
    "task_weighting",
    "crosswalk_quality",
    "score",
    "score_scale_min",
    "score_scale_max",
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
    expected_estimate_type: str
    denominator: str
    common_misreading: str


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
        expected_estimate_type="official_statistic",
        denominator="n/a (a count)",
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
        expected_estimate_type="official_statistic",
        denominator="workers in covered establishments only",
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
        expected_estimate_type="official_statistic",
        denominator="all OFWs",
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
        expected_estimate_type="official_statistic",
        denominator="employed persons in the group",
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
        expected_estimate_type="proxy",
        denominator="n/a",
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
        expected_estimate_type="experimental_model_score",
        denominator="n/a",
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
