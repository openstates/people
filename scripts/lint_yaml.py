#!/usr/bin/env python
import re
import os
import yaml
import glob
import datetime
import click
from utils import get_data_dir
from collections import defaultdict, Counter


DATE_RE = re.compile(r'^\d{4}(-\d{2}(-\d{2})?)?$')
PHONE_RE = re.compile(r'^(1-)?\d{3}-\d{3}-\d{4}$')
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
LEGACY_OS_ID_RE = re.compile(r'[A-Z]{2}L\d{6}')


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
    return isinstance(val, str)


def is_url(val):
    return is_string(val) and val.startswith('http')


def is_social(val):
    return is_string(val) and not val.startswith(('http://', 'https://', '@'))


def is_fuzzy_date(val):
    return is_string(val) and DATE_RE.match(val)


def is_phone(val):
    return is_string(val) and PHONE_RE.match(val)


def is_uuid(val):
    return is_string(val) and UUID_RE.match(val)


def is_legacy_openstates(val):
    return is_string(val) and LEGACY_OS_ID_RE.match(val)


CONTACT_DETAILS = NestedList({
    'note': [is_string, Required],
    'address': [is_string],
    'email': [is_string],
    'voice': [is_phone],
    'fax': [is_phone],
})

URL_LIST = NestedList({
    'note': [is_string],
    'url': [is_url, Required],
})


PERSON_FIELDS = {
    'id': [is_uuid, Required],
    'name': [is_string, Required],
    'sort_name': [is_string],
    'given_name': [is_string],
    'family_name': [is_string],
    'gender': [is_string],
    'summary': [is_string],
    'biography': [is_string],
    'birth_date': [is_fuzzy_date],
    'death_date': [is_fuzzy_date],
    'image': [is_url],
    'contact_details': CONTACT_DETAILS,
    'links': URL_LIST,
    'ids': {
        'twitter': [is_social],
        'youtube': [is_social],
        'instagram': [is_social],
        'facebook': [is_social],
        'legacy_openstates': [is_legacy_openstates],
    },
    'extra_identifiers': NestedList({
        'identifier': [is_string, Required],
        'scheme': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    }),
    'other_names': NestedList({
        'name': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    }),
    'sources': URL_LIST,
    'committees': NestedList({
        'name': [is_string, Required],
        'post': [is_string],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    }),
    'party': NestedList({
        'name': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    }),
    'roles': NestedList({
        'chamber': [is_string, Required],
        'district': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
        'contact_details': CONTACT_DETAILS,
    }),
    'extras': [is_dict],
}


def validate_obj(obj, schema, prefix=None):
    errors = []

    if prefix:
        prefix_str = '.'.join(prefix) + '.'
    else:
        prefix_str = ''

    for field, validators in schema.items():
        value = obj.get(field, Missing)

        if value is Missing:
            if isinstance(validators, list) and Required in validators:
                errors.append(f'{prefix_str}{field} missing')
            # error or not, don't run other validators against missing fields
            continue

        if isinstance(validators, list):
            for validator in validators:
                # required is checked above
                if validator is Required:
                    continue
                if not validator(value):
                    errors.append(
                        f'{prefix_str}{field} failed validation {validator.__name__}: {value}'
                    )
        elif isinstance(validators, dict):
            errors.extend(validate_obj(value, validators, [field]))
        elif isinstance(validators, NestedList):
            # validate list elements against child schema
            for index, item in enumerate(value):
                errors.extend(validate_obj(item, validators.subschema, [field, str(index)]))
        else:
            raise Exception('invalid schema {}'.format(validators))

    # check for extra items that went without validation
    for key in set(obj.keys()) - set(schema.keys()):
        errors.append(f'extra key: {prefix_str}{key}')

    return errors


def role_is_active(role):
    now = datetime.datetime.utcnow().date().strftime('%Y-%m-%d')
    return role.get('end_date') is None or role.get('end_date') > now


def validate_roles(person, roles_key):
    active = [role for role in person[roles_key] if role_is_active(role)]
    if len(active) == 0:
        return [f'no active {roles_key}']
    elif roles_key == 'roles' and len(active) > 1:
        return [f'{len(active)} active roles']
    return []


def get_expected_districts(settings):
    expected = {}
    for key in ('upper', 'lower', 'legislature'):
        seats = settings.get(key + '_seats')
        if not seats:
            continue
        elif isinstance(seats, int):
            # one seat per district by default
            expected[key] = {str(s): 1 for s in range(1, seats+1)}
        elif isinstance(seats, list):
            expected[key] = {s: 1 for s in seats}
        elif isinstance(seats, dict):
            expected[key] = seats
        else:
            raise ValueError(seats)
    return expected


def compare_districts(expected, actual):
    errors = []
    warnings = []

    if expected.keys() != actual.keys():
        errors.append(f'expected districts for {expected.keys()}, got {actual.keys()}')
        return errors

    for chamber in expected:
        expected_districts = set(expected[chamber].keys())
        actual_districts = set(actual[chamber].keys())
        for district in sorted(expected_districts - actual_districts):
            warnings.append(f'missing legislator for {chamber} {district}')
        for district in sorted(actual_districts - expected_districts):
            errors.append(f'extra legislator for unexpected seat {chamber} {district}')
        for district in sorted(actual_districts & expected_districts):
            if actual[chamber][district] < expected[chamber][district]:
                warnings.append(f'missing legislator for {chamber} {district}')
            if actual[chamber][district] > expected[chamber][district]:
                errors.append(f'extra legislator for {chamber} {district}')
    return errors, warnings


class Validator:
    OPTIONAL_FIELD_SET = set(('sort_name', 'given_name', 'family_name',
                              'gender', 'summary', 'biography',
                              'birth_date', 'death_date', 'image',
                              'links', 'other_names', 'sources',
                              ))

    def __init__(self, settings, state):
        self.http_whitelist = tuple(settings['http_whitelist'])
        self.expected = get_expected_districts(settings[state])
        self.errors = defaultdict(list)
        self.warnings = defaultdict(list)
        self.count = 0
        self.parties = Counter()
        self.committees = Counter()
        self.contact_counts = Counter()
        self.id_counts = Counter()
        self.optional_fields = Counter()
        self.extra_counts = Counter()
        self.chamber_districts = defaultdict(Counter)

    def validate_person(self, person, filename):
        self.errors[filename] = validate_obj(person, PERSON_FIELDS)
        self.errors[filename].extend(validate_roles(person, 'roles'))
        self.errors[filename].extend(validate_roles(person, 'party'))
        self.warnings[filename] = self.check_https(person)
        self.summarize_person(person)

    def check_https_url(self, url):
        if url and url.startswith('http://') and not url.startswith(self.http_whitelist):
            return False
        return True

    def check_https(self, person):
        warnings = []
        if not self.check_https_url(person.get('image')):
            warnings.append(f'image URL {person["image"]} should be HTTPS')
        for i, url in enumerate(person.get('links', [])):
            url = url['url']
            if not self.check_https_url(url):
                warnings.append(f'links.{i} URL {url} should be HTTPS')
        for i, url in enumerate(person.get('sources', [])):
            url = url['url']
            if not self.check_https_url(url):
                warnings.append(f'sources.{i} URL {url} should be HTTPS')
        return warnings

    def summarize_person(self, person):
        chamber = None
        district = None

        self.count += 1
        self.optional_fields.update(set(person.keys()) & self.OPTIONAL_FIELD_SET)
        self.extra_counts.update(person.get('extras', {}).keys())

        for role in person.get('roles', []):
            if role_is_active(role):
                chamber = role['chamber']
                district = role['district']
                break
        self.chamber_districts[chamber][district] += 1

        for role in person.get('party', []):
            if role_is_active(role):
                self.parties[role['name']] += 1

        for role in person.get('committees', []):
            if role_is_active(role):
                self.committees[role['name']] += 1

        for cd in person.get('contact_details', []):
            for key in cd:
                if key != 'note':
                    self.contact_counts[key] += 1

        for scheme in person.get('ids', {}):
            self.id_counts[scheme] += 1
        for id in person.get('extra_identifiers', []):
            self.id_counts[id['scheme']] += 1

    def print_validation_report(self, verbose):
        for fn, errors in self.errors.items():
            warnings = self.warnings[fn]
            if errors or warnings:
                click.echo(fn)
                for err in errors:
                    click.secho(' ' + err, fg='red')
                for warning in warnings:
                    click.secho(' ' + warning, fg='yellow')
            if not errors and verbose > 0:
                click.secho(fn, 'OK!', fg='green')

        errors, warnings = compare_districts(self.expected, self.chamber_districts)
        for err in errors:
            click.secho(err, fg='red')
        for warning in warnings:
            click.secho(warning, fg='yellow')

    def print_summary(self):
        click.secho(f'processed {self.count} files', bold=True)
        upper = sum(self.chamber_districts['upper'].values())
        lower = sum(self.chamber_districts['lower'].values())
        click.secho(f'{upper:4d} upper\n{lower:4d} lower')

        click.secho('Parties', bold=True)
        for party, count in self.parties.items():
            if party == 'Republican':
                color = 'red'
            elif party == 'Democratic':
                color = 'blue'
            else:
                color = 'green'
            click.secho(f'{count:4d} {party} ', bg=color)

        click.secho('Committees', bold=True)
        for com, count in sorted(self.committees.items(),
                                 key=lambda x: x[1], reverse=True):
            click.secho(f'{count:4d} {com} ')

        for name, collection in {'Contact Info': self.contact_counts,
                                 'Identifiers': self.id_counts,
                                 'Additional Info': self.optional_fields,
                                 'Extras': self.extra_counts}.items():
            if collection:
                click.secho(name, bold=True)
                for type, count in collection.items():
                    click.secho(f'{count:4d} {type} ')
            else:
                click.secho(name + ' - none', bold=True)


def process_state(state, verbose, summary, settings):
    filenames = glob.glob(os.path.join(get_data_dir(state), '*.yml'))
    validator = Validator(settings, state)

    for filename in filenames:
        print_filename = os.path.basename(filename)
        with open(filename) as f:
            person = yaml.load(f)
            validator.validate_person(person, print_filename)

    validator.print_validation_report(verbose)

    # summary
    if summary:
        validator.print_summary()


@click.command()
@click.argument('state', default='*')
@click.option('-v', '--verbose', count=True)
@click.option('--summary/--no-summary', default=False)
def lint(state, verbose, summary):
    with open(get_data_dir('state-settings.yml')) as f:
        settings = yaml.load(f)
    if state == '*':
        states = [os.path.basename(d)
                  for d in glob.glob(os.path.join(get_data_dir(''), '*/'))]
        for state in states:
            process_state(state, verbose, summary, settings)
    else:
        process_state(state, verbose, summary, settings)


if __name__ == '__main__':
    lint()
