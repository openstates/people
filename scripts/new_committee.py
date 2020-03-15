#!/usr/bin/env python
import os
import click
from collections import OrderedDict
from utils import ocd_uuid, get_jurisdiction_id, get_data_dir, dump_obj


def create_committee(*, name, state, parent, url):
    members = []
    click.echo("Enter members, enter a blank member to stop.")
    while True:
        mname = click.prompt("Member name ('done' to stop)")
        if mname == "done":
            break
        members.append({"name": mname})
    com = OrderedDict(
        {
            "id": ocd_uuid("organization"),
            "name": name,
            "classification": "committee",
            "jurisdiction": get_jurisdiction_id(state),
            "parent": parent,
            "sources": [{"url": url}],
            "links": [{"url": url}],
            "memberships": members,
        }
    )

    output_dir = get_data_dir(state)
    dump_obj(com, output_dir=os.path.join(output_dir, "organizations"))


@click.command()
@click.option("--state", prompt="State", help="State abbreviation")
@click.option("--name", prompt="Name", help="Name of committee")
@click.option("--parent", prompt="Parent", help="upper | lower | legislature")
@click.option("--url", prompt="Source URL", help="URL for committee")
def new_committee(name, state, parent, url):
    """
    Create a new committee record.

    Arguments can be passed via command line flags, omitted arguments will be prompted.

    Be sure to review the file and add any additional data before committing.
    """
    create_committee(
        name=name, state=state, parent=parent, url=url,
    )


if __name__ == "__main__":
    new_committee()
