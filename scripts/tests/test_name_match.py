import pytest
from name_match import find_match

@pytest.mark.parametrize(
    "csv_name, yaml_person, expected",
    [
        # Basic Name
        ("Dan Schneiderman", {"name": "Dan Schneiderman", "family_name": "Schneiderman"}, True),

    ],
)
def test_family_name_simple(csv_name, yaml_person, expected):
    assert find_match(csv_name, yaml_person) == expected