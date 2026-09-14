"""End-to-end exercise of the scoring harness against a stub model client.

The real provider is unreachable from this environment, but the harness itself
must not be untested code: replication, order randomisation, raw-response
retention, provenance completeness and the two refusals are all verified here
against a deterministic stub.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from trabaholens.v2 import score_exposure as sx


class StubClient:
    """Returns a fixed score per task, plus one task whose score oscillates.

    The oscillating task is how the test proves instability is detected rather
    than smoothed away.
    """

    def __init__(self):
        self.calls = 0
        self.seen_user_messages = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, max_tokens, temperature, messages):
        self.calls += 1
        user = messages[-1]["content"]
        self.seen_user_messages.append(user)
        task_id = next(
            line.split(": ", 1)[1] for line in user.splitlines() if line.startswith("task_id: ")
        )
        # T2 disagrees across replicates; everything else is stable.
        exposure = 4 if task_id != "T2" else (1 + self.calls % 4)
        body = json.dumps(
            {
                "technical_task_exposure": exposure,
                "human_interaction_intensity": 1,
                "adoption_friction": 2,
                "evidence_confidence": 3,
                "reasoning": "stub",
                "ai_can_assist_with": "drafting",
                "remains_human_dependent": "accountability",
            }
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=body))])


TASKS = [
    {
        "task_id": f"T{i}",
        "task_statement": f"Task {i} statement",
        "occupation_title": "Test occupation",
        "occupation_source": "O*NET",
        "psoc_code": "25",
        "crosswalk_match_type": "close",
        "crosswalk_match_quality": "medium",
        "task_importance": "3.5",
    }
    for i in range(1, 4)
]


def test_prompt_v010_is_not_distribution_anchored():
    sx.assert_prompt_is_unanchored(sx.load_prompt("0.1.0"))


def test_v1_style_anchor_is_refused():
    text = "# System prompt\nExpected average: ~3.5-4.5\n# User message template\n"
    with pytest.raises(sx.ScoringRefusal, match="distribution-anchoring"):
        sx.assert_prompt_is_unanchored(text)


@pytest.mark.parametrize("field", ["employment_estimate", "avg_monthly_wage_php", "ofw_share", "informal_share"])
def test_labour_market_inputs_are_refused(field):
    with pytest.raises(sx.ScoringRefusal, match="not evidence of"):
        sx.assert_no_prohibited_inputs({"task_id": "T1", field: 1})


def test_scoring_one_task_never_sends_prohibited_fields():
    client = StubClient()
    system = sx.extract_system_prompt(sx.load_prompt("0.1.0"))
    sx.score_one_task(client, system, TASKS[0], "stub/model", 0.0)
    sent = client.seen_user_messages[0]
    for banned in ("employment", "wage", "ofw", "informal"):
        assert banned not in sent.lower(), f"{banned!r} reached the model"


def test_replication_detects_instability():
    client = StubClient()
    system = sx.extract_system_prompt(sx.load_prompt("0.1.0"))
    by_task: dict[str, list[int]] = {}
    for _ in range(4):
        for task in TASKS:
            parsed, _ = sx.score_one_task(client, system, task, "stub/model", 0.0)
            by_task.setdefault(task["task_id"], []).append(parsed["technical_task_exposure"])

    stable = sx.aggregate_replicates(by_task["T1"])
    unstable = sx.aggregate_replicates(by_task["T2"])
    assert stable["stability"] == "stable"
    assert unstable["stability"] == "unstable"
    # Disagreement is retained, not averaged away.
    assert unstable["range"] >= 2
    assert unstable["values"] == by_task["T2"]


def test_single_replicate_reports_no_stability():
    result = sx.aggregate_replicates([3])
    assert result["stability"] == "single_run_no_stability_measure"


def test_weighted_and_unweighted_aggregation_stay_separate():
    entries = [
        {"task": {"task_importance": "5"}, "consensus": {"technical_task_exposure": {"score": 5}}},
        {"task": {"task_importance": "1"}, "consensus": {"technical_task_exposure": {"score": 1}}},
    ]
    unweighted = sx.aggregate_tasks_to_occupation(entries, "technical_task_exposure", weighted=False)
    weighted = sx.aggregate_tasks_to_occupation(entries, "technical_task_exposure", weighted=True)
    assert unweighted == pytest.approx(3.0)
    assert weighted == pytest.approx((5 * 5 + 1 * 1) / 6, abs=1e-4)
    assert unweighted != weighted


def test_missing_scores_do_not_become_zero():
    entries = [
        {"task": {"task_importance": "1"}, "consensus": {"technical_task_exposure": {"score": None}}},
    ]
    assert sx.aggregate_tasks_to_occupation(entries, "technical_task_exposure", weighted=False) is None


def test_out_of_range_response_is_rejected():
    with pytest.raises(ValueError, match="within 0-5"):
        sx.parse_response(json.dumps({
            "technical_task_exposure": 9, "human_interaction_intensity": 1,
            "adoption_friction": 1, "evidence_confidence": 1,
        }))


def test_written_scores_carry_full_provenance(tmp_path, monkeypatch):
    """A released score row must satisfy the release validator."""
    from trabaholens.v2 import validate

    out = tmp_path / "model_scores.csv"
    monkeypatch.setattr(sx, "MODEL_SCORES_CSV", out)

    run_manifest = {
        "run_id": "20260101T000000Z__stub-model",
        "scoring_date": "2026-01-01T00:00:00Z",
        "model_provider": "openrouter",
        "model_id": "stub/model",
        "model_release_or_snapshot": "unpinned",
        "temperature": 0.0,
        "run_count": 3,
        "rubric_version": "0.1.0",
        "prompt_version": "0.1.0",
        "task_source": "O*NET task statements via PSOC crosswalk",
        "human_review_status": "not_reviewed",
        "required_statement": "This experimental score has not yet undergone independent labour-economist validation.",
        "tasks": [
            {
                "task_id": task["task_id"],
                "task": task,
                "consensus": {
                    key: {"score": 3, "range": 1, "stdev": 0.5, "stability": "stable"}
                    for key in sx.DIMENSIONS
                },
            }
            for task in TASKS
        ],
    }
    sx.write_occupation_scores(run_manifest)

    import csv

    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows, "no score rows written"
    assert not validate.check_model_scores(rows)
    # Both aggregations present, neither presented as the score.
    methods = {row["aggregation_method"] for row in rows}
    assert methods == {"unweighted_mean", "importance_weighted_mean"}
    # All four dimensions kept separate.
    assert {row["dimension"] for row in rows} == {"A", "B", "C", "D"}


def test_harness_refuses_to_score_without_task_evidence(tmp_path):
    with pytest.raises(FileNotFoundError, match="task-based"):
        sx.load_tasks(tmp_path / "nope.csv")
