"""Attempt-level records for exposure scoring.

The pre-remediation harness recorded ``run_count = args.runs`` — the number of
attempts *requested* — and dropped failures with a printed message. A task that
succeeded once out of three attempts produced a score whose provenance claimed
three runs, with no trace of the two failures.

So the unit of record here is the **attempt**, not the run. Counts are derived
from attempts that actually succeeded, never from configuration, and a task that
does not meet the configured minimum number of successes is excluded from
publication with its shortfall recorded.

On vocabulary: these are *repeated scoring attempts*, not independent
replicates. Each task is a separate chat request, so shuffling task order cannot
test within-prompt ordering effects — there is no shared prompt to order. At
temperature 0 repeated calls measure run-to-run reproducibility and provider
variability. Calling that statistical independence would be a claim the design
does not support.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

#: Default minimum successful attempts before a task may be published.
DEFAULT_MIN_SUCCESSFUL_ATTEMPTS = 2


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AttemptRecord:
    """One model call, successful or not. Always retained."""

    task_id: str
    attempt_index: int
    status: str  # "succeeded" | "request_failed" | "parse_failed"
    requested_at: str
    completed_at: str = ""
    model_id: str = ""
    resolved_model_id: str = ""
    provider_request_id: str = ""
    temperature: float | None = None
    request_payload: dict[str, Any] = field(default_factory=dict)
    raw_response: str | None = None
    parsed: dict[str, Any] | None = None
    parser_status: str = ""
    error_type: str = ""
    error_message: str = ""
    retry_of_attempt: int | None = None
    #: Provider-reported facts that are not scores: cost, token usage, latency.
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == "succeeded"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskRunRecord:
    """Every attempt made for one task, plus the counts derived from them."""

    task_id: str
    task: dict[str, Any]
    attempts: list[AttemptRecord] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        return len(self.attempts)

    @property
    def successful(self) -> int:
        return sum(1 for a in self.attempts if a.succeeded)

    @property
    def failed(self) -> int:
        return self.attempted - self.successful

    def successful_values(self, dimension: str) -> list[int]:
        return [
            a.parsed[dimension]
            for a in self.attempts
            if a.succeeded and a.parsed and dimension in a.parsed
        ]

    def meets_minimum(self, minimum: int) -> bool:
        return self.successful >= minimum

    def as_dict(self, minimum: int) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task": self.task,
            "attempted_attempts": self.attempted,
            "successful_attempts": self.successful,
            "failed_attempts": self.failed,
            "meets_minimum_successful_attempts": self.meets_minimum(minimum),
            "attempts": [a.as_dict() for a in self.attempts],
        }


def ordinal_summary(values: list[int], scale_max: int = 5) -> dict[str, Any]:
    """Summarise an ordinal set without pretending the spacing is metric.

    The rubric declares each dimension ordinal, so the headline statistic is the
    median and the spread is the interquartile range. The full category
    distribution is published because it is the only lossless summary of an
    ordinal variable.
    """
    if not values:
        return {"n": 0, "median": None, "distribution": {}, "agreement": None}

    ordered = sorted(values)
    counts = Counter(ordered)
    distribution = {str(score): counts.get(score, 0) for score in range(scale_max + 1)}

    if len(ordered) >= 4:
        quantiles = statistics.quantiles(ordered, n=4, method="inclusive")
        q1, q3 = quantiles[0], quantiles[2]
    else:
        q1, q3 = ordered[0], ordered[-1]

    modal = counts.most_common(1)[0][1]
    return {
        "n": len(ordered),
        "median": statistics.median(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "range": ordered[-1] - ordered[0],
        "iqr_lower": q1,
        "iqr_upper": q3,
        "distribution": distribution,
        # Share of attempts landing on the modal category: a reproducibility
        # measure that does not assume interval spacing.
        "agreement": round(modal / len(ordered), 4),
        "values": ordered,
    }


def aggregate_tasks_ordinal(
    task_scores: list[dict[str, Any]],
    dimension: str,
    threshold: int,
    scale_max: int = 5,
) -> dict[str, Any]:
    """Aggregate task-level ordinal scores to an occupation.

    Deliberately not an arithmetic mean by default: the rubric has not
    established that the distance from 1 to 2 equals the distance from 4 to 5,
    and averaging assumes exactly that.

    An arithmetic mean is still reported, clearly labelled experimental, so a
    reader can see how much the choice of statistic matters.
    """
    values = [
        entry["consensus"][dimension]["median"]
        for entry in task_scores
        if entry["consensus"].get(dimension, {}).get("median") is not None
    ]
    if not values:
        return {"n_tasks": 0, "median": None}

    ordered = sorted(int(round(v)) for v in values)
    counts = Counter(ordered)
    above = sum(1 for v in ordered if v >= threshold)

    if len(ordered) >= 4:
        quantiles = statistics.quantiles(ordered, n=4, method="inclusive")
        q1, q3 = quantiles[0], quantiles[2]
    else:
        q1, q3 = ordered[0], ordered[-1]

    return {
        "n_tasks": len(ordered),
        "median": statistics.median(ordered),
        "iqr_lower": q1,
        "iqr_upper": q3,
        "distribution": {str(s): counts.get(s, 0) for s in range(scale_max + 1)},
        "share_of_tasks_at_or_above_threshold": round(above / len(ordered), 4),
        "threshold": threshold,
        "experimental_arithmetic_mean": round(sum(ordered) / len(ordered), 4),
        "experimental_arithmetic_mean_caveat": (
            "Convenience statistic only. The rubric's scale is ordinal, so the "
            "distance between adjacent points is not established to be equal. "
            "Published beside the median so the effect of the choice is visible."
        ),
    }


def weighted_median(values: list[float], weights: list[float]) -> float | None:
    """Median with weights — the ordinal-safe analogue of a weighted mean."""
    if not values or len(values) != len(weights):
        return None
    pairs = sorted(zip(values, weights))
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= total / 2:
            return value
    return pairs[-1][0]
