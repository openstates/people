import re
from typing import List
from unittest.mock import Mock


class MockAirtable:

    
    def __init__(self, mock_airtable_cls, fixture_airtable_data=None):
        self.mock_airtable_cls = mock_airtable_cls
        # will be one Airtable inst per distinct table, so...
        self.mock_airtable_inst_by_table = {}
        self.fixture_airtable_data = fixture_airtable_data
        self.mock_airtable_cls.side_effect = self._mock_init
        self.mock_data_by_table = {}


    def _mock_init(self, base: str, table: str, api_key: str):
        self.base = base
        table_inst = Mock(name=table)
        table_inst.get_all.return_value = self.mock_data_by_table.get(table, [])
        # real Airtable.batch_insert returns created records, but we don't need
        self.mock_airtable_inst_by_table[table] = table_inst
        return table_inst


    def assert_constructor_called_with(self, base: str, table: str, api_key: str):
        self.mock_airtable_cls.assert_called_once_with(base, table, api_key=api_key)


    def assert_table_batch_insert_called_once_with(self, table:str, records: List[dict]):
        self.mock_airtable_inst_by_table[table].batch_insert.assert_called_once_with(records)


    def mock_get_all(self, table: str, data: List[dict]) -> None:
        """
        Stores return data for `Airtable.get_all` for a table name.
        Any subsequent Airtable instance created for the given table name
        will return the provided data for `get_all()`
        """
        self.mock_data_by_table[table] = data


