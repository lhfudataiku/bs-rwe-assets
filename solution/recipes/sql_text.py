"""SQL text helpers for the cohort build (solution-revision-plan.md, R2, R5 and R6).

Import-free on purpose: no DSS module is needed, so everything here is tested offline.
"""
import re

SESSION_COMMIT = {"Snowflake": ["COMMIT"], "Redshift": ["COMMIT"], "Databricks": []}
TEMP_PLACEHOLDER = re.compile(r"@temp_database_schema\.(\w+)", re.IGNORECASE)
SCRATCH_PREFIX = "rwdtmp_"


def split_statements(sql):
    """Split a script into statements on `;` outside quotes, backticks and comments.

    Snowflake and Databricks reject several statements in one call (spike, R5), so each statement
    runs as its own pre-query. Comments are kept inside the statement they precede; a piece that
    holds only comments and whitespace is dropped.
    """
    statements, start, i, n = [], 0, 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in ("'", '"', "`"):
            i += 1
            while i < n:
                if sql[i] == "\\" and ch == "'":
                    i += 2
                    continue
                if sql[i] == ch:
                    if i + 1 < n and sql[i + 1] == ch:  # doubled quote inside a literal
                        i += 2
                        continue
                    break
                i += 1
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n - 1 if end < 0 else end
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n - 1 if end < 0 else end + 1
        elif ch == ";":
            statements.append(sql[start:i])
            start = i + 1
        i += 1
    statements.append(sql[start:])
    return [s.strip() for s in statements if _has_code(s)]


def _has_code(piece):
    without_comments = re.sub(r"/\*.*?\*/|--[^\n]*", "", piece, flags=re.DOTALL)
    return bool(without_comments.strip())


def sql_literal(value, connection_type):
    """A value as a SQL literal for the dialect: NULL, a number, or a quoted, escaped string.

    Snowflake, Databricks and Redshift all read a backslash in a string literal as an escape, so it
    is doubled; the quote is doubled on Snowflake and Redshift and backslash-escaped on Databricks.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if connection_type not in SESSION_COMMIT:
        raise ValueError("No literal rule for connection type %r" % connection_type)
    text = str(value).replace("\\", "\\\\")
    text = text.replace("'", "\\'") if connection_type == "Databricks" else text.replace("'", "''")
    return "'%s'" % text


def temp_table_names(sql):
    """Atlas temporary-table names (`@temp_database_schema.<name>`) in first-seen order, lower case."""
    seen = []
    for name in TEMP_PLACEHOLDER.findall(sql):
        if name.lower() not in seen:
            seen.append(name.lower())
    return seen


def scratch_table_prefix(project_key, cohort_id):
    """`rwdtmp_<project key>__c<cohort id>_`: attributable, and unique per project and cohort.

    The double underscore and `c` keep one project's prefix from matching another key that only
    extends it (`SOL` against `SOL_2`).
    """
    return "%s%s__c%d_" % (SCRATCH_PREFIX, project_key.lower(), int(cohort_id))


def project_scratch_prefix(project_key):
    return "%s%s__c" % (SCRATCH_PREFIX, project_key.lower())


def is_project_scratch_table(name, project_key):
    """A scratch table of this project's cohort build (never one of the characterization's)."""
    return re.match(re.escape(project_scratch_prefix(project_key)) + r"\d+_", name.lower()) is not None


def characterization_scratch_prefix(project_key):
    """`rwdtmp_<project key>__ch_`: the characterization's scratch tables (R3, step 4 part 3).

    One run covers many cohorts, so the prefix carries no cohort id. `ch` is not a number, so the
    cohort build's sweep never drops these, and the characterization's sweep (below) never drops the
    build's: a build and a characterization can run at the same time.
    """
    return "%s%s__ch_" % (SCRATCH_PREFIX, project_key.lower())


def is_characterization_scratch_table(name, project_key):
    return name.lower().startswith(characterization_scratch_prefix(project_key))


def extraction_scratch_prefix(project_key):
    """`rwdtmp_<project key>__pc_`: the patient-level extract's scratch tables (R9).

    Like the characterization's, one run covers many cohorts. `pc` is neither a number nor `ch`, so
    no sweep drops another's tables: a build, a characterization and an extract can run at once.
    """
    return "%s%s__pc_" % (SCRATCH_PREFIX, project_key.lower())


def is_extraction_scratch_table(name, project_key):
    return name.lower().startswith(extraction_scratch_prefix(project_key))


def render_temp_tables(sql, connection_type, prefix=None, qualifier=None):
    """Replace `@temp_database_schema.<name>` for the dialect.

    Snowflake and Redshift scripts create session temporary tables, so the bare name is enough.
    Databricks scripts create real Delta tables (R6); they go to `<qualifier>.<prefix><name>`.
    Returns the script and the fully qualified Databricks scratch tables it uses (empty elsewhere).
    """
    if connection_type != "Databricks":
        return TEMP_PLACEHOLDER.sub(lambda m: m.group(1), sql), []
    if not prefix or not qualifier:
        raise ValueError("Databricks scripts need a scratch prefix and schema")
    tables = ["%s.`%s%s`" % (qualifier, prefix, name) for name in temp_table_names(sql)]
    rendered = TEMP_PLACEHOLDER.sub(lambda m: "%s.`%s%s`" % (qualifier, prefix, m.group(1).lower()), sql)
    return rendered, tables


IDENTIFIER_PART = re.compile(r"`(?:[^`]|``)*`|\"(?:[^\"]|\"\")*\"|[^.`\"]+")


def name_parts(name):
    """Split a possibly quoted, dot-separated SQL name into its parts, quotes kept."""
    parts = IDENTIFIER_PART.findall(name.strip())
    if not parts or ".".join(parts) != name.strip():
        raise ValueError("Not a SQL name: %r" % name)
    return parts


def table_qualifier(resolved_table_name):
    """`catalog.schema` (as quoted by DSS) of a resolved table name; raises on a bare name."""
    parts = name_parts(resolved_table_name)
    if len(parts) < 2:
        raise ValueError("%r has no schema; set the temp_schema variable" % resolved_table_name)
    return ".".join(parts[:-1])


def quote_databricks_name(name):
    """Backtick-quote each part of `schema` or `catalog.schema` that is not quoted yet."""
    return ".".join(p if p.startswith("`") else "`%s`" % p for p in name_parts(name))
