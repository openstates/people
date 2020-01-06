#!/usr/bin/env python
import csv
import click
from utils import (
    get_jurisdiction_id,
    init_django,
)


@click.command()
@click.argument("state_abbr", nargs=-1)
@click.argument("session", nargs=1)
def archive_leg_to_csv(state_abbr, session):
    abbr = state_abbr[0]
    output_filename = "data/archive_data_legislators/" + abbr + session + "legislators.csv"

    init_django()
    jurisdiction_id = get_jurisdiction_id(abbr)

    voter_dictionary = {}

    from opencivicdata.legislative.models import Bill, PersonVote
    bills = Bill.objects.filter(
        legislative_session__identifier=session,
        legislative_session__jurisdiction_id=jurisdiction_id).values_list("id", flat=True)
    for bill in bills:
        voters = PersonVote.objects.filter(
            vote_event_id__bill_id=bill
        )
        for voter in voters:
            if voter.voter_name in voter_dictionary:
                voter_dictionary[voter.voter_name] += 1
            else:
                voter_dictionary[voter.voter_name] = 1

    if voter_dictionary:
        # Writing CSV
        with open(output_filename, "w") as outf:
            out = csv.DictWriter(
                outf,
                (
                    "name",
                    "jurisdiction",
                    "session",
                    "num_occurances",
                ),
            )
            out.writeheader()
            for vname, num_occurances in voter_dictionary.items():
                obj = {
                    "name": vname,
                    "jurisdiction": abbr,
                    "session": session,
                    "num_occurances": num_occurances,
                }
                out.writerow(obj)
    else:
        print("Voters not found")


if __name__ == "__main__":
    archive_leg_to_csv()
