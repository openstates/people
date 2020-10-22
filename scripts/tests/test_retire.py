# import pytest
from retire import retire_person


def test_retire_person():
    person = {
        "id": "123",
        "roles": [
            {"type": "lower", "end_date": "2000-01-01"},  # leave old end date alone
            {"type": "upper", "start_date": "2018-01-01"},  # add end date
            {"type": "gov", "end_date": "2030-01-01"},  # move up future end date
        ],
    }
    person, num = retire_person(person, "2018-10-01")
    assert num == 2
    assert person["roles"][0]["end_date"] == "2000-01-01"
    assert person["roles"][1]["end_date"] == "2018-10-01"
    assert person["roles"][2]["end_date"] == "2018-10-01"

    # idempotent
    person, num = retire_person(person, "2018-11-01")
    assert num == 0
