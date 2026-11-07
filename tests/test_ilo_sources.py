"""ILOSTAT-sourced layers: the slice guards, the classification link, the arithmetic."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from trabaholens.v2.paths import CLASSIFICATIONS_CSV, CROSSWALK_CSV, RAW_DIR
from trabaholens.v2.sources import ilo as _ilo  # noqa: F401  (registers parsers)
from trabaholens.v2.sources.base import FormatValidationError, get_parser

FILES = {
    "ilo_employment_isco2": "ilostat_employment_isco2/ilo_employment_isco2_2024.csv",
    "ilo_earnings_mean": "ilostat_earnings_mean/ilo_earnings_mean_2024.csv",
    "ilo_earnings_median": "ilostat_earnings_median/ilo_earnings_median_2024.csv",
    "ilo_education_attainment": "ilostat_education_attainment/ilo_education_2024.csv",
    "ilo_status_employment": "ilostat_status_employment/ilo_status_employment_2024.csv",
}

pytestmark = pytest.mark.skipif(
    not all((RAW_DIR / f).exists() for f in FILES.values()),
    reason="ILOSTAT raw files not fetched (run `make fetch-data`)",
)


def _rows(parser_id):
    return get_parser(parser_id).run(RAW_DIR / FILES[parser_id]).rows


def _classification_codes(level):
    with open(CLASSIFICATIONS_CSV, encoding="utf-8", newline="") as handle:
        return {r["psoc_code"] for r in csv.DictReader(handle) if r["level"] == level}


def test_sub_major_code_set_matches_psoc_exactly():
    # The ISCO-08 level-2 code list in the ILO file must equal PSOC's 43
    # sub-major groups. This is the evidence behind the structural link.
    assert {r.source_code for r in _rows("ilo_employment_isco2")} == _classification_codes("psoc_sub_major_group")


def test_major_code_set_matches_psoc_exactly():
    for parser_id in ("ilo_earnings_mean", "ilo_earnings_median", "ilo_education_attainment", "ilo_status_employment"):
        assert {r.source_code for r in _rows(parser_id)} == _classification_codes("psoc_major_group")


def test_earnings_are_positive_pesos_and_median_is_not_above_a_plausible_mean():
    means = {r.source_code: r.value for r in _rows("ilo_earnings_mean")}
    medians = {r.source_code: r.value for r in _rows("ilo_earnings_median")}
    assert all(v and v > 0 for v in means.values())
    assert all(r.unit == "PHP per month" for r in _rows("ilo_earnings_mean"))
    # For right-skewed pay a median above twice the mean would signal a mix-up.
    assert all(medians[c] <= 2 * means[c] for c in means)


def test_education_shares_are_proportions_and_note_the_arithmetic():
    rows = _rows("ilo_education_attainment")
    assert rows and all(r.value is not None and 0 <= r.value <= 1 for r in rows)
    assert all("Calculated as advanced / total" in r.notes for r in rows)


def test_employment_is_converted_from_thousands_to_persons():
    total = sum(r.value for r in _rows("ilo_employment_isco2"))
    # About 47.5 million employed in 2024, in persons not thousands.
    assert 40_000_000 < total < 55_000_000


@pytest.mark.parametrize("field,bad", [("TIME_PERIOD", "2023"), ("REF_AREA", "IDN"), ("SEX", "SEX_F"), ("FREQ", "Q")])
def test_a_wrong_slice_is_refused(tmp_path: Path, field, bad):
    source = (RAW_DIR / FILES["ilo_earnings_mean"]).read_text(encoding="utf-8").splitlines()
    header = source[0].split(",")
    index = header.index(field)
    mutated = [source[0]] + [",".join(c if i != index else bad for i, c in enumerate(line.split(","))) for line in source[1:]]
    path = tmp_path / "bad.csv"
    path.write_text("\n".join(mutated), encoding="utf-8")
    with pytest.raises(FormatValidationError):
        get_parser("ilo_earnings_mean").run(path)


def test_education_with_broken_partition_withholds_the_share(tmp_path: Path):
    lines = (RAW_DIR / FILES["ilo_education_attainment"]).read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    value_i, edu_i, ocu_i = header.index("OBS_VALUE"), header.index("EDU"), header.index("OCU")
    out = [lines[0]]
    for line in lines[1:]:
        cells = line.split(",")
        if cells[ocu_i] == "OCU_ISCO08_1" and cells[edu_i] == "EDU_AGGREGATE_ADV":
            cells[value_i] = "1.0"  # no longer adds up to the published total
        out.append(",".join(cells))
    path = tmp_path / "broken.csv"
    path.write_text("\n".join(out), encoding="utf-8")
    managers = [r for r in get_parser("ilo_education_attainment").run(path).rows if r.source_code == "1"][0]
    assert managers.value is None and "do not add to the published total" in managers.notes


def test_structural_crosswalk_rows_are_verified_only_for_codes_in_the_ilo_files():
    with open(CROSSWALK_CSV, encoding="utf-8", newline="") as handle:
        links = [r for r in csv.DictReader(handle) if r["crosswalk_id"].startswith("XW-ISCO-")]
    ilo_codes = {r.source_code for r in _rows("ilo_employment_isco2")} | {r.source_code for r in _rows("ilo_earnings_mean")}
    for link in links:
        if link["review_status"] == "source_verified":
            assert link["psoc_code"] in ilo_codes
            assert link["mapping_basis"] == "structural_derivation"


def test_own_account_family_share_is_a_proportion_and_never_called_informal():
    rows = _rows("ilo_status_employment")
    assert rows and all(r.value is not None and 0 <= r.value <= 1 for r in rows)
    by_code = {r.source_code: r.value for r in rows}
    # Farming is overwhelmingly own-account; managers mostly employees.
    assert by_code["6"] > 0.8 and by_code["1"] < 0.4
    assert all("Not informal employment" in r.notes for r in rows)
