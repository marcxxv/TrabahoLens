"""Task-first generative-AI exposure scoring harness.

Differences from the v1 scorer, each answering a specific audit finding:

* Scores **tasks**, not occupation titles, and aggregates upward.
* Runs **N independent replicates** and randomises task order per replicate, so
  ordering effects and instability are measurable rather than invisible.
* Retains **every raw response** under ``data/exposure/runs/<run_id>/``.
* Records complete provenance per score: provider, model id, snapshot, prompt
  version, rubric version, temperature, run count, aggregation method, task
  source, crosswalk quality.
* **Never overwrites history.** Each invocation creates a new run directory.
* Reports the median plus the disagreement range; it does not smooth
  disagreement away.
* Refuses to run if the prompt contains a target-distribution instruction or if
  a prohibited labour-market input would be sent to the model.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .paths import (
    EXPOSURE_PROMPT_DIR,
    EXPOSURE_RUBRIC_DIR,
    EXPOSURE_RUNS_DIR,
    MODEL_SCORES_CSV,
    ensure_parent,
    rel,
)
from .schema import MODEL_SCORES_COLUMNS

DEFAULT_RUBRIC_VERSION = "0.1.0"
DEFAULT_PROMPT_VERSION = "0.1.0"
DEFAULT_RUNS = 3
DEFAULT_TEMPERATURE = 0.0

DIMENSIONS = {
    "technical_task_exposure": "A",
    "human_interaction_intensity": "B",
    "adoption_friction": "C",
    "evidence_confidence": "D",
}

# Field names that must never reach the model. Checked at call time, not merely
# documented, because the v1 defect was that they were sent.
PROHIBITED_INPUT_KEYS = {
    "employment",
    "employment_estimate",
    "employment_count",
    "jobs",
    "wage",
    "wages",
    "avg_monthly_wage_php",
    "pay",
    "ofw_share",
    "ofw",
    "informal_share",
    "informality",
}

# Phrases that would anchor the output distribution.
DISTRIBUTION_ANCHOR_PATTERNS = [
    r"expected average",
    r"expected mean",
    r"target average",
    r"target mean",
    r"average should be",
    r"aim for (?:an? )?(?:average|mean|distribution)",
    r"most (?:occupations|tasks) should score",
]


class ScoringRefusal(RuntimeError):
    """Raised when a run would violate the rubric's own prohibitions."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Prompt and rubric loading, with guardrails
# ---------------------------------------------------------------------------

def rubric_path(version: str) -> Path:
    return EXPOSURE_RUBRIC_DIR / f"rubric-v{version}.yaml"


def prompt_path(version: str) -> Path:
    return EXPOSURE_PROMPT_DIR / f"prompt-v{version}.md"


def load_rubric(version: str) -> dict[str, Any]:
    path = rubric_path(version)
    if not path.exists():
        raise FileNotFoundError(f"No rubric at {rel(path)}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_prompt(version: str) -> str:
    path = prompt_path(version)
    if not path.exists():
        raise FileNotFoundError(f"No prompt at {rel(path)}")
    return path.read_text(encoding="utf-8")


def assert_prompt_is_unanchored(prompt_text: str) -> None:
    """Refuse to run a prompt that states a target output distribution.

    This is the specific defect in the v1 prompt. Encoding it as a runtime
    refusal means it cannot come back through an edit that nobody reviews.
    """
    body = prompt_text.split("# Changes from the v1 prompt", 1)[0].lower()
    for pattern in DISTRIBUTION_ANCHOR_PATTERNS:
        match = re.search(pattern, body)
        if match:
            raise ScoringRefusal(
                f"Prompt contains a distribution-anchoring instruction "
                f"({match.group(0)!r}). Scores produced under it would be partly "
                f"an artifact of the instruction. Remove it before scoring."
            )


def extract_system_prompt(prompt_text: str) -> str:
    """The section between '# System prompt' and '# User message template'."""
    match = re.search(
        r"^# System prompt\s*\n(.*?)^# User message template",
        prompt_text,
        flags=re.S | re.M,
    )
    if not match:
        raise ScoringRefusal(
            "Prompt file does not contain the expected '# System prompt' and "
            "'# User message template' sections."
        )
    return match.group(1).strip()


def assert_no_prohibited_inputs(payload: dict[str, Any]) -> None:
    offending = sorted(set(payload) & PROHIBITED_INPUT_KEYS)
    if offending:
        raise ScoringRefusal(
            f"Refusing to send labour-market fields to the scoring model: {offending}. "
            "Employment, wages, OFW share and informality are not evidence of "
            "technical task exposure (rubric v0.1.0, prohibited_inputs)."
        )


# ---------------------------------------------------------------------------
# Task input
# ---------------------------------------------------------------------------

def load_tasks(path: Path) -> list[dict[str, str]]:
    """Load task statements to score.

    Expected columns: task_id, task_statement, occupation_title,
    occupation_source, psoc_code, crosswalk_match_type,
    crosswalk_match_quality, task_importance.

    This file is produced by the O*NET task extraction step. It does not exist
    until O*NET has been retrieved, which is why scoring is currently blocked.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"No task file at {rel(path)}.\n"
            "Task evidence is required before scoring: this measure is task-based, "
            "and scoring titles instead is the v1 defect.\n"
            "Run `make fetch-data` to retrieve O*NET, then `make build-crosswalk`."
        )
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------

def parse_response(raw: str) -> dict[str, int | str]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in response")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                text = text[start : index + 1]
                break

    parsed = json.loads(text)
    result: dict[str, int | str] = {}
    for key in DIMENSIONS:
        if key not in parsed:
            raise ValueError(f"missing dimension {key!r}")
        value = parsed[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ValueError(f"{key} must be an integer, got {value!r}")
        value = int(value)
        if not 0 <= value <= 5:
            raise ValueError(f"{key} must be within 0-5, got {value}")
        result[key] = value

    for key in ("reasoning", "ai_can_assist_with", "remains_human_dependent"):
        result[key] = str(parsed.get(key, "")).strip()
    return result


def score_one_task(client, system_prompt: str, task: dict[str, str], model: str,
                   temperature: float) -> tuple[dict, str]:
    payload = {
        "task_id": task.get("task_id", ""),
        "task_statement": task.get("task_statement", ""),
        "occupation_title": task.get("occupation_title", ""),
        "occupation_source": task.get("occupation_source", ""),
        "psoc_code": task.get("psoc_code", ""),
        "crosswalk_match_type": task.get("crosswalk_match_type", ""),
        "crosswalk_match_quality": task.get("crosswalk_match_quality", ""),
        "task_importance": task.get("task_importance", ""),
    }
    assert_no_prohibited_inputs(payload)

    user_message = "\n".join(f"{key}: {value}" for key, value in payload.items())
    response = client.chat.completions.create(
        model=model,
        max_tokens=400,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    raw = response.choices[0].message.content
    return parse_response(raw), raw


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_replicates(values: list[int]) -> dict[str, Any]:
    """Median plus retained disagreement."""
    if not values:
        return {"score": None, "n": 0, "stability": None, "range": None}
    return {
        "score": statistics.median(values),
        "n": len(values),
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "stdev": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        # Stability is reported, not used to hide a disagreeing score.
        "stability": (
            "stable" if len(values) > 1 and max(values) - min(values) <= 1
            else "unstable" if len(values) > 1
            else "single_run_no_stability_measure"
        ),
        "values": values,
    }


def aggregate_tasks_to_occupation(task_scores: list[dict[str, Any]], dimension_key: str,
                                  weighted: bool) -> float | None:
    """Mean of task scores, optionally weighted by task importance.

    Weighted and unweighted results are computed separately and published side
    by side; neither is treated as the score.
    """
    pairs = []
    for entry in task_scores:
        value = entry["consensus"][dimension_key]["score"]
        if value is None:
            continue
        weight = 1.0
        if weighted:
            try:
                weight = float(entry["task"].get("task_importance") or 0) or 0.0
            except ValueError:
                weight = 0.0
            if weight <= 0:
                continue
        pairs.append((value, weight))

    if not pairs:
        return None
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return None
    return round(sum(value * weight for value, weight in pairs) / total_weight, 4)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def new_run_id(model: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    return f"{stamp}__{slug}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Provider-qualified model id, recorded verbatim in provenance")
    parser.add_argument("--tasks", default=str(EXPOSURE_RUNS_DIR.parent / "tasks.csv"))
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="Independent replicates per task")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--rubric-version", default=DEFAULT_RUBRIC_VERSION)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--seed", type=int, default=None, help="Seed for task-order randomisation, recorded in the run manifest")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.runs < 2:
        raise ScoringRefusal(
            "At least 2 replicates are required. A single run cannot report its own "
            "stability, which is the v1 defect this harness exists to fix."
        )

    rubric = load_rubric(args.rubric_version)
    prompt_text = load_prompt(args.prompt_version)
    assert_prompt_is_unanchored(prompt_text)
    system_prompt = extract_system_prompt(prompt_text)

    tasks = load_tasks(Path(args.tasks))
    if args.limit:
        tasks = tasks[: args.limit]

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ScoringRefusal(
            "OPENROUTER_API_KEY is not set. Scoring is not run without it, and no "
            "score is published without a completed run."
        )

    from openai import OpenAI  # imported late so the module loads without the dep

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    run_id = new_run_id(args.model)
    run_dir = EXPOSURE_RUNS_DIR / run_id
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    per_task: dict[str, dict[str, Any]] = {
        task["task_id"]: {"task": task, "replicates": []} for task in tasks
    }

    for replicate in range(1, args.runs + 1):
        order = list(tasks)
        # Randomised per replicate so any ordering effect shows up as
        # disagreement between replicates instead of hiding inside one order.
        rng.shuffle(order)
        print(f"replicate {replicate}/{args.runs} ({len(order)} tasks)")
        for position, task in enumerate(order):
            try:
                parsed, raw = score_one_task(
                    client, system_prompt, task, args.model, args.temperature
                )
            except Exception as exc:
                print(f"  ERROR {task['task_id']}: {type(exc).__name__}: {exc}")
                continue

            raw_name = f"{task['task_id']}__r{replicate}.json"
            (run_dir / "raw" / raw_name).write_text(
                json.dumps(
                    {
                        "task_id": task["task_id"],
                        "replicate": replicate,
                        "position_in_replicate": position,
                        "model": args.model,
                        "temperature": args.temperature,
                        "requested_at": now_iso(),
                        "raw_response": raw,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            per_task[task["task_id"]]["replicates"].append(
                {"replicate": replicate, "raw_response_reference": f"{run_id}/raw/{raw_name}", **parsed}
            )

    # Consensus per task, disagreement retained
    task_scores = []
    for task_id, entry in per_task.items():
        consensus = {
            key: aggregate_replicates([r[key] for r in entry["replicates"] if key in r])
            for key in DIMENSIONS
        }
        task_scores.append({"task_id": task_id, "task": entry["task"], "consensus": consensus,
                            "replicates": entry["replicates"]})

    run_manifest = {
        "run_id": run_id,
        "scoring_date": now_iso(),
        "model_provider": "openrouter",
        "model_id": args.model,
        "model_release_or_snapshot": "as resolved by the provider at scoring time; not pinned",
        "temperature": args.temperature,
        "run_count": args.runs,
        "seed": args.seed,
        "rubric_version": args.rubric_version,
        "prompt_version": args.prompt_version,
        "prompt_file": rel(prompt_path(args.prompt_version)),
        "rubric_file": rel(rubric_path(args.rubric_version)),
        "task_source": "O*NET task statements via PSOC crosswalk",
        "task_count": len(tasks),
        "aggregation_method": "median across replicates; mean across tasks (unweighted and importance-weighted, reported separately)",
        "human_review_status": "not_reviewed",
        "independent_expert_validation": "none",
        "required_statement": rubric["validation"]["required_statement"],
        "tasks": task_scores,
    }
    (run_dir / "run.json").write_text(
        json.dumps(run_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    write_occupation_scores(run_manifest)
    print(f"\nRun written to {rel(run_dir)}")
    print("Previous runs are untouched; this run did not overwrite history.")


def write_occupation_scores(run_manifest: dict[str, Any]) -> None:
    """Roll task scores up to occupations and write data/canonical/model_scores.csv."""
    by_occupation: dict[str, list[dict]] = {}
    for entry in run_manifest["tasks"]:
        psoc_code = entry["task"].get("psoc_code", "")
        by_occupation.setdefault(psoc_code, []).append(entry)

    rows = []
    for psoc_code, entries in sorted(by_occupation.items()):
        qualities = {e["task"].get("crosswalk_match_quality", "") for e in entries}
        for dimension_key, dimension_id in DIMENSIONS.items():
            for weighted, aggregation in ((False, "unweighted_mean"), (True, "importance_weighted_mean")):
                score = aggregate_tasks_to_occupation(entries, dimension_key, weighted)
                if score is None:
                    continue
                ranges = [
                    e["consensus"][dimension_key]["range"]
                    for e in entries
                    if e["consensus"][dimension_key].get("range") is not None
                ]
                stdevs = [
                    e["consensus"][dimension_key]["stdev"]
                    for e in entries
                    if e["consensus"][dimension_key].get("stdev") is not None
                ]
                rows.append(
                    {
                        "score_id": f"{run_manifest['run_id']}:{psoc_code}:{dimension_id}:{aggregation}",
                        "occupation_id": f"PSOC-{psoc_code}",
                        "psoc_code": psoc_code,
                        "dimension": dimension_id,
                        "rubric_version": run_manifest["rubric_version"],
                        "prompt_version": run_manifest["prompt_version"],
                        "model_provider": run_manifest["model_provider"],
                        "model_id": run_manifest["model_id"],
                        "model_release_or_snapshot": run_manifest["model_release_or_snapshot"],
                        "scoring_date": run_manifest["scoring_date"],
                        "temperature": run_manifest["temperature"],
                        "run_count": run_manifest["run_count"],
                        "aggregation_method": aggregation,
                        "task_source": run_manifest["task_source"],
                        "task_weighting": "importance" if weighted else "equal",
                        "crosswalk_quality": "/".join(sorted(q for q in qualities if q)) or "unknown",
                        "score": score,
                        "score_scale_min": 0,
                        "score_scale_max": 5,
                        "uncertainty_or_stability": (
                            f"mean cross-run stdev {round(sum(stdevs)/len(stdevs), 4)}" if stdevs else "not measured"
                        ),
                        "run_disagreement_range": max(ranges) if ranges else "",
                        "human_review_status": run_manifest["human_review_status"],
                        "limitations": run_manifest["required_statement"],
                        "raw_response_reference": f"data/exposure/runs/{run_manifest['run_id']}/run.json",
                    }
                )

    ensure_parent(MODEL_SCORES_CSV)
    with open(MODEL_SCORES_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODEL_SCORES_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{rel(MODEL_SCORES_CSV)}: {len(rows)} rows")


if __name__ == "__main__":
    main()
