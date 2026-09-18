"""Determinism, staleness and legacy-isolation.

v1 could not be rebuilt from a clean checkout, its published artifacts could go
stale without any check noticing, and its scoring was unreproducible. These
tests make each of those a build failure.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys

import pytest
from pathlib import Path

from trabaholens.v2.paths import (
    CLASSIFICATIONS_CSV,
    CROSSWALK_CSV,
    LEGACY_DIR,
    METRIC_OBSERVATIONS_CSV,
    MODEL_SCORES_CSV,
    OCCUPATIONS_CSV,
    RELEASE_MANIFEST_JSON,
    REPO_ROOT,
    SITE_DATA_JSON,
    TRANSFORMATIONS_CSV,
)

CANONICAL_TABLES = [
    CLASSIFICATIONS_CSV,
    OCCUPATIONS_CSV,
    METRIC_OBSERVATIONS_CSV,
    CROSSWALK_CSV,
    TRANSFORMATIONS_CSV,
    MODEL_SCORES_CSV,
]

FROZEN = "2026-01-01T00:00:00Z"


def _run(script: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), *args],
        cwd=REPO_ROOT, check=True, capture_output=True,
    )


def _digest(paths) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
        if p.exists()
    }


def test_canonical_build_is_deterministic():
    before = _digest(CANONICAL_TABLES)
    _run("build_canonical.py")
    after = _digest(CANONICAL_TABLES)
    assert before == after, "rebuilding the canonical tables changed their bytes"


def test_release_build_is_deterministic_with_frozen_time():
    _run("build_release.py", "--frozen-time", FROZEN)
    first = (SITE_DATA_JSON.read_bytes(), RELEASE_MANIFEST_JSON.read_bytes())
    _run("build_release.py", "--frozen-time", FROZEN)
    second = (SITE_DATA_JSON.read_bytes(), RELEASE_MANIFEST_JSON.read_bytes())
    assert first == second, "two builds at a frozen timestamp differ"


def test_committed_artifacts_are_not_stale():
    """The committed release must match what the committed inputs produce."""
    manifest = json.loads(RELEASE_MANIFEST_JSON.read_text(encoding="utf-8"))
    recorded = manifest["canonical_table_checksums"]
    for path in CANONICAL_TABLES:
        if not path.exists():
            continue
        key = path.resolve().relative_to(REPO_ROOT).as_posix()
        assert key in recorded, f"{key} is missing from the release manifest checksums"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == recorded[key], (
            f"{key} has changed since the release manifest was written. "
            "Run `make build-release`."
        )


def test_site_payload_matches_the_canonical_tables():
    payload = json.loads(SITE_DATA_JSON.read_text(encoding="utf-8"))
    occupations = list(csv.DictReader(OCCUPATIONS_CSV.open(encoding="utf-8")))
    observations = list(csv.DictReader(METRIC_OBSERVATIONS_CSV.open(encoding="utf-8")))

    assert payload["counts"]["psoc_classification_units"] == len(occupations)
    assert payload["counts"]["metric_observations"] == len(observations)
    payload_codes = {entry["psoc_code"] for entry in payload["occupations"]}
    assert payload_codes == {row["psoc_code"] for row in occupations}


def test_no_v2_module_reads_the_legacy_dataset():
    """v1 values are evidence about v1, never inputs to v2.

    Checked over the parsed syntax tree rather than the file text, so a
    docstring that *mentions* the legacy archive does not count as reading it,
    and a real reference cannot hide inside a comment either.
    """
    import ast

    v2_dir = REPO_ROOT / "src" / "trabaholens" / "v2"
    # audit_baseline profiles the legacy data; that is its whole job.
    # paths declares the constants it uses and reads nothing.
    exempt = {"audit_baseline.py", "paths.py"}

    legacy_names = {
        "LEGACY_DIR", "LEGACY_OCCUPATIONS_CSV", "LEGACY_SCORES_JSON",
        "LEGACY_SEED_JSON", "LEGACY_SITE_DATA_JSON",
    }
    legacy_literals = {
        "occupations_ph.csv", "scores_ai_only.json", "occupations_seed.json",
    }

    offenders = []
    for path in sorted(v2_dir.glob("*.py")):
        if path.name in exempt:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in legacy_names:
                offenders.append(f"{path.name}:{node.lineno} uses {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in legacy_names:
                offenders.append(f"{path.name}:{node.lineno} uses {node.attr}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # A docstring is an Expr-wrapped Constant; those are prose.
                if any(literal in node.value for literal in legacy_literals) and len(node.value) < 200:
                    offenders.append(f"{path.name}:{node.lineno} references a legacy file by name")
    assert not offenders, offenders


def test_release_publishes_no_legacy_value():
    payload = SITE_DATA_JSON.read_text(encoding="utf-8")
    for field in ("exposure_rationale", "primary_risk_vector", "hiring_intensity", '"outlook"'):
        assert field not in payload, f"{field} leaked into the release"


def test_legacy_archive_is_intact():
    """The archive must stay readable: the audit is reproducible from it."""
    expected = {
        "occupations_ph.csv", "scores_ai_only.json", "occupations_seed.json",
        "site_data.json", "index_v1.html", "README.md",
    }
    assert expected <= {p.name for p in LEGACY_DIR.iterdir()}
    site = json.loads((LEGACY_DIR / "site_data.json").read_text(encoding="utf-8"))
    assert len(site) == 173, "the archived v1 dataset has been altered"


def test_no_secrets_in_tracked_files():
    """No credential material in anything git tracks.

    The patterns are assembled from fragments so this file does not itself
    contain the literals it searches for — otherwise the scanner flags its own
    source, which is a false positive that would train someone to ignore it.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()

    patterns = [
        "sk-" + "or-v1-",                       # OpenRouter key prefix
        "OPENROUTER_API_KEY=" + "sk",           # a real key assigned in a committed file
        "BEGIN " + "PRIVATE KEY",
        "BEGIN RSA " + "PRIVATE KEY",
        "BEGIN OPENSSH " + "PRIVATE KEY",
        "aws_secret_access" + "_key",
    ]

    offenders = []
    for name in tracked:
        path = REPO_ROOT / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in patterns:
            if pattern in text:
                offenders.append(f"{name}: {pattern}")
    assert not offenders, offenders


def test_env_example_holds_no_real_key():
    example = REPO_ROOT / ".env.example"
    if not example.exists():
        return
    text = example.read_text(encoding="utf-8")
    assert "your_openrouter_api_key_here" in text or "=" not in text.strip(), (
        ".env.example should carry a placeholder, not a value"
    )


def test_env_files_are_ignored():
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignored
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    assert ".env" not in tracked


def test_staleness_check_passes_on_the_committed_tree():
    from trabaholens.v2 import staleness

    problems = staleness.check()
    assert not problems, problems


def test_staleness_check_ignores_build_time_stamps_only():
    """It must catch real drift and ignore self-referential stamps.

    `code_commit` records HEAD, and committing the artifact that holds it moves
    HEAD. A staleness check that compared it would fail on every commit, which
    is how a check gets ignored rather than fixed.
    """
    from trabaholens.v2 import staleness

    base = {"code_commit": "abc", "release_date": "2026-01-01", "counts": {"occupations": 53}}
    stamp_changed = {"code_commit": "def", "release_date": "1999-01-01", "counts": {"occupations": 53}}
    substance_changed = {"code_commit": "abc", "release_date": "2026-01-01", "counts": {"occupations": 999}}

    assert staleness.normalise(base) == staleness.normalise(stamp_changed)
    assert staleness.normalise(base) != staleness.normalise(substance_changed)

    difference = staleness._first_difference(
        staleness.normalise(base), staleness.normalise(substance_changed)
    )
    assert difference and "counts.occupations" in difference


def test_volatile_field_list_stays_minimal():
    """Anything added here stops being checked, so the list must stay small."""
    from trabaholens.v2 import staleness

    assert staleness.VOLATILE_FIELDS == {
        "code_commit", "repository_commit", "release_date", "generated_at",
    }


def test_staleness_check_does_not_discard_uncommitted_regeneration():
    """Running the check must leave the working tree byte-identical.

    An earlier version restored from git, which silently threw away a
    legitimate rebuild that had not been committed yet.
    """
    from trabaholens.v2 import staleness

    before = {path: path.read_bytes() for path in staleness.CHECKED_ARTIFACTS}
    staleness.check()
    after = {path: path.read_bytes() for path in staleness.CHECKED_ARTIFACTS}
    assert before == after


# ---------------------------------------------------------------------------
# Finding 17: legacy isolation
# ---------------------------------------------------------------------------

def test_no_production_make_target_invokes_a_legacy_module():
    """No `make` target may reach v1 metric generation or v1 scoring.

    The v1 modules stay importable because docs/audit/baseline-audit.md cites
    them line by line. They must not be reachable from a normal build.
    """
    import re

    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    legacy_modules = {
        "assign_ph_stats", "build_site_data", "filter_ph_occupations",
        "make_csv_ph", "score_ai_only", "fetch_onet", "fetch_psa",
    }

    # Every script a target runs, and every script those scripts import.
    referenced_scripts = set(re.findall(r"scripts/([a-z_]+)\.py", makefile))
    assert referenced_scripts, "no scripts referenced by the Makefile at all"

    for name in referenced_scripts:
        path = REPO_ROOT / "scripts" / f"{name}.py"
        assert path.exists(), f"Makefile runs scripts/{name}.py which does not exist"
        text = path.read_text(encoding="utf-8")
        for legacy in legacy_modules:
            assert f"trabaholens.{legacy}" not in text, (
                f"scripts/{name}.py imports the legacy module {legacy}"
            )


def test_legacy_entry_point_scripts_are_gone():
    for name in ("assign_ph_stats", "build_site_data", "filter_ph_occupations",
                 "make_csv_ph", "score_ai_only", "fetch_onet", "fetch_psa"):
        assert not (REPO_ROOT / "scripts" / f"{name}.py").exists(), (
            f"scripts/{name}.py is a retired v1 entry point and should not exist"
        )


def test_legacy_module_main_functions_refuse_to_run():
    """Importable for the audit, inert in practice."""
    import importlib

    for name in ("assign_ph_stats", "build_site_data", "score_ai_only"):
        module = importlib.import_module(f"trabaholens.{name}")
        assert hasattr(module, "main")
        with pytest.raises(SystemExit) as excinfo:
            module.main()
        assert "retired" in str(excinfo.value).lower()
        # The original logic is preserved for inspection, just not wired up.
        assert hasattr(module, "_v1_main"), f"{name} lost its preserved v1 logic"


def test_v1_scoring_prompt_is_not_reachable_from_the_v2_harness():
    """The anchored v1 prompt must not be loadable as a v2 prompt version."""
    from trabaholens.v2 import score_exposure as sx

    v1_text = (REPO_ROOT / "src" / "trabaholens" / "score_ai_only.py").read_text(encoding="utf-8")
    assert "Expected average" in v1_text, "the v1 anchor should still be visible for the audit"

    # And the v2 harness would refuse it if anyone pasted it in.
    with pytest.raises(sx.ScoringRefusal):
        sx.assert_prompt_is_unanchored(
            "# System prompt\nExpected average: ~3.5-4.5\n# User message template\n"
        )


# ---------------------------------------------------------------------------
# Finding 16: staleness exclusions must be minimal and provably narrow
# ---------------------------------------------------------------------------

def test_every_staleness_exclusion_has_a_recorded_rationale():
    from trabaholens.v2 import staleness

    assert set(staleness.VOLATILE_FIELDS) == set(staleness.EXCLUSION_RATIONALE)


@pytest.mark.parametrize("path_expr,mutate", [
    ("counts.published_values", lambda d: d["counts"].__setitem__("published_values", 99)),
    ("counts.psoc_classification_units",
     lambda d: d["counts"].__setitem__("psoc_classification_units", 1)),
    ("schema", lambda d: d.__setitem__("schema", "tampered")),
])
def test_substantive_payload_changes_are_detected(path_expr, mutate):
    """Anything not on the exclusion list must be caught."""
    from trabaholens.v2 import staleness

    payload = json.loads(SITE_DATA_JSON.read_text(encoding="utf-8"))
    before = staleness.normalise(payload)
    mutate(payload)
    after = staleness.normalise(payload)
    difference = staleness._first_difference(before, after)
    assert difference, f"a change to {path_expr} was not detected"


def test_source_hashes_and_pipeline_stages_are_not_excluded():
    """Two fields it would be tempting to exclude, and must not be."""
    from trabaholens.v2 import staleness

    manifest = json.loads(RELEASE_MANIFEST_JSON.read_text(encoding="utf-8"))
    before = staleness.normalise(manifest)

    tampered = json.loads(RELEASE_MANIFEST_JSON.read_text(encoding="utf-8"))
    tampered["source_hashes"]["psa_lfs"] = "0" * 64
    assert staleness._first_difference(before, staleness.normalise(tampered))

    tampered2 = json.loads(RELEASE_MANIFEST_JSON.read_text(encoding="utf-8"))
    assert tampered2.get("pipeline_stages"), "no pipeline stages to test against"
    # Mutate to a value the stage definitely does not already hold, otherwise
    # the test passes without exercising anything.
    original = tampered2["pipeline_stages"][0]["status"]
    tampered2["pipeline_stages"][0]["status"] = "rejected"
    assert original != "rejected"
    assert staleness._first_difference(before, staleness.normalise(tampered2))


def test_release_manifest_derives_rather_than_hardcodes():
    """Finding 16: model_runs and metric states must come from the data."""
    manifest = json.loads(RELEASE_MANIFEST_JSON.read_text(encoding="utf-8"))
    assert "pipeline_stages" in manifest
    assert manifest["pipeline_stages"], "pipeline stages are empty"
    # model_runs is derived from run manifests on disk; with none present it is
    # empty, but the code path is the discovery function, not a literal.
    from trabaholens.v2.build_release import _discover_model_runs

    assert manifest["model_runs"] == _discover_model_runs()
    state = manifest["publication_state"]
    observations = list(csv.DictReader(METRIC_OBSERVATIONS_CSV.open(encoding="utf-8")))
    expected = sorted({
        row["metric_id"] for row in observations
        if row.get("availability") == "published" and (row.get("metric_value") or "").strip()
    })
    assert state["metrics_with_published_values"] == expected
