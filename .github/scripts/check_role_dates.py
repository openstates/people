#!/usr/bin/env python3
"""Deterministic checks for role-date bugs the openstates-bot has shipped before.

Investigating PR #4038's review comments (see duplicates.md's "auto-merge-2026-08-27"
entry) found two bot defects that `os-people lint` cannot catch because they only look
wrong to something that knows the real-world facts or compares across files:

1. Dangling/duplicate role entries: the bot sometimes appends a new role instead of
   editing an existing one in place, producing either a second active role for a seat
   that already has one (ND: Mike Beltz), or a role whose end_date predates its own
   start_date (NH: Charlie St. Clair) - both nonsensical regardless of jurisdiction.
2. Batched resignation dates: when retiring several legislators found via the same news
   roundup, the bot has used one shared date for all of them instead of each person's
   own effective date (NY Gianaris, NC Hanig, and NH St. Clair were all incorrectly
   dated 2026-08-26 in the same batch; their real dates were 2026-08-07, 2026-08-24, and
   2026-08-22 respectively). No structural check can know which date is "true", but a
   date shared by unrelated people in different jurisdictions is a strong smell worth a
   human/agent double-checking against each person's own source.

Two more, from openstates/issues#1389 and #1390 (both traced to PR #3780,
"Retired Mike Beltz (lower 20), added Dave Rustebakke as replacement"):

3. Wrong incumbent retired in a multi-seat district: ND House district 20 seats two
   people (Beltz and Hagert). Only Hagert resigned; Rustebakke was his replacement. The
   bot matched "district 20" in a news item to *both* incumbents on file and retired
   both, erroneously removing Beltz from the dataset for months. A shared district
   between two people is never grounds to retire either of them - identity (name) must
   match the source describing the departure, not just the district number.
4. Successor already sitting elsewhere, old role never closed: IL Paul Jacobs was
   appointed from House district 118 to fill Senate district 59 (vacated by Fowler, who
   *is* correctly retired). The bot added the SD-59 vacancy but never touched Jacobs's
   own file - he kept an open-ended lower/118 role and never gained an upper/59 role, so
   the seat looked permanently vacant even though the successor already exists in the
   dataset under a different chamber/district.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml

_PERSON_DIRS = ("executive", "legislature", "municipalities", "retired")


def is_person_file(path: Path) -> bool:
    """True if path looks like a person YAML file (data/<state>/<person_dir>/*.yml)."""
    return path.suffix in (".yml", ".yaml") and any(
        part in _PERSON_DIRS for part in path.parts
    )


def person_files(data_dir: Path) -> list[Path]:
    """Return all person YAML files across every jurisdiction, excluding committees."""
    files: list[Path] = []
    if not data_dir.exists():
        return files
    for state_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        for person_dir in _PERSON_DIRS:
            directory = state_dir / person_dir
            if directory.exists():
                files.extend(sorted(directory.glob("*.yml")))
                files.extend(sorted(directory.glob("*.yaml")))
    return files


def check_role_integrity(record: dict) -> list[str]:
    """Flag roles with end_date before start_date, or exact-duplicate role entries."""
    problems: list[str] = []
    roles = record.get("roles") or []
    seen: dict[tuple, int] = {}

    for role in roles:
        start = role.get("start_date")
        end = role.get("end_date")
        if start and end and str(end) < str(start):
            problems.append(
                f"role has end_date {end} before start_date {start} "
                f"(district={role.get('district')!r}, type={role.get('type')!r})"
            )

        key = (role.get("type"), role.get("jurisdiction"), role.get("district"), start)
        seen[key] = seen.get(key, 0) + 1

    for (rtype, jurisdiction, district, start), count in seen.items():
        if count > 1:
            problems.append(
                f"{count} role entries share type={rtype!r}, "
                f"jurisdiction={jurisdiction!r}, district={district!r}, "
                f"start_date={start} - likely a duplicate entry rather than a "
                "real repeated term"
            )

    return problems


def find_same_seat_retirements(
    files: list[Path],
) -> dict[tuple, list[tuple[str, Path]]]:
    """Group newly-added end_dates by (jurisdiction, type, district) among files.

    Catches issue #1389: a multi-seat district (e.g. a state House district electing
    two members) had both incumbents retired in the same batch because a news item
    named the district, when only one of them had actually left. Two people sharing a
    seat number is normal for a multi-seat district; two people sharing a seat number
    *both being retired in the same change* is the smell - it means the district
    number was matched instead of the departing person's name/identity.
    """
    by_seat: dict[tuple, list[tuple[str, Path]]] = defaultdict(list)
    for path in files:
        with path.open() as f:
            record = yaml.safe_load(f) or {}
        name = f"{record.get('given_name', '')} {record.get('family_name', '')}".strip()
        for role in record.get("roles") or []:
            if role.get("end_date"):
                key = (role.get("jurisdiction"), role.get("type"), role.get("district"))
                by_seat[key].append((name, path))
    return {seat: entries for seat, entries in by_seat.items() if len(entries) > 1}


def find_shared_end_dates(
    files: list[Path],
) -> dict[str, list[tuple[str, Path]]]:
    """Group role end_dates by date, among only the given (changed) files.

    Deliberately scoped to changed files rather than the whole repo: fixed
    statutory term-end dates (e.g. a governor inauguration day) are legitimately
    shared by hundreds of unrelated people, so comparing against the full
    historical corpus is pure noise. The bug this catches - several unrelated
    people retired in the same batch under one shared date - only shows up when
    comparing people who changed together, e.g. in one people-merge run that
    bundles several jurisdictions' bot branches.
    """
    by_date: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for path in files:
        with path.open() as f:
            record = yaml.safe_load(f) or {}
        name = f"{record.get('given_name', '')} {record.get('family_name', '')}".strip()
        for role in record.get("roles") or []:
            end = role.get("end_date")
            if end:
                by_date[str(end)].append((name, path))
    return {date: entries for date, entries in by_date.items() if len(entries) > 1}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Catch role-date bugs seen from the openstates-bot: dangling/duplicate "
            "role entries, and resignation dates suspiciously shared across "
            "unrelated people (a sign a batch date was used instead of each "
            "person's own effective date)."
        )
    )
    parser.add_argument("--data-dir", default="data", type=Path)
    parser.add_argument(
        "--changed-files",
        nargs="*",
        help="limit the integrity check to these changed person files",
    )
    args = parser.parse_args()

    if args.changed_files is not None:
        integrity_targets = [
            Path(f)
            for f in args.changed_files
            if is_person_file(Path(f)) and Path(f).exists()
        ]
        if not integrity_targets:
            print("No changed person files to check")
            return 0
    else:
        integrity_targets = person_files(args.data_dir)

    found_problems = False

    for path in integrity_targets:
        with path.open() as f:
            record = yaml.safe_load(f) or {}
        for problem in check_role_integrity(record):
            found_problems = True
            print(f"{path}: {problem}")

    # Scoped to changed files only - see find_shared_end_dates' docstring for why
    # comparing against the whole repo is the wrong check (a seat like a US House
    # district has had many genuinely-unrelated retirees over the decades; only a
    # single batch of changed files makes a shared date/seat meaningful).
    if args.changed_files is not None and integrity_targets:
        shared = find_shared_end_dates(integrity_targets)
        for date, entries in sorted(shared.items()):
            names = ", ".join(f"{name} ({path})" for name, path in entries)
            print(
                f"warning: {len(entries)} people have a role end_date of {date}: "
                f"{names}\n"
                "  Verify each person's effective date individually against their "
                "own source - a shared date across unrelated people is often a "
                "batch/announcement date rather than each person's real one."
            )

        same_seat = find_same_seat_retirements(integrity_targets)
        for (jurisdiction, rtype, district), entries in sorted(
            same_seat.items(), key=lambda kv: str(kv[0])
        ):
            names = ", ".join(f"{name} ({path})" for name, path in entries)
            print(
                f"warning: {len(entries)} people retired for the same seat "
                f"(jurisdiction={jurisdiction!r}, type={rtype!r}, "
                f"district={district!r}): {names}\n"
                "  A multi-seat district can legitimately have two incumbents, "
                "but both being retired in the same change is a sign the "
                "district number was matched instead of the departing "
                "person's name - verify each one individually against a "
                "source naming them specifically before retiring more than "
                "one incumbent of the same seat at once."
            )

    if found_problems:
        print(
            "\nRole date integrity problems found (duplicate/dangling role entries).",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
