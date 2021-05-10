import uuid
from collections import defaultdict
from pathlib import Path
import us
import requests
import click
from ..models.people import (
    Person,
    OtherIdentifier,
    Role,
    Party,
    ContactDetail,
    Link,
    PersonIdBlock,
)
from ..utils import dump_obj, get_data_dir

# chosen at random, but needs to be constant
US_UUID_NAMESPACE = uuid.UUID("bf6b57c6-8cfe-454c-bd26-9c2b508c30b2")


def get_district_offices():
    district_offices = defaultdict(list)
    url = "https://theunitedstates.io/congress-legislators/legislators-district-offices.json"
    entries = requests.get(url).json()
    for entry in entries:
        for office in entry["offices"]:
            address = office.get("address", "")
            if address:
                if office.get("suite"):
                    address += " " + office["suite"]
                address += f"; {office['city']}, {office['state']} {office['zip']}"

            district_offices[entry["id"]["bioguide"]].append(
                ContactDetail(
                    note="District Office",
                    voice=office.get("phone", ""),
                    fax=office.get("fax", ""),
                    address=address,
                )
            )
    return district_offices


def get_social():
    social = defaultdict(list)
    url = "https://theunitedstates.io/congress-legislators/legislators-social-media.json"
    entries = requests.get(url).json()
    for entry in entries:
        social[entry["id"]["bioguide"]] = PersonIdBlock(
            twitter=entry["social"].get("twitter", ""),
            facebook=entry["social"].get("facebook", ""),
            youtube=entry["social"].get("youtube_id", ""),
        )
    return social


def fetch_current():
    url = "https://theunitedstates.io/congress-legislators/legislators-current.json"
    legislators = requests.get(url).json()
    for leg in legislators:
        yield current_to_person(leg)


def current_to_person(current):
    full_name = current["name"].get(
        "official_full", f"{current['name']['first']} {current['name']['last']}"
    )
    bioguide = current["id"]["bioguide"]
    p = Person(
        id="ocd-person/" + str(uuid.uuid5(US_UUID_NAMESPACE, bioguide)),
        name=full_name,
        given_name=current["name"]["first"],
        family_name=current["name"]["last"],
        middle_name=current["name"].get("middle", ""),
        gender=current["bio"]["gender"],
        birth_date=current["bio"]["birthday"],
        roles=[],
    )
    for key, value in current["id"].items():
        if isinstance(value, list):
            for identifier in value:
                p.other_identifiers.append(OtherIdentifier(scheme=key, identifier=identifier))
        else:
            p.other_identifiers.append(OtherIdentifier(scheme=key, identifier=value))

    # keep mapping of start & end dates of party memberships
    parties = defaultdict(dict)
    for term in current["terms"]:
        if term["start"] < parties[term["party"]].get("start", "9999-99-99"):
            parties[term["party"]]["start"] = term["start"]
        if term["end"] > parties[term["party"]].get("end", ""):
            parties[term["party"]]["end"] = term["end"]
        if term["type"] == "sen":
            role_type = "upper"
            district = us.states.lookup(term["state"]).name
            # division_id = f"ocd-division/country:us/state:{term['state']}"
        elif term["type"] == "rep":
            role_type = "lower"
            if term["district"] == 0:
                district = f"{term['state']}-AL"
            else:
                district = f"{term['state']}-{term['district']}"
            # division_id = f"ocd-division/country:us/state:{term['state']}/cd:{term['district']}"
        role = Role(
            type=role_type,
            district=district,
            jurisdiction="ocd-jurisdiction/country:us/government",
            start_date=term["start"],
            end_date=term["end"],
        )
        p.roles.append(role)

    # add party memberships
    for name, times in parties.items():
        if name == "Democrat":
            name = "Democratic"
        p.party.append(Party(name=name, start_date=times["start"], end_date=times["end"]))

    # add contact info from latest term
    cur_term = current["terms"][-1]
    if "url" in cur_term:
        p.links.append(Link(note="website", url=cur_term["url"]))
    if "contact_form" in cur_term:
        p.links.append(Link(note="contact form", url=cur_term["contact_form"]))

    p.contact_details.append(
        ContactDetail(
            note="Capitol Office",
            address=cur_term.get("address", ""),
            voice=cur_term.get("phone", ""),
        )
    )

    return bioguide, p


@click.command()
def main() -> None:
    """
    Create/Update United States legislators from unitedstates.io
    """
    output_dir = Path(get_data_dir("us")) / "legislature"
    district_offices = get_district_offices()
    social = get_social()
    for bioguide, person in fetch_current():
        person.contact_details.extend(district_offices[bioguide])
        person.ids = social[bioguide]
        person.sources.append(Link(url="https://theunitedstates.io/"))
        dump_obj(person.dict(exclude_defaults=True), output_dir=output_dir)


if __name__ == "__main__":
    main()
