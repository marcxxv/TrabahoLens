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

from .exposure_runs import (
    DEFAULT_MIN_SUCCESSFUL_ATTEMPTS,
    AttemptRecord,
    TaskRunRecord,
    aggregate_tasks_ordinal,
    ordinal_summary,
)
from .paths import (
    EXPOSURE_PROMPT_DIR,
    EXPOSURE_RUBRIC_DIR,
    EXPOSURE_RUNS_DIR,
    MODEL_SCORES_CSV,
    ensure_parent,
    rel,
)
from .schema import MODEL_SCORES_COLUMNS

DEFAULT_RUBRIC_VERSION = "0.2.0"
DEFAULT_PROMPT_VERSION = "0.2.0"
DEFAULT_RUNS = 3  # repeated scoring attempts, not independent replicates
DEFAULT_TEMPERATURE = 0.0

#: Dimensions the MODEL is asked to score. C and D are deliberately absent.
#:
#: C (adoption friction) asked the model to judge Philippine regulation,
#: liability, connectivity, device access, employer scale and informality while
#: giving it no Philippine evidence for any of them. It is removed from model
#: scoring entirely and redefined as a future evidence-based contextual layer.
#:
#: D (evidence confidence) is determined by metadata the pipeline already holds
#: — task source, crosswalk quality, Philippine specificity, review status,
#: successful-attempt coverage. It is computed deterministically by
#: `compute_evidence_confidence`, not asked of the model that produced the score.
MODEL_SCORED_DIMENSIONS = {
    "technical_task_exposure": "A",
    "human_interaction_intensity": "B",
}

#: Retained for readers of older run manifests.
RETIRED_MODEL_DIMENSIONS = {
    "adoption_friction": "C — removed: unsupported model judgment about Philippine conditions",
    "evidence_confidence": "D — removed: now computed deterministically from provenance",
}

DIMENSIONS = MODEL_SCORED_DIMENSIONS

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
    # Scan only the operative prompt, not the changelog beneath it. A prompt
    # file documents what it changed, and that documentation necessarily quotes
    # the anchor it removed — scanning it would make an honest changelog
    # unpublishable.
    body = re.split(r"^# Changes from", prompt_text, maxsplit=1, flags=re.M)[0].lower()
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


def assert_no_prohibited_inputs(payload: Any, _trail: str = "") -> None:
    """Refuse labour-market fields anywhere in the payload, at any depth.

    The previous version checked ``set(payload) & PROHIBITED_INPUT_KEYS`` — top
    level only — so a nested dict carrying ``ofw_share`` would have passed
    straight through to the model.
    """
    offending: list[str] = []

    def walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{trail}.{key}" if trail else str(key)
                if str(key).strip().lower() in PROHIBITED_INPUT_KEYS:
                    offending.append(here)
                walk(value, here)
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                walk(value, f"{trail}[{index}]")

    walk(payload, _trail)
    if offending:
        raise ScoringRefusal(
            f"Refusing to send labour-market fields to the scoring model: {sorted(offending)}. "
            "Employment, wages, OFW share and informality are not evidence of "
            "technical task exposure (rubric v0.2.0, prohibited_inputs)."
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
    for key in MODEL_SCORED_DIMENSIONS:
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


def score_one_task(
    client,
    system_prompt: str,
    task: dict[str, str],
    model: str,
    temperature: float,
    attempt_index: int = 1,
    retry_of: int | None = None,
) -> AttemptRecord:
    """One model call. Returns an AttemptRecord whether it succeeds or fails.

    Failures used to be printed and dropped. They are now first-class records,
    so a run's provenance can never claim more successes than it had.
    """
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
    request_payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    record = AttemptRecord(
        task_id=payload["task_id"],
        attempt_index=attempt_index,
        status="request_failed",
        requested_at=now_iso(),
        model_id=model,
        temperature=temperature,
        request_payload=request_payload,
        retry_of_attempt=retry_of,
    )

    try:
        response = client.chat.completions.create(**request_payload)
    except Exception as exc:
        record.completed_at = now_iso()
        record.error_type = type(exc).__name__
        record.error_message = str(exc)[:2000]
        return record

    record.completed_at = now_iso()
    record.raw_response = response.choices[0].message.content
    record.provider_request_id = str(getattr(response, "id", "") or "")
    record.resolved_model_id = str(getattr(response, "model", "") or "")

    try:
        record.parsed = parse_response(record.raw_response)
        record.status = "succeeded"
        record.parser_status = "ok"
    except Exception as exc:
        record.status = "parse_failed"
        record.parser_status = f"{type(exc).__name__}: {exc}"
        record.error_type = type(exc).__name__
        record.error_message = str(exc)[:2000]
    return record


# ---------------------------------------------------------------------------
# Evidence confidence (dimension D) — computed, never asked of the model
# ---------------------------------------------------------------------------

#: Ordered worst to best, matching the rubric's 0-5 anchors.
EVIDENCE_CONFIDENCE_ANCHORS = {
    0: "No usable task evidence; little more than a guess from a title.",
    1: "Title and a short description only.",
    2: "Task text from a proxy classification with a weak crosswalk.",
    3: "Task text from a proxy classification with a defensible crosswalk.",
    4: "Task text with importance weights and a close crosswalk.",
    5: "Philippine-specific task evidence for this occupation.",
}

_CROSSWALK_QUALITY_CEILING = {"high": 4, "medium": 3, "low": 2, "none": 0, "": 0}
_MATCH_TYPE_CEILING = {
    "exact": 4, "close": 4, "narrower": 3, "broader": 3,
    "composite": 2, "no_defensible_match": 0, "": 0,
}


def compute_evidence_confidence(
    *,
    task_statement: str,
    task_importance: str | float | None,
    crosswalk_match_quality: str,
    crosswalk_match_type: str,
    task_source_is_philippine: bool,
    successful_attempts: int,
    minimum_attempts: int,
    human_review_status: str = "not_reviewed",
) -> tuple[int, list[str]]:
    """Derive dimension D from provenance. Returns (score, reasons).

    Asking the scoring model how confident we should be in its own score
    conflates the measurement with its evaluation. Everything D depends on is
    metadata we already hold, so it is computed by rule and the components are
    published alongside the number.
    """
    reasons: list[str] = []

    if not (task_statement or "").strip():
        return 0, ["No task statement: nothing to score but a title."]

    score = 1
    reasons.append("Task statement present.")

    ceiling = min(
        _CROSSWALK_QUALITY_CEILING.get((crosswalk_match_quality or "").lower(), 0),
        _MATCH_TYPE_CEILING.get((crosswalk_match_type or "").lower(), 0),
    )
    if ceiling == 0:
        reasons.append(
            f"Crosswalk unusable (quality={crosswalk_match_quality or 'unrecorded'}, "
            f"type={crosswalk_match_type or 'unrecorded'})."
        )
        return min(score, 1), reasons

    score = max(score, 2)
    reasons.append(
        f"Crosswalk quality {crosswalk_match_quality}, match type {crosswalk_match_type}."
    )

    has_importance = False
    try:
        has_importance = task_importance is not None and float(task_importance) > 0
    except (TypeError, ValueError):
        has_importance = False
    if has_importance:
        score = min(ceiling, 4)
        reasons.append("Task importance rating available.")
    else:
        score = min(ceiling, 3)
        reasons.append("No task importance rating; weighting unavailable.")

    if task_source_is_philippine:
        score = 5
        reasons.append("Philippine-specific task evidence.")
    else:
        reasons.append("Task evidence is US-derived (O*NET), carried across by crosswalk.")

    if successful_attempts < minimum_attempts:
        score = min(score, 1)
        reasons.append(
            f"Only {successful_attempts} successful scoring attempt(s); "
            f"{minimum_attempts} required."
        )
    elif successful_attempts == minimum_attempts:
        reasons.append(f"Minimum attempt coverage met ({successful_attempts}).")
    else:
        reasons.append(f"Attempt coverage above minimum ({successful_attempts}).")

    if human_review_status == "human_reviewed":
        reasons.append("Human-reviewed.")
    else:
        score = min(score, 4)
        reasons.append("Not human-reviewed, so capped below the top anchor.")

    return score, reasons


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
    """Timestamp plus a random suffix.

    A bare second-resolution timestamp collides if two runs start in the same
    second, and a collision would have one run overwrite another's raw
    responses — exactly the history loss the harness is supposed to prevent.
    """
    import secrets

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    return f"{stamp}__{slug}__{secrets.token_hex(4)}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Provider-qualified model id, recorded verbatim in provenance")
    parser.add_argument("--tasks", default=str(EXPOSURE_RUNS_DIR.parent / "tasks.csv"))
    parser.add_argument("--attempts", type=int, default=DEFAULT_RUNS,
                        help="Repeated scoring attempts per task (not independent replicates)")
    parser.add_argument("--min-successful", type=int, default=DEFAULT_MIN_SUCCESSFUL_ATTEMPTS,
                        help="Minimum SUCCESSFUL attempts before a task may be published")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--rubric-version", default=DEFAULT_RUBRIC_VERSION)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--exposure-threshold", type=int, default=4,
                        help="Predeclared dimension-A threshold for the share-above statistic")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.attempts < 2:
        raise ScoringRefusal(
            "At least 2 scoring attempts are required. A single attempt cannot "
            "report its own reproducibility."
        )
    if args.min_successful < 2:
        raise ScoringRefusal("--min-successful must be at least 2.")
    if args.min_successful > args.attempts:
        raise ScoringRefusal(
            f"--min-successful ({args.min_successful}) cannot exceed --attempts ({args.attempts})."
        )

    rubric = load_rubric(args.rubric_version)
    prompt_text = load_prompt(args.prompt_version)
    assert_prompt_is_unanchored(prompt_text)
    system_prompt = extract_system_prompt(prompt_text)

    tasks = load_tasks(Path(args.tasks))
    validate_task_inputs(tasks)
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
    (run_dir / "attempts").mkdir(parents=True, exist_ok=True)

    records = {task["task_id"]: TaskRunRecord(task_id=task["task_id"], task=task) for task in tasks}

    for attempt_index in range(1, args.attempts + 1):
        print(f"attempt pass {attempt_index}/{args.attempts} ({len(tasks)} tasks)")
        for task in tasks:
            record = score_one_task(
                client, system_prompt, task, args.model, args.temperature,
                attempt_index=attempt_index,
            )
            records[task["task_id"]].attempts.append(record)
            # Every attempt is written, successful or not. A failure that leaves
            # no trace is how a run comes to claim more coverage than it had.
            (run_dir / "attempts" / f"{task['task_id']}__a{attempt_index}.json").write_text(
                json.dumps(record.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
            )
            if record.status != "succeeded":
                print(f"  {task['task_id']} attempt {attempt_index}: {record.status} "
                      f"({record.error_type}: {record.error_message[:80]})")

    manifest = build_run_manifest(records, args, run_id, rubric)
    (run_dir / "run.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    write_occupation_scores(manifest)

    print(f"\nRun written to {rel(run_dir)}")
    print(f"  tasks meeting the {args.min_successful}-success minimum: "
          f"{manifest['tasks_meeting_minimum']} of {manifest['task_count']}")
    if manifest["tasks_below_minimum"]:
        print(f"  EXCLUDED (insufficient successful attempts): {manifest['tasks_below_minimum']}")
    print("Previous runs are untouched; this run did not overwrite history.")


def validate_task_inputs(tasks: list[dict[str, str]]) -> None:
    """Reject malformed task input before a single model call is made."""
    required = {"task_id", "task_statement", "psoc_code"}
    problems: list[str] = []
    seen: set[str] = set()

    if not tasks:
        raise ScoringRefusal("Task file contains no rows.")

    for index, task in enumerate(tasks):
        missing = required - set(task)
        if missing:
            problems.append(f"row {index}: missing columns {sorted(missing)}")
            continue
        task_id = (task.get("task_id") or "").strip()
        if not task_id:
            problems.append(f"row {index}: empty task_id")
        elif task_id in seen:
            problems.append(f"row {index}: duplicate task_id {task_id!r}")
        else:
            seen.add(task_id)
        if not (task.get("task_statement") or "").strip():
            problems.append(f"row {index} ({task_id}): empty task_statement")
        if (task.get("crosswalk_match_type") or "").strip() == "no_defensible_match":
            problems.append(
                f"row {index} ({task_id}): crosswalk match type is no_defensible_match; "
                "an occupation with no defensible mapping must not be scored"
            )
        if (task.get("crosswalk_review_status") or "").strip() == "rejected":
            problems.append(
                f"row {index} ({task_id}): crosswalk is rejected; refusing to score through it"
            )
        importance = (task.get("task_importance") or "").strip()
        if importance:
            try:
                value = float(importance)
            except ValueError:
                problems.append(f"row {index} ({task_id}): unparseable task_importance {importance!r}")
            else:
                if not 0 < value <= 5:
                    problems.append(
                        f"row {index} ({task_id}): task_importance {value} outside the O*NET 1-5 scale"
                    )

    versions = {(t.get("task_source_version") or "").strip() for t in tasks}
    versions.discard("")
    if len(versions) > 1:
        problems.append(
            f"tasks mix task-source versions {sorted(versions)}; scores from different "
            "O*NET releases are not comparable within one run"
        )

    if problems:
        raise ScoringRefusal("Task input validation failed:\n  " + "\n  ".join(problems))


def build_run_manifest(records, args, run_id: str, rubric: dict) -> dict[str, Any]:
    """Assemble the run manifest from attempts that actually happened."""
    task_entries = []
    meeting = 0
    below: list[str] = []

    for task_id, record in records.items():
        consensus = {
            dimension: ordinal_summary(record.successful_values(dimension))
            for dimension in MODEL_SCORED_DIMENSIONS
        }
        confidence, reasons = compute_evidence_confidence(
            task_statement=record.task.get("task_statement", ""),
            task_importance=record.task.get("task_importance"),
            crosswalk_match_quality=record.task.get("crosswalk_match_quality", ""),
            crosswalk_match_type=record.task.get("crosswalk_match_type", ""),
            task_source_is_philippine=(
                record.task.get("occupation_source", "").strip().lower().startswith("ph")
            ),
            successful_attempts=record.successful,
            minimum_attempts=args.min_successful,
        )
        entry = record.as_dict(args.min_successful)
        entry["consensus"] = consensus
        entry["evidence_confidence"] = {
            "score": confidence,
            "scale_max": 5,
            "computed": True,
            "reasons": reasons,
            "anchor": EVIDENCE_CONFIDENCE_ANCHORS.get(confidence, ""),
        }
        task_entries.append(entry)

        if record.meets_minimum(args.min_successful):
            meeting += 1
        else:
            below.append(task_id)

    included = [e for e in task_entries if e["meets_minimum_successful_attempts"]]
    occupation_rollup: dict[str, Any] = {}
    by_psoc: dict[str, list[dict]] = {}
    for entry in included:
        by_psoc.setdefault(entry["task"].get("psoc_code", ""), []).append(entry)
    for psoc_code, entries in by_psoc.items():
        occupation_rollup[psoc_code] = {
            dimension: aggregate_tasks_ordinal(entries, dimension, args.exposure_threshold)
            for dimension in MODEL_SCORED_DIMENSIONS
        }
        occupation_rollup[psoc_code]["tasks_included"] = len(entries)
        occupation_rollup[psoc_code]["tasks_total_for_occupation"] = sum(
            1 for e in task_entries if e["task"].get("psoc_code") == psoc_code
        )
        occupation_rollup[psoc_code]["partial_coverage"] = (
            occupation_rollup[psoc_code]["tasks_included"]
            != occupation_rollup[psoc_code]["tasks_total_for_occupation"]
        )

    total_attempts = sum(len(r.attempts) for r in records.values())
    total_success = sum(r.successful for r in records.values())

    return {
        "run_id": run_id,
        "scoring_date": now_iso(),
        "model_provider": "openrouter",
        "model_id": args.model,
        "model_release_or_snapshot": "as resolved by the provider at scoring time; not pinned",
        "resolved_model_ids": sorted({
            a.resolved_model_id for r in records.values() for a in r.attempts if a.resolved_model_id
        }),
        "temperature": args.temperature,
        # Vocabulary: repeated attempts, not independent replicates. Each task is
        # a separate request, so this measures run-to-run reproducibility and
        # provider variability, not statistical independence.
        "attempted_replicates": args.attempts,
        "min_successful_replicates": args.min_successful,
        "attempt_semantics": (
            "Repeated scoring attempts against the same prompt. At temperature 0 "
            "these measure run-to-run reproducibility and provider variability. "
            "They are not statistically independent samples and are not described "
            "as replicates in the statistical sense."
        ),
        "total_attempts": total_attempts,
        "total_successful_attempts": total_success,
        "total_failed_attempts": total_attempts - total_success,
        "rubric_version": args.rubric_version,
        "prompt_version": args.prompt_version,
        "prompt_file": rel(prompt_path(args.prompt_version)),
        "rubric_file": rel(rubric_path(args.rubric_version)),
        "task_source": "O*NET task statements via PSOC crosswalk",
        "task_count": len(records),
        "tasks_meeting_minimum": meeting,
        "tasks_below_minimum": below,
        "exposure_threshold": args.exposure_threshold,
        "aggregation_method": (
            "median across attempts; median across tasks with IQR and full category "
            "distribution (ordinal-safe). An arithmetic mean is reported beside it, "
            "labelled an experimental convenience statistic."
        ),
        "human_review_status": "not_reviewed",
        "independent_expert_validation": "none",
        "required_statement": rubric["validation"]["required_statement"],
        "occupation_rollup": occupation_rollup,
        "tasks": task_entries,
    }


def write_occupation_scores(run_manifest: dict[str, Any]) -> None:
    """Write data/canonical/model_scores.csv from tasks that met the minimum.

    A task below the minimum number of *successful* attempts contributes
    nothing. Partial occupation coverage is recorded on every row it affects,
    so a reader sees that some of the occupation's tasks were dropped.
    """
    rows = []
    rollup = run_manifest.get("occupation_rollup", {})

    for psoc_code, dimensions in sorted(rollup.items()):
        included = dimensions.get("tasks_included", 0)
        total = dimensions.get("tasks_total_for_occupation", 0)
        partial = dimensions.get("partial_coverage", False)

        task_entries = [
            e for e in run_manifest["tasks"]
            if e["task"].get("psoc_code") == psoc_code
            and e["meets_minimum_successful_attempts"]
        ]
        qualities = {e["task"].get("crosswalk_match_quality", "") for e in task_entries}
        confidences = [e["evidence_confidence"]["score"] for e in task_entries]
        agreements = [
            e["consensus"][d]["agreement"]
            for e in task_entries for d in MODEL_SCORED_DIMENSIONS
            if e["consensus"][d].get("agreement") is not None
        ]

        for dimension_key, dimension_id in MODEL_SCORED_DIMENSIONS.items():
            summary = dimensions.get(dimension_key, {})
            if summary.get("median") is None:
                continue
            rows.append({
                "score_id": f"{run_manifest['run_id']}:{psoc_code}:{dimension_id}:median",
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
                "run_count": run_manifest["min_successful_replicates"],
                "attempted_attempts": run_manifest["attempted_replicates"],
                "successful_attempts": min(
                    (e["successful_attempts"] for e in task_entries), default=0
                ),
                "aggregation_method": "median_across_tasks_ordinal",
                "task_source": run_manifest["task_source"],
                "task_weighting": "none (ordinal median)",
                "tasks_included": included,
                "tasks_total_for_occupation": total,
                "partial_coverage": "true" if partial else "false",
                "crosswalk_quality": "/".join(sorted(q for q in qualities if q)) or "unknown",
                "score": summary["median"],
                "score_scale_min": 0,
                "score_scale_max": 5,
                "score_iqr_lower": summary.get("iqr_lower", ""),
                "score_iqr_upper": summary.get("iqr_upper", ""),
                "score_distribution": json.dumps(summary.get("distribution", {})),
                "share_at_or_above_threshold": summary.get("share_of_tasks_at_or_above_threshold", ""),
                "experimental_arithmetic_mean": summary.get("experimental_arithmetic_mean", ""),
                "evidence_confidence": min(confidences) if confidences else "",
                "uncertainty_or_stability": (
                    f"modal-category agreement {round(sum(agreements)/len(agreements), 4)}"
                    if agreements else "not measured"
                ),
                "run_disagreement_range": max(
                    (e["consensus"][d].get("range", 0) or 0
                     for e in task_entries for d in MODEL_SCORED_DIMENSIONS),
                    default="",
                ),
                "human_review_status": run_manifest["human_review_status"],
                "limitations": run_manifest["required_statement"],
                "raw_response_reference": f"data/exposure/runs/{run_manifest['run_id']}/run.json",
            })

    ensure_parent(MODEL_SCORES_CSV)
    with open(MODEL_SCORES_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODEL_SCORES_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{rel(MODEL_SCORES_CSV)}: {len(rows)} rows")


if __name__ == "__main__":
    main()
