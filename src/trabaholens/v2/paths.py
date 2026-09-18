"""Filesystem layout for the v2 pipeline."""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent.parent.parent

DATA_DIR = REPO_ROOT / "data"
CANONICAL_DIR = DATA_DIR / "canonical"
SOURCES_DIR = DATA_DIR / "sources"
RAW_DIR = DATA_DIR / "raw"
LEGACY_DIR = DATA_DIR / "legacy" / "v1"
EXPOSURE_DIR = DATA_DIR / "exposure"
EXPOSURE_RUNS_DIR = EXPOSURE_DIR / "runs"
EXPOSURE_RUBRIC_DIR = EXPOSURE_DIR / "rubric"
EXPOSURE_PROMPT_DIR = EXPOSURE_DIR / "prompts"
RELEASE_DIR = DATA_DIR / "release"

DOCS_DIR = REPO_ROOT / "docs"
AUDIT_DIR = DOCS_DIR / "audit"

SITE_DIR = REPO_ROOT / "site"
SITE_DATA_JSON = SITE_DIR / "data.json"
SITE_INDEX_HTML = SITE_DIR / "index.html"

# Canonical tables
CLASSIFICATIONS_CSV = CANONICAL_DIR / "classifications.csv"
OCCUPATIONS_CSV = CANONICAL_DIR / "occupations.csv"
METRIC_OBSERVATIONS_CSV = CANONICAL_DIR / "metric_observations.csv"
CROSSWALK_CSV = CANONICAL_DIR / "crosswalk_psoc_isco_soc.csv"
REVIEWED_PSOC_ONET_CROSSWALK_CSV = DATA_DIR / "reference" / "reviewed_psoc_onet_crosswalk.csv"
PSOC_VERSION_CORRESPONDENCE_CSV = DATA_DIR / "reference" / "psoc_2012_to_2022_major.csv"
TRANSFORMATIONS_CSV = CANONICAL_DIR / "transformations.csv"
MODEL_SCORES_CSV = CANONICAL_DIR / "model_scores.csv"

# Source governance
SOURCE_REGISTRY_YAML = SOURCES_DIR / "source-registry.yaml"
RETRIEVAL_MANIFEST_JSON = SOURCES_DIR / "retrieval-manifest.json"

# Release
RELEASE_MANIFEST_JSON = RELEASE_DIR / "manifest.json"

# Legacy artifacts (read-only inputs to the audit)
LEGACY_OCCUPATIONS_CSV = LEGACY_DIR / "occupations_ph.csv"
LEGACY_SCORES_JSON = LEGACY_DIR / "scores_ai_only.json"
LEGACY_SEED_JSON = LEGACY_DIR / "occupations_seed.json"
LEGACY_SITE_DATA_JSON = LEGACY_DIR / "site_data.json"


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def rel(path: Path) -> str:
    """Repository-relative POSIX path, for stable output across machines."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()
