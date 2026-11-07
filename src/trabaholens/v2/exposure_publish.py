"""Task-level evidence behind each published exposure score.

The occupation score in ``model_scores.csv`` is a median of task medians. A
reader cannot judge it without seeing the tasks, so the site receives every
included task with PSA's own wording, each attempt's two scores and the
scoring model's short phrases. The phrases are the model's judgement, not
findings, and the interface labels them that way.

Only the run that ``model_scores.csv`` actually references is published. Pilot
runs stay in ``data/exposure/runs/`` as history and never reach the site.
"""

from __future__ import annotations

import csv
import json
import statistics
from typing import Any

from .paths import EXPOSURE_RUNS_DIR, MODEL_SCORES_CSV, REPO_ROOT, rel
from .psoc_tasks import TASKS_REPORT_JSON
from .schema import BANNED_EXPOSURE_TERMS

SITE_EXPOSURE_TASKS_JSON = REPO_ROOT / "site" / "exposure-tasks.json"
TASK_EVIDENCE_SCHEMA = "trabaholens-exposure-tasks/1"


def _published_run_id() -> str | None:
    if not MODEL_SCORES_CSV.exists():
        return None
    with open(MODEL_SCORES_CSV, encoding="utf-8", newline="") as handle:
        references = {row["raw_response_reference"] for row in csv.DictReader(handle)}
    if not references:
        return None
    if len(references) != 1:
        raise ValueError(f"model_scores.csv mixes runs: {sorted(references)}")
    # data/exposure/runs/<run_id>/run.json
    return next(iter(references)).split("/")[-2]


def _phrase(text: str) -> str:
    # Model wording that uses the project's banned hazard vocabulary is not
    # republished, even as a quotation. The score itself is unaffected.
    lowered = (text or "").lower()
    if any(term in lowered for term in BANNED_EXPOSURE_TERMS):
        return ""
    return (text or "").strip()


def build_task_evidence() -> dict[str, Any] | None:
    run_id = _published_run_id()
    if run_id is None:
        return None
    run = json.loads((EXPOSURE_RUNS_DIR / run_id / "run.json").read_text(encoding="utf-8"))
    by_code: dict[str, list[dict[str, Any]]] = {}
    withheld_phrases = 0
    for entry in run["tasks"]:
        if not entry.get("meets_minimum_successful_attempts"):
            continue
        task = entry["task"]
        succeeded = [a for a in entry["attempts"] if a["status"] == "succeeded"]
        first = succeeded[0]["parsed"]
        assist, human = _phrase(first.get("ai_can_assist_with", "")), _phrase(first.get("remains_human_dependent", ""))
        withheld_phrases += (not assist and bool(first.get("ai_can_assist_with"))) + (
            not human and bool(first.get("remains_human_dependent")))
        a_values = [a["parsed"]["technical_task_exposure"] for a in succeeded]
        b_values = [a["parsed"]["human_interaction_intensity"] for a in succeeded]
        by_code.setdefault(task["psoc_code"], []).append({
            "task_id": task["task_id"],
            "source_item_label": task.get("source_item_label", ""),
            "statement": task["task_statement"],
            "source_cell": task.get("source_cell", ""),
            "technical_task_exposure_attempts": a_values,
            "technical_task_exposure_median": statistics.median(a_values),
            "human_interaction_attempts": b_values,
            "human_interaction_median": statistics.median(b_values),
            "model_judged_ai_can_assist_with": assist,
            "model_judged_remains_human_dependent": human,
        })
    for tasks in by_code.values():
        tasks.sort(key=lambda t: t["task_id"])

    coverage = json.loads(TASKS_REPORT_JSON.read_text(encoding="utf-8")) if TASKS_REPORT_JSON.exists() else {}
    return {
        "schema": TASK_EVIDENCE_SCHEMA,
        "run_id": run_id,
        "run_reference": rel(EXPOSURE_RUNS_DIR / run_id / "run.json"),
        "model_provider": run.get("model_provider", ""),
        "model_id": run.get("model_id", ""),
        "resolved_model_ids": run.get("resolved_model_ids", []),
        "rubric_version": run.get("rubric_version", ""),
        "prompt_version": run.get("prompt_version", ""),
        "scoring_date": run.get("scoring_date", ""),
        "task_source": run.get("task_source", ""),
        "task_source_versions": run.get("task_source_versions", []),
        "human_review_status": run.get("human_review_status", ""),
        "phrases_withheld_for_vocabulary": withheld_phrases,
        "note": ("Phrases are what the scoring model judged, not findings. Scores are ordinal "
                 "0-5 and describe potential task interaction with generative AI, not "
                 "employment outcomes."),
        "unit_groups_without_psa_tasks": coverage.get("unit_groups_without_tasks", []),
        "tasks_by_psoc_code": dict(sorted(by_code.items())),
    }


def write_task_evidence() -> str:
    evidence = build_task_evidence()
    if evidence is None:
        if SITE_EXPOSURE_TASKS_JSON.exists():
            SITE_EXPOSURE_TASKS_JSON.unlink()
        return "no published exposure run; site/exposure-tasks.json absent"
    SITE_EXPOSURE_TASKS_JSON.write_text(
        json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    tasks = sum(len(v) for v in evidence["tasks_by_psoc_code"].values())
    return f"{rel(SITE_EXPOSURE_TASKS_JSON)} written ({tasks} tasks, run {evidence['run_id']})"
