from ospeople.utils.retire import retire_person
from ospeople.models.people import Person, Role, Party

JID = "ocd-jurisdiction/country:us/state:nc/government"


def test_retire_person():
    person = Person(
        id="ocd-person/11110000-2222-3333-4444-555555555555",
        name="Test Person",
        party=[
            Party(name="Democratic"),
        ],
        roles=[
            Role(
                type="lower", end_date="2000-01-01", district="1", jurisdiction=JID
            ),  # leave old end date alone
            Role(
                type="upper", start_date="2018-01-01", district="2", jurisdiction=JID
            ),  # add end date
            Role(
                type="governor", end_date="2030-01-01", jurisdiction=JID
            ),  # move up future end date
        ],
    )
    person, num = retire_person(person, "2018-10-01")
    assert num == 2
    assert person.roles[0].end_date == "2000-01-01"
    assert person.roles[1].end_date == "2018-10-01"
    assert person.roles[2].end_date == "2018-10-01"

    # idempotent
    person, num = retire_person(person, "2018-11-01")
    assert num == 0
