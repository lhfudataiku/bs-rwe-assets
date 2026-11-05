"""Offline tests for the Project Setup choices (E2) and the manifest patch tool."""
import copy
import importlib.util
import os
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


class ScopedVariable(unittest.TestCase):
    def test_local_wins_then_standard_then_none(self):
        v = {"local": {"a": "L", "b": ""}, "standard": {"a": "S", "b": "S", "c": "S"}}
        self.assertEqual([c.scoped_variable(v, k) for k in "abcd"], ["L", "S", "S", None])

    def test_missing_scopes(self):
        self.assertIsNone(c.scoped_variable({}, "a"))


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


class CohortDefinitionChoices(unittest.TestCase):
    def dataset(self, names, rows):
        ds = mock.MagicMock()
        ds.read_schema.return_value = [{"name": n} for n in names]
        ds.iter_tuples.return_value = iter(rows)
        return ds

    def test_reads_columns_in_any_case(self):
        ds = self.dataset(["cohort_definition_id", "Cohort_Definition_Name"], [(2, "Stroke"), (1, "HF")])
        self.assertEqual(c.cohort_definition_choices(ds), {"choices": [
            {"value": 1, "label": "HF"}, {"value": 2, "label": "Stroke"}]})

    def test_unbuilt_dataset_gives_no_choices(self):
        ds = self.dataset(["COHORT_DEFINITION_ID"], [])
        ds.iter_tuples.side_effect = Exception("dataset is not built")
        self.assertEqual(c.cohort_definition_choices(ds), {"choices": []})


def load_tool():
    path = os.path.join(stubs.ROOT, "tools", "app_manifest.py")
    spec = importlib.util.spec_from_file_location("app_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ManifestTool(unittest.TestCase):
    MANIFEST = {"homepageSections": [
        {"tiles": []}, {"tiles": []},
        {"tiles": [{"module": "input_data_source_project_selectbox", "python": "old"}, {}, {},
                   {"params": [{"name": "person"}], "python": "old"}, {},
                   {"params": [{"name": "concept"}], "python": "old"}]},
        {}, {}, {}, {}, {},
        {"tiles": [{}, {"params": [{"name": "cohort_definition_id"}], "python": "old"}]}]}

    def test_replaces_the_four_tiles_and_nothing_else(self):
        tool, m = load_tool(), copy.deepcopy(self.MANIFEST)
        self.assertEqual(len(tool.patch(m)), 4)
        self.assertIn("omop_table_choices()", m["homepageSections"][2]["tiles"][3]["python"])
        self.assertEqual(tool.patch(m), [])  # idempotent

    def test_refuses_a_reordered_manifest(self):
        tool, m = load_tool(), copy.deepcopy(self.MANIFEST)
        m["homepageSections"][2]["tiles"][3]["params"][0]["name"] = "concept"
        with self.assertRaises(SystemExit):
            tool.patch(m)

    def test_wrappers_compile_and_name_real_functions(self):
        tiles = os.path.join(stubs.ROOT, "app_manifest", "tiles")
        for fname in os.listdir(tiles):
            ns = {}
            exec(compile(open(os.path.join(tiles, fname)).read(), fname, "exec"), ns)
            self.assertTrue(callable(ns["do"]), fname)


if __name__ == "__main__":
    unittest.main()
