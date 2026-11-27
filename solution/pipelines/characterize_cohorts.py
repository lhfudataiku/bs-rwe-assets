"""`characterize_cohorts`: the static Python recipe behind "Characterize cohorts" (R3, step 4 part 3).

Run from the "Characterize Cohorts" section of Project Setup (decision 14), on the batch saved by
the "Characterization batch" tile in `characterization_submission`:

- the batch is checked again here, as the authority: every cohort must have a successful latest
  build, and a characterized cohort needs *Replace* (decision 15). Entries a run already
  characterized after they were saved are dropped first (`live_submission`): an open Setup page can
  write the batch just run back;
- the population (id -1) is added when it was never characterized or the data was imported since;
- one FeatureExtraction run covers all of them, in one session (`statements.run_statements`);
- `characterization_log` gets one row per cohort, SUCCESS with its entry count, or FAILED with the
  error for every cohort of a failed run; the saved batch is cleared after a success.

Inputs, declared for lineage: `cohort`, `cohort_definition`, `cohort_building_log` and the OMOP tables
the SQL reads. Outputs: `covariate`, `covariate_continuous`, `covariate_ref`, `analysis_ref`,
`characterization_log`, `covariate_balance` (the rows against the population; part 4) and
`covariate_censored` (the ids trimmed under the minimum cell count), written in-database. On Databricks the scratch tables are `rwdtmp_<project key>__ch_<name>`; any left by an
earlier crash are dropped first, and the cohort build's are never touched.
"""
import logging

import dataiku
from dataiku import SQLExecutor2

from solution.characterization.statements import RESULT_TABLES, count_query, log_statement, run_statements
from solution.pipelines.build_cohorts import clean_error, drop_tables, run, scratch_schema
from solution.recipes.sql_script_function import cohort_connection_type, get_sql_path
from solution.recipes.sql_text import characterization_scratch_prefix, is_characterization_scratch_table
from solution.setup.batch import latest_by_id
from solution.setup.characterization import (  # noqa: F401 (re-exported for the recipe and tests)
    CHARACTERIZATION_LOG_COLUMNS, IMPORT_SCENARIO, POPULATION_ID, SUBMISSION, SUCCESS, batch_ids, imported_at,
    live_submission, population_needed, selected_ids, utc_timestamp,
)
from solution.setup.registration import DEFINITION_COLUMNS, LOG_COLUMNS, read_rows
from solution.utils.variables import get_setting, set_local

logger = logging.getLogger(__name__)

OMOP_TABLES = ["person", "observation_period", "visit_occurrence", "condition_era", "drug_era", "concept",
               "concept_ancestor"]


def sweep_scratch_tables(executor, schema, project_key):
    """Drop the characterization's scratch tables left by an earlier crash. Never fails the run."""
    prefix = characterization_scratch_prefix(project_key)
    try:
        listed = executor.query_to_df("SHOW TABLES IN %s LIKE '%s*'" % (schema, prefix))
        names = [n for n in listed["tableName"] if is_characterization_scratch_table(n, project_key)]
        drop_tables(executor, ["%s.`%s`" % (schema, n) for n in names], "Databricks")
        if names:
            logger.warning("Dropped %d scratch tables left by an earlier run: %s", len(names), ", ".join(names))
    except Exception as e:
        logger.warning("Could not sweep scratch tables in %s: %s", schema, e)


def characterize(executor, connection_type, project_key, schema, cohort_ids, population, build_times,
                 population_balance_ids=None):
    """Run one characterization. Returns the log rows (SUCCESS per cohort, or FAILED for all).

    population_balance_ids: the cohorts whose balance against the population is recomputed (part 4);
    by default the run's cohorts.
    """
    tables = {t: get_sql_path(t) for t in OMOP_TABLES}
    paths = {t: get_sql_path(t) for t in list(RESULT_TABLES) + ["cohort"]}
    prefix = characterization_scratch_prefix(project_key) if schema else None
    statements, scratch, cohort_name = run_statements(connection_type, tables, paths, cohort_ids, population,
                                                      prefix, schema, population_balance_ids)
    run_timestamp = utc_timestamp()
    ids = sorted(cohort_ids) + ([POPULATION_ID] if population else [])
    try:
        df = run(executor, ["DROP TABLE IF EXISTS %s" % t for t in scratch] + statements, connection_type,
                 count_query(cohort_name))
        counts = {int(r[0]): int(r[1]) for r in df.itertuples(index=False)}
        rows = [[run_timestamp, i, build_times.get(i, ""), counts.get(i, 0), SUCCESS, ""] for i in ids]
    except Exception as e:
        logger.error("Characterization of %s failed: %s", ids, e)
        error = clean_error(e)
        rows = [[run_timestamp, i, build_times.get(i, ""), 0, "FAILED", error] for i in ids]
    finally:
        try:
            drop_tables(executor, scratch, connection_type)
        except Exception as e:
            logger.warning("Could not drop the characterization's scratch tables: %s", e)
    run(executor, log_statement(paths["characterization_log"], rows, connection_type), connection_type)
    return rows


def population_balance_ids(char_logs, cohort_ids, population):
    """The cohorts whose balance against the population the run recomputes (part 4).

    The run's cohorts; and, when the population itself is recomputed, every cohort whose latest
    characterization succeeded, so every balance uses the current population.
    """
    ids = set(cohort_ids)
    if population:
        ids |= {i for i, log in latest_by_id(char_logs).items()
                if i != POPULATION_ID and str(log.get("status") or "").upper() == SUCCESS}
    return sorted(ids)


def characterize_cohorts():
    project = dataiku.api_client().get_default_project()
    connection_type = cohort_connection_type()
    project_key = dataiku.default_project_key()
    executor = SQLExecutor2(connection=get_setting("main_connection"))
    schema = scratch_schema(connection_type)

    definitions = read_rows(dataiku.Dataset("cohort_definition", ignore_flow=True), DEFINITION_COLUMNS)
    build_logs = read_rows(dataiku.Dataset("cohort_building_log", ignore_flow=True), LOG_COLUMNS)
    char_logs = read_rows(dataiku.Dataset("characterization_log", ignore_flow=True), CHARACTERIZATION_LOG_COLUMNS)
    built = latest_by_id(build_logs)
    built_ids, characterized = batch_ids(definitions, build_logs, char_logs)

    saved = get_setting(SUBMISSION, default=[]) or []
    live = live_submission(saved, char_logs)
    if len(live) != len(saved):
        logger.info("Ignored %d entries of the saved batch already characterized since they were saved.",
                    len(saved) - len(live))
    cohort_ids = selected_ids(live, built_ids, characterized)
    population = population_needed(char_logs, imported_at(project))
    if not cohort_ids and not population:
        logger.info("Nothing to characterize: no cohort in the batch, and the population is up to date.")
        return []

    if schema:
        sweep_scratch_tables(executor, schema, project_key)
    build_times = {i: str(built[i].get("run_timestamp") or "") for i in cohort_ids}
    rows = characterize(executor, connection_type, project_key, schema, cohort_ids, population, build_times,
                        population_balance_ids(char_logs, cohort_ids, population))
    failed = [r for r in rows if r[4] != SUCCESS]
    if failed:
        raise ValueError("Characterization failed for %s (see characterization_log): %s"
                         % (", ".join(str(r[1]) for r in failed), failed[0][5]))
    if saved:
        set_local(project, SUBMISSION, [])
    return rows
