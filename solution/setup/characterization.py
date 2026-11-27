"""Which cohorts to characterize (solution-revision-plan.md, R3 decisions 14 and 15).

The "Characterization batch" tile and the `characterize_cohorts` recipe both call these functions;
the recipe repeats every check and is the authority, as for registration.

- One row per cohort whose latest build succeeded, with its characterization status.
- A cohort not characterized yet is ticked *In batch* by default, so one run covers every new cohort.
- A characterized cohort is never redone unless it is ticked *In batch* and *Replace*.
- The population (id -1) is not chosen by the user: it is characterized when it has never been, or
  when the data was imported after its last characterization.
- Each saved entry carries when it was saved, and expires once a run characterizes its cohort after
  that (`live_submission`). The run clears the saved batch, but an open Project Setup page writes its
  own, older copy of the project variables back while a scenario it started runs (seen on DSS,
  2026-11-27), which restores the batch just run; an expired entry then does nothing.

Timestamps are ISO strings (`%Y-%m-%dT%H:%M:%SZ`, UTC), as `cohort_building_log` writes them.
Pure apart from `imported_at`, which reads a scenario run from the project handle it is given, and
importing only the pure `batch` module: `tools/app_manifest.py` inlines it into the tile.
"""
import datetime

from solution.setup.batch import as_int, batch_errors, latest_by_id

POPULATION_ID = -1
POPULATION_NAME = "Population (every person with 365 days of observation)"
SUCCESS, FAILED = "SUCCESS", "FAILED"

NOT_CHARACTERIZED, IN_BATCH, CHARACTERIZED = "not characterized", "in batch", "characterized"
REBUILT, REIMPORTED, CHAR_FAILED = "rebuilt since characterized", "data re-imported since characterized", \
    "characterization failed"
STATUS_LABELS = {NOT_CHARACTERIZED: "Not characterized", IN_BATCH: "In batch, not run yet",
                 CHARACTERIZED: "Characterized", REBUILT: "Rebuilt since characterized",
                 REIMPORTED: "Data re-imported since characterized", CHAR_FAILED: "Characterization failed"}

CHARACTERIZATION_LOG_COLUMNS = {"run_timestamp": "RUN_TIMESTAMP", "id": "COHORT_DEFINITION_ID",
                                "build_timestamp": "BUILD_TIMESTAMP", "count": "COHORT_COUNT",
                                "status": "STATUS"}
IMPORT_SCENARIO = "IMPORTDATASETSFROMDATAPREPPROJECT"
SUBMISSION = "characterization_submission"


def utc_timestamp(moment=None):
    return (moment or datetime.datetime.utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


def imported_at(project):
    """When "Import Datasets" last succeeded, as a UTC ISO string, or None if unknown."""
    try:
        last = project.get_scenario(IMPORT_SCENARIO).get_last_successful_run()
        end = getattr(last, "end_time", None) if last else None
        if end is None:
            return None
        if end.tzinfo is not None:
            end = end.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return utc_timestamp(end)
    except Exception:  # unknown: then only never-characterized decides for the population
        return None


def batch_ids(definitions, build_logs, characterization_logs):
    """(built ids, characterized ids): registered cohorts whose latest build succeeded, and cohorts
    with a successful characterization. What `validate_selection` and `selected_ids` check against."""
    registered = {as_int(d.get("id")) for d in definitions}
    built = sorted(i for i, log in latest_by_id(build_logs).items() if _succeeded(log) and i in registered)
    characterized = sorted(latest_by_id(characterization_logs, keep=_succeeded))
    return built, characterized


def _succeeded(log):
    return str(log.get("status") or "").upper() == SUCCESS


def population_needed(characterization_logs, imported_at=None):
    """Whether the run must characterize the population: never done, or the data imported since."""
    done = latest_by_id(characterization_logs, keep=_succeeded).get(POPULATION_ID)
    return done is None or bool(imported_at and str(imported_at) > str(done.get("run_timestamp") or ""))


def live_submission(submission, characterization_logs):
    """The saved batch without its expired entries: those whose cohort a run characterized
    successfully at or after the entry was saved. An entry without `saved` (written before entries
    carried it) expires on any successful characterization of its cohort."""
    done = latest_by_id(characterization_logs, keep=_succeeded)
    live = []
    for row in submission or []:
        last = done.get(as_int(row.get("id")))
        if last is not None and str(last.get("run_timestamp") or "") >= str(row.get("saved") or ""):
            continue
        live.append(row)
    return live


def characterization_rows(definitions, build_logs, characterization_logs, submission=None, imported_at=None):
    """The tile's rows: the population first, then each cohort whose latest build succeeded.

    definitions: [{"id", "name"}] from `cohort_definition`; build_logs: [{"run_timestamp", "id",
    "count", "status"}] from `cohort_building_log`; characterization_logs: [{"run_timestamp", "id",
    "build_timestamp", "count", "status"}] from `characterization_log`; submission: the saved
    `characterization_submission` ([{"id", "replace", "saved"}]), whose expired entries are ignored;
    imported_at: when "Import Datasets" last succeeded, or None.
    """
    names = {as_int(d.get("id")): d.get("name") or "" for d in definitions}
    built = latest_by_id(build_logs)
    done = latest_by_id(characterization_logs, keep=_succeeded)
    last_try = latest_by_id(characterization_logs)
    pending = {as_int(r.get("id")): r for r in live_submission(submission, characterization_logs)}

    needed = population_needed(characterization_logs, imported_at)
    population = done.get(POPULATION_ID)
    rows = [{"id": POPULATION_ID, "name": POPULATION_NAME, "population": True,
             "subjects": population.get("count") if population else None, "built": "",
             "characterized": population.get("run_timestamp") if population else "",
             "status": (REIMPORTED if population else NOT_CHARACTERIZED) if needed else CHARACTERIZED,
             "submit": needed, "replace": bool(population) and needed}]

    for cohort_id in sorted(i for i in built if i is not None and i >= 0):
        build = built[cohort_id]
        if not _succeeded(build) or cohort_id not in names:
            continue  # not offered: its latest build failed, or it is no longer registered
        char = done.get(cohort_id)
        attempt = last_try.get(cohort_id)
        if attempt is not None and not _succeeded(attempt):
            # Its latest run failed. On Databricks a failed redo may have deleted its rows already.
            status = CHAR_FAILED
        elif char is None:
            status = NOT_CHARACTERIZED
        elif str(build.get("run_timestamp") or "") > str(char.get("build_timestamp") or ""):
            status = REBUILT
        elif imported_at and str(imported_at) > str(char.get("run_timestamp") or ""):
            status = REIMPORTED
        else:
            status = CHARACTERIZED
        row = {"id": cohort_id, "name": names[cohort_id], "population": False, "subjects": build.get("count"),
               "built": build.get("run_timestamp") or "", "characterized": char.get("run_timestamp") if char else "",
               "status": status, "submit": char is None, "replace": False}
        if cohort_id in pending:
            row.update(status=IN_BATCH, submit=True, replace=bool(pending[cohort_id].get("replace")))
        rows.append(row)
    return rows


def validate_selection(rows, built_ids, characterized_ids):
    """Errors in the ticked rows, as sentences. Empty when the batch can be characterized.

    built_ids: cohorts whose latest build succeeded; characterized_ids: cohorts with a successful
    characterization. The population row is the run's to decide and is never checked here.
    """
    cohorts = [r for r in rows if not r.get("population") and as_int(r.get("id")) != POPULATION_ID]
    errors, valid = batch_errors(cohorts, characterized_ids, _label, "cohort", "is already characterized",
                                 "characterize it again")
    built_ids = {as_int(i) for i in built_ids}
    for row, cohort_id in valid:
        if cohort_id not in built_ids:
            errors.append("%s: cohort %d has no successful build. Build it in Build Cohorts first."
                          % (_label(row), cohort_id))
    return errors


def _label(row):
    return (row.get("name") or "").strip() or "Cohort %s" % row.get("id")


def batch_submission(rows, saved=None):
    """The `characterization_submission` value for the ticked cohort rows (the population excluded),
    each stamped with when it was saved (now, by default)."""
    saved = saved or utc_timestamp()
    return [{"id": as_int(r.get("id")), "replace": bool(r.get("replace")), "saved": saved}
            for r in rows if r.get("submit") and not r.get("population") and as_int(r.get("id")) != POPULATION_ID]


def selected_ids(submission_value, built_ids, characterized_ids):
    """The cohort ids the run characterizes, checked again as the authority. Raises on any error."""
    rows = [{"id": r.get("id"), "submit": True, "replace": bool(r.get("replace"))} for r in (submission_value or [])]
    if not rows:
        return []
    errors = validate_selection(rows, built_ids, characterized_ids)
    if errors:
        raise ValueError("The characterization batch cannot run:\n- " + "\n- ".join(errors))
    return sorted({as_int(r["id"]) for r in rows})
