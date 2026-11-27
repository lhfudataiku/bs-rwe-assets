"""`extract_patient_covariates`: the static Python recipe behind "Extract patient covariates" (R9).

Run on request from the "Extract Patient Covariates" section of Project Setup, on the batch saved by
the "Extraction batch" tile in `extraction_submission`:

- the batch is checked again here, as the authority: every cohort must have a successful latest
  build, and an extracted cohort needs *Replace*. Entries a run already extracted after they were
  saved are dropped first (`live_extraction_submission`): an open Setup page can write the batch
  just run back;
- one FeatureExtraction run in non-aggregated mode covers all of them, in one session
  (`extraction.extraction_statements`), and writes one row per cohort entry and covariate into
  the dataset of its preset, and the new covariates into `patient_cov_ref`. Complete cohorts: no
  sampling, matching, trimming or minimum cell count (R9 decision 4);
- `patient_cov_log` gets one row per cohort: SUCCESS with its entries and rows per preset, or
  FAILED with the error for every cohort of a failed run; the saved batch is cleared after a
  success. Characterization's tables are never read or written.

Inputs, declared for lineage: `cohort`, `cohort_definition`, `cohort_building_log` and the OMOP tables
the SQL reads. Outputs: the 11 `patient_cov_*` preset datasets, `patient_cov_ref` and
`patient_cov_log`, written in-database. On Databricks the scratch tables are
`rwdtmp_<project key>__pc_<name>`; any left by an earlier crash are dropped first, and the build's
and the characterization's are never touched.
"""
import logging
import time

import dataiku
from dataiku import SQLExecutor2

from solution.characterization.extraction import (
    LOG_TABLE, OUTPUT_TABLES, PRESETS, extraction_count_query, extraction_log_statement, extraction_statements,
)
from solution.pipelines.build_cohorts import clean_error, drop_tables, run, scratch_schema
from solution.recipes.sql_script_function import cohort_connection_type, get_sql_path
from solution.recipes.sql_text import extraction_scratch_prefix, is_extraction_scratch_table
from solution.setup.batch import latest_by_id
from solution.setup.characterization import SUCCESS, utc_timestamp
from solution.setup.extraction import (  # noqa: F401 (re-exported for the recipe and tests)
    EXTRACTION_LOG_COLUMNS, EXTRACTION_SUBMISSION, extraction_batch_ids, live_extraction_submission,
    selected_extraction_ids,
)
from solution.setup.registration import DEFINITION_COLUMNS, LOG_COLUMNS, read_rows
from solution.utils.variables import get_setting, set_local

logger = logging.getLogger(__name__)

OMOP_TABLES = ["person", "observation_period", "visit_occurrence", "condition_era", "drug_era", "concept",
               "concept_ancestor"]
DATASET_ORDER = [dataset for _, _, dataset, _ in PRESETS]


def sweep_extraction_scratch_tables(executor, schema, project_key):
    """Drop the extract's scratch tables left by an earlier crash. Never fails the run."""
    prefix = extraction_scratch_prefix(project_key)
    try:
        listed = executor.query_to_df("SHOW TABLES IN %s LIKE '%s*'" % (schema, prefix))
        names = [n for n in listed["tableName"] if is_extraction_scratch_table(n, project_key)]
        drop_tables(executor, ["%s.`%s`" % (schema, n) for n in names], "Databricks")
        if names:
            logger.warning("Dropped %d scratch tables left by an earlier run: %s", len(names), ", ".join(names))
    except Exception as e:
        logger.warning("Could not sweep scratch tables in %s: %s", schema, e)


def log_row(run_timestamp, cohort_id, build_time, status, error, seconds, counts=None):
    counts = counts or {}
    return [run_timestamp, cohort_id, build_time, counts.get("entries", 0), status, error, seconds] + \
        [counts.get(dataset, 0) for dataset in DATASET_ORDER]


def extract(executor, connection_type, project_key, schema, cohort_ids, build_times):
    """Run one extract. Returns the log rows (SUCCESS per cohort, or FAILED for all)."""
    tables = {t: get_sql_path(t) for t in OMOP_TABLES}
    paths = {t: get_sql_path(t) for t in list(OUTPUT_TABLES) + ["cohort"]}
    prefix = extraction_scratch_prefix(project_key) if schema else None
    ids = sorted(cohort_ids)
    statements, scratch, cohort_name = extraction_statements(connection_type, tables, paths, ids, prefix, schema)
    run_timestamp = utc_timestamp()
    started = time.time()
    try:
        df = run(executor, ["DROP TABLE IF EXISTS %s" % t for t in scratch] + statements, connection_type,
                 extraction_count_query(cohort_name, paths, ids))
        counts = {}
        for cohort_id, what, n in df.itertuples(index=False):
            counts.setdefault(int(cohort_id), {})[str(what)] = int(n)
        seconds = int(round(time.time() - started))
        rows = [log_row(run_timestamp, i, build_times.get(i, ""), SUCCESS, "", seconds, counts.get(i)) for i in ids]
    except Exception as e:
        logger.error("Extraction of %s failed: %s", ids, e)
        error, seconds = clean_error(e), int(round(time.time() - started))
        rows = [log_row(run_timestamp, i, build_times.get(i, ""), "FAILED", error, seconds) for i in ids]
    finally:
        try:
            drop_tables(executor, scratch, connection_type)
        except Exception as e:
            logger.warning("Could not drop the extract's scratch tables: %s", e)
    run(executor, extraction_log_statement(paths[LOG_TABLE], rows, connection_type), connection_type)
    return rows


def extract_patient_covariates():
    project = dataiku.api_client().get_default_project()
    connection_type = cohort_connection_type()
    project_key = dataiku.default_project_key()
    executor = SQLExecutor2(connection=get_setting("main_connection"))
    schema = scratch_schema(connection_type)

    definitions = read_rows(dataiku.Dataset("cohort_definition", ignore_flow=True), DEFINITION_COLUMNS)
    build_logs = read_rows(dataiku.Dataset("cohort_building_log", ignore_flow=True), LOG_COLUMNS)
    extraction_logs = read_rows(dataiku.Dataset(LOG_TABLE, ignore_flow=True), EXTRACTION_LOG_COLUMNS)
    built = latest_by_id(build_logs)
    built_ids, extracted = extraction_batch_ids(definitions, build_logs, extraction_logs)

    saved = get_setting(EXTRACTION_SUBMISSION, default=[]) or []
    live = live_extraction_submission(saved, extraction_logs)
    if len(live) != len(saved):
        logger.info("Ignored %d entries of the saved batch already extracted since they were saved.",
                    len(saved) - len(live))
    cohort_ids = selected_extraction_ids(live, built_ids, extracted)
    if not cohort_ids:
        logger.info("Nothing to extract: no cohort in the batch.")
        return []

    if schema:
        sweep_extraction_scratch_tables(executor, schema, project_key)
    build_times = {i: str(built[i].get("run_timestamp") or "") for i in cohort_ids}
    rows = extract(executor, connection_type, project_key, schema, cohort_ids, build_times)
    failed = [r for r in rows if r[4] != SUCCESS]
    if failed:
        raise ValueError("Extraction failed for %s (see %s): %s"
                         % (", ".join(str(r[1]) for r in failed), LOG_TABLE, failed[0][5]))
    if saved:
        set_local(project, EXTRACTION_SUBMISSION, [])
    return rows
