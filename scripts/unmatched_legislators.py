#!/usr/bin/env python
"""Script to create CSVs of unmatched legislators given a state and session"""
import csv
from collections import Counter, defaultdict
from functools import lru_cache
from utils import get_jurisdiction_id, get_all_abbreviations
import click
from django.db.models import Q, F, Count
from openstates_core.utils.django import init_django


class AbortTransaction(Exception):
    pass


def get_unmatched(jurisdiction_id):
    from openstates_core.data.models import PersonVote, BillSponsorship

    voters = list(
        PersonVote.objects.filter(
            vote_event__legislative_session__jurisdiction_id=jurisdiction_id, voter_id=None,
        )
        .values(name=F("voter_name"), session=F("vote_event__legislative_session__identifier"),)
        .annotate(n=Count("id"))
    )

    bill_sponsors = list(
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


@lru_cache(1000)
def get_matching_person(jurisdiction_id, name):
    from openstates_core.data.models import Person

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


def update_objects(jurisdiction_id, objects, obj_type, dry):
    from openstates_core.data.models import PersonVote, BillSponsorship

    assert obj_type in ("vote", "sponsorship")

    for n, rec in enumerate(objects):
        person = get_matching_person(jurisdiction_id, rec["name"])
        if person:
            click.secho(
                f"[{n+1}/{len(objects)}] updating {rec['n']} {obj_type}s for {rec['name']} "
                f"session={rec['session']} to {person}",
                fg="green",
            )
        if person and not dry:
            if obj_type == "vote":
                to_update = PersonVote.objects.filter(
                    vote_event__legislative_session__jurisdiction_id=jurisdiction_id,
                    vote_event__legislative_session__identifier=rec["session"],
                    voter_name=rec["name"],
                    voter_id=None,
                )
            elif obj_type == "sponsorship":
                to_update = BillSponsorship.objects.filter(
                    bill__legislative_session__jurisdiction_id=jurisdiction_id,
                    bill__legislative_session__identifier=rec["session"],
                    name=rec["name"],
                    person_id=None,
                    organization_id=None,
                )

            # if to_update.count() != rec["n"]:
            #     raise AbortTransaction(f"mismatched counts for {rec}, got {to_update.count()}")

            if obj_type == "vote":
                to_update.update(voter=person)
            elif obj_type == "sponsorship":
                to_update.update(person=person)


def check_historical_matches(abbr, dry=True):
    jurisdiction_id = get_jurisdiction_id(abbr)
    voters, sponsorships = get_unmatched(jurisdiction_id)
    update_objects(jurisdiction_id, voters, "vote", dry)
    update_objects(jurisdiction_id, sponsorships, "sponsorship", dry)


@click.command()
@click.argument("abbreviations", nargs=-1)
@click.option("--dump/--no-dump")
@click.option("--match/--no-match")
@click.option("--dry/--no-dry", default=True)
def process_unmatched(abbreviations, dump, match, dry):
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        if match:
            if dry:
                click.secho("dry run, nothing will be saved", fg="blue")
            try:
                check_historical_matches(abbr, dry=dry)
            except AbortTransaction as e:
                click.secho(f"{e}\ntransaction aborted!", fg="red")
        if dump:
            archive_leg_to_csv(abbr)


if __name__ == "__main__":
    init_django()
    process_unmatched()
