import datetime
from os import path, walk
from pathlib import Path, PurePath
import pytest
from shutil import copytree
from unittest.mock import patch, Mock

from freezegun import freeze_time

from lint_yaml import (
    is_url,
    is_social,
    is_fuzzy_date,
    is_phone,
    is_ocd_person,
    is_legacy_openstates,
    process_dir,
    no_bad_comma,
    validate_obj,
    PERSON_FIELDS,
    validate_roles,
    validate_offices,
    get_expected_districts,
    compare_districts,
    Validator,
    ValidationResult,
    BadVacancy,
    PersonType,
)  # noqa
from utils import get_all_abbreviations, load_yaml_path
from tests.helpers import fixture_path

DEFAULT_FROZEN_TIME = datetime.datetime(2021, 1, 10, 0, 0, 0, 0)

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
    settings = {"http_whitelist": ["http://bad.example.com"], "parties": []}
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
    settings = {"http_whitelist": ["http://bad.example.com"], "parties": []}
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



def _assert_all_yaml_files_match(expect_root: str, actual_root: str) -> None:
    assert path.isdir(expect_root)
    assert path.isdir(actual_root)
    for root, dirs, files in walk(expect_root):
        for expect_f in files:
            if not expect_f.endswith(".yml"): continue
            expect_path = path.join(root, expect_f)
            expect_path_from_root = PurePath(expect_path).relative_to(expect_root)
            actual_path = path.join(actual_root, expect_path_from_root)
            assert path.isfile(actual_path)
            assert load_yaml_path(expect_path) == load_yaml_path(actual_path)


def _test_lint(
    mock_metadata_lookup: Mock,
    tmp_path,
    example: str,
    expected_validation_result = ValidationResult(),
    mock_metadata_lookup_return = {},
    retire_inactive = False,
    frozen_time = DEFAULT_FROZEN_TIME
):
    with freeze_time(frozen_time):
        # mock openstates.metadata.lookup return value,
        # so we don't need hundreds of legislator files in example
        # to avoid missing-district errors
        mock_metadata_lookup.returns = mock_metadata_lookup_return
        # root dir of test data for current example
        example_dir = fixture_path(path.join("lint", "examples", example))
        source_data = path.join(example_dir, "source_data")
        # make a tmp copy of our example source data
        # and use that to test sync_down
        test_data = path.join(tmp_path, "data")
        copytree(source_data, test_data)
        # run lint_yaml.py's process_dir on all abbrs in example
        actual_validation_result = ValidationResult()
        for abbr in get_all_abbreviations(data_root=test_data):
            process_dir(
                abbr, 
                data_root=test_data, 
                retire_inactive=retire_inactive,
                result_collector=actual_validation_result
            )
        assert actual_validation_result.to_dict() == expected_validation_result.to_dict()
        assert actual_validation_result.error_count() == expected_validation_result.error_count()
        expected_result_dir = path.join(example_dir, "expected_result")
        # if example has an 'expected_result' dir,
        # test that test_data has been updated 
        # to match expected result
        if path.isdir(expected_result_dir):
            _assert_all_yaml_files_match(
                path.join(example_dir, "expected_result"),
                test_data
            )


@patch("openstates.metadata.lookup")
def test_retires_inactive_when_option_set(
    mock_metadata_lookup: Mock, tmp_path: str
):
    _test_lint(
        mock_metadata_lookup,
        tmp_path,
        "retire_inactive_one_mayor",
        retire_inactive=True
    )


@patch("openstates.metadata.lookup")
def test_raises_error_for_no_active_roles(
    mock_metadata_lookup: Mock, tmp_path: str
):
    _test_lint(
        mock_metadata_lookup,
        tmp_path,
        "one_inactive_mayor_expect_lint_error", 
        expected_validation_result=ValidationResult(
            errors_by_filename={
                'Kathy-Meehan-748a8d71-a44f-44a4-95e0-9cd97d4431b9.yml': ['no active roles']
            }
        )
    )


@patch("openstates.metadata.lookup")
def test_raises_error_for_inconsistent_name(
    mock_metadata_lookup: Mock, tmp_path: str
):
    _test_lint(
        mock_metadata_lookup,
        tmp_path,
        "raises_error_for_inconsistent_name", 
        expected_validation_result=ValidationResult(
            errors_by_filename={
                'Lois-Richardson-5d143251-d27d-4cfe-a3dd-d9928fc5159a.yml': ['inconsistent name']
            }
        )
    )

@patch("openstates.metadata.lookup")
def test_no_inconsistent_name_if_family_name_in_name(
    mock_metadata_lookup: Mock, tmp_path: str
):
    _test_lint(
        mock_metadata_lookup,
        tmp_path,
        "no_inconsistent_name_if_family_name_in_name"
    )

@patch("openstates.metadata.lookup")
def test_no_inconsistent_name_if_given_and_family_names_unset(
    mock_metadata_lookup: Mock, tmp_path: str
):
    _test_lint(
        mock_metadata_lookup,
        tmp_path,
        "no_inconsistent_name_if_given_and_family_names_unset"
    )

"""
Appears that for persons whose names have non-english
characters (e.g. é), it's common for those characters
to be left intact in the person 'name' field
but switched to their closest english counterparts
in the person 'family_name' field. 
"""
@patch("openstates.metadata.lookup")
def test_no_inconsistent_name_non_english_chars(
    mock_metadata_lookup: Mock, tmp_path: str
):
    _test_lint(
        mock_metadata_lookup,
        tmp_path,
        "no_inconsistent_name_non_english_chars"
    )

