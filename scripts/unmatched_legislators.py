#!/usr/bin/env python
"""Script to create CSVs of unmatched legislators given a state and session"""
import csv
from collections import Counter, defaultdict
from utils import get_jurisdiction_id, init_django, get_all_abbreviations
import click
from django.db import transaction


class AbortTransaction(Exception):
    pass


def get_unmatched(jurisdiction_id):
    from opencivicdata.legislative.models import PersonVote, BillSponsorship
    from django.db.models import Count, F

    voters = (
        PersonVote.objects.filter(
            vote_event__legislative_session__jurisdiction_id=jurisdiction_id, voter_id=None,
        )
        .values(name=F("voter_name"), session=F("vote_event__legislative_session__identifier"),)
        .annotate(n=Count("id"))
    )

    bill_sponsors = (
        BillSponsorship.objects.filter(
            bill__legislative_session__jurisdiction_id=jurisdiction_id,
            person_id=None,
            organization_id=None,
        )
        .values("name", session=F("bill__legislative_session__identifier"))
        .annotate(n=Count("id"))
    )

    # both lists have dicts with keys: name, session, n
    return voters, bill_sponsors


def archive_leg_to_csv(state_abbr=None):
    output_filename = f"unmatched_{state_abbr}.csv"

    jurisdiction_id = get_jurisdiction_id(state_abbr)

    # name -> session -> count
    missing_votes = Counter()
    missing_sponsors = Counter()
    sessions_for_name = defaultdict(set)

    voters, bill_sponsors = get_unmatched(jurisdiction_id)

    for voter in voters:
        missing_votes[voter["name"]] += voter["n"]
        sessions_for_name[voter["name"]].add(voter["session"])

    for bill_sponsor in bill_sponsors:
        missing_sponsors[bill_sponsor["name"]] += bill_sponsor["n"]
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


def get_matching_person(jurisdiction_id, name):
    from opencivicdata.core.models import Person
    from django.db.models import Q

    candidates = list(
        Person.objects.filter(
            (Q(name=name) | Q(other_names__name=name) | Q(family_name=name))
            & Q(memberships__organization__jurisdiction_id=jurisdiction_id)
        ).distinct()
    )

    if len(candidates) == 1:
        return candidates[0]
    else:
        click.secho(f"{len(candidates)} possible matches for {name}: {candidates}", fg="yellow")


@transaction.atomic
def check_historical_matches(abbr, dry=True):
    from opencivicdata.legislative.models import PersonVote

    jurisdiction_id = get_jurisdiction_id(abbr)
    voters, sponsorships = get_unmatched(jurisdiction_id)

    for voter in voters:
        person = get_matching_person(jurisdiction_id, voter["name"])
        if person:
            click.secho(
                f"updating {voter['n']} records for {voter['name']} "
                f"session={voter['session']} to {person}",
                fg="green",
            )
        if not dry:
            to_update = PersonVote.objects.filter(
                vote_event__legislative_session__jurisdiction_id=jurisdiction_id,
                vote_event__legislative_session__identifier=voter["session"],
                voter_name=voter["name"],
                voter_id=None,
            )
            if to_update.count() != voter["n"]:
                raise AbortTransaction(f"mismatched counts for {voter}, got {to_update.count()}")
            to_update.update(voter=person)


@click.command()
@click.argument("abbreviations", nargs=-1)
@click.option("--dump/--no-dump")
@click.option("--match/--no-match")
@click.option("--dry/--no-dry", default=True)
def export_unmatched(abbreviations, dump, match, dry):
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        if dump:
            archive_leg_to_csv(abbr)
        if match:
            if dry:
                click.secho("dry run, nothing will be saved", fg="blue")
            try:
                check_historical_matches(abbr, dry=dry)
            except AbortTransaction as e:
                click.secho(f"{e}\ntransaction aborted!", fg="red")


if __name__ == "__main__":
    init_django()
    export_unmatched()
