#!/usr/bin/env python

import os
import glob
import click
import csv
from utils import get_filename, get_data_dir, load_yaml, dump_obj


def find_match(line):
    print(line)

@click.command()
@click.argument("archive_data_csv")
def entrypoint(archive_data_csv):
    archive_data = []
    with open(archive_data_csv) as f:
        archive_data.append(f.read())

    for line in archive_data:
        find_match(line)


if __name__ == "__main__":
    entrypoint()