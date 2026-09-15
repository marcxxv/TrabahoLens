"""Normalised source rows -> canonical metric observations.

This is the stage that decides whether a number may be published, and it is
deliberately strict. A row reaches a canonical observation only if **all** of
these hold:

1. the source was acquired and hash-verified;
2. a parser produced the row;
3. the row's classification version is known and compatible with ours;
4. the row's code reconciles to a canonical PSOC unit;
5. a documented transformation applies;
6. the provenance is complete.

Any failure produces an observation with **no value** and a reason, never a
substituted number. That is the whole point: a visible gap is information.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .acquisition_state import AcquisitionRecord
from .schema import METRIC_DEFINITIONS
from .sources.base import NormalisedRow


@dataclass(frozen=True)
class Transformation:
    transformation_id: str
    name: str
    description: str
    applies_to_measure: str
    produces_metric: str
    #: Pure function from normalised value to canonical value.
    factor: float = 1.0

    def apply(self, value: float) -> float:
        return value * self.factor


#: Identity transformations for now. A share computed from a count and a
#: denominator would be a different entry with its own id, and its own test.
TRANSFORMATIONS: dict[str, Transformation] = {
    "T-000-identity": Transformation(
        transformation_id="T-000-identity",
        name="Identity",
        description="Value published exactly as the source published it.",
        applies_to_measure="*",
        produces_metric="*",
    ),
    "T-010-lfs-employment": Transformation(
        transformation_id="T-010-lfs-employment",
        name="LFS employed persons to employment_count",
        description=(
            "Take the LFS employed-persons count for a PSOC group unchanged. "
            "No redistribution across finer occupations is permitted."
        ),
        applies_to_measure="employed_persons",
        produces_metric="employment_count",
    ),
    "T-011-ows-basic-pay": Transformation(
        transformation_id="T-011-ows-basic-pay",
        name="OWS average monthly basic pay to wage_basic_pay",
        description=(
            "Take the OWS average monthly basic pay for an occupation unchanged. "
            "Carries the OWS establishment universe and its exclusions."
        ),
        applies_to_measure="average_monthly_basic_pay",
        produces_metric="wage_basic_pay",
    ),
    "T-012-sof-distribution": Transformation(
        transformation_id="T-012-sof-distribution",
        name="SOF OFW counts to distribution share",
        description=(
            "Divide the OFW count for a major occupation group by the total OFW "
            "count across all groups. This is P(occupation | OFW). It is NOT the "
            "share of an occupation's workers who are OFWs."
        ),
        applies_to_measure="ofw_count_by_major_occupation",
        produces_metric="ofw_distribution_share",
    ),
    "T-013-onet-job-zone": Transformation(
        transformation_id="T-013-onet-job-zone",
        name="O*NET Job Zone as a US proxy",
        description=(
            "Carry the US Job Zone across a reviewed crosswalk. Remains "
            "proxy-derived and carries the crosswalk quality."
        ),
        applies_to_measure="job_zone",
        produces_metric="onet_job_zone",
    ),
}

TRANSFORMATION_BY_METRIC = {
    t.produces_metric: t for t in TRANSFORMATIONS.values() if t.produces_metric != "*"
}

#: Classification versions this project can reconcile without a correspondence
#: table. Anything else must go through an explicit mapping, not an assumption.
COMPATIBLE_PSOC_VERSIONS = {"PSOC 2012", "PSOC 2012 (2022 Updates)"}


@dataclass
class TransformOutcome:
    metric_id: str
    psoc_code: str
    value: float | None
    reason: str
    transformation_id: str = ""
    normalised_row_id: str = ""
    reference_period: str = ""
    suppression_status: str = "no_value_yet"
    availability: str = "blocked_pending_source"
    uncertainty_lower: float | None = None
    uncertainty_upper: float | None = None


def _sum_for_share(rows: list[NormalisedRow], measure: str) -> float | None:
    values = [r.value for r in rows if r.measure == measure and r.value is not None]
    total = sum(values)
    return total if total > 0 else None


def transform_rows(
    metric_id: str,
    rows: list[NormalisedRow],
    acquisition: AcquisitionRecord,
    canonical_codes: set[str],
    canonical_version: str,
) -> list[TransformOutcome]:
    """Apply the documented transformation for one metric.

    ``canonical_codes`` are the PSOC codes our classification table holds. A row
    whose code is not among them is reported unmatched rather than dropped,
    because a source code we cannot place is a finding about our classification.
    """
    definition = METRIC_DEFINITIONS[metric_id]
    transformation = TRANSFORMATION_BY_METRIC.get(metric_id)
    outcomes: list[TransformOutcome] = []

    if not acquisition.acquired:
        return outcomes
    if transformation is None:
        return outcomes

    relevant = [r for r in rows if r.measure == transformation.applies_to_measure]
    denominator = (
        _sum_for_share(relevant, transformation.applies_to_measure)
        if metric_id == "ofw_distribution_share"
        else None
    )

    for row in relevant:
        # Classification version must be known and compatible. "unknown" is a
        # refusal, not a default: silently applying 2022 codes to a table that
        # used an earlier version is the failure mode this guard exists for.
        if row.source_code_version not in COMPATIBLE_PSOC_VERSIONS and row.source_code_system == "PSOC":
            outcomes.append(
                TransformOutcome(
                    metric_id=metric_id,
                    psoc_code=row.source_code,
                    value=None,
                    reason=(
                        f"Source classification version {row.source_code_version!r} is not "
                        f"reconcilable with the canonical {canonical_version!r} without an "
                        "explicit correspondence table."
                    ),
                    availability="blocked_pending_source",
                    suppression_status="no_value_yet",
                    normalised_row_id=row.normalised_row_id,
                )
            )
            continue

        if row.source_code not in canonical_codes:
            outcomes.append(
                TransformOutcome(
                    metric_id=metric_id,
                    psoc_code=row.source_code,
                    value=None,
                    reason=(
                        f"Source code {row.source_code!r} has no canonical PSOC unit. "
                        "Recorded as unmatched rather than dropped."
                    ),
                    availability="blocked_pending_source",
                    normalised_row_id=row.normalised_row_id,
                )
            )
            continue

        if row.suppression_flag == "suppressed_by_publisher":
            outcomes.append(
                TransformOutcome(
                    metric_id=metric_id,
                    psoc_code=row.source_code,
                    value=None,
                    reason="The publisher suppressed this cell.",
                    availability="suppressed_low_sample",
                    suppression_status="suppressed_by_publisher",
                    transformation_id=transformation.transformation_id,
                    normalised_row_id=row.normalised_row_id,
                    reference_period=row.reference_period,
                )
            )
            continue

        if row.value is None:
            outcomes.append(
                TransformOutcome(
                    metric_id=metric_id,
                    psoc_code=row.source_code,
                    value=None,
                    reason=f"No value in the source row ({row.suppression_flag or 'missing'}).",
                    availability="blocked_pending_source",
                    normalised_row_id=row.normalised_row_id,
                    reference_period=row.reference_period,
                )
            )
            continue

        if not row.reference_period:
            outcomes.append(
                TransformOutcome(
                    metric_id=metric_id,
                    psoc_code=row.source_code,
                    value=None,
                    reason="Source row carries no reference period; refusing to publish an undated figure.",
                    availability="blocked_pending_source",
                    normalised_row_id=row.normalised_row_id,
                )
            )
            continue

        if metric_id == "ofw_distribution_share":
            if not denominator:
                outcomes.append(
                    TransformOutcome(
                        metric_id=metric_id,
                        psoc_code=row.source_code,
                        value=None,
                        reason="Cannot compute a share: the all-OFW denominator is zero or absent.",
                        availability="blocked_pending_source",
                        normalised_row_id=row.normalised_row_id,
                    )
                )
                continue
            value = row.value / denominator
        else:
            value = transformation.apply(row.value)

        outcomes.append(
            TransformOutcome(
                metric_id=metric_id,
                psoc_code=row.source_code,
                value=value,
                reason="Transformed and published.",
                transformation_id=transformation.transformation_id,
                normalised_row_id=row.normalised_row_id,
                reference_period=row.reference_period,
                availability="published",
                suppression_status="not_suppressed",
                uncertainty_lower=row.uncertainty_lower,
                uncertainty_upper=row.uncertainty_upper,
            )
        )

    _ = definition
    return outcomes


def confidence_for(
    *,
    derivation_class: str,
    source_granularity: str,
    display_granularity: str,
    has_uncertainty: bool,
    crosswalk_quality: str = "",
) -> tuple[str, list[str]]:
    """Deterministic confidence grade plus the reasons behind it.

    Returned as (grade, reasons) so the interface can publish *why*, not just a
    letter. Nothing here is a judgement call at runtime; it is a rule table.
    """
    reasons: list[str] = []

    if derivation_class == "model_derived":
        return "E", ["Model-derived: experimental, no observational backing."]

    if derivation_class == "proxy_derived":
        reasons.append("Proxy-derived: measured on a different population than shown.")
        if crosswalk_quality in {"low", "", "none"}:
            reasons.append(f"Crosswalk quality {crosswalk_quality or 'unrecorded'}.")
            return "E", reasons
        return "D", reasons

    granularity_order = [
        "national", "psoc_major_group", "psoc_sub_major_group",
        "psoc_minor_group", "psoc_unit_group", "occupation",
    ]
    coarser = (
        source_granularity in granularity_order
        and display_granularity in granularity_order
        and granularity_order.index(source_granularity) < granularity_order.index(display_granularity)
    )
    if coarser:
        reasons.append(
            f"Source published at {source_granularity}, displayed at {display_granularity}."
        )
        return "C", reasons

    if derivation_class == "estimated":
        reasons.append("Sample-survey estimate.")
        if has_uncertainty:
            reasons.append("Sampling error published by the source.")
            return "A", reasons
        reasons.append("Source did not publish sampling error.")
        return "B", reasons

    if derivation_class == "calculated":
        reasons.append("Calculated by this project from published figures.")
        return "B" if has_uncertainty else "C", reasons

    if derivation_class == "directly_observed":
        reasons.append("Complete enumeration or administrative record.")
        return "A", reasons

    return "D", ["Unrecognised derivation class."]
