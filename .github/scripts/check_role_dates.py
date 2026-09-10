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

Two more, found while combining ten states' worth of executive-record fixes
(openstates/people#4045): the same shapes kept recurring across unrelated states'
governor/AG/lt-governor/SoS files, which `os-people lint` doesn't catch because
neither one is a schema violation:

7. Role missing `start_date`: e.g. GA's Brad Raffensperger (secretary of state) and
   AZ's Adrian Fontes (secretary of state) both had a role with an `end_date` but no
   `start_date`, leaving the term's boundary undefined.
8. A person filed under `executive/` whose every role has already ended: e.g. DE's
   John Carney was still in `executive/` with his governor role's `end_date` in the
   past, well after Matt Meyer's inauguration - he belonged in `retired/`.

Every check above describes a *bot mistake being introduced*, so the check only
reports a finding the change under review actually introduced. Given `--base-ref`,
the same analysis runs twice - once over the base revision of the changed files,
once over the working-tree revision - and only findings absent from the base are
reported. Without that, a PR that merely reformats or re-sorts a file (the bot
rewrites `'2019-01-14'` as `2019-01-14` and re-sorts `links:`, changing no data)
inherits every long-standing problem in every file it happens to touch, and its
author is asked to fix history they did not write. Pre-existing findings are
counted in a single summary line instead, and never block.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import yaml
from _git_base import read_at_base

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


def check_missing_start_date(record: dict) -> list[str]:
    """Flag roles that have an end_date but no start_date.

    A role's term boundary is undefined without a start_date, and this has
    shown up repeatedly across unrelated states' executive records (GA's
    Raffensperger, AZ's Fontes) rather than being a one-off typo.
    """
    return [
        f"role has end_date {role['end_date']} but no start_date "
        f"(district={role.get('district')!r}, type={role.get('type')!r})"
        for role in record.get("roles") or []
        if role.get("end_date") and not role.get("start_date")
    ]


def _person_name(record: dict) -> str:
    given = record.get("given_name", "")
    family = record.get("family_name", "")
    return f"{given} {family}".strip()


def find_stale_executive_persons(
    records: dict[Path, dict],
) -> list[tuple[str, Path, str]]:
    """Flag executive/ files whose every role has already ended.

    Catches DE's John Carney: still filed under executive/ with his governor
    role's end_date in the past. A person whose most recent role has already
    ended belongs in retired/, not executive/.
    """
    today = str(datetime.date.today())
    flagged: list[tuple[str, Path, str]] = []
    for path, record in records.items():
        if "executive" not in path.parts:
            continue
        roles = record.get("roles") or []
        end_dates = [str(r["end_date"]) for r in roles if r.get("end_date")]
        if roles and end_dates and max(end_dates) < today:
            flagged.append((_person_name(record), path, max(end_dates)))
    return flagged


def find_same_seat_retirements(
    records: dict[Path, dict],
) -> dict[tuple, list[tuple[str, Path]]]:
    """Group ended roles by (jurisdiction, type, district) among the given files.

    Catches issue #1389: a multi-seat district (e.g. a state House district electing
    two members) had both incumbents retired in the same batch because a news item
    named the district, when only one of them had actually left. Two people sharing a
    seat number is normal for a multi-seat district; two people sharing a seat number
    *both being retired in the same change* is the smell - it means the district
    number was matched instead of the departing person's name/identity.

    One person legitimately holds the same seat across consecutive terms, which is
    two ended roles for one seat in one file and not this bug at all, so each person
    counts once per seat.
    """
    by_seat: dict[tuple, dict[str, tuple[str, Path]]] = defaultdict(dict)
    for path, record in records.items():
        person = str(record.get("id") or path)
        name = _person_name(record)
        for role in record.get("roles") or []:
            if role.get("end_date"):
                key = (role.get("jurisdiction"), role.get("type"), role.get("district"))
                by_seat[key][person] = (name, path)
    return {
        seat: sorted(people.values(), key=lambda entry: str(entry[1]))
        for seat, people in by_seat.items()
        if len(people) > 1
    }


def find_shared_end_dates(
    records: dict[Path, dict],
) -> dict[str, list[tuple[str, Path]]]:
    """Group role end_dates by date, among only the given (changed) files.

    Deliberately scoped to changed files rather than the whole repo: fixed
    statutory term-end dates (e.g. a governor inauguration day) are legitimately
    shared by hundreds of unrelated people, so comparing against the full
    historical corpus is pure noise. The bug this catches - several unrelated
    people retired in the same batch under one shared date - only shows up when
    comparing people who changed together, e.g. in one people-merge run that
    bundles several jurisdictions' bot branches.

    Even within one change, a date already on file for both people is not a batch
    date this change invented; --base-ref filters those out (see module docstring).

    Placeholder end_dates are skipped: data/us uses 2100-01-01 to mean "no known
    end", so every congressional file added shares it, and none of them describes
    a resignation at all.
    """
    # ~10 years out, in days so a leap day can't make this raise.
    horizon = str(datetime.date.today() + datetime.timedelta(days=3653))
    by_date: dict[str, dict[str, tuple[str, Path]]] = defaultdict(dict)
    for path, record in records.items():
        person = str(record.get("id") or path)
        name = _person_name(record)
        for role in record.get("roles") or []:
            end = role.get("end_date")
            if end and str(end) < horizon:
                by_date[str(end)][person] = (name, path)
    return {
        date: sorted(people.values(), key=lambda entry: str(entry[1]))
        for date, people in by_date.items()
        if len(people) > 1
    }


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
    records: dict[Path, dict],
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
    for path, record in records.items():
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


def load_record(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_records(paths: list[Path]) -> dict[Path, dict]:
    return {path: load_record(path) for path in paths}


def load_base_records(base_ref: str, paths: list[Path]) -> dict[Path, dict]:
    """Load each path as it exists at base_ref, skipping files added by the change.

    A file the change adds has no base revision, so every finding in it is new and
    correctly reported. An unreadable base revision is treated the same way: the
    check falls back to reporting the finding rather than silently dropping it.
    Renames are followed, so retiring a person - which moves their file from
    `legislature/` to `retired/` - does not make their whole history look new.
    """
    records: dict[Path, dict] = {}
    for path in paths:
        content = read_at_base(base_ref, path)
        if content is None:
            continue
        records[path] = yaml.safe_load(content) or {}
    return records


class Finding(NamedTuple):
    """One reported problem, plus a key identifying it across revisions.

    The key must not change when a file is only reformatted, so dates go into it
    as strings: the bot rewrites `'2019-01-14'` as `2019-01-14`, which YAML loads
    as a str in one revision and a datetime.date in the other.
    """

    key: tuple
    message: str
    blocking: bool


def batch_findings(records: dict[Path, dict]) -> list[Finding]:
    """The warning-level (non-blocking) checks that only make sense when scoped to a
    batch of changed files - see find_shared_end_dates' docstring."""
    findings: list[Finding] = []

    for date, entries in sorted(find_shared_end_dates(records).items()):
        names = ", ".join(f"{name} ({path})" for name, path in entries)
        findings.append(
            Finding(
                ("shared-end-date", date, tuple(str(path) for _, path in entries)),
                f"warning: {len(entries)} people have a role end_date of {date}: "
                f"{names}\n"
                "  Verify each person's effective date individually against their "
                "own source - a shared date across unrelated people is often a "
                "batch/announcement date rather than each person's real one.",
                False,
            )
        )

    same_seat = find_same_seat_retirements(records)
    for (jurisdiction, rtype, district), entries in sorted(
        same_seat.items(), key=lambda kv: str(kv[0])
    ):
        names = ", ".join(f"{name} ({path})" for name, path in entries)
        findings.append(
            Finding(
                (
                    "same-seat",
                    str(jurisdiction),
                    str(rtype),
                    str(district),
                    tuple(str(path) for _, path in entries),
                ),
                f"warning: {len(entries)} people retired for the same seat "
                f"(jurisdiction={jurisdiction!r}, type={rtype!r}, "
                f"district={district!r}): {names}\n"
                "  A multi-seat district can legitimately have two incumbents, "
                "but both being retired in the same change is a sign the "
                "district number was matched instead of the departing "
                "person's name - verify each one individually against a "
                "source naming them specifically before retiring more than "
                "one incumbent of the same seat at once.",
                False,
            )
        )

    stale = find_stale_executive_persons(records)
    for name, path, last_end_date in sorted(stale, key=lambda s: str(s[1])):
        findings.append(
            Finding(
                ("stale-executive", str(path)),
                f"warning: {path} lists {name} under executive/ but their most "
                f"recent role ended {last_end_date}, which is in the past - "
                "consider moving this file to retired/ (see openstates/people#4045).",
                False,
            )
        )

    repurposed = find_repurposed_identities(records)
    for path, other_name, given in sorted(repurposed, key=lambda r: str(r[0])):
        findings.append(
            Finding(
                ("repurposed-identity", str(path), other_name),
                f"warning: {path} lists other_name {other_name!r}, a different given "
                f"name than this file's own {given!r} but sharing its family name - "
                "possible repurposed identity (see openstates/issues#4040). Verify "
                f"whether {other_name!r} is a distinct person (e.g. predecessor in "
                "the same seat) who needs their own retired/ file with their own "
                "service history, rather than an alias of the current occupant.",
                False,
            )
        )

    return findings


def collect_findings(records: dict[Path, dict], batch: bool) -> list[Finding]:
    """Every finding in one revision of the files, as comparable Finding keys."""
    findings: list[Finding] = []
    for path, record in sorted(records.items(), key=lambda kv: str(kv[0])):
        problems = check_role_integrity(record) + check_missing_start_date(record)
        findings.extend(
            Finding(("role", str(path), problem), f"{path}: {problem}", True)
            for problem in problems
        )
    if batch:
        findings.extend(batch_findings(records))
    return findings


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
    parser.add_argument(
        "--base-ref",
        help=(
            "git ref the change is based on. Findings that already exist at this "
            "ref are reported as a pre-existing count instead of blocking, so a "
            "change is only asked to answer for what it introduced."
        ),
    )
    args = parser.parse_args()

    scoped = args.changed_files is not None
    if scoped:
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

    # Batch checks are scoped to changed files only - see find_shared_end_dates'
    # docstring for why comparing against the whole repo is the wrong check (a seat
    # like a US House district has had many genuinely-unrelated retirees over the
    # decades; only a single batch of changed files makes a shared date/seat
    # meaningful).
    findings = collect_findings(load_records(integrity_targets), batch=scoped)

    preexisting = 0
    if args.base_ref:
        base_records = load_base_records(args.base_ref, integrity_targets)
        base_keys = {f.key for f in collect_findings(base_records, batch=scoped)}
        new_findings = [f for f in findings if f.key not in base_keys]
        preexisting = len(findings) - len(new_findings)
        findings = new_findings

    for finding in findings:
        print(finding.message)

    if preexisting:
        print(
            f"note: {preexisting} role-date finding(s) in these files already exist "
            f"at {args.base_ref} and are not this change's to fix. Re-run without "
            "--base-ref to list them."
        )

    if any(finding.blocking for finding in findings):
        print(
            "\nRole date integrity problems found (duplicate/dangling role entries).",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
