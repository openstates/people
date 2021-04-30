#!/usr/bin/env python
import typing
import click
import csv
from ..utils import (
    iter_objects,
    role_is_active,
    get_all_abbreviations,
    load_yaml,
    find_file,
    dump_obj,
)


def generate_template_csv(
    abbreviations: list[str], filename: str, missing_id: typing.Optional[str] = None
) -> None:
    fields = ("id", "name", "chamber", "district", "jurisdiction")

    with open(filename, "w") as outfile:
        out = csv.DictWriter(outfile, fields)
        out.writeheader()

        for abbr in abbreviations:
            for person, filename in iter_objects(abbr, "people"):
                skip = False

                if missing_id:
                    for oid in person.get("other_identifiers", []):
                        if oid["scheme"] == missing_id:
                            skip = True
                            break

                if not skip:
                    for role in person["roles"]:
                        if role_is_active(role):
                            break
                    else:
                        raise Exception()
                    out.writerow(
                        {
                            "id": person["id"],
                            "name": person["name"],
                            "chamber": role["type"],
                            "district": role["district"],
                            "jurisdiction": role["jurisdiction"],
                        }
                    )


def update_from_csv(filename: str, fields: list[str], other_identifiers: list[str]) -> None:
    with open(filename) as f:
        for line in csv.DictReader(f):
            yaml_filename = find_file(line["id"])
            with open(yaml_filename) as yf:
                person = load_yaml(yf)

            for field in fields:
                person[field] = line[field]

            if other_identifiers and "other_identifiers" not in person:
                person["other_identifiers"] = []
            for scheme in other_identifiers:
                # TODO: check for duplicates among what was already there
                for id in line[scheme].split(";"):
                    if id:
                        person["other_identifiers"].append({"scheme": scheme, "identifier": id})
            dump_obj(person, filename=yaml_filename)


@click.command()
@click.argument("abbreviations", nargs=-1)
@click.option("--missing-id", default=None)
@click.option("--filename")
@click.option("--fields", multiple=True)
@click.option("--other-identifiers", multiple=True)
def main(
    abbreviations: list[str],
    missing_id: typing.Optional[str],
    filename: str,
    fields: list[str],
    other_identifiers: list[str],
) -> None:
    """
    Import & Export Manual Data CSV Files
    """
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    if missing_id:
        click.secho(f"generating {filename} with all legislators missing {missing_id}")
        generate_template_csv(abbreviations, filename, missing_id=missing_id)

    if fields or other_identifiers:
        click.secho(f"loading {fields} and other_ids{other_identifiers} from {filename}")
        update_from_csv(filename, fields, other_identifiers)


if __name__ == "__main__":
    main()
