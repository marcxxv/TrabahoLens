"""Parser interface and the normalised-source-row contract."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from ..pipeline import StageStatus


class FormatValidationError(ValueError):
    """The snapshot is not the shape this parser expects.

    Raised *before* parsing, so a wrong or truncated download fails with a
    description of what was expected rather than a confusing row-level error
    fifty lines later.
    """


@dataclass(frozen=True)
class NormalisedRow:
    """One fact as the source states it, before any mapping or transformation.

    ``source_code`` is the source's own classification code in the source's own
    classification version. It is deliberately not a PSOC code: reconciliation is
    a later, separately reviewable stage.
    """

    normalised_row_id: str
    source_id: str
    source_table: str
    source_code: str
    source_code_system: str
    source_code_version: str
    source_label: str
    measure: str
    value: float | None
    unit: str
    reference_period: str
    geography: str
    population_scope: str
    suppression_flag: str = ""
    uncertainty_lower: float | None = None
    uncertainty_upper: float | None = None
    notes: str = ""
    standard_error: float | None = None
    coefficient_of_variation: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "normalised_row_id": self.normalised_row_id,
            "source_id": self.source_id,
            "source_table": self.source_table,
            "source_code": self.source_code,
            "source_code_system": self.source_code_system,
            "source_code_version": self.source_code_version,
            "source_label": self.source_label,
            "measure": self.measure,
            "value": "" if self.value is None else self.value,
            "unit": self.unit,
            "reference_period": self.reference_period,
            "geography": self.geography,
            "population_scope": self.population_scope,
            "suppression_flag": self.suppression_flag,
            "uncertainty_lower": "" if self.uncertainty_lower is None else self.uncertainty_lower,
            "uncertainty_upper": "" if self.uncertainty_upper is None else self.uncertainty_upper,
            "notes": self.notes,
            "standard_error": self.standard_error if self.standard_error is not None else "",
            "coefficient_of_variation": self.coefficient_of_variation if self.coefficient_of_variation is not None else "",
        }


NORMALISED_ROW_COLUMNS = [
    "normalised_row_id", "source_id", "source_table", "source_code",
    "source_code_system", "source_code_version", "source_label", "measure",
    "value", "unit", "reference_period", "geography", "population_scope",
    "suppression_flag", "uncertainty_lower", "uncertainty_upper", "notes",
    "standard_error", "coefficient_of_variation",
]


@dataclass
class ParseResult:
    parser_id: str
    parser_version: str
    rows: list[NormalisedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)


class SourceParser(abc.ABC):
    """Turn one verified snapshot into normalised source rows.

    A parser never decides whether something is publishable. It reports what the
    source says; the transformation and validation stages decide the rest.
    """

    parser_id: str = ""
    parser_version: str = "0.1.0"
    source_id: str = ""
    #: Classification system and version the source's own codes are in.
    source_code_system: str = ""
    #: Default status; release reporting derives per-source real-run status from
    #: verified snapshots and canonical outputs.
    status: StageStatus = StageStatus.FIXTURE_TESTED_ONLY

    @abc.abstractmethod
    def validate_format(self, path: Path) -> None:
        """Raise FormatValidationError if the snapshot is not what we expect."""

    @abc.abstractmethod
    def parse(self, path: Path) -> ParseResult:
        """Parse a snapshot that has already passed validate_format."""

    def run(self, path: Path) -> ParseResult:
        self.validate_format(path)
        return self.parse(path)


_REGISTRY: dict[str, SourceParser] = {}


def register(parser_class: type[SourceParser]) -> type[SourceParser]:
    """Class decorator. Registers a single shared instance.

    Parsers are stateless, so one instance per id is enough; registering the
    class itself would hand callers an unbound ``run``.
    """
    if not parser_class.parser_id:
        raise ValueError("parser_id is required")
    _REGISTRY[parser_class.parser_id] = parser_class()
    return parser_class


def get_parser(parser_id: str) -> SourceParser | None:
    return _REGISTRY.get(parser_id)


def registered_parsers() -> dict[str, SourceParser]:
    return dict(_REGISTRY)


def rows_by_measure(rows: Iterable[NormalisedRow], measure: str) -> list[NormalisedRow]:
    return [row for row in rows if row.measure == measure]
