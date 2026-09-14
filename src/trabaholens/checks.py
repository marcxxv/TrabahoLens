"""Fast local check: compile everything, then validate the release.

v1's version of this compiled the source and confirmed that three files shared
the same 173 titles. It passed on a dataset in which no published value was an
observation. It now runs the release validator, which tests the values rather
than their names.
"""

from __future__ import annotations

import compileall

from .pipeline_utils import REPO_ROOT
from .v2.validate import run_all


def main() -> None:
    targets = [REPO_ROOT / "src", REPO_ROOT / "scripts", REPO_ROOT / "tests"]
    failed = [str(path) for path in targets if not compileall.compile_dir(path, quiet=1)]
    if failed:
        raise RuntimeError(f"Compilation failed for: {', '.join(failed)}")

    failures = run_all()
    if failures:
        print(f"Release validation FAILED with {len(failures)} problem(s):\n")
        for failure in failures:
            print(f"  {failure}")
        raise SystemExit(1)

    print("Checks passed.")
