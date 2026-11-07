"""Extract PSA's own task statements from the pinned PSOC workbook.

Why this is the task source, not O*NET:

The 2022 PSOC workbook publishes, for every unit group, a definition and a
lettered "Their tasks include:" list. These are Philippine official task
descriptions for the canonical classification itself, so they need no
US-to-Philippine crosswalk at all. The previous plan carried O*NET task
statements across a SOC-ISCO-PSOC chain, where every link loses precision and
each needed human review before any score could be trusted. Scoring PSA's own
text removes that entire failure mode.

What it cannot give: PSA does not rate task importance or frequency, so only an
unweighted occupation summary is possible. That limit is recorded on every row
rather than filled with O*NET weights from a different classification.

Unit groups whose entry has no task list (residual "not elsewhere classified"
groups and the armed forces) are reported as having no task evidence. They are
never given tasks borrowed from a neighbouring group.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from .paths import REPO_ROOT, ensure_parent, rel
from .sources.psoc_importer import CANONICAL_PSOC_VERSION, PSOC_WORKBOOK_SHA256

PSOC_WORKBOOK = REPO_ROOT / "data" / "raw" / "psa_psoc" / "psoc_2022_updates.xlsx"
TASKS_DIR = REPO_ROOT / "data" / "exposure" / "tasks"
TASKS_CSV = TASKS_DIR / "psoc_tasks.csv"
TASKS_REPORT_JSON = TASKS_DIR / "psoc_tasks_report.json"

#: Marks a task that comes from the canonical classification itself. There is
#: no crosswalk to review, so these values say so explicitly instead of
#: pretending a reviewed mapping exists.
NATIVE_CROSSWALK_ID = "PSOC-NATIVE"
NATIVE_NOT_APPLICABLE = "not_applicable_native_psoc"
OCCUPATION_SOURCE = "ph_psa_psoc_2012_2022_updates"

TASK_COLUMNS = [
    "task_id", "task_statement", "source_item_label", "psoc_code", "occupation_title",
    "occupation_source", "source_cell", "source_file_hash", "task_source_version",
    "onet_soc_code", "crosswalk_id", "crosswalk_match_type",
    "crosswalk_match_quality", "crosswalk_review_status", "task_importance",
]

_TASK_INTRO = re.compile(r"tasks include\s*:?\s*$", re.I)
_TASK_ITEM = re.compile(r"^\(?([a-z]{1,2})\)\s*(.+)$", re.S)
_SECTION_END = re.compile(r"^(examples?\b|some related|related occupations|note\b)", re.I)
_UNIT_CODE = re.compile(r"^\d{4}$")


class TaskExtractionError(ValueError):
    """The workbook no longer has the shape this extractor was reviewed against."""


def _clean_statement(text: str) -> str:
    # Remove list punctuation only. The wording is PSA's and is not paraphrased.
    text = re.sub(r"\s+", " ", text).strip()
    while not text.endswith("etc.") and re.search(r"(;\s*and|;|,\s*and|\.)$", text):
        text = re.sub(r"(;\s*and|;|,\s*and|\.)$", "", text).strip()
    return text


def extract_tasks(path: Path = PSOC_WORKBOOK) -> tuple[list[dict], dict]:
    """Return (task rows, report). Deterministic for a given workbook."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != PSOC_WORKBOOK_SHA256:
        raise TaskExtractionError(
            f"{rel(path)} does not match the reviewed PSOC workbook hash; review "
            "its layout before extracting tasks from it."
        )

    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    units: dict[str, dict] = {}
    try:
        for sheet in workbook:
            current: str | None = None
            state = ""
            for row_number, row in enumerate(sheet.iter_rows(max_col=6, values_only=True), 1):
                code_cells = [str(c).strip() if c is not None else "" for c in row[:3]]
                unit = code_cells[2]
                if _UNIT_CODE.match(unit):
                    if unit in units:
                        raise TaskExtractionError(f"{sheet.title}!C{row_number}: duplicate unit {unit}")
                    current, state = unit, "definition"
                    units[unit] = {
                        "title": str(row[3] or "").strip(),
                        "cell": f"{sheet.title}!C{row_number}",
                        "tasks": [],
                        "intro_seen": False,
                    }
                    continue
                if code_cells[0] or code_cells[1]:
                    current, state = None, ""
                    continue
                if current is None or row[3] is None:
                    continue
                text = str(row[3]).strip()
                if not text:
                    continue
                if _TASK_INTRO.search(text):
                    state = "tasks"
                    units[current]["intro_seen"] = True
                    continue
                if state != "tasks":
                    continue
                if _SECTION_END.match(text):
                    state = "done"
                    continue
                item = _TASK_ITEM.match(text)
                if item:
                    units[current]["tasks"].append(
                        (item.group(1), _clean_statement(item.group(2)), f"{sheet.title}!D{row_number}")
                    )
                elif units[current]["tasks"]:
                    # A wrapped line continues the previous lettered task.
                    letter, statement, cell = units[current]["tasks"][-1]
                    units[current]["tasks"][-1] = (letter, _clean_statement(f"{statement} {text}"), cell)
                else:
                    raise TaskExtractionError(
                        f"{sheet.title}!D{row_number}: unrecognised text before the first task item"
                    )
    finally:
        workbook.close()

    source_version = f"{CANONICAL_PSOC_VERSION}; sha256:{digest}"
    rows: list[dict] = []
    without_tasks: list[dict] = []
    anomalies: list[str] = []
    for code in sorted(units):
        unit = units[code]
        if not unit["tasks"]:
            without_tasks.append({"psoc_code": code, "title": unit["title"], "cell": unit["cell"],
                                  "task_intro_present": unit["intro_seen"]})
            continue
        # IDs follow list position, not PSA's letter: the source repeats some
        # letters (1113 has two "e)" items). The printed letter is kept verbatim
        # and the repetition is reported, not silently renumbered in the text.
        letters = [letter for letter, _, _ in unit["tasks"]]
        if len(set(letters)) != len(letters):
            anomalies.append(f"{code}: repeated item letters in source {letters}")
        for position, (letter, statement, cell) in enumerate(unit["tasks"], 1):
            if not statement:
                raise TaskExtractionError(f"{cell}: empty task statement")
            rows.append({
                "task_id": f"PSOC-{code}-{position:02d}",
                "task_statement": statement,
                "source_item_label": f"{letter})",
                "psoc_code": code,
                "occupation_title": unit["title"],
                "occupation_source": OCCUPATION_SOURCE,
                "source_cell": cell,
                "source_file_hash": digest,
                "task_source_version": source_version,
                "onet_soc_code": "",
                "crosswalk_id": NATIVE_CROSSWALK_ID,
                "crosswalk_match_type": NATIVE_NOT_APPLICABLE,
                "crosswalk_match_quality": NATIVE_NOT_APPLICABLE,
                "crosswalk_review_status": NATIVE_NOT_APPLICABLE,
                # PSA publishes no importance rating. Blank, never a default.
                "task_importance": "",
            })

    report = {
        "source_file": rel(path),
        "source_file_hash": digest,
        "task_source_version": source_version,
        "unit_groups": len(units),
        "unit_groups_with_tasks": len(units) - len(without_tasks),
        "task_statements": len(rows),
        "unit_groups_without_tasks": without_tasks,
        "source_anomalies": anomalies,
        "task_importance": "not published by PSA; occupation summaries are unweighted",
    }
    return rows, report


def write_tasks(rows: list[dict], report: dict) -> None:
    ensure_parent(TASKS_CSV)
    with open(TASKS_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TASK_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    TASKS_REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    rows, report = extract_tasks()
    write_tasks(rows, report)
    print(f"{rel(TASKS_CSV)}: {report['task_statements']} task statements from "
          f"{report['unit_groups_with_tasks']} of {report['unit_groups']} unit groups")
    print(f"unit groups without a PSA task list: {len(report['unit_groups_without_tasks'])} "
          "(reported, never filled)")


if __name__ == "__main__":
    main()
