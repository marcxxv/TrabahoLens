"""Fixtures for the validation tests.

The released dataset currently contains no metric values, so validating it
proves almost nothing on its own. These fixtures are deliberately *invalid*
rows: each test feeds a check the exact defect it was written to catch and
asserts that it fires. A validator that has only ever seen an empty table has
not been tested.
"""

from __future__ import annotations

import pytest


def observation(**overrides) -> dict[str, str]:
    """A schema-complete, valid published observation. Tests break one field."""
    row = {
        "observation_id": "employment_count:1",
        "occupation_id": "PSOC-1",
        "psoc_code": "1",
        "metric_id": "employment_count",
        "metric_name": "Employed persons",
        "metric_value": "1200000",
        "unit": "persons",
        "reference_period": "2024 annual average",
        "geography": "Philippines",
        "population_scope": "n/a (a count)",
        "derivation_class": "estimated",
        "source_authority": "ph_official_statistical_authority",
        "availability": "published",
        "source_granularity": "psoc_major_group",
        "display_granularity": "psoc_major_group",
        "source_id": "psa_lfs",
        "source_organization": "Philippine Statistics Authority",
        "source_dataset": "Labor Force Survey",
        "source_table": "tbl-1",
        "source_url": "https://openstat.psa.gov.ph/example",
        "source_file_hash": "a" * 64,
        "retrieved_at": "2026-01-01T00:00:00Z",
        "parser_id": "psa_lfs_occupation_table",
        "parser_version": "0.1.0",
        "normalised_row_id": "psa_lfs_occupation_table:1:0",
        "transformation_id": "T-010-lfs-employment",
        "crosswalk_id": "",
        "confidence_grade": "B",
        "confidence_reasons": "Sample-survey estimate.",
        "pipeline_status": "implemented_verified_with_real_source",
        "uncertainty_lower": "",
        "uncertainty_upper": "",
        "suppression_status": "not_suppressed",
        "notes": "",
    }
    row.update(overrides)
    return row


def crosswalk_row(**overrides) -> dict[str, str]:
    row = {
        "crosswalk_id": "XW-TEST-1",
        "psoc_code": "1",
        "psoc_version": "PSOC 2012",
        "source_code": "1",
        "source_classification": "ISCO-08",
        "match_type": "exact",
        "match_quality": "high",
        "mapping_basis": "structural_derivation",
        "review_status": "machine_proposed",
        "is_one_to_many": "false",
        "is_many_to_one": "false",
        "notes": "",
    }
    row.update(overrides)
    return row


def score_row(**overrides) -> dict[str, str]:
    row = {
        "score_id": "run:1:A:unweighted_mean",
        "occupation_id": "PSOC-1",
        "psoc_code": "1",
        "dimension": "A",
        "rubric_version": "0.1.0",
        "prompt_version": "0.1.0",
        "model_provider": "openrouter",
        "model_id": "some/model",
        "model_release_or_snapshot": "unpinned",
        "scoring_date": "2026-01-01T00:00:00Z",
        "temperature": "0.0",
        "run_count": "3",
        "attempted_attempts": "3",
        "successful_attempts": "3",
        "aggregation_method": "median_across_tasks_ordinal",
        "tasks_included": "2",
        "tasks_total_for_occupation": "2",
        "partial_coverage": "false",
        "task_source": "O*NET",
        "task_weighting": "equal",
        "crosswalk_quality": "medium",
        "score": "2.5",
        "score_scale_min": "0",
        "score_scale_max": "5",
        "uncertainty_or_stability": "mean cross-run stdev 0.2",
        "run_disagreement_range": "1",
        "human_review_status": "not_reviewed",
        "limitations": "experimental",
        "raw_response_reference": "data/exposure/runs/run/run.json",
    }
    row.update(overrides)
    return row


@pytest.fixture
def registry_ids() -> set[str]:
    return {"psa_lfs", "psa_ows", "psa_sof", "psa_informal", "onet", "llm_scoring",
            "ilostat_employment_isco2", "ilostat_earnings_mean", "ilostat_earnings_median", "ilostat_education_attainment", "ilostat_status_employment"}
