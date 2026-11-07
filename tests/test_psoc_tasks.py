"""PSA's own PSOC task statements as the exposure task source."""
import copy

import pytest

from trabaholens.v2 import psoc_tasks
from trabaholens.v2 import score_exposure as sx
from trabaholens.v2.paths import REPO_ROOT

WORKBOOK = REPO_ROOT / "data/raw/psa_psoc/psoc_2022_updates.xlsx"
needs_workbook = pytest.mark.skipif(not WORKBOOK.exists(), reason="pinned PSOC workbook not present")


@pytest.fixture(scope="module")
def extracted():
    return psoc_tasks.extract_tasks(WORKBOOK)


@needs_workbook
def test_real_workbook_yields_every_published_task_list(extracted):
    rows, report = extracted
    assert report["unit_groups"] == 466
    assert report["unit_groups_with_tasks"] == 447
    assert report["task_statements"] == len(rows) == 3362
    missing = {u["psoc_code"] for u in report["unit_groups_without_tasks"]}
    # Residual groups and the armed forces carry no task list in the source.
    assert {"0110", "0210", "0310", "1219", "5249", "9335"} <= missing
    assert len(missing) == 19


@needs_workbook
def test_task_rows_are_traceable_and_never_borrow_a_crosswalk(extracted):
    rows, _ = extracted
    assert len({r["task_id"] for r in rows}) == len(rows)
    for row in rows:
        assert row["source_cell"].startswith("Group ") and "!D" in row["source_cell"]
        assert row["source_file_hash"] == psoc_tasks.PSOC_WORKBOOK_SHA256
        assert row["crosswalk_id"] == psoc_tasks.NATIVE_CROSSWALK_ID
        assert row["onet_soc_code"] == "" and row["task_importance"] == ""
        statement = row["task_statement"]
        assert statement.endswith("etc.") or not statement.endswith((";", "."))


@needs_workbook
def test_source_letter_repetition_is_reported_not_hidden(extracted):
    rows, report = extracted
    assert any(a.startswith("1113:") for a in report["source_anomalies"])
    labels = [r["source_item_label"] for r in rows if r["psoc_code"] == "1113"]
    assert labels.count("e)") == 2


@needs_workbook
def test_native_tasks_pass_scoring_validation_and_tampering_fails(extracted):
    rows, _ = extracted
    sx.validate_task_inputs(rows)
    borrowed = copy.deepcopy(rows[:1])
    borrowed[0]["onet_soc_code"] = "15-1252.00"
    with pytest.raises(sx.ScoringRefusal, match="O\\*NET code"):
        sx.validate_task_inputs(borrowed)
    claimed = copy.deepcopy(rows[:1])
    claimed[0]["crosswalk_review_status"] = "human_reviewed"
    with pytest.raises(sx.ScoringRefusal, match="crosswalk_review_status"):
        sx.validate_task_inputs(claimed)


def test_extractor_refuses_an_unreviewed_workbook(tmp_path):
    fake = tmp_path / "psoc.xlsx"
    fake.write_bytes(b"not the reviewed workbook")
    with pytest.raises(psoc_tasks.TaskExtractionError, match="reviewed PSOC workbook"):
        psoc_tasks.extract_tasks(fake)


def test_native_evidence_confidence_is_capped_until_human_review():
    kwargs = dict(
        task_statement="preparing scientific papers and reports",
        task_importance="",
        crosswalk_match_quality=psoc_tasks.NATIVE_NOT_APPLICABLE,
        crosswalk_match_type=psoc_tasks.NATIVE_NOT_APPLICABLE,
        task_source_is_philippine=True,
        successful_attempts=2,
        minimum_attempts=2,
    )
    score, reasons = sx.compute_evidence_confidence(**kwargs)
    assert score == 4 and any("no crosswalk" in r for r in reasons)
    reviewed, _ = sx.compute_evidence_confidence(**kwargs, human_review_status="human_reviewed")
    assert reviewed == 5
    thin, _ = sx.compute_evidence_confidence(**{**kwargs, "successful_attempts": 1})
    assert thin == 1


def test_banned_model_wording_is_not_republished():
    from trabaholens.v2.exposure_publish import _phrase

    assert _phrase("drafting reports") == "drafting reports"
    assert _phrase("these roles are at risk of automation") == ""
