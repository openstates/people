#!/usr/bin/env python
import re
import os
import yaml
import glob
import click
from utils import get_data_dir
from collections import defaultdict, Counter


DATE_RE = re.compile('^\d{4}(-\d{2}(-\d{2}))$')
PHONE_RE = re.compile('^\d{3}-\d{3}-\d{4}$')
UUID_RE = re.compile('^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class Missing:
    pass


class Required:
    pass


def is_dict(val):
    return isinstance(val, dict)


def is_string(val):
    return isinstance(val, str)


def is_url(val):
    return is_string(val) and val.startswith('http')


def is_fuzzy_date(val):
    return is_string(val) and DATE_RE.match(val)


def is_phone(val):
    return is_string(val) and PHONE_RE.match(val)


def is_uuid(val):
    return is_string(val) and UUID_RE.match(val)


CONTACT_DETAILS = {
    'note': [is_string, Required],
    'address': [is_string],
    'email': [is_string],
    'voice': [is_phone],
    'fax': [is_phone],
}


PERSON_FIELDS = {
    'id': [is_uuid],
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
    'links': {
        'note': [is_string],
        'url': [is_url, Required],
    },
    'identifiers': {
        'identifier': [is_string, Required],
        'scheme': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    },
    'other_names': {
        'name': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    },
    'sources': {
        'note': [is_string],
        'url': [is_url, Required],
    },
    'committees': {
        'name': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    },
    'party': {
        'name': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    },
    'roles': {
        'chamber': [is_string, Required],
        'district': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
        'contact_details': CONTACT_DETAILS,
    },
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
            if Required in validators:
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
            # validate list elements against child schema
            for index, item in enumerate(value):
                errors.extend(validate_obj(item, validators, [field, str(index)]))
        else:
            raise Exception('invalid schema {}'.format(validators))

    # check for extra items that went without validation
    for key in set(obj.keys()) - set(schema.keys()):
        errors.append(f'extra key: {prefix_str}{key}')

    return errors


def role_is_active(role):
    if role.get('end_date') is None:
        return True


def get_aggregate_stats(person):
    chamber = None
    district = None
    party = []

    for role in person['roles']:
        if role_is_active(role):
            chamber = role['chamber']
            district = role['district']

    for role in person['party']:
        if role_is_active(role):
            party.append(role['name'])

    return {'chamber': chamber, 'district': district, 'party': party}


def get_expected_districts(settings):
    expected = {}
    for key in ('upper', 'lower', 'legislature'):
        seats = settings.get(key + '_seats')
        if not seats:
            continue
        elif isinstance(seats, int):
            # one seat per district by default
            expected[key] = {str(s): 1 for s in range(1, seats+1)}
        else:
            expected[key] = seats
    return expected


def compare_districts(expected, actual):
    errors = []

    if expected.keys() != actual.keys():
        errors.append(f'expected districts for {expected.keys()}, got {actual.keys()}')
        return errors

    for chamber in expected:
        expected_districts = set(expected[chamber].keys())
        actual_districts = set(actual[chamber].keys())
        for district in sorted(expected_districts - actual_districts):
            errors.append(f'missing legislator for {chamber} {district}')
        for district in sorted(actual_districts - expected_districts):
            errors.append(f'extra legislator for unexpected seat {chamber} {district}')
        for district in sorted(actual_districts & expected_districts):
            if actual[chamber][district] < expected[chamber][district]:
                errors.append(f'missing legislator for {chamber} {district}')
            if actual[chamber][district] > expected[chamber][district]:
                errors.append(f'extra legislator for {chamber} {district}')
    return errors


def process_state(state, verbose, settings):
    filenames = glob.glob(os.path.join(get_data_dir(state), '*.yml'))
    chamber_districts = defaultdict(Counter)
    parties = Counter()

    expected = get_expected_districts(settings)

    for filename in filenames:
        print_filename = os.path.basename(filename)
        with open(filename) as f:
            person = yaml.load(f)
            errors = validate_obj(person, PERSON_FIELDS)

            # increment counts for state-level validation
            agg = get_aggregate_stats(person)
            chamber_districts[agg['chamber']][agg['district']] += 1
            parties.update(agg['party'])

            if errors:
                click.echo(print_filename)
            for err in errors:
                click.secho(' ' + err, fg='red')
            if not errors and verbose > 0:
                click.secho(print_filename, 'OK!', fg='green')

    for err in compare_districts(expected, chamber_districts):
        click.secho(err, fg='red')


@click.command()
@click.argument('state')
@click.option('-v', '--verbose', count=True)
def lint(state, verbose):
    with open(get_data_dir('state-settings.yml')) as f:
        state_settings = yaml.load(f)

    process_state(state, verbose, state_settings[state])


if __name__ == '__main__':
    lint()
