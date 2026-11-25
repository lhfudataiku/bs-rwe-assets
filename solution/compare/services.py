"""The "Compare cohorts" webapp's services (solution-revision-plan.md, R3 decisions 10, 12, 13).

A requested pair is computed by the webapp backend itself, in the database, with no scenario
(decision 10 as revised, 2026-11-25): the arithmetic takes about a second, where a scenario adds
about a minute of DSS job overhead.

The backend stays thin: each route calls one method here, so the v2.0 Cohort Workbench can reuse
them. DSS handles are passed in, so the tests pass stand-ins.

- `choices`: the characterized cohorts for A, and the population plus those cohorts for B (default
  the population, decision 13).
- `Comparisons.request`: checks the pair; a pair already in `covariate_balance` is answered at once;
  otherwise it checks the viewer's rights on the project, then computes the pair in the background
  (one session: record the request in `comparison_requests`, delete and insert the pair).
- `Comparisons.status`: the state of that computation, as a sentence for the tile.

The backend is one process serving every viewer, so one lock lets a pair be computed once at a
time: a second request for a pair being computed joins it. Databricks commits per statement, and
two concurrent delete-and-insert runs of one pair would otherwise double its rows.

States: `invalid`, `forbidden`, `cached`, `running`, `done`, `failed`. Each answer carries a
`message` sentence the tile shows as it is.
"""
import datetime
import threading

from solution.characterization.statements import create_table
from solution.compare.balance import BALANCE_TABLE, INPUT_TABLES, pair_cached_query, write_balance_statements
from solution.compare.comparison import (
    REQUEST_KINDS, REQUESTS_TABLE, comparable, cohort_choices, label, pair_problem,
)
from solution.recipes.sql_text import SESSION_COMMIT, sql_literal
from solution.setup.batch import as_int

# Project permissions that allow writing to the project's tables; `admin` implies them.
WRITE_PERMISSIONS = ("admin", "writeProjectContent", "runScenarios")
MAX_ERROR_LENGTH = 500


def utc_timestamp(moment=None):
    return (moment or datetime.datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


def can_compute(auth_info, permissions):
    """Whether the viewer may add a comparison to the project.

    auth_info: `get_auth_info_from_browser_headers` ({"authIdentifier", "groups"});
    permissions: `project.get_permissions()` ({"owner", "permissions": [{"user" or "group", flags}]}).
    The backend writes with its own identity, so it checks the viewer's rights first: the same as
    running a scenario (`runScenarios`, or more).
    """
    login = (auth_info or {}).get("authIdentifier")
    groups = set((auth_info or {}).get("groups") or [])
    if not login:
        return False
    if (permissions or {}).get("owner") == login:
        return True
    for entry in (permissions or {}).get("permissions") or []:
        if entry.get("user") == login or (entry.get("group") and entry.get("group") in groups):
            if any(entry.get(p) for p in WRITE_PERMISSIONS):
                return True
    return False


def choices(definitions, characterization_logs):
    return cohort_choices(definitions, characterization_logs)


def _names(definitions):
    return {as_int(d.get("id")): d.get("name") or "" for d in definitions}


def pair_text(a, b, names):
    return "%s against %s" % (label(a, names), label(b, names))


def is_cached(executor, balance_path, a, b):
    try:
        df = executor.query_to_df(pair_cached_query(balance_path, a, b))
        return int(next(iter(df.itertuples(index=False)))[0]) > 0
    except Exception:
        return False  # the table does not exist yet: nothing is cached


def compute_statements(paths, connection_type, a, b, login, moment=None):
    """One session: record the request, then delete and insert the pair in `covariate_balance`.

    paths: the four aggregate tables, `covariate_balance` and `comparison_requests`.
    """
    row = [utc_timestamp(moment), int(a), int(b), login or ""]
    columns = ", ".join(c for c, _ in REQUEST_KINDS)
    values = ", ".join(sql_literal(v, connection_type) for v in row)
    return ([create_table(REQUESTS_TABLE, paths[REQUESTS_TABLE], connection_type),
             create_table(BALANCE_TABLE, paths[BALANCE_TABLE], connection_type),
             "INSERT INTO %s (%s) VALUES (%s)" % (paths[REQUESTS_TABLE], columns, values)]
            + write_balance_statements(paths, [a], b))


def _clean(error):
    return " ".join(str(error).split())[:MAX_ERROR_LENGTH]


def _in_background(task):
    threading.Thread(target=task, daemon=True).start()


class Comparisons(object):
    """The backend's comparisons: one instance per webapp backend process.

    executor: a `SQLExecutor2` on the main connection; paths: {table: resolved name} for
    `INPUT_TABLES`, `covariate_balance` and `comparison_requests`; start: how a computation is run
    (a background thread; the tests run it at once).
    """

    def __init__(self, executor, paths, connection_type, start=_in_background):
        missing = [t for t in list(INPUT_TABLES) + [BALANCE_TABLE, REQUESTS_TABLE] if t not in paths]
        if missing:
            raise ValueError("No resolved name for %s" % ", ".join(missing))
        self.executor, self.paths, self.connection_type, self.start = executor, paths, connection_type, start
        self.lock = threading.Lock()
        self.jobs = {}  # (a, b) -> {"state", "message"}

    def request(self, cohort_a, cohort_b, auth_info, permissions, definitions, characterization_logs):
        names = _names(definitions)
        a, b = as_int(cohort_a), as_int(cohort_b)
        problem = pair_problem(a, b, comparable(characterization_logs), names)
        if problem:
            return {"state": "invalid", "message": problem}
        text = pair_text(a, b, names)
        with self.lock:
            job = self.jobs.get((a, b))
            if job and job["state"] == "running":
                return dict(job)
        if is_cached(self.executor, self.paths[BALANCE_TABLE], a, b):
            return {"state": "cached", "message": "Ready: select %s in the page filter." % text}
        if not can_compute(auth_info, permissions):
            return {"state": "forbidden",
                    "message": "%s is not computed yet, and you are not allowed to change this project. "
                               "Ask a project contributor to request it." % text}
        with self.lock:
            job = self.jobs.get((a, b))
            if job and job["state"] == "running":
                return dict(job)
            self.jobs[(a, b)] = {"state": "running", "message": "Computing %s." % text}
        login = (auth_info or {}).get("authIdentifier")
        self.start(lambda: self._compute(a, b, text, login))
        return self.status(a, b)

    def _compute(self, a, b, text, login):
        try:
            self.executor.query_to_df("SELECT 1", pre_queries=compute_statements(
                self.paths, self.connection_type, a, b, login),
                post_queries=SESSION_COMMIT[self.connection_type])
            job = {"state": "done", "message": "Done: select %s in the page filter." % text}
        except Exception as e:
            job = {"state": "failed", "message": "The comparison of %s failed: %s" % (text, _clean(e))}
        with self.lock:
            self.jobs[(a, b)] = job

    def status(self, cohort_a, cohort_b):
        a, b = as_int(cohort_a), as_int(cohort_b)
        with self.lock:
            job = self.jobs.get((a, b))
        if job is None:
            return {"state": "invalid", "message": "No comparison of these cohorts was requested here. Request it."}
        return dict(job)
