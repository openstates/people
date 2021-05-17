import sys
import typing
import datetime
from pathlib import Path
from collections import Counter, defaultdict
import click
from openstates.utils import abbr_to_jid
from ..models.people import Person, Role, Party, Link
from ..utils import (
    ocd_uuid,
    get_data_dir,
    dump_obj,
    get_all_abbreviations,
    load_yaml,
    download_state_images,
    load_settings,
)
from ..utils.retire import retire_person, add_vacancy, retire_file
from ..utils.lint_people import Validator, BadVacancy, PersonType, PersonData


OPTIONAL_FIELD_SET = {
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
}


class Summarizer:
    def __init__(self) -> None:
        self.person_count = 0
        self.optional_fields: Counter[str] = Counter()
        self.extra_counts: Counter[str] = Counter()
        self.contact_counts: Counter[str] = Counter()
        self.id_counts: Counter[str] = Counter()
        self.parties: Counter[str] = Counter()
        self.active_legislators: defaultdict[str, defaultdict[str, list[Person]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def summarize(self, person: Person) -> None:
        self.person_count += 1
        self.optional_fields.update(
            set(person.dict(exclude_defaults=True).keys()) & OPTIONAL_FIELD_SET
        )
        self.extra_counts.update(person.extras.keys())

        district = role_type = None
        for role in person.roles:
            if role.is_active():
                role_type = role.type
                district = role.district
                break
        if role_type:
            self.active_legislators[role_type][district].append(person)

        for role in person.party:
            if role.is_active():
                self.parties[role.name] += 1

        for cd in person.contact_details:
            for key in ("voice", "fax", "address"):
                if getattr(cd, key, None):
                    self.contact_counts[cd.note + " " + key] += 1

        for scheme, id_ in person.ids or []:
            if id_:
                self.id_counts[scheme] += 1
        for id_ in person.other_identifiers:
            if id_.scheme not in ("openstates", "legacy_openstates"):
                self.id_counts[id_.scheme] += 1

    def print_summary(self) -> None:  # pragma: no cover
        click.secho(
            f"processed {self.person_count} active people",
            bold=True,
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

    def print_roster(self) -> None:  # pragma: no cover
        for role_type, districts in self.active_legislators.items():
            for district, people in sorted(districts.items()):
                click.secho(f"{role_type} {district}", fg="blue")
                for person in people:
                    click.secho(f"   {person.name}")

    def process_legislature(self, abbr: str) -> None:  # pragma: no cover
        path = Path(get_data_dir(abbr)) / "legislature"
        filenames = path.glob("*.yml")

        for filename in filenames:
            with open(filename) as f:
                person = Person(**load_yaml(f))
                self.summarize(person)


def lint_dir(
    abbr: str, verbose: bool, municipal: bool, date: str, fix: bool
) -> int:  # pragma: no cover
    state_dir = Path(get_data_dir(abbr))
    legislative_filenames = (state_dir / "legislature").glob("*.yml")
    executive_filenames = (state_dir / "executive").glob("*.yml")
    municipality_filenames = (state_dir / "municipalities").glob("*.yml")
    retired_filenames = (state_dir / "retired").glob("*.yml")

    settings = load_settings()
    try:
        validator = Validator(abbr, settings, fix)
    except BadVacancy:
        sys.exit(-1)

    all_filenames = [
        (PersonType.LEGISLATIVE, legislative_filenames),
        (PersonType.RETIRED, retired_filenames),
        (PersonType.EXECUTIVE, executive_filenames),
    ]

    if municipal:
        all_filenames.append((PersonType.MUNICIPAL, municipality_filenames))

    for person_type, filenames in all_filenames:
        for filename in filenames:
            with open(filename) as f:
                data = load_yaml(f)
                person = PersonData(data=data, filename=filename, person_type=person_type)
                validator.validate_person(person, date)

    error_count = validator.print_validation_report(verbose)

    return error_count


def create_person(
    fname: str,
    lname: str,
    name: str,
    state: str,
    district: str,
    party: str,
    rtype: str,
    url: str,
    image: str,
    email: str,
    start_date: str,
) -> None:
    role = Role(
        type=rtype, district=district, jurisdiction=abbr_to_jid(state), start_date=start_date
    )

    if rtype in ("upper", "lower", "legislature"):
        directory = "legislature"
    elif rtype in ("mayor",):
        directory = "municipalities"
    elif rtype in ("governor", "lt_governor"):
        directory = "executive"

    person = Person(
        id=ocd_uuid("person"),
        name=name or f"{fname} {lname}",
        given_name=fname,
        family_name=lname,
        image=image,
        email=email,
        party=[Party(name=party)],
        roles=[role],
        links=[Link(url=url)],
        sources=[Link(url=url)],
    )

    output_dir = Path(get_data_dir(state)) / directory
    dump_obj(person.dict(exclude_defaults=True), output_dir=output_dir)


@click.group()
def main() -> None:
    pass


@main.command()
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
def new(
    fname: str,
    lname: str,
    name: str,
    state: str,
    district: str,
    party: str,
    rtype: str,
    url: str,
    image: str,
    email: str,
    start_date: str,
) -> None:
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


@main.command()
@click.argument("abbreviations", nargs=-1)
@click.option("--roster/--no-roster", default=False, help="Print roster after summary.")
def summarize(abbreviations: list[str], roster: bool) -> None:
    """
    Provide summary of a jurisdiction's data.

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


@main.command()
@click.argument("filenames", nargs=-1)
@click.option("--date")
@click.option("--reason", default=None)
@click.option("--death", is_flag=True)
@click.option("--vacant", is_flag=True)
def retire(
    date: str,
    filenames: list[str],
    reason: typing.Optional[str],
    death: bool,
    vacant: bool,
) -> None:
    """
    Retire a legislator, given END_DATE and FILENAME.

    Will set end_date on active roles.
    """
    for filename in filenames:
        # end the person's active roles & re-save
        with open(filename) as f:
            print(filename)
            person = Person(**load_yaml(f))
        if death:
            reason = "Deceased"
        person, num = retire_person(person, date, reason, death)

        if vacant:
            # default to 60 days for now
            add_vacancy(person, until=datetime.datetime.today() + datetime.timedelta(days=60))

        dump_obj(person.dict(exclude_defaults=True), filename=filename)

        if num == 0:
            click.secho("no active roles to retire", fg="red")
        elif num == 1:
            click.secho("retired person")
        else:
            click.secho(f"retired person from {num} roles")

        new_filename = retire_file(filename)
        click.secho(f"moved from {filename} to {new_filename}")


@main.command()
@click.argument("abbreviations", nargs=-1)
@click.option(
    "--skip-existing/--no-skip-existing",
    help="Skip processing for files that already exist on S3. (default: true)",
)
def sync_images(abbreviations: list[str], skip_existing: bool) -> None:
    """
    Download images and sync them to S3.

    <ABBR> can be provided to restrict to single state.
    """
    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        download_state_images(abbr, skip_existing)


@main.command()
@click.argument("abbreviations", nargs=-1)
@click.option("-v", "--verbose", count=True)
@click.option("--fix/--no-fix", default=False, help="Enable/disable automatic fixing of data.")
@click.option(
    "--municipal/--no-municipal", default=True, help="Enable/disable linting of municipal data."
)
@click.option(
    "--date",
    type=str,
    default=None,
    help="Lint roles using a certain date instead of today.",
)
def lint(abbreviations: list[str], verbose: bool, municipal: bool, date: str, fix: bool) -> None:
    """
    Lint YAML files.

    <ABBR> can be provided to restrict linting to single state's files.
    """
    error_count = 0

    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        click.secho("==== {} ====".format(abbr), bold=True)
        error_count += lint_dir(abbr, verbose, municipal, date, fix)

    if error_count:
        click.secho(f"exiting with {error_count} errors", fg="red")
        sys.exit(99)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
