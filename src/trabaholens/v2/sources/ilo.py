"""ILOSTAT (SDMX CSV) parsers for occupation-level Philippine labour statistics.

Why this source exists: PSA's public OpenSTAT tables publish employed persons by
the ten *major* groups only, and no table of pay, education or informality by
occupation. The ILO re-tabulates the same Philippine Labor Force Survey
microdata and publishes occupation breakdowns under CC BY 4.0.

What this source is not: it is not PSA's own published figure. The ILO's 2024
employed total (47,524 thousand) differs from PSA's (48,841 thousand), because
the two process the survey differently. The parsers therefore emit rows tagged
with the ILO as source and the transformations never combine the two.

Guards, each there because a quieter parser would let a wrong slice through:

* the file must be exactly one slice: Philippines, annual, both sexes, one
  reference year, source field naming the Labour Force Survey;
* ISCO-88 and skill-level aggregates in the same response are ignored by code
  prefix, never by guessing from a title;
* the ILO's own quality flag is kept on the row. A flagged cell is carried with
  the flag in its note and is not silently upgraded to a clean estimate.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .base import FormatValidationError, NormalisedRow, ParseResult, SourceParser, register

REQUIRED_COLUMNS = {
    "REF_AREA", "FREQ", "SEX", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS",
    "UNIT_MULT", "SOURCE", "NOTE_SOURCE",
}
EXPECTED_AREA = "PHL"
EXPECTED_FREQ = "A"
EXPECTED_SEX = "SEX_T"
EXPECTED_YEAR = "2024"
SOURCE_NAME_FRAGMENT = "Labour Force Survey"
CODE_SYSTEM = "ISCO-08"
GEOGRAPHY = "Philippines"
REFERENCE_PERIOD = "2024 Annual"

#: ILOSTAT observation-status flags. Only the meanings the project relies on are
#: spelled out; any other flag is carried through verbatim in the note.
STATUS_MEANING = {"U": "flagged unreliable by the ILO", "B": "break in series", "E": "ILO estimate", "I": "imputed"}


def _number(text: str) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class _IloSdmxParser(SourceParser):
    parser_version = "0.1.0"
    source_code_system = CODE_SYSTEM
    expected_source_table = ""
    population_scope = ""
    #: Name of the column holding the occupation code, and its prefix.
    occupation_column = "OCU"
    occupation_prefix = "OCU_ISCO08_"
    #: Number of digits of the ISCO code this source publishes.
    code_digits = 1

    def _read(self, path: Path) -> list[dict[str, str]]:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def validate_format(self, path: Path) -> None:
        if path.suffix.lower() != ".csv":
            raise FormatValidationError(f"{path.name}: expected an ILOSTAT SDMX .csv")
        rows = self._read(path)
        if not rows:
            raise FormatValidationError(f"{path.name}: no rows")
        missing = (REQUIRED_COLUMNS | {self.occupation_column}) - set(rows[0])
        if missing:
            raise FormatValidationError(f"{path.name}: missing columns {sorted(missing)}")
        for field, expected in (("REF_AREA", EXPECTED_AREA), ("FREQ", EXPECTED_FREQ),
                                ("SEX", EXPECTED_SEX), ("TIME_PERIOD", EXPECTED_YEAR)):
            found = {r[field] for r in rows}
            if found != {expected}:
                raise FormatValidationError(
                    f"{path.name}: {field} must be exactly {expected!r}, found {sorted(found)}. "
                    "The pinned query selects one slice; a wider response is refused."
                )
        if not all(SOURCE_NAME_FRAGMENT in r["SOURCE"] for r in rows):
            raise FormatValidationError(
                f"{path.name}: SOURCE is not the Labour Force Survey for every row: "
                f"{sorted({r['SOURCE'] for r in rows})}"
            )

    def _code(self, raw: str) -> str:
        if not raw.startswith(self.occupation_prefix):
            return ""
        code = raw[len(self.occupation_prefix):]
        if code == "TOTAL" or not code.isdigit() or len(code) != self.code_digits:
            return ""
        return code

    def _note(self, row: dict[str, str]) -> str:
        flag = (row.get("OBS_STATUS") or "").strip()
        base = "Source: ILOSTAT, from the Philippine Labor Force Survey as processed by the ILO."
        if flag:
            return f"{base} ILO status flag {flag!r}: {STATUS_MEANING.get(flag, 'see ILOSTAT metadata')}."
        return base


@register
class IloEmploymentIsco2Parser(_IloSdmxParser):
    parser_id = "ilo_employment_isco2"
    source_id = "ilostat_employment_isco2"
    occupation_column = "OC2"
    occupation_prefix = "OC2_ISCO08_"
    code_digits = 2
    measure = "ilo_employed_persons_isco2"
    expected_source_table = "ILOSTAT DF_EMP_TEMP_SEX_OC2_NB: Employment by sex and occupation, ISCO level 2"
    population_scope = "employed persons 15 years and over (ILO-processed LFS)"

    def parse(self, path: Path) -> ParseResult:
        result = ParseResult(self.parser_id, self.parser_version)
        for index, row in enumerate(self._read(path)):
            code = self._code(row["OC2"])
            if not code:
                continue
            value = _number(row["OBS_VALUE"])
            multiplier = 10 ** int(row["UNIT_MULT"] or 0)
            result.rows.append(NormalisedRow(
                normalised_row_id=f"{self.parser_id}:{code}",
                source_id=self.source_id, source_table=self.expected_source_table,
                source_code=code, source_code_system=CODE_SYSTEM, source_code_version=CODE_SYSTEM,
                source_label=row["OC2"], measure=self.measure,
                value=None if value is None else value * multiplier, unit="persons",
                reference_period=REFERENCE_PERIOD, geography=GEOGRAPHY,
                population_scope=self.population_scope, notes=self._note(row),
            ))
        return result


class _IloEarningsParser(_IloSdmxParser):
    unit = "PHP per month"
    population_scope = "employees (wage and salary workers) only; ILO-processed LFS"

    def parse(self, path: Path) -> ParseResult:
        result = ParseResult(self.parser_id, self.parser_version)
        for row in self._read(path):
            code = self._code(row["OCU"])
            if not code:
                continue
            if row.get("UNIT_MEASURE_TYPE", "LC") and row.get("UNIT_MEASURE") not in ("LC", ""):
                raise FormatValidationError(f"{self.parser_id}: earnings are not in local currency")
            if "PHP" not in (row.get("NOTE_INDICATOR") or ""):
                raise FormatValidationError(f"{self.parser_id}: currency note does not name PHP")
            value = _number(row["OBS_VALUE"])
            result.rows.append(NormalisedRow(
                normalised_row_id=f"{self.parser_id}:{code}",
                source_id=self.source_id, source_table=self.expected_source_table,
                source_code=code, source_code_system=CODE_SYSTEM, source_code_version=CODE_SYSTEM,
                source_label=row["OCU"], measure=self.measure,
                value=None if value is None else value * 10 ** int(row["UNIT_MULT"] or 0),
                unit=self.unit, reference_period=REFERENCE_PERIOD, geography=GEOGRAPHY,
                population_scope=self.population_scope, notes=self._note(row),
            ))
        return result


@register
class IloEarningsMeanParser(_IloEarningsParser):
    parser_id = "ilo_earnings_mean"
    source_id = "ilostat_earnings_mean"
    measure = "ilo_mean_monthly_earnings_employees"
    expected_source_table = "ILOSTAT DF_EAR_EMTA_SEX_OCU_NB: Average monthly earnings of employees by sex and occupation"


@register
class IloEarningsMedianParser(_IloEarningsParser):
    parser_id = "ilo_earnings_median"
    source_id = "ilostat_earnings_median"
    measure = "ilo_median_monthly_earnings_employees"
    expected_source_table = "ILOSTAT DF_EAR_EMTM_SEX_OCU_NB: Median monthly earnings of employees by sex and occupation"


@register
class IloEducationParser(_IloSdmxParser):
    parser_id = "ilo_education_attainment"
    source_id = "ilostat_education_attainment"
    measure = "ilo_advanced_education_share"
    expected_source_table = "ILOSTAT DF_EMP_TEMP_SEX_OCU_EDU_NB: Employment by sex, occupation and education"
    population_scope = "employed persons 15 years and over (ILO-processed LFS)"
    LEVELS = (("LTB", "less than basic"), ("BAS", "basic"), ("INT", "intermediate"), ("ADV", "advanced"))

    def validate_format(self, path: Path) -> None:
        super().validate_format(path)
        if "EDU" not in self._read(path)[0]:
            raise FormatValidationError(f"{path.name}: missing EDU column")

    def parse(self, path: Path) -> ParseResult:
        result = ParseResult(self.parser_id, self.parser_version)
        cells: dict[str, dict[str, dict[str, str]]] = {}
        for row in self._read(path):
            code = self._code(row["OCU"])
            if code and row["EDU"].startswith("EDU_AGGREGATE_"):
                cells.setdefault(code, {})[row["EDU"].removeprefix("EDU_AGGREGATE_")] = row
        for code, by_level in sorted(cells.items()):
            total_row = by_level.get("TOTAL")
            counts = {level: _number(by_level[level]["OBS_VALUE"]) if level in by_level else None
                      for level, _ in self.LEVELS}
            total = _number(total_row["OBS_VALUE"]) if total_row else None
            flags = {r.get("OBS_STATUS", "") for r in by_level.values()} - {""}
            share, note = None, ""
            if total and total > 0 and all(v is not None for v in counts.values()):
                parts = sum(counts.values())
                # The four aggregates must add to the published total. If they do
                # not, the shares would be built on a broken partition.
                if abs(parts - total) / total <= 0.001:
                    share = counts["ADV"] / total
                    pct = ", ".join(f"{label} {counts[level] / total * 100:.1f}%" for level, label in self.LEVELS)
                    note = (f"Calculated as advanced / total from published counts "
                            f"({counts['ADV']:.3f} of {total:.3f} thousand). Education profile: {pct}. "
                            "Advanced = tertiary-level attainment (ISCED 2011 levels 5-8).")
                else:
                    note = "Education aggregates do not add to the published total; share withheld."
            elif total is not None:
                note = "One or more education levels is missing in the source; share withheld."
            if flags:
                note += f" ILO status flag(s) {sorted(flags)} on component cells."
            result.rows.append(NormalisedRow(
                normalised_row_id=f"{self.parser_id}:{code}",
                source_id=self.source_id, source_table=self.expected_source_table,
                source_code=code, source_code_system=CODE_SYSTEM, source_code_version=CODE_SYSTEM,
                source_label=f"OCU_ISCO08_{code}", measure=self.measure,
                value=share, unit="share of employed persons",
                reference_period=REFERENCE_PERIOD, geography=GEOGRAPHY,
                population_scope=self.population_scope,
                notes=(note + " Source: ILOSTAT, from the Philippine Labor Force Survey as processed by the ILO.").strip(),
            ))
        return result
