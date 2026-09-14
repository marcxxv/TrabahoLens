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
from .paths import (
    CLASSIFICATIONS_CSV,
    CROSSWALK_CSV,
    METRIC_OBSERVATIONS_CSV,
    MODEL_SCORES_CSV,
    OCCUPATIONS_CSV,
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


def write_table(path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


# ---------------------------------------------------------------------------
# Classifications and occupations
# ---------------------------------------------------------------------------

def build_classifications() -> list[dict[str, Any]]:
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
                "is_aggregate": "true",
                "verification_status": UNVERIFIED,
                "notes": (
                    "Aggregate classification unit. Detailed (minor and unit group) "
                    "occupations are absent pending retrieval of the PSOC 2012 volume."
                ),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Metric observations
# ---------------------------------------------------------------------------

def build_metric_observations(occupations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (unit, metric) the project intends to publish.

    Each row declares what would be published, from where, at what granularity,
    and why it currently has no value. `metric_value` stays empty: a blocked
    metric is never given a zero, a midpoint, or a neighbour's number.
    """
    registry = {entry["source_id"]: entry for entry in load_registry()["sources"]}
    rows: list[dict[str, Any]] = []

    for definition in METRIC_DEFINITIONS.values():
        source = registry.get(definition.required_source_id, {})
        retrieval = source.get("retrieval", {})
        retrieved = retrieval.get("status") == "retrieved"

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
            rows.append(
                {
                    "observation_id": f"{definition.metric_id}:{unit['psoc_code']}",
                    "occupation_id": unit["occupation_id"],
                    "psoc_code": unit["psoc_code"],
                    "metric_id": definition.metric_id,
                    "metric_name": definition.metric_name,
                    # Deliberately empty. See module docstring.
                    "metric_value": "",
                    "unit": definition.unit,
                    "reference_period": "",
                    "geography": "Philippines",
                    "population_scope": definition.denominator,
                    "estimate_type": definition.expected_estimate_type,
                    "availability": "published" if retrieved else "blocked_pending_source",
                    "source_granularity": definition.expected_source_granularity,
                    "display_granularity": unit["occupation_level"],
                    "source_id": definition.required_source_id,
                    "source_organization": source.get("organization", ""),
                    "source_dataset": source.get("dataset", ""),
                    "source_table": "",
                    "source_url": source.get("authoritative_url", ""),
                    "source_file_hash": "",
                    "retrieved_at": "",
                    "transformation_id": "",
                    "crosswalk_id": "",
                    # D: source specified but not yet retrieved and verified.
                    "confidence_grade": "D",
                    "uncertainty_lower": "",
                    "uncertainty_upper": "",
                    "suppression_status": "no_value_yet",
                    "notes": (
                        f"{retrieval.get('blocked_reason', 'Source not retrieved.').strip()} "
                        f"Common misreading to avoid: {definition.common_misreading}"
                    ),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Crosswalks
# ---------------------------------------------------------------------------

def build_crosswalk(classifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PSOC to ISCO-08, plus the v1 SOC heuristic recorded as rejected."""
    rows: list[dict[str, Any]] = []

    # PSOC 2012 adopts the ISCO-08 structure at major and sub-major level, so
    # the correspondence is structural rather than a judgement about titles.
    for entry in classifications:
        code = entry["psoc_code"]
        rows.append(
            {
                "crosswalk_id": f"XW-ISCO-{code}",
                "psoc_code": code,
                "psoc_version": psoc.PSOC_VERSION,
                "source_code": psoc.ISCO08_EQUIVALENT[code],
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
            "notes": "The only transformation permitted for an official_statistic.",
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
            "description": (
                "Mean of per-task exposure scores for an occupation, all tasks "
                "weighted equally."
            ),
            "inputs": "per-task scores",
            "outputs": "occupation-level exposure score",
            "code_reference": "src/trabaholens/v2/score_exposure.py",
            "reversible": "false",
            "notes": "Kept separate from the importance-weighted variant; never merged.",
        },
        {
            "transformation_id": "T-003-task-aggregation-weighted",
            "name": "Importance-weighted task score aggregation",
            "description": (
                "Per-task exposure scores weighted by O*NET task importance "
                "where importance ratings are available."
            ),
            "inputs": "per-task scores, O*NET task importance ratings",
            "outputs": "occupation-level exposure score",
            "code_reference": "src/trabaholens/v2/score_exposure.py",
            "reversible": "false",
            "notes": "Reported alongside, not instead of, the unweighted variant.",
        },
        {
            "transformation_id": "T-004-run-median",
            "name": "Cross-run median",
            "description": "Median across independent scoring replicates.",
            "inputs": "replicate scores",
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
    observations = build_metric_observations(occupations)
    crosswalk = build_crosswalk(classifications)
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
