"""Acquisition must distinguish dataset bytes from successful HTTP responses."""

from __future__ import annotations

import json
import zipfile

import pytest

from trabaholens.v2.acquire import _validate_download


def test_html_disguised_as_xlsx_is_rejected(tmp_path):
    path = tmp_path / "table.xlsx.part"
    path.write_text("<html>security verification</html>", encoding="utf-8")
    with pytest.raises(ValueError, match="HTML"):
        _validate_download(path, "xlsx", "text/html; charset=UTF-8")


def test_partial_zip_is_rejected(tmp_path):
    path = tmp_path / "onet.zip.part"
    path.write_bytes(b"PK\x03\x04truncated")
    with pytest.raises(ValueError, match="valid zip"):
        _validate_download(path, "zip", "application/zip")


def test_jsonstat1_wrapper_is_accepted(tmp_path):
    path = tmp_path / "lfs.json.part"
    path.write_text(json.dumps({"dataset": {"dimension": {}, "value": []}}), encoding="utf-8")
    _validate_download(path, "json", "application/json")


def test_real_xlsx_signature_is_required(tmp_path):
    path = tmp_path / "table.xlsx.part"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "types")
        archive.writestr("xl/workbook.xml", "workbook")
    _validate_download(
        path,
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
