#!/usr/bin/env python

import sys
import glob
import os
from ..utils import get_data_dir, load_yaml, dump_obj
from collections import defaultdict, OrderedDict
import click


def fix_offices(filename):
    with open(filename) as file:
        data = load_yaml(file)

    # office_type -> key -> set of values seen
    all_details = defaultdict(lambda: defaultdict(set))
    email = set()

    for office in data.get("contact_details", []):
        for key, value in office.items():
            if key == "note":
                continue
            if key == "email":
                email.add(value)
            else:
                otype = office["note"]
                # # Florida fixes
                # if "/fl" in filename and key == "address":
                #     value = "; ".join([v.strip() for v in value.split(";")])
                # if "/fl/" in filename and key == "voice" and not value.startswith("850-"):
                #     otype = "District Office"
                # if "/fl/" in filename and key == "address" and "32399-1300" not in value:
                #     otype = "District Office"
                all_details[otype][key].add(value)

    reformatted = defaultdict(dict)
    error = False

    for office_type, office_details in all_details.items():
        for ctype, values in office_details.items():
            if len(values) == 1:
                reformatted[office_type][ctype] = values.pop()
            else:
                click.secho(f"multiple values for {office_type} {ctype}: {values}", fg="red")
                error = True

    if len(email) == 1:
        email = email.pop()
    elif len(email) > 1:
        emails = list(email)
        if "leg.state.vt.us" in emails[0]:
            email = emails[0]
        elif "leg.state.vt.us" in emails[1]:
            email = emails[0]
        elif emails[0].lower() == emails[1].lower():
            email = emails[0]
        else:
            click.secho(f"multiple values for email: {email}", fg="red")
            error = True

    if not error:
        if email:
            data["email"] = email
        data["contact_details"] = []
        for otype in ("Capitol Office", "District Office", "Primary Office"):
            if otype in reformatted:
                data["contact_details"].append(OrderedDict(note=otype, **reformatted[otype]))
        # click.echo(f"rewrite contact details as {data['contact_details']}")
        dump_obj(data, filename=filename)


def fix_offices_state(state):
    for filename in glob.glob(os.path.join(get_data_dir(state), "executive/*.yml")):
        fix_offices(filename)


def remove_retired_data(state):
    for filename in glob.glob(os.path.join(get_data_dir(state), "retired/*.yml")):
        with open(filename) as file:
            data = load_yaml(file)
        data.pop("contact_details", None)
        dump_obj(data, filename=filename)


if __name__ == "__main__":
    state = sys.argv[1]
    if state == "all":
        state = "*"
    fix_offices_state(state)
    # remove_retired_data(state)
