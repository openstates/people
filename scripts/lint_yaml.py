#!/usr/bin/env python
import re
import os
import sys
import datetime
import glob
import click
from openstates import metadata
from enum import Enum, auto
from utils import (
    get_data_dir,
    role_is_active,
    get_all_abbreviations,
    load_yaml,
    legacy_districts,
    load_municipalities,
    MAJOR_PARTIES,
)
from collections import defaultdict, Counter


class BadVacancy(Exception):
    pass


class PersonType(Enum):
    LEGISLATIVE = auto()
    RETIRED = auto()
    EXECUTIVE = auto()
    MUNICIPAL = auto()


SUFFIX_RE = re.compile(r"(iii?)|(i?v)|((ed|ph|m|o)\.?d\.?)|([sj]r\.?)|(esq\.?)", re.I)
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
PHONE_RE = re.compile(r"^(1-)?\d{3}-\d{3}-\d{4}( ext. \d+)?$")
UUID_RE = re.compile(r"^ocd-\w+/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
JURISDICTION_RE = re.compile(
    r"ocd-jurisdiction/country:us/(state|district|territory):\w\w/((place|county):[a-z_]+/)?government"
)
LEGACY_OS_ID_RE = re.compile(r"[A-Z]{2}L\d{6}")


class Missing:
    pass


class Required:
    pass


class NestedList:
    def __init__(self, subschema):
        self.subschema = subschema


def is_dict(val):
    return isinstance(val, dict)


def is_string(val):
    return isinstance(val, str) and "\n" not in val


def is_multiline_string(val):
    return isinstance(val, str)


def no_bad_comma(val):
    pieces = val.split(",")
    if len(pieces) == 1:
        return True  # no comma
    elif len(pieces) > 2:
        return False  # too many commas for a suffix
    else:
        return bool(SUFFIX_RE.findall(pieces[1]))


def is_url(val):
    return is_string(val) and val.startswith(("http://", "https://", "ftp://"))


def is_social(val):
    return is_string(val) and not val.startswith(("http://", "https://", "@"))


class Enum:
    def __init__(self, *values):
        self.values = values

    def __call__(self, val):
        return is_string(val) and val in self.values

    # for display
    @property
    def __name__(self):
        return f"Enum{self.values}"


def is_fuzzy_date(val):
    return isinstance(val, datetime.date) or (is_string(val) and DATE_RE.match(val))


def is_phone(val):
    return is_string(val) and PHONE_RE.match(val)


def is_ocd_jurisdiction(val):
    return is_string(val) and JURISDICTION_RE.match(val)


def is_ocd_person(val):
    return is_string(val) and val.startswith("ocd-person/") and UUID_RE.match(val)


def is_ocd_organization(val):
    return is_string(val) and val.startswith("ocd-organization/") and UUID_RE.match(val)


def is_legacy_openstates(val):
    return is_string(val) and LEGACY_OS_ID_RE.match(val)


URL_LIST = NestedList({"note": [is_string], "url": [is_url, Required]})


CONTACT_DETAILS = NestedList(
    {
        "note": [Enum("District Office", "Capitol Office", "Primary Office"), Required],
        "address": [is_string],
        "voice": [is_phone],
        "fax": [is_phone],
    }
)


LEGISLATIVE_ROLE_FIELDS = {
    "type": [is_string, Required],
    "district": [is_string, Required],
    "jurisdiction": [is_ocd_jurisdiction, Required],
    "start_date": [is_fuzzy_date],
    "end_date": [is_fuzzy_date],
    "end_reason": [is_string],  # note: this field isn't imported to DB
    "contact_details": CONTACT_DETAILS,
}


EXECUTIVE_ROLE_FIELDS = {
    "type": [is_string, Required],
    "jurisdiction": [is_ocd_jurisdiction, Required],
    "start_date": [is_fuzzy_date],
    "end_date": [is_fuzzy_date, Required],
    "contact_details": CONTACT_DETAILS,
}


def is_role(role):
    role_type = role.get("type")
    if role_type in ("upper", "lower", "legislature"):
        return validate_obj(role, LEGISLATIVE_ROLE_FIELDS)
    elif role_type in (
        "governor",
        "lt_governor",
        "mayor",
        "chief election officer",
        "secretary of state",
    ):
        return validate_obj(role, EXECUTIVE_ROLE_FIELDS)
    else:
        return ["invalid type"]


def is_valid_parent(parent):
    return parent in ("upper", "lower", "legislature") or is_ocd_organization(parent)


ORGANIZATION_FIELDS = {
    "id": [is_ocd_organization, Required],
    "name": [is_string, Required],
    "jurisdiction": [is_ocd_jurisdiction, Required],
    "parent": [is_valid_parent, Required],
    "classification": [is_string, Required],  # TODO: tighten this
    "memberships": NestedList(
        {
            "id": [is_ocd_person],
            "name": [is_string, Required],
            "role": [is_string],
            "start_date": [is_fuzzy_date],
            "end_date": [is_fuzzy_date],
        }
    ),
    "sources": URL_LIST,
    "links": URL_LIST,
}

PERSON_FIELDS = {
    "id": [is_ocd_person, Required],
    "name": [is_string, no_bad_comma, Required],
    "sort_name": [is_string],
    "given_name": [is_string],
    "family_name": [is_string],
    "middle_name": [is_string],
    "email": [is_string],
    "suffix": [is_string],
    "gender": [is_string],
    "biography": [is_multiline_string],
    "birth_date": [is_fuzzy_date],
    "death_date": [is_fuzzy_date],
    "image": [is_url],
    "contact_details": CONTACT_DETAILS,
    "links": URL_LIST,
    "ids": {
        "twitter": [is_social],
        "youtube": [is_social],
        "instagram": [is_social],
        "facebook": [is_social],
        "legacy_openstates": [is_legacy_openstates],
    },
    "other_identifiers": NestedList(
        {
            "identifier": [is_string, Required],
            "scheme": [is_string, Required],
            "start_date": [is_fuzzy_date],
            "end_date": [is_fuzzy_date],
        }
    ),
    "other_names": NestedList(
        {"name": [is_string, Required], "start_date": [is_fuzzy_date], "end_date": [is_fuzzy_date]}
    ),
    "sources": URL_LIST,
    "party": NestedList(
        {"name": [is_string, Required], "start_date": [is_fuzzy_date], "end_date": [is_fuzzy_date]}
    ),
    "roles": NestedList(is_role),
    "extras": [is_dict],
}


def validate_obj(obj, schema, prefix=None):
    errors = []

    if prefix:
        prefix_str = ".".join(prefix) + "."
    else:
        prefix_str = ""

    for field, validators in schema.items():
        if not isinstance(obj, dict):
            raise ValueError(f"{prefix_str} is not a dictionary")
            continue
        value = obj.get(field, Missing)

        if value is Missing:
            if isinstance(validators, list) and Required in validators:
                errors.append(f"{prefix_str}{field} missing")
            # error or not, don't run other validators against missing fields
            continue

        if isinstance(validators, list):
            for validator in validators:
                # required is checked above
                if validator is Required:
                    continue
                if not validator(value):
                    errors.append(
                        f"{prefix_str}{field} failed validation {validator.__name__}: {value}"
                    )
        elif isinstance(validators, dict):
            errors.extend(validate_obj(value, validators, [field]))
        elif isinstance(validators, NestedList):
            if isinstance(validators.subschema, dict):
                # validate list elements against child schema
                for index, item in enumerate(value):
                    errors.extend(validate_obj(item, validators.subschema, [field, str(index)]))
            else:
                # subschema can also be a validation function
                for index, item in enumerate(value):
                    errors.extend(
                        [
                            ".".join([field, str(index)]) + ": " + e
                            for e in validators.subschema(item)
                        ]
                    )
        else:  # pragma: no cover
            raise ValueError("invalid schema {}".format(validators))

    # check for extra items that went without validation
    for key in set(obj.keys()) - set(schema.keys()):
        errors.append(f"extra key: {prefix_str}{key}")

    return errors


def validate_roles(person, roles_key, retired=False, date=None):
    active = [role for role in person.get(roles_key, []) if role_is_active(role, date=date)]
    if len(active) == 0 and not retired:
        return [f"no active {roles_key}"]
    elif roles_key == "roles" and retired and len(active) > 0:
        return [f"{len(active)} active roles on retired person"]
    elif roles_key == "roles" and len(active) > 1:
        return [f"{len(active)} active roles"]
    return []


def validate_offices(person):
    errors = []
    contact_details = person.get("contact_details", [])
    type_counter = Counter()
    seen_values = {}
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


def validate_jurisdictions(person, municipalities):
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


def get_expected_districts(settings, abbr):
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
                "\t{chamber}-{district} (until {vacant_until})".format(**vacancy), fg="yellow"
            )
        else:
            click.secho(
                "\t{chamber}-{district} expired {vacant_until} remove & re-run".format(**vacancy),
                fg="red",
            )
            raise BadVacancy()

    return expected


def compare_districts(expected, actual):
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
    def __init__(self, abbr, settings):
        self.http_whitelist = tuple(settings.get("http_whitelist", []))
        self.expected = get_expected_districts(settings, abbr)
        self.valid_parties = set(settings["parties"])
        self.errors = defaultdict(list)
        self.warnings = defaultdict(list)
        # role type -> district -> filename
        self.active_legislators = defaultdict(lambda: defaultdict(list))
        # field name -> value -> filename
        self.duplicate_values = defaultdict(lambda: defaultdict(list))
        self.legacy_districts = legacy_districts(abbr=abbr)
        self.municipalities = [m["id"] for m in load_municipalities(abbr=abbr)]
        for m in self.municipalities:
            if not JURISDICTION_RE.match(m):
                raise ValueError(f"invalid municipality id {m}")

    def validate_person(self, person, filename, person_type, date=None):
        self.errors[filename] = validate_obj(person, PERSON_FIELDS)
        uid = person["id"].split("/")[1]
        if uid not in filename:
            self.errors[filename].append(f"id piece {uid} not in filename")
        self.errors[filename].extend(validate_jurisdictions(person, self.municipalities))
        self.errors[filename].extend(
            validate_roles(person, "roles", person_type == PersonType.RETIRED, date=date)
        )
        if person_type in (PersonType.LEGISLATIVE, PersonType.EXECUTIVE):
            self.errors[filename].extend(validate_roles(person, "party"))

        self.errors[filename].extend(validate_offices(person))

        # active party validation
        active_parties = []
        for party in person.get("party", []):
            if party["name"] not in self.valid_parties:
                self.errors[filename].append(f"invalid party {party['name']}")
            if role_is_active(party):
                active_parties.append(party["name"])
        if len(active_parties) > 1:
            if len([party for party in active_parties if party in MAJOR_PARTIES]) > 1:
                self.errors[filename].append(
                    f"multiple active major party memberships {active_parties}"
                )
            else:
                self.warnings[filename].append(
                    f"multiple active party memberships {active_parties}"
                )

        # TODO: this was too ambitious, disabling this for now
        # self.warnings[filename] = self.check_https(person)
        if person_type == PersonType.RETIRED:
            self.errors[filename].extend(self.validate_old_district_names(person))

        # check duplicate IDs
        self.duplicate_values["openstates"][person["id"]].append(filename)
        for scheme, value in person.get("ids", {}).items():
            self.duplicate_values[scheme][value].append(filename)
        for id in person.get("other_identifiers", []):
            self.duplicate_values[id["scheme"]][id["identifier"]].append(filename)

        # update active legislators
        if person_type == PersonType.LEGISLATIVE:
            role_type = district = None
            for role in person.get("roles", []):
                if role_is_active(role, date=date):
                    role_type = role["type"]
                    district = role.get("district")
                    break
            self.active_legislators[role_type][district].append(filename)

    def validate_old_district_names(self, person):
        errors = []
        for role in person.get("roles", []):
            if (
                "district" in role
                and role["district"] not in self.expected[role["type"]]
                and role["district"] not in self.legacy_districts[role["type"]]
            ):
                errors.append(f"unknown district name: {role['type']} {role['district']}")
        return errors

    def check_https_url(self, url):
        if url and url.startswith("http://") and not url.startswith(self.http_whitelist):
            return False
        return True

    def check_https(self, person):
        warnings = []
        if not self.check_https_url(person.get("image")):
            warnings.append(f'image URL {person["image"]} should be HTTPS')
        for i, url in enumerate(person.get("links", [])):
            url = url["url"]
            if not self.check_https_url(url):
                warnings.append(f"links.{i} URL {url} should be HTTPS")
        for i, url in enumerate(person.get("sources", [])):
            url = url["url"]
            if not self.check_https_url(url):
                warnings.append(f"sources.{i} URL {url} should be HTTPS")
        return warnings

    def check_duplicates(self):
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

    def print_validation_report(self, verbose):  # pragma: no cover
        error_count = 0

        for fn, errors in self.errors.items():
            warnings = self.warnings[fn]
            if errors or warnings:
                click.echo(fn)
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


def process_dir(abbr, verbose, municipal, date):  # pragma: no cover
    legislative_filenames = glob.glob(os.path.join(get_data_dir(abbr), "legislature", "*.yml"))
    executive_filenames = glob.glob(os.path.join(get_data_dir(abbr), "executive", "*.yml"))
    municipality_filenames = glob.glob(os.path.join(get_data_dir(abbr), "municipalities", "*.yml"))
    retired_filenames = glob.glob(os.path.join(get_data_dir(abbr), "retired", "*.yml"))

    settings_file = os.path.join(os.path.dirname(__file__), "../settings.yml")
    with open(settings_file) as f:
        settings = load_yaml(f)
    try:
        validator = Validator(abbr, settings)
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
            print_filename = os.path.basename(filename)
            with open(filename) as f:
                person = load_yaml(f)
                validator.validate_person(person, print_filename, person_type, date)

    error_count = validator.print_validation_report(verbose)

    return error_count


@click.command()
@click.argument("abbreviations", nargs=-1)
@click.option("-v", "--verbose", count=True)
@click.option(
    "--municipal/--no-municipal", default=True, help="Enable/disable linting of municipal data."
)
@click.option(
    "--date", type=str, default=None, help="Lint roles using a certain date instead of today.",
)
def lint(abbreviations, verbose, municipal, date):
    """
        Lint YAML files.

        <ABBR> can be provided to restrict linting to single state's files.
    """
    error_count = 0

    if not abbreviations:
        abbreviations = get_all_abbreviations()

    for abbr in abbreviations:
        click.secho("==== {} ====".format(abbr), bold=True)
        error_count += process_dir(abbr, verbose, municipal, date)

    if error_count:
        click.secho(f"exiting with {error_count} errors", fg="red")
        sys.exit(99)


if __name__ == "__main__":
    lint()
