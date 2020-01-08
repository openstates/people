#!/usr/bin/env python

import os
import glob
import click
from utils import get_filename, get_data_dir, load_yaml, dump_obj
from retire import retire_person, move_file


class Append:
    def __init__(self, key_name, list_item):
        self.key_name = key_name
        self.list_item = list_item

    def __eq__(self, other):
        return (
            self.key_name == other.key_name
            and self.list_item == other.list_item
        )

    def __str__(self):
        return f"{self.key_name}: append {dict(self.list_item)}"


class Replace:
    def __init__(self, key_name, value_one, value_two):
        self.key_name = key_name
        self.value_one = value_one
        self.value_two = value_two

    def __eq__(self, other):
        return (
            self.key_name == other.key_name
            and self.value_one == other.value_one
            and self.value_two == other.value_two
        )

    def __str__(self):
        return f"{self.key_name}: {self.value_one} => {self.value_two}"


class MergeConflict(Exception):
    def __init__(self, difference):
        self.difference = difference

    def __str__(self):
        return str(self.difference)


def compute_merge(obj1, obj2, prefix="", keep_both_ids=False):
    combined_keys = set(obj1) | set(obj2)
    changes = []
    for key in combined_keys:
        key_name = ".".join((prefix, key)) if prefix else key
        val1 = obj1.get(key)
        val2 = obj2.get(key)

        if isinstance(val1, list) or isinstance(val2, list):
            if val1 and not val2:
                continue
            elif val2 and not val1:
                changes.ppend(Replace(key_name, val1, val2))
            else:
                # both have elements, append new to old, leave old intact
                for item in val2:
                    if item not in val1:
                        changes.append(Append(key_name, item))
        elif isinstance(val1, dict) or isinstance(val2, dict):
            changes.extend(compute_merge(val1 or {}, val2 or {}, prefix=key_name))
        elif key == "id":
            if val1 != val2 and keep_both_ids:
                # old id stays as id: to keep things sane
                changes.append(Append("other_identifiers", {"scheme": "openstates",
                                                            "identifier": val2}))
        elif key == "name":
            if val1 != val2:
                # new name becomes name, but old name goes into other_names
                changes.append(Append("other_names", {"name": val1}))
                changes.append(Replace("name", val1, val2))
        else:
            # if values both exist and differ, or val1 is empty, do a Replace
            if (val1 and val2 and val1 != val2) or (val1 is None):
                changes.append(Replace(key_name, val1, val2))

    return changes


def incoming_merge(abbr, existing_people, new_people, retirement):
    unmatched = []

    # find candidate(s) for each new person
    for new in new_people:
        matched = False
        role_matches = []

        for existing in existing_people:
            name_match = new["name"] == existing["name"]
            role_match = False
            for role in existing["roles"]:
                if new["roles"][0] == role:
                    role_match = True
                    break
            if name_match or role_match:
                matched = interactive_merge(abbr, existing, new, name_match, role_match, retirement)

            if matched:
                break

            # if we haven't matched and this was a role match, save this for later
            if role_match:
                role_matches.append(existing)
        else:
            # not matched
            unmatched.append((new, role_matches))

    return unmatched


def copy_new_incoming(abbr, new):
    fname = get_filename(new)
    oldfname = f"incoming/{abbr}/people/{fname}".format(fname)
    newfname = f"data/{abbr}/people/{fname}".format(fname)
    click.secho(f"moving {oldfname} to {newfname}", fg="yellow")
    os.rename(oldfname, newfname)


def retire(abbr, existing, new, retirement=None):
    if not retirement:
        retirement = click.prompt("Enter retirement date YYYY-MM-DD")
    person, num = retire_person(existing, retirement)
    fname = get_filename(existing)
    fname = f"data/{abbr}/people/{fname}".format(fname)
    dump_obj(person, filename=fname)
    move_file(fname)


def interactive_merge(abbr, old, new, name_match, role_match, retirement):
    """
    returns True iff a merge was done
    """
    oldfname = "data/{}/people/{}".format(abbr, get_filename(old))
    newfname = "incoming/{}/people/{}".format(abbr, get_filename(new))
    click.secho(" {} {}".format(oldfname, newfname), fg="yellow")

    # simulate difference
    changes = compute_merge(old, new, keep_both_ids=False)

    if not changes:
        click.secho(" perfect match, removing " + newfname, fg="green")
        os.remove(newfname)
        return True

    for change in changes:
        if change.key_name == "name" or change.key_name == "roles":
            click.secho("    " + str(change), fg="red", bold=True)
        else:
            click.echo("    " + str(change))

    ch = "~"
    if name_match and role_match:
        choices = "m"
        # automatically pick merge
        ch = "m"
        # there is one very specific case that this fails in, if someone is beaten
        # by someone with the exact same name, that'll need to be caught manually
    elif name_match:
        choices = "m"
        text = "(m)erge?"
    elif role_match:
        choices = "mr"
        text = f"(m)erge? (r)etire {old['name']}"

    while ch not in (choices + "sa"):
        click.secho(text + " (s)kip? (a)bort?", bold=True)
        ch = click.getchar()

    if ch == "a":
        raise SystemExit(-1)
    elif ch == "m":
        merged = merge_people(old, new, keep_both_ids=False)
        dump_obj(merged, filename=oldfname)
        click.secho(" merged.", fg="green")
        os.remove(newfname)
    elif ch == "r":
        copy_new_incoming(abbr, new)
        retire(abbr, old, new, retirement)
    elif ch == "s":
        return False

    return True


def merge_people(old, new, keep_both_ids=False):
    """
    Function to merge two people objects.

    keep_both_ids
        Should be set to True iff people have been imported before.
        If we're dealing with an election, it should be set to false since the new ID
        hasn't been published anywhere yet.
    """
    changes = compute_merge(old, new, keep_both_ids=keep_both_ids)

    for change in changes:
        if isinstance(change, Replace):
            old[change.key_name] = change.value_two
        if isinstance(change, Append):
            if change.key_name not in old:
                old[change.key_name] = []
            old[change.key_name].append(change.list_item)
    return old


@click.command()
@click.option(
    "--incoming",
    default=None,
    help="Operate in incoming mode, argument should be state abbr to scan.",
)
@click.option(
    "--retirement",
    default=None,
    help="Set retirement date for all people marked retired (in incoming mode).",
)
@click.option(
    "--old",
    default=None,
    help="Operate in merge mode, this is the older of two files & will be kept.",
)
@click.option(
    "--new",
    default=None,
    help="In merge mode, this is the newer file that will be removed after merge.",
)
def entrypoint(incoming, old, new, retirement):
    """
        Script to assist with merging legislator files.

        Can be used in two modes: incoming or file merge.

        Incoming mode analyzes incoming/ directory files (generated with to_yaml.py)
        and discovers identical & similar files to assist with merging.

        File merge mode merges two legislator files.
    """
    if incoming:
        abbr = incoming
        existing_people = []
        for filename in glob.glob(os.path.join(get_data_dir(abbr), "people/*.yml")) + glob.glob(
            os.path.join(get_data_dir(abbr), "retired/*.yml")
        ):
            with open(filename) as f:
                existing_people.append(load_yaml(f))

        new_people = []
        incoming_dir = get_data_dir(abbr).replace("data", "incoming")
        for filename in glob.glob(os.path.join(incoming_dir, "people/*.yml")):
            with open(filename) as f:
                new_people.append(load_yaml(f))

        click.secho(
            f"analyzing {len(existing_people)} existing people and {len(new_people)} incoming"
        )

        unmatched = incoming_merge(abbr, existing_people, new_people, retirement)
        click.secho(f"{len(unmatched)} were unmatched")

    if old and new:
        with open(old) as f:
            old_obj = load_yaml(f)
        with open(new) as f:
            new_obj = load_yaml(f)
        keep_both_ids = True
        if "incoming" in new:
            keep_both_ids = False
        merged = merge_people(old_obj, new_obj, keep_both_ids=keep_both_ids)
        dump_obj(merged, filename=old)
        os.remove(new)
        click.secho(f"merged files into {old}\ndeleted {new}\ncheck git diff before committing")


if __name__ == "__main__":
    entrypoint()
