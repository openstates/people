from dataclasses import dataclass
import json
from os import path, walk
from pathlib import Path, PurePath
from shutil import copytree
from typing import Callable
from unittest.mock import patch
import uuid

import pytest

from airtables import OpenstatesAirtables
from utils import load_yaml_path
from .mock_airtable import MockAirtable
from tests.helpers import fixture_path


@dataclass
class _ExampleInfo:
    expected_result_path: str
    mock_airtable_path: str
    source_data_path: str


def _assert_all_yaml_files_match(expect_root: str, actual_root: str) -> None:
    assert path.isdir(expect_root)
    assert path.isdir(actual_root)
    for root, dirs, files in walk(expect_root):
        for expect_f in files:
            if not expect_f.endswith(".yml"): continue
            expect_path = path.join(root, expect_f)
            expect_path_from_root = PurePath(expect_path).relative_to(expect_root)
            actual_path = path.join(actual_root, expect_path_from_root)
            assert path.isfile(actual_path)
            assert load_yaml_path(expect_path) == load_yaml_path(actual_path)


def _example_info(example: str) -> _ExampleInfo:
    d = fixture_path(path.join("airtables", "examples", example))
    return _ExampleInfo(
        expected_result_path = path.join(d, "expected_result"),
        mock_airtable_path = path.join(d, "mock_airtable.json"),
        source_data_path = (
            path.join(d, "source_data") 
            if path.isdir(path.join(d, "source_data"))
            else ''
        )
    )


@pytest.mark.parametrize(
    "example",
    [
        ("no_links"),
        ("no_sources"),
        ("syncdown_assigns_new_ocd_person_id_for_replacement_mayor"),
        ("syncdown_repeated_finds_ocd_person_id_for_replacement_mayor"),
        ("updates_end_dates"),
        ("wrong_address_format_in_airtable"),
        ("wrong_phone_format_in_airtable"),
    ]
)
# mock uuid is for testing case of new person creation
# existing test cases only need one
@patch.object(uuid, 'uuid4', side_effect=["11111111-1111-1111-1111-111111111111"])
def test_sync_down(
    mock_uuid: Callable[[],str],
    tmp_path: str,
    fixture_mock_airtable: MockAirtable,
    fixture_people_default_data: str,
    example: str
) -> None:
    exinfo = _example_info(example)  # paths for current example
    # make a tmp copy of our example source data
    # and use that to test sync_down
    test_data = path.join(tmp_path, "people", "data")
    copytree(exinfo.source_data_path or fixture_people_default_data, test_data)
    # mock data returned by airtable.Airtable client for the example
    with open(exinfo.mock_airtable_path) as f:
        mock_airtables = json.load(f)
        fixture_mock_airtable.mock_get_all("people", mock_airtables.get("people", []))
    # run sync_down
    OpenstatesAirtables(data_root=test_data).sync_down()
    # test that the (updated) files
    # in our tmp 'test_data' directory
    # match the expected results for the example
    _assert_all_yaml_files_match(exinfo.expected_result_path, test_data)
