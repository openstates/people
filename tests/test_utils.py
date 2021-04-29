import pytest
from ospeople.utils import reformat_phone_number, reformat_address, role_is_active, find_file


@pytest.mark.parametrize(
    "input,output",
    [
        ("1234567890", "123-456-7890"),
        ("123-456-7890", "123-456-7890"),
        ("1-123-456-7890", "1-123-456-7890"),
        ("+1-123-456-7890", "1-123-456-7890"),
        ("1-800-FAKENUM", "1-800-FAKENUM"),
        ("email@example.com", "email@example.com"),
        ("555.333.1111", "555-333-1111"),
        ("+1 (555) 333-1111", "1-555-333-1111"),
        ("555-333-1111 ext.100", "555-333-1111 ext. 100"),
        ("555.333.1111 EXT.100", "555-333-1111 ext. 100"),
    ],
)
def test_reformat_phone(input, output):
    assert reformat_phone_number(input) == output


@pytest.mark.parametrize(
    "input,output",
    [
        ("123 Maple Lane\nRaleigh, NC 27511", "123 Maple Lane;Raleigh, NC 27511"),
        ("123 Maple Lane   \n   Raleigh, NC    27511", "123 Maple Lane;Raleigh, NC 27511"),
        ("123 Maple Lane\n \nRaleigh, NC 27511", "123 Maple Lane;Raleigh, NC 27511"),
    ],
)
def test_reformat_address(input, output):
    assert reformat_address(input) == output


@pytest.mark.parametrize(
    "role,expected",
    [
        ({"name": "A"}, True),
        ({"name": "B", "end_date": None}, True),
        ({"name": "C", "end_date": "1990-01-01"}, False),
        ({"name": "D", "end_date": "2100-01-01"}, True),
    ],
)
def test_role_is_active(role, expected):
    assert role_is_active(role) == expected


def test_find_file_good():
    filename = find_file("a2e4a1b2-f0fd-4c35-9e0c-bb009778792f")
    assert "Pam-Snyder" in filename


def test_find_file_missing():
    with pytest.raises(FileNotFoundError):
        find_file("77777777-ffff-0000-9000-bbbbbbbbbbbb")
