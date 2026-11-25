"""Step 4 part 3: what to characterize, the SQL of one run, and the recipe (DSS stubbed)."""
import re
import unittest
from unittest import mock

import stubs

stubs.install()

from solution.characterization import statements as st  # noqa: E402
from solution.pipelines import characterize_cohorts as cc  # noqa: E402
from solution.recipes.sql_text import (  # noqa: E402
    characterization_scratch_prefix, is_characterization_scratch_table, is_project_scratch_table,
    scratch_table_prefix,
)
from solution.setup import characterization as ch  # noqa: E402
from solution.setup.batch import as_int, batch_errors, latest_by_id  # noqa: E402

T1, T2, T3 = "2026-11-20T10:00:00Z", "2026-11-21T10:00:00Z", "2026-11-22T10:00:00Z"
DEFINITIONS = [{"id": 1, "name": "Anemia"}, {"id": 2, "name": "Crohn's"}, {"id": 3, "name": "Sepsis"},
               {"id": 4, "name": "Failed build"}]
BUILDS = [{"run_timestamp": T1, "id": 1, "count": 611, "status": "SUCCESS"},
          {"run_timestamp": T1, "id": 2, "count": 593, "status": "SUCCESS"},
          {"run_timestamp": T1, "id": 3, "count": 247, "status": "SUCCESS"},
          {"run_timestamp": T1, "id": 4, "count": 0, "status": "FAILED"},
          {"run_timestamp": T1, "id": 9, "count": 5, "status": "SUCCESS"}]  # no longer registered


def char(ts, cohort_id, build_ts=T1, status="SUCCESS"):
    return {"run_timestamp": ts, "id": cohort_id, "build_timestamp": build_ts, "count": 1, "status": status}


def by_id(rows):
    return {r["id"]: r for r in rows}


class SharedBatchRules(unittest.TestCase):
    def test_as_int_and_latest(self):
        self.assertEqual([as_int(v) for v in ("12", 12, " 7 ", "1.0", None, "x")], [12, 12, 7, None, None, None])
        logs = [{"id": 1, "run_timestamp": T2, "status": "FAILED"}, {"id": 1, "run_timestamp": T1, "status": "SUCCESS"}]
        self.assertEqual(latest_by_id(logs)[1]["status"], "FAILED")
        self.assertEqual(latest_by_id(logs, keep=lambda l: l["status"] == "SUCCESS")[1]["run_timestamp"], T1)

    def test_batch_errors(self):
        rows = [{"id": 1, "submit": True}, {"id": 1, "submit": True, "replace": True}, {"id": "x", "submit": True}]
        errors, valid = batch_errors(rows, [1], lambda r: "row %s" % r["id"], "cohort", "is done", "redo it")
        self.assertEqual(errors, ["row 1: cohort 1 is done. Tick Replace to redo it.",
                                  "row 1: cohort id 1 is also given to row 1.",
                                  "row x: the cohort id must be a whole number, 0 or more, not 'x'."])
        self.assertEqual(len(valid), 2)
        self.assertEqual(batch_errors([], [], str, "script", "", "")[0], ["Tick In batch on at least one script."])


class CharacterizationRows(unittest.TestCase):
    def test_first_run_offers_every_built_cohort_ticked_and_the_population(self):
        rows = ch.characterization_rows(DEFINITIONS, BUILDS, [])
        self.assertEqual([r["id"] for r in rows], [-1, 1, 2, 3])  # 4 failed, 9 not registered
        self.assertTrue(all(r["submit"] for r in rows))
        self.assertEqual({r["status"] for r in rows}, {ch.NOT_CHARACTERIZED})
        self.assertEqual(rows[1]["subjects"], 611)

    def test_statuses_after_runs(self):
        builds = BUILDS + [{"run_timestamp": T3, "id": 2, "count": 600, "status": "SUCCESS"}]  # 2 rebuilt
        logs = [char(T2, -1, ""), char(T2, 1), char(T2, 2), char(T2, 3, status="FAILED")]
        rows = by_id(ch.characterization_rows(DEFINITIONS, builds, logs))
        self.assertEqual((rows[-1]["status"], rows[-1]["submit"]), (ch.CHARACTERIZED, False))
        self.assertEqual((rows[1]["status"], rows[1]["submit"]), (ch.CHARACTERIZED, False))
        self.assertEqual((rows[2]["status"], rows[2]["submit"]), (ch.REBUILT, False))  # kept until ticked
        self.assertEqual((rows[3]["status"], rows[3]["submit"]), (ch.CHAR_FAILED, True))

    def test_a_failed_redo_shows_as_failed_and_still_needs_replace(self):
        logs = [char(T1, 1), char(T2, 1, status="FAILED")]
        rows = by_id(ch.characterization_rows(DEFINITIONS, BUILDS, logs))
        self.assertEqual((rows[1]["status"], rows[1]["submit"]), (ch.CHAR_FAILED, False))
        self.assertEqual(ch.validate_selection([dict(rows[1], submit=True)], [1], [1])[0][:9], "Anemia: c")

    def test_reimport_marks_cohorts_and_redoes_the_population(self):
        rows = by_id(ch.characterization_rows(DEFINITIONS, BUILDS, [char(T2, -1, ""), char(T2, 1)], imported_at=T3))
        self.assertEqual((rows[-1]["status"], rows[-1]["submit"]), (ch.REIMPORTED, True))
        self.assertEqual((rows[1]["status"], rows[1]["submit"]), (ch.REIMPORTED, False))
        self.assertTrue(ch.population_needed([char(T2, -1, "")], T3))
        self.assertFalse(ch.population_needed([char(T2, -1, "")], T1))

    def test_saved_batch_shows_as_in_batch(self):
        rows = by_id(ch.characterization_rows(DEFINITIONS, BUILDS, [char(T2, 1)], [{"id": 1, "replace": True}]))
        self.assertEqual((rows[1]["status"], rows[1]["submit"], rows[1]["replace"]), (ch.IN_BATCH, True, True))


class Selection(unittest.TestCase):
    def test_characterized_cohort_needs_replace(self):
        rows = [{"id": 1, "name": "Anemia", "submit": True}, {"id": -1, "population": True, "submit": True}]
        self.assertEqual(ch.validate_selection(rows, [1], [1]),
                         ["Anemia: cohort 1 is already characterized. Tick Replace to characterize it again."])
        rows[0]["replace"] = True
        self.assertEqual(ch.validate_selection(rows, [1], [1]), [])

    def test_unbuilt_and_empty(self):
        self.assertEqual(ch.validate_selection([{"id": 4, "name": "X", "submit": True}], [1], []),
                         ["X: cohort 4 has no successful build. Build it in Build Cohorts first."])
        self.assertEqual(ch.validate_selection([{"id": -1, "population": True, "submit": True}], [1], []),
                         ["Tick In batch on at least one cohort."])

    def test_submission_and_authority(self):
        rows = ch.characterization_rows(DEFINITIONS, BUILDS, [])
        self.assertEqual(ch.submission(rows), [{"id": 1, "replace": False}, {"id": 2, "replace": False},
                                               {"id": 3, "replace": False}])
        self.assertEqual(ch.selected_ids([{"id": 2}, {"id": 1}], [1, 2], []), [1, 2])
        self.assertEqual(ch.selected_ids([], [1], []), [])
        with self.assertRaises(ValueError):
            ch.selected_ids([{"id": 1, "replace": False}], [1], [1])


TABLES = {t: "DB.CDM.%s" % t.upper() for t in cc.OMOP_TABLES}
PATHS = {t: "DB.RES.%s" % t.upper() for t in list(st.RESULT_TABLES) + ["cohort"]}


class RunStatements(unittest.TestCase):
    def statements(self, connection_type, ids=(1, 2), population=True):
        args = ("rwdtmp_sol__ch_", "`cat`.`scratch`") if connection_type == "Databricks" else (None, None)
        return st.run_statements(connection_type, TABLES, PATHS, ids, population, *args)

    def test_every_dialect_is_fully_resolved_and_ordered(self):
        for ct in st.FOLDERS:
            statements, scratch, cohort = self.statements(ct)
            text = "\n".join(statements)
            self.assertEqual(re.findall(r"@\w+", text), [], ct)
            first_delete = next(i for i, s in enumerate(statements) if s.startswith("DELETE"))
            before, after = statements[:first_delete], statements[first_delete:]
            # Everything that can fail on the data runs before any result is deleted.
            self.assertEqual(len([s for s in before if s.startswith("CREATE TABLE IF NOT EXISTS DB.RES.")]), 6, ct)
            self.assertTrue(any(s.startswith("CREATE") and cohort in s for s in before), ct)
            self.assertGreater(len(before), 190, ct)
            self.assertEqual(after[:2], ["DELETE FROM DB.RES.COVARIATE WHERE cohort_definition_id IN (1, 2, -1)",
                                         "DELETE FROM DB.RES.COVARIATE_CONTINUOUS WHERE cohort_definition_id IN (1, 2, -1)"])
            inserts = after[2:6]
            self.assertEqual([s.split()[2] for s in inserts], ["DB.RES.COVARIATE", "DB.RES.COVARIATE_CONTINUOUS",
                                                               "DB.RES.COVARIATE_REF", "DB.RES.ANALYSIS_REF"], ct)
            self.assertIn("NOT IN (SELECT covariate_id FROM DB.RES.COVARIATE_REF)", inserts[2], ct)
            self.assertIn("NOT IN (SELECT analysis_id FROM DB.RES.ANALYSIS_REF)", inserts[3], ct)
            # Part 4: the cached pairs of the run's cohorts go; their balance against the population is redone.
            self.assertEqual(after[6], "DELETE FROM DB.RES.COVARIATE_BALANCE WHERE comparator_id <> -1 AND "
                                       "(cohort_definition_id IN (1, 2) OR comparator_id IN (1, 2))", ct)
            self.assertEqual(after[7], "DELETE FROM DB.RES.COVARIATE_BALANCE WHERE comparator_id = -1 AND "
                                       "cohort_definition_id IN (1, 2)", ct)
            self.assertTrue(after[8].startswith("INSERT INTO DB.RES.COVARIATE_BALANCE"), ct)
            code = [re.sub(r"--[^\n]*", "", s).split()[0] for s in after[9:]]
            self.assertEqual(set(code), {"DROP", "TRUNCATE"}, ct)  # cleanup only

    def test_cohort_table_and_population(self):
        statements, _, cohort = self.statements("Snowflake", ids=(3,), population=False)
        create = next(s for s in statements if s.startswith("CREATE TEMP TABLE rwdchar_cohort"))
        self.assertIn("FROM DB.RES.COHORT\nWHERE cohort_definition_id IN (3)", create)
        self.assertNotIn("UNION ALL", create)
        statements, _, _ = self.statements("Snowflake", ids=(), population=True)
        create = next(s for s in statements if s.startswith("CREATE TEMP TABLE rwdchar_cohort"))
        self.assertIn("-1 AS cohort_definition_id", create)
        self.assertIn("DATEADD(day, 365, start_date)", create)
        self.assertIn("FROM DB.CDM.OBSERVATION_PERIOD", create)
        self.assertIn("DELETE FROM DB.RES.COVARIATE WHERE cohort_definition_id IN (-1)", statements)
        with self.assertRaises(ValueError):
            self.statements("Snowflake", ids=(), population=False)

    def test_databricks_scratch_tables(self):
        statements, scratch, cohort = self.statements("Databricks")
        self.assertEqual(cohort, "`cat`.`scratch`.`rwdtmp_sol__ch_cohort`")
        self.assertIn(cohort, scratch)
        self.assertTrue(all(t.startswith("`cat`.`scratch`.`rwdtmp_sol__ch_") for t in scratch))
        self.assertIn("date_add(start_date, 365)", "\n".join(statements))
        with self.assertRaises(ValueError):
            st.run_statements("Databricks", TABLES, PATHS, [1], False)

    def test_result_tables_and_unresolved_tables(self):
        self.assertIn("standard_deviation FLOAT8", st.create_table("covariate_continuous", "t", "Redshift"))
        self.assertIn("covariate_name STRING", st.create_table("covariate_ref", "t", "Databricks"))
        with self.assertRaises(ValueError):
            st.fill("SELECT * FROM @cdm_database_schema.drug_era", {"person": "p"}, "c")

    def test_scratch_prefixes_do_not_cross(self):
        self.assertEqual(characterization_scratch_prefix("SOL"), "rwdtmp_sol__ch_")
        self.assertTrue(is_characterization_scratch_table("rwdtmp_sol__ch_rwdfeatxcov_1", "SOL"))
        self.assertFalse(is_project_scratch_table("rwdtmp_sol__ch_rwdfeatxcov_1", "SOL"))
        self.assertFalse(is_characterization_scratch_table(scratch_table_prefix("SOL", 3) + "codesets", "SOL"))


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def itertuples(self, index=False):
        return iter(self.rows)


class Recipe(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(cc, "get_sql_path", side_effect=lambda t: "R.%s" % t.upper())]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_success_logs_counts(self):
        ex = mock.MagicMock()
        ex.query_to_df.return_value = FakeFrame([(1, 611), (-1, 900)])
        rows = cc.characterize(ex, "Snowflake", "SOL", None, [1], True, {1: T1})
        self.assertEqual([r[1:5] for r in rows], [[1, T1, 611, "SUCCESS"], [-1, "", 900, "SUCCESS"]])
        main, log = ex.query_to_df.call_args_list
        self.assertEqual(main.kwargs["post_queries"], ["COMMIT"])
        self.assertIn("GROUP BY cohort_definition_id", main.args[0])
        self.assertTrue(log.kwargs["pre_queries"][0].startswith("INSERT INTO R.CHARACTERIZATION_LOG"))

    def test_failure_logs_every_cohort_and_drops_databricks_scratch(self):
        ex = mock.MagicMock()
        calls = []

        def query_to_df(query, pre_queries=None, post_queries=None):
            calls.append(pre_queries)
            if len(calls) == 1:
                raise Exception("boom")
            return FakeFrame([])
        ex.query_to_df.side_effect = query_to_df
        rows = cc.characterize(ex, "Databricks", "SOL", "`c`.`s`", [1, 2], False, {})
        self.assertEqual([(r[1], r[4], r[5]) for r in rows], [(1, "FAILED", "boom"), (2, "FAILED", "boom")])
        self.assertTrue(all(q.startswith("DROP TABLE IF EXISTS `c`.`s`.`rwdtmp_sol__ch_") for q in calls[1]))
        self.assertTrue(calls[2][0].startswith("INSERT INTO R.CHARACTERIZATION_LOG"))

    def run_recipe(self, submission, char_logs=(), rows=None):
        project = mock.MagicMock()
        reads = {"cohort_definition": DEFINITIONS, "cohort_building_log": BUILDS, "characterization_log": list(char_logs)}
        with mock.patch.object(cc.dataiku, "api_client") as api, \
                mock.patch.object(cc.dataiku, "Dataset", side_effect=lambda name, **k: name), \
                mock.patch.object(cc, "read_rows", side_effect=lambda ds, cols: reads[ds]), \
                mock.patch.object(cc, "cohort_connection_type", return_value="Snowflake"), \
                mock.patch.object(cc, "scratch_schema", return_value=None), \
                mock.patch.object(cc, "SQLExecutor2"), \
                mock.patch.object(cc, "imported_at", return_value=None), \
                mock.patch.object(cc, "get_setting", side_effect=lambda n, default=None: submission
                                  if n == cc.SUBMISSION else "conn"), \
                mock.patch.object(cc, "set_local") as set_local, \
                mock.patch.object(cc, "characterize", return_value=rows or []) as characterize:
            api.return_value.get_default_project.return_value = project
            result = cc.characterize_cohorts()
        return result, characterize, set_local

    def test_nothing_to_do(self):
        result, characterize, set_local = self.run_recipe([], [char(T2, -1, "")])
        self.assertEqual(result, [])
        characterize.assert_not_called()

    def test_batch_and_population_then_cleared(self):
        ok = [[T2, 1, T1, 611, "SUCCESS", ""], [T2, -1, "", 900, "SUCCESS", ""]]
        _, characterize, set_local = self.run_recipe([{"id": 1}], rows=ok)
        args = characterize.call_args.args
        self.assertEqual((args[4], args[5], args[6]), ([1], True, {1: T1}))
        set_local.assert_called_once()
        self.assertEqual(set_local.call_args.args[1:], (cc.SUBMISSION, []))

    def test_refusals_and_failures(self):
        with self.assertRaises(ValueError):  # characterized without Replace
            self.run_recipe([{"id": 1}], [char(T2, -1, ""), char(T2, 1)])
        with self.assertRaises(ValueError):
            self.run_recipe([{"id": 1}], rows=[[T2, 1, T1, 0, "FAILED", "boom"]])


if __name__ == "__main__":
    unittest.main()
