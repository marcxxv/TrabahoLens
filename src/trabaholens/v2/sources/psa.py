"""Parsers for PSA statistical tables.

PSA OpenSTAT serves PXWeb JSON-stat and JSON-stat2. These parsers read both structures, plus a
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
import itertools
import json
import math
from pathlib import Path

from .base import (
    FormatValidationError,
    NormalisedRow,
    ParseResult,
    SourceParser,
    register,
)

# Values PSA uses to mark a cell it will not publish.
SUPPRESSION_MARKERS = {".", "..", "...", "-", "*", "n.a.", "na", "s"}

PSOC_MAJOR_LABEL_TO_CODE = {
    "Managers": "1",
    "Professionals": "2",
    "Technicians and Associate Professionals": "3",
    "Clerical Support Workers": "4",
    "Service and Sales Workers": "5",
    "Skilled Agricultural Forestry and Fishery Workers": "6",
    "Craft and Related Trades Workers": "7",
    "Plant and Machine Operators and Assemblers": "8",
    "Elementary Occupations": "9",
    "Armed Forces Occupations": "0",
}


def _classification_version(metadata: dict) -> str:
    """Read the occupational classification version out of table metadata.

    Returns ``unknown`` rather than a default. A wrong version silently applied
    across rounds is exactly the failure this project exists to avoid.
    """
    haystack = json.dumps(metadata).lower()
    # Most specific first: the 2022 update must not be read as plain 2012.
    if "psoc 2022" in haystack or "2022 update" in haystack:
        return "PSOC 2012 (2022 Updates)"
    if "psoc 2012" in haystack or "2012 psoc" in haystack:
        return "PSOC 2012"
    if "psoc 1992" in haystack or "1992 psoc" in haystack:
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

    Accepting both matters in practice: OpenSTAT serves JSON-stat variants, but several
    PSA releases are only available as a spreadsheet a person downloads, and a
    manual acquisition should be no less traceable than an automated one.
    """

    measure: str = ""
    parser_version = "0.2.0"
    unit: str = ""
    population_scope: str = ""
    expected_source_table: str = ""
    json_value_factor: float = 1.0
    json_source_unit: str = ""

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
            for index, raw_row in enumerate(reader):
                row = {key.lower(): value for key, value in raw_row.items()}
                # Metadata is row-local. Carrying either field forward silently
                # substitutes a value the source did not provide.
                version = (row.get("classification_version") or "").strip() or "unknown"
                period = (row.get("reference_period") or "").strip()
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
        wrapper = json.loads(path.read_text(encoding="utf-8-sig"))
        # PXWeb's ``json-stat`` format wraps the dataset, whereas
        # ``json-stat2`` places the cube at the root. Both are official output
        # formats and validation has always claimed to accept both.
        payload = wrapper.get("dataset", wrapper)
        result = ParseResult(parser_id=self.parser_id, parser_version=self.parser_version)

        dimension_block = payload.get("dimension", {})
        # JSON-stat 1.x stores id/size/role inside ``dimension``; JSON-stat2
        # stores them beside it. Keep only actual category dimensions here.
        dimension = {
            key: value for key, value in dimension_block.items()
            if isinstance(value, dict) and "category" in value
        }
        version = _classification_version(wrapper)
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

        dimension_ids = payload.get("id") or dimension_block.get("id") or list(dimension)
        sizes = payload.get("size") or dimension_block.get("size") or [
            len(_ordered_category_codes(dimension[key])) for key in dimension_ids
        ]
        if len(dimension_ids) != len(sizes):
            raise FormatValidationError(
                f"{path}: json-stat id/size lengths differ ({len(dimension_ids)} != {len(sizes)})"
            )
        if any(key not in dimension for key in dimension_ids):
            missing = [key for key in dimension_ids if key not in dimension]
            raise FormatValidationError(f"{path}: dimensions named in id are absent: {missing}")

        ordered_codes = [_ordered_category_codes(dimension[key]) for key in dimension_ids]
        for key, expected, codes in zip(dimension_ids, sizes, ordered_codes):
            if int(expected) != len(codes):
                raise FormatValidationError(
                    f"{path}: dimension {key!r} declares size {expected} but has {len(codes)} categories"
                )

        values = payload.get("value", [])
        expected_cells = math.prod(int(size) for size in sizes)
        if isinstance(values, list) and len(values) != expected_cells:
            raise FormatValidationError(
                f"{path}: value array has {len(values)} cells; dimensions require {expected_cells}"
            )
        if not isinstance(values, (list, dict)):
            raise FormatValidationError(f"{path}: json-stat value must be an array or sparse object")

        temporal_keys = [
            key for key in dimension_ids
            if any(token in key.lower() for token in ("time", "year", "month", "quarter", "period"))
        ]
        occupation_position = dimension_ids.index(occupation_key)

        # JSON-stat flattens a multidimensional cube in row-major order (the
        # final dimension changes fastest). Iterate the full Cartesian product
        # so each value keeps its own occupation, period and source slice.
        for flat_index, coordinates in enumerate(itertools.product(*ordered_codes)):
            raw_code = coordinates[occupation_position]
            occupation_label = _category_label(dimension[occupation_key], raw_code)
            code = self._normalise_occupation_code(raw_code, occupation_label)
            if not code:
                continue
            raw = values[flat_index] if isinstance(values, list) else values.get(str(flat_index))
            value, flag = _parse_number(raw)
            if value is not None:
                value *= self.json_value_factor
            period = " ".join(
                _category_label(dimension[key], coordinates[dimension_ids.index(key)])
                for key in temporal_keys
            )
            slice_parts = []
            for key, category_code in zip(dimension_ids, coordinates):
                if key == occupation_key or key in temporal_keys:
                    continue
                slice_parts.append(f"{key}={_category_label(dimension[key], category_code)}")
            if self.json_source_unit:
                slice_parts.append(
                    f"source unit={self.json_source_unit}; normalized to {self.unit}"
                )
            result.rows.append(
                NormalisedRow(
                    normalised_row_id=f"{self.parser_id}:{flat_index}",
                    source_id=self.source_id,
                    source_table=payload.get("label") or self.expected_source_table or path.name,
                    source_code=str(code),
                    source_code_system="PSOC",
                    source_code_version=version,
                    source_label=occupation_label,
                    measure=self.measure,
                    value=value,
                    unit=self.unit,
                    reference_period=period,
                    geography="Philippines",
                    population_scope=self.population_scope,
                    suppression_flag=flag,
                    notes="; ".join(slice_parts),
                )
            )
        return result

    def _normalise_occupation_code(self, raw_code: str, label: str) -> str:
        return str(raw_code)


def _ordered_category_codes(dimension_entry: dict) -> list[str]:
    """Return category codes in json-stat positional order."""
    index = dimension_entry.get("category", {}).get("index", {})
    if isinstance(index, list):
        return [str(code) for code in index]
    if isinstance(index, dict):
        return [str(code) for code, _ in sorted(index.items(), key=lambda item: item[1])]
    raise FormatValidationError("json-stat category.index must be an object or array")


def _category_label(dimension_entry: dict, code: str) -> str:
    labels = dimension_entry.get("category", {}).get("label", {})
    return str(labels.get(code, code))


@register
class PsaLfsOccupationParser(_PxWebCsvParser):
    parser_id = "psa_lfs_occupation_table"
    source_id = "psa_lfs"
    measure = "employed_persons"
    unit = "persons"
    population_scope = "employed persons 15 years and over"
    expected_source_table = "LFS employment by occupation"
    # OpenSTAT matrix 1B3FEMP4 declares UNITS="In thousands" in its PX
    # metadata. Canonical employment_count is persons, so normalization is
    # explicit and test-covered.
    json_value_factor = 1000.0
    json_source_unit = "thousand persons"

    def _normalise_occupation_code(self, raw_code: str, label: str) -> str:
        # Category keys in this matrix are positional: "0" means Total and
        # "10" means Armed Forces, so treating them as PSOC codes would turn
        # Total into Armed Forces. Resolve only exact official major-group
        # labels; do not use fuzzy/title-similarity matching.
        return PSOC_MAJOR_LABEL_TO_CODE.get(label, "")


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
    parser_version = "0.3.0"

    def validate_format(self, path: Path) -> None:
        if path.suffix.lower() == ".xlsx":
            from ..acquire import _validate_download
            _validate_download(path, "xlsx", "")
        else:
            super().validate_format(path)

    def parse(self, path: Path) -> ParseResult:
        if path.suffix.lower() != ".xlsx":
            return super().parse(path)
        from openpyxl import load_workbook
        result = ParseResult(self.parser_id, self.parser_version)
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook["Tab 2"]
            rows = list(sheet.iter_rows(max_col=21, values_only=True))
            expected = {
                (1, 2): "TABLE 2. Percent Distribution of Overseas Filipino Workers and Overseas Contract Workers by Sex, Age Group, Major Occupation, and Region with Measures of Precision: 2024",
                (2, 4): "Overseas Filipino Workers", (3, 4): "Both Sexes",
                (4, 4): "Percent Distribution (%)", (4, 5): "Standard Error\n(%)",
                (4, 6): "Coefficient of Variation (%)", (18, 3): "Percent Distrbution by Major Occupation",
                (31, 3): "Percent Distrbution by Region",
            }
            for (r, c), label in expected.items():
                if rows[r-1][c-1] != label:
                    raise FormatValidationError(f"SOF Tab 2!{r},{c}: unexpected table structure")
            labels = {name.casefold(): code for name, code in PSOC_MAJOR_LABEL_TO_CODE.items()}
            seen = set()
            for r in range(20, 30):
                label = str(rows[r-1][2]).strip()
                code = labels.get(label.casefold())
                if code is None or code in seen:
                    raise FormatValidationError(f"SOF Tab 2!C{r}: unknown or duplicate major-group label")
                seen.add(code)
                value, flag = _parse_number(rows[r-1][3])
                se, se_flag = _parse_number(rows[r-1][4])
                cv, cv_flag = _parse_number(rows[r-1][5])
                if value is not None and (not math.isfinite(value) or not 0 <= value <= 100):
                    raise FormatValidationError(f"SOF Tab 2!D{r}: impossible percentage")
                if value is not None and (se_flag or cv_flag or se < 0 or cv < 0 or not math.isfinite(se+cv)):
                    raise FormatValidationError(f"SOF Tab 2!E{r}: invalid precision")
                if value is not None and value > 0 and abs(cv - 100*se/value) > 0.05:
                    raise FormatValidationError(f"SOF Tab 2!F{r}: CV disagrees with standard error")
                notes = (
                    "Publisher's percentage divided by 100; not recomputed from counts or renormalised. "
                    "PSOC version: SOF 2024 Technical Notes p.2, limitation 5. "
                    "Blank armed-forces percentage stays missing despite zero precision cells. "
                    "https://psa.gov.ph/system/files/iesd/SOF-2024-Technical-Notes.pdf"
                )
                if value is not None and cv > 10:
                    notes += " PSA cautions that CV above 10% may be unreliable due to few observations."
                result.rows.append(NormalisedRow(
                    normalised_row_id=f"{self.parser_id}:Tab 2:D{r}", source_id=self.source_id,
                    source_table="SOF 2024 Table 2; Tab 2!C20:F29; OFWs, both sexes",
                    source_code=code, source_code_system="PSOC", source_code_version="PSOC 2012",
                    source_label=label, measure="ofw_published_share", value=None if value is None else value/100,
                    unit="share of all OFWs", reference_period="2024-04-01 to 2024-09-30",
                    geography="Philippines (households reporting overseas workers)",
                    population_scope="OFWs who departed October 2019-September 2024 and worked abroad April-September 2024; families still residing in the Philippines; both sexes",
                    suppression_flag=flag, notes=notes,
                    standard_error=None if value is None else se/100,
                    coefficient_of_variation=None if value is None else cv,
                ))
            # The source itself discloses rounding. Do not force the sum to one.
            published = [r.value for r in result.rows if r.value is not None]
            if abs(sum(published)-1) > 0.001:
                raise FormatValidationError("SOF occupation distribution does not reconcile within rounding tolerance")
        finally:
            workbook.close()
        return result
