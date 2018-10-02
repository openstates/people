import pytest
import uuid
from lint_yaml import (is_url, is_social, is_fuzzy_date, is_phone, is_uuid, is_legacy_openstates,
                       validate_obj, PERSON_FIELDS, role_is_active, validate_roles,
                       get_expected_districts, compare_districts, Validator) # noqa


def test_is_url():
    assert is_url('http://example.com')
    assert is_url('https://example.com')
    assert not is_url('/fragment')


def test_is_social():
    assert is_social('example_id')
    assert not is_social('@no_at_sign')
    assert not is_social('http://no-urls.com')


def test_is_fuzzy_date():
    assert is_fuzzy_date('2010')
    assert is_fuzzy_date('2019-01')
    assert is_fuzzy_date('2020-01-01')
    assert not is_fuzzy_date('1/1/2011')


def test_is_phone():
    assert is_phone('123-346-7990')
    assert is_phone('1-123-346-7990')
    assert is_phone('1-123-346-7990 ext. 123')
    assert not is_phone('(123) 346-7990')


def test_is_uuid():
    assert is_uuid('abcdef98-0123-7777-8888-1234567890ab')
    assert not is_uuid('abcdef980123777788881234567890ab')


def test_is_legacy_openstates():
    assert is_legacy_openstates('AKL000001')
    assert not is_legacy_openstates('AK000001')
    assert not is_legacy_openstates('AK001')


def test_validate_required():
    example = {
        'id': str(uuid.uuid4()),
        'name': 'Anne A',
    }

    # with required fields
    assert validate_obj(example, PERSON_FIELDS) == []

    errs = validate_obj({}, PERSON_FIELDS)
    assert len(errs) == 2
    assert 'id missing' in errs


def test_validate_nested_required():
    example = {
        'id': str(uuid.uuid4()),
        'name': 'Anne A',
        'links': [
            {'url': 'https://example.com'},
            {'note': 'note only'},
        ]
    }

    assert validate_obj(example, PERSON_FIELDS) == [
        'links.1.url missing'
    ]


def test_validate_nested_list():
    example = {
        'id': str(uuid.uuid4()),
        'name': 'Anne A',
        'links': [
            {'url': 'example.com'},
        ]
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 1
    assert 'links.0.url' in errs[0]


def test_validate_nested_object():
    example = {
        'id': str(uuid.uuid4()),
        'name': 'Anne A',
        'ids': {
            'twitter': '@bad-name',
            'youtube': 'is-ok',
        }
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 1
    assert 'ids.twitter' in errs[0]


def test_validate_extra_keys_not_present():
    example = {
        'id': str(uuid.uuid4()),
        'name': 'Anne A',
        'junk': 100,
        'links': [
            {'url': 'https://example.com', 'bad': 100},
        ]
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 2
    assert 'extra key: junk' in errs
    assert 'extra key: links.0.bad' in errs


@pytest.mark.parametrize("role,expected", [
    ({"name": "A"}, True),
    ({"name": "B", "end_date": None}, True),
    ({"name": "C", "end_date": "1990-01-01"}, False),
    ({"name": "D", "end_date": "2100-01-01"}, True),
])
def test_role_is_active(role, expected):
    assert role_is_active(role) == expected


@pytest.mark.parametrize("person,expected", [
    ({"party": [{"name": "Democratic"}]}, []),
    ({"party": [{"name": "Democratic"}, {"name": "Working Families"}]}, []),
    ({"party": []}, ["no active party"]),
    ({"party": [{"name": "Democratic", "end_date": "1990"}]}, ["no active party"]),
])
def test_validate_roles_party(person, expected):
    assert validate_roles(person, "party") == expected


@pytest.mark.parametrize("person,expected", [
    ({"roles": [{"name": "House"}]}, []),
    ({"roles": [{"name": "House"}, {"name": "Senate"}]}, ["2 active roles"]),
    ({"roles": []}, ["no active roles"]),
    ({"roles": [{"name": "House", "end_date": "1990"}]}, ["no active roles"]),
])
def test_validate_roles_roles(person, expected):
    assert validate_roles(person, "roles") == expected


def test_get_expected_districts():
    expected = get_expected_districts({"upper_seats": 3,
                                       "lower_seats": ["A", "B", "C"],
                                       "legislature_seats": {"At-Large": 3}})
    assert expected['upper'] == {"1": 1, "2": 1, "3": 1}
    assert expected['lower'] == {"A": 1, "B": 1, "C": 1}
    assert expected['legislature'] == {"At-Large": 3}


@pytest.mark.parametrize("expected,actual,errors,warnings", [
    ({"A": 1, "B": 1}, {"A": 1, "B": 1}, 0, 0),     # good
    ({"A": 1}, {"A": 1, "B": 1}, 1, 0),             # extra district
    ({"A": 1, "B": 1}, {"A": 1}, 0, 1),             # missing district
    ({"A": 1, "B": 1}, {"A": 0, "B": 1}, 0, 1),     # missing leg
    ({"A": 1, "B": 1}, {"A": 2, "B": 1}, 1, 0),     # extra leg
    ({"A": 5, "B": 3}, {"A": 3, "B": 5}, 1, 1),     # mix of both
])
def test_compare_districts(expected, actual, errors, warnings):
    e, w = compare_districts({"upper": expected}, {"upper": actual})
    assert len(e) == errors
    assert len(w) == warnings


def test_validator_check_https():
    settings = {'us': {'upper_seats': 100, 'lower_seats': 435},
                'http_whitelist': ['http://bad.example.com']}
    v = Validator(settings, 'us')

    person = {'links': [
        {'url': 'https://example.com'},
        {'url': 'http://insecure.example.com'},
        {'url': 'https://bad.example.com'},
    ]}
    warnings = v.check_https(person)
    assert len(warnings) == 1
    assert 'links.1' in warnings[0]


def test_validator_summary():
    settings = {'us': {'upper_seats': 100, 'lower_seats': 435},
                'http_whitelist': ['http://bad.example.com']}
    v = Validator(settings, 'us')

    people = [
        {'gender': 'F', 'image': 'https://example.com/image1',
         'party': [{'name': 'Democratic'}, {'name': 'Democratic', 'end_date': '1990'}],
         },
        {'gender': 'F', 'image': 'https://example.com/image2',
         'party': [{'name': 'Democratic'}, {'name': 'Working Families'}],
         'extras': {'religion': 'Zoroastrian'},
         'contact_details': [{'fax': '123-456-7890'}],
         'other_identifiers': [{'scheme': 'fake', 'identifier': 'abc'}],
         'ids': {'twitter': 'fake'},
         },
        {'gender': 'M', 'image': 'https://example.com/image3',
         'party': [{'name': 'Republican'}],
         'committees': [{'name': 'Finance'}],
         'contact_details': [{'phone': '123-456-7890'}],
         'other_identifiers': [{'scheme': 'fake', 'identifier': '123'}],
         },
    ]

    for p in people:
        v.summarize_person(p)

    assert v.parties == {'Republican': 1, 'Democratic': 2,
                         'Working Families': 1}
    assert v.committees == {'Finance': 1}
    assert v.contact_counts == {'phone': 1, 'fax': 1}
    assert v.id_counts == {'fake': 2, 'twitter': 1}
    assert v.optional_fields == {'gender': 3, 'image': 3}
    assert v.extra_counts == {'religion': 1}
