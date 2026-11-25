# Python backend of the "Compare cohorts" standard webapp (solution-revision-plan.md R3, decisions 10, 12, 13).
# DSS provides the Flask `app`. Each route calls one service in solution/compare/services.py, which
# holds the logic and its tests; this file only wires DSS and Flask to it.
import dataiku
from dataiku import SQLExecutor2
from flask import jsonify, request

from solution.compare.balance import BALANCE_TABLE, INPUT_TABLES
from solution.compare.comparison import REQUESTS_TABLE
from solution.compare.services import Comparisons, choices
from solution.recipes.sql_script_function import cohort_connection_type, get_sql_path
from solution.setup.characterization import CHARACTERIZATION_LOG_COLUMNS
from solution.setup.registration import DEFINITION_COLUMNS, read_rows
from solution.utils.variables import get_setting

_comparisons = []  # one per backend process, made on first use


def comparisons():
    if not _comparisons:
        paths = {t: get_sql_path(t) for t in list(INPUT_TABLES) + [BALANCE_TABLE, REQUESTS_TABLE]}
        executor = SQLExecutor2(connection=get_setting("main_connection"))
        _comparisons.append(Comparisons(executor, paths, cohort_connection_type()))
    return _comparisons[0]


def cohorts():
    definitions = read_rows(dataiku.Dataset("cohort_definition", ignore_flow=True), DEFINITION_COLUMNS)
    logs = read_rows(dataiku.Dataset("characterization_log", ignore_flow=True), CHARACTERIZATION_LOG_COLUMNS)
    return definitions, logs


def failure(e):
    return jsonify({"state": "failed", "message": "The comparison service failed: %s" % " ".join(str(e).split())})


@app.route("/choices")  # noqa: F821 (DSS defines app)
def get_choices():
    try:
        return jsonify(dict(choices(*cohorts()), state="ok"))
    except Exception as e:
        return failure(e)


@app.route("/request", methods=["POST"])  # noqa: F821
def post_request():
    try:
        body = request.get_json(force=True) or {}
        client = dataiku.api_client()
        auth_info = client.get_auth_info_from_browser_headers(dict(request.headers))
        permissions = client.get_default_project().get_permissions()
        definitions, logs = cohorts()
        return jsonify(comparisons().request(body.get("cohort"), body.get("comparator"), auth_info, permissions,
                                             definitions, logs))
    except Exception as e:
        return failure(e)


@app.route("/status")  # noqa: F821
def get_status():
    try:
        return jsonify(comparisons().status(request.args.get("cohort"), request.args.get("comparator")))
    except Exception as e:
        return failure(e)
