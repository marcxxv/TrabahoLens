"""Fetch Philippine labor datasets from the PSA PXWeb API into ignored raw storage."""

import json
from datetime import datetime, timezone

import requests

from .pipeline_utils import RAW_PSA_DIR

BASE_URL = "https://openstat.psa.gov.ph/PXWeb/api/v1/en"
TABLES = {
    "lfs_employment_by_occupation": "DB/DB__1B__LFS/0031B3AEPO0.px",
    "ows_wage_by_industry": "DB/DB__1B__OWS/0031B3E1030.px",
}
OUT_DIR = RAW_PSA_DIR


def endpoint(path):
    return f"{BASE_URL}/{path}"


def fetch_metadata(path):
    resp = requests.get(endpoint(path), timeout=60)
    resp.raise_for_status()
    return resp.json()


def build_all_query(metadata):
    query = []
    for var in metadata.get("variables", []):
        query.append(
            {
                "code": var["code"],
                "selection": {
                    "filter": "all",
                    "values": ["*"],
                },
            }
        )
    return {
        "query": query,
        "response": {"format": "json-stat2"},
    }


def fetch_data(path, payload):
    resp = requests.post(endpoint(path), json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)


def print_variable_codes(label, metadata):
    print(f"\n[{label}] variable codes:")
    for var in metadata.get("variables", []):
        values = var.get("values", [])
        value_count = len(values)
        sample = ", ".join(values[:5])
        if value_count > 5:
            sample += ", ..."
        print(f"- {var.get('code')}: {var.get('text')} ({value_count} values)")
        if sample:
            print(f"  sample codes: {sample}")


def _v1_main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for label, table_path in TABLES.items():
        print(f"Fetching metadata for {label}...")
        metadata = fetch_metadata(table_path)
        print_variable_codes(label, metadata)

        metadata_path = OUT_DIR / f"{label}_metadata_{run_ts}.json"
        save_json(metadata_path, metadata)
        print(f"Saved metadata: {metadata_path}")

        payload = build_all_query(metadata)
        query_path = OUT_DIR / f"{label}_query_{run_ts}.json"
        save_json(query_path, payload)
        print(f"Saved query payload: {query_path}")

        print(f"Fetching data for {label}...")
        data = fetch_data(table_path, payload)
        data_path = OUT_DIR / f"{label}_data_{run_ts}.json"
        save_json(data_path, data)
        print(f"Saved data: {data_path}")

    print("\nDone.")


_RETIRED = (
    "{name} is a TrabahoLens v1 module, retired by the credibility rebuild.\n"
    "It is kept readable because docs/audit/baseline-audit.md cites it line by\n"
    "line, but it must not run: it would regenerate values the audit found to be\n"
    "synthetic, constant-by-category or placeholder.\n"
    "See docs/migration-notes.md. Use the v2 pipeline: `make help`."
)


def main(*_args, **_kwargs):  # noqa: D401 - retired entry point
    raise SystemExit(_RETIRED.format(name=__name__))
