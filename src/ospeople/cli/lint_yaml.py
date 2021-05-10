#!/usr/bin/env python
import re
import os
import sys
import datetime
import glob
import click
import typing
from dataclasses import dataclass
from collections import defaultdict, Counter
from openstates import metadata
from enum import Enum, auto
from pydantic import ValidationError
from ..utils import (
    get_data_dir,
    role_is_active,
    get_all_abbreviations,
    load_yaml,
    dump_obj,
    legacy_districts,
    load_municipalities,
    retire_file,
    load_settings,
)
from ..models.people import Person


class BadVacancy(Exception):
    pass


class PersonType(Enum):
    LEGISLATIVE = auto()
    RETIRED = auto()
    EXECUTIVE = auto()
    MUNICIPAL = auto()


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]
    fixes: list[str]


@dataclass
class PersonData:
    data: dict
    filename: str
    person_type: PersonType

    @property
    def print_filename(self) -> str:
        return os.path.basename(self.filename)


JURISDICTION_RE = re.compile(
    r"ocd-jurisdiction/country:us/(state|district|territory):\w\w/((place|county):[a-z_]+/)?government"
)

# constant to check for this particular fix
MOVED_TO_RETIRED = "moved to retired"


class Missing:
    pass


def validate_person_data(person_data: dict):
    try:
        Person(**person_data)
        return []
    except ValidationError as ve:
        return [
            f"  {'.'.join(str(l) for l in error['loc'])}: {error['msg']}" for error in ve.errors()
        ]


def validate_roles(
    person: dict, roles_key: str, retired: bool = False, date: typing.Optional[str] = None
) -> list[str]:
    active = [role for role in person.get(roles_key, []) if role_is_active(role, date=date)]
    if len(active) == 0 and not retired:
        return [f"no active {roles_key}"]
    elif roles_key == "roles" and retired and len(active) > 0:
        return [f"{len(active)} active roles on retired person"]
    elif roles_key == "roles" and len(active) > 1:
        return [f"{len(active)} active roles"]
    return []


def validate_roles_key(
    person: PersonData, fix: bool, date: typing.Optional[str] = None
) -> CheckResult:
    resp = CheckResult([], [], [])
    role_issues = validate_roles(
        person.data, "roles", person.person_type == PersonType.RETIRED, date=date
    )

    if person.person_type == PersonType.MUNICIPAL and role_issues == ["no active roles"]:
        # municipals missing roles is a warning to avoid blocking lint
        if fix:
            resp.fixes = [MOVED_TO_RETIRED]
        else:
            resp.warnings.extend(role_issues)
    else:
        resp.errors.extend(role_issues)
    return resp


def validate_offices(person: dict) -> list[str]:
    errors = []
    contact_details = person.get("contact_details", [])
    type_counter: Counter[str] = Counter()
    seen_values: dict[str, str] = {}
    for office in contact_details:
        type_counter[office["note"]] += 1
        for key, value in office.items():
            if key == "note":
                continue
            # reverse lookup to see if we've used this phone number/etc. before
            location_str = f"{office['note']} {key}"
            if value in seen_values:
                errors.append(
                    f"Value '{value}' used multiple times: {seen_values[value]} and {location_str}"
                )
            seen_values[value] = location_str
    # if type_counter["District Office"] > 1:
    #     errors.append("Multiple district offices.")
    if type_counter["Capitol Office"] > 1:
        errors.append("Multiple capitol offices, condense to one.")
    return errors


def validate_name(person: PersonData, fix: bool) -> CheckResult:
    """ some basic checks on a persons name """
    errors = []
    fixes = []
    spaces_in_name = person.data["name"].count(" ")
    if spaces_in_name == 1:
        given_cand, family_cand = person.data["name"].split()
        given = person.data.get("given_name")
        family = person.data.get("family_name")
        if not given and not family and fix:
            person.data["given_name"] = given = given_cand
            person.data["family_name"] = family = family_cand
            fixes.append(f"set given_name={given}")
            fixes.append(f"set family_name={family}")
        if not given:
            errors.append(
                f"missing given_name that could be set to '{given_cand}', run with --fix"
            )
        if not family:
            errors.append(
                f"missing family_name that could be set to '{family_cand}', run with --fix"
            )
        # expected_name = f"{given} {family}"
        # if not errors and person.data["name"] != expected_name:
        #     errors.append(f"names do not match given={given} family={family}, but name={person.data['name']}")
    return CheckResult(errors, [], fixes)


def validate_jurisdictions(person: dict, municipalities: list[str]) -> list[str]:
    errors = []
    for role in person.get("roles", []):
        jid = role.get("jurisdiction")
        try:
            state = metadata.lookup(jurisdiction_id=jid)
        except KeyError:
            state = None
        if jid and (not state and jid not in municipalities):
            errors.append(f"{jid} is not a valid jurisdiction_id")
    return errors


_EXPECTED_DISTRICTS_TYPE = dict[str, dict[str, int]]
_ACTUAL_DISTRICTS_TYPE = defaultdict[str, defaultdict[str, list[str]]]


def get_expected_districts(settings: dict[str, dict], abbr: str) -> _EXPECTED_DISTRICTS_TYPE:
    expected = {}

    state = metadata.lookup(abbr=abbr)
    for chamber in state.chambers:
        chtype = "legislature" if chamber.chamber_type == "unicameral" else chamber.chamber_type
        expected[chtype] = {district.name: district.num_seats for district in chamber.districts}

    # remove vacancies
    vacancies = settings.get(abbr, {}).get("vacancies", [])
    if vacancies:
        click.secho(f"Processing {len(vacancies)} vacancies:")
    for vacancy in vacancies:
        if datetime.date.today() < vacancy["vacant_until"]:
            expected[vacancy["chamber"]][str(vacancy["district"])] -= 1
            click.secho(
                "\t{chamber}-{district} (until {vacant_until})".format(**vacancy), fg="green"
            )
        else:
            click.secho(
                "\t{chamber}-{district} expired {vacant_until} remove & re-run".format(**vacancy),
                fg="red",
            )
            raise BadVacancy()

    return expected


def compare_districts(
    expected: _EXPECTED_DISTRICTS_TYPE, actual: _ACTUAL_DISTRICTS_TYPE
) -> list[str]:
    errors = []

    if expected.keys() != actual.keys():
        errors.append(f"expected districts for {expected.keys()}, got {actual.keys()}")
        return errors

    for chamber in expected:
        expected_districts = set(expected[chamber].keys())
        actual_districts = set(actual[chamber].keys())
        for district in sorted(expected_districts - actual_districts):
            if expected[chamber][district]:
                errors.append(f"missing legislator for {chamber} {district}")
        for district in sorted(actual_districts - expected_districts):
            errors.append(f"extra legislator for unexpected seat {chamber} {district}")
        for district in sorted(actual_districts & expected_districts):
            if len(actual[chamber][district]) < expected[chamber][district]:
                errors.append(f"missing legislator for {chamber} {district}")
            if len(actual[chamber][district]) > expected[chamber][district]:
                people = "\n\t".join(actual[chamber][district])
                errors.append(f"extra legislator for {chamber} {district}:\n\t" + people)
    return errors


class Validator:
    def __init__(self, abbr: str, settings: dict, fix: bool):
        self.expected = get_expected_districts(settings, abbr)
        self.errors: defaultdict[str, list[str]] = defaultdict(list)
        self.warnings: defaultdict[str, list[str]] = defaultdict(list)
        self.fixes: defaultdict[str, list[str]] = defaultdict(list)
        # role type -> district -> filename
        self.active_legislators: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # field name -> value -> filename
        self.duplicate_values: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self.legacy_districts = legacy_districts(abbr=abbr)
        self.municipalities = [m["id"] for m in load_municipalities(abbr=abbr)]
        self.fix = fix
        for m in self.municipalities:
            if not JURISDICTION_RE.match(m):
                raise ValueError(f"invalid municipality id {m}")

    def process_validator_result(
        self, validator_func: typing.Callable[[PersonData, bool], CheckResult], person: PersonData
    ) -> None:
        result = validator_func(person, self.fix)
        self.errors[person.print_filename].extend(result.errors)
        self.warnings[person.print_filename].extend(result.warnings)
        if result.fixes:
            self.fixes[person.print_filename].extend(result.fixes)
            dump_obj(person.data, filename=person.filename)

    def validate_person(self, person: PersonData, date: typing.Optional[str] = None) -> None:
        self.errors[person.print_filename] = validate_person_data(person.data)
        uid = person.data["id"].split("/")[1]
        if uid not in person.print_filename:
            self.errors[person.print_filename].append(f"id piece {uid} not in filename")
        self.errors[person.print_filename].extend(
            validate_jurisdictions(person.data, self.municipalities)
        )

        # looser validation for upstream-maintained unitedstates.io data
        if "/us/legislature" not in person.filename:
            self.errors[person.print_filename].extend(validate_offices(person.data))
        self.process_validator_result(validate_roles_key, person)
        self.process_validator_result(validate_name, person)

        if person.person_type == PersonType.RETIRED:
            self.errors[person.print_filename].extend(
                self.validate_old_district_names(person.data)
            )

        # check duplicate IDs
        self.duplicate_values["openstates"][person.data["id"]].append(person.print_filename)
        for scheme, value in person.data.get("ids", {}).items():
            self.duplicate_values[scheme][value].append(person.print_filename)
        for id in person.data.get("other_identifiers", []):
            self.duplicate_values[id["scheme"]][id["identifier"]].append(person.print_filename)

        # special case for the auto-retirement fix
        if MOVED_TO_RETIRED in self.fixes[person.print_filename]:
            retire_file(person.filename)

        # update active legislators
        if person.person_type == PersonType.LEGISLATIVE:
            role_type = district = None
            for role in person.data.get("roles", []):
                if role_is_active(role, date=date):
                    role_type = role["type"]
                    district = role.get("district")
                    break
            self.active_legislators[str(role_type)][str(district)].append(person.print_filename)

    def validate_old_district_names(self, person: dict) -> list[str]:
        errors = []
        for role in person.get("roles", []):
            if (
                "district" in role
                and role["district"] not in self.expected[role["type"]]
                and role["district"] not in self.legacy_districts[role["type"]]
            ):
                errors.append(f"unknown district name: {role['type']} {role['district']}")
        return errors

    def check_duplicates(self) -> list[str]:
        """
        duplicates should already be stored in self.duplicate_values
        this method just needs to turn them into errors
        """
        errors = []
        for key, values in self.duplicate_values.items():
            for value, instances in values.items():
                if len(instances) > 1:
                    if len(instances) > 3:
                        instance_str = ", ".join(instances[:3])
                        instance_str += " and {} more...".format(len(instances) - 3)
                    else:
                        instance_str = ", ".join(instances)
                    errors.append(f'duplicate {key}: "{value}" {instance_str}')
        return errors

    def print_validation_report(self, verbose: bool) -> int:  # pragma: no cover
        error_count = 0

        for fn, errors in self.errors.items():
            warnings = self.warnings[fn]
            fixes = self.fixes[fn]
            if errors or warnings or fixes:
                click.echo(fn)
                for fix in fixes:
                    click.secho(" " + fix, fg="green")
                for err in errors:
                    click.secho(" " + err, fg="red")
                    error_count += 1
                for warning in warnings:
                    click.secho(" " + warning, fg="yellow")
            if not errors and verbose > 0:
                click.secho(fn + " OK!", fg="green")

        for err in self.check_duplicates():
            click.secho(err, fg="red")
            error_count += 1

        errors = compare_districts(self.expected, self.active_legislators)
        for err in errors:
            click.secho(err, fg="red")
            error_count += 1

        return error_count


def process_dir(
    abbr: str, verbose: bool, municipal: bool, date: str, fix: bool
) -> int:  # pragma: no cover
    legislative_filenames = glob.glob(os.path.join(get_data_dir(abbr), "legislature", "*.yml"))
    executive_filenames = glob.glob(os.path.join(get_data_dir(abbr), "executive", "*.yml"))
    municipality_filenames = glob.glob(os.path.join(get_data_dir(abbr), "municipalities", "*.yml"))
    retired_filenames = glob.glob(os.path.join(get_data_dir(abbr), "retired", "*.yml"))

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


@click.command()
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
def main(abbreviations: list[str], verbose: bool, municipal: bool, date: str, fix: bool) -> None:
    """
    Lint YAML files.

    <ABBR> can be provided to restrict linting to single state's files.
    """
    error_count = 0

    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        click.secho("==== {} ====".format(abbr), bold=True)
        error_count += process_dir(abbr, verbose, municipal, date, fix)

    if error_count:
        click.secho(f"exiting with {error_count} errors", fg="red")
        sys.exit(99)


if __name__ == "__main__":
    main()
