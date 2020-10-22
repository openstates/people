#!/usr/bin/env python

import sys
import glob
import os
from utils import get_data_dir, load_yaml, dump_obj
from collections import defaultdict, OrderedDict
import click


def fix_offices(filename):
    with open(filename) as file:
        data = load_yaml(file)
    # office_type -> key -> set of values seen
    all_details = defaultdict(lambda: defaultdict(set))
    for office in data.get("contact_details", []):
        for key, value in office.items():
            if key == "note":
                continue
            all_details[office["note"]][key].add(value)

    reformatted = defaultdict(dict)
    error = False

    for office_type, office_details in all_details.items():
        for ctype, values in office_details.items():
            if len(values) == 1:
                reformatted[office_type][ctype] = values.pop()
            else:
                click.secho(f"multiple values for {office_type} {ctype}: {values}", fg="red")
                error = True

    if not error:
        data["contact_details"] = []
        for otype in ("Capitol Office", "District Office", "Primary Office"):
            if otype in reformatted:
                data["contact_details"].append(OrderedDict(note=otype, **reformatted[otype]))
        # click.echo(f"rewrite contact details as {data['contact_details']}")
    dump_obj(data, filename=filename)


def fix_offices_state(state):
    for filename in glob.glob(os.path.join(get_data_dir(state), "legislature/*.yml")):
        fix_offices(filename)


if __name__ == "__main__":
    state = sys.argv[1]
    fix_offices_state(state)
