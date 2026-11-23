"""R5 and R6: statement splitting, literal escaping, Databricks scratch tables and the build loop."""
import glob
import os
import re
import unittest
from unittest import mock

import stubs

stubs.install()
from solution.recipes import sql_text as t  # noqa: E402
from solution.pipelines import build_cohorts as b  # noqa: E402

DIALECT_FOLDERS = ("snowflake", "databricks", "redshift", "postgre")


def scripts():
    for folder in DIALECT_FOLDERS:
        for path in sorted(glob.glob(os.path.join(stubs.ROOT, "cohort_scripts", folder, "*.sql"))):
            yield os.path.relpath(path, stubs.ROOT), open(path, encoding="utf-8").read()


def outside_quotes_and_comments(sql):
    return re.sub(r"'(?:[^'\\]|\\.|'')*'|\"[^\"]*\"|`[^`]*`|--[^\n]*|/\*.*?\*/", "", sql, flags=re.S)


class SplitStatements(unittest.TestCase):
    def test_quotes_comments_and_backticks(self):
        sql = """-- header; not a statement
        INSERT INTO t VALUES ('a;b', 'it''s', 'c\\';d');  /* x; y */
        SELECT "col;1", `t;2` FROM x;
        -- trailing comment only;
        """
        self.assertEqual(t.split_statements(sql), [
            "-- header; not a statement\n        INSERT INTO t VALUES ('a;b', 'it''s', 'c\\';d')",
            '/* x; y */\n        SELECT "col;1", `t;2` FROM x'])

    def test_no_trailing_semicolon_and_empty_input(self):
        self.assertEqual(t.split_statements("SELECT 1"), ["SELECT 1"])
        self.assertEqual(t.split_statements(" ;\n; -- c\n"), [])

    def test_every_cohort_script_splits_into_single_statements(self):
        found = 0
        for path, sql in scripts():
            found += 1
            with self.subTest(path=path):
                statements = t.split_statements(sql)
                self.assertTrue(statements)
                for s in statements:
                    self.assertNotIn(";", outside_quotes_and_comments(s))
                    self.assertTrue(outside_quotes_and_comments(s).strip())
                # Rejoining and splitting again is stable, and no code was lost.
                self.assertEqual(t.split_statements(";\n".join(statements)), statements)
                self.assertEqual(re.sub(r"[\s;]", "", outside_quotes_and_comments(";".join(statements))),
                                 re.sub(r"[\s;]", "", outside_quotes_and_comments(sql)))
        self.assertGreater(found, 100)

    def test_e4_anemia_on_snowflake_matches_the_spike(self):
        # The spike ran this script as 22 statements: the cohort init statement plus these 21.
        sql = open(os.path.join(stubs.ROOT, "cohort_scripts", "snowflake", "feature_condition_anemia.sql")).read()
        self.assertEqual(len(t.split_statements(sql)), 21)


class SqlLiteral(unittest.TestCase):
    def test_quotes_and_backslashes_per_dialect(self):
        name = "Crohn's disease \\ test"
        self.assertEqual(t.sql_literal(name, "Snowflake"), "'Crohn''s disease \\\\ test'")
        self.assertEqual(t.sql_literal(name, "Redshift"), "'Crohn''s disease \\\\ test'")
        self.assertEqual(t.sql_literal(name, "Databricks"), "'Crohn\\'s disease \\\\ test'")

    def test_escaped_literal_is_one_token_for_the_splitter(self):
        for dialect in ("Snowflake", "Redshift", "Databricks"):
            with self.subTest(dialect=dialect):
                sql = "INSERT INTO log VALUES (%s); SELECT 1" % t.sql_literal("a'; DROP TABLE x; --", dialect)
                self.assertEqual(len(t.split_statements(sql)), 2)

    def test_null_numbers_and_unknown_dialect(self):
        self.assertEqual(t.sql_literal(None, "Snowflake"), "NULL")
        self.assertEqual(t.sql_literal(611, "Databricks"), "611")
        with self.assertRaises(ValueError):
            t.sql_literal("x", "Oracle")


class ScratchTables(unittest.TestCase):
    SQL = ("CREATE TABLE @temp_database_schema.qkromrnsCodesets (id int);\n"
           "INSERT INTO @temp_database_schema.qkromrnsCodesets SELECT 1;\n"
           "DROP TABLE @temp_database_schema.qkromrnsCodesets;")

    def test_session_dialects_keep_the_bare_name(self):
        for dialect in ("Snowflake", "Redshift"):
            rendered, tables = t.render_temp_tables(self.SQL, dialect)
            self.assertNotIn("@temp_database_schema", rendered)
            self.assertIn("CREATE TABLE qkromrnsCodesets", rendered)
            self.assertEqual(tables, [])

    def test_databricks_tables_are_attributable_and_qualified(self):
        prefix = t.scratch_table_prefix("SOL_RWD_COHORT_DISCOVERY", 3)
        rendered, tables = t.render_temp_tables(self.SQL, "Databricks", prefix, "`cat-1`.`default`")
        name = "`cat-1`.`default`.`rwdtmp_sol_rwd_cohort_discovery__c3_qkromrnscodesets`"
        self.assertEqual(tables, [name])
        self.assertEqual(rendered.count(name), 3)
        self.assertNotIn("@temp_database_schema", rendered)
        with self.assertRaises(ValueError):
            t.render_temp_tables(self.SQL, "Databricks")

    def test_project_prefix_does_not_match_a_longer_key(self):
        self.assertTrue(t.is_project_scratch_table("rwdtmp_sol__c12_x", "SOL"))
        self.assertFalse(t.is_project_scratch_table("rwdtmp_sol_2__c12_x", "SOL"))
        self.assertFalse(t.is_project_scratch_table("rwdtmp_sol__c12_x", "SOL_2"))

    def test_qualifier_and_quoting(self):
        self.assertEqual(t.table_qualifier("`se-sandbox`.`business_solutions`.`PREP_person`"),
                         "`se-sandbox`.`business_solutions`")
        self.assertEqual(t.table_qualifier('"DB"."SCH"."T"'), '"DB"."SCH"')
        with self.assertRaises(ValueError):
            t.table_qualifier('"T"')
        self.assertEqual(t.quote_databricks_name("business_solutions.scratch"), "`business_solutions`.`scratch`")
        self.assertEqual(t.quote_databricks_name("`se-sandbox`.tmp"), "`se-sandbox`.`tmp`")


class FakeFrame:
    def __init__(self, value):
        self.iloc = {(0, 0): value}


class BuildOne(unittest.TestCase):
    COHORT = {"id": 7, "name": "Crohn's", "tables": ["person"], "script_file": "c.sql"}
    SCRIPT = ("CREATE TABLE @temp_database_schema.abCodesets (i int);\n"
              "DELETE FROM `c`.`s`.`cohort` WHERE cohort_definition_id = 7;\n"
              "DROP TABLE @temp_database_schema.abCodesets;")

    def executor(self, fail=False):
        ex = mock.MagicMock()

        def query_to_df(query, pre_queries=None, post_queries=None):
            if fail and pre_queries and any(q.startswith("DELETE") for q in pre_queries):
                raise Exception("During pre-query 'DELETE ...':\n boom")
            return FakeFrame(42)
        ex.query_to_df.side_effect = query_to_df
        return ex

    def test_databricks_success_drops_scratch_before_and_after(self):
        ex = self.executor()
        status = b.build_one(ex, self.COHORT, self.SCRIPT, "Databricks", "P", "`c`.`s`", "`c`.`s`.`cohort`")
        self.assertEqual(status, ("SUCCESS", 42, ""))
        scratch = "`c`.`s`.`rwdtmp_p__c7_abcodesets`"
        first, last = ex.query_to_df.call_args_list[0], ex.query_to_df.call_args_list[-1]
        self.assertEqual(first.kwargs["pre_queries"][0], "DROP TABLE IF EXISTS " + scratch)
        self.assertEqual(first.kwargs["post_queries"], [])  # no COMMIT on Databricks
        self.assertIn("cohort_definition_id = 7", first.args[0])
        self.assertEqual(last.kwargs["pre_queries"], ["DROP TABLE IF EXISTS " + scratch])

    def test_failure_is_reported_and_scratch_still_dropped(self):
        ex = self.executor(fail=True)
        status, count, error = b.build_one(ex, self.COHORT, self.SCRIPT, "Databricks", "P", "`c`.`s`",
                                           "`c`.`s`.`cohort`")
        self.assertEqual((status, count), ("FAILED", 42))
        self.assertEqual(error, "During pre-query 'DELETE ...': boom")
        self.assertEqual(ex.query_to_df.call_args_list[-1].kwargs["pre_queries"],
                         ["DROP TABLE IF EXISTS `c`.`s`.`rwdtmp_p__c7_abcodesets`"])

    def test_snowflake_commits_and_uses_session_tables(self):
        ex = self.executor()
        b.build_one(ex, self.COHORT, self.SCRIPT, "Snowflake", "P", None, '"D"."S"."COHORT"')
        self.assertEqual(ex.query_to_df.call_count, 1)  # no scratch tables to drop
        call = ex.query_to_df.call_args
        self.assertEqual(call.kwargs["post_queries"], ["COMMIT"])
        self.assertTrue(call.kwargs["pre_queries"][0].startswith("CREATE TABLE abCodesets"))


class BuildCohorts(unittest.TestCase):
    def test_continues_past_a_failure_logs_every_cohort_then_fails(self):
        batch = [{"id": 1, "name": "A", "tables": ["person"], "script_file": "a.sql"},
                 {"id": 2, "name": "B'", "tables": ["person"], "script_file": "b.sql"}]
        outcomes = {1: ("FAILED", 0, "bad"), 2: ("SUCCESS", 5, "")}
        executor = mock.MagicMock()
        patches = [
            mock.patch.object(b, "read_batch", return_value=batch),
            mock.patch.object(b, "build_one", side_effect=lambda ex, c, *a: outcomes[c["id"]]),
            mock.patch.object(b, "SQLExecutor2", return_value=executor),
            mock.patch.object(b, "get_setting", return_value="conn"),
            mock.patch.object(b, "cohort_connection_type", return_value="Snowflake"),
            mock.patch.object(b, "get_sql_path", side_effect=lambda name: '"S"."%s"' % name.upper()),
            mock.patch.object(b, "get_script_by_connection_type",
                              return_value="CREATE TABLE IF NOT EXISTS @cohort_building_log (x int);\n"
                                           "INSERT INTO @cohort_building_log VALUES @cohort_log ;"),
            mock.patch.object(b, "validate_cdm_tables"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with self.assertRaises(ValueError) as e:
            b.build_cohorts()
        self.assertIn("1 of 2", str(e.exception))
        self.assertIn("Cohort 1 (A): bad", str(e.exception))
        log_call = executor.query_to_df.call_args
        insert = log_call.kwargs["pre_queries"][1]
        self.assertIn("'B'''", insert)  # the name is escaped
        self.assertIn(", 1, 'A', 0, 'FAILED', 'bad', 'a.sql')", insert)
        self.assertIn(", 2, 'B''', 5, 'SUCCESS', '', 'b.sql')", insert)
        self.assertEqual(log_call.kwargs["post_queries"], ["COMMIT"])


if __name__ == "__main__":
    unittest.main()
