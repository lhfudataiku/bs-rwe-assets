from solution.setup.extraction import EXTRACTION_LOG_COLUMNS, EXTRACTION_SUBMISSION, extraction_batch_ids, extraction_rows, extraction_submission, validate_extraction
from solution.setup.characterization import imported_at
from solution.setup.registration import DEFINITION_COLUMNS, LOG_COLUMNS, read_rows
from solution.utils.variables import get_setting, set_local


def do(payload, config, plugin_config, inputs):
    """"Extraction batch" tile (R9). payload {"action": "load"} lists every cohort whose latest build
    succeeded, with its extraction status, nothing ticked; {"action": "save", "rows": [...]} checks
    the ticked rows and stores them as `extraction_submission`.
    Errors come back as sentences ({"ok": false, "errors": [...]}), never as a traceback.
    """
    try:
        import dataiku
        project = dataiku.api_client().get_default_project()
        definitions = read_rows(dataiku.Dataset("cohort_definition"), DEFINITION_COLUMNS)
        build_logs = read_rows(dataiku.Dataset("cohort_building_log"), LOG_COLUMNS)
        extraction_logs = read_rows(dataiku.Dataset("patient_cov_log"), EXTRACTION_LOG_COLUMNS)
        built_ids, extracted_ids = extraction_batch_ids(definitions, build_logs, extraction_logs)
        if (payload or {}).get("action") == "save":
            rows = payload.get("rows") or []
            errors = validate_extraction(rows, built_ids, extracted_ids)
            if errors:
                return {"ok": False, "errors": errors}
            saved = set_local(project, EXTRACTION_SUBMISSION, extraction_submission(rows))
            return {"ok": True, "saved": len(saved)}
        last = get_setting(EXTRACTION_SUBMISSION, project.get_variables()) or []
        rows = extraction_rows(definitions, build_logs, extraction_logs, last if isinstance(last, list) else [],
                               imported_at(project))
        return {"ok": True, "rows": rows, "extracted_ids": extracted_ids}
    except Exception as e:
        return {"ok": False, "errors": ["Could not read the cohorts and their extraction: %s" % e]}
