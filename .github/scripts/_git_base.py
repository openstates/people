"""Read a file as it existed at a base revision, following renames.

Shared by check_role_dates.py and check_duplicate_people.py, which both report
only findings a change introduced and so need each changed file's base revision.

Resolving that by path alone is wrong for this repository: retiring a legislator
moves their file from `legislature/` to `retired/`, so `git show <base>:<new
path>` finds nothing, the file looks brand new, and every long-standing problem
in it is blamed on the change that merely moved it. NH's PR #4074 hit exactly
that - a moved file's decade-old malformed roles were reported as newly
introduced. So a path missing at the base is looked up again under its rename
source before being treated as new.
"""

from __future__ import annotations

import shutil
import subprocess
from functools import cache
from pathlib import Path

_RENAME_SIMILARITY = "50"


def _git() -> str:
    return shutil.which("git") or "git"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    # Fixed argv, no shell: every argument is a git ref or repo path supplied by
    # the caller (CI passes the event's base SHA), not free text.
    return subprocess.run(  # noqa: S603
        [_git(), *args],
        capture_output=True,
        text=True,
        check=False,
    )


@cache
def rename_sources(base_ref: str) -> dict[str, str]:
    """Map each renamed file's current path to the path it had at base_ref."""
    result = _run(
        [
            "diff",
            f"--find-renames={_RENAME_SIMILARITY}%",
            "--diff-filter=R",
            "--name-status",
            "-z",
            base_ref,
        ]
    )
    if result.returncode != 0:
        return {}
    # -z output is NUL-separated: status, old path, new path, status, ...
    fields = result.stdout.split("\0")
    renames: dict[str, str] = {}
    index = 0
    while index + 2 < len(fields):
        status, old, new = fields[index], fields[index + 1], fields[index + 2]
        if not status.startswith("R"):
            break
        renames[new] = old
        index += 3
    return renames


def read_at_base(base_ref: str, path: Path) -> str | None:
    """Return path's contents at base_ref, or None if it did not exist there.

    A file the change renamed is read from its pre-rename path, so moving a
    person into `retired/` does not make their whole history look new.
    """
    posix = path.as_posix()
    for candidate in (posix, rename_sources(base_ref).get(posix)):
        if candidate is None:
            continue
        result = _run(["show", f"{base_ref}:{candidate}"])
        if result.returncode == 0:
            return result.stdout
    return None
