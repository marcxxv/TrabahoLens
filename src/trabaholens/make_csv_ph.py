"""Build the derived CSV used by scoring and the static site."""

from __future__ import annotations

import csv
import json

from .pipeline_utils import (
    DERIVED_OCCUPATIONS_CSV,
    DERIVED_PH_OCCUPATIONS_WITH_STATS_JSON,
    ensure_parent_dir,
)
from .validation import require_file


FIELDNAMES = [
    "id",
    "soc_code",
    "title",
    "psoc_major",
    "psoc_label",
    "category",
    "employment_estimate",
    "avg_monthly_wage_php",
    "education_code",
    "education_label",
    "informal_share",
    "ofw_share",
    "hiring_intensity",
    "description",
]

def _v1_main() -> None:
    require_file(DERIVED_PH_OCCUPATIONS_WITH_STATS_JSON, "Stats JSON")
    with open(DERIVED_PH_OCCUPATIONS_WITH_STATS_JSON, encoding="utf-8") as file_handle:
        occupations = json.load(file_handle)

    rows = []
    for occ in occupations:
        rows.append({field: occ[field] for field in FIELDNAMES})

    ensure_parent_dir(DERIVED_OCCUPATIONS_CSV)
    with open(DERIVED_OCCUPATIONS_CSV, "w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {DERIVED_OCCUPATIONS_CSV}")
    if rows:
        print(f"Sample: {rows[0]['id']} | {rows[0]['title']} | {rows[0]['avg_monthly_wage_php']}")


_RETIRED = (
    "{name} is a TrabahoLens v1 module, retired by the credibility rebuild.\n"
    "It is kept readable because docs/audit/baseline-audit.md cites it line by\n"
    "line, but it must not run: it would regenerate values the audit found to be\n"
    "synthetic, constant-by-category or placeholder.\n"
    "See docs/migration-notes.md. Use the v2 pipeline: `make help`."
)


def main(*_args, **_kwargs):  # noqa: D401 - retired entry point
    raise SystemExit(_RETIRED.format(name=__name__))
