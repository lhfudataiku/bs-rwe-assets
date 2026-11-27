"""Which cohorts to extract patient-level covariates for (solution-revision-plan.md, R9).

The "Extraction batch" tile and the `extract_patient_covariates` recipe both call these functions;
the recipe repeats every check and is the authority, as for the characterization.

- One row per cohort whose latest build succeeded, with its extraction status. There is no
  population row: an extract is requested for the cohorts of a study.
- Nothing is ticked by default (R9 decision 1: on request).
- An extracted cohort is never redone unless it is ticked *In batch* and *Replace*.
- Each saved entry carries when it was saved, and expires once a run extracts its cohort after that,
  for the reason given in `solution.setup.characterization` (an open Setup page writes its old copy
  of the project variables back while a scenario it started runs).

Pure apart from what it imports from `characterization` (itself pure but for `imported_at`), so
`tools/app_manifest.py` inlines it into the tile. Its top-level names must not repeat
characterization's: the inliner puts both in one namespace and refuses a shared name.
"""
from solution.setup.batch import as_int, batch_errors, latest_by_id
from solution.setup.characterization import SUCCESS, live_submission, utc_timestamp

EXTRACTION_SUBMISSION = "extraction_submission"
EXTRACTION_LOG_COLUMNS = {"run_timestamp": "RUN_TIMESTAMP", "id": "COHORT_DEFINITION_ID",
                          "build_timestamp": "BUILD_TIMESTAMP", "count": "ENTRY_COUNT", "status": "STATUS"}

NOT_EXTRACTED, EXTRACTION_IN_BATCH, EXTRACTED = "not extracted", "in batch", "extracted"
REBUILT_SINCE_EXTRACTED, REIMPORTED_SINCE_EXTRACTED, EXTRACTION_FAILED = \
    "rebuilt since extracted", "data re-imported since extracted", "extraction failed"
EXTRACTION_STATUS_LABELS = {
    NOT_EXTRACTED: "Not extracted", EXTRACTION_IN_BATCH: "In batch, not run yet", EXTRACTED: "Extracted",
    REBUILT_SINCE_EXTRACTED: "Rebuilt since extracted",
    REIMPORTED_SINCE_EXTRACTED: "Data re-imported since extracted", EXTRACTION_FAILED: "Extraction failed"}


def _run_succeeded(log):
    return str(log.get("status") or "").upper() == SUCCESS


def extraction_batch_ids(definitions, build_logs, extraction_logs):
    """(built ids, extracted ids): registered cohorts whose latest build succeeded, and cohorts with a
    successful extraction. What `validate_extraction` and `selected_extraction_ids` check against."""
    registered = {as_int(d.get("id")) for d in definitions}
    built = sorted(i for i, log in latest_by_id(build_logs).items()
                   if _run_succeeded(log) and i in registered and i >= 0)
    extracted = sorted(latest_by_id(extraction_logs, keep=_run_succeeded))
    return built, extracted


def live_extraction_submission(submission, extraction_logs):
    """The saved batch without the entries a run extracted at or after they were saved."""
    return live_submission(submission, extraction_logs)


def extraction_rows(definitions, build_logs, extraction_logs, submission=None, imported_at=None):
    """The tile's rows: each cohort whose latest build succeeded, with its extraction status.

    definitions: [{"id", "name"}] from `cohort_definition`; build_logs: [{"run_timestamp", "id",
    "count", "status"}] from `cohort_building_log`; extraction_logs: [{"run_timestamp", "id",
    "build_timestamp", "count", "status"}] from `patient_cov_log`; submission: the saved
    `extraction_submission` ([{"id", "replace", "saved"}]), whose expired entries are ignored;
    imported_at: when "Import Datasets" last succeeded, or None.
    """
    names = {as_int(d.get("id")): d.get("name") or "" for d in definitions}
    built = latest_by_id(build_logs)
    done = latest_by_id(extraction_logs, keep=_run_succeeded)
    last_try = latest_by_id(extraction_logs)
    pending = {as_int(r.get("id")): r for r in live_extraction_submission(submission, extraction_logs)}
    rows = []
    for cohort_id in sorted(i for i in built if i is not None and i >= 0):
        build = built[cohort_id]
        if not _run_succeeded(build) or cohort_id not in names:
            continue  # not offered: its latest build failed, or it is no longer registered
        extract = done.get(cohort_id)
        attempt = last_try.get(cohort_id)
        if attempt is not None and not _run_succeeded(attempt):
            status = EXTRACTION_FAILED  # on Databricks a failed redo may have deleted its rows already
        elif extract is None:
            status = NOT_EXTRACTED
        elif str(build.get("run_timestamp") or "") > str(extract.get("build_timestamp") or ""):
            status = REBUILT_SINCE_EXTRACTED
        elif imported_at and str(imported_at) > str(extract.get("run_timestamp") or ""):
            status = REIMPORTED_SINCE_EXTRACTED
        else:
            status = EXTRACTED
        row = {"id": cohort_id, "name": names[cohort_id], "subjects": build.get("count"),
               "built": build.get("run_timestamp") or "", "extracted": extract.get("run_timestamp") if extract else "",
               "entries": extract.get("count") if extract else None,
               "status": status, "submit": False, "replace": False}
        if cohort_id in pending:
            row.update(status=EXTRACTION_IN_BATCH, submit=True, replace=bool(pending[cohort_id].get("replace")))
        rows.append(row)
    return rows


def _extraction_label(row):
    return (row.get("name") or "").strip() or "Cohort %s" % row.get("id")


def validate_extraction(rows, built_ids, extracted_ids):
    """Errors in the ticked rows, as sentences. Empty when the batch can be extracted."""
    errors, valid = batch_errors(rows, extracted_ids, _extraction_label, "cohort", "is already extracted",
                                 "extract it again")
    built_ids = {as_int(i) for i in built_ids}
    for row, cohort_id in valid:
        if cohort_id not in built_ids:
            errors.append("%s: cohort %d has no successful build. Build it in Build Cohorts first."
                          % (_extraction_label(row), cohort_id))
    return errors


def extraction_submission(rows, saved=None):
    """The `extraction_submission` value for the ticked rows, each stamped with when it was saved."""
    saved = saved or utc_timestamp()
    return [{"id": as_int(r.get("id")), "replace": bool(r.get("replace")), "saved": saved}
            for r in rows if r.get("submit")]


def selected_extraction_ids(submission_value, built_ids, extracted_ids):
    """The cohort ids the run extracts, checked again as the authority. Raises on any error."""
    rows = [{"id": r.get("id"), "submit": True, "replace": bool(r.get("replace"))} for r in (submission_value or [])]
    if not rows:
        return []
    errors = validate_extraction(rows, built_ids, extracted_ids)
    if errors:
        raise ValueError("The extraction batch cannot run:\n- " + "\n- ".join(errors))
    return sorted({as_int(r["id"]) for r in rows})
