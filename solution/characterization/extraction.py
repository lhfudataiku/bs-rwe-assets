"""The SQL of one patient-level extract (solution-revision-plan.md, R9).

Builds, as plain statement lists, everything `extract_patient_covariates` runs in one session:

1. create the output tables if they do not exist yet: one per preset (R9 decision 7),
   `patient_cov_ref` and `patient_cov_log`;
2. one scratch cohort table holding every entry of the run's cohorts, numbered by `row_id`
   (FeatureExtraction's non-aggregated mode writes one row per `row_id`);
3. FeatureExtraction's person-mode construction (`sql/<connection>/person/construction.sql`), once
   for all of them;
4. per preset, delete the run's cohorts and insert its rows from that preset's scratch table,
   joined back to the entry (cohort, subject, start date); complete cohorts, no minimum cell count
   (decision 4);
5. `patient_cov_ref` gains the ids it does not hold yet, with the dataset that holds each;
6. FeatureExtraction's cleanup script.

Everything that reads the data (2, 3) runs before the first delete, so a run that fails there
changes no output. Nothing here reads or writes the characterization's tables.

Import-free apart from the pure SQL text helpers and `statements`, so it is tested offline.
"""
from solution.characterization.statements import _ids, _strip_header, fill, read_sql
from solution.recipes.sql_text import render_temp_tables, split_statements, sql_literal

PERSON_FOLDER = "person"
EXTRACTION_TOKEN = "@extraction_cohort"
SESSION_ID = "rwdfeatx"  # tools/render_feature_extraction.py SESSION_ID

# Preset -> (analysis id, dataset, kind), R9 "Outputs". The scratch table of each analysis is
# recorded by the renderer (MANIFEST.json, modes.person.scratch_tables), and tests check the two agree.
PRESETS = [
    ("DemographicsGender", 1, "patient_cov_demographics_gender", "binary"),
    ("DemographicsAge", 2, "patient_cov_demographics_age", "continuous"),
    ("DemographicsAgeGroup", 3, "patient_cov_demographics_age_group", "binary"),
    ("DemographicsRace", 4, "patient_cov_demographics_race", "binary"),
    ("DemographicsPriorObservationTime", 8, "patient_cov_demographics_prior_observation_time", "continuous"),
    ("DemographicsPostObservationTime", 9, "patient_cov_demographics_post_observation_time", "continuous"),
    ("DemographicsTimeInCohort", 10, "patient_cov_demographics_time_in_cohort", "continuous"),
    ("ConditionGroupEraLongTerm", 210, "patient_cov_condition_group_era_long_term", "binary"),
    ("DrugGroupEraLongTerm", 410, "patient_cov_drug_group_era_long_term", "binary"),
    ("CharlsonIndex", 901, "patient_cov_charlson_index", "continuous"),
    ("VisitConceptCountLongTerm", 923, "patient_cov_visit_concept_count_long_term", "continuous"),
]
SCRATCH_TABLES = {"cov_1": 210, "cov_2": 10, "cov_3": 1, "cov_4": 4, "cov_5": 9, "cov_6": 923, "cov_7": 901,
                  "cov_8": 3, "cov_9": 2, "cov_10": 8, "cov_11": 410}
DATASETS = {analysis_id: dataset for _, analysis_id, dataset, _ in PRESETS}
REF_TABLE, LOG_TABLE = "patient_cov_ref", "patient_cov_log"

DATE, BIG, INT, NUM, TEXT, SHORT = "date", "bigint", "int", "float", "text", "short"
TYPES = {
    "Snowflake": {DATE: "DATE", INT: "INTEGER", BIG: "BIGINT", NUM: "FLOAT", TEXT: "VARCHAR", SHORT: "VARCHAR(255)"},
    "Redshift": {DATE: "DATE", INT: "INTEGER", BIG: "BIGINT", NUM: "FLOAT8", TEXT: "VARCHAR(65535)",
                 SHORT: "VARCHAR(255)"},
    "Databricks": {DATE: "DATE", INT: "INT", BIG: "BIGINT", NUM: "DOUBLE", TEXT: "STRING", SHORT: "STRING"},
}
PRESET_COLUMNS = [("cohort_definition_id", BIG), ("subject_id", BIG), ("cohort_start_date", DATE),
                  ("covariate_id", BIG), ("covariate_value", NUM)]
REF_COLUMNS = [("covariate_id", BIG), ("covariate_name", TEXT), ("concept_id", BIG), ("analysis_id", INT),
               ("analysis_name", SHORT), ("domain_id", SHORT), ("start_day", INT), ("end_day", INT),
               ("is_binary", SHORT), ("dataset", SHORT)]
# One row per cohort and run: when, which build, entries, outcome, time, and rows written per preset.
LOG_COLUMNS = [("run_timestamp", SHORT), ("cohort_definition_id", BIG), ("build_timestamp", SHORT),
               ("entry_count", BIG), ("status", SHORT), ("error", TEXT), ("seconds", BIG)] + \
              [("rows_" + dataset[len("patient_cov_"):], BIG) for _, _, dataset, _ in PRESETS]
OUTPUT_TABLES = dict([(dataset, PRESET_COLUMNS) for _, _, dataset, _ in PRESETS],
                     **{REF_TABLE: REF_COLUMNS, LOG_TABLE: LOG_COLUMNS})


def create_output_table(table, path, connection_type):
    columns = ",\n  ".join("%s %s" % (name, TYPES[connection_type][kind]) for name, kind in OUTPUT_TABLES[table])
    return "CREATE TABLE IF NOT EXISTS %s (\n  %s)" % (path, columns)


def extraction_cohort_name(connection_type, scratch_prefix=None, scratch_schema=None):
    """The run's entries: a session temp table, or a Delta scratch table on Databricks (R6)."""
    if connection_type == "Databricks":
        return "%s.`%scohort`" % (scratch_schema, scratch_prefix)
    return "#rwdpcov_cohort" if connection_type == "Redshift" else "rwdpcov_cohort"


def scratch_table_name(connection_type, bare, scratch_prefix=None, scratch_schema=None):
    """The resolved name of a person-mode scratch table (`cov_N`), as the construction creates it:
    `#cov_N` on Redshift, `rwdfeatxcov_N` on Snowflake, a prefixed Delta table on Databricks."""
    if connection_type == "Redshift":
        return "#" + bare
    if connection_type == "Databricks":
        rendered, _ = render_temp_tables("@temp_database_schema.%s%s" % (SESSION_ID, bare), connection_type,
                                         scratch_prefix, scratch_schema)
        return rendered
    return SESSION_ID + bare


def extraction_cohort_statements(connection_type, name, cohort_table, cohort_ids):
    """Create the run's entry table from `cohort`, one `row_id` per entry."""
    if not cohort_ids:
        raise ValueError("An extraction run needs at least one cohort")
    create = {"Snowflake": "CREATE TEMP TABLE %s AS\n", "Redshift": "CREATE TABLE %s AS\n",
              "Databricks": "CREATE TABLE %s USING DELTA AS\n"}[connection_type] % name
    select = ("SELECT CAST(ROW_NUMBER() OVER (ORDER BY cohort_definition_id, subject_id, cohort_start_date,\n"
              "    cohort_end_date) AS BIGINT) AS row_id,\n"
              "  cohort_definition_id, subject_id, cohort_start_date, cohort_end_date\n"
              "FROM %s\nWHERE cohort_definition_id IN (%s)" % (cohort_table, _ids(cohort_ids)))
    return ["DROP TABLE IF EXISTS %s" % name, create + select]


def _query(connection_type, name, cohort_name, scratch_prefix, scratch_schema):
    query = fill(read_sql(connection_type, "%s/%s" % (PERSON_FOLDER, name)), {}, cohort_name, EXTRACTION_TOKEN)
    query, _ = render_temp_tables(query, connection_type, scratch_prefix, scratch_schema)
    (query,) = split_statements(_strip_header(query))
    return query


def output_statements(connection_type, paths, cohort_name, ids, scratch_prefix=None, scratch_schema=None):
    """Replace the run's cohorts in every preset dataset, then add new ids to `patient_cov_ref`."""
    columns = ", ".join(c for c, _ in PRESET_COLUMNS)
    statements = []
    for bare, analysis_id in SCRATCH_TABLES.items():
        path = paths[DATASETS[analysis_id]]
        statements.append("DELETE FROM %s WHERE cohort_definition_id IN (%s)" % (path, _ids(ids)))
        statements.append(
            "INSERT INTO %s (%s)\n"
            "SELECT entry.cohort_definition_id, entry.subject_id, entry.cohort_start_date, f.covariate_id,\n"
            "  f.covariate_value\n"
            "FROM %s f\nINNER JOIN %s entry ON f.row_id = entry.row_id"
            % (path, columns, scratch_table_name(connection_type, bare, scratch_prefix, scratch_schema), cohort_name))
    covariates = _query(connection_type, "query_covariate_ref.sql", cohort_name, scratch_prefix, scratch_schema)
    analyses = _query(connection_type, "query_analysis_ref.sql", cohort_name, scratch_prefix, scratch_schema)
    dataset = "CASE a.analysis_id %s END" % " ".join(
        "WHEN %d THEN %s" % (analysis_id, sql_literal(DATASETS[analysis_id], connection_type))
        for _, analysis_id, _, _ in PRESETS)
    statements.append(
        "INSERT INTO %s (%s)\n"
        "SELECT c.covariate_id, c.covariate_name, c.concept_id, c.analysis_id, a.analysis_name, a.domain_id,\n"
        "  a.start_day, a.end_day, a.is_binary, %s\n"
        "FROM (\n%s\n) c\nINNER JOIN (\n%s\n) a ON c.analysis_id = a.analysis_id\n"
        "WHERE c.covariate_id NOT IN (SELECT covariate_id FROM %s)"
        % (paths[REF_TABLE], ", ".join(c for c, _ in REF_COLUMNS), dataset, covariates, analyses, paths[REF_TABLE]))
    return statements


def extraction_statements(connection_type, tables, paths, cohort_ids, scratch_prefix=None, scratch_schema=None):
    """Every statement of one extract, in order, and the Databricks scratch tables it uses.

    tables: {OMOP table: resolved name}; paths: {output table and "cohort": resolved name}.
    Returns (statements, scratch tables, the run's entry table name). The caller reads the counts
    with `extraction_count_query`, then drops the scratch tables.
    """
    if connection_type == "Databricks" and not (scratch_prefix and scratch_schema):
        raise ValueError("Databricks needs a scratch prefix and schema")
    ids = sorted(set(int(i) for i in cohort_ids))
    cohort_name = extraction_cohort_name(connection_type, scratch_prefix, scratch_schema)
    statements = [create_output_table(t, paths[t], connection_type) for t in OUTPUT_TABLES]
    statements += extraction_cohort_statements(connection_type, cohort_name, paths["cohort"], ids)
    construction = fill(read_sql(connection_type, "%s/construction.sql" % PERSON_FOLDER), tables, cohort_name,
                        EXTRACTION_TOKEN)
    construction, scratch = render_temp_tables(construction, connection_type, scratch_prefix, scratch_schema)
    statements += split_statements(construction)
    statements += output_statements(connection_type, paths, cohort_name, ids, scratch_prefix, scratch_schema)
    cleanup, _ = render_temp_tables(read_sql(connection_type, "%s/cleanup.sql" % PERSON_FOLDER), connection_type,
                                    scratch_prefix, scratch_schema)
    statements += split_statements(cleanup)
    if connection_type == "Databricks":
        scratch = scratch + [cohort_name]
    return statements, scratch, cohort_name


def extraction_count_query(cohort_name, paths, ids):
    """(cohort id, what, count) rows: entries per cohort ("entries"), and rows per preset dataset."""
    parts = ["SELECT cohort_definition_id, 'entries' AS what, COUNT(*) AS n FROM %s GROUP BY cohort_definition_id"
             % cohort_name]
    for _, _, dataset, _ in PRESETS:
        parts.append("SELECT cohort_definition_id, '%s' AS what, COUNT(*) AS n FROM %s\n"
                     "WHERE cohort_definition_id IN (%s) GROUP BY cohort_definition_id"
                     % (dataset, paths[dataset], _ids(ids)))
    return "\nUNION ALL\n".join(parts)


def extraction_log_statement(path, rows, connection_type):
    """Append log rows, in LOG_COLUMNS order, to `patient_cov_log`."""
    values = ",\n".join("(" + ", ".join(sql_literal(v, connection_type) for v in row) + ")" for row in rows)
    return ["INSERT INTO %s (%s)\nVALUES\n%s" % (path, ", ".join(c for c, _ in LOG_COLUMNS), values)]
