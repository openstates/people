import pytest
import datetime
from lint_yaml import (
    is_url,
    is_social,
    is_fuzzy_date,
    is_phone,
    is_ocd_person,
    is_legacy_openstates,
    no_bad_comma,
    validate_obj,
    PERSON_FIELDS,
    validate_roles,
    validate_name,
    validate_offices,
    get_expected_districts,
    compare_districts,
    Validator,
    BadVacancy,
    PersonType,
)  # noqa


def test_is_url():
    assert is_url("http://example.com")
    assert is_url("https://example.com")
    assert not is_url("/fragment")


def test_is_social():
    assert is_social("example_id")
    assert not is_social("@no_at_sign")
    assert not is_social("http://no-urls.com")


def test_is_fuzzy_date():
    assert is_fuzzy_date("2010")
    assert is_fuzzy_date("2019-01")
    assert is_fuzzy_date("2020-01-01")
    assert not is_fuzzy_date("1/1/2011")


def test_is_phone():
    assert is_phone("123-346-7990")
    assert is_phone("1-123-346-7990")
    assert is_phone("1-123-346-7990 ext. 123")
    assert not is_phone("(123) 346-7990")


def test_no_bad_comma():
    assert no_bad_comma("John Smith")
    assert no_bad_comma("John Smith, II")
    assert no_bad_comma("John Smith, III")
    assert no_bad_comma("John Smith, Jr.")
    assert no_bad_comma("John Smith, Sr.")
    assert no_bad_comma("John Smith, PH.D.")
    assert no_bad_comma("John Smith, M.D.")
    assert no_bad_comma("John Smith, MD")
    assert no_bad_comma("Smith, John") is False
    assert no_bad_comma("Smith, J.R.") is False


def test_is_ocd_person():
    assert is_ocd_person("ocd-person/abcdef98-0123-7777-8888-1234567890ab")
    assert not is_ocd_person("abcdef98-0123-7777-8888-1234567890ab")
    assert not is_ocd_person("ocd-person/abcdef980123777788881234567890ab")


def test_is_legacy_openstates():
    assert is_legacy_openstates("AKL000001")
    assert not is_legacy_openstates("AK000001")
    assert not is_legacy_openstates("AK001")


EXAMPLE_OCD_PERSON_ID = "ocd-person/12345678-0000-1111-2222-1234567890ab"
EXAMPLE_OCD_ORG_ID = "ocd-organization/00001111-2222-3333-aaaa-444455556666"


def test_validate_required():
    example = {"id": EXAMPLE_OCD_PERSON_ID, "name": "Anne A"}

    # with required fields
    assert validate_obj(example, PERSON_FIELDS) == []

    errs = validate_obj({}, PERSON_FIELDS)
    assert len(errs) == 2
    assert "id missing" in errs


def test_validate_nested_required():
    example = {
        "id": EXAMPLE_OCD_PERSON_ID,
        "name": "Anne A",
        "links": [{"url": "https://example.com"}, {"note": "note only"}],
    }

    assert validate_obj(example, PERSON_FIELDS) == ["links.1.url missing"]


def test_validate_nested_list():
    example = {"id": EXAMPLE_OCD_PERSON_ID, "name": "Anne A", "links": [{"url": "example.com"}]}

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 1
    assert "links.0.url" in errs[0]


def test_validate_nested_role_list():
    example = {
        "id": EXAMPLE_OCD_PERSON_ID,
        "name": "Anne A",
        "roles": [
            {
                "type": "upper",
                "district": "4",
                "end_date": "2010",
                "jurisdiction": "ocd-jurisdiction/country:us/state:nc/government",
            },
            {
                "type": "governor",
                "start_date": "2010",
                "end_date": "2016",
                "jurisdiction": "ocd-jurisdiction/country:us/state:nc/government",
            },
            # bad roles
            {"type": "upper", "jurisdiction": "ocd-jurisdiction/country:us/state:nc/government"},
            {
                "type": "governor",
                "district": "4",
                "end_date": "2016",
                "jurisdiction": "ocd-jurisdiction/country:us/state:nc/government",
            },
        ],
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 2
    assert "roles.2" in errs[0]
    assert "roles.3" in errs[1]


def test_validate_nested_object():
    example = {
        "id": EXAMPLE_OCD_PERSON_ID,
        "name": "Anne A",
        "ids": {"twitter": "@bad-name", "youtube": "is-ok"},
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 1
    assert "ids.twitter" in errs[0]


def test_validate_extra_keys_not_present():
    example = {
        "id": EXAMPLE_OCD_PERSON_ID,
        "name": "Anne A",
        "junk": 100,
        "links": [{"url": "https://example.com", "bad": 100}],
    }

    errs = validate_obj(example, PERSON_FIELDS)
    assert len(errs) == 2
    assert "extra key: junk" in errs
    assert "extra key: links.0.bad" in errs


@pytest.mark.parametrize(
    "person,expected",
    [
        ({"party": [{"name": "Democratic"}]}, []),
        ({"party": [{"name": "Democratic"}, {"name": "Working Families"}]}, []),
        ({"party": []}, ["no active party"]),
        ({"party": [{"name": "Democratic", "end_date": "1990"}]}, ["no active party"]),
    ],
)
def test_validate_roles_party(person, expected):
    assert validate_roles(person, "party") == expected


@pytest.mark.parametrize(
    "person,expected",
    [
        ({"name": "Phillip J Swoozle"}, []),
        (
            {"name": "Phillip Swoozle"},
            [
                "missing given_name that could be set to 'Phillip'",
                "missing family_name that could be set to 'Swoozle'",
            ],
        ),
        (
            {"name": "Phillip Swoozle", "given_name": "Phil"},
            [
                "missing family_name that could be set to 'Swoozle'",
            ],
        ),
        (
            {"name": "Phillip Swoozle", "given_name": "Phil", "family_name": "Swoozle"},
            [],
        ),
    ],
)
def test_validate_name(person, expected):
    assert validate_name(person) == expected


@pytest.mark.parametrize(
    "person,expected",
    [
        ({"roles": [{"name": "House"}]}, []),
        ({"roles": [{"name": "House"}, {"name": "Senate"}]}, ["2 active roles"]),
        ({"roles": []}, ["no active roles"]),
        ({"roles": [{"name": "House", "end_date": "1990"}]}, ["no active roles"]),
    ],
)
def test_validate_roles_roles(person, expected):
    assert validate_roles(person, "roles") == expected


@pytest.mark.parametrize(
    "person,expected",
    [
        ({"contact_details": []}, []),
        (
            {"contact_details": [{"note": "Capitol Office"}, {"note": "Capitol Office"}]},
            ["Multiple capitol offices, condense to one."],
        ),
        ({"contact_details": [{"note": "District Office"}, {"note": "District Office"}]}, []),
        (
            {
                "contact_details": [
                    {"note": "District Office", "phone": "123"},
                    {"note": "Capitol Office", "phone": "123"},
                ]
            },
            ["Value '123' used multiple times: District Office phone and Capitol Office phone"],
        ),
    ],
)
def test_validate_offices(person, expected):
    assert validate_offices(person) == expected


@pytest.mark.parametrize(
    "person,expected",
    [
        ({"roles": [{"name": "House"}]}, ["1 active roles on retired person"]),
        ({"roles": [{"name": "House"}, {"name": "Senate"}]}, ["2 active roles on retired person"]),
        ({"roles": []}, []),
        ({"roles": [{"name": "House", "end_date": "1990"}]}, []),
    ],
)
def test_validate_roles_retired(person, expected):
    assert validate_roles(person, "roles", retired=True) == expected


def test_get_expected_districts():
    expected = get_expected_districts({}, "ne")
    assert len(expected["legislature"]) == 49
    assert expected["legislature"]["1"] == 1

    expected = get_expected_districts({}, "md")
    print(expected)
    assert expected["lower"]["3A"] == 2
    assert expected["lower"]["3B"] == 1


def test_expected_districts_vacancies():
    vacancies = {
        "ne": {
            "vacancies": [
                {
                    "chamber": "legislature",
                    "district": "1",
                    "vacant_until": datetime.date(2100, 1, 1),
                }
            ]
        }
    }
    expected = get_expected_districts(vacancies, "ne")
    assert expected["legislature"]["1"] == 0

    with pytest.raises(BadVacancy):
        get_expected_districts(
            {
                "ne": {
                    "vacancies": [
                        {
                            "chamber": "upper",
                            "district": "2",
                            "vacant_until": datetime.date(2000, 1, 1),
                        }
                    ]
                }
            },
            "ne",
        )


@pytest.mark.parametrize(
    "expected,actual,errors",
    [
        ({"A": 1, "B": 1}, {"A": ["a"], "B": ["a"]}, 0),  # good
        ({"A": 1}, {"A": ["a"], "B": ["a"]}, 1),  # extra district
        ({"A": 1, "B": 1}, {"A": ["a"]}, 1),  # missing district
        ({"A": 1, "B": 1}, {"A": [], "B": ["a"]}, 1),  # missing leg
    ],
)
def test_compare_districts(expected, actual, errors):
    e = compare_districts({"upper": expected}, {"upper": actual})
    assert len(e) == errors


def test_compare_districts_overfill():
    expected = {"A": 1}
    actual = {"A": ["Anne", "Bob"]}
    e = compare_districts({"upper": expected}, {"upper": actual})
    assert len(e) == 1
    assert "Anne" in e[0]
    assert "Bob" in e[0]


def test_validator_check_https():
    settings = {"http_allow": ["http://bad.example.com"], "parties": []}
    v = Validator("ak", settings)

    person = {
        "links": [
            {"url": "https://example.com"},
            {"url": "http://insecure.example.com"},
            {"url": "https://bad.example.com"},
        ]
    }
    warnings = v.check_https(person)
    assert len(warnings) == 1
    assert "links.1" in warnings[0]


def test_person_duplicates():
    settings = {"http_allow": ["http://bad.example.com"], "parties": []}
    v = Validator("ak", settings)

    people = [
        # duplicates across people
        {"id": "ocd-person/1", "name": "One", "ids": {"twitter": "no-twitter", "youtube": "fake"}},
        {"id": "ocd-person/2", "name": "Two", "ids": {"twitter": "no-twitter", "youtube": "fake"}},
        # duplicate on same person
        {
            "id": "ocd-person/3",
            "name": "Three",
            "ids": {"twitter": "no-twitter"},
            "other_identifiers": [
                {"scheme": "external_service_id", "identifier": "XYZ"},
                {"scheme": "external_service_id", "identifier": "XYZ"},
            ],
        },
        {"id": "ocd-person/4", "name": "Four", "ids": {"twitter": "no-twitter"}},
    ]
    for person in people:
        v.validate_person(person, person["name"] + ".yml", PersonType.LEGISLATIVE)
    errors = v.check_duplicates()
    assert len(errors) == 3
    assert 'duplicate youtube: "fake" One.yml, Two.yml' in errors
    assert 'duplicate external_service_id: "XYZ" Three.yml, Three.yml' in errors
    assert 'duplicate twitter: "no-twitter" One.yml, Two.yml, Three.yml and 1 more...' in errors


def test_filename_id_test():
    person = {"id": EXAMPLE_OCD_PERSON_ID, "name": "Jane Smith", "roles": [], "party": []}
    v = Validator("ak", {"parties": []})
    v.validate_person(person, "bad-filename", PersonType.LEGISLATIVE)
    for err in v.errors["bad-filename"]:
        if "not in filename" in err:
            break
    else:
        raise AssertionError("did not check for id in filename")
