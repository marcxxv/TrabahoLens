"""The sensitivity report must describe the runs it is given, not a template."""

from __future__ import annotations

from trabaholens.v2 import exposure_analysis as ea


def _task(task_id: str, code: str, title: str, a: float) -> dict:
    return {
        "task_id": task_id,
        "task": {"psoc_code": code, "occupation_title": title},
        "consensus": {
            "technical_task_exposure": {"median": a, "range": 0, "agreement": 1.0, "values": [a, a]},
            "human_interaction_intensity": {"median": 2.0, "range": 0, "agreement": 1.0, "values": [2.0, 2.0]},
        },
    }


def test_face_validity_lists_the_extremes_not_the_average():
    run = {
        "occupation_rollup": {
            "1111": {"technical_task_exposure": {"median": 2.0, "n_tasks": 7}},
            "9216": {"technical_task_exposure": {"median": 0.0, "n_tasks": 5}},
            "2523": {"technical_task_exposure": {"median": 4.0, "n_tasks": 6}},
        },
        "tasks": [
            {"task": {"psoc_code": "1111", "occupation_title": "Legislators"}},
            {"task": {"psoc_code": "9216", "occupation_title": "Elementary workers"}},
            {"task": {"psoc_code": "2523", "occupation_title": "Network professionals"}},
        ],
    }
    slices = ea.face_validity_slices(run)
    assert slices["status"] == "computed"
    assert slices["highest"][0]["psoc_code"] == "2523"
    assert slices["lowest"][0]["psoc_code"] == "9216"
    assert slices["lowest"][0]["technical_task_exposure_median"] == 0.0


def test_within_model_stability_marks_only_a_gap_above_one_point():
    run = {
        "tasks": [
            _task("T1", "1111", "A", 2.0),
            {
                "task_id": "T2",
                "task": {"psoc_code": "1111", "occupation_title": "A"},
                "consensus": {
                    "technical_task_exposure": {"median": 2.0, "range": 2, "agreement": 0.0, "values": [1, 3]},
                    "human_interaction_intensity": {"median": 2.0, "range": 0, "agreement": 1.0, "values": [2, 2]},
                },
            },
        ]
    }
    stability = ea.within_model_stability(run)
    assert stability["tasks_with_repeated_attempts"] == 2
    assert stability["unstable_task_ids"] == ["T2"]
    assert stability["unstable_share"] == 0.5


def test_between_model_agreement_reports_the_direction_of_a_shift():
    """A steady +1 is not the same as noise, and must not be reported as if it were."""
    low = {"model_id": "a-low", "tasks": [_task("T1", "1111", "A", 1.0), _task("T2", "2523", "B", 2.0)]}
    high = {"model_id": "b-high", "tasks": [_task("T1", "1111", "A", 2.0), _task("T2", "2523", "B", 3.0)]}
    result = ea.between_model_agreement([low, high])
    pair = result["pairs"][0]
    assert pair["mean_absolute_difference"] == 1.0
    assert pair["mean_signed_difference"] == 1.0
    assert pair["model_b_higher_share"] == 1.0
    assert pair["model_b_lower_share"] == 0.0
