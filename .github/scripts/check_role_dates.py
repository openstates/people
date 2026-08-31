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

One more, from openstates/issues#4040: a predecessor's file was repurposed for their
successor instead of retiring the predecessor and creating a new file. MS SD-21's
Barbara Blackmon left the seat in 2024 and her son Bradford Blackmon took it - the bot
overwrote her file in place (roles, offices, sources all became his) and left "Barbara
Blackmon" sitting in the new occupant's `other_names`, so a search for "Bradford
Blackmon" misses the file entirely and Barbara's own service history is gone. A
same-family-name-different-given-name entry in `other_names` (not an initial or
nickname of the current given_name) is the fingerprint: `other_names` should hold
aliases of the file's own occupant, not a different person who once held the seat.
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


def _normalized(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


_NICKNAME_PREFIX_LEN = 3
_MIN_GIVEN_TOKEN_LEN = 2
_MIN_NAME_PARTS = 2

# Classic English nicknames that share no letters with their formal name, so the
# prefix-overlap check below can't recognize them as the same person (Dave/David or
# Steve/Stephen share a prefix and are already handled without this table).
_CLASSIC_NICKNAMES = {
    frozenset({"bill", "william"}),
    frozenset({"billy", "william"}),
    frozenset({"jack", "john"}),
    frozenset({"bob", "robert"}),
    frozenset({"bobby", "robert"}),
    frozenset({"dick", "richard"}),
    frozenset({"rick", "richard"}),
    frozenset({"peggy", "margaret"}),
    frozenset({"peg", "margaret"}),
    frozenset({"ted", "edward"}),
    frozenset({"ned", "edward"}),
    frozenset({"hank", "henry"}),
    frozenset({"chuck", "charles"}),
    frozenset({"kate", "katherine"}),
    frozenset({"kate", "catherine"}),
    frozenset({"sally", "sarah"}),
    frozenset({"betty", "elizabeth"}),
    frozenset({"beth", "elizabeth"}),
    frozenset({"liz", "elizabeth"}),
    frozenset({"peggy", "margaret"}),
    frozenset({"polly", "mary"}),
    frozenset({"molly", "mary"}),
    frozenset({"jim", "james"}),
    frozenset({"jimmy", "james"}),
    frozenset({"don", "donald"}),
    frozenset({"ron", "ronald"}),
    frozenset({"tom", "thomas"}),
    frozenset({"tommy", "thomas"}),
    frozenset({"ken", "kenneth"}),
    frozenset({"fred", "frederick"}),
    frozenset({"ed", "edward"}),
    frozenset({"eddie", "edward"}),
    frozenset({"joe", "joseph"}),
    frozenset({"al", "albert"}),
    frozenset({"gus", "augustus"}),
    frozenset({"peg", "margaret"}),
}


def _plausible_same_person_nickname(given: str, other_given: str) -> bool:
    """True if the two given-name tokens are very likely nickname/legal-name variants
    of the same person, rather than two different people.

    Most English nicknames share a prefix with the formal name (Dave/David,
    Danny/Daniel, Patty/Patricia) - a shared prefix of 3+ letters is treated as the
    same person. A short table covers the common exceptions that share no letters
    (Bill/William, Jack/John, Bob/Robert). This is a heuristic, not a name database:
    it trades a few missed detections for not drowning the real #4040-style signal
    in nickname noise.
    """
    g, o = given.lower(), other_given.lower()
    if g == o:
        return True
    prefix_len = min(_NICKNAME_PREFIX_LEN, len(g), len(o))
    if prefix_len >= _NICKNAME_PREFIX_LEN and g[:prefix_len] == o[:prefix_len]:
        return True
    return frozenset({g, o}) in _CLASSIC_NICKNAMES


def _given_name_token(name: str, family: str) -> str | None:
    """Extract a plausible given-name token from a "First ... Last" other_names entry.

    Requires the entry to end with the record's own family_name exactly, so bare
    surnames ("Pilkington"), "Last, First" forms, and initials-only entries ("B.",
    "B.J.") are skipped - those are legitimate shorthand for the record's own name,
    not evidence of a different person.
    """
    if "," in name:
        return None
    parts = name.split()
    if len(parts) < _MIN_NAME_PARTS or parts[-1] != family:
        return None
    token = parts[0].rstrip(".")
    if len(token) <= _MIN_GIVEN_TOKEN_LEN or not token.isalpha():
        return None
    return token


def find_repurposed_identities(
    files: list[Path],
) -> list[tuple[Path, str, str]]:
    """Flag other_names entries that look like a *different* person's name.

    Catches openstates/issues#4040: a predecessor's file gets repurposed for their
    successor (same family, e.g. parent/child) instead of retiring the predecessor
    into their own file. other_names should hold aliases of the file's own occupant
    (nicknames, initials, maiden names) - a full given name that differs from the
    record's given_name while sharing its family_name is the fingerprint of a
    different person's identity left behind in the file, not a legitimate alias.
    """
    flagged: list[tuple[Path, str, str]] = []
    for path in files:
        with path.open() as f:
            record = yaml.safe_load(f) or {}
        given = (record.get("given_name") or "").strip()
        family = (record.get("family_name") or "").strip()
        if not given or not family:
            continue
        for other in record.get("other_names") or []:
            other_name = (other.get("name") or "").strip()
            token = _given_name_token(other_name, family)
            if not token or token.lower() == given.lower():
                continue
            # "Kerry (Bubba) Underwood" for given_name "Bubba", or 'Artis "A. J."
            # McCampbell' for given_name "A.J." - the record's own given_name shows
            # up inside the other_names string itself, so it's describing this same
            # person under a fuller/legal form, not a different individual.
            if _normalized(given) in _normalized(other_name):
                continue
            if _plausible_same_person_nickname(given, token):
                continue
            flagged.append((path, other_name, given))
    return flagged


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

    if args.changed_files is not None and integrity_targets:
        repurposed = find_repurposed_identities(integrity_targets)
        for path, other_name, given in sorted(repurposed, key=lambda r: str(r[0])):
            print(
                f"warning: {path} lists other_name {other_name!r}, a different given "
                f"name than this file's own {given!r} but sharing its family name - "
                "possible repurposed identity (see openstates/issues#4040). Verify "
                f"whether {other_name!r} is a distinct person (e.g. predecessor in "
                "the same seat) who needs their own retired/ file with their own "
                "service history, rather than an alias of the current occupant."
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
