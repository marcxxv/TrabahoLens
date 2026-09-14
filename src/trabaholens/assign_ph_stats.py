"""Assign Philippine wage, employment, and informality statistics."""

from __future__ import annotations

import json
from collections import defaultdict

from .pipeline_utils import (
    DERIVED_PH_OCCUPATIONS_JSON,
    DERIVED_PH_OCCUPATIONS_WITH_STATS_JSON,
    PH_SPECIFIC_OCCUPATIONS,
    PSOC_OFW_SHARE,
    category_from_soc_code,
    informal_share_for_category,
    load_current_occupations_map,
    make_onet_id,
    normalize_text,
    psoc_label,
    psoc_major_from_soc_code,
    size_multiplier_for_title,
    wage_for_occupation,
)


INPUT_JSON = DERIVED_PH_OCCUPATIONS_JSON
OUTPUT_JSON = DERIVED_PH_OCCUPATIONS_WITH_STATS_JSON

GROUP_TOTALS = {
    1: 1_200_000,
    2: 5_500_000,
    3: 3_200_000,
    4: 2_800_000,
    5: 11_000_000,
    6: 8_500_000,
    7: 4_200_000,
    8: 3_800_000,
    9: 10_500_000,
}

EDUCATION_LABELS = {
    1: "No formal education",
    2: "High school/Vocational",
    3: "Some college",
    4: "Bachelor's degree",
    5: "Post-graduate",
}


def load_source_records():
    with open(INPUT_JSON, encoding="utf-8") as file_handle:
        return json.load(file_handle)


def ph_specific_sources(records: list[dict]) -> dict[str, dict]:
    return {normalize_text(spec["title"]): spec for spec in PH_SPECIFIC_OCCUPATIONS}


def allocate_group_employment(records: list[dict], current_map: dict[str, dict], ph_specific_map: dict[str, dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["psoc_major"]].append(record)

    output: list[dict] = []
    for major in sorted(grouped):
        group_records = grouped[major]
        target_total = GROUP_TOTALS.get(major, 0)

        fixed = []
        variable = []
        for record in group_records:
            baseline = current_map.get(normalize_text(record["title"]))
            if baseline is None and record.get("is_ph_specific"):
                spec = ph_specific_map.get(normalize_text(record["title"]))
                if spec is not None:
                    baseline = current_map.get(normalize_text(spec.get("source_title", "")))

            if baseline and baseline.get("employment_estimate"):
                record["employment_estimate"] = int(baseline["employment_estimate"])
                fixed.append(record)
            else:
                variable.append(record)

        fixed_total = sum(int(item.get("employment_estimate") or 0) for item in fixed)
        if fixed_total > target_total and fixed_total > 0:
            scale = target_total / fixed_total
            scaled = 0
            for index, item in enumerate(fixed):
                if index == len(fixed) - 1:
                    item["employment_estimate"] = max(target_total - scaled, 0)
                else:
                    value = int(round(int(item["employment_estimate"]) * scale))
                    item["employment_estimate"] = value
                    scaled += value
            variable_budget = 0
        else:
            variable_budget = max(target_total - fixed_total, 0)

        if variable:
            weights = []
            for item in variable:
                weight = size_multiplier_for_title(item["title"])
                lower_title = item["title"].lower()
                if major == 2 and any(keyword in lower_title for keyword in ("nurse", "teacher", "doctor", "dentist", "pharmacist", "software", "computer", "data")):
                    weight *= 1.8
                if major == 5 and any(keyword in lower_title for keyword in ("cook", "food", "waiter", "server", "cleaner", "janitor", "hair", "beauty")):
                    weight *= 1.4
                if major == 6 and any(keyword in lower_title for keyword in ("farmer", "fish", "agric", "crop")):
                    weight *= 1.6
                if major == 7 and any(keyword in lower_title for keyword in ("construction", "carpenter", "plumber", "electrician", "welder", "mason")):
                    weight *= 1.6
                if major == 8 and any(keyword in lower_title for keyword in ("driver", "operator", "machine", "assembler", "pilot", "transport")):
                    weight *= 1.5
                weights.append(weight)

            total_weight = sum(weights)
            remaining = variable_budget
            for index, item in enumerate(variable):
                if total_weight <= 0:
                    share = 0
                elif index == len(variable) - 1:
                    share = remaining
                else:
                    share = int(round(variable_budget * weights[index] / total_weight))
                    remaining -= share
                item["employment_estimate"] = max(share, 0)

        output.extend(fixed)
        output.extend(variable)

    return output


def build_stats(records: list[dict], current_map: dict[str, dict], ph_specific_map: dict[str, dict]) -> list[dict]:
    assigned = allocate_group_employment(records, current_map, ph_specific_map)

    output: list[dict] = []
    for record in assigned:
        title = record["title"]
        soc_code = record["soc_code"]
        major = record["psoc_major"]
        category = category_from_soc_code(soc_code, title)
        if record.get("is_ph_specific"):
            category = ph_specific_map[normalize_text(title)]["category"]

        wage = wage_for_occupation(soc_code, title, category)
        informal_share = informal_share_for_category(category)
        ofw_share = PSOC_OFW_SHARE.get(major, 0.1)

        education_code = int(record.get("education_code") or 3)

        output.append(
            {
                "id": record["id"],
                "soc_code": soc_code,
                "title": title,
                "category": category,
                "employment_estimate": int(record["employment_estimate"]),
                "avg_monthly_wage_php": int(wage),
                "education_code": education_code,
                "education_label": EDUCATION_LABELS.get(education_code, "Some college"),
                "informal_share": round(float(informal_share), 2),
                "ofw_share": round(float(ofw_share), 2),
                "hiring_intensity": 50,
                "description": record["description"],
                "psoc_major": major,
                "psoc_label": psoc_label(major),
            }
        )

    return output


def print_group_summary(records: list[dict]) -> None:
    print("Group breakdown:")
    grouped: dict[int, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["psoc_major"]].append(record)

    for major in sorted(grouped):
        group_records = grouped[major]
        total_employment = sum(record["employment_estimate"] for record in group_records)
        avg_wage = sum(record["avg_monthly_wage_php"] for record in group_records) / len(group_records)
        print(
            f"  PSOC {major}: {len(group_records)} occupations | "
            f"employment={total_employment:,} | avg wage=₱{avg_wage:,.0f}"
        )


def _v1_main() -> None:
    records = load_source_records()
    current_map = load_current_occupations_map()
    ph_specific_map = ph_specific_sources(records)

    stats_records = build_stats(records, current_map, ph_specific_map)

    required_fields = (
        "id",
        "soc_code",
        "title",
        "category",
        "employment_estimate",
        "avg_monthly_wage_php",
        "education_code",
        "education_label",
        "informal_share",
        "ofw_share",
        "hiring_intensity",
        "description",
        "psoc_major",
        "psoc_label",
    )
    for record in stats_records:
        for field in required_fields:
            if record.get(field) is None:
                raise RuntimeError(f"Null value detected for {field} in {record.get('title')}")

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as file_handle:
        json.dump(stats_records, file_handle, ensure_ascii=False, indent=2)

    print(f"Wrote {len(stats_records)} occupations to {OUTPUT_JSON}")
    print_group_summary(stats_records)


_RETIRED = (
    "{name} is a TrabahoLens v1 module, retired by the credibility rebuild.\n"
    "It is kept readable because docs/audit/baseline-audit.md cites it line by\n"
    "line, but it must not run: it would regenerate values the audit found to be\n"
    "synthetic, constant-by-category or placeholder.\n"
    "See docs/migration-notes.md. Use the v2 pipeline: `make help`."
)


def main(*_args, **_kwargs):  # noqa: D401 - retired entry point
    raise SystemExit(_RETIRED.format(name=__name__))
