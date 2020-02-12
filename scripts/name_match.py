#!/usr/bin/env python

import os
import glob
import click
import csv
from collections import defaultdict
from utils import get_filename, get_data_dir, load_yaml, dump_obj

unmatched = []

def interactive_check(csv_name, yml_name, possible_name_match):

    choices = ""
    if possible_name_match:
        click.secho(f"Last name matched between '{csv_name}' and '{yml_name}'", fg="yellow")
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


def find_match(name, person):

    possible_name_match = False
    matched = False

    cleaned_name = str.lower(name)
    cleaned_name = cleaned_name.replace(".", " ")
    cleaned_name = cleaned_name.replace("*", " ")
    cleaned_name = cleaned_name.replace(",", " ")

    cleaned_person_name = str.lower(person["name"])
    cleaned_person_name = cleaned_person_name.replace(".", " ")
    cleaned_person_name = cleaned_person_name.replace("*", " ")
    cleaned_person_name = cleaned_person_name.replace(",", " ")

    if person.get("family_name") != None:

        cleaned_person_family_name = str.lower(person["family_name"])

        if cleaned_name == cleaned_person_family_name:
            matched = True
        elif cleaned_name in cleaned_person_family_name:
            matched = True
        elif cleaned_name.split()[-1] == cleaned_person_family_name:
            # Example: Tom Brinkman
            matched = True
        elif cleaned_name.split()[0].replace(",", "") == cleaned_person_family_name:
            # Example Kwan, Karen
            matched = True
        elif len(cleaned_name.split()) == 3 and (cleaned_person_family_name in cleaned_name.split()[1]):
            # Example: Matt Huffman, M.
            matched = True
        elif len(cleaned_name.split()) == 3 and (cleaned_name.split()[0] == cleaned_person_family_name):
            # Example: ZEIGLER of Montville
            matched = True
        elif len(cleaned_name.split()) == 4 and (cleaned_name.split()[2] in cleaned_person_family_name):
            # Example: Louis W. Blessing, III
            matched = True
        elif len(cleaned_name.split()) > 4 and (cleaned_name.split()[1] in cleaned_person_family_name):
            # Example: S. CHANG (Introduced by request of another party) in Hawaii
            matched = True
        elif cleaned_name.replace("'", "") == cleaned_person_family_name.replace("'", ""):
            # Example O'Donnell
            matched = True
        elif cleaned_name.replace(" ", "") == cleaned_person_family_name.replace(" ", ""):
            # Example Crosswhite Hader == CrosswhiteHader
            matched = True
    elif cleaned_name in person["name"]:
        matched = True
    elif (" of " in cleaned_name) and (cleaned_name.split(" of ")[0] in cleaned_person_name):
        # Example: carpenter of aroostook
        matched = True
    elif cleaned_name[0] == cleaned_person_name[-1]:
        # Another example for: Carpenter of Aroostook, 
        matched = True
    elif len(cleaned_name.split()) > 0 and (cleaned_name.split()[0] in cleaned_person_name):
        # Example: West (Tammy)
        matched = True
    elif len(cleaned_name.split()) > 2 and (cleaned_name.split()[2] in cleaned_person_name):
        #Matt Huffman, M.
        matched = True

    if matched:
        return True
    else:
        return False


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
        for person in existing_people:
            matched = find_match(line["name"], person)
            if matched:
                # interactive_check(line["name"], person["name"], matched)
                break
        else:
            unmatched.append(line["name"])

    print("\n\nTotal unmatched:")
    for name in unmatched:
        print(name)

if __name__ == "__main__":
    entrypoint()