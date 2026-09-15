"""Every validator is tested against a fixture that violates it.

Each test names the v1 defect it guards against, so a future change that
weakens a check fails a test that explains why the check exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import crosswalk_row, observation, score_row
from trabaholens.v2 import validate


# ---------------------------------------------------------------------------
# The baseline dataset must itself validate
# ---------------------------------------------------------------------------

def test_released_dataset_validates():
    failures = validate.run_all()
    assert not failures, "\n".join(str(f) for f in failures)


# ---------------------------------------------------------------------------
# Placeholder fill — v1 hiring_intensity = 50 for all 173 rows
# ---------------------------------------------------------------------------

def test_universal_constant_is_rejected():
    rows = [
        observation(observation_id=f"hiring:{i}", psoc_code=str(i), metric_id="employment_count",
                    metric_value="50", unit="persons")
        for i in range(10)
    ]
    failures = validate.check_no_placeholder_fill(rows)
    assert any(f.check == "placeholder_fill" for f in failures)
    assert "one distinct value" in str(failures[0])


def test_near_constant_fill_is_rejected():
    """v1's wages: 11 distinct values across 173 rows."""
    rows = [
        observation(observation_id=f"wage:{i}", psoc_code=str(i), metric_value="28000")
        for i in range(30)
    ] + [observation(observation_id="wage:x", psoc_code="x", metric_value="45000")]
    failures = validate.check_no_placeholder_fill(rows)
    assert any(f.check == "placeholder_fill" for f in failures)


def test_varied_values_pass():
    rows = [
        observation(observation_id=f"e:{i}", psoc_code=str(i), metric_value=str(1000 * (i + 1)))
        for i in range(10)
    ]
    assert not validate.check_no_placeholder_fill(rows)


# ---------------------------------------------------------------------------
# Missing values must stay missing
# ---------------------------------------------------------------------------

def test_unavailable_metric_carrying_a_value_is_rejected():
    rows = [observation(availability="blocked_pending_source", metric_value="0")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any(f.check == "value_without_publication" for f in failures)


def test_published_metric_without_a_value_is_rejected():
    rows = [observation(metric_value="")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any(f.check == "published_without_value" for f in failures)


# ---------------------------------------------------------------------------
# Provenance is mandatory for any published value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["source_url", "reference_period", "source_file_hash", "retrieved_at"])
def test_published_value_without_provenance_is_rejected(field):
    rows = [observation(**{field: ""})]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any(f.check == "provenance" and field in f.detail for f in failures)


def test_unregistered_source_is_rejected():
    rows = [observation(source_id="some_blog")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any(f.check == "source_registry" for f in failures)


# ---------------------------------------------------------------------------
# Granularity — v1 broadcast PSOC-major constants onto occupations
# ---------------------------------------------------------------------------

def test_broad_source_shown_finer_cannot_be_official():
    rows = [observation(source_granularity="psoc_major_group",
                        display_granularity="occupation",
                        derivation_class="estimated")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any(f.check == "granularity_mismatch" and "proxy_derived" in f.detail for f in failures)


def test_broad_source_shown_finer_cannot_hold_high_confidence():
    rows = [observation(source_granularity="psoc_major_group",
                        display_granularity="occupation",
                        derivation_class="proxy_derived", confidence_grade="A")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any(f.check == "granularity_mismatch" and "confidence grade" in f.detail for f in failures)


def test_disclosed_proxy_at_finer_granularity_passes():
    """Allowed when labelled proxy_derived and graded down — disclosure is the point."""
    rows = [observation(source_granularity="psoc_major_group",
                        display_granularity="occupation",
                        derivation_class="proxy_derived", confidence_grade="C")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert not [f for f in failures if f.check == "granularity_mismatch"]


# ---------------------------------------------------------------------------
# Impossible values
# ---------------------------------------------------------------------------

def test_share_above_one_is_rejected():
    rows = [observation(metric_id="ofw_distribution_share", unit="share of all OFWs",
                        metric_value="1.4", source_id="psa_sof")]
    failures = validate.check_observations(rows, {"psa_sof"})
    assert any(f.check == "impossible_percentage" for f in failures)


def test_negative_employment_is_rejected():
    rows = [observation(metric_value="-5")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any(f.check == "negative_count" for f in failures)


# ---------------------------------------------------------------------------
# Double counting — v1 published broad PH categories beside O*NET components
# ---------------------------------------------------------------------------

def test_aggregate_published_with_its_components_is_rejected():
    rows = [
        observation(observation_id="a", psoc_code="9", metric_value="10500000"),
        observation(observation_id="b", psoc_code="91", metric_value="4000000"),
    ]
    failures = validate.check_no_double_counting(rows)
    assert any(f.check == "double_counting" for f in failures)


def test_siblings_without_their_parent_pass():
    rows = [
        observation(observation_id="a", psoc_code="91", metric_value="4000000"),
        observation(observation_id="b", psoc_code="92", metric_value="3000000"),
    ]
    assert not validate.check_no_double_counting(rows)


def test_children_that_do_not_sum_to_parent_are_rejected():
    rows = [
        observation(observation_id="a", psoc_code="9", metric_value="10500000"),
        observation(observation_id="b", psoc_code="91", metric_value="1000000"),
        observation(observation_id="c", psoc_code="92", metric_value="1000000"),
    ]
    failures = validate.check_group_total_reconciliation(rows)
    assert any(f.check == "group_total_reconciliation" for f in failures)


# ---------------------------------------------------------------------------
# Crosswalk integrity — v1 had no crosswalk table at all
# ---------------------------------------------------------------------------

def test_title_similarity_mapping_must_be_rejected_status():
    rows = [crosswalk_row(mapping_basis="title_similarity_only", review_status="human_reviewed")]
    failures = validate.check_crosswalk(rows)
    assert any("title-similarity-only" in f.detail for f in failures)


def test_impossible_crosswalk_states_are_rejected():
    rows = [crosswalk_row(crosswalk_id="x1", match_type="no_defensible_match", match_quality="high")]
    failures = validate.check_crosswalk(rows)
    assert any("no_defensible_match" in f.detail for f in failures)

    rows = [crosswalk_row(crosswalk_id="x2", match_type="exact", match_quality="low")]
    failures = validate.check_crosswalk(rows)
    assert any("contradictory" in f.detail for f in failures)


def test_cardinality_flags_must_match_the_table():
    rows = [
        crosswalk_row(crosswalk_id="x1", psoc_code="2", source_code="13", is_one_to_many="false"),
        crosswalk_row(crosswalk_id="x2", psoc_code="2", source_code="15", is_one_to_many="false"),
    ]
    failures = validate.check_crosswalk(rows)
    assert any("is_one_to_many" in f.detail for f in failures)


def test_observation_through_a_rejected_crosswalk_is_refused():
    crosswalk = [crosswalk_row(crosswalk_id="XW-BAD", review_status="rejected",
                               mapping_basis="undocumented_heuristic",
                               match_type="broader", match_quality="low")]
    rows = [observation(crosswalk_id="XW-BAD")]
    failures = validate.check_observations_do_not_use_rejected_crosswalks(rows, crosswalk)
    assert any(f.check == "rejected_crosswalk" for f in failures)


# ---------------------------------------------------------------------------
# Model score provenance — all 11 fields were absent in v1
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field",
    ["rubric_version", "prompt_version", "model_provider", "model_id", "scoring_date",
     "temperature", "run_count", "aggregation_method", "uncertainty_or_stability",
     "human_review_status", "raw_response_reference"],
)
def test_score_missing_any_provenance_field_is_rejected(field):
    failures = validate.check_model_scores([score_row(**{field: ""})])
    assert any(f.check == "score_provenance" and field in f.detail for f in failures)


def test_single_run_score_is_rejected():
    failures = validate.check_model_scores([score_row(run_count="1")])
    assert any("cannot support a stability measure" in f.detail for f in failures)


def test_score_outside_its_declared_scale_is_rejected():
    failures = validate.check_model_scores([score_row(score="9")])
    assert any(f.check == "score_range" for f in failures)


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

def test_hazard_language_is_rejected(tmp_path: Path):
    page = tmp_path / "page.html"
    page.write_text("<p>These are the jobs at risk from AI.</p>", encoding="utf-8")
    failures = validate.check_language([page])
    assert any(f.check == "banned_language" for f in failures)


def test_risk_vector_label_is_rejected(tmp_path: Path):
    page = tmp_path / "page.html"
    page.write_text('<div class="risk-title">Risk Vector Explainer</div>', encoding="utf-8")
    failures = validate.check_language([page])
    assert any("risk vector" in f.detail for f in failures)


def test_disclaiming_the_framing_is_allowed(tmp_path: Path):
    """The required disclaimer must not trip the ban it enforces."""
    page = tmp_path / "page.html"
    page.write_text(
        "<p>It is not an estimate of automation, displacement, layoffs, or future "
        "employment. This is not a job loss forecast.</p>",
        encoding="utf-8",
    )
    assert not validate.check_language([page])


def test_negation_does_not_leak_across_sentences(tmp_path: Path):
    """A denial in an earlier sentence must not license an assertion later."""
    page = tmp_path / "page.html"
    page.write_text(
        "<p>This is not a forecast. These occupations are the most likely to be "
        "automated in the next decade.</p>",
        encoding="utf-8",
    )
    failures = validate.check_language([page])
    assert any("most likely to be automated" in f.detail for f in failures)


def test_quoting_v1_language_for_audit_is_allowed(tmp_path: Path):
    page = tmp_path / "page.html"
    page.write_text(
        '<p><!-- v1-quote -->The old build called this "jobs at risk".<!-- /v1-quote --></p>',
        encoding="utf-8",
    )
    assert not validate.check_language([page])


# ---------------------------------------------------------------------------
# Hard-coded counts — v1 hard-coded 173 in README and og:description
# ---------------------------------------------------------------------------

def test_hardcoded_occupation_count_is_rejected(tmp_path: Path):
    page = tmp_path / "page.html"
    page.write_text('<meta content="Treemap of 173 Philippine occupations" />', encoding="utf-8")
    failures = validate.check_no_hardcoded_counts(page, 53)
    assert any(f.check == "hardcoded_count" for f in failures)


def test_derived_count_passes(tmp_path: Path):
    page = tmp_path / "page.html"
    page.write_text("<div id=\"count\"></div><script>el.textContent = data.counts.occupations;</script>",
                    encoding="utf-8")
    assert not validate.check_no_hardcoded_counts(page, 53)


# ---------------------------------------------------------------------------
# Site payload
# ---------------------------------------------------------------------------

def test_site_payload_rejects_a_zero_filled_missing_value(tmp_path: Path):
    import json

    payload = {
        "schema": "x", "release": {}, "derivation_class_legend": {},
        "source_authority_legend": {}, "metrics": {},
        "occupations": [
            {
                "psoc_code": "1",
                "metrics": {
                    "employment_count": {
                        "value": 0,
                        "availability": "blocked_pending_source",
                        "derivation_class": "estimated",
                        "source_authority": "ph_official_statistical_authority",
                    }
                },
            }
        ],
    }
    path = tmp_path / "data.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    failures = validate.check_site_payload(path)
    assert any("never zero or a neutral midpoint" in f.detail for f in failures)


def test_site_payload_rejects_a_value_without_provenance(tmp_path: Path):
    import json

    payload = {
        "schema": "x", "release": {}, "derivation_class_legend": {},
        "source_authority_legend": {}, "metrics": {},
        "occupations": [
            {
                "psoc_code": "1",
                "metrics": {
                    "employment_count": {
                        "value": 1200000,
                        "availability": "published",
                        "derivation_class": "estimated",
                        "source_authority": "ph_official_statistical_authority",
                        "source_organization": "", "source_url": "",
                        "reference_period": "", "confidence_grade": "",
                        "parser_id": "", "transformation_id": "",
                    }
                },
            }
        ],
    }
    path = tmp_path / "data.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    failures = validate.check_site_payload(path)
    assert any("published value without" in f.detail for f in failures)
