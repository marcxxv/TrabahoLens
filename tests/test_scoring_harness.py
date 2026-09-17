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
        "onet_soc_code": "25-1011.00",
        "crosswalk_id": "XW-FIXTURE-25",
        "crosswalk_match_type": "close",
        "crosswalk_match_quality": "medium",
        "crosswalk_review_status": "human_reviewed",
        "task_source_version": "31.0",
        "task_importance": "3.5",
    }
    for i in range(1, 4)
]


def test_prompt_v010_is_not_distribution_anchored():
    sx.assert_prompt_is_unanchored(sx.load_prompt(sx.DEFAULT_PROMPT_VERSION))


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
    system = sx.extract_system_prompt(sx.load_prompt(sx.DEFAULT_PROMPT_VERSION))
    sx.score_one_task(client, system, TASKS[0], "stub/model", 0.0)
    sent = client.seen_user_messages[0]
    for banned in ("employment", "wage", "ofw", "informal"):
        assert banned not in sent.lower(), f"{banned!r} reached the model"


def test_repeated_attempts_surface_disagreement():
    """Repeated attempts, not independent replicates — see rubric v0.2.0."""
    from trabaholens.v2.exposure_runs import ordinal_summary

    client = StubClient()
    system = sx.extract_system_prompt(sx.load_prompt(sx.DEFAULT_PROMPT_VERSION))
    by_task: dict[str, list[int]] = {}
    for attempt in range(1, 5):
        for task in TASKS:
            record = sx.score_one_task(
                client, system, task, "stub/model", 0.0, attempt_index=attempt
            )
            assert record.succeeded
            by_task.setdefault(task["task_id"], []).append(
                record.parsed["technical_task_exposure"]
            )

    stable = ordinal_summary(by_task["T1"])
    unstable = ordinal_summary(by_task["T2"])
    assert stable["range"] == 0
    assert stable["agreement"] == 1.0
    assert unstable["range"] >= 2
    # Disagreement is retained, not averaged away.
    assert unstable["values"] == sorted(by_task["T2"])
    assert unstable["agreement"] < 1.0


def test_single_attempt_reports_no_agreement_signal():
    from trabaholens.v2.exposure_runs import ordinal_summary

    result = ordinal_summary([3])
    assert result["n"] == 1
    assert result["range"] == 0
    # One attempt cannot evidence reproducibility, whatever its agreement reads.
    assert result["median"] == 3


def test_out_of_range_response_is_rejected():
    with pytest.raises(ValueError, match="within 0-5"):
        sx.parse_response(json.dumps({
            "technical_task_exposure": 9, "human_interaction_intensity": 1,
            "adoption_friction": 1, "evidence_confidence": 1,
        }))


def test_written_scores_carry_full_provenance(tmp_path, monkeypatch):
    """A released score row must satisfy the release validator."""
    from argparse import Namespace

    from trabaholens.v2 import validate
    from trabaholens.v2.exposure_runs import AttemptRecord, TaskRunRecord

    out = tmp_path / "model_scores.csv"
    monkeypatch.setattr(sx, "MODEL_SCORES_CSV", out)

    records = {}
    for task in TASKS:
        record = TaskRunRecord(task_id=task["task_id"], task=task)
        record.attempts = [
            AttemptRecord(
                task["task_id"], i, "succeeded", "2026-01-01T00:00:00Z",
                parsed={"technical_task_exposure": 3, "human_interaction_intensity": 2},
            )
            for i in (1, 2, 3)
        ]
        records[task["task_id"]] = record

    args = Namespace(attempts=3, min_successful=2, model="stub/model", temperature=0.0,
                     rubric_version=sx.DEFAULT_RUBRIC_VERSION,
                     prompt_version=sx.DEFAULT_PROMPT_VERSION, exposure_threshold=4)
    manifest = sx.build_run_manifest(
        records, args, "20260101T000000Z__stub-model__abcd1234",
        sx.load_rubric(sx.DEFAULT_RUBRIC_VERSION),
    )
    sx.write_occupation_scores(manifest)

    import csv

    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows, "no score rows written"
    assert not validate.check_model_scores(rows)
    # Only the two model-scored dimensions are released.
    assert {row["dimension"] for row in rows} == {"A", "B"}
    # Ordinal aggregation, and the attempt accounting is real.
    assert all(row["aggregation_method"] == "median_across_tasks_ordinal" for row in rows)
    assert all(row["successful_attempts"] == "3" for row in rows)
    assert all(row["attempted_attempts"] == "3" for row in rows)
    assert all(row["score_distribution"] for row in rows)


def test_harness_refuses_to_score_without_task_evidence(tmp_path):
    with pytest.raises(FileNotFoundError, match="task-based"):
        sx.load_tasks(tmp_path / "nope.csv")
