"""Download and parse the O*NET 30.2 text database."""

from __future__ import annotations

import csv
import json
import re
import zipfile
from pathlib import Path

import requests

from .pipeline_utils import (
    DERIVED_ONET_OCCUPATIONS_JSON,
    ONET_RELEASE,
    ONET_TEXT_ZIP_URL,
    RAW_ONET_DIR,
)


ZIP_NAME = f"db_{ONET_RELEASE.replace('.', '_')}_text.zip"
OUTPUT_JSON = DERIVED_ONET_OCCUPATIONS_JSON


def download_zip(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()

    with open(destination, "wb") as file_handle:
        for chunk in response.iter_content(chunk_size=1024 * 128):
            if chunk:
                file_handle.write(chunk)

    return destination


def extract_text_files(zip_path: Path, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    wanted = {
        "occupation data.txt": None,
        "education, training, and experience.txt": None,
        "job zones.txt": None,
    }

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            member_name = Path(member).name
            lower_name = member_name.lower()
            if lower_name in wanted:
                target_path = output_dir / member_name
                with archive.open(member) as source, open(target_path, "wb") as target:
                    target.write(source.read())
                wanted[lower_name] = target_path

    missing = [name for name, path in wanted.items() if path is None]
    if missing:
        raise RuntimeError(f"Missing expected O*NET files in archive: {', '.join(missing)}")

    return {name: path for name, path in wanted.items() if path is not None}


def detect_field(fieldnames: list[str], candidates: list[str]) -> str:
    for candidate in candidates:
        for field in fieldnames:
            if candidate.lower() == field.lower():
                return field
    for candidate in candidates:
        for field in fieldnames:
            if candidate.lower() in field.lower():
                return field
    raise KeyError(f"Could not find any of {candidates} in fields: {fieldnames}")


def parse_occupation_data(path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    with open(path, encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle, delimiter="\t")
        code_field = detect_field(list(reader.fieldnames or []), ["O*NET-SOC Code"])
        title_field = detect_field(list(reader.fieldnames or []), ["Title"])
        description_field = detect_field(list(reader.fieldnames or []), ["Description"])

        for row in reader:
            soc_code = (row.get(code_field) or "").strip()
            title = (row.get(title_field) or "").strip()
            description = (row.get(description_field) or "").strip()
            if not soc_code or not title:
                continue
            records.append(
                {
                    "soc_code": soc_code,
                    "title": title,
                    "description": description,
                }
            )

    return records


def parse_job_zones(path: Path) -> dict[str, int]:
    zones: dict[str, int] = {}
    with open(path, encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.DictReader(file_handle, delimiter="\t")
        code_field = detect_field(list(reader.fieldnames or []), ["O*NET-SOC Code"])
        zone_field = detect_field(list(reader.fieldnames or []), ["Job Zone"])

        for row in reader:
            soc_code = (row.get(code_field) or "").strip()
            zone_value = (row.get(zone_field) or "").strip()
            if not soc_code or not zone_value:
                continue
            match = re.search(r"[1-5]", zone_value)
            if not match:
                continue
            zones[soc_code] = int(match.group(0))

    return zones


def _v1_main() -> None:
    zip_path = RAW_ONET_DIR / ZIP_NAME
    print(f"Downloading O*NET text database {ONET_RELEASE}...")
    download_zip(ONET_TEXT_ZIP_URL, zip_path)

    files = extract_text_files(zip_path, RAW_ONET_DIR)
    occupation_data_path = files["occupation data.txt"]
    job_zone_path = files["job zones.txt"]

    occupations = parse_occupation_data(occupation_data_path)
    job_zones = parse_job_zones(job_zone_path)

    merged = []
    for occupation in occupations:
        merged.append(
            {
                **occupation,
                "education_code": job_zones.get(occupation["soc_code"]),
            }
        )

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as file_handle:
        json.dump(merged, file_handle, ensure_ascii=False, indent=2)

    print(f"Saved {occupation_data_path.name} and {job_zone_path.name} to {RAW_ONET_DIR}")
    print(f"Wrote {len(merged)} occupations to {OUTPUT_JSON}")


_RETIRED = (
    "{name} is a TrabahoLens v1 module, retired by the credibility rebuild.\n"
    "It is kept readable because docs/audit/baseline-audit.md cites it line by\n"
    "line, but it must not run: it would regenerate values the audit found to be\n"
    "synthetic, constant-by-category or placeholder.\n"
    "See docs/migration-notes.md. Use the v2 pipeline: `make help`."
)


def main(*_args, **_kwargs):  # noqa: D401 - retired entry point
    raise SystemExit(_RETIRED.format(name=__name__))
