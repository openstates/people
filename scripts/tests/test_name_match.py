import pytest
from name_match import find_match

@pytest.mark.parametrize(
    "csv_name, yaml_person, expected",
    [
        # Basic Name
        ("Dan Schneiderman", {"name": "Dan Schneiderman", "family_name": "Schneiderman"}, True),

        # Just Last Name
        ("Schneiderman", {"name": "Dan Schneiderman", "family_name": "Schneiderman"}, True),

        # Name with a comma
        ("Kwan, Karen", {"name": "Karen Kwan", "family_name": "Kwan"}, True),

        # Name with an initial at the end Matt Huffman, M.
        ("Matt Huffman, M", {"name": "Matt Huffman", "family_name": "Huffman"}, True),

        # Last name of location ZEIGLER of Montville
        ("ZEIGLER of Montville", {"name": "Stanley Paige Zeigler", "family_name": "Zeigler"}, True),

        # Full name with initial and number at end of name
        ("Louis W. Blessing, III", {"name": "Louis W. Blessing", "family_name": "Blessing"}, True),

    ],
)
def test_family_name(csv_name, yaml_person, expected):
    assert find_match(csv_name, yaml_person) == expected