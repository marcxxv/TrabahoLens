"""PSOC importer and crosswalk composition. Findings 4, 5 and 6."""

from __future__ import annotations

import csv
import json

import pytest

from trabaholens.v2.crosswalk import (
    CrosswalkEdge,
    ComposedMapping,
    compose,
    coverage_report,
)
from trabaholens.v2.sources.base import FormatValidationError
from trabaholens.v2.sources.psoc_importer import (
    CANONICAL_PSOC_VERSION,
    EXPECTED_STRUCTURE,
    PsocVolumeParser,
)


def write_psoc_csv(path, rows, version=CANONICAL_PSOC_VERSION):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["code", "title", "version", "isco08_code"])
        writer.writeheader()
        for code, title in rows:
            writer.writerow({"code": code, "title": title, "version": version, "isco08_code": code})
    return path


# ---------------------------------------------------------------------------
# PSOC importer
# ---------------------------------------------------------------------------

def test_importer_builds_hierarchy_from_a_code_list(tmp_path):
    path = write_psoc_csv(tmp_path / "psoc.csv", [
        ("2", "Professionals"),
        ("25", "ICT Professionals"),
        ("251", "Software and Applications Developers"),
        ("2512", "Software Developers"),
    ])
    report = PsocVolumeParser().import_classification(path)
    assert report.counts["psoc_major_group"] == 1
    assert report.counts["psoc_unit_group"] == 1
    unit = next(r for r in report.rows if r["psoc_code"] == "2512")
    assert unit["level"] == "psoc_unit_group"
    assert unit["parent_psoc_code"] == "251"
    assert unit["psoc_major_label"] == "Professionals"
    assert unit["verification_status"] == "verified_against_source"


def test_importer_reports_an_incomplete_import_rather_than_accepting_it(tmp_path):
    path = write_psoc_csv(tmp_path / "psoc.csv", [("2", "Professionals")])
    report = PsocVolumeParser().import_classification(path)
    assert not report.complete
    assert any("not a complete PSOC" in p for p in report.problems)
    assert report.counts["psoc_unit_group"] == 0


def test_importer_flags_orphans(tmp_path):
    path = write_psoc_csv(tmp_path / "psoc.csv", [("2512", "Software Developers")])
    report = PsocVolumeParser().import_classification(path)
    assert any("has no parent" in p for p in report.problems)


def test_importer_rejects_duplicate_and_malformed_codes(tmp_path):
    path = write_psoc_csv(tmp_path / "psoc.csv", [
        ("2", "Professionals"), ("2", "Professionals again"), ("2A", "Bad code"),
    ])
    report = PsocVolumeParser().import_classification(path)
    assert any("duplicate code" in p for p in report.problems)
    assert any("non-numeric code" in p for p in report.problems)


def test_importer_refuses_to_mix_classification_versions(tmp_path):
    path = tmp_path / "mixed.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["code", "title", "version"])
        writer.writeheader()
        writer.writerow({"code": "2", "title": "Professionals", "version": "PSOC 2012"})
        writer.writerow({"code": "25", "title": "ICT", "version": "PSOC 1992"})
    report = PsocVolumeParser().import_classification(path)
    assert any("must not mix classification versions" in p for p in report.problems)


def test_importer_refuses_a_pdf(tmp_path):
    path = tmp_path / "psoc.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(FormatValidationError, match="not a source of record"):
        PsocVolumeParser().validate_format(path)


def test_expected_structure_matches_the_psa_publication():
    """10 major, 43 sub-major, 130 minor, 456 unit — the 2022 Updates."""
    assert EXPECTED_STRUCTURE == {
        "psoc_major_group": 10,
        "psoc_sub_major_group": 43,
        "psoc_minor_group": 130,
        "psoc_unit_group": 456,
    }


def test_production_classification_is_still_unverified():
    """Nothing may claim verification until the real volume is imported."""
    rows = list(csv.DictReader(open("data/canonical/classifications.csv", encoding="utf-8")))
    assert rows
    assert all(r["verification_status"] == "unverified_pending_source" for r in rows), (
        "a classification row claims verification, but the PSA volume has not been retrieved"
    )
    # And it holds only the aggregate levels, not invented detail.
    assert {r["level"] for r in rows} == {"psoc_major_group", "psoc_sub_major_group"}


# ---------------------------------------------------------------------------
# Crosswalk composition
# ---------------------------------------------------------------------------

def edge(frm_sys, frm, to_sys, to, match="exact", quality="high",
         basis="published_correspondence", review="human_reviewed"):
    return CrosswalkEdge(frm_sys, frm, to_sys, to, match, quality, basis, review)


CHAIN = (
    [edge("PSOC", "25", "ISCO-08", "25")],
    [edge("ISCO-08", "25", "SOC", "15")],
    [edge("SOC", "15", "O*NET-SOC", "15-1252.00")],
)


def test_every_intermediate_classification_is_preserved():
    mapping = compose("25", *CHAIN)[0]
    assert mapping.intermediate_codes == ["ISCO-08:25", "SOC:15"]
    assert mapping.hop_count if hasattr(mapping, "hop_count") else len(mapping.hops) == 3


def test_a_clean_chain_is_publishable():
    mapping = compose("25", *CHAIN)[0]
    assert mapping.resolution == "resolved"
    assert mapping.match_quality == "high"
    assert mapping.publishable


def test_chain_quality_is_the_weakest_hop():
    weak = ([edge("PSOC", "25", "ISCO-08", "25")],
            [edge("ISCO-08", "25", "SOC", "15", match="broader", quality="low")],
            [edge("SOC", "15", "O*NET-SOC", "15-1252.00")])
    mapping = compose("25", *weak)[0]
    assert mapping.match_quality == "low"
    assert mapping.match_type == "broader"


def test_title_similarity_alone_cannot_authorise_publication():
    proposed = ([edge("PSOC", "25", "ISCO-08", "25")],
                [edge("ISCO-08", "25", "SOC", "15", basis="title_similarity_only",
                      review="machine_proposed")],
                [edge("SOC", "15", "O*NET-SOC", "15-1252.00")])
    mapping = compose("25", *proposed)[0]
    assert mapping.mapping_basis == "title_similarity_only"
    assert not mapping.publishable


def test_many_to_many_is_never_silently_resolved():
    fan_out = (CHAIN[0], CHAIN[1],
               [edge("SOC", "15", "O*NET-SOC", "15-1252.00"),
                edge("SOC", "15", "O*NET-SOC", "15-1211.00")])
    mappings = compose("25", *fan_out)
    assert len(mappings) == 2
    assert all(m.resolution == "ambiguous" for m in mappings)
    assert all(not m.publishable for m in mappings)
    assert all("must choose or reject" in m.notes for m in mappings)


def test_no_defensible_match_ends_the_chain():
    broken = ([edge("PSOC", "91", "ISCO-08", "91", match="no_defensible_match", quality="none")],
              CHAIN[1], CHAIN[2])
    mapping = compose("91", *broken)[0]
    assert mapping.resolution == "unmatched"
    assert not mapping.publishable


def test_missing_correspondence_is_reported_at_the_hop_that_failed():
    mapping = compose("25", CHAIN[0], CHAIN[1], [])[0]
    assert mapping.resolution == "unmatched"
    assert "No SOC->O*NET correspondence" in mapping.notes


def test_a_rejected_hop_makes_the_chain_rejected():
    rejected = (CHAIN[0],
                [edge("ISCO-08", "25", "SOC", "15", review="rejected")],
                CHAIN[2])
    mapping = compose("25", *rejected)[0]
    assert mapping.review_status == "rejected"
    assert not mapping.publishable


def test_unreviewed_chain_is_machine_proposed_not_human_reviewed():
    unreviewed = (CHAIN[0],
                  [edge("ISCO-08", "25", "SOC", "15", review="unreviewed")],
                  CHAIN[2])
    assert compose("25", *unreviewed)[0].review_status == "machine_proposed"


def test_coverage_report_separates_the_four_outcomes():
    good = compose("25", *CHAIN)
    unmatched = compose("91", [], [], [])  # no PSOC->ISCO edge at all
    report = coverage_report(good + unmatched, ["25", "91", "0"])
    assert report["high_quality_mappings"] == ["25"]
    assert "91" in report["unmatched_philippine_specific"]
    assert "0" in report["unmatched_philippine_specific"]
    assert "25" not in report["excluded_from_exposure_scoring"]


def test_ambiguous_codes_are_excluded_from_exposure_scoring():
    fan_out = (CHAIN[0], CHAIN[1],
               [edge("SOC", "15", "O*NET-SOC", "15-1252.00"),
                edge("SOC", "15", "O*NET-SOC", "15-1211.00")])
    report = coverage_report(compose("25", *fan_out), ["25"])
    assert report["ambiguous_mappings"] == ["25"]
    assert "25" in report["excluded_from_exposure_scoring"]
    assert report["coverage_share_high_quality"] == 0.0


def test_no_real_crosswalk_chain_is_shipped():
    """The canonical crosswalk must hold no publishable PSOC->O*NET chain yet."""
    rows = list(csv.DictReader(open("data/canonical/crosswalk_psoc_isco_soc.csv", encoding="utf-8")))
    onet_rows = [r for r in rows if r["source_classification"] == "O*NET-SOC"]
    assert not onet_rows, (
        "a PSOC->O*NET mapping is present, but no published correspondence has been retrieved"
    )
