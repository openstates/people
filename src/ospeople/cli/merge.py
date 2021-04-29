#!/usr/bin/env python
import os
import glob
import click
from collections import defaultdict
from openstates import metadata
from ..utils import get_new_filename, get_data_dir, load_yaml, dump_obj, find_file, retire_file
from .retire import retire_person


def merge_contact_details(old, new):
    # figure out which office entries are which
    old_offices = defaultdict(dict)
    new_offices = defaultdict(dict)
    offices = []
    update = False

    for office in old or []:
        note = office["note"]
        if not old_offices[note]:
            old_offices[note] = office
        else:
            raise NotImplementedError(f"extra old {note}")
    for office in new or []:
        note = office["note"]
        if not new_offices[note]:
            new_offices[note] = office
        else:
            raise NotImplementedError(f"extra old {note}")

    for note in sorted(set(old_offices) | set(new_offices)):
        combined = update_office(old_offices[note], new_offices[note])
        offices.append(combined)
        if combined != old_offices[note]:
            update = True

    # return all offices if there were any changes
    if update:
        return offices
    else:
        return None


def update_office(old_office, new_office):
    """ function returns a copy of old_office updated with values from new if applicable """
    updated_office = old_office.copy()
    # update each field in office
    for newfield, newval in new_office.items():
        for oldfield, oldval in old_office.items():
            if oldfield == newfield and newval != oldval:
                updated_office[oldfield] = newval
                break
        else:
            # add new fields to updated office
            updated_office[newfield] = newval
    return updated_office


class Append:
    def __init__(self, key_name, list_item):
        self.key_name = key_name
        self.list_item = list_item

    def __eq__(self, other):
        return self.key_name == other.key_name and self.list_item == other.list_item

    def __str__(self):
        return f"{self.key_name}: append {dict(self.list_item)}"

    def __repr__(self):
        return f"Append({self.key_name}, {self.list_item})"


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

    def __repr__(self):
        return f"Replace({self.key_name}, {self.value_one}, {self.value_two})"


class ContactDetailsReplace(Replace):
    def __str__(self):
        def _fmt_cd(cd):
            cd_str = f"{cd['note']}"
            for key in ("address", "voice", "fax"):
                if key in cd:
                    cd_str += f" {key}={cd[key]}"
            return cd_str

        old = "\n\t".join(_fmt_cd(cd) for cd in self.value_one)
        new = "\n\t".join(_fmt_cd(cd) for cd in self.value_two)

        return f"{self.key_name} changed from: \n\t{old}\n  to\n\t{new}"


def compute_merge(obj1, obj2, prefix="", keep_both_ids=False):
    combined_keys = set(obj1) | set(obj2)
    changes = []
    for key in combined_keys:
        key_name = ".".join((prefix, key)) if prefix else key
        val1 = obj1.get(key)
        val2 = obj2.get(key)

        # special cases first
        if key == "id":
            if val1 != val2 and keep_both_ids:
                # old id stays as id: to keep things sane
                changes.append(
                    Append("other_identifiers", {"scheme": "openstates", "identifier": val2})
                )
        elif key == "name":
            if val1 != val2:
                # new name becomes name, but old name goes into other_names
                changes.append(Append("other_names", {"name": val1}))
                changes.append(Replace("name", val1, val2))
        elif key == "contact_details":
            changed = merge_contact_details(val1, val2)
            if changed:
                changes.append(ContactDetailsReplace("contact_details", val1 or [], changed))
        elif isinstance(val1, list) or isinstance(val2, list):
            if val1 and not val2:
                continue
            elif val2 and not val1:
                changes.append(Replace(key_name, val1, val2))
            else:
                # both have elements, append new to old, leave old intact
                for item in val2:
                    if item not in val1:
                        changes.append(Append(key_name, item))
        elif isinstance(val1, dict) or isinstance(val2, dict):
            changes.extend(compute_merge(val1 or {}, val2 or {}, prefix=key_name))
        else:
            # if values both exist and differ, or val1 is empty, do a Replace
            if (val1 and val2 and val1 != val2) or (val1 is None):
                changes.append(Replace(key_name, val1, val2))

    return changes


def incoming_merge(abbr, existing_people, new_people, retirement):
    unmatched = []

    seats_for_district = {}
    state = metadata.lookup(abbr=abbr)
    for chamber in state.chambers:
        chtype = "legislature" if chamber.chamber_type == "unicameral" else chamber.chamber_type
        seats_for_district[chtype] = {
            district.name: district.num_seats for district in chamber.districts
        }

    # find candidate(s) for each new person
    for new in new_people:
        matched = False
        role_matches = []

        for existing in existing_people:
            name_match = new["name"] == existing["name"]
            role_match = False
            for role in existing.get("roles", []):
                if role["type"] == "mayor" or role["type"] == "governor":
                    continue
                role_copy = role.copy()
                role_copy.pop("start_date", None)
                seats = seats_for_district[role_copy["type"]].get(role_copy["district"], 1)
                if new["roles"][0] == role_copy and seats == 1:
                    role_match = True
                    # if they match without start date, copy the start date over so it isn't
                    # alterred or otherwise removed in the merge
                    new["roles"][0] = role
                    break
            if name_match or role_match:
                matched = interactive_merge(
                    abbr, existing, new, name_match, role_match, retirement
                )

            if matched:
                break

            # if we haven't matched and this was a role match, save this for later
            if role_match:
                role_matches.append(existing)
        else:
            # not matched
            unmatched.append((new, role_matches))

    return unmatched


def copy_new_incoming(abbr, new, _type):
    fname = get_new_filename(new)
    oldfname = f"incoming/{abbr}/{_type}/{fname}".format(fname)
    newfname = f"data/{abbr}/{_type}/{fname}".format(fname)
    click.secho(f"moving {oldfname} to {newfname}", fg="yellow")
    os.rename(oldfname, newfname)


def retire(abbr, existing, new, retirement=None):
    if not retirement:
        retirement = click.prompt("Enter retirement date YYYY-MM-DD")
    person, num = retire_person(existing, retirement)
    fname = find_file(existing["id"])
    dump_obj(person, filename=fname)
    new_filename = retire_file(fname)
    click.secho(f"moved from {fname} to {new_filename}")


def interactive_merge(abbr, old, new, name_match, role_match, retirement):
    """
    returns True iff a merge was done
    """
    oldfname = find_file(old["id"])
    newfname = "incoming/{}/legislature/{}".format(abbr, get_new_filename(new))
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
        copy_new_incoming(abbr, new, "legislature")
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
            keys = change.key_name.split(".")

            # recursively set the value based on dotted key
            temp_obj = old
            for key in keys[:-1]:
                temp_obj = temp_obj.setdefault(key, {})
            temp_obj[keys[-1]] = change.value_two
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
        for filename in glob.glob(
            os.path.join(get_data_dir(abbr), "legislature/*.yml")
        ) + glob.glob(os.path.join(get_data_dir(abbr), "retired/*.yml")):
            with open(filename) as f:
                existing_people.append(load_yaml(f))

        new_people = []
        incoming_dir = get_data_dir(abbr).replace("data", "incoming")
        for filename in glob.glob(os.path.join(incoming_dir, "legislature/*.yml")):
            with open(filename) as f:
                new_people.append(load_yaml(f))

        click.secho(
            f"analyzing {len(existing_people)} existing people and {len(new_people)} incoming"
        )

        unmatched = incoming_merge(abbr, existing_people, new_people, retirement)
        click.secho(f"{len(unmatched)} people were unmatched")

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
