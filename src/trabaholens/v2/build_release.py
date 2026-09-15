"""Build the release manifest and the site payload.

The payload is provenance-first: the interface cannot render a number without
also receiving its estimate type, availability, source, reference period and
confidence grade, because they arrive in the same object. Making provenance
structurally inseparable from the value is the point — a front-end cannot
forget to show what it was never given separately.

Determinism: nothing here reads the clock except the explicitly declared
``generated_at``, and ``--frozen-time`` pins that so two builds can be compared
byte for byte.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from . import psoc
from .paths import (
    CLASSIFICATIONS_CSV,
    CROSSWALK_CSV,
    METRIC_OBSERVATIONS_CSV,
    MODEL_SCORES_CSV,
    OCCUPATIONS_CSV,
    RELEASE_MANIFEST_JSON,
    RETRIEVAL_MANIFEST_JSON,
    SITE_DATA_JSON,
    SOURCE_REGISTRY_YAML,
    TRANSFORMATIONS_CSV,
    ensure_parent,
    rel,
)
from .build_canonical import pipeline_stage_reports
from .schema import (
    AVAILABILITY,
    CONFIDENCE_GRADES,
    DERIVATION_CLASSES,
    METRIC_DEFINITIONS,
    SCHEMA_VERSION,
    SOURCE_AUTHORITIES,
)

PAYLOAD_SCHEMA = "trabaholens-site-payload/2"
METHODOLOGY_VERSION = "2.0.0"
RUBRIC_VERSION = "0.1.0"
PROMPT_VERSION = "0.1.0"

EXPOSURE_DISCLAIMER = (
    "Generative-AI task exposure indicates how much an occupation's tasks may be "
    "affected or assisted by generative AI. It is not an estimate of automation, "
    "displacement, layoffs, or future employment."
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def _value_or_none(raw: str) -> Any:
    """Parse a stored value, or None. Never substitutes a zero or a midpoint."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def build_metric_block(row: dict[str, str]) -> dict[str, Any]:
    definition = METRIC_DEFINITIONS.get(row["metric_id"])
    return {
        "value": _value_or_none(row.get("metric_value", "")),
        "unit": row.get("unit", ""),
        # Two independent axes. The interface shows both, because "PSA
        # published it" and "it was directly observed" are different claims.
        "derivation_class": row.get("derivation_class", ""),
        "derivation_class_label": DERIVATION_CLASSES.get(row.get("derivation_class", ""), ("", ""))[0],
        "source_authority": row.get("source_authority", ""),
        "source_authority_label": SOURCE_AUTHORITIES.get(row.get("source_authority", ""), ("", ""))[0],
        "availability": row.get("availability", ""),
        "confidence_grade": row.get("confidence_grade", ""),
        "confidence_reasons": [
            r.strip() for r in (row.get("confidence_reasons", "") or "").split("|") if r.strip()
        ],
        "pipeline_status": row.get("pipeline_status", ""),
        "parser_id": row.get("parser_id", ""),
        "normalised_row_id": row.get("normalised_row_id", ""),
        "transformation_id": row.get("transformation_id", ""),
        "reference_period": row.get("reference_period", ""),
        "geography": row.get("geography", ""),
        "population_scope": row.get("population_scope", ""),
        "source_granularity": row.get("source_granularity", ""),
        "display_granularity": row.get("display_granularity", ""),
        "granularity_mismatch": row.get("source_granularity") != row.get("display_granularity"),
        "source_id": row.get("source_id", ""),
        "source_organization": row.get("source_organization", ""),
        "source_dataset": row.get("source_dataset", ""),
        "source_url": row.get("source_url", ""),
        "source_file_hash": row.get("source_file_hash", ""),
        "retrieved_at": row.get("retrieved_at", ""),
        "uncertainty_lower": _value_or_none(row.get("uncertainty_lower", "")),
        "uncertainty_upper": _value_or_none(row.get("uncertainty_upper", "")),
        "suppression_status": row.get("suppression_status", ""),
        "common_misreading": definition.common_misreading if definition else "",
        "notes": row.get("notes", ""),
    }


def build_payload(release: dict[str, Any]) -> dict[str, Any]:
    occupations = read_csv(OCCUPATIONS_CSV)
    observations = read_csv(METRIC_OBSERVATIONS_CSV)
    scores = read_csv(MODEL_SCORES_CSV)

    by_occupation: dict[str, list[dict[str, str]]] = {}
    for row in observations:
        by_occupation.setdefault(row["occupation_id"], []).append(row)

    scores_by_occupation: dict[str, list[dict[str, str]]] = {}
    for row in scores:
        scores_by_occupation.setdefault(row["occupation_id"], []).append(row)

    entries = []
    for occupation in occupations:
        oid = occupation["occupation_id"]
        metrics = {
            row["metric_id"]: build_metric_block(row)
            for row in by_occupation.get(oid, [])
        }
        exposure = [
            {
                "dimension": row["dimension"],
                "score": _value_or_none(row.get("score", "")),
                "scale_min": _value_or_none(row.get("score_scale_min", "")),
                "scale_max": _value_or_none(row.get("score_scale_max", "")),
                "aggregation_method": row.get("aggregation_method", ""),
                "task_weighting": row.get("task_weighting", ""),
                "task_source": row.get("task_source", ""),
                "crosswalk_quality": row.get("crosswalk_quality", ""),
                "stability": row.get("uncertainty_or_stability", ""),
                "run_disagreement_range": _value_or_none(row.get("run_disagreement_range", "")),
                "model_provider": row.get("model_provider", ""),
                "model_id": row.get("model_id", ""),
                "model_release_or_snapshot": row.get("model_release_or_snapshot", ""),
                "rubric_version": row.get("rubric_version", ""),
                "prompt_version": row.get("prompt_version", ""),
                "scoring_date": row.get("scoring_date", ""),
                "run_count": _value_or_none(row.get("run_count", "")),
                "human_review_status": row.get("human_review_status", ""),
                "raw_response_reference": row.get("raw_response_reference", ""),
            }
            for row in scores_by_occupation.get(oid, [])
        ]

        entries.append(
            {
                "occupation_id": oid,
                "psoc_code": occupation["psoc_code"],
                "psoc_version": occupation["psoc_version"],
                "title": occupation["occupation_title"],
                "level": occupation["occupation_level"],
                "parent_psoc_code": occupation["parent_psoc_code"],
                "psoc_major": occupation["psoc_major"],
                "psoc_major_label": occupation["psoc_major_label"],
                "is_aggregate": occupation["is_aggregate"] == "true",
                "verification_status": occupation["verification_status"],
                "metrics": metrics,
                "exposure": exposure,
            }
        )

    published_values = sum(
        1
        for entry in entries
        for metric in entry["metrics"].values()
        if metric["availability"] == "published" and metric["value"] is not None
    )

    return {
        "schema": PAYLOAD_SCHEMA,
        "release": release,
        "disclaimers": {
            "exposure": EXPOSURE_DISCLAIMER,
            "classification_verification": (
                "The PSOC 2012 code list in this release was entered from "
                "classification documentation, not from the PSA volume, which could "
                "not be retrieved. Every classification row is marked "
                "unverified_pending_source."
            ),
        },
        "derivation_class_legend": {
            key: {"label": label, "explanation": explanation}
            for key, (label, explanation) in DERIVATION_CLASSES.items()
        },
        "source_authority_legend": {
            key: {"label": label, "explanation": explanation}
            for key, (label, explanation) in SOURCE_AUTHORITIES.items()
        },
        "confidence_grade_legend": CONFIDENCE_GRADES,
        "availability_legend": {
            "published": "A value is available and shown.",
            "blocked_pending_source": (
                "The metric is defined and its source is identified, but that source "
                "has not been retrieved, so there is no value to show."
            ),
            "suppressed_low_sample": "Withheld because the sample behind it is too small to publish.",
            "not_applicable": "This metric does not apply to this occupation.",
            "withdrawn_unsupported": (
                "Published in a previous version and withdrawn because no evidence "
                "supported it."
            ),
        },
        "metrics": {
            definition.metric_id: {
                "name": definition.metric_name,
                "unit": definition.unit,
                "definition": definition.definition,
                "denominator": definition.denominator,
                "common_misreading": definition.common_misreading,
                "required_source": definition.required_source_id,
                "expected_source_granularity": definition.expected_source_granularity,
                "expected_derivation_class": definition.expected_derivation_class,
                "expected_source_authority": definition.expected_source_authority,
                "parser_id": definition.parser_id,
            }
            for definition in METRIC_DEFINITIONS.values()
        },
        "counts": {
            # Derived, never hard-coded. The interface reads these.
            "occupations": len(entries),
            "psoc_major_groups": sum(1 for e in entries if e["level"] == "psoc_major_group"),
            "psoc_sub_major_groups": sum(1 for e in entries if e["level"] == "psoc_sub_major_group"),
            "metrics_defined": len(METRIC_DEFINITIONS),
            "metric_observations": len(read_csv(METRIC_OBSERVATIONS_CSV)),
            "published_values": published_values,
            "exposure_scores": len(read_csv(MODEL_SCORES_CSV)),
        },
        "occupations": entries,
    }


def _discover_model_runs() -> list[dict[str, Any]]:
    """Derive the model-run list from run manifests on disk.

    Previously hard-coded to []. A hard-coded empty list is indistinguishable
    from "we looked and found none", which is the distinction that matters.
    """
    from .paths import EXPOSURE_RUNS_DIR

    runs: list[dict[str, Any]] = []
    if not EXPOSURE_RUNS_DIR.exists():
        return runs
    for run_json in sorted(EXPOSURE_RUNS_DIR.glob("*/run.json")):
        try:
            payload = json.loads(run_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            runs.append({"run_id": run_json.parent.name, "status": "unreadable_run_manifest"})
            continue
        runs.append(
            {
                "run_id": payload.get("run_id", run_json.parent.name),
                "model_id": payload.get("model_id", ""),
                "rubric_version": payload.get("rubric_version", ""),
                "prompt_version": payload.get("prompt_version", ""),
                "scoring_date": payload.get("scoring_date", ""),
                "attempted_replicates": payload.get("attempted_replicates"),
                "min_successful_replicates": payload.get("min_successful_replicates"),
                "tasks_meeting_minimum": payload.get("tasks_meeting_minimum"),
                "tasks_below_minimum": payload.get("tasks_below_minimum"),
                "human_review_status": payload.get("human_review_status", ""),
            }
        )
    return runs


def build_release_manifest(frozen_time: str | None) -> dict[str, Any]:
    registry = yaml.safe_load(SOURCE_REGISTRY_YAML.read_text(encoding="utf-8"))
    retrieval = (
        json.loads(RETRIEVAL_MANIFEST_JSON.read_text(encoding="utf-8"))
        if RETRIEVAL_MANIFEST_JSON.exists()
        else {"retrievals": []}
    )

    latest: dict[str, dict] = {}
    for entry in retrieval.get("retrievals", []):
        latest[entry["source_id"]] = entry

    source_versions = {}
    source_hashes = {}
    for source in registry["sources"]:
        sid = source["source_id"]
        attempt = latest.get(sid, {})
        source_versions[sid] = {
            "organization": source["organization"],
            "dataset": source["dataset"],
            "declared_status": source["retrieval"]["status"],
            "last_attempt": attempt.get("attempted_at", "never"),
            "last_attempt_result": attempt.get("status", "none"),
            "blocked_reason": source["retrieval"].get("blocked_reason", ""),
        }
        source_hashes[sid] = attempt.get("sha256")

    observations = read_csv(METRIC_OBSERVATIONS_CSV)
    blocked = sorted({row["metric_id"] for row in observations if row["availability"] != "published"})

    unrepresentable = sorted(
        definition.metric_id
        for definition in METRIC_DEFINITIONS.values()
        if not any(row["metric_id"] == definition.metric_id for row in observations)
    )

    checksums = {}
    for path in (
        CLASSIFICATIONS_CSV, OCCUPATIONS_CSV, METRIC_OBSERVATIONS_CSV,
        CROSSWALK_CSV, TRANSFORMATIONS_CSV, MODEL_SCORES_CSV,
    ):
        if path.exists():
            checksums[rel(path)] = sha256_file(path)

    return {
        "release_id": "v2.0.0-pre",
        "release_date": frozen_time or "unset",
        "generated_at": frozen_time or "unset",
        "code_commit": git_commit(),
        "code_commit_note": (
            "The commit the build ran at. It necessarily precedes the commit that "
            "records it, because committing this manifest moves HEAD. Treat it as "
            "'generated from this input state', not as a self-describing id. "
            "`make check-stale` excludes it for the same reason."
        ),
        "schema_version": SCHEMA_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "exposure_rubric_version": RUBRIC_VERSION,
        "prompt_version": PROMPT_VERSION,
        "crosswalk_version": "0.1.0",
        "psoc_version": psoc.PSOC_VERSION,
        "source_versions": source_versions,
        "source_hashes": source_hashes,
        "canonical_table_checksums": checksums,
        "model_runs": _discover_model_runs(),
        "pipeline_stages": [report.as_dict() for report in pipeline_stage_reports()],
        "publication_state": {
            "metrics_defined": sorted(METRIC_DEFINITIONS),
            "metrics_with_published_values": [],
            "metrics_blocked_pending_source": blocked,
            "metrics_not_representable_at_current_granularity": unrepresentable,
        },
        "known_limitations": [
            "No metric in this release carries a value. Every PSA host, "
            "www.onetcenter.org and openrouter.ai returned HTTP 403 at this build "
            "environment's egress proxy, so no source could be retrieved. See "
            "data/sources/retrieval-manifest.json for the dated attempts.",
            "The PSOC 2012 code list was entered from classification documentation "
            "rather than the PSA volume. Every classification row is marked "
            "unverified_pending_source and must be diffed against the PSA volume.",
            "The canonical table holds PSOC major and sub-major groups only. Minor "
            "and unit groups are absent rather than guessed, so occupation-level "
            "metrics (wages, O*NET Job Zone, task exposure) have no unit to attach "
            "to yet.",
            "No generative-AI task exposure score is published. The scoring harness "
            "requires task evidence that could not be retrieved and a provider that "
            "could not be reached.",
            "The v1 exposure scores are not carried forward and are not a fallback.",
            "This experimental exposure score has not yet undergone independent "
            "labour-economist validation.",
            "No component of this release has been reviewed by a Philippine labour "
            "statistician.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--frozen-time",
        default=None,
        help="Pin release_date/generated_at so two builds are byte-identical (determinism check).",
    )
    args = parser.parse_args()

    release = build_release_manifest(args.frozen_time)
    payload = build_payload(release)

    ensure_parent(RELEASE_MANIFEST_JSON)
    RELEASE_MANIFEST_JSON.write_text(
        json.dumps(release, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    ensure_parent(SITE_DATA_JSON)
    SITE_DATA_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    counts = payload["counts"]
    print(f"{rel(RELEASE_MANIFEST_JSON)} written")
    print(f"{rel(SITE_DATA_JSON)} written")
    print(f"  occupations (PSOC units): {counts['occupations']}")
    print(f"  metrics defined:          {counts['metrics_defined']}")
    print(f"  metric observations:      {counts['metric_observations']}")
    print(f"  published values:         {counts['published_values']}")
    print(f"  exposure scores:          {counts['exposure_scores']}")


if __name__ == "__main__":
    main()
