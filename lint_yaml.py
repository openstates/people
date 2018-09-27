class Missing:
    pass

class Required:
    pass


def is_string(val):
    return isinstance(val, str)


def is_url(val):
    return is_string(val) and val.startswith('http')


def is_fuzzy_date(val):
    return is_string(val)  # TODO


def is_phone(val):
    return is_string(val)  # TODO


PERSON_FIELDS = {
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
        'voice': [is_phone],
        'fax': [is_phone],
        'address': [is_string],
        'email': [is_string],
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
    # 'committees': [],
    'party': {
        'name': [is_string, Required],
        'start_date': [is_fuzzy_date],
        'end_date': [is_fuzzy_date],
    },
    'terms': {
        'chamber': ['lower', 'upper'],
    },
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
            continue

        if isinstance(validators, list):
            for validator in validators:
                # don't call any method for Required check
                if validator is Required:
                    continue
                if not validator(value):
                    errors.append(f'{prefix_str}{field} failed validation {validator.__name__}: {value}')
        elif isinstance(validators, dict):
            # validate list elements against child schema
            for index, item in enumerate(value):
                errors.extend(validate_obj(item, validators, [field, str(index)]))
        else:
            print('error', field, validators)
    return errors

for err in validate_obj({'name': 'James', 'contact_details': [{'voice': 3}]}, PERSON_FIELDS):
    print(err)
