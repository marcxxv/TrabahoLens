"""Regression tests against retained, unmodified publisher bytes, not custom plugs."""
from collections import Counter
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from trabaholens.v2.paths import REPO_ROOT
from trabaholens.v2.sources.base import FormatValidationError
from trabaholens.v2.sources.psa import PsaSofOccupationParser
from trabaholens.v2.sources.psoc_importer import PsocVolumeParser, WORKBOOK_STRUCTURE
from trabaholens.v2 import wage_benchmarks as wages

PSOC = REPO_ROOT / "data/raw/psa_psoc/psoc_2022_updates.xlsx"
SOF = REPO_ROOT / "data/raw/psa_sof/sof_2024_table_2_major_occupation.xlsx"
OWS = REPO_ROOT / "data/raw/psa_ows/ows_2024_wage_estimates_precision.xlsx"


def test_official_workbook_explicit_codes_not_webpage_count():
    report = PsocVolumeParser().import_classification(PSOC)
    assert report.complete and not report.problems
    assert report.counts == WORKBOOK_STRUCTURE
    assert len(report.rows) == len({r['psoc_code'] for r in report.rows})
    assert report.warnings and '456' in report.warnings[0]
    rows = {r['psoc_code']: r for r in report.rows}
    assert rows['0110']['parent_psoc_code'] == '011'
    assert rows['2124']['title'] == 'DATA SCIENTIST'
    assert all(not r['isco08_code'] for r in report.rows)


def test_sof_selects_ofws_both_sexes_not_ocws_or_domestic_workers():
    rows = PsaSofOccupationParser().run(SOF).rows
    assert len(rows) == 10
    by_code = {r.source_code: r for r in rows}
    assert by_code['0'].value is None
    assert by_code['0'].standard_error is None
    assert by_code['9'].value == pytest.approx(43.5883 / 100)
    assert by_code['1'].standard_error == pytest.approx(.364427 / 100)
    assert by_code['1'].coefficient_of_variation > 10
    # Keep publisher rounding, not artificially normalised shares.
    assert sum(r.value for r in rows if r.value is not None) == pytest.approx(1.00000017)
    assert {r.source_code_version for r in rows} == {'PSOC 2012'}
    assert all('families still residing' in r.population_scope for r in rows)


def test_sof_rejects_changed_slice(tmp_path):
    workbook = load_workbook(SOF)
    workbook['Tab 2']['D2'] = 'Overseas Contract Workers'
    path = tmp_path / 'wrong.xlsx'
    workbook.save(path)
    workbook.close()
    with pytest.raises(FormatValidationError):
        PsaSofOccupationParser().run(path)


def test_ows_keeps_source_industry_slices_and_quarantines_copied_intervals():
    rows = wages.parse_workbook(OWS)
    assert Counter(r['availability'] for r in rows) == {'published': 684, 'blocked_source_inconsistency': 9}
    assert len({r['observation_id'] for r in rows}) == 693
    blocked = [r for r in rows if r['availability'] != 'published']
    assert {int(r['observation_id'].split('row')[1]) for r in blocked} == set(range(588, 597))
    assert all(r['value'] is None and r['uncertainty_lower'] is None for r in blocked)
    assert all(r['classification_reconciliation'] == 'unmapped_source_native' for r in rows)
    assert any(r['industry_code'] == 'F' for r in rows)
    assert any(r['industry_code'] == 'A01/A02' for r in rows)
    assert all(r['confidence_grade'] == 'D' for r in rows if r['coefficient_of_variation'] is not None and r['coefficient_of_variation'] > 10)


def test_ows_release_replays_source_and_detects_plausible_tampering():
    rows = wages.load()
    assert not wages.validate(rows)
    assert not wages.validate_against_source(rows)
    changed = deepcopy(rows)
    changed[0]['value'] += 1
    assert wages.validate_against_source(changed)
    changed[0]['standard_error'] = float('nan')
    assert wages.validate(changed)
