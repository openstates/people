import pytest
import datetime
from pydantic import ValidationError
from ospeople.models.common import (
    validate_fuzzy_date,
    validate_ocd_jurisdiction,
    validate_ocd_person,
    validate_str_no_newline,
    validate_url,
    Link,
    OtherName,
    OtherIdentifier,
)


@pytest.mark.parametrize(
    "validator,val,valid",
    [
        (validate_fuzzy_date, "2020", True),
        (validate_fuzzy_date, "2020-01", True),
        (validate_fuzzy_date, "2020-01-22", True),
        (validate_fuzzy_date, datetime.date(2020, 1, 22), True),
        (validate_fuzzy_date, "2020-1-22", False),
        (validate_fuzzy_date, "2020/1/22", False),
        (validate_fuzzy_date, "x", False),
        (validate_ocd_person, "ocd-person/abcdef98-0123-7777-8888-1234567890ab", True),
        (validate_ocd_person, "abcdef98-0123-7777-8888-1234567890ab", False),
        (validate_ocd_person, "ocd-person/abcdef980123777788881234567890ab", False),
        (validate_ocd_jurisdiction, "ocd-jurisdiction/country:us/state:nc/government", True),
        (validate_ocd_jurisdiction, "ocd-jurisdiction/country:us/state:nc", False),
        (validate_ocd_jurisdiction, "ocd-jurisdiction/country:us/state:xy/government", False),
        (validate_ocd_jurisdiction, "ocd-jurisdiction/country:us/state:nc/county:wake", False),
        (validate_str_no_newline, "long string with no breaks", True),
        (validate_str_no_newline, "multi\nline", False),
        (validate_url, "http://example.com", True),
        (validate_url, "https://example.com", True),
        (validate_url, "example.com", False),
    ],
)
def test_common_validators(validator, val, valid):
    if valid:
        assert validator(val) == val
    else:
        with pytest.raises(ValueError):
            validator(val)


def test_link():
    good = Link(url="https://example.com", note="simple note")
    assert good.url and good.note
    with pytest.raises(ValidationError):
        Link(url="bad-url")
    with pytest.raises(ValidationError):
        Link(url="https://good.url", note="no \n newlines!")
    with pytest.raises(ValidationError):
        Link(note="missing URL!")


def test_other_name():
    good = OtherName(name="fine", start_date="2021")
    assert good.name
    with pytest.raises(ValidationError):
        OtherName(name="newline \n not allowed!")
    with pytest.raises(ValidationError):
        OtherName(name="bad date", start_date="2")
    with pytest.raises(ValidationError):
        OtherName(name="bad date", end_date="2")
    with pytest.raises(ValidationError):
        OtherName(start_date="2021")


def test_other_ids():
    good = OtherIdentifier(identifier="fine", scheme="openstates", start_date="2021")
    assert good.identifier
    with pytest.raises(ValidationError):
        OtherIdentifier(identifier="newline \n not allowed!", scheme="openstates")
    with pytest.raises(ValidationError):
        OtherIdentifier(identifier="no scheme")
    with pytest.raises(ValidationError):
        OtherIdentifier(identifier="bad date", scheme="openstates", start_date="x")
    with pytest.raises(ValidationError):
        OtherIdentifier(identifier="bad date", scheme="openstates", end_date="x")
