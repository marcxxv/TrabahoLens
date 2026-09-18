"""Regression tests for the final adversarial-review findings."""

from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import pytest

from trabaholens.v2.acquisition_state import AcquisitionRecord
from trabaholens.v2.build_canonical import collapse_outcomes_by_code
from trabaholens.v2.sources.base import NormalisedRow
from trabaholens.v2.sources.psa import PsaLfsOccupationParser
from trabaholens.v2.transform import TransformOutcome, transform_rows


CANONICAL_VERSION = "PSOC 2012 (2022 Updates)"
MAJOR_CODES = {str(value) for value in range(10)}
ACQUIRED = AcquisitionRecord(source_id="fixture", acquired=True, reason="fixture")


def test_pxweb_jsonstat_decodes_every_multidimensional_cell(tmp_path):
    path = tmp_path / "lfs.json"
    path.write_text(json.dumps({
        "class": "dataset",
        "label": "LFS by occupation, PSOC 2012 2022 Updates",
        "id": ["occupation", "time"],
        "size": [2, 2],
        "dimension": {
            "occupation": {"category": {
                "index": {"1": 0, "2": 1},
                "label": {"1": "Managers", "2": "Professionals"},
            }},
            "time": {"category": {
                "index": {"2023": 0, "2024": 1},
                "label": {"2023": "2023", "2024": "2024"},
            }},
        },
        "value": [10, 11, 20, 21],
    }), encoding="utf-8")

    rows = PsaLfsOccupationParser().run(path).rows
    assert [(row.source_code, row.reference_period, row.value) for row in rows] == [
        ("1", "2023", 10000), ("1", "2024", 11000),
        ("2", "2023", 20000), ("2", "2024", 21000),
    ]


def test_pxweb_jsonstat1_wrapper_and_positional_major_codes(tmp_path):
    path = tmp_path / "lfs.json"
    path.write_text(json.dumps({"dataset": {
        "label": "LFS major occupation (2012 PSOC Code)",
        "id": ["Year", "Month", "Major Occupation Group (2012 PSOC Code)"],
        "size": [1, 1, 3],
        "dimension": {
            "Year": {"category": {"index": {"8": 0}, "label": {"8": "2024"}}},
            "Month": {"category": {"index": {"12": 0}, "label": {"12": "Annual"}}},
            "Major Occupation Group (2012 PSOC Code)": {"category": {
                "index": {"0": 0, "1": 1, "10": 2},
                "label": {"0": "Total", "1": "Managers", "10": "Armed Forces Occupations"},
            }},
        },
        "value": [100, 12.5, 0.5],
    }}), encoding="utf-8")

    rows = PsaLfsOccupationParser().run(path).rows
    assert [(row.source_code, row.reference_period, row.value) for row in rows] == [
        ("1", "2024 Annual", 12500),
        ("0", "2024 Annual", 500),
    ]
    assert all("normalized to persons" in row.notes for row in rows)


def test_csv_metadata_is_not_carried_forward(tmp_path):
    path = tmp_path / "lfs.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "occupation_code", "occupation_label", "value",
            "reference_period", "classification_version",
        ])
        writer.writeheader()
        writer.writerow({"occupation_code": "1", "occupation_label": "Managers", "value": 10,
                         "reference_period": "2024", "classification_version": CANONICAL_VERSION})
        writer.writerow({"occupation_code": "2", "occupation_label": "Professionals", "value": 20,
                         "reference_period": "", "classification_version": ""})

    rows = PsaLfsOccupationParser().run(path).rows
    assert rows[1].reference_period == ""
    assert rows[1].source_code_version == "unknown"


def _row(code: str, value: float, period: str, *, version: str = CANONICAL_VERSION):
    return NormalisedRow(
        normalised_row_id=f"fixture:{code}:{period}", source_id="psa_sof",
        source_table="SOF fixture", source_code=code, source_code_system="PSOC",
        source_code_version=version, source_label=code,
        measure="ofw_count_by_major_occupation", value=value, unit="persons",
        reference_period=period, geography="Philippines", population_scope="OFWs",
    )


def test_psoc_versions_require_exact_match():
    row = NormalisedRow(
        normalised_row_id="fixture:1", source_id="psa_lfs", source_table="LFS fixture",
        source_code="1", source_code_system="PSOC", source_code_version="PSOC 2012",
        source_label="Managers", measure="employed_persons", value=10, unit="persons",
        reference_period="2024", geography="Philippines", population_scope="employed persons",
    )
    outcome = transform_rows(
        "employment_count", [row], ACQUIRED, MAJOR_CODES, CANONICAL_VERSION
    )[0]
    assert outcome.value is None
    assert "not reconcilable" in outcome.reason


def test_psoc_version_change_requires_and_uses_explicit_correspondence():
    row = NormalisedRow(
        normalised_row_id="fixture:1", source_id="psa_lfs", source_table="LFS fixture",
        source_code="1", source_code_system="PSOC", source_code_version="PSOC 2012",
        source_label="Managers", measure="employed_persons", value=10, unit="persons",
        reference_period="2024", geography="Philippines", population_scope="employed persons",
    )
    correspondence = [{
        "correspondence_id": "PSOCVER-1", "source_version": "PSOC 2012",
        "target_version": CANONICAL_VERSION, "source_code": "1", "target_code": "1",
        "mapping_basis": "official_update_structure", "review_status": "source_verified",
    }]
    outcome = transform_rows(
        "employment_count", [row], ACQUIRED, MAJOR_CODES, CANONICAL_VERSION,
        version_correspondence_rows=correspondence,
    )[0]
    assert outcome.value == 10
    assert outcome.crosswalk_id == "PSOCVER-1"


def test_ofw_denominators_are_period_specific_and_require_complete_distribution():
    rows = []
    for period, multiplier in (("2023", 1), ("2024", 2)):
        rows.extend(_row(code, (int(code) + 1) * multiplier, period) for code in sorted(MAJOR_CODES))
    outcomes = transform_rows(
        "ofw_distribution_share", rows, ACQUIRED, MAJOR_CODES, CANONICAL_VERSION
    )
    for period in ("2023", "2024"):
        assert sum(o.value for o in outcomes if o.reference_period == period) == pytest.approx(1.0)

    incomplete = transform_rows(
        "ofw_distribution_share", rows[:-1], ACQUIRED, MAJOR_CODES, CANONICAL_VERSION
    )
    assert all(o.value is None for o in incomplete if o.reference_period == "2024")


def test_duplicate_canonical_candidates_block_instead_of_overwrite():
    outcomes = [
        TransformOutcome("employment_count", "1", 10, "ok", normalised_row_id="row-1"),
        TransformOutcome("employment_count", "1", 20, "ok", normalised_row_id="row-2"),
    ]
    collapsed = collapse_outcomes_by_code(outcomes, "employment_count")
    assert collapsed["1"].value is None
    assert "refusing silent overwrite" in collapsed["1"].reason


def test_onet_value_requires_one_human_reviewed_crosswalk():
    row = NormalisedRow(
        normalised_row_id="onet:1", source_id="onet", source_table="Job Zones.txt",
        source_code="11-1011.00", source_code_system="O*NET-SOC", source_code_version="31.0",
        source_label="Chief Executives", measure="job_zone", value=5, unit="ordinal zone",
        reference_period="O*NET 31.0", geography="United States", population_scope="O*NET occupations",
    )
    accepted = [{
        "crosswalk_id": "XW-1", "psoc_code": "1", "source_code": "11-1011.00",
        "source_classification": "O*NET-SOC", "match_quality": "high",
        "mapping_basis": "published_correspondence", "review_status": "human_reviewed",
    }]
    outcome = transform_rows(
        "onet_job_zone", [row], ACQUIRED, MAJOR_CODES, CANONICAL_VERSION,
        crosswalk_rows=accepted,
    )[0]
    assert outcome.psoc_code == "1"
    assert outcome.value == 5
    assert outcome.crosswalk_id == "XW-1"
    assert outcome.source_table == "Job Zones.txt"


def test_production_classification_builder_uses_verified_psoc_import(monkeypatch, tmp_path):
    from trabaholens.v2 import build_canonical

    source_path = tmp_path / "psoc.csv"
    source_path.write_text("code,title\n1,Managers\n", encoding="utf-8")
    imported = [{
        "psoc_code": "1", "psoc_version": CANONICAL_VERSION,
        "level": "psoc_major_group", "title": "Managers",
        "parent_psoc_code": "", "psoc_major": "1", "psoc_major_label": "Managers",
        "isco08_code": "1", "definition": "",
        "verification_status": "verified_against_source", "notes": "",
    }]
    report = SimpleNamespace(
        complete=True, problems=[], version=CANONICAL_VERSION, rows=imported
    )
    parser = SimpleNamespace(import_classification=lambda path: report)
    monkeypatch.setattr(build_canonical, "verify_all", lambda ids: {
        "psa_psoc": AcquisitionRecord(
            "psa_psoc", True, "verified", source_path, "a" * 64,
            "2026-01-01T00:00:00Z", "https://psa.example/psoc.csv",
        )
    })
    monkeypatch.setattr(build_canonical, "get_parser", lambda parser_id: parser)
    monkeypatch.setattr(build_canonical, "load_registry", lambda: {"sources": [{
        "source_id": "psa_psoc", "organization": "PSA", "dataset": "PSOC",
        "authoritative_url": "https://psa.example/psoc",
    }]})

    rows = build_canonical.build_classifications()
    assert rows == [{
        **imported[0], "source_organization": "PSA", "source_dataset": "PSOC",
        "source_url": "https://psa.example/psoc.csv",
        "notes": f"Imported from SHA-256 {'a' * 64}.",
    }]


def test_release_metric_state_is_derived_per_metric_not_per_row():
    from trabaholens.v2.build_release import derive_publication_state

    state = derive_publication_state([
        {"metric_id": "employment_count", "availability": "published", "metric_value": "10"},
        {"metric_id": "employment_count", "availability": "blocked_pending_source", "metric_value": ""},
        {"metric_id": "ofw_distribution_share", "availability": "blocked_pending_source", "metric_value": ""},
    ])
    assert "employment_count" in state["metrics_with_published_values"]
    assert "employment_count" not in state["metrics_blocked_pending_source"]
    assert "ofw_distribution_share" in state["metrics_blocked_pending_source"]
