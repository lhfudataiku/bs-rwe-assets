from solution.setup.characterization import CHARACTERIZATION_LOG_COLUMNS, SUBMISSION, batch_ids, characterization_rows, imported_at, batch_submission, validate_selection
from solution.setup.registration import DEFINITION_COLUMNS, LOG_COLUMNS, read_rows
from solution.utils.variables import get_setting, set_local


def do(payload, config, plugin_config, inputs):
    """"Characterization batch" tile (R3, decisions 14 and 15). payload {"action": "load"} lists the
    population and every cohort whose latest build succeeded, with its status; {"action": "save",
    "rows": [...]} checks the ticked rows and stores them as `characterization_submission`.
    Errors come back as sentences ({"ok": false, "errors": [...]}), never as a traceback.
    """
    try:
        import dataiku
        project = dataiku.api_client().get_default_project()
        definitions = read_rows(dataiku.Dataset("cohort_definition"), DEFINITION_COLUMNS)
        build_logs = read_rows(dataiku.Dataset("cohort_building_log"), LOG_COLUMNS)
        char_logs = read_rows(dataiku.Dataset("characterization_log"), CHARACTERIZATION_LOG_COLUMNS)
        built_ids, characterized_ids = batch_ids(definitions, build_logs, char_logs)
        if (payload or {}).get("action") == "save":
            rows = payload.get("rows") or []
            errors = validate_selection(rows, built_ids, characterized_ids)
            if errors:
                return {"ok": False, "errors": errors}
            saved = set_local(project, SUBMISSION, batch_submission(rows))
            return {"ok": True, "saved": len(saved)}
        last = get_setting(SUBMISSION, project.get_variables()) or []
        rows = characterization_rows(definitions, build_logs, char_logs, last if isinstance(last, list) else [],
                                     imported_at(project))
        return {"ok": True, "rows": rows, "characterized_ids": characterized_ids}
    except Exception as e:
        return {"ok": False, "errors": ["Could not read the cohorts and their characterization: %s" % e]}
