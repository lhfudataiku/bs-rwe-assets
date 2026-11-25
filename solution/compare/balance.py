"""Standardized differences over stored aggregates (solution-revision-plan.md, R3 decisions 3, 8-10).

A cohort's covariates are stored once, in FeatureExtraction's aggregated format (`covariate`,
`covariate_continuous`). The balance between a cohort and a comparator, the population (id -1) or
another cohort, is arithmetic on those rows: one SQL statement, which never reads person-level data.

- binary: `(p1 - p2) / sqrt((p1(1 - p1) + p2(1 - p2)) / 2)`, with p the stored `average_value`;
- continuous: `(m1 - m2) / sqrt((s1^2 + s2^2) / 2)`, from `average_value` and `standard_deviation`.

A covariate present on one side only:

- binary: FeatureExtraction stores no row for a covariate nobody has, so the missing side is 0;
- continuous: 0 (mean and standard deviation) when its analysis says `missing_means_zero = 'Y'`;
  otherwise the missing side stays NULL, and so does the difference.

When both standard deviations are 0 the difference is NULL rather than a division by zero.

The SQL uses only what Snowflake, Databricks and Redshift share (derived tables, UNION, CROSS JOIN,
COALESCE, NULLIF, SQRT, ABS), so one text serves all three. Pure and import-free: it is tested
offline, "Characterize cohorts" runs it against the population, and the "Compare cohorts" webapp
backend runs `pair_balance_sql` for a requested pair (decision 10 as revised, 2026-11-25).
"""
POPULATION_ID = -1

BALANCE_TABLE = "covariate_balance"
BALANCE_COLUMNS = ["cohort_definition_id", "comparator_id", "covariate_id", "covariate_name", "analysis_id",
                   "is_binary", "cohort_mean", "cohort_sd", "comparator_mean", "comparator_sd", "std_diff",
                   "abs_std_diff"]
# Column kinds, as in `solution.characterization.statements.RESULT_TABLES`.
BALANCE_KINDS = ["bigint", "bigint", "bigint", "text", "int", "short", "float", "float", "float", "float",
                 "float", "float"]
INPUT_TABLES = ("covariate", "covariate_continuous", "covariate_ref", "analysis_ref")


def _id(value):
    number = int(value)
    if number != value and str(number) != str(value).strip():
        raise ValueError("Not a cohort id: %r" % (value,))
    return number


def _ids(values):
    ids = sorted(set(_id(v) for v in values))
    if not ids:
        raise ValueError("A balance needs at least one cohort")
    return ids


def _target_ids(ids):
    """Derived table of the cohort ids, portable across the three dialects (no VALUES clause)."""
    return " UNION ALL ".join("SELECT %d AS cohort_id" % i for i in ids)


def _keys(table, ids, comparator):
    """Every (cohort, covariate) present in a cohort or in the comparator."""
    return ("SELECT cohort_definition_id AS cohort_id, covariate_id FROM %s WHERE cohort_definition_id IN (%s)\n"
            "  UNION\n"
            "  SELECT ids.cohort_id, cmp.covariate_id FROM (%s) ids\n"
            "  CROSS JOIN (SELECT covariate_id FROM %s WHERE cohort_definition_id = %d) cmp"
            % (table, ", ".join(str(i) for i in ids), _target_ids(ids), table, comparator))


def _binary(paths, ids, comparator):
    p1, p2 = "COALESCE(t.average_value, 0)", "COALESCE(c.average_value, 0)"
    return ("SELECT k.cohort_id, k.covariate_id, r.covariate_name, r.analysis_id, 'Y' AS is_binary,\n"
            "  %s AS cohort_mean, SQRT(%s * (1 - %s)) AS cohort_sd,\n"
            "  %s AS comparator_mean, SQRT(%s * (1 - %s)) AS comparator_sd\n"
            "FROM (%s) k\n"
            "LEFT JOIN %s t ON t.cohort_definition_id = k.cohort_id AND t.covariate_id = k.covariate_id\n"
            "LEFT JOIN %s c ON c.cohort_definition_id = %d AND c.covariate_id = k.covariate_id\n"
            "LEFT JOIN %s r ON r.covariate_id = k.covariate_id"
            % (p1, p1, p1, p2, p2, p2, _keys(paths["covariate"], ids, comparator), paths["covariate"],
               paths["covariate"], comparator, paths["covariate_ref"]))


def _continuous(paths, ids, comparator):
    def side(alias, column):
        return ("CASE WHEN %s.covariate_id IS NOT NULL THEN %s.%s WHEN a.missing_means_zero = 'Y' THEN 0 END"
                % (alias, alias, column))
    table = paths["covariate_continuous"]
    return ("SELECT k.cohort_id, k.covariate_id, r.covariate_name, r.analysis_id, 'N' AS is_binary,\n"
            "  %s AS cohort_mean, %s AS cohort_sd,\n"
            "  %s AS comparator_mean, %s AS comparator_sd\n"
            "FROM (%s) k\n"
            "LEFT JOIN %s t ON t.cohort_definition_id = k.cohort_id AND t.covariate_id = k.covariate_id\n"
            "LEFT JOIN %s c ON c.cohort_definition_id = %d AND c.covariate_id = k.covariate_id\n"
            "LEFT JOIN %s r ON r.covariate_id = k.covariate_id\n"
            "LEFT JOIN %s a ON a.analysis_id = r.analysis_id"
            % (side("t", "average_value"), side("t", "standard_deviation"), side("c", "average_value"),
               side("c", "standard_deviation"), _keys(table, ids, comparator), table, table, comparator,
               paths["covariate_ref"], paths["analysis_ref"]))


def balance_sql(paths, cohort_ids, comparator_id=POPULATION_ID):
    """One SELECT of the balance rows (`BALANCE_COLUMNS`) of each cohort against the comparator.

    paths: {"covariate", "covariate_continuous", "covariate_ref", "analysis_ref": resolved name}.
    """
    missing = [t for t in INPUT_TABLES if t not in paths]
    if missing:
        raise ValueError("No resolved name for %s" % ", ".join(missing))
    comparator = _id(comparator_id)
    ids = _ids(cohort_ids)
    if comparator in ids:
        raise ValueError("Cohort %d cannot be compared with itself" % comparator)
    diff = ("(v.cohort_mean - v.comparator_mean) / "
            "NULLIF(SQRT((v.cohort_sd * v.cohort_sd + v.comparator_sd * v.comparator_sd) / 2), 0)")
    return ("SELECT v.cohort_id AS cohort_definition_id, %d AS comparator_id, v.covariate_id, v.covariate_name,\n"
            "  v.analysis_id, v.is_binary, v.cohort_mean, v.cohort_sd, v.comparator_mean, v.comparator_sd,\n"
            "  %s AS std_diff,\n  ABS(%s) AS abs_std_diff\n"
            "FROM (\n%s\nUNION ALL\n%s\n) v"
            % (comparator, diff, diff, _binary(paths, ids, comparator), _continuous(paths, ids, comparator)))


def pair_balance_sql(paths, cohort_a, cohort_b):
    """The balance of cohort A against cohort B (B may be the population, -1). Decision 8."""
    return balance_sql(paths, [cohort_a], cohort_b)


def write_balance_statements(paths, cohort_ids, comparator_id=POPULATION_ID):
    """Delete, then insert, the balance rows of each cohort against the comparator."""
    ids = _ids(cohort_ids)
    table = paths[BALANCE_TABLE]
    return ["DELETE FROM %s WHERE comparator_id = %d AND cohort_definition_id IN (%s)"
            % (table, _id(comparator_id), ", ".join(str(i) for i in ids)),
            "INSERT INTO %s (%s)\n%s" % (table, ", ".join(BALANCE_COLUMNS), balance_sql(paths, ids, comparator_id))]


def recharacterized_statements(paths, recharacterized_ids, population_balance_ids):
    """The balance statements of one characterization run (decision 10, the cache).

    recharacterized_ids: the user's cohorts characterized again or for the first time; every cached
    pair naming one of them is deleted, to be recomputed on the next request.
    population_balance_ids: the cohorts whose balance against the population is (re)computed, which
    is every characterized cohort when the population itself was recomputed.
    """
    statements = []
    redone = sorted(set(_id(i) for i in recharacterized_ids) - {POPULATION_ID})
    if redone:
        listed = ", ".join(str(i) for i in redone)
        statements.append("DELETE FROM %s WHERE comparator_id <> %d AND (cohort_definition_id IN (%s) "
                          "OR comparator_id IN (%s))" % (paths[BALANCE_TABLE], POPULATION_ID, listed, listed))
    targets = sorted(set(_id(i) for i in population_balance_ids) - {POPULATION_ID})
    if targets:
        statements += write_balance_statements(paths, targets, POPULATION_ID)
    return statements


def cached_pairs_query(path):
    return "SELECT DISTINCT cohort_definition_id, comparator_id FROM %s" % path


def pair_cached_query(path, cohort_a, cohort_b):
    return ("SELECT COUNT(*) AS n FROM %s WHERE cohort_definition_id = %d AND comparator_id = %d"
            % (path, _id(cohort_a), _id(cohort_b)))
