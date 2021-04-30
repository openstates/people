#!/usr/bin/env python3
import os
import sys
import csv
import glob
import datetime
import click
from ..utils import ocd_uuid, dump_obj, reformat_phone_number, load_yaml, find_file
from collections import defaultdict, OrderedDict


def city_to_jurisdiction(city, state):
    return f"ocd-jurisdiction/country:us/state:{state.lower()}/place:{city.lower().replace(' ', '_')}/government"


def get_existing_mayor(state, name):
    for fn in glob.glob(f"data/{state}/municipalities/*.yml") + glob.glob(
        f"data/{state}/retired/*.yml"
    ):
        with open(fn) as f:
            person = load_yaml(f)
            if person["name"] == name:
                return person, "retired" in fn
    return False, False


def update_municipalities(municipalities, state):
    fname = f"data/{state}/municipalities.yml"
    with open(fname, "r") as f:
        contents = load_yaml(f)
    dump_obj(contents + municipalities, filename=fname)


def get_mayor_details(csv_fname):
    with open(csv_fname) as f:
        data = csv.DictReader(f)

        mayors_by_state = defaultdict(list)
        municipalities_by_state = defaultdict(list)

        for line in data:
            state = line["Postal Code"].lower()
            if state == "dc":
                continue
            # if state != state_to_import:
            #     continue
            city = line["City"].strip()
            given_name = line["Given Name"].strip()
            family_name = line["Family Name"].strip()
            name = f"{given_name} {family_name}"
            email = line["Email"].strip()
            source = line["Source"].strip()
            phone = reformat_phone_number(f"{line['Voice']} line['Phone Extension']")
            address = line["Address"].strip()
            zipcode = line["Zip Code"].strip()
            if not line["Term End"]:
                term_end = "2022-01-01"  # temporary term end date for the unknowns
            else:
                term_end = datetime.datetime.strptime(line["Term End"], "%m/%d/%Y").strftime(
                    "%Y-%m-%d"
                )

            if term_end < "2020-09-24":
                click.secho(f"skipping retired {name}, {term_end}", fg="yellow")
                continue

            full_address = f"{address};{city}, {state.upper()} {zipcode}"

            contact = OrderedDict({"note": "Primary Office"})
            if full_address:
                contact["address"] = full_address
            if phone:
                contact["voice"] = phone

            jid = city_to_jurisdiction(city, state)

            existing, retired = get_existing_mayor(state, name)
            if existing:
                pid = existing["id"]
            else:
                pid = ocd_uuid("person")

            if retired:
                os.remove(find_file(existing["id"]))

            mayors_by_state[state].append(
                OrderedDict(
                    {
                        "id": pid,
                        "name": name,
                        "given_name": given_name,
                        "family_name": family_name,
                        "roles": [{"jurisdiction": jid, "type": "mayor", "end_date": term_end}],
                        "contact_details": [contact],
                        "sources": [{"url": source}] if source else [],
                        "links": [{"url": source}] if source else [],
                        "email": email,
                    }
                )
            )

            municipalities_by_state[state].append(OrderedDict({"name": city, "id": jid}))

    return mayors_by_state, municipalities_by_state


def main(mayor_csv):
    mayors_by_state, municipalities_by_state = get_mayor_details(mayor_csv)

    for state, mayors in mayors_by_state.items():
        for mayor in mayors:
            dump_obj(mayor, output_dir=f"data/{state}/municipalities/")

    for state, jids in municipalities_by_state.items():
        update_municipalities(jids, state)


if __name__ == "__main__":
    # make_mayors("ak")
    main(sys.argv[1])
