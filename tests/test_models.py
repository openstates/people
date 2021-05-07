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
from ospeople.models.people import (
    Person,
    Party,
    RoleType,
    ContactType,
    ContactDetail,
    PersonIdBlock,
    Role,
)
from ospeople.models.committees import (
    Membership,
    ScrapeCommittee,
    Committee,
)

VALID_PERSON_ID = "ocd-person/abcdef98-0123-7777-8888-1234567890ab"
VALID_ORG_ID = "ocd-organization/abcdef98-0123-7777-8888-1234567890ab"
VALID_JURISDICTION_ID = "ocd-jurisdiction/country:us/state:nc/government"


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
        (validate_ocd_person, VALID_PERSON_ID, True),
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


def test_person_basics():
    with pytest.raises(ValidationError):
        Person(name="missing fields")
    good = Person(
        id="ocd-person/11111111-2222-3333-4444-555555555555",
        name="Joan Jones",
        party=[Party(name="Democratic")],
        roles=[],
    )
    assert good.name
    with pytest.raises(ValidationError):
        good.death_date = "X"
    with pytest.raises(ValidationError):
        good.birth_date = "X"
    with pytest.raises(ValidationError):
        good.birth_date = "X"
    with pytest.raises(ValidationError):
        good.id = "123"
    with pytest.raises(ValidationError):
        good.image = "/fragment"


def test_person_commas():
    with pytest.raises(ValidationError):
        Person(
            id="ocd-person/11111111-2222-3333-4444-555555555555",
            name="Jones, Joan",
            party=[Party(name="Democratic")],
            roles=[],
        )
    good_comma = Person(
        id="ocd-person/11111111-2222-3333-4444-555555555555",
        name="Joan Jones, Jr.",
        party=[Party(name="Democratic")],
        roles=[],
    )
    assert good_comma.name


def test_party():
    party = Party(name="Democratic")
    assert party.name
    with pytest.raises(ValidationError):
        party.end_date = "x"


def test_contact_detail():
    # need at least one type
    with pytest.raises(ValidationError):
        ContactDetail(note=ContactType.DISTRICT)
    cd = ContactDetail(note=ContactType.DISTRICT, address="123 Boogie Woogie Ave")
    with pytest.raises(ValidationError):
        cd.address = "123 Boogie Woogie Avenue\nSpringfield, MA"
    with pytest.raises(ValidationError):
        cd.voice = "911"
    cd.fax = "919-555-1234"
    cd.voice = "1-123-555-6666 ext. 3333"
    with pytest.raises(ValidationError):
        cd.fax = "911"
    # no such field
    with pytest.raises(ValueError):
        cd.phone = "911"


def test_person_id_block():
    assert PersonIdBlock(twitter="realFoolish")
    with pytest.raises(ValidationError):
        PersonIdBlock(twitter="@realFoolish")
    with pytest.raises(ValidationError):
        PersonIdBlock(youtube="https://youtube.com/test")


def test_role_basics():
    with pytest.raises(ValidationError):
        Role(type=RoleType.UPPER, jurisdiction="us")
    with pytest.raises(ValidationError):
        Role(type=RoleType.UPPER, jurisdiction=VALID_JURISDICTION_ID, end_reason="stuff\nhere")


def test_role_conditional_requires():
    assert Role(
        type=RoleType.UPPER, district=4, end_date="2010", jurisdiction=VALID_JURISDICTION_ID
    )
    assert Role(
        type=RoleType.GOVERNOR,
        start_date="2010",
        end_date="2016",
        jurisdiction=VALID_JURISDICTION_ID,
    )

    with pytest.raises(ValidationError):
        assert Role(type=RoleType.UPPER, end_date="2010", jurisdiction=VALID_JURISDICTION_ID)

    with pytest.raises(ValidationError):
        assert Role(type=RoleType.GOVERNOR, start_date="2010", jurisdiction=VALID_JURISDICTION_ID)


def test_committee_membership():
    assert Membership(name="Franz Ferdinand", role="member")
    assert Membership(name="Franz Ferdinand", role="member", person_id=VALID_PERSON_ID)
    with pytest.raises(ValidationError):
        Membership(name="No Role", person_id=VALID_PERSON_ID)
    with pytest.raises(ValidationError):
        Membership(name="Bad ID", role="chair", person_id="123")


def test_scrapecommittee():
    assert ScrapeCommittee(name="Health", parent="upper")
    with pytest.raises(ValidationError):
        ScrapeCommittee(name="Health \n Roads", parent="upper")


def test_committee():
    assert Committee(
        name="Health", parent="upper", id=VALID_ORG_ID, jurisdiction=VALID_JURISDICTION_ID
    )
    with pytest.raises(ValidationError):
        Committee(name="Health", parent="upper", id="123", jurisdiction=VALID_JURISDICTION_ID)
    with pytest.raises(ValidationError):
        Committee(name="Health", parent="upper", id=VALID_ORG_ID, jurisdiction="canada")


def test_committee_dict_order():
    c = Committee(
        name="Health", parent="upper", id=VALID_ORG_ID, jurisdiction=VALID_JURISDICTION_ID
    )
    assert list(c.to_dict().keys())[:3] == ["id", "jurisdiction", "name"]
