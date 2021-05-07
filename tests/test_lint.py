import pytest
import datetime
from ospeople.cli.lint_yaml import (
    validate_name,
    validate_roles,
    validate_offices,
    get_expected_districts,
    compare_districts,
    Validator,
    BadVacancy,
    PersonType,
    PersonData,
)  # noqa


EXAMPLE_OCD_PERSON_ID = "ocd-person/12345678-0000-1111-2222-1234567890ab"
EXAMPLE_OCD_ORG_ID = "ocd-organization/00001111-2222-3333-aaaa-444455556666"


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
                "missing given_name that could be set to 'Phillip', run with --fix",
                "missing family_name that could be set to 'Swoozle', run with --fix",
            ],
        ),
        (
            {"name": "Phillip Swoozle", "given_name": "Phil"},
            [
                "missing family_name that could be set to 'Swoozle', run with --fix",
            ],
        ),
        (
            {"name": "Phillip Swoozle", "given_name": "Phil", "family_name": "Swoozle"},
            [],
        ),
    ],
)
def test_validate_name_errors(person, expected):
    assert validate_name(PersonData(person, "", ""), fix=False).errors == expected
    assert validate_name(PersonData(person, "", ""), fix=False).warnings == []
    assert validate_name(PersonData(person, "", ""), fix=False).fixes == []


def test_validate_name_fixes():
    person = PersonData({"name": "Phillip Swoozle"}, "", "")
    result = validate_name(person, fix=True)
    assert result.errors == []
    assert len(result.fixes) == 2
    assert person.data["given_name"] == "Phillip"
    assert person.data["family_name"] == "Swoozle"

    # no fixes on an OK name
    result = validate_name(person, fix=True)
    assert result.errors == result.fixes == []


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
    v = Validator("ak", settings, False)

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
    v = Validator("ak", settings, False)

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
        v.validate_person(PersonData(person, person["name"] + ".yml", PersonType.LEGISLATIVE))
    errors = v.check_duplicates()
    assert len(errors) == 3
    assert 'duplicate youtube: "fake" One.yml, Two.yml' in errors
    assert 'duplicate external_service_id: "XYZ" Three.yml, Three.yml' in errors
    assert 'duplicate twitter: "no-twitter" One.yml, Two.yml, Three.yml and 1 more...' in errors


def test_filename_id_test():
    person = {"id": EXAMPLE_OCD_PERSON_ID, "name": "Jane Smith", "roles": [], "party": []}
    v = Validator("ak", {"parties": []}, False)
    v.validate_person(PersonData(person, "bad-filename", PersonType.LEGISLATIVE))
    for err in v.errors["bad-filename"]:
        if "not in filename" in err:
            break
    else:
        raise AssertionError("did not check for id in filename")
