"""Importer for the PSA Philippine Standard Occupational Classification.

## Architecture decision: one canonical version with version-specific mappings

Two architectures were available (finding 4):

**A. Canonical "2022 Updates to the 2012 PSOC", with version-specific source
mappings.** One classification tree; each source declares which version it used
and is mapped onto the canonical tree through a correspondence table.

**B. Parallel versioned PSOC tables with an explicit correspondence table.**
Every version held side by side, observations attached to their own version.

**Chosen: A.** The reasons, so the choice can be argued with:

* The canonical tree is what a reader browses. Holding several parallel trees
  would make "which occupation am I looking at" a question the interface has to
  answer before it can show anything, and that is a worse default than one tree
  with declared provenance per observation.
* The 2022 Updates revise the 2012 structure rather than replace it, so a
  correspondence is expected to be mostly identity at major and sub-major level
  and to concentrate at minor and unit level — where B's duplication would cost
  most and buy least.
* B is strictly more faithful and remains the correct answer if the PSA volume
  turns out to renumber substantially. That contingency is recorded rather than
  assumed away.

Either way, the rule that matters is enforced in code: an observation whose
source used a version other than the canonical version is **refused** unless an
explicit correspondence is supplied; it is never silently renumbered.

## What this importer has actually done

Nothing, against the real source. The official classification API is identified
but requires a personal token, so the authoritative code list has not been
retrieved, hashed or parsed. The importer is implemented and fixture-tested;
the production classification rows remain the ISCO-08-aligned skeleton marked
``unverified_pending_source``.

Detailed groups are deliberately **not** transcribed from secondary material.
The PSA publication describes 10 major, 43 sub-major, 130 minor and 456 unit
groups; copying several hundred codes out of a third-party summary would
manufacture exactly the false precision this project exists to remove.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from ..pipeline import StageStatus
from .base import FormatValidationError, ParseResult, SourceParser, register

#: The version this project treats as canonical.
CANONICAL_PSOC_VERSION = "PSOC 2012 (2022 Updates)"

#: Structure the PSA publication describes. Used to check an import for
#: completeness, never to fabricate the rows themselves.
EXPECTED_STRUCTURE = {
    "psoc_major_group": 10,
    "psoc_sub_major_group": 43,
    "psoc_minor_group": 130,
    "psoc_unit_group": 456,
}

LEVEL_BY_CODE_LENGTH = {
    1: "psoc_major_group",
    2: "psoc_sub_major_group",
    3: "psoc_minor_group",
    4: "psoc_unit_group",
}


@dataclass
class PsocImportReport:
    version: str
    rows: list[dict]
    counts: dict[str, int]
    problems: list[str]
    complete: bool

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "counts": self.counts,
            "expected": EXPECTED_STRUCTURE,
            "complete": self.complete,
            "problems": self.problems,
            "row_count": len(self.rows),
        }


@register
class PsocVolumeParser(SourceParser):
    """Parse a PSOC code list into classification rows.

    Accepts the CSV/JSON export shapes PSA publishes for classification
    systems. The PDF volume is not parsed: a code list extracted from a PDF by
    heuristic is not a source of record, and a person should convert it to a
    tabular form that can be diffed.
    """

    parser_id = "psa_psoc_volume"
    source_id = "psa_psoc"
    source_code_system = "PSOC"
    status = StageStatus.FIXTURE_TESTED_ONLY

    REQUIRED_COLUMNS = {"code", "title"}

    def validate_format(self, path: Path) -> None:
        if not path.exists():
            raise FormatValidationError(f"{path} does not exist")
        if path.stat().st_size == 0:
            raise FormatValidationError(f"{path} is empty")
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            raise FormatValidationError(
                "The PSOC volume is distributed as a PDF. A code list extracted "
                "from a PDF by heuristic is not a source of record. Convert it to "
                "CSV or JSON, review the conversion, and import that."
            )
        if suffix == ".csv":
            with open(path, encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle), None)
            if not header:
                raise FormatValidationError(f"{path}: no header row")
            missing = self.REQUIRED_COLUMNS - {c.strip().lower() for c in header}
            if missing:
                raise FormatValidationError(
                    f"{path}: missing required columns {sorted(missing)}"
                )
        elif suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FormatValidationError(f"{path} is not valid JSON: {exc}") from exc
            if not isinstance(payload, list):
                raise FormatValidationError(f"{path}: expected a JSON array of code entries")
        else:
            raise FormatValidationError(
                f"{path}: unsupported extension {suffix!r}; expected .csv or .json"
            )

    def _entries(self, path: Path) -> list[dict]:
        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return [{k.strip().lower(): v for k, v in row.items()} for row in csv.DictReader(handle)]

    def parse(self, path: Path) -> ParseResult:
        """Not used for metric observations; see import_classification."""
        report = self.import_classification(path)
        result = ParseResult(parser_id=self.parser_id, parser_version=self.parser_version)
        result.warnings = report.problems
        return result

    def import_classification(self, path: Path, version: str | None = None) -> PsocImportReport:
        """Turn a code list into classification rows, checking the hierarchy."""
        self.validate_format(path)
        entries = self._entries(path)

        rows: list[dict] = []
        problems: list[str] = []
        counts = {level: 0 for level in EXPECTED_STRUCTURE}
        declared_version = version
        seen: set[str] = set()

        for index, entry in enumerate(entries):
            code = str(entry.get("code", "")).strip()
            title = str(entry.get("title", "")).strip()
            entry_version = str(entry.get("version", "") or "").strip()
            if entry_version:
                if declared_version and entry_version != declared_version:
                    problems.append(
                        f"row {index}: version {entry_version!r} differs from {declared_version!r}; "
                        "a single import must not mix classification versions"
                    )
                declared_version = declared_version or entry_version

            if not code:
                problems.append(f"row {index}: empty code")
                continue
            if not code.isdigit():
                problems.append(f"row {index}: non-numeric code {code!r}")
                continue
            if code in seen:
                problems.append(f"row {index}: duplicate code {code!r}")
                continue
            seen.add(code)

            level = LEVEL_BY_CODE_LENGTH.get(len(code))
            if level is None:
                problems.append(f"row {index}: code {code!r} has no recognised level (1-4 digits)")
                continue
            if not title:
                problems.append(f"row {index}: code {code!r} has no title")
                continue

            counts[level] += 1
            rows.append(
                {
                    "psoc_code": code,
                    "psoc_version": declared_version or CANONICAL_PSOC_VERSION,
                    "level": level,
                    "title": title,
                    "parent_psoc_code": code[:-1] if len(code) > 1 else "",
                    "psoc_major": code[0],
                    "psoc_major_label": "",
                    "isco08_code": str(entry.get("isco08_code", "") or ""),
                    "definition": str(entry.get("definition", "") or ""),
                    "verification_status": "verified_against_source",
                    "notes": "",
                }
            )

        # Orphan check: every non-major code must have its parent present.
        for row in rows:
            parent = row["parent_psoc_code"]
            if parent and parent not in seen:
                problems.append(
                    f"code {row['psoc_code']!r} has no parent {parent!r} in the import"
                )

        # Fill major labels once the majors are known.
        majors = {r["psoc_code"]: r["title"] for r in rows if r["level"] == "psoc_major_group"}
        for row in rows:
            row["psoc_major_label"] = majors.get(row["psoc_major"], "")

        complete = all(counts[level] == expected for level, expected in EXPECTED_STRUCTURE.items())
        if not complete:
            problems.append(
                "Import is not a complete PSOC: counts "
                f"{counts} against expected {EXPECTED_STRUCTURE}. A partial import may "
                "be used for testing but must not be published as the classification."
            )

        return PsocImportReport(
            version=declared_version or CANONICAL_PSOC_VERSION,
            rows=rows,
            counts=counts,
            problems=problems,
            complete=complete,
        )
