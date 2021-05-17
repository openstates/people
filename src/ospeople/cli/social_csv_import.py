#!/usr/bin/env python
import re
import csv
import click
import typing
from ..utils import load_yaml, dump_obj, find_file


def load_person_by_id(
    abbr: str, person_id: str
) -> tuple[typing.Optional[str], typing.Optional[dict]]:
    filename = find_file(person_id, state=abbr)
    with open(filename) as f:
        return filename, load_yaml(f)


def clean_id(value: typing.Optional[str], id_type: str) -> typing.Optional[str]:
    if not value:
        return None
    try:
        if id_type == "facebook":
            return re.findall(r"facebook.com/([-\.\w\d]+)/?$", value)[0]
        if id_type == "twitter":
            return re.findall(r"twitter.com/([-\.\w\d]+)/?$", value)[0]
        if id_type == "instagram":
            return re.findall(r"instagram.com/([-\.\w\d]+)/(\??.*)$", value)[0][0]
    except IndexError:
        click.secho(f"skipping {id_type} id {value}", fg="yellow")
        return None
    return value


def add_id_if_exists(person: dict, id_type: str, id_or_none: typing.Optional[str]) -> None:
    new_id = clean_id(id_or_none, id_type)
    if new_id:
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
def main(abbr: str, filename: str) -> None:
    with open(filename) as f:
        social_data = csv.DictReader(f)

        for line in social_data:
            person_id = line["id"]
            person_fname, person = load_person_by_id(abbr, person_id)
            if not person:
                return

            for id_type in ("twitter", "facebook", "instagram"):
                add_id_if_exists(person, id_type, line.get(id_type))
            for link_type in ("linkedin", "youtube", "campaign_url"):
                if url := line.get(link_type):
                    person["links"].append({"url": url, "note": link_type})

            dump_obj(person, filename=person_fname)


if __name__ == "__main__":
    main()
