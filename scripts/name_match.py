#!/usr/bin/env python

import os
import glob
import click
import csv
from utils import get_filename, get_data_dir, load_yaml, dump_obj


def find_match(name, jurisdiction, session, num_occurances, existing_people):
    for person in existing_people:
        if name == person["family_name"]:
            print(name, "::", person["name"])


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
    # print("Total existing_people:", existing_people[0]["family_name"])

    for line in archive_data:
        find_match(line["name"], line["jurisdiction"], line["session"], line["num_occurances"], existing_people)


if __name__ == "__main__":
    entrypoint()