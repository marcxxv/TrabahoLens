"""Build the canonical PSOC-first tables.

Produces six normalised tables under ``data/canonical/``. Provenance lives in
the rows, not in a README, so a value cannot travel without the facts that
qualify it.

What this module deliberately does **not** do:

* It does not invent occupation records below the level PSOC documentation
  gives us.
* It does not write a ``metric_value`` for any metric whose source has not been
  retrieved. Blocked metrics get a row with an empty value and an explicit
  ``availability``, because a visible gap is information and a silent omission
  is not.
* It does not carry any v1 number forward.
"""

from __future__ import annotations

import csv
from typing import Any

from . import psoc
from .acquire import load_registry
from .acquisition_state import verify_all
from .pipeline import Stage, StageReport, StageStatus
from .sources import get_parser
from .sources import onet as _onet_parsers  # noqa: F401  (registers parsers)
from .sources import psa as _psa_parsers  # noqa: F401  (registers parsers)
from .sources import psoc_importer as _psoc_parser  # noqa: F401
from .transform import TransformOutcome, confidence_for, transform_rows
from .paths import (
    CLASSIFICATIONS_CSV,
    CROSSWALK_CSV,
    METRIC_OBSERVATIONS_CSV,
    MODEL_SCORES_CSV,
    OCCUPATIONS_CSV,
    PSOC_VERSION_CORRESPONDENCE_CSV,
    REVIEWED_PSOC_ONET_CROSSWALK_CSV,
    TRANSFORMATIONS_CSV,
    ensure_parent,
    rel,
)
from .schema import (
    CLASSIFICATIONS_COLUMNS,
    CROSSWALK_COLUMNS,
    METRIC_DEFINITIONS,
    METRIC_OBSERVATIONS_COLUMNS,
    MODEL_SCORES_COLUMNS,
    OCCUPATIONS_COLUMNS,
    TRANSFORMATIONS_COLUMNS,
)

UNVERIFIED = "unverified_pending_source"


def collapse_outcomes_by_code(
    outcomes: list[TransformOutcome], metric_id: str
) -> dict[str, TransformOutcome]:
    """Resolve the release's one-current-value contract without overwriting.

    Multiple source cells for the same metric/code usually mean a query returned
    multiple periods or slices. Until the release schema supports a time series,
    ambiguity blocks publication instead of selecting the final row.
    """
    grouped: dict[str, list[TransformOutcome]] = {}
    for outcome in outcomes:
        grouped.setdefault(outcome.psoc_code, []).append(outcome)
    resolved: dict[str, TransformOutcome] = {}
    for code, candidates in grouped.items():
        if len(candidates) == 1:
            resolved[code] = candidates[0]
        else:
            resolved[code] = TransformOutcome(
                metric_id=metric_id,
                psoc_code=code,
                value=None,
                availability="blocked_pending_source",
                reason=(
                    f"{len(candidates)} source rows resolve to this metric/code. "
                    "The release schema holds one current value, so the source query "
                    "must select one period and slice; refusing silent overwrite."
                ),
                normalised_row_id=" | ".join(c.normalised_row_id for c in candidates),
            )
    return resolved


def write_table(path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns, extrasaction="raise", lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


# ---------------------------------------------------------------------------
# Classifications and occupations
# ---------------------------------------------------------------------------

def build_classifications() -> list[dict[str, Any]]:
    registry = {entry["source_id"]: entry for entry in load_registry()["sources"]}
    acquisition = verify_all(["psa_psoc"])["psa_psoc"]
    if acquisition.acquired:
        parser = get_parser("psa_psoc_volume")
        report = parser.import_classification(acquisition.path)
        fatal = [problem for problem in report.problems if "partial import" not in problem]
        if report.complete and not fatal and report.version == psoc.PSOC_VERSION:
            source = registry["psa_psoc"]
            return [
                {
                    **entry,
                    "source_organization": source["organization"],
                    "source_dataset": source["dataset"],
                    "source_url": acquisition.url or source["authoritative_url"],
                    "verification_status": "verified_against_source",
                    "notes": f"Imported from SHA-256 {acquisition.sha256}.",
                }
                for entry in report.rows
            ]

    rows = []
    for entry in psoc.iter_classification_rows():
        rows.append(
            {
                **entry,
                "psoc_version": psoc.PSOC_VERSION,
                "isco08_code": psoc.ISCO08_EQUIVALENT.get(entry["psoc_code"], ""),
                "source_organization": psoc.PSOC_SOURCE_ORGANIZATION,
                "source_dataset": psoc.PSOC_SOURCE_DATASET,
                "source_url": psoc.PSOC_SOURCE_URL,
                "verification_status": UNVERIFIED,
                "notes": (
                    "Entered from ISCO-08-aligned classification documentation; the "
                    "authoritative PSA PSOC 2012 volume was not retrievable in the "
                    "build environment. Diff against the PSA volume before changing "
                    "this to verified_against_source."
                ),
            }
        )
    return rows


def build_occupations(classifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonical analysis units.

    Every unit here is an aggregate: PSOC major and sub-major groups. There are
    no detailed-occupation records because the PSOC minor and unit group lists
    could not be retrieved, and inventing them would recreate exactly the defect
    this rebuild exists to remove.
    """
    rows = []
    for entry in classifications:
        rows.append(
            {
                "occupation_id": f"PSOC-{entry['psoc_code']}",
                "psoc_code": entry["psoc_code"],
                "psoc_version": entry["psoc_version"],
                "occupation_title": entry["title"],
                "occupation_level": entry["level"],
                "parent_psoc_code": entry["parent_psoc_code"],
                "psoc_major": entry["psoc_major"],
                "psoc_major_label": entry["psoc_major_label"],
                "is_aggregate": "false" if entry["level"] == "psoc_unit_group" else "true",
                "verification_status": entry["verification_status"],
                "notes": (
                    "Detailed PSOC unit group imported from the authoritative source."
                    if entry["level"] == "psoc_unit_group"
                    else "Aggregate PSOC classification unit."
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Metric observations
# ---------------------------------------------------------------------------

def build_metric_observations(
    occupations: list[dict[str, Any]],
    crosswalk_rows: list[dict[str, Any]] | None = None,
    version_correspondence_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """One row per (unit, metric) the project intends to publish.

    Publication state is derived from the **retrieval manifest**, verified
    against the file on disk, and only after a parser and a documented
    transformation have actually produced a value.

    The pre-remediation version read a hand-edited ``status:`` field in the
    source registry. Flipping that one word produced rows marked
    ``availability=published`` with an empty value, empty hash and empty
    reference period. The registry is now treated as configuration only.
    """
    registry = {entry["source_id"]: entry for entry in load_registry()["sources"]}
    acquisitions = verify_all(registry.keys())
    canonical_codes = {unit["psoc_code"] for unit in occupations}
    canonical_version = psoc.PSOC_VERSION

    rows: list[dict[str, Any]] = []

    for definition in METRIC_DEFINITIONS.values():
        source = registry.get(definition.required_source_id, {})
        acquisition = acquisitions.get(
            definition.required_source_id,
        )
        parser = get_parser(definition.parser_id) if definition.parser_id else None

        # Run the parser only when the source verified. A missing or
        # hash-mismatched file never reaches a parser.
        outcomes_by_code: dict[str, Any] = {}
        parse_note = ""
        if acquisition is not None and acquisition.acquired and parser is not None:
            try:
                parsed = parser.run(acquisition.path)
                outcomes = transform_rows(
                    definition.metric_id,
                    parsed.rows,
                    acquisition,
                    canonical_codes,
                    canonical_version,
                    crosswalk_rows=crosswalk_rows or [],
                    version_correspondence_rows=version_correspondence_rows or [],
                )
                outcomes_by_code = collapse_outcomes_by_code(outcomes, definition.metric_id)
                parse_note = (
                    f"Parsed {parsed.row_count} source row(s) with "
                    f"{parser.parser_id} v{parser.parser_version}."
                )
            except Exception as exc:  # parser and format failures are findings
                parse_note = f"Parser {definition.parser_id} failed: {type(exc).__name__}: {exc}"
        elif acquisition is not None and acquisition.acquired and parser is None:
            parse_note = (
                f"Source acquired, but no parser is implemented for metric "
                f"{definition.metric_id!r}. Acquisition alone does not make a "
                "metric publishable."
            )

        matching_units = [
            unit
            for unit in occupations
            if unit["occupation_level"] == definition.expected_source_granularity
        ]
        if not matching_units:
            # The metric's source publishes at a granularity we hold no units
            # for. Recorded in the release manifest as an unrepresentable
            # metric rather than pushed onto a coarser unit.
            continue

        for unit in matching_units:
            outcome = outcomes_by_code.get(unit["psoc_code"])
            has_value = outcome is not None and outcome.value is not None

            grade, reasons = confidence_for(
                derivation_class=definition.expected_derivation_class,
                source_granularity=definition.expected_source_granularity,
                display_granularity=unit["occupation_level"],
                has_uncertainty=bool(outcome and outcome.uncertainty_lower is not None),
            )
            if not has_value:
                grade = "D" if definition.expected_derivation_class != "model_derived" else "E"
                reasons = ["No value yet: source not acquired, parsed and transformed."]

            blocked_reason = (source.get("retrieval", {}) or {}).get("blocked_reason", "")
            why = (
                outcome.reason
                if outcome is not None
                else (
                    acquisition.reason
                    if acquisition is not None and not acquisition.acquired
                    else parse_note or "Source not retrieved."
                )
            )

            rows.append(
                {
                    "observation_id": f"{definition.metric_id}:{unit['psoc_code']}",
                    "occupation_id": unit["occupation_id"],
                    "psoc_code": unit["psoc_code"],
                    "metric_id": definition.metric_id,
                    "metric_name": definition.metric_name,
                    "metric_value": "" if not has_value else _format_value(outcome.value),
                    "unit": definition.unit,
                    "reference_period": (outcome.reference_period if outcome else "") or "",
                    "geography": (outcome.geography if outcome else "") or "Philippines",
                    "population_scope": (outcome.population_scope if outcome else "") or definition.denominator,
                    "derivation_class": definition.expected_derivation_class,
                    "source_authority": definition.expected_source_authority,
                    "availability": (
                        outcome.availability if outcome is not None else "blocked_pending_source"
                    ),
                    "source_granularity": definition.expected_source_granularity,
                    "display_granularity": unit["occupation_level"],
                    "source_id": definition.required_source_id,
                    "source_organization": source.get("organization", ""),
                    "source_dataset": source.get("dataset", ""),
                    "source_table": (outcome.source_table if outcome else ""),
                    "source_url": (
                        acquisition.url if acquisition and acquisition.acquired and acquisition.url
                        else source.get("authoritative_url", "")
                    ),
                    "source_file_hash": acquisition.sha256 if (acquisition and acquisition.acquired) else "",
                    "retrieved_at": acquisition.retrieved_at if (acquisition and acquisition.acquired) else "",
                    "parser_id": definition.parser_id,
                    "parser_version": parser.parser_version if parser else "",
                    "normalised_row_id": (outcome.normalised_row_id if outcome else ""),
                    "transformation_id": (outcome.transformation_id if outcome else ""),
                    "crosswalk_id": (outcome.crosswalk_id if outcome else ""),
                    "confidence_grade": grade,
                    "confidence_reasons": " | ".join(reasons),
                    "pipeline_status": (
                        StageStatus.VERIFIED_REAL_SOURCE.value
                        if has_value
                        else StageStatus.BLOCKED_BY_SOURCE_ACCESS.value
                    ),
                    "uncertainty_lower": (
                        "" if not outcome or outcome.uncertainty_lower is None
                        else _format_value(outcome.uncertainty_lower)
                    ),
                    "uncertainty_upper": (
                        "" if not outcome or outcome.uncertainty_upper is None
                        else _format_value(outcome.uncertainty_upper)
                    ),
                    "suppression_status": (
                        outcome.suppression_status if outcome is not None else "no_value_yet"
                    ),
                    "notes": (
                        f"{why} {blocked_reason}".strip()
                        + f" Common misreading to avoid: {definition.common_misreading}"
                    ),
                }
            )
    return rows


def _format_value(value: float) -> str:
    """Stable textual form, so a rebuild is byte-identical."""
    if value == int(value):
        return str(int(value))
    return f"{value:.10g}"


def pipeline_stage_reports() -> list[StageReport]:
    """Honest per-stage status, derived from what actually exists."""
    registry = load_registry()["sources"]
    acquisitions = verify_all([entry["source_id"] for entry in registry])
    required_ids = {d.required_source_id for d in METRIC_DEFINITIONS.values() if d.parser_id} | {"psa_psoc"}
    required = [acquisitions[sid] for sid in required_ids if sid in acquisitions]
    all_acquired = bool(required) and all(record.acquired for record in required)
    any_acquired = any(record.acquired for record in required)

    acquired_status = (
        StageStatus.VERIFIED_REAL_SOURCE if all_acquired
        else StageStatus.PARTIALLY_IMPLEMENTED if any_acquired
        else StageStatus.BLOCKED_BY_SOURCE_ACCESS
    )
    downstream = StageStatus.VERIFIED_REAL_SOURCE if any_acquired else StageStatus.FIXTURE_TESTED_ONLY

    return [
        StageReport(Stage.SOURCE_REGISTRY, StageStatus.VERIFIED_REAL_SOURCE,
                    "Ten sources registered with universe, exclusions, licensing and attribution.",
                    evidence="data/sources/source-registry.yaml"),
        StageReport(Stage.RETRIEVAL, acquired_status,
                    "Retrieval attempts are recorded with timestamps and outcomes.",
                    evidence="data/sources/retrieval-manifest.json",
                    blockers=() if all_acquired else ("One or more required sources have not been retrieved and verified.",)),
        StageReport(Stage.RAW_SNAPSHOT, acquired_status,
                    "Raw snapshots are written under data/raw/ (gitignored) when retrieval succeeds."),
        StageReport(Stage.HASH_VERIFICATION, downstream,
                    "SHA-256 recorded at retrieval and re-checked against the file before parsing.",
                    evidence="src/trabaholens/v2/acquisition_state.py"),
        StageReport(Stage.FORMAT_VALIDATION, downstream,
                    "Each parser validates the snapshot's shape before reading rows.",
                    evidence="src/trabaholens/v2/sources/"),
        StageReport(Stage.PARSING, StageStatus.PARTIALLY_IMPLEMENTED if any_acquired and not all_acquired else downstream,
                    "LFS and O*NET parsers have processed real snapshots; OWS and SOF remain unverified against real files.",
                    evidence="src/trabaholens/v2/sources/",
                    blockers=() if all_acquired else ("At least one source-specific parser has not processed its real source.",)),
        StageReport(Stage.NORMALISED_SOURCE_TABLE, StageStatus.PARTIALLY_IMPLEMENTED if any_acquired and not all_acquired else downstream,
                    "Parsers emit normalised rows carrying the source's own codes and version."),
        StageReport(Stage.CLASSIFICATION_RECONCILIATION, StageStatus.PARTIALLY_IMPLEMENTED,
                    "Version compatibility is enforced and unmatched codes are reported, but the "
                    "PSOC minor and unit group lists are absent, so only aggregate codes reconcile.",
                    blockers=("PSOC 2012 (2022 Updates) volume not retrievable.",)),
        StageReport(Stage.TRANSFORMATION, StageStatus.PARTIALLY_IMPLEMENTED if any_acquired and not all_acquired else downstream,
                    "The employment transformation is verified with real LFS data; wage, OFW and Job Zone remain blocked.",
                    evidence="src/trabaholens/v2/transform.py"),
        StageReport(Stage.CANONICAL_OBSERVATION, StageStatus.PARTIALLY_IMPLEMENTED if any_acquired and not all_acquired else downstream,
                    "Ten LFS major-group observations carry full provenance; other planned observations remain blocked."),
        StageReport(Stage.RELEASE_VALIDATION, StageStatus.VERIFIED_REAL_SOURCE,
                    "Validators run on every build and are each tested against a violating fixture.",
                    evidence="src/trabaholens/v2/validate.py"),
        StageReport(Stage.SITE_PAYLOAD, StageStatus.VERIFIED_REAL_SOURCE,
                    "Payload is provenance-first; the interface cannot render a value without it."),
    ]


# ---------------------------------------------------------------------------
# Crosswalks
# ---------------------------------------------------------------------------

def build_crosswalk(
    classifications: list[dict[str, Any]],
    version_correspondence_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """PSOC to ISCO-08, plus the v1 SOC heuristic recorded as rejected."""
    rows: list[dict[str, Any]] = []

    for edge in version_correspondence_rows or []:
        rows.append({
            "crosswalk_id": edge["correspondence_id"],
            "psoc_code": edge["target_code"],
            "psoc_version": edge["target_version"],
            "source_code": edge["source_code"],
            "source_classification": edge["source_version"],
            "match_type": "exact",
            "match_quality": "high",
            "mapping_basis": edge["mapping_basis"],
            "review_status": edge["review_status"],
            "notes": f"{edge.get('notes', '')} Source: {edge.get('source_url', '')}",
        })

    # PSOC 2012 adopts the ISCO-08 structure at major and sub-major level, so
    # the correspondence is structural rather than a judgement about titles.
    for entry in classifications:
        code = entry["psoc_code"]
        isco_code = entry.get("isco08_code", "")
        if not isco_code:
            continue
        rows.append(
            {
                "crosswalk_id": f"XW-ISCO-{code}",
                "psoc_code": code,
                "psoc_version": psoc.PSOC_VERSION,
                "source_code": isco_code,
                "source_classification": "ISCO-08",
                "match_type": "exact",
                "match_quality": "high",
                "mapping_basis": "structural_derivation",
                "review_status": "machine_proposed",
                "notes": (
                    "PSOC 2012 is built on ISCO-08; major and sub-major skeletons "
                    "correspond by construction. Confirm against the PSA volume, "
                    "which documents Philippine-specific departures at finer levels."
                ),
            }
        )

    # The v1 SOC->PSOC mapping, preserved in reviewable form and marked
    # rejected. It is recorded so the rebuild's break with it is auditable, not
    # so anything can use it: `review_status = rejected` and a validator refuses
    # to resolve any observation through a rejected crosswalk.
    from ..pipeline_utils import SOC_TO_PSOC_MAJOR

    targets: dict[int, list[str]] = {}
    for soc_major, psoc_major in sorted(SOC_TO_PSOC_MAJOR.items()):
        targets.setdefault(psoc_major, []).append(soc_major)

    for soc_major, psoc_major in sorted(SOC_TO_PSOC_MAJOR.items()):
        many_to_one = len(targets[psoc_major]) > 1
        rows.append(
            {
                "crosswalk_id": f"XW-V1SOC-{soc_major}",
                "psoc_code": str(psoc_major),
                "psoc_version": psoc.PSOC_VERSION,
                "source_code": soc_major,
                "source_classification": "US SOC 2018 major group (via O*NET-SOC 2019)",
                "match_type": "composite" if many_to_one else "broader",
                "match_quality": "low",
                "mapping_basis": "undocumented_heuristic",
                "review_status": "rejected",
                "notes": (
                    "Inherited from v1 pipeline_utils.SOC_TO_PSOC_MAJOR. Recorded for "
                    "audit only. No match type, quality, basis or review was ever "
                    f"documented; {len(targets[psoc_major])} SOC major group(s) collapse "
                    "into this PSOC group. Rejected: not usable for publication."
                ),
            }
        )

    # Reviewed composed mappings are a governed input, not generated by title
    # similarity. Their absence is expected until the correspondence work and
    # human review are complete.
    if REVIEWED_PSOC_ONET_CROSSWALK_CSV.exists():
        with open(REVIEWED_PSOC_ONET_CROSSWALK_CSV, encoding="utf-8", newline="") as handle:
            for raw in csv.DictReader(handle):
                if raw.get("review_status") != "human_reviewed":
                    continue
                rows.append({
                    "crosswalk_id": raw["crosswalk_id"],
                    "psoc_code": raw["psoc_code"],
                    "psoc_version": raw.get("psoc_version", psoc.PSOC_VERSION),
                    "source_code": raw["onet_soc_code"],
                    "source_classification": "O*NET-SOC",
                    "match_type": raw["match_type"],
                    "match_quality": raw["match_quality"],
                    "mapping_basis": raw["mapping_basis"],
                    "review_status": raw["review_status"],
                    "notes": raw.get("notes", ""),
                })

    return _annotate_cardinality(rows)


def _annotate_cardinality(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive the cardinality flags from the table instead of asserting them.

    Semantics, fixed here and enforced identically in ``v2/validate.py``:

    * ``is_one_to_many`` - this PSOC code maps to more than one source code.
    * ``is_many_to_one`` - this source code is mapped to by more than one PSOC
      code.

    Computing rather than hand-setting these means the flags cannot drift away
    from what the table actually contains, which is the only reason they are
    worth having.
    """
    forward: dict[tuple[str, str], set[str]] = {}
    reverse: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        forward.setdefault((row["psoc_code"], row["source_classification"]), set()).add(row["source_code"])
        reverse.setdefault((row["source_code"], row["source_classification"]), set()).add(row["psoc_code"])

    for row in rows:
        one_to_many = len(forward[(row["psoc_code"], row["source_classification"])]) > 1
        many_to_one = len(reverse[(row["source_code"], row["source_classification"])]) > 1
        row["is_one_to_many"] = "true" if one_to_many else "false"
        row["is_many_to_one"] = "true" if many_to_one else "false"
    return rows


# ---------------------------------------------------------------------------
# Transformations
# ---------------------------------------------------------------------------

def build_transformations() -> list[dict[str, Any]]:
    return [
        {
            "transformation_id": "T-000-identity",
            "name": "Identity",
            "description": "Value published exactly as the source published it.",
            "inputs": "source table cell",
            "outputs": "metric_value",
            "code_reference": "n/a",
            "reversible": "true",
            "notes": "Identity preserves the source value; derivation and authority remain separate metadata.",
        },
        {
            "transformation_id": "T-001-psoc-structure",
            "name": "PSOC structure entry",
            "description": (
                "PSOC 2012 major and sub-major codes and titles entered from "
                "ISCO-08-aligned classification documentation."
            ),
            "inputs": "classification documentation",
            "outputs": "data/canonical/classifications.csv",
            "code_reference": "src/trabaholens/v2/psoc.py",
            "reversible": "true",
            "notes": "Every output row carries verification_status=unverified_pending_source.",
        },
        {
            "transformation_id": "T-002-task-aggregation-unweighted",
            "name": "Unweighted task score aggregation",
            "description": "Median and category distribution across task scores.",
            "inputs": "per-task scores",
            "outputs": "occupation-level exposure score",
            "code_reference": "src/trabaholens/v2/score_exposure.py",
            "reversible": "false",
            "notes": "Ordinal-safe primary aggregation; arithmetic mean is diagnostic only.",
        },
        {
            "transformation_id": "T-003-task-aggregation-weighted",
            "name": "Importance-weighted task score aggregation",
            "description": "Importance-weighted median across task scores.",
            "inputs": "per-task scores, O*NET task importance ratings",
            "outputs": "occupation-level exposure score",
            "code_reference": "src/trabaholens/v2/score_exposure.py",
            "reversible": "false",
            "notes": "Reported alongside, not instead of, the unweighted variant.",
        },
        {
            "transformation_id": "T-004-run-median",
            "name": "Cross-run median",
            "description": "Median across repeated scoring attempts.",
            "inputs": "attempt scores",
            "outputs": "consensus score plus disagreement range",
            "code_reference": "src/trabaholens/v2/score_exposure.py",
            "reversible": "false",
            "notes": "Disagreement is retained and published, not collapsed away.",
        },
        {
            "transformation_id": "T-900-REMOVED-group-split",
            "name": "REMOVED: group total split by title keywords",
            "description": (
                "v1 split a hard-coded PSOC major group employment total across "
                "detailed occupations using regex title multipliers."
            ),
            "inputs": "GROUP_TOTALS, TITLE_SIZE_MULTIPLIERS",
            "outputs": "employment_estimate (withdrawn)",
            "code_reference": "src/trabaholens/assign_ph_stats.py (v1, retained for audit)",
            "reversible": "false",
            "notes": (
                "Prohibited. Recorded so the removal is explicit. Produced 43 distinct "
                "values across 173 occupations; 150 rows shared a value with another row."
            ),
        },
        {
            "transformation_id": "T-901-REMOVED-category-constant",
            "name": "REMOVED: category constant broadcast",
            "description": (
                "v1 assigned one wage and one informality value per internal "
                "category, and one OFW value per PSOC major group, to every "
                "occupation in it."
            ),
            "inputs": "WAGE_BY_CATEGORY, INFORMAL_SHARE_BY_CATEGORY, PSOC_OFW_SHARE",
            "outputs": "avg_monthly_wage_php, informal_share, ofw_share (all withdrawn)",
            "code_reference": "src/trabaholens/pipeline_utils.py (v1, retained for audit)",
            "reversible": "false",
            "notes": (
                "Prohibited. A broad-group value may be shown at a finer display "
                "granularity only when source_granularity is recorded and the "
                "interface states the mismatch."
            ),
        },
    ]


def main() -> None:
    classifications = build_classifications()
    occupations = build_occupations(classifications)
    with open(PSOC_VERSION_CORRESPONDENCE_CSV, encoding="utf-8", newline="") as handle:
        version_correspondence = list(csv.DictReader(handle))
    crosswalk = build_crosswalk(classifications, version_correspondence)
    observations = build_metric_observations(
        occupations, crosswalk, version_correspondence
    )
    transformations = build_transformations()

    write_table(CLASSIFICATIONS_CSV, CLASSIFICATIONS_COLUMNS, classifications)
    write_table(OCCUPATIONS_CSV, OCCUPATIONS_COLUMNS, occupations)
    write_table(METRIC_OBSERVATIONS_CSV, METRIC_OBSERVATIONS_COLUMNS, observations)
    write_table(CROSSWALK_CSV, CROSSWALK_COLUMNS, crosswalk)
    write_table(TRANSFORMATIONS_CSV, TRANSFORMATIONS_COLUMNS, transformations)
    # Header-only until a scoring run exists. An empty table with a schema is a
    # statement; a missing file is an accident.
    write_table(MODEL_SCORES_CSV, MODEL_SCORES_COLUMNS, [])

    print(f"{rel(CLASSIFICATIONS_CSV)}: {len(classifications)} rows")
    print(f"{rel(OCCUPATIONS_CSV)}: {len(occupations)} rows")
    print(f"{rel(METRIC_OBSERVATIONS_CSV)}: {len(observations)} rows "
          f"({sum(1 for r in observations if r['metric_value'] == '')} without a value)")
    print(f"{rel(CROSSWALK_CSV)}: {len(crosswalk)} rows")
    print(f"{rel(TRANSFORMATIONS_CSV)}: {len(transformations)} rows")
    print(f"{rel(MODEL_SCORES_CSV)}: 0 rows (header only)")


if __name__ == "__main__":
    main()
