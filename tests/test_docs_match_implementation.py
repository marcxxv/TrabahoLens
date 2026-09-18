"""Documentation must match the implementation it describes.

v1's README claimed "173 occupations" as a string literal. It happened to be
right, but nothing checked it, so it would have gone stale silently. Any figure
this project states in prose is asserted here against the data.

If one of these fails, fix whichever is wrong — do not delete the assertion.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import yaml

from trabaholens.v2 import psoc
from trabaholens.v2.paths import (
    METRIC_OBSERVATIONS_CSV,
    OCCUPATIONS_CSV,
    REPO_ROOT,
    SITE_DATA_JSON,
    SOURCE_REGISTRY_YAML,
)
from trabaholens.v2.schema import DERIVATION_CLASSES, METRIC_DEFINITIONS, SOURCE_AUTHORITIES

DOCS = [REPO_ROOT / "README.md"] + sorted((REPO_ROOT / "docs").glob("*.md"))


def _payload() -> dict:
    return json.loads(SITE_DATA_JSON.read_text(encoding="utf-8"))


def _all_prose() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in DOCS)


def test_psoc_group_counts_stated_in_docs_are_correct():
    prose = _all_prose()
    majors = len(psoc.MAJOR_GROUPS)
    subs = len(psoc.SUB_MAJOR_GROUPS)

    # Every "<n> major groups" claim must equal the real count.
    for stated in re.findall(r"(\d+)\s+(?:PSOC\s+)?major groups", prose):
        assert int(stated) == majors, f"docs claim {stated} major groups; there are {majors}"
    for stated in re.findall(r"(\d+)\s+sub-major groups", prose):
        assert int(stated) == subs, f"docs claim {stated} sub-major groups; there are {subs}"


def test_source_count_stated_in_docs_is_correct():
    registry = yaml.safe_load(SOURCE_REGISTRY_YAML.read_text(encoding="utf-8"))
    actual = len(registry["sources"])
    for stated in re.findall(r"(\d+)\s+sources with", _all_prose()):
        assert int(stated) == actual, f"docs claim {stated} sources; the registry has {actual}"


def test_observation_count_stated_in_limitations_is_correct():
    rows = list(csv.DictReader(METRIC_OBSERVATIONS_CSV.open(encoding="utf-8")))
    text = (REPO_ROOT / "docs" / "limitations.md").read_text(encoding="utf-8")
    match = re.search(r"contains (\d+) rows: (\w+) published", text)
    assert match, "limitations.md no longer states observation and publication counts"
    assert int(match.group(1)) == len(rows)
    words = {"zero": 0, "ten": 10}
    assert words[match.group(2)] == sum(bool((row["metric_value"] or "").strip()) for row in rows)


def test_published_value_count_matches_payload():
    payload = _payload()
    canonical = list(csv.DictReader(METRIC_OBSERVATIONS_CSV.open(encoding="utf-8")))
    published = [row for row in canonical if (row["metric_value"] or "").strip()]
    assert payload["counts"]["published_values"] == len(published)
    assert {row["metric_id"] for row in published} == {"employment_count"}
    assert payload["counts"]["exposure_scores"] == 0
    values = [
        metric["value"]
        for entry in payload["occupations"]
        for metric in entry["metrics"].values()
    ]
    assert values, "no metrics in the payload at all — the claim is vacuous"
    assert sum(value is not None for value in values) == len(published)


def test_classification_unit_count_in_payload_matches_the_canonical_table():
    occupations = list(csv.DictReader(OCCUPATIONS_CSV.open(encoding="utf-8")))
    payload = _payload()
    assert payload["counts"]["psoc_classification_units"] == len(occupations)


def test_classification_units_are_not_described_as_measured_occupations():
    """Finding 14: 53 aggregate units must not read as 53 occupations."""
    payload = _payload()
    counts = payload["counts"]
    assert counts["detailed_occupations"] == 0, (
        "detailed_occupations is non-zero, but PSOC minor and unit groups have not "
        "been retrieved"
    )
    assert "vocabulary_note" in counts
    # The interface must not carry a bare "N occupations" headline.
    html = (REPO_ROOT / "site" / "index.html").read_text(encoding="utf-8")
    assert "counts.occupations" not in html


def test_every_evidence_axis_value_is_documented_in_the_dictionary():
    """Both axes must be documented, not just one."""
    text = (REPO_ROOT / "docs" / "data-dictionary.md").read_text(encoding="utf-8")
    for key in DERIVATION_CLASSES:
        assert f"`{key}`" in text, f"derivation_class {key!r} is undocumented"
    for key in SOURCE_AUTHORITIES:
        assert f"`{key}`" in text, f"source_authority {key!r} is undocumented"


def test_no_metric_is_directly_observed_while_its_source_is_a_survey():
    """Guards the axis conflation the remediation removed."""
    for definition in METRIC_DEFINITIONS.values():
        if definition.expected_derivation_class == "directly_observed":
            assert "survey" not in definition.definition.lower(), (
                f"{definition.metric_id} is marked directly_observed but its definition "
                "describes a survey. Authority is not derivation."
            )


def test_every_metric_is_documented_in_the_methodology_or_dictionary():
    prose = (
        (REPO_ROOT / "docs" / "methodology.md").read_text(encoding="utf-8")
        + (REPO_ROOT / "docs" / "data-dictionary.md").read_text(encoding="utf-8")
        + (REPO_ROOT / "docs" / "migration-notes.md").read_text(encoding="utf-8")
    )
    for metric_id in METRIC_DEFINITIONS:
        assert metric_id in prose, f"metric {metric_id!r} is not described in the docs"


def test_required_disclaimer_is_verbatim_everywhere_it_appears():
    """The exact wording is specified; paraphrase would weaken it."""
    required = (
        "Generative-AI task exposure indicates how much an occupation's tasks may be "
        "affected or assisted by generative AI. It is not an estimate of automation, "
        "displacement, layoffs, or future employment."
    )
    payload = _payload()
    assert payload["disclaimers"]["exposure"] == required

    def normalise(text: str) -> str:
        # Strip Markdown blockquote markers and collapse wrapping, so a
        # correctly quoted disclaimer is not judged on its line breaks.
        return re.sub(r"\s+", " ", re.sub(r"^\s*>\s?", "", text, flags=re.M))

    # It must appear, unparaphrased, in the interface-facing documents.
    for path in (REPO_ROOT / "README.md", REPO_ROOT / "docs" / "methodology.md"):
        assert normalise(required) in normalise(path.read_text(encoding="utf-8")), (
            f"{path.name} does not carry the disclaimer verbatim"
        )


def test_no_independent_validation_claim_is_consistent():
    """Either an expert reviewed it, or every document says none did."""
    statement = "has not yet undergone independent"
    for name in ("methodology.md", "limitations.md", "exposure-protocol.md", "sensitivity-report.md"):
        text = (REPO_ROOT / "docs" / name).read_text(encoding="utf-8")
        assert statement in text, f"docs/{name} omits the no-validation statement"


def test_documented_make_targets_exist():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    declared = set(re.search(r"^\.PHONY:([\s\S]*?)\n\n", makefile, re.M).group(1).replace("\\", "").split())
    # Only code-formatted or line-leading invocations; "make it ready" is prose.
    invocations = re.findall(r"`make ([a-z][a-z-]*)", _all_prose())
    invocations += re.findall(r"^make ([a-z][a-z-]*)", _all_prose(), re.M)
    assert invocations, "no make invocations found in the docs at all"
    for target in invocations:
        assert target in declared, f"docs reference `make {target}` which the Makefile does not define"


def test_documented_paths_exist():
    prose = _all_prose()
    referenced = set(re.findall(r"`(data/[a-z0-9_/.-]+|docs/[a-z0-9_/.-]+\.(?:md|csv|json))`", prose))
    missing = [
        ref for ref in referenced
        if not Path(REPO_ROOT / ref).exists() and not ref.endswith("/")
    ]
    # Runtime paths (created by a fetch or a scoring run) and the three v1
    # locations the migration notes describe as vacated are expected absences.
    vacated_by_migration = {
        "data/derived/occupations_ph.csv",
        "data/derived/scores_ai_only.json",
        "data/reference/occupations_seed.json",
    }
    missing = [
        m for m in missing
        if "runs/" not in m and "raw/" not in m and m not in vacated_by_migration
    ]
    assert not missing, f"docs reference paths that do not exist: {missing}"
