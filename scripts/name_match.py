#!/usr/bin/env python

import os
import glob
import click
import csv
from collections import defaultdict
from utils import get_filename, get_data_dir, load_yaml, dump_obj

unmatched = []

def interactive_check(csv_name, yml_name, possible_name_match):

    if last_name_match:
        click.secho(f"Last name matched between {csv_name} and {yml_name}", fg="yellow")
        text = "(a)dd name?"

    ch = "~"
    if possible_name_match:
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
        possible_name_match = False
        matched = False

        cleaned_name = str.capitalize(name)

        if person.get("family_name") != None:
            if cleaned_name == person["family_name"]:
                possible_name_match = True
                matched = True#interactive_check(name, person["name"], possible_name_match)
            elif cleaned_name.split()[-1] == person["family_name"]:
                # Example: Tom Brinkman
                matched = True
            elif cleaned_name.split()[0].replace(",", "") == person["family_name"]:
                # Example Kwan, Karen
                matched = True
            elif cleaned_name.replace("'", "") == person["family_name"].replace("'", ""):
                # Example O'Donnell
                matched = True
            elif cleaned_name.replace(" ", "") == person["family_name"].replace(" ", ""):
                # Example Crosswhite Hader == CrosswhiteHader
                matched = True
        elif cleaned_name in person["name"]:
            matched = True
        elif len(cleaned_name.split()) > 0 and (cleaned_name.split()[0] in person["name"]):
            # Example: West (Tammy)
            matched = True
        elif len(cleaned_name.split()) > 2 and (cleaned_name.split()[2] in person["name"]):
            #Matt Huffman, M.
            matched = True
        if matched:
            break
    else:
        unmatched.append(name)


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

    print("\n\nTotal unmatched:")
    for name in unmatched:
        print(name)

if __name__ == "__main__":
    entrypoint()