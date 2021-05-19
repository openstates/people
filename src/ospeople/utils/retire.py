#!/usr/bin/env python
import typing
import os
import yaml
from pathlib import Path
from datetime import datetime
from openstates import metadata
from ..utils import dump_obj
from ..models.people import Person


def add_vacancy(person: dict, until: datetime) -> None:
    with open("settings.yml") as f:
        settings = yaml.safe_load(f)
    last_role = person["roles"][-1]
    abbr = metadata.lookup(jurisdiction_id=last_role["jurisdiction"]).abbr.lower()
    if abbr not in settings:
        settings[abbr] = {"vacancies": []}
    settings[abbr]["vacancies"].append(
        {
            "chamber": last_role["type"],
            "district": last_role["district"],
            "vacant_until": until.date(),
        }
    )
    dump_obj(settings, filename="settings.yml")


def retire_person(
    person: Person, end_date: datetime, reason: typing.Optional[str] = None, death: bool = False
) -> tuple[Person, int]:
    num = 0
    for role in person.roles:
        if role.is_active():
            role.end_date = end_date
            if reason:
                role.end_reason = reason
            num += 1

    if death:
        person.death_date = end_date

    # remove old contact details
    person.contact_details = []

    return person, num


def retire_file(filename: typing.Union[Path, str]) -> str:  # pragma: no cover
    if isinstance(filename, Path):
        filename = str(filename)
    new_filename = filename.replace("/legislature/", "/retired/").replace(
        "/municipalities/", "/retired/"
    )
    os.renames(filename, new_filename)
    return new_filename
