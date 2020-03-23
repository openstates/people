#!/usr/bin/env python
"""Script to create CSVs of unmatched legislators given a state and session"""

import csv
from collections import Counter
from utils import get_jurisdiction_id, init_django
import click


init_django()

from opencivicdata.legislative.models import (
    LegislativeSession,
    PersonVote,
    BillSponsorship,
)  # noqa


def archive_leg_to_csv(state_abbr=None, session=None):
    output_filename = f"unmatched_{state_abbr}_{session}.csv"

    jurisdiction_id = get_jurisdiction_id(state_abbr)

    missing_votes = Counter()
    missing_sponsors = Counter()

    voters = PersonVote.objects.filter(
        vote_event__bill__legislative_session__identifier=session,
        vote_event__bill__legislative_session__jurisdiction_id=jurisdiction_id,
        voter_id=None,
    )
    for voter in voters:
        missing_votes[voter.voter_name] += 1

    bill_sponsors = BillSponsorship.objects.filter(
        bill__legislative_session__identifier=session,
        bill__legislative_session__jurisdiction_id=jurisdiction_id,
        person_id=None,
        organization_id=None,
    )
    for bill_sponsor in bill_sponsors:
        missing_sponsors[bill_sponsor.name] += 1

    all_names = set(missing_votes) | set(missing_sponsors)

    if all_names:
        with open(output_filename, "w") as outf:
            out = csv.DictWriter(
                outf, ("name", "jurisdiction", "session", "votes", "sponsorships")
            )
            out.writeheader()
            for name in sorted(all_names):
                obj = {
                    "name": name,
                    "jurisdiction": state_abbr,
                    "session": session,
                    "votes": missing_votes[name],
                    "sponsorships": missing_sponsors[name],
                }
                out.writerow(obj)
    else:
        print(f"no unmatched for {session}")


@click.command()
@click.argument("state_abbr", nargs=1)
@click.argument("session", nargs=1, required=False)
def export_unmatched(state_abbr=None, session=None):
    jurisdiction_id = get_jurisdiction_id(state_abbr)

    if session:
        archive_leg_to_csv(state_abbr, session)
    else:
        sessions = LegislativeSession.objects.filter(jurisdiction_id=jurisdiction_id).values_list(
            "identifier", flat=True
        )
        for session in sessions:
            archive_leg_to_csv(state_abbr, session)


if __name__ == "__main__":
    export_unmatched()
