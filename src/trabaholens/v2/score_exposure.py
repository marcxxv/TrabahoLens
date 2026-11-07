"""Task-first generative-AI exposure scoring harness.

Differences from the v1 scorer, each answering a specific audit finding:

* Scores **tasks**, not occupation titles, and aggregates upward.
* Runs **N repeated scoring attempts** per task to measure run-to-run agreement;
  these are not claimed to be statistically independent replicates.
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
    CROSSWALK_CSV,
    EXPOSURE_PROMPT_DIR,
    EXPOSURE_RUBRIC_DIR,
    EXPOSURE_RUNS_DIR,
    MODEL_SCORES_CSV,
    OCCUPATIONS_CSV,
    ensure_parent,
    rel,
)
from .psoc_tasks import NATIVE_CROSSWALK_ID, NATIVE_NOT_APPLICABLE, OCCUPATION_SOURCE, TASKS_CSV
from .schema import MODEL_SCORES_COLUMNS

DEFAULT_RUBRIC_VERSION = "0.3.0"
DEFAULT_PROMPT_VERSION = "0.3.0"
DEFAULT_RUNS = 3  # repeated scoring attempts, not independent replicates
DEFAULT_TEMPERATURE = 0.0
#: Recorded retries per attempt slot after a failed or unparseable call.
MAX_RETRIES = 2

#: OpenAI-compatible scoring providers. `nyolab` is the low-cost provider used
#: for pilots and full-coverage runs; its key is read from the environment and
#: never written to disk. `claude-cli` is handled separately (no HTTP API).
PROVIDER_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "nyolab": "https://llm.nyolab.ai/api/public/v1",
}
PROVIDER_KEY_ENVS = {
    "openrouter": "OPENROUTER_API_KEY",
    "nyolab": "NYOLAB_API_KEY",
}
#: NYO's reasoning models charge reasoning tokens against max_tokens, so a
#: 400-token budget can be spent before any answer is written.
NYOLAB_MAX_TOKENS = 2400

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
    max_tokens: int = 400,
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
        "max_tokens": max_tokens,
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
    record.provider_metadata = dict(getattr(response, "provider_metadata", {}) or {})
    usage = getattr(response, "usage", None)
    if usage is not None and "usage" not in record.provider_metadata:
        record.provider_metadata["usage"] = (
            usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
        )

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

    if task_source_is_philippine and (crosswalk_match_type or "") == NATIVE_NOT_APPLICABLE:
        # PSA's own task text for the canonical unit group: there is no
        # crosswalk to degrade it, so the crosswalk ceiling does not apply.
        ceiling = 5
        reasons.append("Task text is PSA's own PSOC task statement; no crosswalk involved.")
    else:
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
        reasons.append(
            f"Crosswalk quality {crosswalk_match_quality}, match type {crosswalk_match_type}."
        )

    score = max(score, 2)

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


class HttpChatClient:
    """Minimal chat-completions client for an OpenAI-compatible endpoint.

    Used for NYO because the OpenAI SDK hangs against that endpoint from this
    machine even with a short timeout and no retries, while httpx and curl
    return in about two seconds. It sends the same request body and returns the
    same response shape, so nothing downstream changes.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.chat = self
        self.completions = self

    def create(self, *, model, messages, temperature=None, max_tokens=None, **_ignored):
        import httpx
        from types import SimpleNamespace

        body: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:400]}")
        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=choice["message"]["content"]))],
            id=data.get("id", ""),
            model=data.get("model", ""),
            provider_metadata={"usage": usage} if usage else {},
        )


def build_openai_client(provider: str):
    """Client for an OpenAI-compatible scoring provider.

    Refuses before any call when the provider's key is missing: a run with no
    provider cannot honestly produce a score, and a run with no recorded model
    has no provenance.
    """
    if provider not in PROVIDER_BASE_URLS:
        raise ScoringRefusal(f"Unknown scoring provider {provider!r}.")
    env = PROVIDER_KEY_ENVS[provider]
    api_key = os.environ.get(env)
    if not api_key:
        raise ScoringRefusal(
            f"{env} is not set. {provider} scoring is not run without its key, and "
            "no score is published without a completed run. Use --provider "
            "claude-cli on a machine with an authenticated Claude Code CLI."
        )
    if provider == "nyolab":
        return HttpChatClient(PROVIDER_BASE_URLS[provider], api_key)
    from openai import OpenAI  # imported late so the module loads without the dep

    return OpenAI(api_key=api_key, base_url=PROVIDER_BASE_URLS[provider], timeout=180.0)


class ClaudeCliClient:
    """Minimal chat-completions shape over the Claude Code CLI.

    Used when no API key is configured but the machine has an authenticated
    `claude` CLI. Each call is a fresh, tool-less session with the rubric as the
    entire system prompt, run from an empty directory so no project files or
    memory reach the model. Temperature is not settable through the CLI; the
    run manifest says so instead of recording a value that was not applied.
    """

    def __init__(self, timeout: int = 240):
        import tempfile

        self.timeout = timeout
        self.workdir = tempfile.mkdtemp(prefix="trabaholens-scoring-")
        self.chat = self
        self.completions = self

    def create(self, *, model, messages, **_ignored):
        import subprocess
        from types import SimpleNamespace

        system = next(m["content"] for m in messages if m["role"] == "system")
        user = next(m["content"] for m in messages if m["role"] == "user")
        command = [
            "claude", "-p", "--output-format", "json", "--model", model,
            "--system-prompt", system, "--tools", "", "--setting-sources", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--no-chrome",
            "--disable-slash-commands", "--exclude-dynamic-system-prompt-sections",
            "--no-session-persistence",
        ]
        completed = subprocess.run(
            command, input=user, capture_output=True, text=True,
            timeout=self.timeout, cwd=self.workdir,
        )
        text = completed.stdout
        try:
            result = json.loads(text[text.index("{"): text.rindex("}") + 1])
        except ValueError as exc:
            raise RuntimeError(f"CLI returned no JSON (exit {completed.returncode}): "
                               f"{(completed.stderr or text)[:500]}") from exc
        if result.get("is_error") or result.get("subtype") != "success":
            raise RuntimeError(f"CLI error: {str(result.get('result', ''))[:500]}")
        usage = result.get("modelUsage") or {}
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=result.get("result", "")))],
            id=result.get("session_id", ""),
            model=",".join(sorted(usage)) or model,
            provider_metadata={
                "cost_usd_list": result.get("total_cost_usd"),
                "duration_ms": result.get("duration_ms"),
                "usage": result.get("usage", {}),
            },
        )


def _select_tasks(tasks: list[dict[str, str]], args) -> list[dict[str, str]]:
    """Deterministic subsets for pilots. Never random: a pilot must be replayable."""
    if args.occupations:
        wanted = {c.strip() for c in args.occupations.split(",") if c.strip()}
        tasks = [t for t in tasks if t["psoc_code"] in wanted]
    if args.sample_every:
        codes = sorted({t["psoc_code"] for t in tasks})
        keep = set(codes[:: args.sample_every])
        tasks = [t for t in tasks if t["psoc_code"] in keep]
    if args.limit:
        tasks = tasks[: args.limit]
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="",
                        help="Provider-qualified model id, recorded verbatim in provenance. "
                             "Required to score; not needed with --publish-run, which reads the "
                             "model from the run manifest.")
    parser.add_argument("--provider", choices=["openrouter", "claude-cli", "nyolab"], default="openrouter")
    parser.add_argument("--tasks", default=str(TASKS_CSV))
    parser.add_argument("--attempts", type=int, default=DEFAULT_RUNS,
                        help="Repeated scoring attempts per task (not independent replicates)")
    parser.add_argument("--min-successful", type=int, default=DEFAULT_MIN_SUCCESSFUL_ATTEMPTS,
                        help="Minimum SUCCESSFUL attempts before a task may be published")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=None,
                        help="Output budget per call (default 400; 2400 for nyolab, whose "
                             "reasoning tokens count against the same budget)")
    parser.add_argument("--rubric-version", default=DEFAULT_RUBRIC_VERSION)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT_VERSION)
    parser.add_argument("--exposure-threshold", type=int, default=4,
                        help="Predeclared dimension-A threshold for the share-above statistic")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--occupations", default="", help="Comma-separated PSOC unit codes to score")
    parser.add_argument("--sample-every", type=int, default=0,
                        help="Deterministic pilot: every Nth unit group in code order")
    parser.add_argument("--workers", type=int, default=1, help="Parallel model calls")
    parser.add_argument("--resume", default="", help="Existing run id to complete; finished attempts are kept")
    parser.add_argument("--no-publish", action="store_true",
                        help="Write the run only; leave data/canonical/model_scores.csv untouched")
    parser.add_argument("--publish-run", default="",
                        help="Publish an existing complete run to model_scores.csv without scoring")
    parser.add_argument("--allow-partial", action="store_true",
                        help="With --publish-run, allow a pilot subset (for local previews only)")
    args = parser.parse_args()

    if args.max_tokens is None:
        args.max_tokens = NYOLAB_MAX_TOKENS if args.provider == "nyolab" else 400

    if args.publish_run:
        publish_run(args.publish_run, allow_partial=args.allow_partial)
        return

    if not args.model:
        parser.error("--model is required unless --publish-run supplies a finished run")

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
    tasks = _select_tasks(tasks, args)
    if not tasks:
        raise ScoringRefusal("Task selection is empty.")

    if args.provider == "claude-cli":
        client = ClaudeCliClient()
        args.temperature = None
    else:
        client = build_openai_client(args.provider)

    run_id = args.resume or new_run_id(args.model)
    run_dir = EXPOSURE_RUNS_DIR / run_id
    if args.resume and not run_dir.exists():
        raise ScoringRefusal(f"No run {run_id!r} to resume.")
    (run_dir / "attempts").mkdir(parents=True, exist_ok=True)

    records = {task["task_id"]: TaskRunRecord(task_id=task["task_id"], task=task) for task in tasks}
    from concurrent.futures import ThreadPoolExecutor

    def attempt(job):
        """One attempt slot: the call, plus at most MAX_RETRIES recorded retries.

        A retry is a new call, recorded as its own attempt with retry_of_attempt
        set. The failed call stays on disk and in the manifest, so attempt counts
        include it; only successes count toward the minimum.
        """
        attempt_index, task = job
        made: list[tuple[AttemptRecord, bool]] = []
        for retry in range(MAX_RETRIES + 1):
            suffix = "" if retry == 0 else f"__retry{retry}"
            path = run_dir / "attempts" / f"{task['task_id']}__a{attempt_index}{suffix}.json"
            if path.exists():
                # Resuming: a finished attempt is evidence, never redone or replaced.
                record = AttemptRecord(**json.loads(path.read_text(encoding="utf-8")))
                made.append((record, False))
            else:
                record = score_one_task(client, system_prompt, task, args.model, args.temperature,
                                        attempt_index=attempt_index,
                                        retry_of=attempt_index if retry else None,
                                        max_tokens=args.max_tokens)
                # Every attempt is written, successful or not. A failure that leaves
                # no trace is how a run comes to claim more coverage than it had.
                path.write_text(json.dumps(record.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                made.append((record, True))
            if record.status == "succeeded":
                break
        return made

    spent = 0.0
    cost_reported = False
    for attempt_index in range(1, args.attempts + 1):
        print(f"attempt pass {attempt_index}/{args.attempts} ({len(tasks)} tasks, {args.workers} workers)", flush=True)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            for done, made in enumerate(pool.map(attempt, [(attempt_index, t) for t in tasks]), 1):
                for record, fresh in made:
                    records[record.task_id].attempts.append(record)
                    cost = (record.provider_metadata or {}).get("cost_usd_list")
                    if cost is not None:
                        cost_reported = True
                        spent += float(cost) if fresh else 0.0
                    if record.status != "succeeded":
                        print(f"  {record.task_id} attempt {attempt_index}: {record.status} "
                              f"({record.error_type}: {record.error_message[:80]})", flush=True)
                if done % 100 == 0:
                    suffix = f" · list cost so far ${spent:.2f}" if cost_reported else ""
                    print(f"  {done}/{len(tasks)}{suffix}", flush=True)

    manifest = build_run_manifest(records, args, run_id, rubric)
    manifest["selection"] = {
        "occupations": args.occupations, "sample_every": args.sample_every, "limit": args.limit,
        "complete_task_file": not (args.occupations or args.sample_every or args.limit),
    }
    manifest["provider_cost_usd_list_this_invocation"] = round(spent, 4) if cost_reported else None
    (run_dir / "run.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if args.no_publish:
        print("--no-publish: model_scores.csv left unchanged.")
    else:
        write_occupation_scores(manifest)

    print(f"\nRun written to {rel(run_dir)}")
    print(f"  tasks meeting the {args.min_successful}-success minimum: "
          f"{manifest['tasks_meeting_minimum']} of {manifest['task_count']}")
    if manifest["tasks_below_minimum"]:
        print(f"  EXCLUDED (insufficient successful attempts): {manifest['tasks_below_minimum']}")
    if cost_reported:
        print(f"  provider list cost this invocation: ${spent:.2f}")
    else:
        print("  provider reported no per-call list cost; token usage is recorded per attempt")
    print("Previous runs are untouched; this run did not overwrite history.")


def validate_task_inputs(
    tasks: list[dict[str, str]], *, canonical_codes: set[str] | None = None,
    accepted_crosswalks: set[tuple[str, str, str]] | None = None,
) -> None:
    """Reject malformed task input before a single model call is made."""
    required = {
        "task_id", "task_statement", "psoc_code", "onet_soc_code", "crosswalk_id",
        "crosswalk_match_type", "crosswalk_match_quality", "crosswalk_review_status",
        "task_source_version",
    }
    problems: list[str] = []
    seen: set[str] = set()

    if canonical_codes is None:
        with open(OCCUPATIONS_CSV, encoding="utf-8", newline="") as handle:
            canonical_codes = {row["psoc_code"] for row in csv.DictReader(handle)}
    if accepted_crosswalks is None:
        with open(CROSSWALK_CSV, encoding="utf-8", newline="") as handle:
            accepted_crosswalks = {
                (row["crosswalk_id"], row["psoc_code"], row["source_code"])
                for row in csv.DictReader(handle)
                if row.get("source_classification") == "O*NET-SOC"
                and row.get("review_status") == "human_reviewed"
                and row.get("match_quality") in {"high", "medium"}
                and row.get("mapping_basis") not in {"title_similarity_only", "undocumented_heuristic"}
            }

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
        psoc_code = (task.get("psoc_code") or "").strip()
        onet_code = (task.get("onet_soc_code") or "").strip()
        crosswalk_id = (task.get("crosswalk_id") or "").strip()
        if psoc_code and psoc_code not in canonical_codes:
            problems.append(f"row {index} ({task_id}): unknown canonical PSOC code {psoc_code!r}")
        if crosswalk_id == NATIVE_CROSSWALK_ID:
            # PSA's own task statement for a canonical unit group. No crosswalk
            # exists, so none can be claimed as reviewed; every crosswalk field
            # must say "not applicable" rather than borrow a reviewed status.
            if onet_code:
                problems.append(f"row {index} ({task_id}): a native PSOC task cannot carry an O*NET code")
            if len(psoc_code) != 4:
                problems.append(f"row {index} ({task_id}): native tasks must belong to a PSOC unit group")
            if (task.get("occupation_source") or "").strip() != OCCUPATION_SOURCE:
                problems.append(f"row {index} ({task_id}): native task source must be {OCCUPATION_SOURCE}")
            for key in ("crosswalk_match_type", "crosswalk_match_quality", "crosswalk_review_status"):
                if (task.get(key) or "").strip() != NATIVE_NOT_APPLICABLE:
                    problems.append(f"row {index} ({task_id}): {key} must be {NATIVE_NOT_APPLICABLE}")
            continue
        if onet_code and (crosswalk_id, psoc_code, onet_code) not in accepted_crosswalks:
            problems.append(
                f"row {index} ({task_id}): no accepted human-reviewed crosswalk for "
                f"{psoc_code!r} -> {onet_code!r} ({crosswalk_id!r})"
            )
        if (task.get("crosswalk_review_status") or "").strip() != "human_reviewed":
            problems.append(
                f"row {index} ({task_id}): crosswalk must be human_reviewed before scoring"
            )
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


def _task_source_label(records) -> str:
    sources = {str(r.task.get("occupation_source", "")) for r in records.values()}
    if sources == {OCCUPATION_SOURCE}:
        return "PSA PSOC 2012 (2022 Updates) unit-group task statements (native; no crosswalk)"
    return "O*NET task statements via PSOC crosswalk"


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
        "model_provider": getattr(args, "provider", "openrouter"),
        "model_id": args.model,
        "model_release_or_snapshot": "as resolved by the provider at scoring time; not pinned",
        "resolved_model_ids": sorted({
            a.resolved_model_id for r in records.values() for a in r.attempts if a.resolved_model_id
        }),
        "temperature": args.temperature,
        "temperature_note": (
            "Not controllable through the Claude Code CLI; provider default used."
            if getattr(args, "provider", "openrouter") == "claude-cli"
            else (
                "Temperature 0. Repeated attempts are expected to be identical, so the "
                "attempt-agreement statistic measures provider reproducibility, not the "
                "stability of the judgement under a changed prompt or context."
                if args.temperature == 0.0
                else ""
            )
        ),
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
        "task_source": _task_source_label(records),
        "task_source_versions": sorted({
            str(r.task.get("task_source_version", "")) for r in records.values()
        } - {""}),
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


def publish_run(run_id: str, *, allow_partial: bool = False) -> None:
    """Publish a finished run. Only a run over the complete task file qualifies.

    A pilot covers a sample of occupations; publishing it would present a
    sample as the layer. ``allow_partial`` exists for local previews and the
    resulting rows still name the run, so the release shows what it came from.
    """
    manifest = json.loads((EXPOSURE_RUNS_DIR / run_id / "run.json").read_text(encoding="utf-8"))
    if not manifest.get("selection", {}).get("complete_task_file") and not allow_partial:
        raise ScoringRefusal(f"Run {run_id} scored a subset of the task file; refusing to publish it.")
    write_occupation_scores(manifest)


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
                # A value that was never applied is not recorded as if it were.
                "temperature": (
                    run_manifest["temperature"] if run_manifest["temperature"] is not None
                    else "provider_default_not_controllable"
                ),
                "run_count": run_manifest["min_successful_replicates"],
                # Actual calls, including recorded retries, not the requested count.
                "attempted_attempts": max(
                    (e["attempted_attempts"] for e in task_entries),
                    default=run_manifest["attempted_replicates"],
                ),
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
        writer = csv.DictWriter(
            handle, fieldnames=MODEL_SCORES_COLUMNS, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"{rel(MODEL_SCORES_CSV)}: {len(rows)} rows")


if __name__ == "__main__":
    main()
