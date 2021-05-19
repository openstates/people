#!/usr/bin/env python
import re
import json
import click
from pathlib import Path
from collections import defaultdict, OrderedDict
from openstates.utils import abbr_to_jid
from ..utils import (
    get_data_path,
    dump_obj,
    ocd_uuid,
)


PHONE_RE = re.compile(
    r"""^
                      \D*(1?)\D*                                # prefix
                      (\d{3})\D*(\d{3})\D*(\d{4}).*?             # main 10 digits
                      (?:(?:ext|Ext|EXT)\.?\s*\s*(\d{1,4}))?    # extension
                      $""",
    re.VERBOSE,
)


def reformat_phone_number(phone: str) -> str:
    match = PHONE_RE.match(phone)
    if match:
        groups = match.groups()

        ext = groups[-1]
        if ext:
            ext = f" ext. {ext}"
        else:
            ext = ""

        if not groups[0]:
            groups = groups[1:-1]
        else:
            groups = groups[:-1]
        return "-".join(groups) + ext
    else:
        return phone


def reformat_address(address: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\s*\n\s*", ";", address))


def process_link(link: dict[str, str]) -> dict[str, str]:
    if not link["note"]:
        del link["note"]
    return link


def process_dir(input_dir: Path, output_dir: Path, jurisdiction_id: str) -> None:
    person_memberships = defaultdict(list)

    # collect memberships
    for filename in input_dir.glob("membership_*.json"):
        with open(filename) as f:
            membership = json.load(f)

        if membership["person_id"].startswith("~"):
            raise ValueError(membership)
        person_memberships[membership["person_id"]].append(membership)

    # process people
    for filename in input_dir.glob("person_*.json"):
        with open(filename) as f:
            person = json.load(f)

        scrape_id = person["_id"]
        person["memberships"] = person_memberships[scrape_id]
        person = process_person(person, jurisdiction_id)

        dump_obj(person, output_dir=output_dir)


def process_person(person: dict, jurisdiction_id: str) -> dict:
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

    contact_details: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
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
def main(input_dir: str) -> None:
    """
    Convert scraped JSON in INPUT_DIR to YAML files for this repo.

    Will put data into incoming/ directory for usage with merge.py's --incoming option.
    """

    # abbr is last piece of directory name
    abbr = ""
    for piece in input_dir.split("/")[::-1]:
        if piece:
            abbr = piece
            break

    jurisdiction_id = abbr_to_jid(abbr)

    output_dir = get_data_path(abbr)
    output_dir = Path(str(output_dir).replace("data", "incoming")) / "legislature"
    assert "incoming" in str(output_dir)

    try:
        output_dir.mkdir()
    except FileExistsError:
        for file in output_dir.glob("*.yml"):
            file.unlink()
    process_dir(Path(input_dir), output_dir, jurisdiction_id)


if __name__ == "__main__":
    main()
