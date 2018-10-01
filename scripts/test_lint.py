import sys
import pytest
import uuid

sys.path.append('.')

from lint_yaml import (is_url, is_social, is_fuzzy_date, is_phone, is_uuid,
                       validate_obj, PERSON_FIELDS)


def test_is_url():
    assert is_url('http://example.com')
    assert is_url('https://example.com')
    assert not is_url('/fragment')


def test_is_social():
    assert is_social('example_id')
    assert not is_social('@no_at_sign')
    assert not is_social('http://no-urls.com')


def test_is_fuzzy_date():
    assert is_fuzzy_date('2010')
    assert is_fuzzy_date('2019-01')
    assert is_fuzzy_date('2020-01-01')
    assert not is_fuzzy_date('1/1/2011')


def test_is_phone():
    assert is_phone('123-346-7990')
    assert is_phone('1-123-346-7990')
    assert not is_phone('(123) 346-7990')


def test_is_uuid():
    assert is_uuid('abcdef98-0123-7777-8888-1234567890ab')
    assert not is_uuid('abcdef980123777788881234567890ab')


def test_validate_obj_required():
    example = {
        'id': str(uuid.uuid4()),
        'name': 'Anne A',
        'links': [
            {'url': 'https://example.com'},
        ],
    }

    assert validate_obj(example, PERSON_FIELDS) == []
