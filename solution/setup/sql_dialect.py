"""Which SQL dialect an Atlas cohort script was exported for, from markers Atlas always writes.

Sampled on 2026-11-24: five atlas-demo.ohdsi.org cohorts (WebAPI 2.14) rendered for Snowflake,
Databricks ("spark") and Redshift, plus every script in `cohort_scripts/`. Each dialect has markers
in every script:

- Snowflake: `CREATE TEMP TABLE` and `DATEADD(day, ...)`.
- Databricks: `USING DELTA` and `date_add(...)`.
- Redshift: `#` session tables with `DISTKEY`, `DISTSTYLE` or `ANALYZE`.
- PostgreSQL (not supported): `CREATE TEMP TABLE` with `INTERVAL` arithmetic and no `DATEADD`.
- The untranslated OHDSI template (Atlas's "SQL Server" export, not supported): `SELECT ... INTO #t`.

A script with none of these markers (hand-written SQL) is not judged: only a script that clearly
belongs to another dialect is refused. Pure: no DSS module is imported, so the Setup tiles inline it.
"""
import re

SNOWFLAKE, DATABRICKS, REDSHIFT = "Snowflake", "Databricks", "Redshift"
POSTGRES, TEMPLATE = "PostgreSQL", "OHDSI SQL template"
SUPPORTED = (SNOWFLAKE, DATABRICKS, REDSHIFT)

_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_INTO_HASH = re.compile(r"(\w+)\s+INTO\s+#\w+", re.I)  # SELECT ... INTO #t; INSERT INTO #t is Redshift too
_HASH_TABLE = re.compile(r"#\w+")
_REDSHIFT = re.compile(r"\bDISTKEY\s*\(|\bDISTSTYLE\b|^\s*ANALYZE\s+#", re.I | re.M)
_USING_DELTA = re.compile(r"\bUSING\s+DELTA\b", re.I)
_DATE_ADD = re.compile(r"\bdate_add\s*\(", re.I)
_DATEADD = re.compile(r"\bDATEADD\s*\(", re.I)
_TEMP_TABLE = re.compile(r"\bCREATE\s+TEMP(?:ORARY)?\s+TABLE\b", re.I)
_INTERVAL = re.compile(r"\bINTERVAL\b", re.I)


def detect_dialect(sql):
    """The dialect the script was written for, or None when it carries no known marker."""
    code = _COMMENTS.sub(" ", sql or "")
    if any(word.upper() != "INSERT" for word in _INTO_HASH.findall(code)):
        return TEMPLATE
    if _USING_DELTA.search(code) or _DATE_ADD.search(code):
        return DATABRICKS
    if _HASH_TABLE.search(code) and _REDSHIFT.search(code):
        return REDSHIFT
    if _TEMP_TABLE.search(code):
        if _DATEADD.search(code):
            return SNOWFLAKE
        if _INTERVAL.search(code):
            return POSTGRES
    return None


def dialect_error(sql, connection_type, label):
    """A sentence when the script was written for another dialect than the connection; else None."""
    found = detect_dialect(sql)
    if found is None or connection_type not in SUPPORTED or found == connection_type:
        return None
    if found in SUPPORTED:
        return ("%s: the script was exported for %s, but this project runs on %s. Export it from Atlas "
                "for %s." % (label, found, connection_type, connection_type))
    what = "the untranslated OHDSI SQL template" if found == TEMPLATE else "written for " + found
    return ("%s: the script is %s, which the solution does not run. Export it from Atlas for %s."
            % (label, what, connection_type))
