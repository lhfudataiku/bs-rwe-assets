"""R9 stage 2: what to extract, the SQL of one extract, and the recipe (DSS stubbed)."""
import importlib.util
import json
import os
import re
import sqlite3
import unittest
from unittest import mock

import stubs

stubs.install()

from solution.characterization import extraction as ex  # noqa: E402
from solution.characterization import statements as st  # noqa: E402
from solution.pipelines import extract_patient_covariates as pc  # noqa: E402
from solution.recipes.sql_text import (  # noqa: E402
    extraction_scratch_prefix, is_characterization_scratch_table, is_extraction_scratch_table,
    is_project_scratch_table, render_temp_tables,
)
from solution.setup import extraction as xs  # noqa: E402
from solution.variables import LOCAL_KEYS  # noqa: E402

T1, T2, T3 = "2026-11-20T10:00:00Z", "2026-11-21T10:00:00Z", "2026-11-22T10:00:00Z"
DEFINITIONS = [{"id": 1, "name": "Anemia"}, {"id": 2, "name": "Crohn's"}, {"id": 3, "name": "Sepsis"},
               {"id": 4, "name": "Failed build"}]
BUILDS = [{"run_timestamp": T1, "id": 1, "count": 611, "status": "SUCCESS"},
          {"run_timestamp": T1, "id": 2, "count": 593, "status": "SUCCESS"},
          {"run_timestamp": T1, "id": 3, "count": 247, "status": "SUCCESS"},
          {"run_timestamp": T1, "id": 4, "count": 0, "status": "FAILED"},
          {"run_timestamp": T1, "id": 9, "count": 5, "status": "SUCCESS"}]  # no longer registered
SQL_DIR = os.path.join(stubs.ROOT, "solution", "characterization", "sql")


def log(ts, cohort_id, build_ts=T1, status="SUCCESS"):
    return {"run_timestamp": ts, "id": cohort_id, "build_timestamp": build_ts, "count": 1, "status": status}


def by_id(rows):
    return {r["id"]: r for r in rows}


def load_tool():
    path = os.path.join(stubs.ROOT, "tools", "render_feature_extraction.py")
    spec = importlib.util.spec_from_file_location("render_feature_extraction", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ExtractionRows(unittest.TestCase):
    def test_built_cohorts_offered_none_ticked(self):
        rows = xs.extraction_rows(DEFINITIONS, BUILDS, [])
        self.assertEqual([r["id"] for r in rows], [1, 2, 3])  # 4 failed, 9 not registered, no population
        self.assertFalse(any(r["submit"] for r in rows))  # on request: nothing by default
        self.assertEqual({r["status"] for r in rows}, {xs.NOT_EXTRACTED})

    def test_statuses_after_runs(self):
        builds = BUILDS + [{"run_timestamp": T3, "id": 2, "count": 600, "status": "SUCCESS"}]
        logs = [log(T2, 1), log(T2, 2), log(T2, 3, status="FAILED")]
        rows = by_id(xs.extraction_rows(DEFINITIONS, builds, logs))
        self.assertEqual(rows[1]["status"], xs.EXTRACTED)
        self.assertEqual(rows[1]["extracted"], T2)
        self.assertEqual(rows[2]["status"], xs.REBUILT_SINCE_EXTRACTED)
        self.assertEqual(rows[3]["status"], xs.EXTRACTION_FAILED)
        rows = by_id(xs.extraction_rows(DEFINITIONS, BUILDS, [log(T2, 1)], imported_at=T3))
        self.assertEqual(rows[1]["status"], xs.REIMPORTED_SINCE_EXTRACTED)

    def test_saved_batch_and_written_back_batch(self):
        rows = by_id(xs.extraction_rows(DEFINITIONS, BUILDS, [log(T2, 1)], [{"id": 1, "replace": True, "saved": T3}]))
        self.assertEqual((rows[1]["status"], rows[1]["submit"], rows[1]["replace"]), (xs.EXTRACTION_IN_BATCH, True, True))
        # An open Setup page restored the batch the run had cleared: its entries expired.
        stale = [{"id": 1, "replace": False, "saved": T1}]
        self.assertEqual(xs.live_extraction_submission(stale, [log(T2, 1)]), [])
        self.assertFalse(by_id(xs.extraction_rows(DEFINITIONS, BUILDS, [log(T2, 1)], stale))[1]["submit"])

    def test_replace_rule_and_authority(self):
        rows = [{"id": 1, "name": "Anemia", "submit": True}]
        self.assertEqual(xs.validate_extraction(rows, [1, 2], [1]),
                         ["Anemia: cohort 1 is already extracted. Tick Replace to extract it again."])
        rows[0]["replace"] = True
        self.assertEqual(xs.validate_extraction(rows, [1, 2], [1]), [])
        self.assertEqual(xs.validate_extraction([{"id": 4, "name": "X", "submit": True}], [1], []),
                         ["X: cohort 4 has no successful build. Build it in Build Cohorts first."])
        self.assertEqual(xs.validate_extraction([], [1], []), ["Tick In batch on at least one cohort."])
        self.assertEqual(xs.extraction_submission([{"id": 2, "submit": True}, {"id": 3}], T3),
                         [{"id": 2, "replace": False, "saved": T3}])
        self.assertEqual(xs.selected_extraction_ids([{"id": 2}, {"id": 1}], [1, 2], []), [1, 2])
        self.assertEqual(xs.selected_extraction_ids([], [1], []), [])
        with self.assertRaises(ValueError):
            xs.selected_extraction_ids([{"id": 1}], [1], [1])

    def test_contract_and_names_apart_from_characterization(self):
        self.assertIn(xs.EXTRACTION_SUBMISSION, LOCAL_KEYS)
        # The tile inlines both modules into one namespace, which refuses a shared top-level name.
        import solution.setup.characterization as ch
        mine = {n for n in vars(xs) if not n.startswith("__")} - {"as_int", "batch_errors", "latest_by_id",
                                                                   "SUCCESS", "live_submission", "utc_timestamp"}
        self.assertEqual(mine & set(vars(ch)), set())


class PresetsMatchTheRender(unittest.TestCase):
    def test_scratch_tables_and_datasets(self):
        tool = load_tool()
        with open(os.path.join(SQL_DIR, "MANIFEST.json")) as fh:
            manifest = json.load(fh)
        self.assertEqual(ex.SCRATCH_TABLES, tool.PERSON_TABLES)
        self.assertEqual(ex.SCRATCH_TABLES, manifest["modes"]["person"]["scratch_tables"])
        self.assertEqual(ex.SESSION_ID, tool.SESSION_ID)
        self.assertEqual(ex.EXTRACTION_TOKEN, tool.MODES["person"]["cohort_table"])
        self.assertEqual(sorted(p for p, _, _, _ in ex.PRESETS), sorted(manifest["presets"]))
        self.assertEqual(sorted(ex.DATASETS), sorted(ex.SCRATCH_TABLES.values()))
        self.assertTrue(all(d.startswith("patient_cov_") for d in ex.DATASETS.values()))
        self.assertEqual(len(set(ex.DATASETS.values())), 11)

    def test_kinds_follow_feature_extraction(self):
        # analysis_ref's is_binary, as rendered: 'Y' for the binary presets.
        text = open(os.path.join(SQL_DIR, "snowflake", "person", "construction.sql")).read()
        binary = {int(a): b for a, b in re.findall(
            r"SELECT\s+(\d+)\s+AS analysis_id,.*?CAST\('([YN])' AS VARCHAR\(1\)\) AS is_binary", text, re.S)}
        self.assertEqual(len(binary), 11)
        self.assertEqual({a for a, b in binary.items() if b == "Y"},
                         {a for _, a, _, kind in ex.PRESETS if kind == "binary"})


TABLES = {t: "DB.CDM.%s" % t.upper() for t in pc.OMOP_TABLES}
PATHS = {t: "DB.RES.%s" % t.upper() for t in list(ex.OUTPUT_TABLES) + ["cohort"]}
CHARACTERIZATION_TABLES = [t.upper() for t in st.TABLES]


class RunStatements(unittest.TestCase):
    def statements(self, connection_type, ids=(1, 2)):
        args = ("rwdtmp_sol__pc_", "`cat`.`scratch`") if connection_type == "Databricks" else (None, None)
        return ex.extraction_statements(connection_type, TABLES, PATHS, ids, *args)

    def test_every_dialect_is_fully_resolved_and_ordered(self):
        for ct in st.FOLDERS:
            statements, scratch, cohort = self.statements(ct)
            text = "\n".join(statements)
            self.assertEqual(re.findall(r"@\w+", text), [], ct)
            first_delete = next(i for i, s in enumerate(statements) if s.startswith("DELETE"))
            before, after = statements[:first_delete], statements[first_delete:]
            # Everything that reads the data runs before any output is deleted.
            self.assertEqual(len([s for s in before if s.startswith("CREATE TABLE IF NOT EXISTS DB.RES.")]), 13, ct)
            self.assertTrue(any(s.startswith("CREATE") and cohort in s and "ROW_NUMBER()" in s for s in before), ct)
            self.assertGreater(len(before), 80, ct)
            # Per preset: delete the run's cohorts, then insert from its scratch table.
            pairs = after[:22]
            for (bare, analysis_id), i in zip(ex.SCRATCH_TABLES.items(), range(0, 22, 2)):
                path = "DB.RES.%s" % ex.DATASETS[analysis_id].upper()
                self.assertEqual(pairs[i], "DELETE FROM %s WHERE cohort_definition_id IN (1, 2)" % path, ct)
                self.assertTrue(pairs[i + 1].startswith("INSERT INTO %s (" % path), ct)
                self.assertIn("FROM %s f\n" % ex.scratch_table_name(ct, bare, "rwdtmp_sol__pc_", "`cat`.`scratch`"),
                              pairs[i + 1], ct)
            self.assertTrue(after[22].startswith("INSERT INTO DB.RES.PATIENT_COV_REF"), ct)
            self.assertIn("NOT IN (SELECT covariate_id FROM DB.RES.PATIENT_COV_REF)", after[22], ct)
            code = [re.sub(r"--[^\n]*", "", s).split()[0] for s in after[23:]]
            self.assertEqual(set(code), {"DROP", "TRUNCATE"}, ct)  # cleanup only
            # No minimum cell count (decision 4), and the characterization's tables are never touched.
            self.assertNotIn("< 5", text, ct)
            for name in CHARACTERIZATION_TABLES:
                self.assertNotIn("DB.RES.%s " % name, text + " ", ct)
                self.assertNotIn("DB.RES.%s\n" % name, text, ct)

    def test_scratch_tables_are_those_the_construction_creates(self):
        for ct in st.FOLDERS:
            statements, scratch, _ = self.statements(ct)
            text = "\n".join(statements)
            for bare in ex.SCRATCH_TABLES:
                name = ex.scratch_table_name(ct, bare, "rwdtmp_sol__pc_", "`cat`.`scratch`")
                self.assertRegex(text, r"CREATE (TEMP )?TABLE %s(?!\w)" % re.escape(name), ct)

    def test_every_qualified_omop_column_has_its_table_in_scope(self):
        # Step 4 part 5: `condition_era.person_id` fails once the table has a quoted full name.
        for ct in st.FOLDERS:
            for statement in self.statements(ct)[0]:
                for name in set(re.findall(r"\b(%s)\.\w+" % "|".join(pc.OMOP_TABLES), statement)):
                    in_scope = re.search(r"%s\s+(AS\s+)?%s\b" % (re.escape(TABLES[name]), name), statement)
                    self.assertTrue(in_scope, "%s: %s.<column> without %s in scope" % (ct, name, name))

    def test_databricks_scratch_tables(self):
        statements, scratch, cohort = self.statements("Databricks")
        self.assertEqual(cohort, "`cat`.`scratch`.`rwdtmp_sol__pc_cohort`")
        self.assertIn(cohort, scratch)
        self.assertTrue(all(t.startswith("`cat`.`scratch`.`rwdtmp_sol__pc_") for t in scratch))
        with self.assertRaises(ValueError):
            ex.extraction_statements("Databricks", TABLES, PATHS, [1])
        with self.assertRaises(ValueError):
            self.statements("Snowflake", ids=())

    def test_scratch_prefixes_do_not_cross(self):
        self.assertEqual(extraction_scratch_prefix("SOL"), "rwdtmp_sol__pc_")
        name = "rwdtmp_sol__pc_rwdfeatxcov_1"
        self.assertTrue(is_extraction_scratch_table(name, "SOL"))
        self.assertFalse(is_project_scratch_table(name, "SOL"))
        self.assertFalse(is_characterization_scratch_table(name, "SOL"))
        self.assertFalse(is_extraction_scratch_table("rwdtmp_sol__ch_rwdfeatxcov_1", "SOL"))
        self.assertFalse(is_extraction_scratch_table("rwdtmp_sol__c3_codesets", "SOL"))

    def test_output_tables(self):
        self.assertIn("cohort_start_date DATE", ex.create_output_table("patient_cov_charlson_index", "t", "Redshift"))
        self.assertIn("covariate_value DOUBLE", ex.create_output_table("patient_cov_demographics_age", "t", "Databricks"))
        create = ex.create_output_table("patient_cov_log", "t", "Snowflake")
        self.assertIn("rows_drug_group_era_long_term BIGINT", create)
        self.assertEqual(len(ex.LOG_COLUMNS), 7 + 11)


class OutputSqlRuns(unittest.TestCase):
    """The SQL this module writes (not FeatureExtraction's), run in SQLite on stand-in scratch tables."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.paths = {t: t for t in ex.OUTPUT_TABLES}
        for t in ex.OUTPUT_TABLES:
            self.db.execute(ex.create_output_table(t, t, "Snowflake").replace(" IF NOT EXISTS", ""))
        self.db.execute("CREATE TABLE rwdpcov_cohort (row_id, cohort_definition_id, subject_id, cohort_start_date, "
                        "cohort_end_date)")
        for bare in ex.SCRATCH_TABLES:
            self.db.execute("CREATE TABLE rwdfeatx%s (row_id, covariate_id, covariate_value)" % bare)
        self.db.execute("CREATE TABLE rwdfeatxcov_ref (covariate_id, covariate_name, analysis_id, concept_id, "
                        "value_as_concept_id, collisions)")
        self.db.execute("CREATE TABLE rwdfeatxanalysis_ref (analysis_id, analysis_name, domain_id, start_day, "
                        "end_day, is_binary, missing_means_zero)")
        for _, analysis_id, _, kind in ex.PRESETS:
            self.db.execute("INSERT INTO rwdfeatxanalysis_ref VALUES (?, ?, 'X', -365, 0, ?, 'N')",
                            (analysis_id, "A%d" % analysis_id, "Y" if kind == "binary" else "N"))

    def load(self, entries, covariates):
        """entries: [(row_id, cohort, subject, start)]; covariates: [(scratch table, row_id, covariate_id, value)]."""
        for t in ["rwdpcov_cohort", "rwdfeatxcov_ref"] + ["rwdfeatx" + b for b in ex.SCRATCH_TABLES]:
            self.db.execute("DELETE FROM %s" % t)
        self.db.executemany("INSERT INTO rwdpcov_cohort VALUES (?, ?, ?, ?, '2020-12-31')", entries)
        for bare, row_id, covariate_id, value in covariates:
            self.db.execute("INSERT INTO rwdfeatx%s VALUES (?, ?, ?)" % bare, (row_id, covariate_id, value))
        for covariate_id in sorted({c[2] for c in covariates}):
            analysis_id = ex.SCRATCH_TABLES[[c for c in covariates if c[2] == covariate_id][0][0]]
            self.db.execute("INSERT INTO rwdfeatxcov_ref VALUES (?, ?, ?, ?, 0, 0)",
                            (covariate_id, "C%d" % covariate_id, analysis_id, covariate_id // 1000))

    def run_outputs(self, ids):
        for statement in ex.output_statements("Snowflake", self.paths, "rwdpcov_cohort", ids):
            self.db.execute(statement)

    def rows(self, table):
        return sorted(self.db.execute("SELECT * FROM %s" % table).fetchall())

    def test_one_row_per_entry_in_its_preset_and_the_reference(self):
        # Subject 7 has two entries in cohort 1: each keeps its own rows (decision 3).
        self.load([(1, 1, 7, "2020-01-01"), (2, 1, 7, "2020-06-01"), (3, 2, 8, "2020-02-01")],
                  [("cov_3", 1, 8507001, 1), ("cov_3", 2, 8507001, 1), ("cov_3", 3, 8532001, 1),
                   ("cov_9", 1, 1002, 71), ("cov_9", 2, 1002, 72), ("cov_1", 3, 201826210, 1)])
        self.run_outputs([1, 2])
        self.assertEqual(self.rows("patient_cov_demographics_gender"),
                         [(1, 7, "2020-01-01", 8507001, 1.0), (1, 7, "2020-06-01", 8507001, 1.0),
                          (2, 8, "2020-02-01", 8532001, 1.0)])
        self.assertEqual(self.rows("patient_cov_demographics_age"),
                         [(1, 7, "2020-01-01", 1002, 71.0), (1, 7, "2020-06-01", 1002, 72.0)])
        self.assertEqual(self.rows("patient_cov_condition_group_era_long_term"),
                         [(2, 8, "2020-02-01", 201826210, 1.0)])
        ref = {r[0]: r for r in self.rows("patient_cov_ref")}
        self.assertEqual(sorted(ref), [1002, 8507001, 8532001, 201826210])
        self.assertEqual(ref[1002][3:], (2, "A2", "X", -365, 0, "N", "patient_cov_demographics_age"))
        self.assertEqual(ref[201826210][-1], "patient_cov_condition_group_era_long_term")

    def test_replace_redoes_only_the_run_cohorts_and_keeps_reference_ids(self):
        self.load([(1, 1, 7, "2020-01-01"), (2, 2, 8, "2020-02-01")],
                  [("cov_3", 1, 8507001, 1), ("cov_3", 2, 8532001, 1)])
        self.run_outputs([1, 2])
        # Cohort 1 redone: now subject 9 only. Cohort 2's rows stay; no duplicates; the ref keeps old ids.
        self.load([(1, 1, 9, "2020-03-01")], [("cov_3", 1, 8532001, 1)])
        self.run_outputs([1])
        self.assertEqual(self.rows("patient_cov_demographics_gender"),
                         [(1, 9, "2020-03-01", 8532001, 1.0), (2, 8, "2020-02-01", 8532001, 1.0)])
        self.assertEqual([r[0] for r in self.rows("patient_cov_ref")], [8507001, 8532001])

    def test_counts_and_log(self):
        self.load([(1, 1, 7, "2020-01-01"), (2, 1, 8, "2020-01-01")], [("cov_3", 1, 8507001, 1)])
        self.run_outputs([1])
        counts = self.db.execute(ex.extraction_count_query("rwdpcov_cohort", self.paths, [1])).fetchall()
        self.assertEqual(sorted(counts), [(1, "entries", 2), (1, "patient_cov_demographics_gender", 1)])
        row = pc.log_row(T2, 1, T1, "SUCCESS", "", 3, {"entries": 2, "patient_cov_demographics_gender": 1})
        for statement in ex.extraction_log_statement("patient_cov_log", [row], "Snowflake"):
            self.db.execute(statement)
        self.assertEqual(self.rows("patient_cov_log"), [(T2, 1, T1, 2, "SUCCESS", "", 3, 1) + (0,) * 10])


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def itertuples(self, index=False):
        return iter(self.rows)


class Recipe(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(pc, "get_sql_path", side_effect=lambda t: "R.%s" % t.upper())
        p.start()
        self.addCleanup(p.stop)

    def test_success_logs_counts(self):
        exe = mock.MagicMock()
        exe.query_to_df.return_value = FakeFrame([(1, "entries", 611), (1, "patient_cov_demographics_gender", 611),
                                                  (2, "entries", 593)])
        rows = pc.extract(exe, "Snowflake", "SOL", None, [2, 1], {1: T1, 2: T1})
        self.assertEqual([r[1:5] for r in rows], [[1, T1, 611, "SUCCESS"], [2, T1, 593, "SUCCESS"]])
        self.assertEqual(rows[0][7], 611)  # rows_demographics_gender
        main, log_call = exe.query_to_df.call_args_list
        self.assertEqual(main.kwargs["post_queries"], ["COMMIT"])
        self.assertIn("'entries' AS what", main.args[0])
        self.assertTrue(log_call.kwargs["pre_queries"][0].startswith("INSERT INTO R.PATIENT_COV_LOG"))

    def test_failure_logs_every_cohort_and_drops_databricks_scratch(self):
        exe = mock.MagicMock()
        calls = []

        def query_to_df(query, pre_queries=None, post_queries=None):
            calls.append(pre_queries)
            if len(calls) == 1:
                raise Exception("boom")
            return FakeFrame([])
        exe.query_to_df.side_effect = query_to_df
        rows = pc.extract(exe, "Databricks", "SOL", "`c`.`s`", [1, 2], {})
        self.assertEqual([(r[1], r[4], r[5]) for r in rows], [(1, "FAILED", "boom"), (2, "FAILED", "boom")])
        self.assertTrue(all(q.startswith("DROP TABLE IF EXISTS `c`.`s`.`rwdtmp_sol__pc_") for q in calls[1]))
        self.assertTrue(calls[2][0].startswith("INSERT INTO R.PATIENT_COV_LOG"))

    def run_recipe(self, submission, logs=(), rows=None):
        project = mock.MagicMock()
        reads = {"cohort_definition": DEFINITIONS, "cohort_building_log": BUILDS, "patient_cov_log": list(logs)}
        with mock.patch.object(pc.dataiku, "api_client") as api, \
                mock.patch.object(pc.dataiku, "Dataset", side_effect=lambda name, **k: name), \
                mock.patch.object(pc, "read_rows", side_effect=lambda ds, cols: reads[ds]), \
                mock.patch.object(pc, "cohort_connection_type", return_value="Snowflake"), \
                mock.patch.object(pc, "scratch_schema", return_value=None), \
                mock.patch.object(pc, "SQLExecutor2"), \
                mock.patch.object(pc, "get_setting", side_effect=lambda n, default=None: submission
                                  if n == pc.EXTRACTION_SUBMISSION else "conn"), \
                mock.patch.object(pc, "set_local") as set_local, \
                mock.patch.object(pc, "extract", return_value=rows or []) as extract:
            api.return_value.get_default_project.return_value = project
            result = pc.extract_patient_covariates()
        return result, extract, set_local

    def test_nothing_ticked_extracts_nothing(self):
        result, extract, set_local = self.run_recipe([])
        self.assertEqual(result, [])
        extract.assert_not_called()
        set_local.assert_not_called()

    def test_batch_then_cleared(self):
        ok = [pc.log_row(T2, i, T1, "SUCCESS", "", 5) for i in (1, 3)]
        _, extract, set_local = self.run_recipe([{"id": 3, "saved": T1}, {"id": 1, "saved": T1}], rows=ok)
        self.assertEqual((extract.call_args.args[4], extract.call_args.args[5]), ([1, 3], {1: T1, 3: T1}))
        self.assertEqual(set_local.call_args.args[1:], (pc.EXTRACTION_SUBMISSION, []))

    def test_a_written_back_batch_runs_nothing(self):
        result, extract, _ = self.run_recipe([{"id": 1, "replace": False, "saved": T1}], [log(T2, 1)])
        self.assertEqual(result, [])
        extract.assert_not_called()

    def test_refusals_and_failures(self):
        with self.assertRaises(ValueError):  # extracted, then saved again without Replace
            self.run_recipe([{"id": 1, "saved": T3}], [log(T2, 1)])
        with self.assertRaises(ValueError):
            self.run_recipe([{"id": 1}], rows=[pc.log_row(T2, 1, T1, "FAILED", "boom", 1)])


if __name__ == "__main__":
    unittest.main()
