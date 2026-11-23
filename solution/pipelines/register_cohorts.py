"""`register_cohorts`: the static Python recipe that ingests the submitted batch (R1, R2, R5).

Input: the "Original Scripts" folder. Outputs: the mapped scripts folder, `cohort_definition` and
`uploaded_cohort_definition` (the batch `build_cohorts` reads). The batch is the project variable
`cohort_submission`, written by the "Register cohorts" Setup tile or `tools/register_cohorts.py`.

Every check runs before anything is written, and every problem in the batch is reported at once:
the tile's checks again, against the data (an id already in `cohort_definition` needs Replace);
Atlas references the table naming does not cover (R1); OMOP tables missing from the project.
Names, descriptions and filenames are written through `sql_literal`.
"""
import json
import logging

import dataiku
from dataiku import SQLExecutor2

from solution.recipes.sql_script_function import (
    PROJECT, cohort_connection_type, create_cohort_definition_table_script, create_cohort_sql_script,
    return_script_cdm_tables, validate_cdm_tables,
)
from solution.recipes.sql_text import SESSION_COMMIT, split_statements, sql_literal
from solution.setup.registration import (
    DEFINITION_COLUMNS, folder_texts, provenance, read_rows, script_digest, validate_batch,
)
from solution.setup.table_naming import ATLAS, LABELS, key_map, unmapped_references
from solution.utils.variables import get_setting

logger = logging.getLogger(__name__)

ORIGINAL_SCRIPTS_FOLDER = "PqOBn6B3"
MAPPED_SCRIPTS_FOLDER = "lMM00YKr"


def read_submission():
    value = get_setting("cohort_submission")
    if isinstance(value, str):
        value = json.loads(value) if value.strip() else []
    if not isinstance(value, list) or not value:
        raise ValueError("No cohorts submitted. Register cohorts in Project Setup first.")
    return value


def table_naming():
    naming = get_setting("cohort_script_table_naming", default=ATLAS)
    return naming, key_map(naming, get_setting("cohort_script_table_prefix", default=""))


def map_batch(batch, files, mapping, naming):
    """Mapped script text and input tables per cohort id, plus the errors found on the way."""
    mapped, errors = {}, []
    for row in batch:
        label = "Cohort %s (%s, %s)" % (row["id"], row["name"], row["file"])
        text = files[row["file"]]
        unmapped = unmapped_references(text, mapping)
        if unmapped:
            errors.append("%s: the script uses %s, which the '%s' table naming does not cover. Check "
                          "'Cohort script table naming' in Project Setup."
                          % (label, ", ".join(unmapped), LABELS.get(naming, naming)))
            continue
        tables = return_script_cdm_tables(text, mapping)
        inputs = sorted(t for t in tables if t != "cohort")
        try:
            validate_cdm_tables(inputs, PROJECT, {"id": row["id"], "name": row["name"]})
        except ValueError as e:
            errors.append(str(e))
            continue
        mapped[row["id"]] = (create_cohort_sql_script(text, tables, row["id"], mapping), inputs)
    return mapped, errors


def definition_statements(batch, files, mapped, connection_type):
    timestamp = "GETDATE()" if connection_type == "Redshift" else "CURRENT_TIMESTAMP()"
    lit = lambda v: sql_literal(v, connection_type)  # noqa: E731
    ids, rows, uploaded = [], [], []
    for row in batch:
        cohort_id = int(row["id"])
        syntax = provenance(row["file"], script_digest(files[row["file"]]))
        ids.append(str(cohort_id))
        rows.append("(%d, %s, %s, 0, %s, 0, %s)" % (cohort_id, lit(row["name"]), lit(row["description"] or None),
                                                     lit(syntax), timestamp))
        uploaded.append("(%d, %s, %s, %s, %s)" % (cohort_id, lit(row["name"]), lit(row["description"] or None),
                                                  lit("|".join(mapped[cohort_id][1])), lit(row["file"])))
    return split_statements(create_cohort_definition_table_script(ids, rows, uploaded))


def register_cohorts():
    batch = read_submission()
    files = folder_texts(dataiku.Folder(ORIGINAL_SCRIPTS_FOLDER, ignore_flow=True))
    registered = read_rows(dataiku.Dataset("cohort_definition", ignore_flow=True), DEFINITION_COLUMNS)

    errors = validate_batch([dict(r, submit=True) for r in batch], [c["id"] for c in registered], set(files))
    if not errors:
        batch = [dict(r, id=int(r["id"]), name=r["name"].strip()) for r in batch]
        naming, mapping = table_naming()
        mapped, errors = map_batch(batch, files, mapping, naming)
    if errors:
        raise ValueError("Cohort registration refused; nothing was written:\n- " + "\n- ".join(errors))

    output = dataiku.Folder(MAPPED_SCRIPTS_FOLDER, ignore_flow=True)
    for cohort_id, (script, _) in mapped.items():
        output.upload_data("cohort_%d" % cohort_id, script.encode("utf-8"))
    connection_type = cohort_connection_type()
    SQLExecutor2(connection=get_setting("main_connection")).query_to_df(
        "SELECT 1", pre_queries=definition_statements(batch, files, mapped, connection_type),
        post_queries=SESSION_COMMIT[connection_type])
    logger.info("Registered %d cohorts: %s", len(batch), ", ".join(str(r["id"]) for r in batch))
    return sorted(mapped)
