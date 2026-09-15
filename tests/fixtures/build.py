"""Construct a populated source tree in a temporary directory.

Produces a manifest, hashed raw files and the parser inputs needed to drive the
whole path: manifest -> hash check -> parser -> normalised rows -> mapping ->
transformation -> canonical observations -> release -> payload.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

#: Obviously synthetic: three-digit employment counts for a whole major group.
LFS_ROWS = [
    # code, label, value, period, classification version
    ("1", "Managers", "111", "FIXTURE 2024 annual average", "PSOC 2012 (2022 Updates)"),
    ("2", "Professionals", "222", "FIXTURE 2024 annual average", "PSOC 2012 (2022 Updates)"),
    ("9", "Elementary Occupations", "999", "FIXTURE 2024 annual average", "PSOC 2012 (2022 Updates)"),
    # A publisher-suppressed cell: must reach the release as suppressed, not zero.
    ("0", "Armed Forces Occupations", "..", "FIXTURE 2024 annual average", "PSOC 2012 (2022 Updates)"),
]

SOF_ROWS = [
    ("1", "Managers", "10", "FIXTURE 2024 October round", "PSOC 2012 (2022 Updates)"),
    ("2", "Professionals", "30", "FIXTURE 2024 October round", "PSOC 2012 (2022 Updates)"),
    ("9", "Elementary Occupations", "60", "FIXTURE 2024 October round", "PSOC 2012 (2022 Updates)"),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_psa_csv(path: Path, rows) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["occupation_code", "occupation_label", "value", "reference_period",
         "classification_version", "geography", "notes"]
    )
    for code, label, value, period, version in rows:
        writer.writerow([code, label, value, period, version, "Philippines", "SYNTHETIC FIXTURE"])
    data = buffer.getvalue().encode("utf-8")
    path.write_bytes(data)
    return sha256_bytes(data)


def write_onet_zip(path: Path, release: str = "31.0") -> str:
    """A minimal O*NET text archive with the four files the project reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "db_31_0_text/Occupation Data.txt",
            "O*NET-SOC Code\tTitle\tDescription\n"
            "11-1011.00\tFIXTURE Chief Executives\tSynthetic description.\n"
            "25-1011.00\tFIXTURE Business Teachers\tSynthetic description.\n",
        )
        archive.writestr(
            "db_31_0_text/Job Zones.txt",
            "O*NET-SOC Code\tJob Zone\tDate\tDomain Source\n"
            "11-1011.00\t5\t08/2025\tAnalyst\n"
            "25-1011.00\t4\t08/2025\tAnalyst\n",
        )
        archive.writestr(
            "db_31_0_text/Task Statements.txt",
            "O*NET-SOC Code\tTask ID\tTask\tTask Type\tIncumbents Responding\tDate\tDomain Source\n"
            "11-1011.00\t8823\tFIXTURE: Prepare budget summaries.\tCore\t12\t08/2025\tAnalyst\n"
            "11-1011.00\t8824\tFIXTURE: Chair board meetings in person.\tCore\t12\t08/2025\tAnalyst\n",
        )
        archive.writestr(
            "db_31_0_text/Task Ratings.txt",
            "O*NET-SOC Code\tTask ID\tScale ID\tCategory\tData Value\tN\tDate\tDomain Source\n"
            "11-1011.00\t8823\tIM\t\t4.5\t12\t08/2025\tAnalyst\n"
            "11-1011.00\t8824\tIM\t\t3.0\t12\t08/2025\tAnalyst\n"
            "11-1011.00\t8823\tFT\t1\t10.0\t12\t08/2025\tAnalyst\n",
        )
    data = buffer.getvalue()
    path.write_bytes(data)
    _ = release
    return sha256_bytes(data)


def build_populated_sources(root: Path) -> dict:
    """Write raw fixture files and return a retrieval manifest describing them.

    ``root`` stands in for the repository root, so ``destination`` paths in the
    manifest are relative in exactly the way a real manifest's are.
    """
    raw = root / "data" / "raw"
    entries = []

    lfs_path = raw / "psa_lfs" / "lfs_employment_by_occupation_FIXTURE.csv"
    lfs_hash = write_psa_csv(lfs_path, LFS_ROWS)
    entries.append(
        {
            "source_id": "psa_lfs",
            "url": "https://openstat.psa.gov.ph/FIXTURE",
            "destination": str(lfs_path.relative_to(root).as_posix()),
            "attempted_at": "2026-01-01T00:00:00Z",
            "status": "retrieved",
            "bytes": lfs_path.stat().st_size,
            "sha256": lfs_hash,
            "retrieved_at": "2026-01-01T00:00:00Z",
        }
    )

    sof_path = raw / "psa_sof" / "sof_ofw_by_occupation_FIXTURE.csv"
    sof_hash = write_psa_csv(sof_path, SOF_ROWS)
    entries.append(
        {
            "source_id": "psa_sof",
            "url": "https://psa.gov.ph/FIXTURE",
            "destination": str(sof_path.relative_to(root).as_posix()),
            "attempted_at": "2026-01-01T00:00:00Z",
            "status": "retrieved",
            "bytes": sof_path.stat().st_size,
            "sha256": sof_hash,
            "retrieved_at": "2026-01-01T00:00:00Z",
        }
    )

    onet_path = raw / "onet" / "db_31_0_text.zip"
    onet_hash = write_onet_zip(onet_path)
    entries.append(
        {
            "source_id": "onet",
            "url": "https://www.onetcenter.org/dl_files/database/db_31_0_text.zip",
            "destination": str(onet_path.relative_to(root).as_posix()),
            "attempted_at": "2026-01-01T00:00:00Z",
            "status": "retrieved",
            "bytes": onet_path.stat().st_size,
            "sha256": onet_hash,
            "retrieved_at": "2026-01-01T00:00:00Z",
        }
    )

    # A source that was attempted and failed: must stay blocked downstream.
    entries.append(
        {
            "source_id": "psa_ows",
            "url": "https://psa.gov.ph/FIXTURE-ows",
            "destination": "data/raw/psa_ows/never_arrived.csv",
            "attempted_at": "2026-01-01T00:00:00Z",
            "status": "failed",
            "error": "ProxyError: FIXTURE",
            "sha256": None,
        }
    )

    manifest = {
        "schema": "trabaholens-retrieval-manifest/1",
        "description": "SYNTHETIC FIXTURE manifest for end-to-end pipeline tests.",
        "retrievals": entries,
    }
    manifest_path = root / "data" / "sources" / "retrieval-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
