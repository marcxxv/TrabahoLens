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

    assert payload["counts"]["occupations"] == len(occupations)
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
