#!/usr/bin/env python3
"""Flatten a change to person YAML files into one fact per line, for data review.

    uv run python .claude/skills/data-review/extract_claims.py BASE [SCOPE ...] [--all]

Compares the working tree (commits, uncommitted edits and untracked files) with BASE,
usually `git merge-base <upstream>/main HEAD`. SCOPE is state codes (`ca fl`) or paths
(`data/de/executive`); default all of data/. --all also prints facts the change left
alone, and with a SCOPE it covers every person file in the scope, changed or not.

Output is tab-separated: file, person, change, field, old, new. `change` is one of
added/deleted/moved/edited/unchanged. List items (roles, party, offices...) are paired
by their identifying fields so an edited role prints as field-level old -> new.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

PERSON_DIRS = ("/executive/", "/legislature/", "/municipalities/", "/retired/")
# fields that identify a list item, so an edit pairs with its old version
ITEM_KEYS = {
    "roles": ("type", "district", "start_date"),
    "party": ("name",),
    "offices": ("classification",),
    "other_identifiers": ("scheme", "identifier"),
    "other_names": ("name",),
}


def git(*args):
    exe = shutil.which("git") or "git"
    return subprocess.run(  # noqa: S603
        [exe, *args], capture_output=True, text=True, check=True
    ).stdout


def load(ref, path):
    if path is None:
        return {}
    if ref is None:
        return yaml.safe_load(Path(path).read_text()) or {}
    return yaml.safe_load(git("show", f"{ref}:{path}")) or {}


def text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str, sort_keys=True)
    return " ".join(
        str(value).split()
    )  # data can hold tabs/newlines; keep the TSV intact


def pair(field, old_items, new_items):
    """Yield (label, old, new) for list items, pairing edits by identifying keys."""
    keys = ITEM_KEYS.get(field, ())
    old_left = [i for i in old_items if i not in new_items]
    new_left = [i for i in new_items if i not in old_items]
    for item in old_items:
        if item in new_items:
            yield f"{field}[{label(item, keys)}]", item, item
    for old in old_left:
        # best partner: the added item sharing the most identifying fields (>= 1)
        scored = [
            (
                sum(
                    isinstance(old, dict)
                    and isinstance(n, dict)
                    and old.get(k) == n.get(k)
                    for k in keys
                ),
                n,
            )
            for n in new_left
        ]
        score, new = max(scored, key=lambda s: s[0], default=(0, None))
        if score == 0 or new is None:
            yield f"{field}[{label(old, keys)}]", old, None
            continue
        new_left.remove(new)
        for k in sorted(set(old) | set(new)):
            if old.get(k) != new.get(k):
                yield f"{field}[{label(old, keys)}].{k}", old.get(k), new.get(k)
    for new in new_left:
        yield f"{field}[{label(new, keys)}]", None, new


def label(item, keys):
    if not isinstance(item, dict):
        return text(item)
    return " ".join(text(item.get(k)) for k in keys if item.get(k) is not None) or "?"


def facts(old, new):
    for field in sorted(set(old) | set(new)):
        a, b = old.get(field), new.get(field)
        if isinstance(a, list) or isinstance(b, list):
            yield from pair(field, a or [], b or [])
        elif isinstance(a, dict) or isinstance(b, dict):
            for k in sorted(set(a or {}) | set(b or {})):
                yield f"{field}.{k}", (a or {}).get(k), (b or {}).get(k)
        else:
            yield field, a, b


def is_person(path):
    return path.endswith(".yml") and any(d in path for d in PERSON_DIRS)


def scope_paths(scope):
    paths = [f"data/{s}" if re.fullmatch("[a-z]{2}", s) else s for s in scope]
    return paths or ["data"]


def changed_files(base, scope, every_file=False):
    """Yield (kind, old_path, new_path) for person files in scope.

    Compares the working tree with base.
    """
    paths = scope_paths(scope)
    seen = set()
    for line in git("diff", "--name-status", "-M", base, "--", *paths).splitlines():
        status, *names = line.split("\t")
        if not is_person(names[-1]):
            continue
        seen.add(names[-1])
        if status.startswith("R"):
            yield "moved", names[0], names[1]
        elif status == "A":
            yield "added", None, names[0]
        elif status == "D":
            yield "deleted", names[0], None
        else:
            yield "edited", names[0], names[0]
    for name in git(
        "ls-files", "--others", "--exclude-standard", "--", *paths
    ).splitlines():
        if is_person(name):
            seen.add(name)
            yield "added", None, name
    if every_file:
        for name in git("ls-files", "--", *paths).splitlines():
            if is_person(name) and name not in seen:
                yield "unchanged", name, name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("scope", nargs="*")
    parser.add_argument("--all", action="store_true", help="include unchanged facts")
    args = parser.parse_args()

    out = sys.stdout
    for kind, old_path, new_path in changed_files(
        args.base, args.scope, args.all and bool(args.scope)
    ):
        old, new = load(args.base, old_path), load(None, new_path)
        who = text(new.get("name") or old.get("name"))
        path = new_path or old_path
        if kind == "moved":
            out.write(f"{path}\t{who}\tmoved\tpath\t{old_path}\t{new_path}\n")
        for field, a, b in facts(old, new):
            change = (
                "unchanged"
                if a == b
                else kind
                if kind in ("added", "deleted")
                else "edited"
            )
            if change != "unchanged" or args.all:
                out.write(f"{path}\t{who}\t{change}\t{field}\t{text(a)}\t{text(b)}\n")


if __name__ == "__main__":
    main()
