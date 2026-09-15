"""Are the committed generated artifacts what the committed inputs produce?

That is the question worth asking, and it is narrower than "did any byte
change". Some fields in a generated artifact are **build-time stamps**: the
commit the build ran at, and the timestamp it ran. They describe the act of
building, not its inputs.

`code_commit` in particular is self-referential — the manifest records HEAD, and
committing the manifest moves HEAD — so a plain `git diff --exit-code` after a
rebuild can never pass. A check that cannot pass teaches people to ignore it.

So this module rebuilds the artifacts and compares them with the declared
volatile fields normalised away. Everything else must match exactly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .paths import AUDIT_DIR, RELEASE_MANIFEST_JSON, REPO_ROOT, SITE_DATA_JSON, rel

PROFILE_JSON = AUDIT_DIR / "current-data-profile.json"

# Field names that record *when and where the build ran*, not what it consumed.
# Kept deliberately short: anything added here stops being checked, so a new
# entry needs a reason as good as self-reference.
VOLATILE_FIELDS = frozenset(
    {
        "code_commit",         # self-referential: committing the artifact changes it
        "repository_commit",   # same, in the audit profile
        "release_date",        # build-time stamp
        "generated_at",        # build-time stamp
    }
)

#: Reassessed under finding 16. Each exclusion was re-argued rather than
#: inherited:
#:
#: * ``code_commit`` / ``repository_commit`` — genuinely self-referential. The
#:   artifact records HEAD, and committing the artifact moves HEAD, so no value
#:   can be stable. Unavoidable.
#: * ``release_date`` / ``generated_at`` — wall-clock at build time. Excluded so
#:   `make check-stale` can run at any time; `make determinism` pins them and
#:   compares them byte for byte, so they are not unchecked overall.
#:
#: Candidates considered and NOT excluded, so they stay checked: every
#: ``sha256``, every ``source_versions`` entry, every ``pipeline_stages`` entry,
#: all counts, and every canonical table checksum. Substantive drift in any of
#: those is a staleness failure, and a test proves it.
EXCLUSION_RATIONALE = {
    "code_commit": "self-referential; committing the artifact changes it",
    "repository_commit": "self-referential; same reason",
    "release_date": "wall-clock build stamp; pinned and compared by make determinism",
    "generated_at": "wall-clock build stamp; pinned and compared by make determinism",
}

CHECKED_ARTIFACTS = (RELEASE_MANIFEST_JSON, SITE_DATA_JSON, PROFILE_JSON)


def normalise(value: Any) -> Any:
    """Recursively blank the volatile fields so only substance is compared."""
    if isinstance(value, dict):
        return {
            key: ("<volatile>" if key in VOLATILE_FIELDS else normalise(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalise(item) for item in value]
    return value


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _first_difference(left: Any, right: Any, trail: str = "") -> str | None:
    """Locate the first substantive difference, so the error names a field."""
    if type(left) is not type(right):
        return f"{trail or '<root>'}: type {type(left).__name__} vs {type(right).__name__}"
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left:
                return f"{trail}.{key}: missing from the committed artifact"
            if key not in right:
                return f"{trail}.{key}: present in the committed artifact but not in the rebuild"
            found = _first_difference(left[key], right[key], f"{trail}.{key}")
            if found:
                return found
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{trail}: {len(left)} items vs {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            found = _first_difference(a, b, f"{trail}[{index}]")
            if found:
                return found
        return None
    if left != right:
        return f"{trail or '<root>'}: {left!r} vs {right!r}"
    return None


def rebuild(frozen_time: str = "1970-01-01T00:00:00Z") -> None:
    """Regenerate the artifacts in place, at a pinned timestamp."""
    for script, args in (
        ("audit_baseline.py", []),
        ("build_canonical.py", []),
        ("build_release.py", ["--frozen-time", frozen_time]),
    ):
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / script), *args],
            cwd=REPO_ROOT, check=True, capture_output=True,
        )


def check() -> list[str]:
    """Compare the on-disk artifacts against a fresh rebuild. Empty means fresh.

    The working tree is restored byte for byte afterwards, from bytes captured
    here rather than from git — so running this never discards a legitimate
    uncommitted regeneration.
    """
    original: dict[Path, bytes] = {}
    for path in CHECKED_ARTIFACTS:
        if not path.exists():
            return [f"{rel(path)} does not exist; run `make all`"]
        original[path] = path.read_bytes()

    try:
        rebuild()
        problems = []
        for path in CHECKED_ARTIFACTS:
            before = normalise(json.loads(original[path].decode("utf-8")))
            difference = _first_difference(before, normalise(_load(path)))
            if difference:
                problems.append(f"{rel(path)} is stale at {difference}")
    finally:
        for path, data in original.items():
            path.write_bytes(data)
    return problems


def main() -> None:
    problems = check()
    if problems:
        print("Generated artifacts are stale:\n")
        for problem in problems:
            print(f"  {problem}")
        print("\nRun `make all` and commit the result.")
        raise SystemExit(1)
    print(
        "Generated artifacts match their inputs "
        f"(ignoring build-time stamps: {', '.join(sorted(VOLATILE_FIELDS))})."
    )


if __name__ == "__main__":
    main()
