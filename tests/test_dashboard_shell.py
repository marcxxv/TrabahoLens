"""Pin the actual deployed styling, not a subjective claim of resemblance."""
import hashlib
from html.parser import HTMLParser
import re
import shutil
import subprocess

import pytest

from trabaholens.v2.paths import REPO_ROOT


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id":
                self.ids.append(value)


def test_deployed_css_is_preserved_verbatim():
    css = (REPO_ROOT / "site/dashboard.css").read_text()
    original = css.split("\n/* Evidence and keyboard additions;")[0]
    # Inline stylesheet retrieved from trabaho-lens.vercel.app on 2026-09-28.
    assert hashlib.sha256(original.encode()).hexdigest() == (
        "9da7fda58156d70cc91f95d9cb49db5fd3534d59edc4884b1cc362d276216794"
    )


def test_original_structural_hooks_and_script_targets_exist():
    html = (REPO_ROOT / "site/index.html").read_text()
    js = (REPO_ROOT / "site/dashboard.js").read_text()
    parsed = Elements()
    parsed.feed(html)
    assert len(parsed.ids) == len(set(parsed.ids)), "Duplicate HTML identifiers"
    required = {"wrapper", "header", "colorToggle", "industryFilter", "statsRow",
                "canvas", "tooltip", "riskOverlay", "riskPanel", "riskClose"}
    required.update(re.findall(r'\$\("([^"\n]+)"\)', js))
    assert required <= set(parsed.ids)
    assert all(f'id="block{i}"' in html for i in range(2, 9))
    assert 'role="dialog"' in html and 'inert' in html


def test_javascript_adapter_and_layout():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for JavaScript adapter tests")
    subprocess.run([node, "--check", "site/dashboard.js"], cwd=REPO_ROOT, check=True)
    subprocess.run([node, "--test", "tests/dashboard.test.cjs"], cwd=REPO_ROOT, check=True)
