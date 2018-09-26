def is_string(val):
    return isinstance(val, str)


def is_url(val):
    return is_string(val) and val.startswith('http')


def is_fuzzy_date(val):
    return is_string(val)  # TODO


def is_phone(val):
    return is_string(val)  # TODO


PERSON_FIELDS = {
    'name': is_string,
    'sort_name': is_string,
    'given_name': is_string,
    'family_name': is_string,
    'gender': is_string,
    'summary': is_string,
    'biography': is_string,
    'birth_date': is_fuzzy_date,
    'death_date': is_fuzzy_date,
    'image': is_url,

    'contact_details': {
        'note': is_string,
        'voice': is_phone,
        'fax': is_phone,
        'address': is_string,
        'email': is_string,
    },
    'links': {
        'note': is_string,
        'url': is_url,
    },
    'identifiers': {
        'identifier': is_string,
        'scheme': is_string,
        'start_date': is_fuzzy_date,
        'end_date': is_fuzzy_date,
    },
    'other_names': {
        'name': is_string,
        'start_date': is_fuzzy_date,
        'end_date': is_fuzzy_date,
    },

    'sources': {
        'note': is_string,
        'url': is_url,
    },
    # 'committees': [],
    'party': {
        'name': is_string,
        'start_date': is_fuzzy_date,
        'end_date': is_fuzzy_date,
    },
    'terms': {
        'chamber': ['lower', 'upper'],
    },
}


class Missing:
    pass


def validate_obj(obj, schema, prefix=None):
    errors = []

    if prefix:
        prefix_str = '.'.join(prefix) + '.'
    else:
        prefix_str = ''

    for field, validator in schema.items():
        value = obj.get(field, Missing)

        if value is Missing:
            continue

        if callable(validator):
            if not validator(value):
                errors.append(f'{prefix_str}{field} failed validation {validator.__name__}: {value}')
        elif isinstance(validator, dict):
            # validate list elements against child schema
            for index, item in enumerate(value):
                errors.extend(validate_obj(item, validator, [field, str(index)]))
        else:
            print('error', field, validator)
    return errors

for err in validate_obj({'name': 'James', 'contact_details': [{'voice': 3}]}, PERSON_FIELDS):
    print(err)
