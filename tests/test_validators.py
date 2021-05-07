import pytest
from ospeople.models.common import validate_ocd_person, validate_str_no_newline


def test_validate_ocd_person():
    good_id = "ocd-person/abcdef98-0123-7777-8888-1234567890ab"
    assert validate_ocd_person(good_id) == good_id
    with pytest.raises(ValueError):
        validate_ocd_person("abcdef98-0123-7777-8888-1234567890ab")
    with pytest.raises(ValueError):
        validate_ocd_person("ocd-person/abcdef980123777788881234567890ab")


def test_validate_str_no_newline():
    assert validate_str_no_newline("long string with no breaks") == "long string with no breaks"
    with pytest.raises(ValueError):
        validate_str_no_newline("simple\nbad")
