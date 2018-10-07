import pytest
from utils import reformat_phone_number, reformat_address


@pytest.mark.parametrize("input,output", [
    ('123-456-7890', '123-456-7890'),
    ('1-123-456-7890', '1-123-456-7890'),
    ('+1-123-456-7890', '1-123-456-7890'),
    ('1-800-FAKENUM', '1-800-FAKENUM'),
    ('email@example.com', 'email@example.com'),
    ('555.333.1111', '555-333-1111'),
    ('+1 (555) 333-1111', '1-555-333-1111'),
    ('555-333-1111 ext.100', '555-333-1111 ext. 100'),
    ('555.333.1111 EXT.100', '555-333-1111 ext. 100'),
])
def test_reformat_phone(input, output):
    assert reformat_phone_number(input) == output


@pytest.mark.parametrize("input,output", [
    ('123 Maple Lane\nRaleigh, NC 27511', '123 Maple Lane;Raleigh, NC 27511'),
    ('123 Maple Lane   \n   Raleigh, NC    27511', '123 Maple Lane;Raleigh, NC 27511'),
    ('123 Maple Lane\n \nRaleigh, NC 27511', '123 Maple Lane;Raleigh, NC 27511'),
])
def test_reformat_address(input, output):
    assert reformat_address(input) == output
