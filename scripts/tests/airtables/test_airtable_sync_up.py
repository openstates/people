from dataclasses import dataclass
from os import path
from typing import Generator, List, TypedDict
from unittest.mock import patch

import pytest

from airtables import (
    AirtablePerson, 
    AirtablePersonContact,
    AirtablePersonRole,
    OpenstatesAirtables,
)
from .mock_airtable import MockAirtable
from tests.helpers import fixture_path

@dataclass
class ImportExample:
    airtable_prefix: str
    state: str
    govt_branch: str
    expected_people: List[AirtablePerson]
    expected_people_contacts: List[AirtablePersonContact]
    expected_people_roles: List[AirtablePersonRole]


IMPORT_EXAMPLE_AZ_MUNICIPALITIES = ImportExample(
    airtable_prefix="openstates_",
    state="az",
    govt_branch="municipalities",
    expected_people=[
        AirtablePerson(
            state="az",
            govt_branch="municipalities",
            id="ocd-person/8b688e20-dffc-4792-bd30-935d21c78127",
            name = "Cathy Carlat",
            given_name = "Cathy",
            family_name = "Carlat",
            email = "mayor@peoriaaz.gov",
            role_place = "peoria",
            role_jurisdiction="ocd-jurisdiction/country:us/state:az/place:peoria/government",
            role_type="mayor",
            role_end_date='2022-11-08',
            contact_note='Primary Office',
            contact_address = "8401 W. Monroe St.;Peoria, AZ 85345",
            contact_voice = "623-773-5133",
            source_url = "https://www.peoriaaz.gov/government/mayor-and-city-council",
            link_url = "https://www.peoriaaz.gov/government/mayor-and-city-council"
        ),
        AirtablePerson(
            state="az",
            govt_branch="municipalities",
            id="ocd-person/355d5767-e6d5-4128-8268-152b74cf2417",
            name = "Coral Evans",
            given_name = "Coral",
            family_name = "Evans",
            email = "cevans@flagstaffaz.gov",
            role_place = "flagstaff",
            role_jurisdiction="ocd-jurisdiction/country:us/state:az/place:flagstaff/government",
            role_type="mayor",
            role_end_date='2020-12-31',
            contact_note = "Primary Office",
            contact_address = "211 W Aspen Avenue;Flagstaff, AZ 86001",
            contact_voice = "928-774-5281",
            source_url = "http://www.flagstaff.az.gov/",
            link_url = "http://www.flagstaff.az.gov/"
        )
    ],
    expected_people_roles = [
        AirtablePersonRole(
            state="az",
            govt_branch="municipalities",
            person_id="ocd-person/8b688e20-dffc-4792-bd30-935d21c78127",
            name = "Cathy Carlat",
            jurisdiction="ocd-jurisdiction/country:us/state:az/place:peoria/government",
            type="mayor",
            place = "peoria",
            end_date='2020-11-08'
        ),
    ],
    expected_people_contacts = [
        AirtablePersonContact(
            state="az",
            govt_branch="municipalities",
            person_id="ocd-person/355d5767-e6d5-4128-8268-152b74cf2417",
            name="Coral Evans",
            note="Capital Office",
            address="999 W Aspen Avenue;Flagstaff, AZ 86001",
            voice="123-456-7890",
            place="flagstaff"
        ),
    ]
)

IMPORT_EXAMPLE_CA_MUNICIPALITIES = ImportExample(
    airtable_prefix="openstates_",
    state="ca",
    govt_branch="municipalities",
    expected_people=[
        AirtablePerson(
            state="ca",
            govt_branch="municipalities",
            id="ocd-person/594ad199-1d69-4af4-9761-a5df048f8ada",
            name = "Acquanetta Warren",
            given_name = "Acquanetta",
            family_name = "Warren",
            email = "awarren@fontana.org",
            role_place = "fontana",
            role_jurisdiction="ocd-jurisdiction/country:us/state:ca/place:fontana/government",
            role_type="mayor",
            role_end_date="2022-11-08",
            contact_note='Primary Office',
            contact_address = "8353 Sierra Avenue;Fontana, CA 92335",
            contact_voice = "909-350-7601"
        ),
        AirtablePerson(
            state="ca",
            govt_branch="municipalities",
            id="ocd-person/fa56b40f-5b69-4b90-a5f8-e0f2edb5ba2e",
            name = "Adrian Fine",
            given_name = "Adrian",
            family_name = "Fine",
            email = "adrian.fine@cityofpaloalto.org",
            role_place = "palo_alto",
            role_jurisdiction="ocd-jurisdiction/country:us/state:ca/place:palo_alto/government",
            role_type="mayor",
            role_end_date="2021-01-01",
            contact_note = "Primary Office",
            contact_address = "250 Hamilton Avenue;Palo Alto, CA 94301",
            contact_voice = "650-285-3694"
        ),
        AirtablePerson(
            state="ca",
            govt_branch="municipalities",
            id="ocd-person/7451e00b-d236-492e-8049-224cc4b600f2",
            name = "Aja Brown",
            given_name = "Aja",
            family_name = "Brown",
            email = "ajabrown@comptoncity.org",
            role_place = "compton",
            role_jurisdiction="ocd-jurisdiction/country:us/state:ca/place:compton/government",
            role_type="mayor",
            role_end_date="2021-04-06",
            contact_note = "Primary Office",
            contact_address = "205 S Willowbrook Ave;Compton, CA 90220",
            contact_voice = "310-605-5585"
        )
    ],
    expected_people_roles = [],
    expected_people_contacts = []
)

IMPORT_EXAMPLE_ALL_MUNICIPALITIES = ImportExample(
    airtable_prefix="openstates_",
    state="",
    govt_branch="municipalities",
    expected_people=[
        *[p for p in IMPORT_EXAMPLE_AZ_MUNICIPALITIES.expected_people],
        *[p for p in IMPORT_EXAMPLE_CA_MUNICIPALITIES.expected_people]
    ],
    expected_people_roles = [
        *[p for p in IMPORT_EXAMPLE_AZ_MUNICIPALITIES.expected_people_roles],
        *[p for p in IMPORT_EXAMPLE_CA_MUNICIPALITIES.expected_people_roles]
    ],
    expected_people_contacts =  [
        *[p for p in IMPORT_EXAMPLE_AZ_MUNICIPALITIES.expected_people_contacts],
        *[p for p in IMPORT_EXAMPLE_CA_MUNICIPALITIES.expected_people_contacts]
    ],
)


def _test_imports_persons_to_a_schema_of_airtables(
    example: ImportExample,
    fixture_people_default_data: str,
    fixture_mock_airtable: MockAirtable
):
    """
    airtable can't easily represent a complex person document
    in a single table so in addition to person records 
    we create an airtable for each complex person relation,
    e.g. person-contacts, person-roles 
    """
    OpenstatesAirtables(
        data_root=fixture_people_default_data,
        airtable_api_key='fake_api_key',
        airtable_base='some_base',
        airtable_table_prefix=example.airtable_prefix
    ).sync_up(
        people_state=example.state,
        people_govt_branch=example.govt_branch
    )
    fixture_mock_airtable.assert_table_batch_insert_called_once_with(
        f"{example.airtable_prefix}people",
        example.expected_people
    )
    if example.expected_people_roles:
        fixture_mock_airtable.assert_table_batch_insert_called_once_with(
            f"{example.airtable_prefix}people_roles",
            example.expected_people_roles
        )
    if example.expected_people_contacts:
        fixture_mock_airtable.assert_table_batch_insert_called_once_with(
            f"{example.airtable_prefix}people_contacts",
            example.expected_people_contacts
        )
        

@pytest.mark.parametrize(
    "example",
    [
        (IMPORT_EXAMPLE_AZ_MUNICIPALITIES),
        (IMPORT_EXAMPLE_CA_MUNICIPALITIES)
    ]
)
def test_imports_people_for_one_state(
    example: ImportExample,
    fixture_people_default_data: str,
    fixture_mock_airtable: MockAirtable
):
    _test_imports_persons_to_a_schema_of_airtables(
        example, fixture_people_default_data, fixture_mock_airtable
    )

@pytest.mark.parametrize(
    "example",
    [
        (IMPORT_EXAMPLE_ALL_MUNICIPALITIES),
    ]
)
def test_imports_people_for_all_states_when_state_not_passed(
    example: ImportExample,
    fixture_people_default_data: str,
    fixture_mock_airtable: MockAirtable
):
    _test_imports_persons_to_a_schema_of_airtables(
        example, fixture_people_default_data, fixture_mock_airtable
    )
