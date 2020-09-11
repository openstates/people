#!/usr/bin/env python
import os
import sys
import csv
import glob
import click
from utils import (
    get_data_dir,
    get_jurisdiction_id,
    get_all_abbreviations,
    load_yaml,
    role_is_active,
)


def load_person_by_id(abbr, person_id):
    directory = get_data_dir(abbr)

    person_id = person_id.replace("ocd-person/", "")

    person = glob.glob(os.path.join(directory, "*", f"*{person_id}.yml"))
    if len(person) < 1:
        click.secho(f"could not find {abbr} {person_id}")
        return
    elif len(person) > 1:
        click.secho(f"multiple matches for {abbr} {person_id}")
        return

    # found them, load & return
    with open(person[0]) as f:
        return load_yaml(f)


@click.command()
@click.argument("abbr")
@click.argument("filename")
def social_csv_import(abbr, filename):
    with open(filename) as f:
        social_data = csv.DictReader(f)

        for line in social_data:
            person_id = line["id"]
            person = load_person_by_id(abbr, person_id)
            if not person:
                return
            print(person["name"])

            twitter = line.get("twitter")
            facebook = line.get("facebook")
            youtube = line.get("youtube")
            instagram = line.get("instagram")
            linkedin = line.get("linkedin")


if __name__ == "__main__":
    social_csv_import()
