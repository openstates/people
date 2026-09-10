#!/usr/bin/env python3
"""Fail when person files duplicate a given_name/family_name within one state.

Scoped for CI: a duplicate group only fails when the change under review created
it. A group whose every member already carried those names at the base revision
is pre-existing history, and the change that merely reformats one of its files
is not the one that introduced it - see check_role_dates.py's module docstring
for the same reasoning applied to role dates.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml
from _git_base import read_at_base

_PERSON_DIRS = ("executive", "legislature", "municipalities", "retired")


def normalize(value: object) -> str:
    """Normalize names for duplicate comparisons."""
    return " ".join(str(value or "").casefold().split())


def person_files(data_dir: Path, state: str) -> list[Path]:
    """Return all person YAML files for a state, excluding committees."""
    state_dir = data_dir / state
    files: list[Path] = []
    for person_dir in _PERSON_DIRS:
        directory = state_dir / person_dir
        if directory.exists():
            files.extend(sorted(directory.glob("*.yml")))
            files.extend(sorted(directory.glob("*.yaml")))
    return files


def person_file_state(data_dir: Path, path: Path) -> str | None:
    """Return a changed person file's state, or None when the path should be ignored."""
    if path.is_absolute():
        try:
            path = path.relative_to(Path.cwd())
        except ValueError:
            return None

    parts = path.parts
    data_parts = data_dir.parts
    if len(parts) != len(data_parts) + 3:
        return None
    if parts[: len(data_parts)] != data_parts:
        return None
    if parts[len(data_parts) + 1] not in _PERSON_DIRS:
        return None
    if path.suffix not in (".yml", ".yaml"):
        return None
    return parts[len(data_parts)]


def check_state(data_dir: Path, state: str) -> dict[tuple[str, str], list[Path]]:
    """Find duplicate person files in one state by normalized given and family name."""
    people: dict[tuple[str, str], list[Path]] = defaultdict(list)

    for path in person_files(data_dir, state):
        with path.open() as file:
            record = yaml.safe_load(file) or {}

        given_name = normalize(record.get("given_name"))
        family_name = normalize(record.get("family_name"))
        if not given_name or not family_name:
            continue

        people[(given_name, family_name)].append(path)

    return {key: paths for key, paths in sorted(people.items()) if len(paths) > 1}


def name_at_base(base_ref: str, path: Path) -> tuple[str, str] | None:
    """Return (given_name, family_name) for path at base_ref, or None if absent.

    Renames are followed, so a person moved from `legislature/` to `retired/` is
    still recognised as the same pre-existing record. None also covers an
    unparseable base revision: the group is then treated as new and reported,
    rather than silently dropped.
    """
    content = read_at_base(base_ref, path)
    if content is None:
        return None
    try:
        record = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return None
    return normalize(record.get("given_name")), normalize(record.get("family_name"))


def group_predates_change(
    base_ref: str, names: tuple[str, str], paths: list[Path]
) -> bool:
    """True if this duplicate group already existed at base_ref.

    A group exists at base when every member file was already there under these
    same names: that is enough to conclude the duplicate is pre-existing, and it
    reads only the group's own files rather than the whole state at base. A file
    the change adds, or renames onto a name that collides, has no such base entry
    and makes the group new.
    """
    return all(name_at_base(base_ref, path) == names for path in paths)


def changed_person_files(
    data_dir: Path, changed_files: list[str]
) -> dict[str, set[Path]]:
    """Group changed person files by state for CI-scoped duplicate checks."""
    changed_by_state: dict[str, set[Path]] = defaultdict(set)
    for changed_file in changed_files:
        path = Path(changed_file)
        state = person_file_state(data_dir, path)
        if state is None or not path.exists():
            continue
        changed_by_state[state].add(path)
    return changed_by_state


def report_changed_duplicates(
    data_dir: Path,
    changed_by_state: dict[str, set[Path]],
    base_ref: str | None,
) -> tuple[bool, int]:
    """Print duplicate groups this change introduced; count the ones it inherited.

    Historical duplicate groups are allowed unless this change touches one of
    them, and - given a base ref - unless this change is what created it.
    """
    found_duplicates = False
    preexisting = 0
    for state, changed_paths in sorted(changed_by_state.items()):
        duplicates = check_state(data_dir, state)
        for (given_name, family_name), paths in duplicates.items():
            if not changed_paths.intersection(paths):
                continue
            if base_ref and group_predates_change(
                base_ref, (given_name, family_name), paths
            ):
                preexisting += 1
                continue
            found_duplicates = True
            print(
                f"{state}: changed file violates duplicate person rule for "
                f"given_name={given_name!r}, family_name={family_name!r}"
            )
            for path in paths:
                marker = " (changed)" if path in changed_paths else ""
                print(f"  - {path}{marker}")
    return found_duplicates, preexisting


def main() -> int:
    """Run either a full-state duplicate scan or a changed-file-scoped CI scan."""
    parser = argparse.ArgumentParser(
        description=(
            "Fail if person files have duplicate given_name and family_name "
            "in the same state."
        )
    )
    parser.add_argument(
        "states", nargs="*", help="state abbreviations to check, e.g. ar ma"
    )
    parser.add_argument("--data-dir", default="data", type=Path)
    parser.add_argument(
        "--changed-files",
        nargs="*",
        help=(
            "limit failures to duplicate groups containing one of these "
            "changed person files"
        ),
    )
    parser.add_argument(
        "--base-ref",
        help=(
            "git ref the change is based on. Duplicate groups that already "
            "exist at this ref are reported as a pre-existing count instead of "
            "failing, so a change is only asked to answer for what it introduced."
        ),
    )
    args = parser.parse_args()

    found_duplicates = False
    preexisting = 0
    changed_by_state = changed_person_files(args.data_dir, args.changed_files or [])

    if args.changed_files is not None:
        if not changed_by_state:
            print("No changed person files to check")
            return 0
        found_duplicates, preexisting = report_changed_duplicates(
            args.data_dir, changed_by_state, args.base_ref
        )
    else:
        if not args.states:
            parser.error("provide states to check, or use --changed-files")

        for state in sorted(set(args.states)):
            duplicates = check_state(args.data_dir, state)
            for (given_name, family_name), paths in duplicates.items():
                found_duplicates = True
                print(
                    f"{state}: duplicate person records for given_name={given_name!r}, "
                    f"family_name={family_name!r}"
                )
                for path in paths:
                    print(f"  - {path}")

    if preexisting:
        print(
            f"note: {preexisting} duplicate person group(s) touched by this "
            f"change already exist at {args.base_ref} and are not this "
            "change's to fix."
        )

    if found_duplicates:
        print(
            "\nDuplicate person records found. A person is considered "
            "duplicate when given_name and family_name match within the "
            "same state. In CI, only duplicate groups containing changed "
            "person files fail.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
