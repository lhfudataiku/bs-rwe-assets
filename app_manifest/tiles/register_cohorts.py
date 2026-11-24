from solution.setup.registration import DEFINITION_COLUMNS, folder_texts, read_rows, registration_rows, submission, validate_batch
from solution.utils.variables import get_setting, set_local

ORIGINAL_SCRIPTS_FOLDER = "PqOBn6B3"


def do(payload, config, plugin_config, inputs):
    """"Register cohorts" tile (R2). payload {"action": "load"} lists one row per uploaded script;
    {"action": "save", "rows": [...]} checks the ticked rows and stores them as `cohort_submission`.
    Errors come back as sentences ({"ok": false, "errors": [...]}), never as a traceback.
    """
    try:
        import dataiku
        project = dataiku.api_client().get_default_project()
        files = folder_texts(dataiku.Folder(ORIGINAL_SCRIPTS_FOLDER))
        registered = read_rows(dataiku.Dataset("cohort_definition"), DEFINITION_COLUMNS)
        try:  # the project's SQL dialect: cohort sits on the main connection
            connection_type = project.get_dataset("cohort").get_settings().type
        except Exception:
            connection_type = None  # no dialect check rather than no tile
        if (payload or {}).get("action") == "save":
            rows = payload.get("rows") or []
            errors = validate_batch(rows, [c["id"] for c in registered], files, connection_type)
            if errors:
                return {"ok": False, "errors": errors}
            saved = set_local(project, "cohort_submission", submission(rows))
            return {"ok": True, "saved": len(saved)}
        last = get_setting("cohort_submission", project.get_variables()) or []
        return {"ok": True, "rows": registration_rows(files, registered, last if isinstance(last, list) else [],
                                                      connection_type),
                "registered_ids": [c["id"] for c in registered]}
    except Exception as e:
        return {"ok": False, "errors": ["Could not read the scripts or registered cohorts: %s" % e]}
