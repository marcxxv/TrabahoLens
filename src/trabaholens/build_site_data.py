"""Build `site/data.json` from the committed derived CSV and score cache."""

from __future__ import annotations

import json

from .pipeline_utils import SITE_DATA_JSON, ensure_parent_dir
from .validation import validate_scores_cover_titles


def _v1_main() -> None:
    rows, scores_list, missing_titles = validate_scores_cover_titles()
    scores = {entry["title"]: entry for entry in scores_list}

    if missing_titles:
        preview = "\n".join(f"  - {title}" for title in missing_titles[:10])
        raise RuntimeError(
            "Cannot build site data because some occupations do not have AI scores.\n"
            f"{preview}"
        )

    data = []
    for row in rows:
        title = row["title"]
        score = scores[title]
        soc_code = row.get("soc_code", "")
        data.append(
            {
                "title": title,
                "category": row["category"],
                "pay": int(float(row["avg_monthly_wage_php"])) if row["avg_monthly_wage_php"] else None,
                "jobs": int(float(row["employment_estimate"])) if row["employment_estimate"] else None,
                "outlook": int(float(row["hiring_intensity"])) if row["hiring_intensity"] else None,
                "outlook_desc": "Hiring intensity (0-100)",
                "education": int(row["education_code"]) if row["education_code"] else None,
                "exposure": score["exposure"],
                "exposure_rationale": score["rationale"],
                "primary_risk_vector": score["primary_risk_vector"],
                "ofw_share": float(row["ofw_share"]),
                "informal_share": float(row["informal_share"]),
                "psoc_major": int(row["psoc_major"]),
                "psoc_label": row["psoc_label"],
                "source": "ph_native" if soc_code.startswith("PH-") else "onet",
            }
        )

    ensure_parent_dir(SITE_DATA_JSON)
    with open(SITE_DATA_JSON, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, ensure_ascii=False, indent=2)

    total_jobs = sum(item["jobs"] for item in data if item["jobs"])
    print(f"Wrote {len(data)} occupations to {SITE_DATA_JSON}")
    print(f"Total jobs represented: {total_jobs:,}")


_RETIRED = (
    "{name} is a TrabahoLens v1 module, retired by the credibility rebuild.\n"
    "It is kept readable because docs/audit/baseline-audit.md cites it line by\n"
    "line, but it must not run: it would regenerate values the audit found to be\n"
    "synthetic, constant-by-category or placeholder.\n"
    "See docs/migration-notes.md. Use the v2 pipeline: `make help`."
)


def main(*_args, **_kwargs):  # noqa: D401 - retired entry point
    raise SystemExit(_RETIRED.format(name=__name__))
