#!/usr/bin/env python3
import os
import csv
from ..utils import ocd_uuid, dump_obj, reformat_phone_number
from openstates import metadata
from collections import OrderedDict


def make_governors():
    with open("governors.csv") as f:
        data = csv.DictReader(f)
        for line in data:
            state = line["state"]
            name = line["name"]
            given_name = line["first_name"]
            family_name = line["last_name"]
            party = line["party"]
            birth_date = line["birth_date"]
            start_date = line["start_date"]
            end_date = line["end_date"]
            website = line["website"]
            twitter = line["twitter"]
            webform = line["webform"]

            full_address = "; ".join([n.strip() for n in line["address"].splitlines()])
            phone = line["phone"]
            email = line["email"]
            fax = line["fax"]

            contact = {"note": "Capitol Office"}
            if full_address:
                contact["address"] = full_address
            if fax:
                contact["fax"] = reformat_phone_number(fax)
            if phone:
                contact["voice"] = reformat_phone_number(phone)
            if email:
                contact["email"] = email

            ids = {}
            if twitter:
                ids["twitter"] = twitter

            jid = metadata.lookup(name=state).jurisdiction_id
            abbr = metadata.lookup(name=state).abbr.lower()

            obj = OrderedDict(
                {
                    "id": ocd_uuid("person"),
                    "name": name,
                    "given_name": given_name,
                    "family_name": family_name,
                    "birth_date": birth_date,
                    "party": [{"name": party}],
                    "roles": [
                        {
                            "jurisdiction": jid,
                            "type": "governor",
                            "start_date": start_date,
                            "end_date": end_date,
                        }
                    ],
                    "contact_details": [contact],
                    "ids": ids,
                    "sources": [{"url": website}],
                    "links": [{"url": website}, {"url": webform, "note": "webform"}],
                }
            )
            outdir = f"data/{abbr}/executive/"
            os.makedirs(outdir)
            dump_obj(obj, output_dir=outdir)


if __name__ == "__main__":
    make_governors()
