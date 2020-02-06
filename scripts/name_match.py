#!/usr/bin/env python

import os
import glob
import click
import csv
from collections import defaultdict
from utils import get_filename, get_data_dir, load_yaml, dump_obj


def interactive_check(csv_name, yml_name, last_name_match):

    if last_name_match:
        click.secho(f"Last name matched between {csv_name} and {yml_name}", fg="yellow")
        text = "(a)dd name"
        # click.secho(f"Add name to {yml_name}?", fg="yellow")

    ch = "~"
    if last_name_match:
        choices = "a"

    while ch not in (choices + "sa"):
        click.secho(text + " (s)kip? (e)xit?", bold=True)
        ch = click.getchar()

    if ch == "e":
        raise SystemExit(-1)
    elif ch == "a":
        click.secho(" adding.", fg="green")
    elif ch == "s":
        return False

    return True


def find_match(name, jurisdiction, session, num_occurances, existing_people):

    for person in existing_people:
        last_name_match = False

        if name == person["family_name"]:
            last_name_match = True
            matched = interactive_check(name, person["name"], last_name_match)
        
        if matched:
            break


@click.command()
@click.argument("archive_data_csv")
def entrypoint(archive_data_csv):
    archive_data = []
    with open(archive_data_csv, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            archive_data.append({
                "name": row['name'],
                "jurisdiction": row['jurisdiction'],
                "session": row['session'],
                "num_occurances": row['num_occurances']
            })

    existing_people = []
    for filename in glob.glob(os.path.join(get_data_dir(archive_data[0]["jurisdiction"]), "people/*.yml")):
        with open(filename) as f:
            existing_people.append(load_yaml(f))

    for line in archive_data:
        find_match(line["name"], line["jurisdiction"], line["session"], line["num_occurances"], existing_people)

if __name__ == "__main__":
    entrypoint()