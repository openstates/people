#!/usr/bin/env python
import os
import click
from datetime import datetime
from utils import load_yaml, dump_obj, role_is_active


def retire_person(person, end_date, reason=None, death=False):
    num = 0
    for role in person["roles"]:
        if role_is_active(role):
            role["end_date"] = end_date
            if reason:
                role["end_reason"] = reason
            num += 1

    if death:
        person["death_date"] = end_date

    # remove old contact details
    person.pop("contact_details", None)

    return person, num


def move_file(filename):  # pragma: no cover
    new_filename = filename.replace("/legislature/", "/retired/").replace(
        "/municipalities/", "/retired/"
    )
    click.secho(f"moved from {filename} to {new_filename}")
    os.renames(filename, new_filename)


def validate_end_date(ctx, param, value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise click.BadParameter("END_DATE must be a valid date in the format YYYY-MM-DD")


@click.command()
@click.argument("end_date", callback=validate_end_date)
@click.argument("filename")
@click.option("--reason", default=None)
@click.option("--death", is_flag=True)
def retire(end_date, filename, reason, death):
    """
    Retire a legislator, given END_DATE and FILENAME.

    Will set end_date on active roles.
    """
    # end the person's active roles & re-save
    with open(filename) as f:
        person = load_yaml(f)
    if death:
        reason = "Deceased"
    person, num = retire_person(person, end_date, reason, death)
    dump_obj(person, filename=filename)

    if num == 0:
        click.secho("no active roles to retire", fg="red")
    elif num == 1:
        click.secho("retired person")
    else:
        click.secho(f"retired person from {num} roles")

    move_file(filename)


if __name__ == "__main__":
    retire()
