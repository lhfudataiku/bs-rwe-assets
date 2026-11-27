from solution.setup.registration import DEFINITION_COLUMNS, LOG_COLUMNS, built_cohort_rows, read_rows


def do(payload, config, plugin_config, inputs):
    """"Built cohorts" tile (R2): every registered cohort with its latest build. Read-only."""
    try:
        import dataiku
        definitions = read_rows(dataiku.Dataset("cohort_definition"), DEFINITION_COLUMNS)
        logs = read_rows(dataiku.Dataset("cohort_building_log"), LOG_COLUMNS)
        return {"ok": True, "rows": built_cohort_rows(definitions, logs)}
    except Exception as e:
        return {"ok": False, "errors": ["Could not read the cohorts: %s" % e]}
