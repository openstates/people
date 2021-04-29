#!/usr/bin/env python
import os
import click
from collections import OrderedDict
from ..utils import ocd_uuid, get_jurisdiction_id, get_data_dir, dump_obj


def create_person(
    fname, lname, name, state, district, party, rtype, url, image, email, start_date
):
    role = {
        "type": rtype,
        "district": district,
        "jurisdiction": get_jurisdiction_id(state),
        "start_date": start_date,
    }
    if rtype in ("upper", "lower", "legislature"):
        directory = "legislature"
    elif rtype in ("mayor",):
        directory = "municipalities"
        role.pop("district")
    elif rtype in ("governor", "lt_governor"):
        directory = "executive"
        role.pop("district")
    else:
        raise ValueError(f"unknown role type {rtype}")

    person = OrderedDict(
        {
            "id": ocd_uuid("person"),
            "name": name or f"{fname} {lname}",
            "given_name": fname,
            "family_name": lname,
            "image": image,
            "email": email,
            "party": [{"name": party}],
            "roles": [role],
            "links": [{"url": url}],
            "sources": [{"url": url}],
        }
    )

    output_dir = get_data_dir(state)
    dump_obj(person, output_dir=os.path.join(output_dir, directory))


@click.command()
@click.option("--fname", prompt="First Name", help="First Name")
@click.option("--lname", prompt="Last Name", help="Last Name")
@click.option("--name", help="Optional Name, if not provided First + Last will be used")
@click.option("--state", prompt="State", help="State abbreviation")
@click.option("--district", prompt="District", help="District")
@click.option("--party", prompt="Party", help="Party")
@click.option("--rtype", prompt="Role Type (upper|lower|mayor)", help="Role Type")
@click.option("--url", prompt="URL", help="Source URL")
@click.option("--image", prompt="Image URL", help="Image URL")
@click.option("--email", prompt="Email", help="Email")
@click.option("--start-date", prompt="Start Date", help="Start Date YYYY-MM-DD")
def new_person(fname, lname, name, state, district, party, rtype, url, image, email, start_date):
    """
    Create a new person record.

    Arguments can be passed via command line flags, omitted arguments will be prompted.

    Be sure to review the file and add any additional data before committing.
    """
    create_person(
        fname=fname,
        lname=lname,
        name=name,
        state=state,
        district=district,
        party=party,
        rtype=rtype,
        url=url,
        image=image,
        email=email,
        start_date=start_date,
    )


if __name__ == "__main__":
    new_person()
