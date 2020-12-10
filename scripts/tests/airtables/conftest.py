from os import path
from typing import Generator, List
from unittest.mock import Mock, patch
from shutil import copytree

import pytest

from .mock_airtable import MockAirtable
from tests.helpers import fixture_path

@pytest.fixture()
def fixture_airtables() -> str:
    return fixture_path(path.join("airtables"))


@pytest.fixture()
def fixture_people_default_data(fixture_airtables) -> str:
    return fixture_path(path.join("airtables", "people_default", "data"))


@pytest.fixture()
def fixture_data_root_tmp_copy(fixture_people_default_data, tmp_path) -> str:
    d = path.join(tmp_path, "people", "data")
    copytree(fixture_people_default_data, d)
    return d


@pytest.fixture(autouse=True)
def fixture_mock_airtable() -> Generator[MockAirtable, None, None]:
    mock_airtable_patch = patch("airtable.Airtable")
    mock_airtable_cls = mock_airtable_patch.start()
    mock_airtable = MockAirtable(mock_airtable_cls)
    yield mock_airtable
    mock_airtable_patch.stop()