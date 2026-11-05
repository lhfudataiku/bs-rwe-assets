"""Offline tests for the import fixes in solution/pipelines/sync_omop_datasets.py (E3 fixes 1-3, 5)."""
import unittest
from unittest import mock

import stubs

stubs.install()
from solution.pipelines import sync_omop_datasets as s  # noqa: E402

TABLES = ["person", "concept"]


def variables(local_prep="PREP_RWD_SF_1K", local_conn="bs-snowflake"):
    local = {"data_preparation_project_key": local_prep, "main_connection": local_conn,
             "omop_cdm_standard_tables_import": [], "omop_standardised_vocabulary_tables_import": []}
    local.update({t: t + "_sf" for t in TABLES})
    return {"standard": {"data_preparation_project_key": "OLD", "main_connection": "standard-conn"},
            "local": local}


class TransformSchema(unittest.TestCase):
    def test_every_non_uppercase_name_is_renamed_mixed_case_included(self):
        schema, renames = s._transform_schema(
            [{"name": "person_id", "type": "int"}, {"name": "Person_Source", "type": "string"},
             {"name": "YEAR_OF_BIRTH", "type": "int"}])
        self.assertEqual([c["name"] for c in schema], ["PERSON_ID", "PERSON_SOURCE", "YEAR_OF_BIRTH"])
        self.assertEqual(renames, [{"from": "person_id", "to": "PERSON_ID"},
                                   {"from": "Person_Source", "to": "PERSON_SOURCE"}])

    def test_ingestion_types_are_kept_as_documented(self):
        schema, _ = s._transform_schema([{"name": "a", "type": "bigint"}, {"name": "b", "type": "double"},
                                         {"name": "c", "type": "dateonly"}])
        self.assertEqual([c["type"] for c in schema], ["int", "float", "dateonly"])

    def test_source_schema_is_not_mutated(self):
        src = [{"name": "person_id", "type": "bigint"}]
        s._transform_schema(src)
        self.assertEqual(src, [{"name": "person_id", "type": "bigint"}])


class SyncOmopDatasets(unittest.TestCase):
    def setUp(self):
        self.project = mock.MagicMock(project_key="SOL")
        self.client = mock.MagicMock()
        patches = {
            "get_current_project_and_variables": mock.MagicMock(return_value=(self.project, variables())),
            "MANDATORY_TABLES": ["person"], "MANDATORY_VOCABULARY": ["concept"], "OMOP_CDM_KEYS": TABLES,
            "check_project_key_exists": mock.MagicMock(),
            "get_all_project_dataset_names": mock.MagicMock(return_value=[]),
            "get_all_project_recipe_names": mock.MagicMock(return_value=[]),
            "share_object_with_name": mock.MagicMock(),
            "get_dataset_schema": mock.MagicMock(return_value=[{"name": "x", "type": "int"}]),
            "set_dataset_schema": mock.MagicMock(), "instantiate_prepare_recipe": mock.MagicMock(),
            "reset_prepare_recipe_steps": mock.MagicMock(), "move_dataset_in_flow_zone": mock.MagicMock(),
        }
        for name, value in patches.items():
            p = mock.patch.object(s, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(s.dataiku, "api_client", return_value=self.client)
        p.start()
        self.addCleanup(p.stop)

    def test_missing_prep_project_fails_before_any_change(self):
        s.check_project_key_exists.side_effect = ValueError("no such project")
        with self.assertRaises(ValueError):
            s.sync_omop_datasets()
        s.check_project_key_exists.assert_called_once_with("PREP_RWD_SF_1K")
        s.share_object_with_name.assert_not_called()
        s.instantiate_prepare_recipe.assert_not_called()
        self.project.new_job.assert_not_called()

    def test_all_tables_build_in_one_waited_job(self):
        s.sync_omop_datasets()
        self.project.new_job.assert_called_once_with("NON_RECURSIVE_FORCED_BUILD")
        job = self.project.new_job.return_value
        built = sorted(c.args[0] for c in job.with_output.call_args_list)
        self.assertEqual(built, sorted(TABLES))
        job.start_and_wait.assert_called_once_with()

    def test_failed_build_fails_the_step(self):
        self.project.new_job.return_value.start_and_wait.side_effect = RuntimeError("job failed")
        with self.assertRaises(Exception):
            s.sync_omop_datasets()

    def test_prep_key_and_main_connection_come_from_local_scope(self):
        s.sync_omop_datasets()
        self.client.get_project.assert_called_with("PREP_RWD_SF_1K")
        connections = {c.args[4] for c in s.instantiate_prepare_recipe.call_args_list}
        self.assertEqual(connections, {"bs-snowflake"})


if __name__ == "__main__":
    unittest.main()
