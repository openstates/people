#!/usr/bin/env python
import glob
import os
from collections import Counter, defaultdict
import click
from utils import (
    get_data_dir,
    load_yaml,
    role_is_active,
    get_all_abbreviations,
)

OPTIONAL_FIELD_SET = set(
    (
        "sort_name",
        "given_name",
        "family_name",
        "gender",
        "summary",
        "biography",
        "birth_date",
        "image",
        "email",
        "other_names",
    )
)


class Summarizer:
    def __init__(self):
        self.person_count = 0
        self.optional_fields = Counter()
        self.extra_counts = Counter()
        self.contact_counts = Counter()
        self.id_counts = Counter()
        self.parties = Counter()
        self.active_legislators = defaultdict(lambda: defaultdict(list))

    def summarize(self, person):
        self.person_count += 1
        self.optional_fields.update(set(person.keys()) & OPTIONAL_FIELD_SET)
        self.extra_counts.update(person.get("extras", {}).keys())

        for role in person.get("roles", []):
            if role_is_active(role):
                role_type = role["type"]
                district = role.get("district")
                break
        self.active_legislators[role_type][district].append(person)

        for role in person.get("party", []):
            if role_is_active(role):
                self.parties[role["name"]] += 1

        for cd in person.get("contact_details", []):
            for key, value in cd.items():
                if key != "note":
                    self.contact_counts[cd["note"] + " " + key] += 1

        for scheme, value in person.get("ids", {}).items():
            self.id_counts[scheme] += 1
        for id in person.get("other_identifiers", []):
            if id["scheme"] not in ("openstates", "legacy_openstates"):
                self.id_counts[id["scheme"]] += 1

    def print_summary(self):  # pragma: no cover
        click.secho(
            f"processed {self.person_count} active people", bold=True,
        )
        for role_type in self.active_legislators:
            count = sum([len(v) for v in self.active_legislators[role_type].values()])
            click.secho(f"{count:4d} {role_type}")

        click.secho("Parties", bold=True)
        for party, count in self.parties.items():
            if party == "Republican":
                color = "red"
            elif party == "Democratic":
                color = "blue"
            else:
                color = "green"
            click.secho(f"{count:4d} {party} ", bg=color)

        for name, collection in {
            "Contact Info": self.contact_counts,
            "Identifiers": self.id_counts,
            "Additional Info": self.optional_fields,
            "Extras": self.extra_counts,
        }.items():
            if collection:
                click.secho(name, bold=True)
                for type, count in collection.items():
                    click.secho(f" {type:<25} {count:4d} {count/self.person_count*100:.0f}% ")
            else:
                click.secho(name + " - none", bold=True)

    def print_roster(self):  # pragma: no cover
        for role_type, districts in self.active_legislators.items():
            for district, people in sorted(districts.items()):
                click.secho(f"{role_type} {district}", fg="blue")
                for person in people:
                    click.secho(f"   {person['name']}")

    def process_legislature(self, abbr):  # pragma: no cover
        filenames = glob.glob(os.path.join(get_data_dir(abbr), "legislature", "*.yml"))

        # settings_file = os.path.join(os.path.dirname(__file__), "../settings.yml")
        # with open(settings_file) as f:
        #     settings = load_yaml(f)

        for filename in filenames:
            with open(filename) as f:
                person = load_yaml(f)
                self.summarize(person)


@click.command()
@click.argument("abbreviations", nargs=-1)
@click.option("-v", "--verbose", count=True)
@click.option("--roster/--no-roster", default=False, help="Print roster after summary.")
@click.option(
    "--municipal/--no-municipal", default=True, help="Enable/disable linting of municipal data."
)
def summarize(abbreviations, verbose, roster, municipal):
    """
    Lint YAML files, optionally also providing a summary of state's data.

    <ABBR> can be provided to restrict linting to single state's files.
    """
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    summarizer = Summarizer()
    for abbr in abbreviations:
        summarizer.process_legislature(abbr)
    summarizer.print_summary()
    if roster:
        summarizer.print_roster()


if __name__ == "__main__":
    summarize()
