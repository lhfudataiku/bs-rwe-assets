"""The SQL of one characterization run (solution-revision-plan.md, R3; step 4 part 3).

Builds, as plain statement lists, everything `characterize_cohorts` runs in one session:

1. create the result tables if they do not exist yet;
2. one scratch cohort table holding every cohort of the run, and the population when it is
   included (id -1: every person whose first observation period lasts 365 days or more, from one
   year after its start to its end; decision 5);
3. FeatureExtraction's construction script (`sql/<connection>/construction.sql`, part 1), once for
   all of them;
4. per result table, delete the run's cohorts and insert the new rows; `covariate_ref` and
   `analysis_ref` only gain the ids they do not hold yet;
5. FeatureExtraction's cleanup script.

The failure-prone work (2, 3) comes before any delete, so a run that fails there changes no
result. Snowflake and Redshift commit at the end of the session; Databricks commits per statement.

Import-free apart from the pure SQL text helpers, so everything here is tested offline.
"""
import os
import re

from solution.recipes.sql_text import render_temp_tables, split_statements, sql_literal

POPULATION_ID = -1
SQL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql")
FOLDERS = {"Snowflake": "snowflake", "Databricks": "databricks", "Redshift": "redshift"}
OMOP_TOKEN = re.compile(r"@cdm_database_schema\.(\w+)", re.IGNORECASE)  # fixed token (part 1)
COHORT_TOKEN = "@characterization_cohort"

# Result tables: FeatureExtraction's aggregated format (decision 2), plus the run log.
INT, BIG, NUM, TEXT, SHORT = "int", "bigint", "float", "text", "short"
RESULT_TABLES = {
    "covariate": [("cohort_definition_id", BIG), ("covariate_id", BIG), ("sum_value", BIG),
                  ("average_value", NUM)],
    "covariate_continuous": [("cohort_definition_id", BIG), ("covariate_id", BIG), ("count_value", BIG),
                             ("min_value", NUM), ("max_value", NUM), ("average_value", NUM),
                             ("standard_deviation", NUM), ("median_value", NUM), ("p10_value", NUM),
                             ("p25_value", NUM), ("p75_value", NUM), ("p90_value", NUM)],
    "covariate_ref": [("covariate_id", BIG), ("covariate_name", TEXT), ("analysis_id", INT), ("concept_id", INT),
                      ("value_as_concept_id", INT), ("collisions", INT)],
    "analysis_ref": [("analysis_id", BIG), ("analysis_name", TEXT), ("domain_id", SHORT), ("start_day", INT),
                     ("end_day", INT), ("is_binary", SHORT), ("missing_means_zero", SHORT)],
    "characterization_log": [("run_timestamp", SHORT), ("cohort_definition_id", BIG), ("build_timestamp", SHORT),
                             ("cohort_count", BIG), ("status", SHORT), ("error", TEXT)],
}
TYPES = {
    "Snowflake": {INT: "INTEGER", BIG: "BIGINT", NUM: "FLOAT", TEXT: "VARCHAR", SHORT: "VARCHAR(255)"},
    "Redshift": {INT: "INTEGER", BIG: "BIGINT", NUM: "FLOAT8", TEXT: "VARCHAR(65535)", SHORT: "VARCHAR(255)"},
    "Databricks": {INT: "INT", BIG: "BIGINT", NUM: "DOUBLE", TEXT: "STRING", SHORT: "STRING"},
}
# FeatureExtraction query (part 1 file) -> result table; the ref tables are keyed by their first column.
QUERIES = [("query_covariates.sql", "covariate"), ("query_covariates_continuous.sql", "covariate_continuous"),
           ("query_covariate_ref.sql", "covariate_ref"), ("query_analysis_ref.sql", "analysis_ref")]
REFERENCE_TABLES = ("covariate_ref", "analysis_ref")


def read_sql(connection_type, name):
    if connection_type not in FOLDERS:
        raise ValueError("No characterization SQL for a %s connection" % (connection_type or "unknown"))
    with open(os.path.join(SQL_DIR, FOLDERS[connection_type], name), encoding="utf-8") as fh:
        return fh.read()


def create_table(table, path, connection_type):
    columns = ",\n  ".join("%s %s" % (name, TYPES[connection_type][kind]) for name, kind in RESULT_TABLES[table])
    return "CREATE TABLE IF NOT EXISTS %s (\n  %s)" % (path, columns)


def scratch_cohort_name(connection_type, scratch_prefix=None, scratch_schema=None):
    """The run's cohort table: a session temp table, or a Delta scratch table on Databricks (R6)."""
    if connection_type == "Databricks":
        return "%s.`%scohort`" % (scratch_schema, scratch_prefix)
    return "#rwdchar_cohort" if connection_type == "Redshift" else "rwdchar_cohort"


def _ids(ids):
    return ", ".join(str(int(i)) for i in ids)


def cohort_table_statements(connection_type, name, cohort_table, observation_period, cohort_ids, population):
    """Create the run's cohort table from `cohort` (the chosen ids) and, when asked, the population."""
    parts = []
    if cohort_ids:
        parts.append("SELECT cohort_definition_id, subject_id, cohort_start_date, cohort_end_date\n"
                     "FROM %s\nWHERE cohort_definition_id IN (%s)" % (cohort_table, _ids(cohort_ids)))
    if population:
        if connection_type == "Databricks":
            start, length = "date_add(start_date, 365)", "datediff(end_date, start_date)"
        else:
            start, length = "DATEADD(day, 365, start_date)", "DATEDIFF(day, start_date, end_date)"
        parts.append(
            "SELECT %d AS cohort_definition_id, person_id AS subject_id, %s AS cohort_start_date,\n"
            "  end_date AS cohort_end_date\n"
            "FROM (SELECT person_id, observation_period_start_date AS start_date,\n"
            "        observation_period_end_date AS end_date,\n"
            "        ROW_NUMBER() OVER (PARTITION BY person_id ORDER BY observation_period_start_date) AS period_number\n"
            "      FROM %s) first_period\n"
            "WHERE period_number = 1 AND %s >= 365" % (POPULATION_ID, start, observation_period, length))
    if not parts:
        raise ValueError("A characterization run needs at least one cohort or the population")
    select = "\nUNION ALL\n".join(parts)
    create = {"Snowflake": "CREATE TEMP TABLE %s AS\n", "Redshift": "CREATE TABLE %s AS\n",
              "Databricks": "CREATE TABLE %s USING DELTA AS\n"}[connection_type] % name
    return ["DROP TABLE IF EXISTS %s" % name, create + select]


def fill(sql, tables, cohort_name):
    """Replace the part 1 placeholders: OMOP tokens by resolved names, the cohort token by the run's table.

    tables: {OMOP table: resolved SQL name}. A token naming a table not in `tables` raises, so a run
    never sends a placeholder to the database.
    """
    def table(match):
        name = match.group(1).lower()
        if name not in tables:
            raise ValueError("The characterization SQL reads %s, which this project has not resolved" % name)
        return tables[name]
    return OMOP_TOKEN.sub(table, sql).replace(COHORT_TOKEN, cohort_name)


def _strip_header(sql):
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--")).strip()


def result_statements(connection_type, paths, cohort_name, ids, scratch_prefix=None, scratch_schema=None):
    """Delete the run's ids from the result tables, then insert the new rows."""
    statements = ["DELETE FROM %s WHERE cohort_definition_id IN (%s)" % (paths[t], _ids(ids))
                  for t in ("covariate", "covariate_continuous")]
    for name, table in QUERIES:
        query = fill(read_sql(connection_type, name), {}, cohort_name)
        query, _ = render_temp_tables(query, connection_type, scratch_prefix, scratch_schema)
        (query,) = split_statements(_strip_header(query))
        columns = [c for c, _ in RESULT_TABLES[table]]
        if table in REFERENCE_TABLES:
            key = columns[0]
            query = ("SELECT %s FROM (\n%s\n) new_rows\nWHERE %s NOT IN (SELECT %s FROM %s)"
                     % (", ".join(columns), query, key, key, paths[table]))
        statements.append("INSERT INTO %s (%s)\n%s" % (paths[table], ", ".join(columns), query))
    return statements


def run_statements(connection_type, tables, paths, cohort_ids, population, scratch_prefix=None, scratch_schema=None):
    """Every statement of one run, in order, and the Databricks scratch tables it uses.

    tables: {OMOP table: resolved name}, at least `observation_period` and what the SQL reads;
    paths: {result table and "cohort": resolved name}. Returns (statements, scratch tables, the
    run's cohort table name). The caller reads the entries per cohort from the cohort table, then
    drops the scratch tables.
    """
    if connection_type == "Databricks" and not (scratch_prefix and scratch_schema):
        raise ValueError("Databricks needs a scratch prefix and schema")
    cohort_name = scratch_cohort_name(connection_type, scratch_prefix, scratch_schema)
    ids = sorted(set(int(i) for i in cohort_ids)) + ([POPULATION_ID] if population else [])
    statements = [create_table(t, paths[t], connection_type) for t in RESULT_TABLES]
    statements += cohort_table_statements(connection_type, cohort_name, paths["cohort"],
                                          tables["observation_period"], sorted(set(cohort_ids)), population)
    construction, scratch = render_temp_tables(fill(read_sql(connection_type, "construction.sql"), tables, cohort_name),
                                               connection_type, scratch_prefix, scratch_schema)
    statements += split_statements(construction)
    statements += result_statements(connection_type, paths, cohort_name, ids, scratch_prefix, scratch_schema)
    cleanup, _ = render_temp_tables(read_sql(connection_type, "cleanup.sql"), connection_type,
                                    scratch_prefix, scratch_schema)
    statements += split_statements(cleanup)
    if connection_type == "Databricks":
        scratch = scratch + [cohort_name]
    return statements, scratch, cohort_name


def count_query(cohort_name):
    """Entries per cohort in the run's cohort table: what FeatureExtraction counted as denominators."""
    return ("SELECT cohort_definition_id, COUNT(*) AS cohort_count FROM %s GROUP BY cohort_definition_id"
            % cohort_name)


def log_statement(path, rows, connection_type):
    """Append rows [run_timestamp, cohort id, build_timestamp, count, status, error] to the log."""
    values = ",\n".join("(" + ", ".join(sql_literal(v, connection_type) for v in row) + ")" for row in rows)
    columns = ", ".join(c for c, _ in RESULT_TABLES["characterization_log"])
    return ["INSERT INTO %s (%s)\nVALUES\n%s" % (path, columns, values)]
