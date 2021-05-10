from collections import defaultdict
import requests
from ..models.people import Person, OtherIdentifier, Role, Party, ContactDetail, Link


def fetch_current():
    url = "https://theunitedstates.io/congress-legislators/legislators-current.json"
    legislators = requests.get(url).json()
    for leg in legislators:
        yield current_to_person(leg)


def current_to_person(current):
    full_name = current["name"].get(
        "official_full", f"{current['name']['first']} {current['name']['last']}"
    )
    p = Person(
        id="ocd-person/00001111-2222-3333-4444-555566667777",
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
            district = term["state"]
            # division_id = f"ocd-division/country:us/state:{term['state']}"
        elif term["type"] == "rep":
            role_type = "lower"
            district = "{term['state']}-{term['district']}"
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
        p.roles.append(Party(name=name, start_date=times["start"], end_date=times["end"]))

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

    return p


for x in fetch_current():
    print(x)
