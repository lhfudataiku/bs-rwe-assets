"""R2 ingestion: `register_cohorts` checks everything before writing, then writes escaped definitions."""
import unittest
from unittest import mock

import stubs

stubs.install()
from solution.pipelines import register_cohorts as rc  # noqa: E402
from solution.setup import registration  # noqa: E402

ATLAS_SCRIPT = ("DELETE FROM @target_database_schema.@target_cohort_table WHERE cohort_definition_id = @target_cohort_id;\n"
                "CREATE TEMP TABLE @temp_database_schema.abCodesets (i int);\n"
                "INSERT INTO @target_database_schema.@target_cohort_table SELECT * FROM @cdm_database_schema.person;")
TEMPLATE = ("DELETE FROM @cohort_definition WHERE cohort_definition_id IN ( @cohort_ids );\n"
            "INSERT INTO @cohort_definition VALUES @row_values ;\n"
            "DROP TABLE IF EXISTS @uploaded_cohort_definition ;\n"
            "INSERT INTO @uploaded_cohort_definition VALUES @uploaded_row_values ;")


class RegisterCohorts(unittest.TestCase):
    def setUp(self):
        self.settings = {"cohort_submission": [
            {"id": 1, "name": "Crohn's", "description": "", "file": "a.sql", "replace": False}],
            "cohort_script_table_naming": "atlas", "main_connection": "conn"}
        self.files = {"a.sql": ATLAS_SCRIPT}
        self.registered = []
        self.executor = mock.MagicMock()
        self.output = mock.MagicMock()
        paths = {"cohort": '"D"."S"."COHORT"', "person": '"D"."S"."PERSON"',
                 "cohort_definition": '"D"."S"."COHORT_DEFINITION"',
                 "uploaded_cohort_definition": '"D"."S"."UPLOADED_COHORT_DEFINITION"'}
        sf = "solution.recipes.sql_script_function"
        patches = [
            mock.patch.object(rc, "get_setting", side_effect=lambda k, default=None: self.settings.get(k, default)),
            mock.patch.object(rc, "folder_texts", side_effect=lambda folder: self.files),
            mock.patch.object(rc, "read_rows", side_effect=lambda ds, cols: self.registered),
            mock.patch.object(rc, "validate_cdm_tables"),
            mock.patch.object(rc, "SQLExecutor2", return_value=self.executor),
            mock.patch.object(rc, "cohort_connection_type", return_value="Snowflake"),
            mock.patch.object(rc.dataiku, "Folder", side_effect=lambda fid, **kw: self.output),
            mock.patch(sf + ".get_sql_path", side_effect=lambda t: paths[t]),
            mock.patch(sf + ".get_script_by_connection_type",
                       side_effect=lambda name: TEMPLATE if name == "cohort_definition_script" else "CREATE @cohort;\n"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_writes_mapped_script_and_escaped_definitions(self):
        self.assertEqual(rc.register_cohorts(), [1])
        name, data = self.output.upload_data.call_args.args
        script = data.decode()
        self.assertEqual(name, "cohort_1")
        self.assertIn('FROM "D"."S"."PERSON"', script)
        self.assertIn("@temp_database_schema.abCodesets", script)  # rendered at build time (R6)
        self.assertIn('DELETE FROM "D"."S"."COHORT" WHERE cohort_definition_id = 1', script)
        call = self.executor.query_to_df.call_args
        statements = call.kwargs["pre_queries"]
        self.assertEqual(len(statements), 4)
        self.assertIn("(1, 'Crohn''s', NULL, 0, '{\"script\": \"a.sql\", \"sha256\": ", statements[1])
        self.assertIn("(1, 'Crohn''s', NULL, 'person', 'a.sql')", statements[3])
        self.assertEqual(call.kwargs["post_queries"], ["COMMIT"])

    def test_existing_id_without_replace_writes_nothing(self):
        self.registered = [{"id": 1, "name": "Old", "description": "", "syntax": ""}]
        with self.assertRaises(ValueError) as e:
            rc.register_cohorts()
        self.assertIn("cohort 1 already exists", str(e.exception))
        self.output.upload_data.assert_not_called()
        self.executor.query_to_df.assert_not_called()

    def test_replace_is_accepted(self):
        self.registered = [{"id": 1, "name": "Old", "description": "", "syntax": ""}]
        self.settings["cohort_submission"][0]["replace"] = True
        self.assertEqual(rc.register_cohorts(), [1])

    def test_wrong_naming_names_the_placeholders(self):
        self.settings["cohort_script_table_naming"] = "plain"
        with self.assertRaises(ValueError) as e:
            rc.register_cohorts()
        self.assertIn("@cdm_database_schema.person", str(e.exception))
        self.assertIn("Plain OMOP table names", str(e.exception))
        self.executor.query_to_df.assert_not_called()

    def test_custom_mapping_from_a_json_variable(self):
        self.settings["cohort_script_table_naming"] = "mapping"
        self.settings["cohort_script_table_map"] = (
            '{"person": "@cdm_database_schema.person", "cohort": "@target_database_schema.@target_cohort_table"}')
        self.assertEqual(rc.register_cohorts(), [1])
        self.settings["cohort_script_table_map"] = {"person": "@cdm_database_schema.person"}
        with self.assertRaises(ValueError) as e:
            rc.register_cohorts()
        self.assertIn("@target_database_schema.@target_cohort_table", str(e.exception))
        self.assertIn("Custom mapping table", str(e.exception))

    def test_submission_as_json_text_and_empty(self):
        self.settings["cohort_submission"] = '[{"id": 1, "name": "A", "description": "", "file": "a.sql"}]'
        self.assertEqual(rc.register_cohorts(), [1])
        self.settings["cohort_submission"] = []
        with self.assertRaises(ValueError) as e:
            rc.register_cohorts()
        self.assertIn("No cohorts submitted", str(e.exception))

    def test_provenance_marks_the_registered_script(self):
        rc.register_cohorts()
        rows = registration.registration_rows(self.files, [{
            "id": 1, "name": "Crohn's", "description": None,
            "syntax": registration.provenance("a.sql", registration.script_digest(ATLAS_SCRIPT))}])
        self.assertEqual(rows[0]["status"], "registered")


if __name__ == "__main__":
    unittest.main()
