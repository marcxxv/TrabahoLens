"""Parsers for the O*NET database text distribution.

O*NET ships as a zip of tab-separated files. These parsers read the four files
the exposure layer needs plus the version metadata, straight from the archive,
so the snapshot on disk stays the single hashed artifact.

Everything produced here describes **United States** occupations. Nothing in this
module maps to PSOC; that is the crosswalk stage's job, and its quality is
carried forward onto anything derived from these rows.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

from .base import (
    FormatValidationError,
    NormalisedRow,
    ParseResult,
    SourceParser,
    register,
)

#: Pinned release. See docs/data-licenses.md and the source registry for why a
#: specific release is pinned rather than "latest".
ONET_PINNED_RELEASE = "31.0"


def _open_member(archive: zipfile.ZipFile, wanted: str) -> io.StringIO:
    for member in archive.namelist():
        if Path(member).name.lower() == wanted.lower():
            return io.StringIO(archive.read(member).decode("utf-8-sig"))
    raise FormatValidationError(f"{wanted!r} not found in the O*NET archive")


def _read_tsv(handle: io.StringIO) -> list[dict[str, str]]:
    return list(csv.DictReader(handle, delimiter="\t"))


def _field(row: dict[str, str], *candidates: str) -> str:
    for candidate in candidates:
        for key in row:
            if key.strip().lower() == candidate.lower():
                return (row[key] or "").strip()
    for candidate in candidates:
        for key in row:
            if candidate.lower() in key.strip().lower():
                return (row[key] or "").strip()
    return ""


class _OnetArchiveParser(SourceParser):
    source_id = "onet"
    source_code_system = "O*NET-SOC"
    member: str = ""

    def validate_format(self, path: Path) -> None:
        if not path.exists():
            raise FormatValidationError(f"{path} does not exist")
        if not zipfile.is_zipfile(path):
            raise FormatValidationError(
                f"{path} is not a zip archive; expected the O*NET text database."
            )
        with zipfile.ZipFile(path) as archive:
            names = {Path(name).name.lower() for name in archive.namelist()}
            if self.member.lower() not in names:
                raise FormatValidationError(
                    f"{path.name} does not contain {self.member!r}. "
                    f"Present: {sorted(names)[:8]}…"
                )

    def release_from_path(self, path: Path) -> str:
        """Read the release out of the filename, e.g. db_31_0_text.zip -> 31.0."""
        match = re.search(r"db_(\d+)_(\d+)_text", path.name.lower())
        return f"{match.group(1)}.{match.group(2)}" if match else "unknown"


@register
class OnetOccupationParser(_OnetArchiveParser):
    parser_id = "onet_occupation_data"
    member = "Occupation Data.txt"

    def parse(self, path: Path) -> ParseResult:
        release = self.release_from_path(path)
        result = ParseResult(parser_id=self.parser_id, parser_version=self.parser_version)
        with zipfile.ZipFile(path) as archive:
            rows = _read_tsv(_open_member(archive, self.member))
        for index, row in enumerate(rows):
            code = _field(row, "O*NET-SOC Code")
            if not code:
                continue
            result.rows.append(
                NormalisedRow(
                    normalised_row_id=f"{self.parser_id}:{code}",
                    source_id=self.source_id,
                    source_table=self.member,
                    source_code=code,
                    source_code_system=self.source_code_system,
                    source_code_version=release,
                    source_label=_field(row, "Title"),
                    measure="occupation_description",
                    value=None,
                    unit="text",
                    reference_period=f"O*NET {release}",
                    geography="United States",
                    population_scope="US occupations",
                    notes=_field(row, "Description")[:2000],
                )
            )
            _ = index
        return result


@register
class OnetJobZoneParser(_OnetArchiveParser):
    parser_id = "onet_job_zones"
    member = "Job Zones.txt"

    def parse(self, path: Path) -> ParseResult:
        release = self.release_from_path(path)
        result = ParseResult(parser_id=self.parser_id, parser_version=self.parser_version)
        with zipfile.ZipFile(path) as archive:
            rows = _read_tsv(_open_member(archive, self.member))
        for row in rows:
            code = _field(row, "O*NET-SOC Code")
            zone = _field(row, "Job Zone")
            if not code or not zone:
                continue
            match = re.search(r"[1-5]", zone)
            if not match:
                result.warnings.append(f"{code}: unparseable Job Zone {zone!r}")
                continue
            result.rows.append(
                NormalisedRow(
                    normalised_row_id=f"{self.parser_id}:{code}",
                    source_id=self.source_id,
                    source_table=self.member,
                    source_code=code,
                    source_code_system=self.source_code_system,
                    source_code_version=release,
                    source_label="",
                    measure="job_zone",
                    value=float(match.group(0)),
                    unit="ordinal 1-5",
                    reference_period=f"O*NET {release}",
                    geography="United States",
                    population_scope="US occupations",
                )
            )
        return result


@register
class OnetTaskStatementParser(_OnetArchiveParser):
    parser_id = "onet_task_statements"
    member = "Task Statements.txt"

    def parse(self, path: Path) -> ParseResult:
        release = self.release_from_path(path)
        result = ParseResult(parser_id=self.parser_id, parser_version=self.parser_version)
        with zipfile.ZipFile(path) as archive:
            rows = _read_tsv(_open_member(archive, self.member))
        for row in rows:
            code = _field(row, "O*NET-SOC Code")
            task_id = _field(row, "Task ID")
            statement = _field(row, "Task")
            if not code or not task_id or not statement:
                continue
            result.rows.append(
                NormalisedRow(
                    normalised_row_id=f"{self.parser_id}:{task_id}",
                    source_id=self.source_id,
                    source_table=self.member,
                    source_code=code,
                    source_code_system=self.source_code_system,
                    source_code_version=release,
                    source_label=statement,
                    measure="task_statement",
                    value=None,
                    unit="text",
                    reference_period=f"O*NET {release}",
                    geography="United States",
                    population_scope="US occupations",
                    notes=f"task_id={task_id};task_type={_field(row, 'Task Type')}",
                )
            )
        return result


@register
class OnetTaskRatingsParser(_OnetArchiveParser):
    parser_id = "onet_task_ratings"
    member = "Task Ratings.txt"

    def parse(self, path: Path) -> ParseResult:
        release = self.release_from_path(path)
        result = ParseResult(parser_id=self.parser_id, parser_version=self.parser_version)
        with zipfile.ZipFile(path) as archive:
            rows = _read_tsv(_open_member(archive, self.member))
        for row in rows:
            code = _field(row, "O*NET-SOC Code")
            task_id = _field(row, "Task ID")
            scale = _field(row, "Scale ID")
            raw = _field(row, "Data Value")
            # IM = Importance. Frequency (FT) is a distribution across
            # categories and is not a single comparable number, so it is not
            # used as a weight.
            if scale.upper() != "IM" or not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                result.warnings.append(f"task {task_id}: unparseable importance {raw!r}")
                continue
            result.rows.append(
                NormalisedRow(
                    normalised_row_id=f"{self.parser_id}:{task_id}:IM",
                    source_id=self.source_id,
                    source_table=self.member,
                    source_code=code,
                    source_code_system=self.source_code_system,
                    source_code_version=release,
                    source_label="",
                    measure="task_importance",
                    value=value,
                    unit="O*NET importance scale 1-5",
                    reference_period=f"O*NET {release}",
                    geography="United States",
                    population_scope="US occupations",
                    notes=f"task_id={task_id}",
                )
            )
        return result
