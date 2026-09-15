"""Parsers for PSA statistical tables.

PSA OpenSTAT serves PXWeb JSON-stat2. These parsers read that structure, plus a
simple CSV form for tables downloaded by hand.

Every parser records the **source's own** occupational code and classification
version. Which PSOC version a given 2024 round used must be read off the table
metadata, not assumed, because LFS, OWS and SOF do not necessarily move to a new
classification in the same year. If the metadata does not state a version, the
parser records ``unknown`` and the reconciliation stage refuses the rows rather
than guessing.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .base import (
    FormatValidationError,
    NormalisedRow,
    ParseResult,
    SourceParser,
    register,
)

# Values PSA uses to mark a cell it will not publish.
SUPPRESSION_MARKERS = {"..", "...", "-", "*", "n.a.", "na", "s"}


def _classification_version(metadata: dict) -> str:
    """Read the occupational classification version out of table metadata.

    Returns ``unknown`` rather than a default. A wrong version silently applied
    across rounds is exactly the failure this project exists to avoid.
    """
    haystack = json.dumps(metadata).lower()
    # Most specific first: the 2022 update must not be read as plain 2012.
    if "psoc 2022" in haystack or "2022 update" in haystack:
        return "PSOC 2012 (2022 Updates)"
    if "psoc 2012" in haystack:
        return "PSOC 2012"
    if "psoc 1992" in haystack:
        return "PSOC 1992"
    return "unknown"


def _parse_number(raw) -> tuple[float | None, str]:
    """Return (value, suppression_flag). A suppressed cell is never a zero."""
    if raw is None:
        return None, "missing"
    text = str(raw).strip()
    if not text:
        return None, "missing"
    if text.lower() in SUPPRESSION_MARKERS:
        return None, "suppressed_by_publisher"
    try:
        return float(text.replace(",", "")), ""
    except ValueError:
        return None, "unparseable"


class _PxWebCsvParser(SourceParser):
    """Shared behaviour for PSA tables held as JSON-stat2 or flat CSV.

    Accepting both matters in practice: OpenSTAT serves JSON-stat2, but several
    PSA releases are only available as a spreadsheet a person downloads, and a
    manual acquisition should be no less traceable than an automated one.
    """

    measure: str = ""
    unit: str = ""
    population_scope: str = ""
    expected_source_table: str = ""

    def validate_format(self, path: Path) -> None:
        if not path.exists():
            raise FormatValidationError(f"{path} does not exist")
        if path.stat().st_size == 0:
            raise FormatValidationError(f"{path} is empty")

        suffix = path.suffix.lower()
        if suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FormatValidationError(f"{path} is not valid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise FormatValidationError(f"{path}: expected a JSON object at the root")
            if "dimension" not in payload and "dataset" not in payload:
                raise FormatValidationError(
                    f"{path}: no 'dimension' or 'dataset' key — this does not look "
                    "like PXWeb json-stat2 output."
                )
        elif suffix == ".csv":
            with open(path, encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), None)
            if not header:
                raise FormatValidationError(f"{path}: no header row")
            required = {"occupation_code", "occupation_label", "value"}
            missing = required - {column.strip().lower() for column in header}
            if missing:
                raise FormatValidationError(
                    f"{path}: CSV is missing required columns {sorted(missing)}"
                )
        else:
            raise FormatValidationError(
                f"{path}: unsupported extension {suffix!r}; expected .json or .csv"
            )

    def parse(self, path: Path) -> ParseResult:
        if path.suffix.lower() == ".json":
            return self._parse_jsonstat(path)
        return self._parse_csv(path)

    def _parse_csv(self, path: Path) -> ParseResult:
        result = ParseResult(parser_id=self.parser_id, parser_version=self.parser_version)
        with open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = {name.lower(): name for name in (reader.fieldnames or [])}
            version = "unknown"
            period = ""
            for index, raw_row in enumerate(reader):
                row = {key.lower(): value for key, value in raw_row.items()}
                version = (row.get("classification_version") or version or "unknown").strip() or "unknown"
                period = (row.get("reference_period") or period or "").strip()
                value, flag = _parse_number(row.get("value"))
                code = (row.get("occupation_code") or "").strip()
                if not code:
                    result.warnings.append(f"row {index}: no occupation_code; skipped")
                    continue
                result.rows.append(
                    NormalisedRow(
                        normalised_row_id=f"{self.parser_id}:{code}:{index}",
                        source_id=self.source_id,
                        source_table=self.expected_source_table or path.name,
                        source_code=code,
                        source_code_system="PSOC",
                        source_code_version=version,
                        source_label=(row.get("occupation_label") or "").strip(),
                        measure=self.measure,
                        value=value,
                        unit=self.unit,
                        reference_period=period,
                        geography=(row.get("geography") or "Philippines").strip(),
                        population_scope=self.population_scope,
                        suppression_flag=flag,
                        notes=(row.get("notes") or "").strip(),
                    )
                )
            _ = fields
        return result

    def _parse_jsonstat(self, path: Path) -> ParseResult:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = ParseResult(parser_id=self.parser_id, parser_version=self.parser_version)

        dimension = payload.get("dimension", {})
        version = _classification_version(payload)
        occupation_key = next(
            (key for key in dimension if "occupation" in key.lower() or "psoc" in key.lower()),
            None,
        )
        if occupation_key is None:
            result.warnings.append(
                "No occupation dimension found; the table may be by industry rather "
                "than by occupation. No rows produced."
            )
            return result

        category = dimension[occupation_key].get("category", {})
        index_map = category.get("index", {})
        labels = category.get("label", {})
        values = payload.get("value", [])
        period = ""
        time_key = next((key for key in dimension if "time" in key.lower() or "year" in key.lower()), None)
        if time_key:
            time_labels = dimension[time_key].get("category", {}).get("label", {})
            period = ", ".join(str(v) for v in time_labels.values())

        for code, position in sorted(index_map.items(), key=lambda kv: kv[1]):
            raw = values[position] if isinstance(values, list) and position < len(values) else None
            value, flag = _parse_number(raw)
            result.rows.append(
                NormalisedRow(
                    normalised_row_id=f"{self.parser_id}:{code}:{position}",
                    source_id=self.source_id,
                    source_table=self.expected_source_table or path.name,
                    source_code=str(code),
                    source_code_system="PSOC",
                    source_code_version=version,
                    source_label=str(labels.get(code, "")),
                    measure=self.measure,
                    value=value,
                    unit=self.unit,
                    reference_period=period,
                    geography="Philippines",
                    population_scope=self.population_scope,
                    suppression_flag=flag,
                )
            )
        return result


@register
class PsaLfsOccupationParser(_PxWebCsvParser):
    parser_id = "psa_lfs_occupation_table"
    source_id = "psa_lfs"
    measure = "employed_persons"
    unit = "persons"
    population_scope = "employed persons 15 years and over"
    expected_source_table = "LFS employment by occupation"


@register
class PsaOwsOccupationParser(_PxWebCsvParser):
    parser_id = "psa_ows_occupation_table"
    source_id = "psa_ows"
    measure = "average_monthly_basic_pay"
    unit = "PHP per month"
    population_scope = (
        "time-rated workers on full-time basis in establishments covered by OWS; "
        "excludes agriculture, establishments below the size threshold, informal "
        "and own-account workers"
    )
    expected_source_table = "OWS wages by occupation"

    def validate_format(self, path: Path) -> None:
        super().validate_format(path)
        # v1 pointed at an OWS table that was by industry. An industry table
        # cannot produce an occupational wage, so refuse it here by name rather
        # than silently emitting zero rows later.
        haystack = path.name.lower()
        if "industry" in haystack and "occupation" not in haystack:
            raise FormatValidationError(
                f"{path.name} looks like an OWS *industry* table. OWS publishes "
                "separate industry and occupation tables; only the occupation "
                "table can support an occupational wage."
            )


@register
class PsaSofOccupationParser(_PxWebCsvParser):
    parser_id = "psa_sof_occupation_table"
    source_id = "psa_sof"
    # The measure name carries the conditional. This is P(occupation | OFW):
    # of all OFWs, the share whose occupation abroad falls in this group.
    measure = "ofw_count_by_major_occupation"
    unit = "persons"
    population_scope = "overseas Filipino workers as defined by the SOF round"
    expected_source_table = "SOF overseas Filipino workers by major occupation group"
