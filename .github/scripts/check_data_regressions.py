#!/usr/bin/env python3
"""Warn when a change drops contact data that already existed in the base revision.

The openstates-bot has repeatedly overwritten manually-fixed office phones,
emails, and fax numbers with empty values because the scraper did not collect
them (see openstates/issues#1445 and #1453). The bot's merge passes every
structural lint check - the YAML is valid, the schema allows empty offices -
so nothing has caught it until a human noticed the data was gone.

This script compares each changed person YAML file against its base revision
and reports any `offices` contact field (voice, fax, email) that was present
at the base and is now absent or empty. It never fails the build on its own
(exit code is always 0) because a removal can be legitimate:

  - A legislator resigned or retired: their office contact is no longer theirs.
  - The legislature changed its numbering: the old number is dead.
  - A prior entry was wrong: removing it is an improvement.

The check is therefore a *warning* that tells a human or the @resolve-lint
agent "something was dropped here - please verify it was intentional before
merging." The agent's job is to look up whether the person is still in office
and whether the official site still lists the contact before deciding to restore
or accept the removal.

Scoped like check_role_dates.py and check_duplicate_people.py:
  --changed-files limits the check to files this PR touched.
  --base-ref skips regressions that already existed at the base, so a PR
    that merely reformats a file is not asked to fix gaps it did not create.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from _git_base import read_at_base

_PERSON_DIRS = ("executive", "legislature", "municipalities", "retired")

# Office sub-fields that carry contact information.
# address and name are structural - losing them when an office entry disappears
# entirely is a separate signal (the whole entry was dropped), but a missing
# address alone is not the class of regression we are catching here.
_CONTACT_FIELDS = ("voice", "fax", "email")


def is_person_file(path: Path) -> bool:
    """True if path looks like a person YAML file (data/<state>/<person_dir>/*.yml)."""
    return path.suffix in (".yml", ".yaml") and any(
        part in _PERSON_DIRS for part in path.parts
    )


def person_files(data_dir: Path) -> list[Path]:
    """Return all person YAML files across every jurisdiction."""
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


def _person_name(record: dict) -> str:
    given = record.get("given_name", "")
    family = record.get("family_name", "")
    return f"{given} {family}".strip()


def _contact_snapshot(record: dict) -> dict[tuple[str, str], frozenset[str]]:
    """Return a flat map of (office_type, field) -> frozenset of non-empty values.

    Uses a set per (classification, field) key so that multiple offices sharing
    the same classification (e.g. two 'district' offices) are all captured.
    A single dict key with one value is overwritten by the last writer, which
    would silently hide any regression on earlier same-classification offices.
    With a set, a dropped value is detected as the difference base_values -
    head_values, regardless of how many offices share the classification.

    office_type is the value of the `classification` key when present, or the
    zero-based index of the office entry as a string when absent, so entries
    without a classification can still be matched position-to-position.
    """
    snapshot: dict[tuple[str, str], set[str]] = {}
    for idx, office in enumerate(record.get("offices") or []):
        key = str(office.get("classification") or idx)
        for field in _CONTACT_FIELDS:
            value = str(office.get(field) or "").strip()
            if value:
                snapshot.setdefault((key, field), set()).add(value)
    return {k: frozenset(v) for k, v in snapshot.items()}


def _regression_key(path: Path, office_key: str, field: str) -> tuple:
    """Stable key used to compare a finding across base and head revisions."""
    return ("contact-regression", str(path), office_key, field)


def load_record(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_base_record(base_ref: str, path: Path) -> dict | None:
    content = read_at_base(base_ref, path)
    if content is None:
        return None
    try:
        return yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return None


class Regression:
    """One dropped contact field, with enough context to act on it."""

    def __init__(
        self,
        path: Path,
        name: str,
        office_key: str,
        field: str,
        old_value: str,
    ) -> None:
        self.path = path
        self.name = name
        self.office_key = office_key
        self.field = field
        self.old_value = old_value

    @property
    def key(self) -> tuple:
        return _regression_key(self.path, self.office_key, self.field)

    def __str__(self) -> str:
        return (
            f"warning: {self.path} ({self.name}) lost offices[{self.office_key!r}]"
            f".{self.field} = {self.old_value!r}\n"
            "  Verify whether this person is still in office and the contact is "
            "still on the official site before accepting this removal "
            "(see openstates/issues#1445, #1453)."
        )


def find_regressions(
    path: Path,
    base_record: dict,
    head_record: dict,
) -> list[Regression]:
    """Return contact fields that existed in base_record but are gone in head_record."""
    base_contacts = _contact_snapshot(base_record)
    head_contacts = _contact_snapshot(head_record)
    name = _person_name(head_record) or _person_name(base_record)
    regressions = []
    for (office_key, field), base_values in sorted(base_contacts.items()):
        head_values = head_contacts.get((office_key, field), frozenset())
        for old_value in sorted(base_values - head_values):
            regressions.append(
                Regression(path, name, office_key, field, old_value)
            )
    return regressions


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Warn when a change drops office contact data (voice/fax/email) "
            "that already existed in the base revision. Never exits non-zero: "
            "the warning is for human or agent review, since a removal can be "
            "legitimate (retired legislator, changed number, corrected typo)."
        )
    )
    parser.add_argument("--data-dir", default="data", type=Path)
    parser.add_argument(
        "--changed-files",
        nargs="*",
        help="limit the check to these changed person files (CI mode)",
    )
    parser.add_argument(
        "--base-ref",
        required=True,
        help=(
            "git ref the change is based on. Only regressions absent from the "
            "base are reported, so a PR that reformats a file is not asked to "
            "fix gaps it did not create."
        ),
    )
    args = parser.parse_args()

    if args.changed_files is not None:
        targets = [
            Path(f)
            for f in args.changed_files
            if is_person_file(Path(f)) and Path(f).exists()
        ]
    else:
        targets = person_files(args.data_dir)

    if not targets:
        print("No changed person files to check")
        return 0

    all_regressions: list[Regression] = []
    preexisting = 0

    for path in sorted(targets):
        base_record = load_base_record(args.base_ref, path)
        if base_record is None:
            # File is new in this change - nothing to regress against.
            continue
        head_record = load_record(path)
        regressions = find_regressions(path, base_record, head_record)
        if not regressions:
            continue

        # Filter out regressions that already existed at the base, so a PR
        # that merely reformats a file is not blamed for a pre-existing gap.
        # A "pre-existing regression" means the contact was already absent
        # from head AND absent from base - i.e. the base itself was already
        # missing it. That is not possible by construction (find_regressions
        # only fires when base HAS the value and head DOES NOT), so every
        # regression here is genuinely introduced by this change.
        # The base_ref filter is therefore a no-op structurally, but we keep
        # the preexisting counter for parity with the other check scripts, in
        # case future callers pass a mid-chain ref where the gap was already
        # partially introduced.
        for regression in regressions:
            all_regressions.append(regression)

    new_regressions = all_regressions  # see comment above - all are new by construction

    for regression in new_regressions:
        print(regression)

    if preexisting:
        print(
            f"note: {preexisting} contact regression(s) in these files already "
            f"exist at {args.base_ref} and are not this change's to fix."
        )

    if new_regressions:
        total = len(new_regressions)
        files = len({r.path for r in new_regressions})
        print(
            f"\n{total} contact regression(s) across {files} file(s). "
            "These are warnings only - the build is not failed because a "
            "removal may be legitimate. Review each one before merging "
            "(see openstates/issues#1445, #1453).",
            file=sys.stderr,
        )

    # Always exit 0: this is a non-blocking warning check.
    # The @resolve-lint agent reads the warning output and decides whether
    # to restore the value (person still in office, contact still on official
    # site) or accept the removal (person retired, number changed/wrong).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
