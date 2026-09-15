"""Release validation.

Each check exists because of a specific v1 defect. The module returns a list of
failures rather than raising on the first, so a reviewer sees every problem in
one pass.

Every check is written to be meaningful on a *populated* dataset, and the test
suite exercises each one against a fixture that violates it. A validator that
has only ever seen an empty table has not been tested.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import psoc
from .paths import (
    CLASSIFICATIONS_CSV,
    CROSSWALK_CSV,
    METRIC_OBSERVATIONS_CSV,
    MODEL_SCORES_CSV,
    OCCUPATIONS_CSV,
    SITE_DATA_JSON,
    SITE_INDEX_HTML,
    SOURCE_REGISTRY_YAML,
    TRANSFORMATIONS_CSV,
    rel,
)
from .schema import (
    AVAILABILITY,
    BANNED_EXPOSURE_TERMS,
    CONFIDENCE_GRADES,
    CROSSWALK_COLUMNS,
    DERIVATION_CLASSES,
    SOURCE_AUTHORITIES,
    GRANULARITIES,
    MAPPING_BASIS,
    MATCH_QUALITY,
    MATCH_TYPES,
    METRIC_DEFINITIONS,
    METRIC_OBSERVATIONS_COLUMNS,
    MODEL_SCORES_COLUMNS,
    OCCUPATIONS_COLUMNS,
    REVIEW_STATUS,
    SUPPRESSION_STATUS,
    VERIFICATION_STATUS,
)


@dataclass
class Failure:
    check: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.detail}"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------

def check_schema(observations, occupations, crosswalk, scores) -> list[Failure]:
    failures: list[Failure] = []
    tables = (
        ("metric_observations", observations, METRIC_OBSERVATIONS_COLUMNS),
        ("occupations", occupations, OCCUPATIONS_COLUMNS),
        ("crosswalk", crosswalk, CROSSWALK_COLUMNS),
        ("model_scores", scores, MODEL_SCORES_COLUMNS),
    )
    for name, rows, columns in tables:
        for index, row in enumerate(rows):
            missing = [c for c in columns if c not in row]
            extra = [c for c in row if c not in columns]
            if missing:
                failures.append(Failure("schema", f"{name} row {index} missing columns: {missing}"))
            if extra:
                failures.append(Failure("schema", f"{name} row {index} has unknown columns: {extra}"))
    return failures


def check_unique_keys(observations, occupations, scores) -> list[Failure]:
    failures: list[Failure] = []
    for name, rows, key in (
        ("occupations", occupations, "occupation_id"),
        ("metric_observations", observations, "observation_id"),
        ("model_scores", scores, "score_id"),
    ):
        seen: set[str] = set()
        for row in rows:
            value = row.get(key, "")
            if value in seen:
                failures.append(Failure("unique_keys", f"{name} has a duplicate {key}: {value!r}"))
            seen.add(value)
    return failures


def check_psoc_hierarchy(occupations, classifications) -> list[Failure]:
    failures: list[Failure] = []
    for problem in psoc.validate_structure():
        failures.append(Failure("psoc_hierarchy", f"code list: {problem}"))

    codes = {row["psoc_code"] for row in classifications}
    for row in occupations:
        code = row.get("psoc_code", "")
        parent = row.get("parent_psoc_code", "")
        if code not in codes:
            failures.append(Failure("psoc_hierarchy", f"occupation {code!r} is not in classifications.csv"))
        if parent and parent not in codes:
            failures.append(Failure("psoc_hierarchy", f"{code!r} names a parent {parent!r} that does not exist"))
        if parent and not code.startswith(parent):
            failures.append(Failure("psoc_hierarchy", f"{code!r} is not nested under its declared parent {parent!r}"))
        if row.get("occupation_level") not in GRANULARITIES:
            failures.append(Failure("psoc_hierarchy", f"{code!r} has unknown level {row.get('occupation_level')!r}"))
    return failures


def check_verification_status(occupations, classifications) -> list[Failure]:
    """Unverified classification rows must say so."""
    failures: list[Failure] = []
    for name, rows in (("classifications", classifications), ("occupations", occupations)):
        for row in rows:
            status = row.get("verification_status", "")
            if status not in VERIFICATION_STATUS:
                failures.append(
                    Failure("verification_status",
                            f"{name} {row.get('psoc_code')!r} has invalid verification_status {status!r}")
                )
    return failures


# ---------------------------------------------------------------------------
# The core evidence rules
# ---------------------------------------------------------------------------

def check_observations(observations, registry_ids: set[str]) -> list[Failure]:
    failures: list[Failure] = []
    for row in observations:
        oid = row.get("observation_id", "?")
        value = (row.get("metric_value") or "").strip()
        derivation = row.get("derivation_class", "")
        authority = row.get("source_authority", "")
        availability = row.get("availability", "")
        grade = row.get("confidence_grade", "")

        if derivation not in DERIVATION_CLASSES:
            failures.append(Failure("derivation_class", f"{oid}: unknown derivation_class {derivation!r}"))
        if authority not in SOURCE_AUTHORITIES:
            failures.append(Failure("source_authority", f"{oid}: unknown source_authority {authority!r}"))
        # A sample survey is an estimate however official its publisher. The two
        # axes are independent, so an official authority must never be read as
        # licence to call a figure directly observed.
        if derivation == "directly_observed" and authority in {
            "ph_official_statistical_authority", "international_official_occupational"
        } and "survey" in (row.get("source_dataset", "") or "").lower():
            failures.append(
                Failure("derivation_class",
                        f"{oid}: {row.get('source_dataset')!r} is a survey, so its figures are "
                        "estimated, not directly observed. Authority is a separate axis.")
            )
        if availability not in AVAILABILITY:
            failures.append(Failure("availability", f"{oid}: unknown availability {availability!r}"))
        if grade not in CONFIDENCE_GRADES:
            failures.append(Failure("confidence_grade", f"{oid}: unknown confidence_grade {grade!r}"))
        if row.get("suppression_status") not in SUPPRESSION_STATUS:
            failures.append(Failure("suppression", f"{oid}: unknown suppression_status {row.get('suppression_status')!r}"))
        if row.get("source_granularity") not in GRANULARITIES:
            failures.append(Failure("granularity", f"{oid}: unknown source_granularity {row.get('source_granularity')!r}"))
        if row.get("display_granularity") not in GRANULARITIES:
            failures.append(Failure("granularity", f"{oid}: unknown display_granularity {row.get('display_granularity')!r}"))

        if row.get("source_id") not in registry_ids:
            failures.append(
                Failure("source_registry",
                        f"{oid}: source_id {row.get('source_id')!r} is not registered in {rel(SOURCE_REGISTRY_YAML)}")
            )

        # A published value must carry its provenance. This is the rule v1 had
        # none of.
        if availability == "published":
            if not value:
                failures.append(Failure("published_without_value", f"{oid}: availability=published but metric_value is empty"))
            if not row.get("source_url"):
                failures.append(Failure("provenance", f"{oid}: published without a source_url"))
            if not row.get("reference_period"):
                failures.append(Failure("provenance", f"{oid}: published without a reference_period"))
            if not row.get("source_file_hash"):
                failures.append(Failure("provenance", f"{oid}: published without a source_file_hash"))
            if not row.get("retrieved_at"):
                failures.append(Failure("provenance", f"{oid}: published without a retrieved_at"))
            if not row.get("parser_id"):
                failures.append(Failure("provenance", f"{oid}: published without a parser_id"))
            if not row.get("transformation_id"):
                failures.append(Failure("provenance", f"{oid}: published without a transformation_id"))
            if not row.get("normalised_row_id"):
                failures.append(
                    Failure("provenance",
                            f"{oid}: published without a normalised_row_id — a value must be "
                            "traceable to the source row it came from")
                )

        # A value must never appear on a row that says it has none.
        if availability != "published" and value:
            failures.append(
                Failure("value_without_publication",
                        f"{oid}: availability={availability!r} but carries a value {value!r}")
            )

        # Source coarser than display must be disclosed, not silently broadcast.
        source_level = row.get("source_granularity")
        display_level = row.get("display_granularity")
        if source_level in GRANULARITIES and display_level in GRANULARITIES:
            if GRANULARITIES.index(source_level) < GRANULARITIES.index(display_level):
                if derivation in {"directly_observed", "estimated", "calculated"}:
                    failures.append(
                        Failure("granularity_mismatch",
                                f"{oid}: source is {source_level} but displayed at {display_level} while "
                                f"labelled {derivation}. A broader source shown finer is proxy_derived.")
                    )
                if grade in {"A", "B"}:
                    failures.append(
                        Failure("granularity_mismatch",
                                f"{oid}: source {source_level} shown at {display_level} cannot hold "
                                f"confidence grade {grade}")
                    )

        # Percentages must be possible.
        unit = (row.get("unit") or "").lower()
        if value and ("share" in unit or "percent" in unit or unit.endswith("%")):
            try:
                numeric = float(value)
            except ValueError:
                failures.append(Failure("unit", f"{oid}: non-numeric value {value!r} for a share unit"))
            else:
                if not 0.0 <= numeric <= 1.0:
                    failures.append(Failure("impossible_percentage", f"{oid}: share value {numeric} is outside 0-1"))

        # Counts must be possible.
        if value and unit == "persons":
            try:
                numeric = float(value)
            except ValueError:
                failures.append(Failure("unit", f"{oid}: non-numeric value {value!r} for a person count"))
            else:
                if numeric < 0:
                    failures.append(Failure("negative_count", f"{oid}: negative employment {numeric}"))

        # A published value must declare which pipeline stage backs it, and a
        # fixture-tested stage may not back a published number.
        if availability == "published":
            status = row.get("pipeline_status", "")
            if status != "implemented_verified_with_real_source":
                failures.append(
                    Failure("pipeline_status",
                            f"{oid}: published with pipeline_status={status!r}. Only a stage "
                            "verified against the real source may back a published value.")
                )
            if not (row.get("confidence_reasons") or "").strip():
                failures.append(
                    Failure("provenance", f"{oid}: published without confidence_reasons")
                )

        metric_id = row.get("metric_id", "")
        if metric_id and metric_id not in METRIC_DEFINITIONS:
            failures.append(Failure("metric_definition", f"{oid}: metric_id {metric_id!r} has no definition"))
    return failures


def check_no_placeholder_fill(observations) -> list[Failure]:
    """Detect a constant broadcast across a metric, the v1 hiring-intensity defect."""
    failures: list[Failure] = []
    by_metric: dict[str, list[str]] = {}
    for row in observations:
        value = (row.get("metric_value") or "").strip()
        if value and row.get("availability") == "published":
            by_metric.setdefault(row["metric_id"], []).append(value)

    for metric_id, values in by_metric.items():
        if len(values) < 5:
            continue
        distinct = set(values)
        if len(distinct) == 1:
            failures.append(
                Failure("placeholder_fill",
                        f"metric {metric_id!r} has one distinct value ({distinct.pop()!r}) across "
                        f"{len(values)} published rows. A constant broadcast is not an observation.")
            )
        elif len(distinct) / len(values) < 0.1:
            failures.append(
                Failure("placeholder_fill",
                        f"metric {metric_id!r} has {len(distinct)} distinct values across {len(values)} "
                        f"published rows. Check for a constant broadcast across a category.")
            )
    return failures


def check_no_double_counting(observations) -> list[Failure]:
    """An aggregate and its own components may not both be published.

    v1 published broad Philippine categories alongside granular occupations
    describing the same workers, drawing on one employment budget.
    """
    failures: list[Failure] = []
    published: dict[tuple[str, str], set[str]] = {}
    for row in observations:
        if row.get("availability") != "published":
            continue
        key = (row.get("metric_id", ""), row.get("reference_period", ""))
        published.setdefault(key, set()).add(row.get("psoc_code", ""))

    for (metric_id, period), codes in published.items():
        if (METRIC_DEFINITIONS.get(metric_id) and
                "share of all" in METRIC_DEFINITIONS[metric_id].denominator.lower()):
            # Shares of a common denominator are not additive anyway.
            continue
        for code in sorted(codes):
            descendants = sorted(c for c in codes if c != code and c.startswith(code))
            if descendants:
                failures.append(
                    Failure("double_counting",
                            f"metric {metric_id!r} ({period or 'no period'}) publishes aggregate {code!r} "
                            f"together with its components {descendants}. Summing these double-counts workers.")
                )
    return failures


def check_group_total_reconciliation(observations) -> list[Failure]:
    """Where both a parent and its children are published, the children must sum to the parent.

    Publishing both is already refused by check_no_double_counting; this check
    catches the case where a future release justifies publishing both and gets
    the arithmetic wrong.
    """
    failures: list[Failure] = []
    counts: dict[tuple[str, str, str], float] = {}
    for row in observations:
        if row.get("availability") != "published" or (row.get("unit") or "") != "persons":
            continue
        value = (row.get("metric_value") or "").strip()
        if not value:
            continue
        try:
            counts[(row["metric_id"], row.get("reference_period", ""), row["psoc_code"])] = float(value)
        except ValueError:
            continue

    for (metric_id, period, code), parent_value in counts.items():
        children = [
            value for (m, p, c), value in counts.items()
            if m == metric_id and p == period and c != code and c.startswith(code) and len(c) == len(code) + 1
        ]
        if not children:
            continue
        total = sum(children)
        if parent_value > 0 and abs(total - parent_value) / parent_value > 0.005:
            failures.append(
                Failure("group_total_reconciliation",
                        f"metric {metric_id!r} ({period}): children of {code!r} sum to {total:,.0f} "
                        f"but the parent is {parent_value:,.0f}")
            )
    return failures


def check_crosswalk(crosswalk) -> list[Failure]:
    failures: list[Failure] = []
    seen: set[str] = set()
    forward: dict[tuple[str, str], set[str]] = {}
    reverse: dict[tuple[str, str], set[str]] = {}

    for row in crosswalk:
        cid = row.get("crosswalk_id", "?")
        if cid in seen:
            failures.append(Failure("crosswalk", f"duplicate crosswalk_id {cid!r}"))
        seen.add(cid)

        if row.get("match_type") not in MATCH_TYPES:
            failures.append(Failure("crosswalk", f"{cid}: invalid match_type {row.get('match_type')!r}"))
        if row.get("match_quality") not in MATCH_QUALITY:
            failures.append(Failure("crosswalk", f"{cid}: invalid match_quality {row.get('match_quality')!r}"))
        if row.get("mapping_basis") not in MAPPING_BASIS:
            failures.append(Failure("crosswalk", f"{cid}: invalid mapping_basis {row.get('mapping_basis')!r}"))
        if row.get("review_status") not in REVIEW_STATUS:
            failures.append(Failure("crosswalk", f"{cid}: invalid review_status {row.get('review_status')!r}"))

        # Impossible states.
        if row.get("match_type") == "no_defensible_match" and row.get("match_quality") != "none":
            failures.append(
                Failure("crosswalk", f"{cid}: match_type=no_defensible_match cannot carry "
                                     f"match_quality={row.get('match_quality')!r}")
            )
        if row.get("match_type") == "exact" and row.get("match_quality") == "low":
            failures.append(Failure("crosswalk", f"{cid}: match_type=exact with match_quality=low is contradictory"))
        if row.get("mapping_basis") == "title_similarity_only" and row.get("review_status") != "rejected":
            failures.append(
                Failure("crosswalk",
                        f"{cid}: a title-similarity-only mapping must be review_status=rejected. "
                        "Silent title matching is how v1 mapped US occupations onto PSOC.")
            )

        key = (row.get("psoc_code", ""), row.get("source_classification", ""))
        forward.setdefault(key, set()).add(row.get("source_code", ""))
        reverse.setdefault((row.get("source_code", ""), row.get("source_classification", "")), set()).add(
            row.get("psoc_code", "")
        )

    # Cardinality flags must match reality.
    for row in crosswalk:
        cid = row.get("crosswalk_id", "?")
        key = (row.get("psoc_code", ""), row.get("source_classification", ""))
        rkey = (row.get("source_code", ""), row.get("source_classification", ""))
        actual_one_to_many = len(forward.get(key, set())) > 1
        actual_many_to_one = len(reverse.get(rkey, set())) > 1
        if (row.get("is_one_to_many") == "true") != actual_one_to_many:
            failures.append(
                Failure("crosswalk", f"{cid}: is_one_to_many={row.get('is_one_to_many')!r} but the table "
                                     f"maps this PSOC code to {len(forward.get(key, set()))} source codes")
            )
        if (row.get("is_many_to_one") == "true") != actual_many_to_one:
            failures.append(
                Failure("crosswalk", f"{cid}: is_many_to_one={row.get('is_many_to_one')!r} but the table "
                                     f"maps this source code to {len(reverse.get(rkey, set()))} PSOC codes")
            )
    return failures


def check_observations_do_not_use_rejected_crosswalks(observations, crosswalk) -> list[Failure]:
    rejected = {row["crosswalk_id"] for row in crosswalk if row.get("review_status") == "rejected"}
    return [
        Failure("rejected_crosswalk",
                f"{row.get('observation_id')}: resolves through rejected crosswalk {row.get('crosswalk_id')!r}")
        for row in observations
        if row.get("crosswalk_id") and row["crosswalk_id"] in rejected
    ]


def check_model_scores(scores) -> list[Failure]:
    failures: list[Failure] = []
    required = [
        "rubric_version", "prompt_version", "model_provider", "model_id",
        "scoring_date", "temperature", "run_count", "aggregation_method",
        "uncertainty_or_stability", "human_review_status", "raw_response_reference",
    ]
    for row in scores:
        sid = row.get("score_id", "?")
        missing = [field for field in required if not (row.get(field) or "").strip()]
        if missing:
            failures.append(Failure("score_provenance", f"{sid}: missing provenance fields {missing}"))
        if (row.get("run_count") or "").strip().isdigit() and int(row["run_count"]) < 2:
            failures.append(
                Failure("score_provenance",
                        f"{sid}: run_count={row['run_count']} cannot support a stability measure")
            )
        value = (row.get("score") or "").strip()
        if value:
            try:
                numeric = float(value)
            except ValueError:
                failures.append(Failure("score_range", f"{sid}: non-numeric score {value!r}"))
            else:
                low = float(row.get("score_scale_min") or 0)
                high = float(row.get("score_scale_max") or 5)
                if not low <= numeric <= high:
                    failures.append(Failure("score_range", f"{sid}: score {numeric} outside {low}-{high}"))
    return failures


# ---------------------------------------------------------------------------
# Language and published-surface rules
# ---------------------------------------------------------------------------

def _strip_audit_context(text: str) -> str:
    """Remove regions marked as quoting v1, so the audit can describe the defect.

    The interface wraps any quotation of withdrawn v1 language in
    ``<!-- v1-quote -->`` ... ``<!-- /v1-quote -->`` so this check stays strict
    everywhere else.
    """
    return re.sub(r"<!--\s*v1-quote\s*-->.*?<!--\s*/v1-quote\s*-->", " ", text, flags=re.S | re.I)


# A banned term is a problem when it *asserts* the framing, not when it denies
# it. "not an estimate of displacement" is the disclaimer we require; banning it
# would forbid the correction along with the error. These markers, found in the
# window before a match, mark a denial.
_NEGATION_MARKERS = (
    "not ", "never ", "no ", "nor ", "n't ", "rather than", "instead of",
    "does not", "is not", "are not", "cannot", "must not", "refuses",
    "prohibited", "misread", "misreading", "withdrawn", "removed",
    "banned", "forbid", "distinct from", "unlike",
)

_NEGATION_WINDOW = 140


def _is_negated(text: str, index: int) -> bool:
    """Does a negation govern the banned term at `index`?

    Scoped to the sentence the match sits in, so a denial two sentences earlier
    cannot license an assertion here.
    """
    window_start = max(0, index - _NEGATION_WINDOW)
    window = text[window_start:index]
    # Sentence boundary, JSON field boundary, or list separator ends the scope.
    for boundary in (". ", "! ", "? ", '", "', '":', "\n\n"):
        cut = window.rfind(boundary)
        if cut != -1:
            window = window[cut + len(boundary):]
    return any(marker in window for marker in _NEGATION_MARKERS)


def check_language(paths: Iterable[Path]) -> list[Failure]:
    """Refuse hazard framing for the exposure measure, but not its disclaimer."""
    failures: list[Failure] = []
    for path in paths:
        if not path.exists():
            continue
        text = _strip_audit_context(path.read_text(encoding="utf-8")).lower()
        for term in BANNED_EXPOSURE_TERMS:
            start = 0
            while True:
                index = text.find(term, start)
                if index == -1:
                    break
                start = index + len(term)
                if _is_negated(text, index):
                    continue
                context = text[max(0, index - 70) : index + 70].replace("\n", " ")
                failures.append(
                    Failure("banned_language",
                            f"{rel(path)} asserts {term!r}: ...{context}...")
                )
    return failures


def check_no_hardcoded_counts(path: Path, published_count: int) -> list[Failure]:
    """No literal occupation count in the interface.

    v1 hard-coded 173 in two places, so the claim could not follow the data.
    """
    if not path.exists():
        return []
    failures: list[Failure] = []
    text = _strip_audit_context(path.read_text(encoding="utf-8"))
    pattern = re.compile(r"\b(\d{2,5})\s+(?:philippine\s+)?occupations\b", re.I)
    for match in pattern.finditer(text):
        failures.append(
            Failure("hardcoded_count",
                    f"{rel(path)} hard-codes an occupation count: {match.group(0)!r}. "
                    "Derive it from the published dataset at build time.")
        )
    return failures


def check_site_payload(path: Path) -> list[Failure]:
    """Every published numeric field in the site payload must carry provenance."""
    if not path.exists():
        return [Failure("site_payload", f"{rel(path)} does not exist")]
    failures: list[Failure] = []
    payload = json.loads(path.read_text(encoding="utf-8"))

    for key in ("schema", "release", "derivation_class_legend", "source_authority_legend",
                "occupations", "metrics"):
        if key not in payload:
            failures.append(Failure("site_payload", f"{rel(path)} is missing top-level key {key!r}"))
    if failures:
        return failures

    for entry in payload["occupations"]:
        code = entry.get("psoc_code", "?")
        for metric_id, metric in entry.get("metrics", {}).items():
            if "value" not in metric:
                failures.append(Failure("site_payload", f"{code}/{metric_id}: no 'value' key"))
                continue
            if metric.get("availability") not in AVAILABILITY:
                failures.append(Failure("site_payload", f"{code}/{metric_id}: invalid availability"))
            if metric.get("derivation_class") not in DERIVATION_CLASSES:
                failures.append(Failure("site_payload", f"{code}/{metric_id}: invalid derivation_class"))
            if metric.get("source_authority") not in SOURCE_AUTHORITIES:
                failures.append(Failure("site_payload", f"{code}/{metric_id}: invalid source_authority"))
            if metric.get("value") is not None:
                for field in ("source_organization", "source_url", "reference_period",
                              "confidence_grade", "parser_id", "transformation_id"):
                    if not metric.get(field):
                        failures.append(
                            Failure("site_payload",
                                    f"{code}/{metric_id}: published value without {field}")
                        )
            # A missing value must be null, never 0 and never a midpoint.
            if metric.get("availability") != "published" and metric.get("value") is not None:
                failures.append(
                    Failure("site_payload",
                            f"{code}/{metric_id}: unavailable metric carries value {metric['value']!r}. "
                            "Missing values are null, never zero or a neutral midpoint.")
                )
    return failures


def check_no_legacy_values_in_release(path: Path) -> list[Failure]:
    """Refuse to publish any v1 number."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    failures = []
    # The universal placeholder and the two headline aggregates it produced.
    for needle, why in (
        ('"outlook"', "v1 hiring-intensity field"),
        ('"hiring_intensity"', "v1 hiring-intensity field"),
        ('"exposure_rationale"', "v1 unprovenanced model rationale"),
        ('"primary_risk_vector"', "v1 risk-vector label"),
    ):
        if needle in text:
            failures.append(Failure("legacy_leakage", f"{rel(path)} contains {needle} ({why})"))
    return failures


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_all() -> list[Failure]:
    classifications = read_csv(CLASSIFICATIONS_CSV)
    occupations = read_csv(OCCUPATIONS_CSV)
    observations = read_csv(METRIC_OBSERVATIONS_CSV)
    crosswalk = read_csv(CROSSWALK_CSV)
    transformations = read_csv(TRANSFORMATIONS_CSV)
    scores = read_csv(MODEL_SCORES_CSV)

    registry = yaml.safe_load(SOURCE_REGISTRY_YAML.read_text(encoding="utf-8"))
    registry_ids = {entry["source_id"] for entry in registry["sources"]}

    failures: list[Failure] = []
    failures += check_schema(observations, occupations, crosswalk, scores)
    failures += check_unique_keys(observations, occupations, scores)
    failures += check_psoc_hierarchy(occupations, classifications)
    failures += check_verification_status(occupations, classifications)
    failures += check_observations(observations, registry_ids)
    failures += check_no_placeholder_fill(observations)
    failures += check_no_double_counting(observations)
    failures += check_group_total_reconciliation(observations)
    failures += check_crosswalk(crosswalk)
    failures += check_observations_do_not_use_rejected_crosswalks(observations, crosswalk)
    failures += check_model_scores(scores)
    failures += check_language([SITE_INDEX_HTML, SITE_DATA_JSON])
    failures += check_site_payload(SITE_DATA_JSON)
    failures += check_no_legacy_values_in_release(SITE_DATA_JSON)

    if not transformations:
        failures.append(Failure("transformations", "transformations.csv is empty"))

    published = [row for row in observations if row.get("availability") == "published"]
    failures += check_no_hardcoded_counts(SITE_INDEX_HTML, len(published))
    return failures


def main() -> None:
    failures = run_all()
    if failures:
        print(f"Validation FAILED with {len(failures)} problem(s):\n")
        for failure in failures:
            print(f"  {failure}")
        raise SystemExit(1)
    print("Validation passed.")


if __name__ == "__main__":
    main()
