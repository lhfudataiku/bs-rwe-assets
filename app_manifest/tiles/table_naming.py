from solution.setup.table_naming import ATLAS, LABELS, NAMINGS, key_map, naming_errors, table_groups
from solution.utils.variables import get_setting, set_local


def do(payload, config, plugin_config, inputs):
    """"Cohort script table naming" tile (R1). payload {"action": "load"} returns the stored choice,
    prefix and mapping, with the Atlas names to start a mapping from; {"action": "save", "naming",
    "prefix", "mapping"} checks them and stores the three variables. Errors come back as sentences.
    """
    try:
        import json
        import dataiku
        project = dataiku.api_client().get_default_project()
        payload = payload or {}
        if payload.get("action") == "save":
            naming = payload.get("naming") or ATLAS
            prefix = (payload.get("prefix") or "").strip()
            mapping = {k: (v or "").strip() for k, v in (payload.get("mapping") or {}).items()}
            errors = naming_errors(naming, prefix, mapping)
            if errors:
                return {"ok": False, "errors": errors}
            set_local(project, "cohort_script_table_naming", naming)
            set_local(project, "cohort_script_table_prefix", prefix)
            set_local(project, "cohort_script_table_map", {k: v for k, v in mapping.items() if v})
            return {"ok": True}
        variables = project.get_variables()
        mapping = get_setting("cohort_script_table_map", variables) or {}
        if isinstance(mapping, str):
            mapping = json.loads(mapping) if mapping.strip() else {}
        return {"ok": True, "naming": get_setting("cohort_script_table_naming", variables) or ATLAS,
                "prefix": get_setting("cohort_script_table_prefix", variables) or "", "mapping": mapping,
                "atlas": key_map(ATLAS), "choices": [{"value": n, "label": LABELS[n]} for n in NAMINGS],
                "groups": [{"label": label, "tables": tables} for label, tables in table_groups()]}
    except Exception as e:
        return {"ok": False, "errors": ["Could not read or save the table naming: %s" % e]}
