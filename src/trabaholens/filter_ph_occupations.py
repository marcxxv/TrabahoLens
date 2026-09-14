"""Filter O*NET occupations down to Philippines-relevant records."""

from __future__ import annotations

import json

from .pipeline_utils import (
    CANONICAL_OCCUPATIONS_JSON,
    DERIVED_ONET_OCCUPATIONS_JSON,
    DERIVED_PH_OCCUPATIONS_JSON,
    PH_SPECIFIC_OCCUPATIONS,
    ensure_parent_dir,
    is_us_specific_title,
    make_onet_id,
    normalize_text,
    psoc_label,
    psoc_major_from_soc_code,
)


INPUT_JSON = DERIVED_ONET_OCCUPATIONS_JSON
CURRENT_OCCUPATIONS_JSON = CANONICAL_OCCUPATIONS_JSON
OUTPUT_JSON = DERIVED_PH_OCCUPATIONS_JSON

GROUP_LIMITS = {
    1: 12,
    2: 55,
    3: 18,
    4: 12,
    5: 20,
    6: 15,
    7: 18,
    8: 15,
}

BASE_GROUP_PRIORITY = {
    1: 80,
    2: 75,
    3: 70,
    4: 60,
    5: 65,
    6: 68,
    7: 72,
    8: 66,
}

KEYWORD_BONUSES = [
    ("nurse", 40),
    ("teacher", 35),
    ("doctor", 30),
    ("dentist", 30),
    ("pharmacist", 28),
    ("therapist", 28),
    ("counselor", 25),
    ("social worker", 25),
    ("account", 24),
    ("finance", 22),
    ("software", 30),
    ("computer", 25),
    ("developer", 25),
    ("programmer", 25),
    ("engineer", 24),
    ("architect", 20),
    ("manager", 22),
    ("supervisor", 20),
    ("director", 20),
    ("clerk", 20),
    ("secretary", 18),
    ("cashier", 18),
    ("sales", 18),
    ("driver", 22),
    ("operator", 18),
    ("mechanic", 18),
    ("carpenter", 18),
    ("electrician", 18),
    ("plumber", 18),
    ("weld", 18),
    ("cook", 18),
    ("food", 18),
    ("cleaner", 16),
    ("security", 16),
    ("farmer", 18),
    ("fish", 18),
    ("laborer", 16),
    ("care", 16),
    ("hair", 14),
    ("beauty", 14),
    ("repair", 14),
    ("maintenance", 12),
]

LOW_VALUE_KEYWORDS = (
    "mathematic",
    "statistic",
    "astronom",
    "nuclear",
    "subway",
    "postal service",
    "gaming",
    "logging equipment",
    "petroleum",
)


def load_current_by_title() -> dict[str, dict]:
    with open(CURRENT_OCCUPATIONS_JSON, encoding="utf-8") as file_handle:
        occupations = json.load(file_handle)
    return {normalize_text(occupation["title"]): occupation for occupation in occupations}


def occupation_priority(occupation: dict) -> int:
    title = occupation["title"].lower()
    major = psoc_major_from_soc_code(occupation["soc_code"])
    score = BASE_GROUP_PRIORITY.get(major or 0, 0)

    if is_us_specific_title(title):
        return -1000

    if any(keyword in title for keyword in LOW_VALUE_KEYWORDS):
        score -= 40

    for keyword, bonus in KEYWORD_BONUSES:
        if keyword in title:
            score += bonus

    if major == 2 and any(keyword in title for keyword in ("nurse", "teacher", "doctor", "dentist", "pharmacist", "software", "computer", "data")):
        score += 20
    if major == 5 and any(keyword in title for keyword in ("cook", "food", "waiter", "server", "cleaner", "janitor", "hair", "beauty")):
        score += 14
    if major == 6 and any(keyword in title for keyword in ("farmer", "fish", "agric", "crop")):
        score += 16
    if major == 7 and any(keyword in title for keyword in ("construction", "carpenter", "plumber", "electrician", "welder", "mason")):
        score += 12
    if major == 8 and any(keyword in title for keyword in ("driver", "operator", "machine", "assembler", "pilot", "transport")):
        score += 12

    return score


def include_occupation(occupation: dict) -> bool:
    major = psoc_major_from_soc_code(occupation["soc_code"])
    if major not in GROUP_LIMITS:
        return False
    if is_us_specific_title(occupation["title"]):
        return False
    if any(keyword in occupation["title"].lower() for keyword in LOW_VALUE_KEYWORDS):
        return False
    return True


def build_ph_specific_records(current_by_title: dict[str, dict]) -> list[dict]:
    records = []
    for spec in PH_SPECIFIC_OCCUPATIONS:
        source_record = current_by_title.get(normalize_text(spec["source_title"]))
        description = ""
        education_code = 3
        if source_record:
            description = source_record.get("description", "")
            education_code = int(source_record.get("education_code") or education_code)
        records.append(
            {
                "id": spec["id"],
                "soc_code": spec["soc_code"],
                "title": spec["title"],
                "description": description,
                "education_code": education_code,
                "psoc_major": spec["psoc_major"],
                "psoc_label": psoc_label(spec["psoc_major"]),
                "is_ph_specific": True,
            }
        )
    return records


def _v1_main() -> None:
    with open(INPUT_JSON, encoding="utf-8") as file_handle:
        onet_occupations = json.load(file_handle)

    current_by_title = load_current_by_title()

    selected_by_group: dict[int, list[dict]] = {major: [] for major in GROUP_LIMITS}
    for occupation in onet_occupations:
        if not include_occupation(occupation):
            continue
        major = psoc_major_from_soc_code(occupation["soc_code"])
        if major is None:
            continue
        selected_by_group.setdefault(major, []).append(occupation)

    output: list[dict] = []

    for major in sorted(GROUP_LIMITS):
        candidates = selected_by_group.get(major, [])
        candidates.sort(key=lambda item: (-occupation_priority(item), item["title"]))
        chosen = candidates[: GROUP_LIMITS[major]]

        for occupation in chosen:
            output.append(
                {
                    "id": make_onet_id(occupation["soc_code"]),
                    "soc_code": occupation["soc_code"],
                    "title": occupation["title"],
                    "description": occupation["description"],
                    "education_code": occupation.get("education_code") or 3,
                    "psoc_major": major,
                    "psoc_label": psoc_label(major),
                    "is_ph_specific": False,
                }
            )

    output.extend(build_ph_specific_records(current_by_title))

    deduped = {}
    for record in output:
        deduped[record["soc_code"]] = record

    final_records = sorted(deduped.values(), key=lambda item: (item["psoc_major"], item["title"]))

    ensure_parent_dir(OUTPUT_JSON)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as file_handle:
        json.dump(final_records, file_handle, ensure_ascii=False, indent=2)

    print(f"Wrote {len(final_records)} occupations to {OUTPUT_JSON}")
    print("PSOC counts:")
    for major in sorted(GROUP_LIMITS):
        count = sum(1 for record in final_records if record["psoc_major"] == major)
        print(f"  PSOC {major}: {count}")
    ph_count = sum(1 for record in final_records if record["is_ph_specific"])
    print(f"PH-specific occupations: {ph_count}")


_RETIRED = (
    "{name} is a TrabahoLens v1 module, retired by the credibility rebuild.\n"
    "It is kept readable because docs/audit/baseline-audit.md cites it line by\n"
    "line, but it must not run: it would regenerate values the audit found to be\n"
    "synthetic, constant-by-category or placeholder.\n"
    "See docs/migration-notes.md. Use the v2 pipeline: `make help`."
)


def main(*_args, **_kwargs):  # noqa: D401 - retired entry point
    raise SystemExit(_RETIRED.format(name=__name__))
