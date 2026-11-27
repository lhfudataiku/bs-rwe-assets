"""Dialect fingerprint of Atlas cohort scripts: a script exported for another dialect is refused."""
import glob
import os
import unittest

import stubs

stubs.install()
from solution.setup import sql_dialect as d  # noqa: E402

# Short forms of what Atlas writes (atlas-demo.ohdsi.org, WebAPI 2.14, sampled 2026-11-24).
SNOWFLAKE = "CREATE TEMP TABLE @temp_database_schema.ab12Codesets (i int);\nSELECT DATEADD(day,1,d) FROM t;"
DATABRICKS = "CREATE TABLE @temp_database_schema.ab12Codesets\nUSING DELTA\nAS SELECT date_add(d, 1) FROM t;"
REDSHIFT = ("CREATE TABLE #Codesets (i int)\nDISTSTYLE ALL;\nINSERT INTO #Codesets SELECT 1;\n"
            "ANALYZE #Codesets;\nSELECT DATEADD(day,CAST(1 as int),d) FROM t;")
TEMPLATE = "SELECT person_id INTO #qualified_events FROM t;\nSELECT DATEADD(day,1,d) FROM t;"
POSTGRES = "CREATE TEMP TABLE Codesets (i int);\nSELECT d + 1*INTERVAL'1 day' FROM t;"


class Detect(unittest.TestCase):
    def test_atlas_forms(self):
        self.assertEqual([d.detect_dialect(s) for s in (SNOWFLAKE, DATABRICKS, REDSHIFT, TEMPLATE, POSTGRES)],
                         [d.SNOWFLAKE, d.DATABRICKS, d.REDSHIFT, d.TEMPLATE, d.POSTGRES])

    def test_hand_written_sql_is_not_judged(self):
        self.assertIsNone(d.detect_dialect("DELETE FROM cohort WHERE cohort_definition_id = 1;\nINSERT INTO cohort SELECT 1;"))

    def test_markers_in_comments_do_not_count(self):
        self.assertIsNone(d.detect_dialect("-- USING DELTA\n/* INTO #t */ SELECT 1;"))

    def test_every_shipped_script(self):
        expected = {"snowflake": d.SNOWFLAKE, "databricks": d.DATABRICKS, "redshift": d.REDSHIFT,
                    "postgre": d.POSTGRES}
        for folder, dialect in expected.items():
            for path in sorted(glob.glob(os.path.join(stubs.ROOT, "cohort_scripts", folder, "*.sql"))):
                with self.subTest(script=folder + "/" + os.path.basename(path)), open(path) as fh:
                    self.assertEqual(d.detect_dialect(fh.read()), dialect)


class Error(unittest.TestCase):
    def test_sentences(self):
        self.assertIsNone(d.dialect_error(SNOWFLAKE, "Snowflake", "a.sql"))
        self.assertIsNone(d.dialect_error("SELECT 1;", "Snowflake", "a.sql"))
        self.assertEqual(d.dialect_error(DATABRICKS, "Snowflake", "a.sql"),
                         "a.sql: the script was exported for Databricks, but this project runs on Snowflake. "
                         "Export it from Atlas for Snowflake.")
        self.assertIn("untranslated OHDSI SQL template", d.dialect_error(TEMPLATE, "Redshift", "a.sql"))
        self.assertIn("written for PostgreSQL", d.dialect_error(POSTGRES, "Databricks", "a.sql"))

    def test_unknown_connection_is_not_judged(self):
        self.assertIsNone(d.dialect_error(DATABRICKS, None, "a.sql"))


if __name__ == "__main__":
    unittest.main()
