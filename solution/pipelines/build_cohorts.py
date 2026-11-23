"""`build_cohorts`: the static Python recipe that writes the cohorts of the last batch (R5, R6).

Inputs: the mapped scripts folder, `uploaded_cohort_definition` (the batch), and the imported OMOP
tables, declared for lineage. Outputs, both in append mode: `cohort`, written in-database by the
scripts, and `cohort_building_log`, one row per cohort and run.

Each cohort's mapped script is split into statements and run in one session
(`SQLExecutor2.query_to_df(count, pre_queries=statements, post_queries=commit)`), so Snowflake and
Redshift session temporary tables live until the count is read. On Databricks the Atlas scratch tables
are Delta tables named `rwdtmp_<project key>__c<id>_<name>` in the scratch schema; they are dropped
before and after each cohort, and any left by an earlier crash at the start of the build. A failed
cohort is logged and the build moves on; the recipe fails at the end if any cohort failed.
"""
import datetime
import logging

import dataiku
from dataiku import SQLExecutor2

from solution.recipes.sql_script_function import (
    PROJECT, cohort_connection_type, get_script_by_connection_type, get_sql_path, replace_sql_script_variables,
    validate_cdm_tables,
)
from solution.recipes.sql_text import (
    SESSION_COMMIT, is_project_scratch_table, quote_databricks_name, render_temp_tables, scratch_table_prefix,
    project_scratch_prefix, split_statements, sql_literal, table_qualifier,
)
from solution.utils.variables import get_setting

logger = logging.getLogger(__name__)

MAPPED_SCRIPTS_FOLDER = "lMM00YKr"
BATCH_DATASET = "uploaded_cohort_definition"
MAX_ERROR_LENGTH = 1000


def scratch_schema(connection_type):
    """Databricks only: `temp_schema` if set, else the schema that holds the `cohort` table."""
    if connection_type != "Databricks":
        return None
    configured = get_setting("temp_schema")
    return quote_databricks_name(configured) if configured else table_qualifier(get_sql_path("cohort"))


def run(executor, statements, connection_type, query="SELECT 1"):
    """Run statements in one session, then the query, then the dialect's commit."""
    return executor.query_to_df(query, pre_queries=statements, post_queries=SESSION_COMMIT[connection_type])


def drop_tables(executor, tables, connection_type):
    if tables:
        run(executor, ["DROP TABLE IF EXISTS %s" % t for t in tables], connection_type)


def sweep_scratch_tables(executor, schema, project_key):
    """Drop this project's scratch tables left by an earlier crash. Never fails the build."""
    try:
        listed = executor.query_to_df("SHOW TABLES IN %s LIKE '%s*'" % (schema, project_scratch_prefix(project_key)))
        names = [n for n in listed["tableName"] if is_project_scratch_table(n, project_key)]
        drop_tables(executor, ["%s.`%s`" % (schema, n) for n in names], "Databricks")
        if names:
            logger.warning("Dropped %d scratch tables left by an earlier run: %s", len(names), ", ".join(names))
    except Exception as e:  # the per-cohort drops still protect this run
        logger.warning("Could not sweep scratch tables in %s: %s", schema, e)


def cohort_count(executor, cohort_table, cohort_id):
    df = executor.query_to_df("SELECT COUNT(subject_id) AS cohort_count FROM %s WHERE cohort_definition_id = %d"
                              % (cohort_table, int(cohort_id)))
    return int(df.iloc[0, 0])


def build_one(executor, cohort, script, connection_type, project_key, schema, cohort_table):
    """Run one cohort's script. Returns (status, count, error)."""
    prefix = scratch_table_prefix(project_key, cohort["id"]) if schema else None
    rendered, scratch = render_temp_tables(script, connection_type, prefix, schema)
    statements = ["DROP TABLE IF EXISTS %s" % t for t in scratch] + split_statements(rendered)
    count_query = ("SELECT COUNT(subject_id) AS cohort_count FROM %s WHERE cohort_definition_id = %d"
                   % (cohort_table, int(cohort["id"])))
    try:
        df = run(executor, statements, connection_type, count_query)
        return "SUCCESS", int(df.iloc[0, 0]), ""
    except Exception as e:
        logger.error("Cohort %s (%s) failed: %s", cohort["id"], cohort["name"], e)
        error = " ".join(str(e).split())
        try:  # what the table holds now: the previous rows, or none (Databricks commits per statement)
            count = cohort_count(executor, cohort_table, cohort["id"])
        except Exception:
            count = 0
        return "FAILED", count, error[:MAX_ERROR_LENGTH]
    finally:
        try:
            drop_tables(executor, scratch, connection_type)
        except Exception as e:
            logger.warning("Could not drop scratch tables of cohort %s: %s", cohort["id"], e)


def read_batch():
    """Rows of `uploaded_cohort_definition`: id, name, description, input tables, script file."""
    batch = []
    for row in dataiku.Dataset(BATCH_DATASET, ignore_flow=True).iter_tuples():
        batch.append({"id": int(row[0]), "name": row[1], "tables": [t for t in (row[3] or "").split("|") if t],
                      "script_file": row[4]})
    return batch


def log_statements(rows, connection_type):
    values = ",\n".join("(" + ", ".join(sql_literal(v, connection_type) for v in row) + ")" for row in rows)
    script = replace_sql_script_variables(get_script_by_connection_type("cohort_log_script"), {
        "@cohort_building_log": get_sql_path("cohort_building_log"), "@cohort_log": values})
    return split_statements(script)


def build_cohorts():
    main_connection = get_setting("main_connection")
    connection_type = cohort_connection_type()
    project_key = dataiku.default_project_key()
    executor = SQLExecutor2(connection=main_connection)
    schema = scratch_schema(connection_type)
    cohort_table = get_sql_path("cohort")
    folder = dataiku.Folder(MAPPED_SCRIPTS_FOLDER, ignore_flow=True)
    run_timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    if schema:
        sweep_scratch_tables(executor, schema, project_key)

    log, failures = [], []
    for cohort in read_batch():
        logger.info("Building cohort %s (%s)", cohort["id"], cohort["name"])
        try:
            validate_cdm_tables(cohort["tables"], PROJECT, cohort)
            with folder.get_download_stream("cohort_%d" % cohort["id"]) as f:
                script = f.read().decode("utf-8")
        except Exception as e:
            status, count, error = "FAILED", 0, " ".join(str(e).split())[:MAX_ERROR_LENGTH]
        else:
            status, count, error = build_one(executor, cohort, script, connection_type, project_key, schema,
                                             cohort_table)
        log.append([run_timestamp, cohort["id"], cohort["name"], count, status, error, cohort["script_file"]])
        if status != "SUCCESS":
            failures.append("Cohort %s (%s): %s" % (cohort["id"], cohort["name"], error))
        logger.info("Cohort %s: %s, %d subjects", cohort["id"], status, count)

    if log:
        run(executor, log_statements(log, connection_type), connection_type)
    if failures:
        raise ValueError("Cohort building failed for %d of %d cohorts (see cohort_building_log):\n%s"
                         % (len(failures), len(log), "\n".join(failures)))
    return log
