#!/usr/bin/env python3
import csv
import datetime
from utils import ocd_uuid, dump_obj, reformat_phone_number
from collections import OrderedDict


def city_to_jurisdiction(city, state):
    return f"ocd-jurisdiction/country:us/state:{state.lower()}/place:{city.lower()}/government"


def make_mayors(state_to_import):
    with open("mayors.csv") as f:
        data = csv.DictReader(f)
        for line in data:
            state = line["Postal Code"].lower()
            if state != state_to_import:
                continue
            city = line["City"]
            given_name = line["First"]
            family_name = line["Last"]
            name = f"{given_name} {family_name}"
            email = line["Email"]
            webform = line["Web Form"]
            phone = reformat_phone_number(line["Phone"])
            fax = reformat_phone_number(line["Fax"])
            address1 = line["Address 1"]
            address2 = line["Address 2"]
            zipcode = line["Zip Code"]
            if line["Zip Plus 4"]:
                zipcode += "-" + line["Zip Plus 4"]
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

            obj = OrderedDict(
                {
                    "id": ocd_uuid("person"),
                    "name": name,
                    "given_name": given_name,
                    "family_name": family_name,
                    "roles": [
                        {
                            "jurisdiction": city_to_jurisdiction(city, state),
                            "type": "mayor",
                            "end_date": term_end,
                        }
                    ],
                    "contact_details": [contact],
                    "sources": [{"url": webform}] if webform else [],
                    "links": [{"url": webform}] if webform else [],
                }
            )
            dump_obj(obj, output_dir=f"data/{state}/localities/")


if __name__ == "__main__":
    make_mayors("al")
