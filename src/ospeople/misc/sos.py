#!/usr/bin/env python3
import csv
from ..utils import ocd_uuid, dump_obj, reformat_phone_number
from openstates import metadata
from collections import OrderedDict


def make_ceos():
    with open("ceo.csv") as f:
        data = csv.DictReader(f)
        for line in data:
            state = line["State"].strip()
            given_name = line["First"]
            family_name = line["Last"]
            name = f"{given_name} {family_name}"
            role = line["Role"].strip().lower()
            addr1 = line["Address 1"]
            addr2 = line["Address 2"]
            city = line["City"]
            state_abbr = line["Postal Code"]
            zip5 = line["Zip Code"]
            zip4 = line["Zip Plus 4"]
            phone = line["Phone"]
            email = line["Email"]
            fax = line["Fax"]
            contact_form = line["Contact Form"]
            source = line["Source"]
            twitter = line["Twitter"]
            party = line["Party"]

            if party == "R":
                party = "Republican"
            elif party == "D":
                party = "Democratic"
            else:
                party = "Independent"

            if role != "secretary of state":
                role = "chief election officer"

            full_address = "; ".join([addr1, addr2, f"{city}, {state_abbr} {zip5}-{zip4}"])

            contact = {"note": "Capitol Office"}
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

            try:
                jid = metadata.lookup(name=state).jurisdiction_id
            except KeyError:
                continue
            abbr = metadata.lookup(name=state).abbr.lower()

            links = [{"url": source}]
            if contact_form:
                links.append({"url": contact_form, "note": "webform"})
            obj = OrderedDict(
                {
                    "id": ocd_uuid("person"),
                    "name": name,
                    "given_name": given_name,
                    "family_name": family_name,
                    "roles": [
                        {
                            "jurisdiction": jid,
                            "type": role.strip().lower(),
                            "end_date": "2021-12-31",
                        },
                    ],
                    "contact_details": [contact],
                    "ids": ids,
                    "sources": [{"url": source}],
                    "links": links,
                    "party": [{"name": party}],
                }
            )
            outdir = f"data/{abbr}/executive/"
            # os.makedirs(outdir)
            dump_obj(obj, output_dir=outdir)


if __name__ == "__main__":
    make_ceos()
