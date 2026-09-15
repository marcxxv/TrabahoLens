"""Exposure-run integrity: attempts, not configuration, determine provenance.

The pre-remediation harness recorded ``run_count = args.runs`` — the number of
attempts *requested* — and dropped failures with a printed message. One success
out of three attempts published a score claiming three runs, and the two
failures left no trace.

These tests drive the harness against a stub client whose failures are
controlled, and assert the specific guarantees finding 7 requires.
"""

from __future__ import annotations

import json
from argparse import Namespace
from types import SimpleNamespace

import pytest

from trabaholens.v2 import score_exposure as sx
from trabaholens.v2.exposure_runs import (
    AttemptRecord,
    TaskRunRecord,
    aggregate_tasks_ordinal,
    ordinal_summary,
    weighted_median,
)

TASKS = [
    {
        "task_id": f"T{i}",
        "task_statement": f"FIXTURE task {i} statement.",
        "occupation_title": "FIXTURE occupation",
        "occupation_source": "ONET",
        "psoc_code": "25",
        "crosswalk_match_type": "close",
        "crosswalk_match_quality": "medium",
        "task_importance": "3.5",
        "task_source_version": "31.0",
    }
    for i in (1, 2)
]


class StubClient:
    """Fails a configurable set of (task_id, attempt) pairs."""

    def __init__(self, fail_on=(), bad_json_on=()):
        self.fail_on = set(fail_on)
        self.bad_json_on = set(bad_json_on)
        self.calls = 0
        self.seen = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, max_tokens, temperature, messages):
        self.calls += 1
        user = messages[-1]["content"]
        self.seen.append(user)
        task_id = next(
            line.split(": ", 1)[1] for line in user.splitlines() if line.startswith("task_id: ")
        )
        key = (task_id, self.calls)
        if task_id in self.fail_on or key in self.fail_on:
            raise RuntimeError("FIXTURE provider error")
        body = (
            "not json at all"
            if task_id in self.bad_json_on
            else json.dumps({"technical_task_exposure": 4, "human_interaction_intensity": 1})
        )
        return SimpleNamespace(
            id=f"req-{self.calls}",
            model=f"{model}-resolved",
            choices=[SimpleNamespace(message=SimpleNamespace(content=body))],
        )


def _attempts(client, task, n, start=1):
    system = sx.extract_system_prompt(sx.load_prompt("0.2.0"))
    return [
        sx.score_one_task(client, system, task, "stub/model", 0.0, attempt_index=i)
        for i in range(start, start + n)
    ]


# ---------------------------------------------------------------------------
# Finding 7: replication must not be misreported
# ---------------------------------------------------------------------------

def test_failed_attempts_are_retained_not_dropped():
    client = StubClient(fail_on={("T1", 1)})
    records = _attempts(client, TASKS[0], 3)
    assert len(records) == 3, "a failed attempt must still produce a record"
    failed = [r for r in records if not r.succeeded]
    assert len(failed) == 1
    assert failed[0].error_type == "RuntimeError"
    assert failed[0].error_message
    assert failed[0].request_payload, "the request payload must be auditable"


def test_two_successes_are_not_reported_as_three():
    client = StubClient(fail_on={("T1", 1)})
    record = TaskRunRecord(task_id="T1", task=TASKS[0])
    record.attempts = _attempts(client, TASKS[0], 3)
    assert record.attempted == 3
    assert record.successful == 2
    assert record.failed == 1
    payload = record.as_dict(minimum=2)
    assert payload["attempted_attempts"] == 3
    assert payload["successful_attempts"] == 2
    assert payload["successful_attempts"] != payload["attempted_attempts"]


def test_one_success_out_of_three_cannot_be_published():
    record = TaskRunRecord(task_id="T1", task=TASKS[0])
    record.attempts = [
        AttemptRecord("T1", 1, "request_failed", "t", error_type="RuntimeError"),
        AttemptRecord("T1", 2, "succeeded", "t", parsed={"technical_task_exposure": 4}),
        AttemptRecord("T1", 3, "parse_failed", "t", error_type="ValueError"),
    ]
    assert record.successful == 1
    assert not record.meets_minimum(2)
    assert not record.as_dict(minimum=2)["meets_minimum_successful_attempts"]


def test_parse_failure_counts_as_failure_not_success():
    client = StubClient(bad_json_on={"T1"})
    records = _attempts(client, TASKS[0], 2)
    assert all(r.status == "parse_failed" for r in records)
    assert all(not r.succeeded for r in records)
    # The raw response is kept even though it could not be parsed.
    assert all(r.raw_response for r in records)
    assert all(r.parser_status.startswith("ValueError") for r in records)


def test_completely_failed_task_does_not_disappear_silently():
    client = StubClient(fail_on={"T2"})
    record = TaskRunRecord(task_id="T2", task=TASKS[1])
    record.attempts = _attempts(client, TASKS[1], 3)
    assert record.successful == 0
    payload = record.as_dict(minimum=2)
    # It is present in the manifest with zero successes, not absent from it.
    assert payload["task_id"] == "T2"
    assert payload["successful_attempts"] == 0
    assert len(payload["attempts"]) == 3


def test_provider_request_id_and_resolved_model_are_recorded():
    client = StubClient()
    record = _attempts(client, TASKS[0], 1)[0]
    assert record.provider_request_id.startswith("req-")
    assert record.resolved_model_id == "stub/model-resolved"


def test_run_ids_are_collision_resistant():
    ids = {sx.new_run_id("stub/model") for _ in range(50)}
    assert len(ids) == 50, "run ids collided; a collision overwrites another run's raw responses"


def test_manifest_excludes_below_minimum_tasks_from_the_rollup():
    good = TaskRunRecord(task_id="T1", task=TASKS[0])
    good.attempts = [
        AttemptRecord("T1", i, "succeeded", "t",
                      parsed={"technical_task_exposure": 4, "human_interaction_intensity": 1})
        for i in (1, 2, 3)
    ]
    poor = TaskRunRecord(task_id="T2", task=TASKS[1])
    poor.attempts = [
        AttemptRecord("T2", 1, "request_failed", "t", error_type="RuntimeError"),
        AttemptRecord("T2", 2, "request_failed", "t", error_type="RuntimeError"),
        AttemptRecord("T2", 3, "succeeded", "t",
                      parsed={"technical_task_exposure": 5, "human_interaction_intensity": 0}),
    ]
    args = Namespace(attempts=3, min_successful=2, model="stub/model", temperature=0.0,
                     rubric_version="0.2.0", prompt_version="0.2.0", exposure_threshold=4)
    rubric = sx.load_rubric("0.2.0")
    manifest = sx.build_run_manifest({"T1": good, "T2": poor}, args, "run-x", rubric)

    assert manifest["tasks_meeting_minimum"] == 1
    assert manifest["tasks_below_minimum"] == ["T2"]
    assert manifest["total_attempts"] == 6
    assert manifest["total_successful_attempts"] == 4
    assert manifest["total_failed_attempts"] == 2
    # T2's single success must not influence the occupation rollup.
    rollup = manifest["occupation_rollup"]["25"]
    assert rollup["tasks_included"] == 1
    assert rollup["tasks_total_for_occupation"] == 2
    assert rollup["partial_coverage"] is True


def test_partial_coverage_is_disclosed_on_written_scores(tmp_path, monkeypatch):
    from trabaholens.v2 import validate

    out = tmp_path / "model_scores.csv"
    monkeypatch.setattr(sx, "MODEL_SCORES_CSV", out)

    good = TaskRunRecord(task_id="T1", task=TASKS[0])
    good.attempts = [
        AttemptRecord("T1", i, "succeeded", "t",
                      parsed={"technical_task_exposure": 4, "human_interaction_intensity": 1})
        for i in (1, 2, 3)
    ]
    poor = TaskRunRecord(task_id="T2", task=TASKS[1])
    poor.attempts = [AttemptRecord("T2", 1, "request_failed", "t", error_type="RuntimeError")]

    args = Namespace(attempts=3, min_successful=2, model="stub/model", temperature=0.0,
                     rubric_version="0.2.0", prompt_version="0.2.0", exposure_threshold=4)
    manifest = sx.build_run_manifest({"T1": good, "T2": poor}, args, "run-y", sx.load_rubric("0.2.0"))
    sx.write_occupation_scores(manifest)

    import csv

    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows
    assert all(r["partial_coverage"] == "true" for r in rows)
    assert all(r["tasks_included"] == "1" and r["tasks_total_for_occupation"] == "2" for r in rows)
    assert not validate.check_model_scores(rows)


# ---------------------------------------------------------------------------
# Findings 10 and 11: dimensions C and D
# ---------------------------------------------------------------------------

def test_model_is_not_asked_for_adoption_friction_or_evidence_confidence():
    assert set(sx.MODEL_SCORED_DIMENSIONS) == {
        "technical_task_exposure", "human_interaction_intensity"
    }
    assert "adoption_friction" not in sx.MODEL_SCORED_DIMENSIONS
    assert "evidence_confidence" not in sx.MODEL_SCORED_DIMENSIONS


def test_prompt_does_not_ask_for_adoption_friction():
    prompt = sx.load_prompt(sx.DEFAULT_PROMPT_VERSION)
    body = prompt.split("# Changes from", 1)[0].lower()
    assert "adoption_friction" not in body
    assert "evidence_confidence" not in body


def test_response_missing_retired_dimensions_still_parses():
    parsed = sx.parse_response(json.dumps({
        "technical_task_exposure": 3, "human_interaction_intensity": 2,
    }))
    assert parsed["technical_task_exposure"] == 3


def test_evidence_confidence_is_deterministic_and_explains_itself():
    kwargs = dict(
        task_statement="FIXTURE statement.", task_importance=4.0,
        crosswalk_match_quality="high", crosswalk_match_type="close",
        task_source_is_philippine=False, successful_attempts=3, minimum_attempts=2,
    )
    first, reasons = sx.compute_evidence_confidence(**kwargs)
    second, _ = sx.compute_evidence_confidence(**kwargs)
    assert first == second, "the same inputs must give the same grade"
    assert reasons, "the component reasons must be published, not just the number"


def test_evidence_confidence_collapses_when_the_crosswalk_is_unusable():
    score, reasons = sx.compute_evidence_confidence(
        task_statement="FIXTURE.", task_importance=4.0,
        crosswalk_match_quality="none", crosswalk_match_type="no_defensible_match",
        task_source_is_philippine=False, successful_attempts=3, minimum_attempts=2,
    )
    assert score <= 1
    assert any("Crosswalk unusable" in r for r in reasons)


def test_evidence_confidence_collapses_on_insufficient_attempts():
    score, reasons = sx.compute_evidence_confidence(
        task_statement="FIXTURE.", task_importance=4.0,
        crosswalk_match_quality="high", crosswalk_match_type="close",
        task_source_is_philippine=False, successful_attempts=1, minimum_attempts=2,
    )
    assert score <= 1
    assert any("successful scoring attempt" in r for r in reasons)


# ---------------------------------------------------------------------------
# Finding 9: ordinal aggregation
# ---------------------------------------------------------------------------

def test_ordinal_summary_publishes_a_median_and_the_full_distribution():
    summary = ordinal_summary([0, 4, 4, 5])
    assert summary["median"] == 4
    assert summary["distribution"]["4"] == 2
    assert summary["distribution"]["0"] == 1
    assert 0 <= summary["agreement"] <= 1


def test_task_aggregation_is_median_based_with_mean_labelled_experimental():
    entries = [{"consensus": {"A": {"median": m}}} for m in [0, 0, 5, 5, 5]]
    result = aggregate_tasks_ordinal(entries, "A", threshold=4)
    assert result["median"] == 5
    assert result["share_of_tasks_at_or_above_threshold"] == pytest.approx(0.6)
    assert "ordinal" in result["experimental_arithmetic_mean_caveat"].lower()
    assert "convenience statistic" in result["experimental_arithmetic_mean_caveat"].lower()
    # The mean and median genuinely differ here, which is the point of showing both.
    assert result["experimental_arithmetic_mean"] != result["median"]


def test_weighted_median_is_ordinal_safe():
    assert weighted_median([1, 5], [9, 1]) == 1
    assert weighted_median([1, 5], [1, 9]) == 5
    assert weighted_median([], []) is None


# ---------------------------------------------------------------------------
# Finding 12: input and foreign-key validation
# ---------------------------------------------------------------------------

def test_prohibited_inputs_are_refused_at_any_depth():
    with pytest.raises(sx.ScoringRefusal, match="not evidence of"):
        sx.assert_no_prohibited_inputs({"task": {"nested": {"ofw_share": 0.4}}})
    with pytest.raises(sx.ScoringRefusal):
        sx.assert_no_prohibited_inputs({"rows": [{"employment_count": 5}]})
    sx.assert_no_prohibited_inputs({"task_id": "T1", "task_statement": "fine"})


@pytest.mark.parametrize("mutation,expected", [
    ({"task_id": ""}, "empty task_id"),
    ({"task_statement": "  "}, "empty task_statement"),
    ({"task_importance": "9"}, r"outside the O\*NET 1-5 scale"),
    ({"task_importance": "abc"}, "unparseable task_importance"),
    ({"crosswalk_match_type": "no_defensible_match"}, "no defensible mapping"),
    ({"crosswalk_review_status": "rejected"}, "rejected"),
])
def test_task_input_validation_rejects_bad_rows(mutation, expected):
    task = {**TASKS[0], **mutation}
    with pytest.raises(sx.ScoringRefusal, match=expected):
        sx.validate_task_inputs([task])


def test_duplicate_task_ids_are_rejected():
    with pytest.raises(sx.ScoringRefusal, match="duplicate task_id"):
        sx.validate_task_inputs([TASKS[0], dict(TASKS[0])])


def test_mixed_task_source_versions_are_rejected():
    a = {**TASKS[0], "task_source_version": "30.2"}
    b = {**TASKS[1], "task_source_version": "31.0"}
    with pytest.raises(sx.ScoringRefusal, match="mix task-source versions"):
        sx.validate_task_inputs([a, b])


def test_valid_task_rows_pass():
    sx.validate_task_inputs(TASKS)


# ---------------------------------------------------------------------------
# Release-gate: the validator inspects successes, not a declared number
# ---------------------------------------------------------------------------

def test_validator_rejects_a_score_with_one_successful_attempt():
    from tests.conftest import score_row
    from trabaholens.v2 import validate

    rows = [score_row(attempted_attempts="3", successful_attempts="1")]
    failures = validate.check_model_scores(rows)
    assert any(f.check == "attempt_accounting" for f in failures)
    assert any("at least 2 successes" in f.detail for f in failures)


def test_validator_rejects_more_successes_than_attempts():
    from tests.conftest import score_row
    from trabaholens.v2 import validate

    rows = [score_row(attempted_attempts="2", successful_attempts="5")]
    failures = validate.check_model_scores(rows)
    assert any("exceeds" in f.detail for f in failures)


def test_validator_rejects_a_score_with_no_attempt_accounting():
    from tests.conftest import score_row
    from trabaholens.v2 import validate

    rows = [score_row(attempted_attempts="", successful_attempts="")]
    failures = validate.check_model_scores(rows)
    assert any("without attempted/successful attempt counts" in f.detail for f in failures)


@pytest.mark.parametrize("dimension", ["C", "D"])
def test_validator_rejects_retired_dimensions(dimension):
    from tests.conftest import score_row
    from trabaholens.v2 import validate

    failures = validate.check_model_scores([score_row(dimension=dimension)])
    assert any(f.check == "retired_dimension" for f in failures)


def test_valid_score_row_passes():
    from tests.conftest import score_row
    from trabaholens.v2 import validate

    assert not validate.check_model_scores([score_row()])
