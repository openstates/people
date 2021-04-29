#!/usr/bin/env python
import glob
import json
import os
import click
from collections import defaultdict, OrderedDict
from ..utils import (
    reformat_phone_number,
    reformat_address,
    get_data_dir,
    get_jurisdiction_id,
    dump_obj,
    ocd_uuid,
)


def process_link(link):
    if not link["note"]:
        del link["note"]
    return link


def process_dir(input_dir, output_dir, jurisdiction_id):
    person_memberships = defaultdict(list)

    # collect memberships
    for filename in glob.glob(os.path.join(input_dir, "membership_*.json")):
        with open(filename) as f:
            membership = json.load(f)

        if membership["person_id"].startswith("~"):
            raise ValueError(membership)
        person_memberships[membership["person_id"]].append(membership)

    # process people
    for filename in glob.glob(os.path.join(input_dir, "person_*.json")):
        with open(filename) as f:
            person = json.load(f)

        scrape_id = person["_id"]
        person["memberships"] = person_memberships[scrape_id]
        person = process_person(person, jurisdiction_id)

        dump_obj(person, output_dir=os.path.join(output_dir, "legislature"))


def process_person(person, jurisdiction_id):
    optional_keys = (
        "image",
        "gender",
        "biography",
        "given_name",
        "family_name",
        "birth_date",
        "death_date",
        "national_identity",
        "summary",
        # maybe post-process these?
        "other_names",
    )

    result = OrderedDict(
        id=ocd_uuid("person"),
        name=person["name"],
        email=None,
        party=[],
        roles=[],
        contact_details=[],
        links=[process_link(link) for link in person["links"]],
        sources=[process_link(link) for link in person["sources"]],
    )

    contact_details = defaultdict(lambda: defaultdict(list))
    email = None
    for detail in person["contact_details"]:
        value = detail["value"]
        if detail["type"] in ("voice", "fax"):
            value = reformat_phone_number(value)
        elif detail["type"] == "address":
            value = reformat_address(value)
        elif detail["type"] == "email":
            email = value
            continue
        contact_details[detail["note"]][detail["type"]] = value

    if email:
        result["email"] = email
    result["contact_details"] = [{"note": key, **val} for key, val in contact_details.items()]

    for membership in person["memberships"]:
        organization_id = membership["organization_id"]
        if organization_id.startswith("~"):
            org = json.loads(organization_id[1:])
            if org["classification"] in ("upper", "lower", "legislature"):
                post = json.loads(membership["post_id"][1:])["label"]
                result["roles"] = [
                    {
                        "type": org["classification"],
                        "district": str(post),
                        "jurisdiction": jurisdiction_id,
                    }
                ]
            elif org["classification"] == "party":
                result["party"] = [{"name": org["name"]}]

    for key in optional_keys:
        if person.get(key):
            result[key] = person[key]

    # promote some extras where appropriate
    extras = person.get("extras", {}).copy()
    for key in person.get("extras", {}).keys():
        if key in optional_keys:
            result[key] = extras.pop(key)
    if extras:
        result["extras"] = extras

    if person.get("identifiers"):
        result["other_identifiers"] = person["identifiers"]

    return result


@click.command()  # pragma: no cover
@click.argument("input_dir")
def to_yaml(input_dir):
    """
    Convert scraped JSON in INPUT_DIR to YAML files for this repo.

    Will put data into incoming/ directory for usage with merge.py's --incoming option.
    """

    # abbr is last piece of directory name
    abbr = None
    for piece in input_dir.split("/")[::-1]:
        if piece:
            abbr = piece
            break

    output_dir = get_data_dir(abbr)
    jurisdiction_id = get_jurisdiction_id(abbr)

    output_dir = output_dir.replace("data", "incoming")
    assert "incoming" in output_dir

    try:
        os.makedirs(os.path.join(output_dir, "legislature"))
    except FileExistsError:
        for file in glob.glob(os.path.join(output_dir, "legislature", "*.yml")):
            os.remove(file)
    process_dir(input_dir, output_dir, jurisdiction_id)


if __name__ == "__main__":
    to_yaml()
