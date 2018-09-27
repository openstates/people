#!/usr/bin/env python

import re
import sys
import yaml


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
    'contact_details': {
        'note': [is_string, Required],
        'address': [is_string],
        'email': [is_string],
        'voice': [is_phone],
        'fax': [is_phone],
    },
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


if __name__ == '__main__':
    filenames = sys.argv[1:]

    for filename in filenames:
        with open(filename) as f:
            errors = validate_obj(yaml.load(f), PERSON_FIELDS)
            print(filename)
            for err in errors:
                print(' ', err)
            if not errors:
                print('  no errors!')
