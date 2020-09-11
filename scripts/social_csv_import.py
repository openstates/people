#!/usr/bin/env python
import os
import re
import csv
import glob
import click
from utils import (
    get_data_dir,
    load_yaml,
    dump_obj,
)


def load_person_by_id(abbr, person_id):
    directory = get_data_dir(abbr)

    person_id = person_id.replace("ocd-person/", "")

    person = glob.glob(os.path.join(directory, "*", f"*{person_id}.yml"))
    if len(person) < 1:
        click.secho(f"could not find {abbr} {person_id}")
        return None, None
    elif len(person) > 1:
        click.secho(f"multiple matches for {abbr} {person_id}")
        return None, None

    # found them, load & return
    with open(person[0]) as f:
        return person[0], load_yaml(f)


def clean_id(value, id_type):
    if id_type == "facebook":
        print(value)
        return re.findall(r"facebook.com/([-\.\w\d]+)/?$", value)[0]
    if id_type == "twitter":
        print(value)
        return re.findall(r"twitter.com/([-\.\w\d]+)/?$", value)[0]
    return value


def add_id_if_exists(person, id_type, id_or_none):
    if id_or_none:
        new_id = clean_id(id_or_none, id_type)
        existing = person.get("ids", {}).get(id_type)
        # doesn't yet exist, set it
        if not existing:
            if "ids" not in person:
                person["ids"] = {}
            person["ids"][id_type] = new_id
            click.secho(f"set {person['id']} {id_type} to {new_id}")
        # already exists, conflict
        if existing and existing != new_id:
            click.secho(f"conflict for {person['id']} {id_type} old={existing}, new={new_id}")


@click.command()
@click.argument("abbr")
@click.argument("filename")
def social_csv_import(abbr, filename):
    with open(filename) as f:
        social_data = csv.DictReader(f)

        for line in social_data:
            person_id = line["id"]
            person_fname, person = load_person_by_id(abbr, person_id)
            if not person:
                return

            for id_type in ("twitter", "facebook", "youtube", "instagram", "linkedin"):
                add_id_if_exists(person, id_type, line.get(id_type))

            dump_obj(person, filename=person_fname)


if __name__ == "__main__":
    social_csv_import()
