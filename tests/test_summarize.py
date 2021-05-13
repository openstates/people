from ospeople.cli.people import Summarizer
from ospeople.models.people import (
    Person,
    Party,
    ContactDetail,
    OtherIdentifier,
    PersonIdBlock,
)
from ospeople.utils import ocd_uuid


def test_person_summary():
    s = Summarizer()

    people = [
        Person(
            id=ocd_uuid("person"),
            name="Jorna Corno",
            gender="F",
            image="https://example.com/image1",
            party=[Party(name="Democratic"), Party(name="Democratic", end_date="1990")],
            roles=[],
        ),
        Person(
            id=ocd_uuid("person"),
            name="Linda Under",
            gender="F",
            image="https://example.com/image2",
            party=[Party(name="Democratic"), Party(name="Progressive")],
            extras={"religion": "Zoroastrian"},
            contact_details=[ContactDetail(fax="123-435-9999", note="Capitol Office")],
            other_identifiers=[OtherIdentifier(scheme="fake", identifier="abc")],
            ids=PersonIdBlock(twitter="fake"),
            roles=[],
        ),
        Person(
            id=ocd_uuid("person"),
            name="Phil Gort",
            gender="M",
            image="https://example.com/image3",
            party=[Party(name="Republican")],
            contact_details=[ContactDetail(voice="123-435-9999", note="Capitol Office")],
            other_identifiers=[OtherIdentifier(scheme="fake", identifier="123")],
            roles=[],
        ),
    ]

    for p in people:
        s.summarize(p)

    assert s.parties == {"Republican": 1, "Democratic": 2, "Progressive": 1}
    assert s.contact_counts == {"Capitol Office voice": 1, "Capitol Office fax": 1}
    assert s.id_counts == {"fake": 2, "twitter": 1}
    assert s.optional_fields == {"gender": 3, "image": 3}
    assert s.extra_counts == {"religion": 1}
