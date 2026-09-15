"""End-to-end proof that a populated source reaches a published value.

The rest of the suite proves validators reject bad input. On an empty
production dataset that is close to vacuous: everything passes because nothing
is there. These tests drive the whole path with synthetic sources and assert
that a value actually comes out the other end — and that each specific
corruption stops it.

Path exercised:
  retrieval manifest -> hash verification -> format validation -> parser
  -> normalised rows -> classification reconciliation -> transformation
  -> canonical observation -> release validation -> site payload.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures.build import (
    LFS_ROWS,
    build_populated_sources,
    write_onet_zip,
    write_psa_csv,
)
from trabaholens.v2 import acquisition_state, transform
from trabaholens.v2.sources import get_parser
from trabaholens.v2.sources import onet as _onet  # noqa: F401  (registers)
from trabaholens.v2.sources import psa as _psa  # noqa: F401  (registers)

CANONICAL_CODES = {str(d) for d in range(10)} | {"11", "12", "21", "25", "91"}
CANONICAL_VERSION = "PSOC 2012 (2022 Updates)"


@pytest.fixture
def populated(tmp_path, monkeypatch):
    """A temporary repo root with hashed fixture sources and a manifest."""
    manifest = build_populated_sources(tmp_path)
    monkeypatch.setattr(acquisition_state, "REPO_ROOT", tmp_path)
    return {"root": tmp_path, "manifest": manifest}


# ---------------------------------------------------------------------------
# The happy path, stage by stage
# ---------------------------------------------------------------------------

def test_acquisition_verifies_a_good_snapshot(populated):
    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    assert record.acquired, record.reason
    assert len(record.sha256) == 64
    assert record.retrieved_at


def test_failed_retrieval_never_counts_as_acquired(populated):
    """psa_ows was attempted and failed; it must not be treated as available."""
    record = acquisition_state.verify("psa_ows", populated["manifest"])
    assert not record.acquired
    assert "No successful retrieval" in record.reason


def test_parser_produces_normalised_rows(populated):
    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    result = get_parser("psa_lfs_occupation_table").run(record.path)
    assert result.row_count == len(LFS_ROWS)
    managers = next(r for r in result.rows if r.source_code == "1")
    assert managers.value == 111
    assert managers.source_code_version == CANONICAL_VERSION
    assert managers.reference_period
    # The suppressed cell must survive as suppressed, not as a zero.
    armed = next(r for r in result.rows if r.source_code == "0")
    assert armed.value is None
    assert armed.suppression_flag == "suppressed_by_publisher"


def test_valid_published_survey_estimate_reaches_an_observation(populated):
    """Fixture 1 of 7: a valid published survey estimate."""
    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    rows = get_parser("psa_lfs_occupation_table").run(record.path).rows
    outcomes = transform.transform_rows(
        "employment_count", rows, record, CANONICAL_CODES, CANONICAL_VERSION
    )
    published = [o for o in outcomes if o.availability == "published"]
    assert published, "no employment value published from a good fixture"
    managers = next(o for o in published if o.psoc_code == "1")
    assert managers.value == 111
    assert managers.transformation_id == "T-010-lfs-employment"
    assert managers.normalised_row_id
    assert managers.reference_period


def test_calculated_statistic_reaches_an_observation(populated):
    """Fixture 2 of 7: a calculated statistic — the OFW distribution share."""
    record = acquisition_state.verify("psa_sof", populated["manifest"])
    rows = get_parser("psa_sof_occupation_table").run(record.path).rows
    outcomes = transform.transform_rows(
        "ofw_distribution_share", rows, record, CANONICAL_CODES, CANONICAL_VERSION
    )
    published = {o.psoc_code: o.value for o in outcomes if o.availability == "published"}
    assert published, "no OFW share computed"
    # 10 / (10+30+60) = 0.1 — this is P(occupation | OFW).
    assert published["1"] == pytest.approx(0.10)
    assert published["9"] == pytest.approx(0.60)
    assert sum(published.values()) == pytest.approx(1.0)


def test_proxy_derived_onet_value_reaches_an_observation(populated):
    """Fixture 3 of 7: a proxy-derived O*NET value."""
    record = acquisition_state.verify("onet", populated["manifest"])
    rows = get_parser("onet_job_zones").run(record.path).rows
    assert rows, "no Job Zone rows parsed"
    zone = next(r for r in rows if r.source_code == "11-1011.00")
    assert zone.value == 5
    assert zone.geography == "United States"
    assert zone.source_code_version == "31.0"


def test_suppressed_value_is_published_as_suppressed_not_zero(populated):
    """Fixture 4 of 7: a suppressed value."""
    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    rows = get_parser("psa_lfs_occupation_table").run(record.path).rows
    outcomes = transform.transform_rows(
        "employment_count", rows, record, CANONICAL_CODES, CANONICAL_VERSION
    )
    armed = next(o for o in outcomes if o.psoc_code == "0")
    assert armed.value is None
    assert armed.availability == "suppressed_low_sample"
    assert armed.suppression_status == "suppressed_by_publisher"


def test_onet_task_statements_and_importance_parse(populated):
    record = acquisition_state.verify("onet", populated["manifest"])
    tasks = get_parser("onet_task_statements").run(record.path).rows
    ratings = get_parser("onet_task_ratings").run(record.path).rows
    assert len(tasks) == 2
    # Only Importance is kept; the Frequency row must be ignored.
    assert len(ratings) == 2
    assert all(r.measure == "task_importance" for r in ratings)


# ---------------------------------------------------------------------------
# Mutations: each must stop publication
# ---------------------------------------------------------------------------

def test_wrong_hash_blocks_the_source(populated):
    """Mutation: the file changed after the manifest recorded it."""
    root = populated["root"]
    path = root / "data" / "raw" / "psa_lfs" / "lfs_employment_by_occupation_FIXTURE.csv"
    path.write_text(path.read_text(encoding="utf-8") + "9,Tampered,1,x,y,z,w\n", encoding="utf-8")

    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    assert not record.acquired
    assert "Hash mismatch" in record.reason


def test_missing_raw_file_blocks_the_source(populated):
    """Mutation: a stale manifest pointing at a file that is gone."""
    root = populated["root"]
    (root / "data" / "raw" / "psa_lfs" / "lfs_employment_by_occupation_FIXTURE.csv").unlink()
    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    assert not record.acquired
    assert "not on disk" in record.reason


def test_incompatible_classification_version_is_refused(populated, tmp_path):
    """Mutation: a source that used an older PSOC must not be silently accepted."""
    path = tmp_path / "old_version.csv"
    write_psa_csv(path, [("1", "Managers", "111", "FIXTURE 2016", "PSOC 1992")])
    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    rows = get_parser("psa_lfs_occupation_table").run(path).rows
    outcomes = transform.transform_rows(
        "employment_count", rows, record, CANONICAL_CODES, CANONICAL_VERSION
    )
    assert all(o.value is None for o in outcomes)
    assert any("not reconcilable" in o.reason for o in outcomes)


def test_unknown_occupation_code_is_reported_not_dropped(populated, tmp_path):
    """Mutation: an unknown foreign key must surface, not vanish."""
    path = tmp_path / "unknown_code.csv"
    write_psa_csv(path, [("XX", "Nonexistent", "5", "FIXTURE 2024", "PSOC 2012 (2022 Updates)")])
    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    rows = get_parser("psa_lfs_occupation_table").run(path).rows
    outcomes = transform.transform_rows(
        "employment_count", rows, record, CANONICAL_CODES, CANONICAL_VERSION
    )
    assert len(outcomes) == 1
    assert outcomes[0].value is None
    assert "no canonical PSOC unit" in outcomes[0].reason


def test_missing_reference_period_blocks_publication(populated, tmp_path):
    """Mutation: an undated figure must not publish."""
    path = tmp_path / "no_period.csv"
    write_psa_csv(path, [("1", "Managers", "111", "", "PSOC 2012 (2022 Updates)")])
    record = acquisition_state.verify("psa_lfs", populated["manifest"])
    rows = get_parser("psa_lfs_occupation_table").run(path).rows
    outcomes = transform.transform_rows(
        "employment_count", rows, record, CANONICAL_CODES, CANONICAL_VERSION
    )
    assert outcomes[0].value is None
    assert "reference period" in outcomes[0].reason


def test_industry_table_is_refused_by_the_ows_parser(tmp_path):
    """Mutation: v1's actual defect — an OWS industry table used for occupations."""
    from trabaholens.v2.sources.base import FormatValidationError

    path = tmp_path / "ows_wage_by_industry_2024.csv"
    write_psa_csv(path, [("C", "Manufacturing", "18000", "FIXTURE", "PSOC 2012 (2022 Updates)")])
    with pytest.raises(FormatValidationError, match="industry"):
        get_parser("psa_ows_occupation_table").run(path)


def test_malformed_json_is_refused_before_parsing(tmp_path):
    from trabaholens.v2.sources.base import FormatValidationError

    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FormatValidationError, match="not valid JSON"):
        get_parser("psa_lfs_occupation_table").run(path)


def test_csv_missing_required_columns_is_refused(tmp_path):
    from trabaholens.v2.sources.base import FormatValidationError

    path = tmp_path / "wrong_columns.csv"
    path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(FormatValidationError, match="missing required columns"):
        get_parser("psa_lfs_occupation_table").run(path)


def test_onet_archive_missing_a_member_is_refused(tmp_path):
    import zipfile

    from trabaholens.v2.sources.base import FormatValidationError

    path = tmp_path / "db_31_0_text.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("db_31_0_text/Occupation Data.txt", "O*NET-SOC Code\tTitle\n")
    with pytest.raises(FormatValidationError, match="does not contain"):
        get_parser("onet_job_zones").run(path)


def test_non_zip_onet_snapshot_is_refused(tmp_path):
    from trabaholens.v2.sources.base import FormatValidationError

    path = tmp_path / "db_31_0_text.zip"
    path.write_text("this is not a zip", encoding="utf-8")
    with pytest.raises(FormatValidationError, match="not a zip"):
        get_parser("onet_job_zones").run(path)


def test_duplicate_source_rows_are_visible_in_normalised_ids(populated, tmp_path):
    """Mutation: duplicated rows must not silently collapse or double count."""
    path = tmp_path / "dupes.csv"
    write_psa_csv(
        path,
        [
            ("1", "Managers", "111", "FIXTURE 2024", "PSOC 2012 (2022 Updates)"),
            ("1", "Managers", "111", "FIXTURE 2024", "PSOC 2012 (2022 Updates)"),
        ],
    )
    rows = get_parser("psa_lfs_occupation_table").run(path).rows
    assert len(rows) == 2
    # Row ids carry the ordinal, so duplicates are distinguishable downstream
    # rather than overwriting one another in a dict keyed by code.
    assert len({r.normalised_row_id for r in rows}) == 2


def test_impossible_share_is_caught_by_the_release_validator():
    """Mutation: a share above 1 must fail validation."""
    from tests.conftest import observation
    from trabaholens.v2 import validate

    rows = [
        observation(
            metric_id="ofw_distribution_share",
            unit="share of all OFWs",
            metric_value="1.4",
            source_id="psa_sof",
        )
    ]
    failures = validate.check_observations(rows, {"psa_sof"})
    assert any(f.check == "impossible_percentage" for f in failures)


def test_fixture_tested_stage_cannot_back_a_published_value():
    """A parser that has never seen its real source may not publish a number."""
    from tests.conftest import observation
    from trabaholens.v2 import validate

    rows = [observation(pipeline_status="implemented_fixture_tested_only")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any(f.check == "pipeline_status" for f in failures)


def test_published_value_without_a_normalised_row_id_is_refused():
    from tests.conftest import observation
    from trabaholens.v2 import validate

    rows = [observation(normalised_row_id="")]
    failures = validate.check_observations(rows, {"psa_lfs"})
    assert any("normalised_row_id" in f.detail for f in failures)


# ---------------------------------------------------------------------------
# Full build: manifest -> canonical tables -> release -> site payload
# ---------------------------------------------------------------------------

def test_full_build_publishes_a_value_and_it_reaches_the_site_payload(populated, monkeypatch, tmp_path):
    """The one test that proves the whole pipeline, not its pieces.

    Drives the real canonical builder and release builder against the fixture
    manifest and asserts a value arrives in the payload the interface reads,
    carrying its provenance.
    """
    import csv as _csv

    from trabaholens.v2 import build_canonical, build_release, validate

    out = tmp_path / "canonical"
    out.mkdir()
    obs_path = out / "metric_observations.csv"

    # Point every module that reads the manifest at the fixture.
    monkeypatch.setattr(build_canonical, "verify_all", lambda ids: {
        sid: acquisition_state.verify(sid, populated["manifest"]) for sid in ids
    })
    monkeypatch.setattr(build_canonical, "METRIC_OBSERVATIONS_CSV", obs_path)

    classifications = build_canonical.build_classifications()
    occupations = build_canonical.build_occupations(classifications)
    observations = build_canonical.build_metric_observations(occupations)
    build_canonical.write_table(
        obs_path, build_canonical.METRIC_OBSERVATIONS_COLUMNS, observations
    )

    rows = list(_csv.DictReader(obs_path.open(encoding="utf-8")))
    published = [r for r in rows if r["availability"] == "published"]
    assert published, "the populated fixture produced no published observation"

    managers = next(
        r for r in published
        if r["metric_id"] == "employment_count" and r["psoc_code"] == "1"
    )
    assert managers["metric_value"] == "111"
    assert managers["derivation_class"] == "estimated"
    assert managers["source_authority"] == "ph_official_statistical_authority"
    assert len(managers["source_file_hash"]) == 64
    assert managers["retrieved_at"]
    assert managers["reference_period"]
    assert managers["parser_id"] == "psa_lfs_occupation_table"
    assert managers["transformation_id"] == "T-010-lfs-employment"
    assert managers["normalised_row_id"]
    assert managers["confidence_reasons"]
    assert managers["pipeline_status"] == "implemented_verified_with_real_source"

    # And the release validator accepts these rows.
    registry_ids = {"psa_lfs", "psa_ows", "psa_sof", "psa_informal", "onet", "llm_scoring", "psa_psoc"}
    failures = validate.check_observations(rows, registry_ids)
    assert not failures, [str(f) for f in failures]

    # ...and the payload the interface reads carries the value with provenance.
    monkeypatch.setattr(build_release, "METRIC_OBSERVATIONS_CSV", obs_path)
    monkeypatch.setattr(build_release, "OCCUPATIONS_CSV", _write(out / "occupations.csv",
                        build_canonical.OCCUPATIONS_COLUMNS, occupations))
    monkeypatch.setattr(build_release, "MODEL_SCORES_CSV", _write(out / "model_scores.csv",
                        build_canonical.MODEL_SCORES_COLUMNS, []))
    payload = build_release.build_payload({"psoc_version": "FIXTURE"})

    entry = next(o for o in payload["occupations"] if o["psoc_code"] == "1")
    metric = entry["metrics"]["employment_count"]
    assert metric["value"] == 111
    assert metric["derivation_class"] == "estimated"
    assert metric["source_authority"] == "ph_official_statistical_authority"
    assert metric["confidence_reasons"]
    assert payload["counts"]["published_values"] >= 1


def _write(path: Path, columns, rows) -> Path:
    from trabaholens.v2.build_canonical import write_table

    write_table(path, columns, rows)
    return path


def test_suppressed_row_reaches_the_payload_as_null_not_zero(populated, monkeypatch, tmp_path):
    """A suppressed cell must arrive as null, never as 0."""
    from trabaholens.v2 import build_canonical, build_release

    out = tmp_path / "canonical2"
    out.mkdir()
    obs_path = out / "metric_observations.csv"
    monkeypatch.setattr(build_canonical, "verify_all", lambda ids: {
        sid: acquisition_state.verify(sid, populated["manifest"]) for sid in ids
    })
    classifications = build_canonical.build_classifications()
    occupations = build_canonical.build_occupations(classifications)
    observations = build_canonical.build_metric_observations(occupations)
    build_canonical.write_table(obs_path, build_canonical.METRIC_OBSERVATIONS_COLUMNS, observations)

    monkeypatch.setattr(build_release, "METRIC_OBSERVATIONS_CSV", obs_path)
    monkeypatch.setattr(build_release, "OCCUPATIONS_CSV", _write(out / "occupations.csv",
                        build_canonical.OCCUPATIONS_COLUMNS, occupations))
    monkeypatch.setattr(build_release, "MODEL_SCORES_CSV", _write(out / "model_scores.csv",
                        build_canonical.MODEL_SCORES_COLUMNS, []))
    payload = build_release.build_payload({"psoc_version": "FIXTURE"})

    armed = next(o for o in payload["occupations"] if o["psoc_code"] == "0")
    metric = armed["metrics"]["employment_count"]
    assert metric["value"] is None
    assert metric["availability"] == "suppressed_low_sample"
