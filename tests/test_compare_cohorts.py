"""Step 4 part 4: standardized differences, the comparison cache and the webapp services.

The balance SQL is run in SQLite over small stored aggregates and checked against a hand
calculation of the two formulas (decision 3).
"""
import math
import sqlite3
import unittest
from unittest import mock

import stubs

stubs.install()

from solution.characterization import statements as st  # noqa: E402
from solution.compare import balance as bal  # noqa: E402
from solution.compare import comparison as cmp  # noqa: E402
from solution.compare import services as svc  # noqa: E402
from solution.pipelines import characterize_cohorts as cc  # noqa: E402

PATHS = {t: t for t in bal.INPUT_TABLES + (bal.BALANCE_TABLE,)}
# covariate_id: (name, analysis id); analysis id: missing_means_zero
REF = {8507001: ("gender = FEMALE", 1), 1001: ("condition group A", 210), 1002: ("condition group B", 210),
       1003: ("everyone has it", 210), 2: ("age in years", 2), 1901: ("Charlson index", 901),
       9: ("time in cohort", 9)}
ANALYSES = {1: "N", 210: "N", 2: "N", 901: "Y", 9: "N"}
BINARY = [(1, 8507001, 0.6), (1, 1001, 0.2), (1, 1003, 1.0),
          (2, 8507001, 0.4), (2, 1002, 0.5), (2, 1003, 1.0),
          (-1, 8507001, 0.5), (-1, 1001, 0.1), (-1, 1002, 0.25), (-1, 1003, 1.0)]
CONTINUOUS = [(1, 2, 50.0, 10.0), (1, 1901, 1.0, 0.5), (1, 9, 300.0, 30.0),
              (2, 2, 40.0, 20.0),
              (-1, 2, 45.0, 15.0), (-1, 1901, 0.5, 1.0)]


def database():
    db = sqlite3.connect(":memory:")
    db.create_function("SQRT", 1, lambda x: None if x is None else math.sqrt(x))
    db.execute("CREATE TABLE covariate (cohort_definition_id, covariate_id, sum_value, average_value)")
    db.execute("CREATE TABLE covariate_continuous (cohort_definition_id, covariate_id, average_value, "
               "standard_deviation)")
    db.execute("CREATE TABLE covariate_ref (covariate_id, covariate_name, analysis_id)")
    db.execute("CREATE TABLE analysis_ref (analysis_id, missing_means_zero)")
    db.execute("CREATE TABLE covariate_balance (%s)" % ", ".join(bal.BALANCE_COLUMNS))
    db.executemany("INSERT INTO covariate VALUES (?, ?, ?, ?)",
                   [(c, k, round(p * (1000 if c == -1 else 100)), p) for c, k, p in BINARY])
    db.executemany("INSERT INTO covariate_continuous VALUES (?, ?, ?, ?)", CONTINUOUS)
    db.executemany("INSERT INTO covariate_ref VALUES (?, ?, ?)", [(k, n, a) for k, (n, a) in REF.items()])
    db.executemany("INSERT INTO analysis_ref VALUES (?, ?)", list(ANALYSES.items()))
    return db


def rows(db, sql):
    cursor = db.execute(sql)
    columns = [d[0] for d in cursor.description]
    return {(r[0], r[1], r[2]): dict(zip(columns, r)) for r in cursor.fetchall()}


def binary_smd(p1, p2):
    return (p1 - p2) / math.sqrt((p1 * (1 - p1) + p2 * (1 - p2)) / 2)


def continuous_smd(m1, s1, m2, s2):
    return (m1 - m2) / math.sqrt((s1 ** 2 + s2 ** 2) / 2)


class Formulas(unittest.TestCase):
    def setUp(self):
        self.db = database()

    def test_columns_and_hand_calculation_against_the_population(self):
        cursor = self.db.execute(bal.balance_sql(PATHS, [1]))
        self.assertEqual([d[0] for d in cursor.description], bal.BALANCE_COLUMNS)
        got = rows(self.db, bal.balance_sql(PATHS, [1]))
        self.assertAlmostEqual(got[(1, -1, 8507001)]["std_diff"], binary_smd(0.6, 0.5))
        self.assertAlmostEqual(got[(1, -1, 1001)]["std_diff"], binary_smd(0.2, 0.1))
        self.assertAlmostEqual(got[(1, -1, 2)]["std_diff"], continuous_smd(50, 10, 45, 15))
        self.assertAlmostEqual(got[(1, -1, 1901)]["std_diff"], continuous_smd(1.0, 0.5, 0.5, 1.0))
        self.assertAlmostEqual(got[(1, -1, 8507001)]["abs_std_diff"], abs(binary_smd(0.6, 0.5)))
        row = got[(1, -1, 2)]
        self.assertEqual((row["covariate_name"], row["analysis_id"], row["is_binary"]), ("age in years", 2, "N"))
        self.assertEqual(got[(1, -1, 1001)]["is_binary"], "Y")

    def test_covariate_on_one_side_only(self):
        got = rows(self.db, bal.balance_sql(PATHS, [1], 2))
        # Binary: no row means nobody has it, so 0.
        self.assertAlmostEqual(got[(1, 2, 1001)]["std_diff"], binary_smd(0.2, 0.0))
        self.assertAlmostEqual(got[(1, 2, 1002)]["std_diff"], binary_smd(0.0, 0.5))
        self.assertEqual(got[(1, 2, 1002)]["cohort_mean"], 0)
        # Continuous with missing_means_zero = 'Y' (Charlson): 0 and 0.
        self.assertAlmostEqual(got[(1, 2, 1901)]["std_diff"], continuous_smd(1.0, 0.5, 0, 0))
        # Continuous without it: unknown, so no difference.
        self.assertIsNone(got[(1, 2, 9)]["comparator_mean"])
        self.assertIsNone(got[(1, 2, 9)]["std_diff"])
        self.assertEqual(len(got), 4 + 3)  # every covariate of either side, binary then continuous

    def test_zero_variance_gives_null(self):
        got = rows(self.db, bal.balance_sql(PATHS, [1], 2))
        self.assertIsNone(got[(1, 2, 1003)]["std_diff"])
        self.assertIsNone(got[(1, 2, 1003)]["abs_std_diff"])

    def test_antisymmetry(self):
        ab = rows(self.db, bal.pair_balance_sql(PATHS, 1, 2))
        ba = rows(self.db, bal.pair_balance_sql(PATHS, 2, 1))
        self.assertEqual({k for _, _, k in ab}, {k for _, _, k in ba})
        for (_, _, k), row in ab.items():
            other = ba[(2, 1, k)]["std_diff"]
            if row["std_diff"] is None:
                self.assertIsNone(other, k)
            else:
                self.assertAlmostEqual(row["std_diff"], -other, msg=k)

    def test_several_cohorts_in_one_statement_equal_one_at_a_time(self):
        together = rows(self.db, bal.balance_sql(PATHS, [2, 1]))
        apart = rows(self.db, bal.balance_sql(PATHS, [1]))
        apart.update(rows(self.db, bal.balance_sql(PATHS, [2])))
        self.assertEqual(together, apart)

    def test_refusals(self):
        with self.assertRaises(ValueError):
            bal.balance_sql(PATHS, [1], 1)
        with self.assertRaises(ValueError):
            bal.balance_sql(PATHS, [])
        with self.assertRaises(ValueError):
            bal.balance_sql({"covariate": "c"}, [1])
        with self.assertRaises(ValueError):
            bal.balance_sql(PATHS, ["1; DROP TABLE x"])


class MinimumCellCount(unittest.TestCase):
    def setUp(self):
        self.db = database()
        # Cohort 1: 3 of 100 people have 1004; the population: 40 of 1000. Cohort 2: 6 of 100 have 1005.
        self.db.executemany("INSERT INTO covariate VALUES (?, ?, ?, ?)",
                            [(1, 1004, 3, 0.03), (-1, 1004, 40, 0.04), (2, 1005, 6, 0.06)])
        self.db.executemany("INSERT INTO covariate_ref VALUES (?, ?, ?)", [(1004, "rare", 210), (1005, "six", 210)])

    def test_small_cells_never_reach_the_balance(self):
        got = rows(self.db, bal.balance_sql(PATHS, [1]))
        self.assertNotIn((1, -1, 1004), got)  # 3 people: left out
        self.assertIn((1, -1, 1001), got)     # 20 against 100
        self.assertIn((1, -1, 1002), got)     # 0 against 250: 0 is not a small cell
        got = rows(self.db, bal.balance_sql(PATHS, [2], 1))
        self.assertAlmostEqual(got[(2, 1, 1005)]["std_diff"], binary_smd(0.06, 0.0))
        self.assertIn((1, -1, 1004), rows(self.db, bal.balance_sql(PATHS, [1], min_cell_count=1)))

    def test_balance_first_then_the_cut(self):
        for s in bal.write_balance_statements(PATHS, [1, 2]) + bal.censor_statements(PATHS, [1, 2, -1]):
            self.db.execute(s)
        stored = {(c, k) for c, k in self.db.execute("SELECT cohort_definition_id, covariate_id FROM covariate")}
        self.assertNotIn((1, 1004), stored)
        self.assertIn((-1, 1004), stored)
        self.assertIn((2, 1005), stored)
        # The balance against the population came from the full rows, before the cut.
        self.assertIn((2, -1, 1001), rows(self.db, "SELECT * FROM covariate_balance"))


class Cache(unittest.TestCase):
    def test_write_then_recharacterize(self):
        db = database()
        for s in bal.write_balance_statements(PATHS, [1, 2]) + bal.write_balance_statements(PATHS, [1], 2) \
                + bal.write_balance_statements(PATHS, [2], 1):
            db.execute(s)
        pairs = {(a, b) for a, b in db.execute(bal.cached_pairs_query("covariate_balance"))}
        self.assertEqual(pairs, {(1, -1), (2, -1), (1, 2), (2, 1)})
        # Writing a pair again replaces it rather than doubling it.
        for s in bal.write_balance_statements(PATHS, [1], 2):
            db.execute(s)
        self.assertEqual(db.execute(bal.pair_cached_query("covariate_balance", 1, 2)).fetchone()[0],
                         len(rows(db, bal.pair_balance_sql(PATHS, 1, 2))))
        # Re-characterizing cohort 1: its pairs go, its population rows are redone, cohort 2's stay.
        for s in bal.recharacterized_statements(PATHS, [1], [1]):
            db.execute(s)
        pairs = {(a, b) for a, b in db.execute(bal.cached_pairs_query("covariate_balance"))}
        self.assertEqual(pairs, {(1, -1), (2, -1)})

    def test_population_recomputed_alone(self):
        statements = bal.recharacterized_statements(PATHS, [], [1, 2, -1])
        self.assertEqual(statements[0], "DELETE FROM covariate_balance WHERE comparator_id = -1 AND "
                                        "cohort_definition_id IN (1, 2)")
        self.assertEqual(len(statements), 2)  # no pair deleted
        self.assertEqual(bal.recharacterized_statements(PATHS, [], []), [])

    def test_population_balance_ids(self):
        logs = [{"run_timestamp": "T1", "id": 1, "status": "SUCCESS"},
                {"run_timestamp": "T1", "id": 2, "status": "SUCCESS"},
                {"run_timestamp": "T2", "id": 2, "status": "FAILED"},
                {"run_timestamp": "T1", "id": -1, "status": "SUCCESS"}]
        self.assertEqual(cc.population_balance_ids(logs, [3], False), [3])
        self.assertEqual(cc.population_balance_ids(logs, [3], True), [1, 3])  # 2's latest attempt failed


T1, T2, T3 = "2026-11-20T10:00:00Z", "2026-11-21T10:00:00Z", "2026-11-22T10:00:00Z"
CHAR = [{"run_timestamp": T1, "id": -1, "status": "SUCCESS"}, {"run_timestamp": T1, "id": 1, "status": "SUCCESS"},
        {"run_timestamp": T2, "id": 2, "status": "SUCCESS"}, {"run_timestamp": T1, "id": 3, "status": "SUCCESS"},
        {"run_timestamp": T2, "id": 3, "status": "FAILED"}]
DEFINITIONS = [{"id": 1, "name": "Anemia"}, {"id": 2, "name": "Crohn's"}, {"id": 3, "name": "Sepsis"},
               {"id": 4, "name": "Not characterized"}]
NAMES = {1: "Anemia", 2: "Crohn's", 3: "Sepsis", 4: "Not characterized"}


class Requests(unittest.TestCase):
    def test_comparable_and_problems(self):
        characterized = cmp.comparable(CHAR)
        self.assertEqual(sorted(characterized), [-1, 1, 2])  # 3's latest attempt failed
        self.assertIsNone(cmp.pair_problem(1, 2, characterized))
        self.assertIsNone(cmp.pair_problem("1", "-1", characterized))
        self.assertIn("same", cmp.pair_problem(1, 1, characterized))
        self.assertIn("population can only be cohort B", cmp.pair_problem(-1, 1, characterized))
        self.assertEqual(cmp.pair_problem(1, 3, characterized, NAMES),
                         "Sepsis (cohort 3) is not characterized. Characterize it in Project Setup first.")
        self.assertIn("population is not characterized", cmp.pair_problem(1, -1, {1: T1}))
        self.assertEqual(cmp.pair_problem(None, 2, characterized), "Choose cohort A and cohort B.")

    def test_choices_default_to_the_population(self):
        got = cmp.cohort_choices(DEFINITIONS, CHAR)
        self.assertEqual([c["id"] for c in got["cohorts"]], [1, 2])
        self.assertEqual([c["id"] for c in got["comparators"]], [-1, 1, 2])
        self.assertEqual(got["comparators"][0]["label"], "Population")
        self.assertEqual(got["default_comparator"], -1)
        self.assertIsNone(cmp.cohort_choices(DEFINITIONS, CHAR[1:])["default_comparator"])


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def itertuples(self, index=False):
        return iter(self.rows)


class Services(unittest.TestCase):
    AUTH = {"authIdentifier": "ana", "groups": ["analysts"]}
    PATHS = {t: "R.%s" % t.upper() for t in bal.INPUT_TABLES + (bal.BALANCE_TABLE, cmp.REQUESTS_TABLE)}

    def test_rights(self):
        perms = {"owner": "olga", "permissions": [{"group": "analysts", "readDashboards": True},
                                                  {"group": "builders", "runScenarios": True},
                                                  {"user": "wes", "writeProjectContent": True}]}
        self.assertFalse(svc.can_compute(self.AUTH, perms))
        self.assertTrue(svc.can_compute({"authIdentifier": "ana", "groups": ["builders"]}, perms))
        self.assertTrue(svc.can_compute({"authIdentifier": "wes"}, perms))
        self.assertTrue(svc.can_compute({"authIdentifier": "olga"}, perms))
        self.assertFalse(svc.can_compute({}, perms))

    def comparisons(self, cached=False, fail=None, start=None):
        ex = mock.MagicMock()

        def query_to_df(query, pre_queries=None, post_queries=None):
            if pre_queries and fail:
                raise Exception(fail)
            return FakeFrame([(5 if cached else 0,)])
        ex.query_to_df.side_effect = query_to_df
        return svc.Comparisons(ex, self.PATHS, "Snowflake", start=start or (lambda task: task())), ex

    def ask(self, comparisons, a, b, allowed=True):
        perms = {"owner": "ana" if allowed else "olga", "permissions": []}
        return comparisons.request(a, b, self.AUTH, perms, DEFINITIONS, CHAR)

    def test_cached_invalid_and_forbidden_run_nothing(self):
        comparisons, ex = self.comparisons(cached=True)
        self.assertEqual(self.ask(comparisons, 1, -1),
                         {"state": "cached", "message": "Ready: select Anemia (cohort 1) against Population in the page filters."})
        comparisons, ex = self.comparisons()
        self.assertEqual(self.ask(comparisons, 1, 3)["state"], "invalid")
        self.assertEqual(self.ask(comparisons, 1, 2, allowed=False)["state"], "forbidden")
        self.assertTrue(all(not c.kwargs.get("pre_queries") for c in ex.query_to_df.call_args_list))
        self.assertEqual(comparisons.status(1, 2)["state"], "invalid")

    def test_computed_in_one_session(self):
        comparisons, ex = self.comparisons()
        self.assertEqual(self.ask(comparisons, 1, 2),
                         {"state": "done",
                          "message": "Done: select Anemia (cohort 1) against Crohn's (cohort 2) in the page filters."})
        session = ex.query_to_df.call_args
        statements = session.kwargs["pre_queries"]
        self.assertEqual([s.split()[0] for s in statements], ["CREATE", "CREATE", "INSERT", "DELETE", "INSERT"])
        self.assertRegex(statements[2], r"^INSERT INTO R.COMPARISON_REQUESTS \(request_timestamp, cohort_definition_id, "
                                        r"comparator_id, requested_by\) VALUES \('[0-9T:-]+Z', 1, 2, 'ana'\)$")
        self.assertEqual(statements[3], "DELETE FROM R.COVARIATE_BALANCE WHERE comparator_id = 2 AND "
                                        "cohort_definition_id IN (1)")
        self.assertEqual(session.kwargs["post_queries"], ["COMMIT"])
        self.assertEqual(comparisons.status("1", "2")["state"], "done")

    def test_failure_is_a_sentence(self):
        comparisons, _ = self.comparisons(fail="SQL compilation error:\n  bad")
        self.assertEqual(self.ask(comparisons, 1, 2)["message"],
                         "The comparison of Anemia (cohort 1) against Crohn's (cohort 2) failed: SQL compilation error: bad")

    def test_a_pair_being_computed_is_joined_not_started_twice(self):
        tasks = []
        comparisons, ex = self.comparisons(start=tasks.append)
        self.assertEqual(self.ask(comparisons, 1, 2)["state"], "running")
        self.assertEqual(self.ask(comparisons, 1, 2)["state"], "running")
        self.assertEqual(len(tasks), 1)
        tasks[0]()
        self.assertEqual(comparisons.status(1, 2)["state"], "done")

    def test_paths_are_required(self):
        with self.assertRaises(ValueError):
            svc.Comparisons(mock.MagicMock(), {"covariate": "c"}, "Snowflake")


class DashboardRefresh(unittest.TestCase):
    """Page 2 reads a flow-built copy; a written pair is done only once the copy is rebuilt."""
    AUTH = Services.AUTH
    PATHS = dict(Services.PATHS, **{bal.DISPLAY_TABLE: "R.COVARIATE_BALANCE_DISPLAY"})

    def comparisons(self, cached=False, shown=False, refresh_error=None, connection_type="Snowflake"):
        ex = mock.MagicMock()
        calls = []

        def query_to_df(query, pre_queries=None, post_queries=None):
            if pre_queries:
                calls.append("compute")
                return FakeFrame([(1,)])
            hit = shown if bal.DISPLAY_TABLE.upper() in query else cached
            return FakeFrame([(5 if hit else 0,)])
        ex.query_to_df.side_effect = query_to_df

        def refresh():
            calls.append("refresh")
            if refresh_error:
                raise Exception(refresh_error)
        comparisons = svc.Comparisons(ex, self.PATHS, connection_type, start=lambda task: task(), refresh=refresh)
        return comparisons, ex, calls

    def ask(self, comparisons, a, b, allowed=True):
        perms = {"owner": "ana" if allowed else "olga", "permissions": []}
        return comparisons.request(a, b, self.AUTH, perms, DEFINITIONS, CHAR)

    def test_new_pair_is_computed_then_the_dashboard_rebuilt(self):
        comparisons, _, calls = self.comparisons()
        self.assertEqual(self.ask(comparisons, 1, 2)["state"], "done")
        self.assertEqual(calls, ["compute", "refresh"])

    def test_pair_on_the_dashboard_runs_nothing(self):
        comparisons, ex, calls = self.comparisons(cached=True, shown=True)
        self.assertEqual(self.ask(comparisons, 1, -1)["state"], "cached")
        self.assertEqual(calls, [])

    def test_cached_pair_missing_from_the_dashboard_is_rebuilt_not_recomputed(self):
        comparisons, _, calls = self.comparisons(cached=True, shown=False)
        self.assertEqual(self.ask(comparisons, 1, 2),
                         {"state": "done",
                          "message": "Done: select Anemia (cohort 1) against Crohn's (cohort 2) in the page filters."})
        self.assertEqual(calls, ["refresh"])

    def test_cached_pair_missing_from_the_dashboard_needs_rights(self):
        comparisons, _, calls = self.comparisons(cached=True, shown=False)
        answer = self.ask(comparisons, 1, 2, allowed=False)
        self.assertEqual(answer["state"], "forbidden")
        self.assertIn("computed but not on the dashboard yet", answer["message"])
        self.assertEqual(calls, [])

    def test_failed_rebuild_is_a_sentence(self):
        comparisons, _, calls = self.comparisons(refresh_error="Job failed:\n  busy")
        self.assertEqual(self.ask(comparisons, 1, 2)["message"],
                         "Anemia (cohort 1) against Crohn's (cohort 2) is computed, but the dashboard could not be "
                         "updated: Job failed: busy. Request it again to retry.")
        self.assertEqual(calls, ["compute", "refresh"])

    def test_display_path_required_with_refresh(self):
        with self.assertRaises(ValueError):
            svc.Comparisons(mock.MagicMock(), Services.PATHS, "Snowflake", refresh=lambda: None)

    def test_display_query_quotes_the_lower_case_columns(self):
        self.assertEqual(bal.display_pair_query("D", 1, -1, "Snowflake"),
                         'SELECT COUNT(*) AS n FROM D WHERE "cohort_definition_id" = 1 AND "comparator_id" = -1')
        self.assertIn("`comparator_id` = 2", bal.display_pair_query("D", 1, 2, "Databricks"))
        with self.assertRaises(ValueError):
            bal.display_pair_query("D", 1, 2, "Oracle")


class Tables(unittest.TestCase):
    def test_new_tables_have_types_in_every_dialect(self):
        for ct in st.TYPES:
            self.assertIn("std_diff", st.create_table("covariate_balance", "t", ct))
            self.assertIn("requested_by", st.create_table("comparison_requests", "t", ct))
        self.assertIn("is_binary VARCHAR(255)", st.create_table("covariate_balance", "t", "Snowflake"))


if __name__ == "__main__":
    unittest.main()
