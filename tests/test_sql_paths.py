"""R4: SQL table names come from DSS (`quotedResolvedTableName`), not from dataset parameters."""
import unittest
from unittest import mock

import stubs

stubs.install()
from solution.recipes import sql_script_function as f  # noqa: E402

# Names DSS returned in the spike (solution-revision-plan.md, "Spike results", R4).
RESOLVED = {
    "Snowflake": '"DKU_SOLUTION_DESIGN"."SOL_DESIGN"."PREP_RWD_SF_1K_PERSON_SF"',
    "Databricks": "`se-sandbox`.`business_solutions`.`PREP_RWD_DB_1K_person_db`",
    "Redshift": '"TMP_RWD_SPIKE_R_Out-RS"',
}


class GetSqlPath(unittest.TestCase):
    def patch(self, connection_type, info):
        settings = mock.patch.object(f, "get_dataset_settings_and_dictionary",
                                     return_value=(None, {"type": connection_type, "params": {}}))
        dataset = mock.patch.object(f.dataiku, "Dataset")
        settings.start()
        ds = dataset.start()
        self.addCleanup(settings.stop)
        self.addCleanup(dataset.stop)
        ds.return_value.get_location_info.return_value = {"locationInfoType": "SQL", "info": info}
        return ds

    def test_returns_the_name_dss_resolves_for_each_supported_type(self):
        for connection_type, name in RESOLVED.items():
            with self.subTest(connection_type=connection_type):
                ds = self.patch(connection_type, {"quotedResolvedTableName": name, "table": "ignored"})
                self.assertEqual(f.get_sql_path("person"), name)
                ds.assert_called_with("person")

    def test_unsupported_connection_type_raises_with_supported_list(self):
        self.patch("Filesystem", {})
        with self.assertRaises(ValueError) as e:
            f.get_sql_path("cohort")
        self.assertIn("Databricks, Redshift, Snowflake", str(e.exception))
        self.assertIn("'cohort'", str(e.exception))

    def test_missing_resolved_name_raises(self):
        self.patch("Snowflake", {"table": "COHORT"})
        with self.assertRaises(ValueError):
            f.get_sql_path("cohort")

    def test_resolved_names_are_substituted_verbatim_into_scripts(self):
        name = RESOLVED["Databricks"]
        self.patch("Databricks", {"quotedResolvedTableName": name})
        script = f.create_cdm_table_paths({}, ["person"])
        self.assertEqual(script, {"person": name})
        sql = f.replace_sql_script_variables("SELECT * FROM @cdm_database_schema.person p", {
            "@cdm_database_schema.person": name})
        self.assertEqual(sql, "SELECT * FROM %s p" % name)


if __name__ == "__main__":
    unittest.main()
