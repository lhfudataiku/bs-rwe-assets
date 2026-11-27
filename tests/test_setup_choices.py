"""Offline tests for the Project Setup choices (E2). The manifest tool is in test_app_manifest.py."""
import unittest
from unittest import mock

import stubs

stubs.install()
from solution.setup import choices as c  # noqa: E402

PREP, MAIN = "PREP_RWD_SF_1K", "bs-snowflake"


def client(local=None, standard=None, projects=("SOL", PREP), conn_type="Snowflake", datasets=None):
    cl = mock.MagicMock()
    cl.list_project_keys.return_value = list(projects)
    sol, prep = mock.MagicMock(), mock.MagicMock()
    sol.get_variables.return_value = {"local": local or {}, "standard": standard or {}}
    prep.list_datasets.return_value = datasets if datasets is not None else [
        {"name": "person_sf", "type": "Snowflake"}, {"name": "concept_sf", "type": "Snowflake"},
        {"name": "person", "type": "S3"}]
    cl.get_project.side_effect = lambda key: sol if key == "SOL" else prep
    cl.get_connection.return_value.get_info.return_value = {"type": conn_type}
    return cl, prep


class OmopTableChoices(unittest.TestCase):
    def test_lists_datasets_on_main_connection_type_sorted(self):
        cl, prep = client(local={"data_preparation_project_key": PREP, "main_connection": MAIN})
        self.assertEqual(c.omop_table_choices(cl, "SOL"), {"choices": [
            {"value": "concept_sf", "label": "concept_sf"}, {"value": "person_sf", "label": "person_sf"}]})
        prep.get_dataset.assert_not_called()  # type comes from list_datasets, not per-dataset settings

    def test_no_prep_project_selected(self):
        cl, _ = client(local={"main_connection": MAIN})
        self.assertEqual(c.omop_table_choices(cl, "SOL"), {"choices": [c.NO_PREP_PROJECT]})

    def test_dangling_prep_project_does_not_raise(self):
        cl, _ = client(local={"data_preparation_project_key": "SNOWFLAKESYNPUFOMOP23DATAPREPERATION",
                              "main_connection": MAIN})
        self.assertEqual(c.omop_table_choices(cl, "SOL"), {"choices": [c.NO_PREP_PROJECT]})

    def test_falls_back_to_standard_scope(self):
        cl, _ = client(standard={"data_preparation_project_key": PREP, "main_connection": MAIN})
        self.assertEqual(len(c.omop_table_choices(cl, "SOL")["choices"]), 2)

    def test_missing_or_unreadable_main_connection(self):
        cl, _ = client(local={"data_preparation_project_key": PREP})
        self.assertEqual(c.omop_table_choices(cl, "SOL"), {"choices": [c.NO_MAIN_CONNECTION]})
        cl, _ = client(local={"data_preparation_project_key": PREP, "main_connection": "gone"})
        cl.get_connection.return_value.get_info.side_effect = Exception("not found")
        self.assertEqual(c.omop_table_choices(cl, "SOL"), {"choices": [c.NO_MAIN_CONNECTION]})

