import pytest
from name_match import find_match


#  Tests that include family name within the yaml person file
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

        # First name initial then last name S. CHANG
        ("S. CHANG ", {"name": "Stephanie Chang", "family_name": "Chang"}, True),

        # Last name with an abbrivation
        ("O'Donnell ", {"name": "Daniel O'Donnell", "family_name": "O'Donnell"}, True),

        # Two Name Last Name
        ("CrosswhiteHader ", {"name": "Denise Crosswhite Hader", "family_name": "Crosswhite Hader"}, True),

    ],
)
def test_family_name(csv_name, yaml_person, expected):
    assert find_match(csv_name, yaml_person) == expected


# Tests with no family name
@pytest.mark.parametrize(
    "csv_name, yaml_person, expected",
    [
        # Basic Name
        ("Dan Schneiderman", {"name": "Dan Schneiderman"}, True),

        # Last name of location ZEIGLER of Montville
        ("ZEIGLER of Montville", {"name": "Stanley Paige Zeigler"}, True),

    ],
)
def test_no_family_name(csv_name, yaml_person, expected):
    assert find_match(csv_name, yaml_person) == expected