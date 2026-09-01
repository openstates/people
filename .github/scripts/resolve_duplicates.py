#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["openstates==6.25.2", "pyyaml"]
#
# [tool.uv]
# # textract (pulled in transitively by openstates<7) pins six~=1.12.0,
# # which lacks six.moves support under 3.13 (see
# # https://github.com/benjaminp/six/issues/517). Force a modern six.
# override-dependencies = ["six>=1.16"]
# ///
"""Deterministically merge duplicate person records found by check_duplicate_people.py.

Canonical file per group = the non-retired file if one exists, else the
first file (sorted, so deterministic). Fields on the canonical record are
never overwritten by a duplicate's value; duplicates only fill blanks and
append to list fields (roles, links, sources, other_identifiers, names).
This is the opposite of openstates.utils.people.merge.merge_people, which
is designed for incoming *fresher* scrape data overwriting stale records -
here neither file is fresher, so overwriting would risk clobbering good
data with stale data at random depending on group ordering.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from check_duplicate_people import check_state  # ty: ignore[unresolved-import]
from openstates.models.people import OtherIdentifier, OtherName, Person
from openstates.utils.people import dump_obj

_SCALAR_FILL_ONLY = [
    "gender",
    "email",
    "image",
    "biography",
    "birth_date",
    "given_name",
    "family_name",
    "suffix",
]
_LIST_APPEND = ["roles", "links", "sources", "other_identifiers"]
_ID_FIELDS = ["twitter", "youtube", "instagram", "facebook", "wikidata"]
_UUID_RE = re.compile(
    r"([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def load(path: Path) -> Person:
    with path.open() as f:
        return Person(**yaml.safe_load(f))


def merge_offices(old_offices: list, new_offices: list) -> None:
    old_by_name = {o.name: o for o in old_offices}
    for o in new_offices:
        existing = old_by_name.get(o.name)
        if existing is None:
            old_offices.append(o)
        else:
            for field in existing.__fields__:
                if not getattr(existing, field) and getattr(o, field):
                    setattr(existing, field, getattr(o, field))


def _merge_identity(old: Person, new: Person) -> None:
    """Record `new`'s id and name(s) on `old` as alternates, if not already present."""
    if new.id != old.id and not any(
        oi.identifier == new.id for oi in old.other_identifiers
    ):
        old.other_identifiers.append(
            OtherIdentifier(scheme="openstates", identifier=new.id)
        )

    if new.name != old.name and not any(on.name == new.name for on in old.other_names):
        old.other_names.append(OtherName(name=new.name))
    for on in new.other_names:
        if on.name != old.name and not any(x.name == on.name for x in old.other_names):
            old.other_names.append(on)


def safe_merge(old: Person, new: Person) -> None:
    """Merge `new` into `old` in place, never overwriting an existing old value."""
    _merge_identity(old, new)

    for field in _SCALAR_FILL_ONLY:
        if not getattr(old, field) and getattr(new, field):
            setattr(old, field, getattr(new, field))

    for field in _LIST_APPEND:
        old_list = getattr(old, field)
        for item in getattr(new, field):
            if item not in old_list:
                old_list.append(item)

    for f in _ID_FIELDS:
        if not getattr(old.ids, f) and getattr(new.ids, f):
            setattr(old.ids, f, getattr(new.ids, f))

    if not old.party and new.party:
        old.party = list(new.party)

    merge_offices(old.offices, new.offices)

    for k, v in new.extras.items():
        if k not in old.extras:
            old.extras[k] = v


def pick_canonical(paths: list[Path]) -> tuple[Path, list[Path]]:
    ordered = sorted(paths)
    canonical = next(
        (p for p in ordered if "/retired/" not in p.as_posix()), ordered[0]
    )
    others = [p for p in ordered if p != canonical]
    return canonical, others


_ResolveResult = tuple[str, str, Path, list[Path]]


def resolve_state(data_dir: Path, state: str, apply: bool) -> list[_ResolveResult]:
    """Return (given, family, canonical, others) for every duplicate group in state."""
    duplicates = check_state(data_dir, state)
    results = []
    for (given, family), paths in duplicates.items():
        canonical, others = pick_canonical(paths)
        old = load(canonical)
        for other_path in others:
            safe_merge(old, load(other_path))
        if apply:
            dump_obj(old, filename=canonical)
            for other_path in others:
                other_path.unlink()
        results.append((given, family, canonical, others))
    return results


def format_resolved_line(
    state: str, given: str, family: str, canonical: Path, others: list[Path]
) -> str:
    match = _UUID_RE.search(canonical.stem)
    short_id = match.group(1) if match else canonical.stem
    return (
        f"- `{state}` `{given}` `{family}`: consolidated {len(others)} dupe(s) "
        f"into {canonical.parent.name} `{short_id}`"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "states", nargs="+", help="state abbreviations to resolve, e.g. az ar"
    )
    parser.add_argument("--data-dir", default="data", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write merges and delete duplicate files (default: dry run)",
    )
    args = parser.parse_args()

    for state in sorted(set(args.states)):
        results = resolve_state(args.data_dir, state, args.apply)
        if not results:
            print(f"# {state}: no duplicates found")
            continue
        for given, family, canonical, others in results:
            print(format_resolved_line(state, given, family, canonical, others))
            if not args.apply:
                for other_path in others:
                    print(
                        f"    (dry run) would merge {other_path} -> {canonical}, "
                        "then delete it"
                    )

    if not args.apply:
        print(
            "\ndry run only - pass --apply to write merges and delete duplicate files",
            file=sys.stderr,
        )

    return 0


def _selftest() -> None:
    """Minimal sanity check for safe_merge's fill-only/append semantics."""
    old_id = "ocd-person/00000000-0000-0000-0000-000000000001"
    new_id = "ocd-person/00000000-0000-0000-0000-000000000002"
    old = Person(id=old_id, name="Jane Doe", roles=[], gender="Female")
    new = Person(
        id=new_id, name="Jane A. Doe", roles=[], gender="Male", email="jane@example.com"
    )
    safe_merge(old, new)
    assert old.gender == "Female", "canonical scalar must not be overwritten"  # noqa: S101
    assert old.email == "jane@example.com", "blank scalar must be filled from duplicate"  # noqa: S101
    assert old.name == "Jane Doe", "canonical name must never change"  # noqa: S101
    assert any(on.name == "Jane A. Doe" for on in old.other_names), (  # noqa: S101
        "duplicate name must be recorded"
    )
    assert any(oi.identifier == new_id for oi in old.other_identifiers)  # noqa: S101
    print("selftest OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _selftest()
        raise SystemExit(0)
    raise SystemExit(main())
