"""Pipeline stage model.

The previous branch described the project as "acquisition, hashing, manifest and
validators are complete; only the bytes are missing". That was false: parsing,
classification reconciliation, estimation and source-to-observation construction
did not exist. A single "blocked" word cannot distinguish code that runs against
real data from code that has only ever seen a fixture.

So stage status is a closed vocabulary, recorded per stage, derived at build
time, and carried into the release manifest. Documentation renders it rather
than restating it in prose that can drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StageStatus(str, Enum):
    """How far a pipeline stage actually is. Ordered best to worst."""

    VERIFIED_REAL_SOURCE = "implemented_verified_with_real_source"
    FIXTURE_TESTED_ONLY = "implemented_fixture_tested_only"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    DESIGNED_NOT_IMPLEMENTED = "designed_not_implemented"
    BLOCKED_BY_SOURCE_ACCESS = "blocked_by_source_access"
    BLOCKED_BY_METHODOLOGY = "blocked_by_unresolved_methodology"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    REJECTED = "rejected"


STATUS_EXPLANATION = {
    StageStatus.VERIFIED_REAL_SOURCE: (
        "Implemented, and exercised end to end against the real primary source."
    ),
    StageStatus.FIXTURE_TESTED_ONLY: (
        "Implemented and covered by tests, but only against a synthetic fixture. "
        "It has never processed the real source."
    ),
    StageStatus.PARTIALLY_IMPLEMENTED: (
        "Some of the stage exists; named parts are missing."
    ),
    StageStatus.DESIGNED_NOT_IMPLEMENTED: (
        "Specified in the methodology, with no implementation yet."
    ),
    StageStatus.BLOCKED_BY_SOURCE_ACCESS: (
        "Cannot proceed because the source cannot be retrieved in this environment."
    ),
    StageStatus.BLOCKED_BY_METHODOLOGY: (
        "Cannot proceed because a methodological question is unresolved."
    ),
    StageStatus.AWAITING_HUMAN_REVIEW: (
        "Implemented, but its output must be reviewed by a person before use."
    ),
    StageStatus.REJECTED: (
        "Considered and deliberately not done. The reason is recorded."
    ),
}


class Stage(str, Enum):
    """The stages a value must pass through to be published.

    Ordered. A value may not skip one.
    """

    SOURCE_REGISTRY = "source_registry"
    RETRIEVAL = "retrieval"
    RAW_SNAPSHOT = "raw_snapshot"
    HASH_VERIFICATION = "hash_verification"
    FORMAT_VALIDATION = "format_validation"
    PARSING = "parsing"
    NORMALISED_SOURCE_TABLE = "normalised_source_table"
    CLASSIFICATION_RECONCILIATION = "classification_reconciliation"
    TRANSFORMATION = "transformation"
    CANONICAL_OBSERVATION = "canonical_observation"
    RELEASE_VALIDATION = "release_validation"
    SITE_PAYLOAD = "site_payload"


STAGE_ORDER = list(Stage)


@dataclass(frozen=True)
class StageReport:
    stage: Stage
    status: StageStatus
    detail: str
    evidence: str = ""
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "status_meaning": STATUS_EXPLANATION[self.status],
            "detail": self.detail,
            "evidence": self.evidence,
            "blockers": list(self.blockers),
        }


def worst_status(statuses) -> StageStatus:
    """A chain is only as good as its weakest stage."""
    order = list(StageStatus)
    worst = StageStatus.VERIFIED_REAL_SOURCE
    for status in statuses:
        if order.index(status) > order.index(worst):
            worst = status
    return worst


def publishable(status: StageStatus) -> bool:
    """Only a stage verified against the real source may back a published value.

    Fixture-tested code is correct code with no evidence behind it. It may not
    put a number in front of a reader.
    """
    return status is StageStatus.VERIFIED_REAL_SOURCE
