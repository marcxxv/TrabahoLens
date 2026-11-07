"""Source-native OWS reference table, deliberately NOT a PSOC crosswalk.

The source labels its codes PSOC/OWS but does not declare the PSOC version.
These records retain the publisher's occupation x industry slices. They must
never join domestic employment, be averaged into national occupational wages,
or be represented as canonical PSOC-2022 observations.
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from openpyxl import load_workbook

from .acquisition_state import verify
from .paths import REPO_ROOT
from .sources.base import FormatValidationError

TABLE_PATH = REPO_ROOT / "data/reference/ows_wage_benchmarks.csv"
SOURCE_HASH = "78823a5d60b625398ce97cebfde9e5dd0df7d412c6862d2e1b4bd245ea91eef2"
COLUMNS = [
    "observation_id", "source_code", "source_occupation", "industry_code", "industry",
    "value", "unit", "reference_period", "population_scope", "availability",
    "derivation_class", "source_authority", "confidence_grade", "standard_error",
    "coefficient_of_variation", "uncertainty_lower", "uncertainty_upper", "confidence_level",
    "source_id", "source_url", "source_file_hash", "retrieved_at", "source_table",
    "source_granularity", "display_granularity", "classification_reconciliation", "notes",
]


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def parse_workbook(path: Path) -> list[dict]:
    """Read only the published A:H table; hidden calculation columns are ignored."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    output = []
    industry_code = industry = ""
    try:
        sheet = workbook["Table 1"]
        rows = list(sheet.iter_rows(max_col=8, values_only=True))
        if "Philippines:  August 2024" not in str(rows[0][0]) or rows[3][:4] != (
            "PSIC/PSOC", None, "Industry/Occupation", "Wage Rate Estimate"
        ) or rows[3][6] != "90% Confidence Interval":
            raise FormatValidationError("OWS 2024 Table 1 headers changed")
        for row_number, row in enumerate(rows[6:], 7):
            code = str(row[0] or "").strip()
            if re.fullmatch(r"[A-S](?:\d{2,4})?(?:/[A-S]\d{2,4})?(?:/[A-S]\d{2,4})?(?: only)?", code):
                if row[3] is not None or not row[2]:
                    raise FormatValidationError(f"OWS row {row_number}: malformed industry heading")
                industry_code, industry = code, " ".join(str(row[2]).split())
                continue
            if not code.isdigit():
                # Repeated page headers and footnotes do not reset the explicit
                # table section. This is hierarchy, not forward-filled metrics.
                if number(row[3]) is not None and row_number > 6:
                    raise FormatValidationError(f"OWS row {row_number}: unrecognised value row")
                continue
            if not industry_code or not row[2]:
                raise FormatValidationError(f"OWS row {row_number}: missing industry/occupation")
            value, se, cv, lower, upper = map(number, row[3:8])
            reasons = []
            if value is None or value < 0:
                reasons.append("Missing, non-finite or negative wage estimate")
            precision = [se, cv, lower, upper]
            if any(x is None and raw not in (None, ".", "", " ") for x, raw in zip(precision, row[4:8])):
                reasons.append("Unrecognised or non-finite precision field")
            if value is not None and any(x is not None for x in precision):
                if any(x is None for x in precision):
                    reasons.append("Incomplete precision fields")
                elif se < 0 or cv < 0 or lower > value or upper < value:
                    reasons.append("Publisher's confidence interval/precision is inconsistent with its estimate")
                elif abs((lower+upper)/2-value) > 1.0:
                    reasons.append("Publisher's interval is not centred on its estimate; possible copied bounds")
                elif value > 0 and abs(cv-100*se/value) > 0.05:
                    reasons.append("Publisher's coefficient of variation disagrees with its standard error")
            if reasons:
                availability, grade = "blocked_source_inconsistency", "D"
            elif cv is not None and cv > 10:
                availability, grade = "published", "D"
            elif se is None:
                availability, grade = "published", "B"
            else:
                availability, grade = "published", "A"
            notes = [
                "Wage rate includes basic pay and regular/guaranteed cash allowances; not basic pay alone.",
                "Industry-specific job position, not the earnings of all workers in this occupation.",
                "Source-native reference only: occupational code version unconfirmed; no canonical PSOC mapping or employment join.",
            ]
            if cv is not None and cv > 10:
                notes.append("PSA cautions: CV above 10%, less reliable or precise.")
            if se is None:
                notes.append("PSA displays '.' for sampling precision; no interval inferred.")
            if row[1] == "a":
                notes.append("Source footnote a: average wage rate across selected occupations in selected industries; benchmark aggregate, not a detailed occupation.")
            if row[1] == "b":
                notes.append("Source footnote b: OWS-specific code.")
            notes.extend(reasons)
            output.append(dict(
                observation_id=f"OWS2024:Table1:row{row_number}", source_code=code,
                source_occupation=" ".join(str(row[2]).split()), industry_code=industry_code, industry=industry,
                value=value if not reasons else None, unit="PHP per month", reference_period="2024-08",
                population_scope="Time-rated full-time workers in covered formal establishments employing 10 or more workers; specified industry and job position; Philippines",
                availability=availability, derivation_class="estimated",
                source_authority="ph_official_statistical_authority", confidence_grade=grade,
                standard_error=se if not reasons else None, coefficient_of_variation=cv if not reasons else None,
                uncertainty_lower=lower if not reasons else None, uncertainty_upper=upper if not reasons else None,
                confidence_level=0.9 if lower is not None and not reasons else None,
                source_table=f"2024 OWS SE CV; Table 1!A{row_number}:H{row_number}",
                source_granularity="source_job_position_in_industry", display_granularity="source_job_position_in_industry",
                classification_reconciliation="unmapped_source_native", notes=" ".join(notes),
            ))
    finally:
        workbook.close()
    if not output:
        raise FormatValidationError("OWS table contains no occupation observations")
    return output


def build() -> list[dict]:
    acquisition = verify("psa_ows")
    rows = []
    if acquisition.acquired:
        if acquisition.sha256 != SOURCE_HASH:
            raise FormatValidationError("OWS workbook changed; review before publishing")
        rows = parse_workbook(acquisition.path)
        for row in rows:
            row.update(source_id="psa_ows", source_url=acquisition.url,
                       source_file_hash=acquisition.sha256, retrieved_at=acquisition.retrieved_at)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def load() -> list[dict]:
    if not TABLE_PATH.exists():
        return []
    with TABLE_PATH.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ("value", "standard_error", "coefficient_of_variation", "uncertainty_lower", "uncertainty_upper", "confidence_level"):
            row[key] = float(row[key]) if row[key] else None
    return rows


def validate(rows: list[dict]) -> list[str]:
    errors = []
    seen = set()
    for row in rows:
        oid = row.get("observation_id")
        if oid in seen:
            errors.append(f"Duplicate OWS record {oid}")
        seen.add(oid)
        for key in COLUMNS:
            if key not in {"value", "standard_error", "coefficient_of_variation", "uncertainty_lower", "uncertainty_upper", "confidence_level"} and not row.get(key):
                errors.append(f"{oid}: missing {key}")
        value = row.get("value")
        for key in ("standard_error", "coefficient_of_variation", "uncertainty_lower", "uncertainty_upper", "confidence_level"):
            if row.get(key) is not None and number(row[key]) is None:
                errors.append(f"{oid}: non-finite {key}")
        if row.get("source_file_hash") != SOURCE_HASH or row.get("source_id") != "psa_ows":
            errors.append(f"{oid}: source does not match reviewed workbook")
        if row.get("availability") not in {"published", "blocked_source_inconsistency"}:
            errors.append(f"{oid}: invalid availability")
        if row.get("availability") == "published":
            if number(value) is None or value < 0:
                errors.append(f"{oid}: invalid published wage")
                continue
            lo, hi = row.get("uncertainty_lower"), row.get("uncertainty_upper")
            if (lo is None) != (hi is None) or (lo is not None and not lo <= value <= hi):
                errors.append(f"{oid}: invalid confidence interval")
            cv = row.get("coefficient_of_variation")
            if cv is not None and cv > 10 and row.get("confidence_grade") != "D":
                errors.append(f"{oid}: high CV without caution grade")
        elif value is not None:
            errors.append(f"{oid}: blocked record carries a value")
        if row.get("classification_reconciliation") != "unmapped_source_native":
            errors.append(f"{oid}: unsupported PSOC reconciliation")
    return errors


def validate_against_source(rows: list[dict]) -> list[str]:
    """Replay the retained source; a plausible edit to the CSV cannot pass."""
    acquisition = verify("psa_ows")
    if not acquisition.acquired:
        return ["OWS references exist without a verified source snapshot"] if rows else []
    if acquisition.sha256 != SOURCE_HASH:
        return ["OWS source hash differs from the reviewed workbook"]
    expected = parse_workbook(acquisition.path)
    for row in expected:
        row.update(source_id="psa_ows", source_url=acquisition.url,
                   source_file_hash=acquisition.sha256, retrieved_at=acquisition.retrieved_at)
    return [] if rows == expected else ["OWS reference table differs from a fresh source extraction"]
