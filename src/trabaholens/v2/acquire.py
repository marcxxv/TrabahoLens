"""Reproducible source acquisition with hashing and manifest recording.

Design rules, all of which exist because v1 broke them:

* Every retrieval records URL, HTTP status, retrieval timestamp, byte count and
  SHA-256. A file without a hash is not a source.
* A failed retrieval is recorded as a failure. It never silently leaves a stale
  file in place and reports success.
* Nothing here parses or transforms. Acquisition and interpretation are
  separate steps so a bad parse cannot be mistaken for a bad download.
* Raw files land in ``data/raw/`` which is gitignored. The manifest — URLs,
  hashes, timestamps — is committed, so a reviewer can verify that someone
  else's copy of a source is the same bytes.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from .paths import (
    RAW_DIR,
    RETRIEVAL_MANIFEST_JSON,
    SOURCE_REGISTRY_YAML,
    ensure_parent,
    rel,
)

MANIFEST_SCHEMA = "trabaholens-retrieval-manifest/1"


def load_registry() -> dict[str, Any]:
    return yaml.safe_load(SOURCE_REGISTRY_YAML.read_text(encoding="utf-8"))


def registry_by_id() -> dict[str, dict]:
    return {entry["source_id"]: entry for entry in load_registry()["sources"]}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_manifest() -> dict[str, Any]:
    if RETRIEVAL_MANIFEST_JSON.exists():
        return json.loads(RETRIEVAL_MANIFEST_JSON.read_text(encoding="utf-8"))
    return {
        "schema": MANIFEST_SCHEMA,
        "description": (
            "Every attempt to retrieve a registered source, successful or not. "
            "Failures are recorded so that an empty dataset is explained rather "
            "than merely empty."
        ),
        "retrievals": [],
    }


def write_manifest(manifest: dict[str, Any]) -> None:
    ensure_parent(RETRIEVAL_MANIFEST_JSON)
    RETRIEVAL_MANIFEST_JSON.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def record(entry: dict[str, Any]) -> None:
    manifest = load_manifest()
    manifest["retrievals"].append(entry)
    write_manifest(manifest)


def _validate_download(path: Path, expected_format: str, content_type: str) -> None:
    """Reject error pages, partial archives and mislabeled downloads.

    An HTTP 200 only proves that the server returned *something*. PSA's CDN,
    for example, can return an HTML bot-check page for an ``.xlsx`` URL. Such
    bytes must never become a successful source snapshot.
    """
    if path.stat().st_size == 0:
        raise ValueError("downloaded response is empty")
    if "text/html" in content_type.lower():
        raise ValueError("server returned HTML instead of the registered dataset")

    if expected_format == "json":
        with open(path, encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict) or not (
            "dimension" in payload or "dataset" in payload
        ):
            raise ValueError("response is JSON but not a PXWeb JSON-stat dataset")
    elif expected_format in {"zip", "xlsx"}:
        if not zipfile.is_zipfile(path):
            raise ValueError(f"response is not a valid {expected_format} archive")
        with zipfile.ZipFile(path) as archive:
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise ValueError(f"archive member {corrupt_member!r} failed CRC validation")
            if expected_format == "xlsx":
                names = set(archive.namelist())
                required = {"[Content_Types].xml", "xl/workbook.xml"}
                if not required.issubset(names):
                    raise ValueError("archive is not an XLSX workbook")


def fetch(
    source_id: str,
    url: str,
    destination: Path,
    timeout: int = 120,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    expected_format: str = "",
) -> dict[str, Any]:
    """Retrieve one URL, validate and hash it, recording the outcome either way."""
    entry: dict[str, Any] = {
        "source_id": source_id,
        "url": url,
        "destination": rel(destination),
        "attempted_at": now_iso(),
    }
    try:
        response = requests.request(
            method.upper(), url, json=json_body, stream=True, timeout=timeout
        )
        entry["http_status"] = response.status_code
        response.raise_for_status()

        ensure_parent(destination)
        partial = destination.with_name(destination.name + ".part")
        with open(partial, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 17):
                if chunk:
                    handle.write(chunk)
        content_type = response.headers.get("Content-Type", "")
        _validate_download(partial, expected_format, content_type)
        partial.replace(destination)

        entry.update(
            {
                "status": "retrieved",
                "bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
                "retrieved_at": now_iso(),
                "content_type": content_type,
                "last_modified": response.headers.get("Last-Modified", ""),
                "request_method": method.upper(),
                "expected_format": expected_format,
            }
        )
    except Exception as exc:
        partial = destination.with_name(destination.name + ".part")
        if partial.exists():
            partial.unlink()
        entry.update(
            {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "sha256": None,
            }
        )
    record(entry)
    return entry


def fetch_registered(source_id: str) -> dict[str, Any]:
    """Retrieve a source using the URL declared in the registry."""
    entry = registry_by_id().get(source_id)
    if entry is None:
        raise KeyError(
            f"{source_id!r} is not in {rel(SOURCE_REGISTRY_YAML)}. "
            "Register a source before acquiring it."
        )

    automated = entry.get("retrieval", {}).get("automated") or {}
    url = automated.get("url", "")
    if not url.startswith("http"):
        return {
            "source_id": source_id,
            "status": "no_automated_download",
            "manual_instruction": entry["retrieval"].get("manual_instruction", ""),
            "note": (
                "The registry declares no machine-retrievable URL for this "
                "source. Acquire it manually, then run `make validate-raw` to "
                "hash it into the manifest."
            ),
        }

    filename = automated.get("destination_filename") or Path(url).name
    destination = RAW_DIR / source_id / filename
    return fetch(
        source_id,
        url,
        destination,
        timeout=int(automated.get("timeout_seconds", 120)),
        method=automated.get("method", "GET"),
        json_body=automated.get("json_body"),
        expected_format=automated.get("expected_format", ""),
    )


def hash_existing_raw_files() -> list[dict[str, Any]]:
    """Hash whatever is already in data/raw/ and record it.

    This is the path for sources that must be downloaded by hand: a reviewer
    drops the file into data/raw/<source_id>/ and the manifest picks it up, so
    a manual acquisition is as traceable as an automated one.
    """
    recorded = []
    if not RAW_DIR.exists():
        return recorded
    for path in sorted(RAW_DIR.rglob("*")):
        if not path.is_file():
            continue
        source_id = path.relative_to(RAW_DIR).parts[0]
        entry = {
            "source_id": source_id,
            "url": "(manual acquisition)",
            "destination": rel(path),
            "attempted_at": now_iso(),
            "status": "hashed_existing_file",
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "retrieved_at": now_iso(),
        }
        record(entry)
        recorded.append(entry)
    return recorded


def main() -> None:
    """`make fetch-data`: attempt every registered source that declares a URL."""
    registry = load_registry()
    results = []
    for entry in registry["sources"]:
        source_id = entry["source_id"]
        status = entry["retrieval"]["status"]
        if status == "not_used":
            print(f"  {source_id}: skipped (registered as not used)")
            continue
        print(f"  {source_id}: attempting...", flush=True)
        result = fetch_registered(source_id)
        results.append(result)
        print(f"    -> {result['status']}" + (f" ({result.get('error','')})" if result.get("error") else ""))

    retrieved = [r for r in results if r.get("status") == "retrieved"]
    print(f"\nRetrieved {len(retrieved)} of {len(results)} attempted sources.")
    print(f"Manifest: {rel(RETRIEVAL_MANIFEST_JSON)}")
    if len(retrieved) < len(results):
        print(
            "\nSome sources were not retrieved. Their metrics stay marked "
            "blocked_pending_source in the release; nothing is substituted for "
            "them."
        )


if __name__ == "__main__":
    main()
