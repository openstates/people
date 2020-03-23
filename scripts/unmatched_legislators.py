#!/usr/bin/env python
"""Script to create CSVs of unmatched legislators given a state and session"""
import csv
from collections import Counter, defaultdict
from utils import get_jurisdiction_id, init_django, get_all_abbreviations
import click


def archive_leg_to_csv(state_abbr=None):
    from opencivicdata.legislative.models import PersonVote, BillSponsorship
    from django.db.models import Count, F

    output_filename = f"unmatched_{state_abbr}.csv"

    jurisdiction_id = get_jurisdiction_id(state_abbr)

    # name -> session -> count
    missing_votes = Counter()
    missing_sponsors = Counter()
    sessions_for_name = defaultdict(set)

    voters = (
        PersonVote.objects.filter(
            vote_event__legislative_session__jurisdiction_id=jurisdiction_id, voter_id=None,
        )
        .values("voter_name", session=F("vote_event__legislative_session__identifier"))
        .annotate(n=Count("id"))
    )
    for voter in voters:
        missing_votes[voter["voter_name"]] += voter["n"]
        sessions_for_name[voter["voter_name"]].add(voter["session"])

    bill_sponsors = (
        BillSponsorship.objects.filter(
            bill__legislative_session__jurisdiction_id=jurisdiction_id,
            person_id=None,
            organization_id=None,
        )
        .values("name", session=F("bill__legislative_session__identifier"))
        .annotate(n=Count("id"))
    )
    for bill_sponsor in bill_sponsors:
        missing_sponsors[bill_sponsor["name"]] += 1
        sessions_for_name[bill_sponsor["name"]].add(bill_sponsor["session"])

    all_names = sorted(sessions_for_name.keys())

    with open(output_filename, "w") as outf:
        out = csv.DictWriter(outf, ("name", "jurisdiction", "sessions", "votes", "sponsorships"))
        out.writeheader()
        for name in all_names:
            obj = {
                "name": name,
                "jurisdiction": state_abbr,
                "sessions": "; ".join(sorted(sessions_for_name[name])),
                "votes": missing_votes[name],
                "sponsorships": missing_sponsors[name],
            }
            out.writerow(obj)


@click.command()
@click.argument("abbreviations", nargs=-1)
def export_unmatched(abbreviations=None):
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        archive_leg_to_csv(abbr)


if __name__ == "__main__":
    init_django()
    export_unmatched()
