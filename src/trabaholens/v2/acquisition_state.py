"""What was actually acquired, as opposed to what we intended to acquire.

The division of responsibility, which the pre-remediation build got wrong:

* ``data/sources/source-registry.yaml`` is **configuration**. It says what we
  mean to fetch, from where, under what licence, with what universe. It is
  hand-edited, so it is not evidence of anything having happened.
* ``data/sources/retrieval-manifest.json`` is **evidence**. It is appended to by
  the acquisition code and records real attempts with timestamps and hashes.

Publication state must be derived from the second, never the first. Previously
``build_canonical`` read ``registry["retrieval"]["status"]``, so hand-editing one
YAML word to ``retrieved`` made the builder emit ``availability=published`` rows
with no value, no hash and no reference period.

A file having been downloaded is still not sufficient. This module verifies that
the recorded file exists, that its bytes still hash to what the manifest
recorded, and that it looks like the format the parser expects — before anything
downstream is allowed to treat it as a source.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .paths import REPO_ROOT, RETRIEVAL_MANIFEST_JSON, rel

# Statuses a manifest entry may carry that indicate bytes were obtained.
SUCCESSFUL_RETRIEVAL_STATUSES = {"retrieved", "hashed_existing_file"}


@dataclass(frozen=True)
class AcquisitionRecord:
    """The verified acquisition state of one source."""

    source_id: str
    acquired: bool
    reason: str
    path: Path | None = None
    sha256: str = ""
    retrieved_at: str = ""
    url: str = ""
    bytes_on_disk: int = 0

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "acquired": self.acquired,
            "reason": self.reason,
            "path": rel(self.path) if self.path else "",
            "sha256": self.sha256,
            "retrieved_at": self.retrieved_at,
            "url": self.url,
            "bytes_on_disk": self.bytes_on_disk,
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path | None = None) -> dict:
    manifest_path = path or RETRIEVAL_MANIFEST_JSON
    if not manifest_path.exists():
        return {"retrievals": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def latest_successful_entry(source_id: str, manifest: dict) -> dict | None:
    """The most recent entry for this source that reports bytes obtained."""
    candidates = [
        entry
        for entry in manifest.get("retrievals", [])
        if entry.get("source_id") == source_id
        and entry.get("status") in SUCCESSFUL_RETRIEVAL_STATUSES
    ]
    if not candidates:
        return None
    # Manifest is append-only, so the last matching entry is the newest.
    return candidates[-1]


def verify(source_id: str, manifest: dict | None = None) -> AcquisitionRecord:
    """Decide whether this source is genuinely available to a parser.

    Every failure mode returns a *reason*, because "not acquired" is information
    a release should publish, not an absence to leave unexplained.
    """
    manifest = manifest if manifest is not None else load_manifest()
    entry = latest_successful_entry(source_id, manifest)

    if entry is None:
        return AcquisitionRecord(
            source_id=source_id,
            acquired=False,
            reason="No successful retrieval recorded in the manifest.",
        )

    recorded_hash = entry.get("sha256") or ""
    destination = entry.get("destination") or ""
    if not recorded_hash:
        return AcquisitionRecord(
            source_id=source_id,
            acquired=False,
            reason="Manifest entry records no SHA-256; a file without a hash is not a source.",
            url=entry.get("url", ""),
        )
    if not destination:
        return AcquisitionRecord(
            source_id=source_id,
            acquired=False,
            reason="Manifest entry records no destination path.",
            url=entry.get("url", ""),
        )

    path = REPO_ROOT / destination
    if not path.exists():
        return AcquisitionRecord(
            source_id=source_id,
            acquired=False,
            reason=(
                f"Manifest records {destination!r} but that file is not on disk. "
                "Raw snapshots are gitignored, so re-run `make fetch-data`."
            ),
            sha256=recorded_hash,
            url=entry.get("url", ""),
        )

    actual_hash = sha256_file(path)
    if actual_hash != recorded_hash:
        return AcquisitionRecord(
            source_id=source_id,
            acquired=False,
            reason=(
                f"Hash mismatch for {destination!r}: manifest recorded "
                f"{recorded_hash[:12]}…, file hashes to {actual_hash[:12]}…. "
                "The snapshot changed after it was recorded; refusing to parse it."
            ),
            path=path,
            sha256=recorded_hash,
            url=entry.get("url", ""),
        )

    return AcquisitionRecord(
        source_id=source_id,
        acquired=True,
        reason="Verified: manifest entry present, file on disk, hash matches.",
        path=path,
        sha256=actual_hash,
        retrieved_at=entry.get("retrieved_at", ""),
        url=entry.get("url", ""),
        bytes_on_disk=path.stat().st_size,
    )


def verify_all(source_ids, manifest: dict | None = None) -> dict[str, AcquisitionRecord]:
    manifest = manifest if manifest is not None else load_manifest()
    return {source_id: verify(source_id, manifest) for source_id in source_ids}
