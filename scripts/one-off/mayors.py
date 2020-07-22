#!/usr/bin/env python3
import sys
import csv
import datetime
from utils import ocd_uuid, dump_obj, reformat_phone_number
from collections import OrderedDict


def city_to_jurisdiction(city, state):
    return f"ocd-jurisdiction/country:us/state:{state.lower()}/place:{city.lower()}/government"


def make_mayors(state_to_import):
    all_municipalities = []
    with open("mayors.csv") as f:
        data = csv.DictReader(f)
        for line in data:
            state = line["Postal Code"].lower()
            if state != state_to_import:
                continue
            city = line["City"].strip()
            given_name = line["First"].strip()
            family_name = line["Last"].strip()
            name = f"{given_name} {family_name}"
            email = line["Email"].strip()
            webform = line["Web Form"].strip()
            phone = reformat_phone_number(line["Phone"])
            fax = reformat_phone_number(line["Fax"])
            address1 = line["Address 1"].strip()
            address2 = line["Address 2"].strip()
            zipcode = line["Zip Code"].strip()
            if line["Zip Plus 4"].strip():
                zipcode += "-" + line["Zip Plus 4"].strip()
            term_end = datetime.datetime.strptime(line["Term End"], "%m/%d/%Y").strftime(
                "%Y-%m-%d"
            )

            if address2:
                full_address = f"{address1};{address2};{city}, {state.upper()} {zipcode}"
            else:
                full_address = f"{address1};{city}, {state.upper()} {zipcode}"

            contact = {"note": "Primary Office"}
            if full_address:
                contact["address"] = full_address
            if fax:
                contact["fax"] = fax
            if phone:
                contact["voice"] = phone
            if email:
                contact["email"] = email

            jid = city_to_jurisdiction(city, state)
            all_municipalities.append(OrderedDict({"name": city, "id": jid}))

            obj = OrderedDict(
                {
                    "id": ocd_uuid("person"),
                    "name": name,
                    "given_name": given_name,
                    "family_name": family_name,
                    "roles": [{"jurisdiction": jid, "type": "mayor", "end_date": term_end}],
                    "contact_details": [contact],
                    "sources": [{"url": webform}] if webform else [],
                    "links": [{"url": webform}] if webform else [],
                }
            )
            dump_obj(obj, output_dir=f"data/{state}/municipalities/")
        dump_obj(all_municipalities, filename=f"data/{state_to_import}/municipalities.yml")


if __name__ == "__main__":
    # make_mayors("ak")
    make_mayors(sys.argv[1])
