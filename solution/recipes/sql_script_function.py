import re
import logging

import dataiku
from dku_utils.projects.project_commons import get_current_project_and_variables, get_all_project_dataset_names
from dku_utils.projects.datasets.dataset_commons import (
    get_dataset_settings_and_dictionary,
)

from variables import OMOP_CDM_KEYS, SQL_SCRIPT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT, VARIABLES = get_current_project_and_variables()
OMOP_KEYS = OMOP_CDM_KEYS +['cohort']

def create_cohort_sql_script(
    sql_code,
    script_cdm_table_names,
    cohort_definition_id,
    key_map,
):
    # Create CDM standard table to SQL table path map
    replacement = create_cdm_table_paths(
        key_map, script_cdm_table_names
    )
    # Create replacement for temporary table names in cohort scripts from Atlas
    temp_map = create_temp_table_map(sql_code)
    replacement.update(temp_map)
    # Replace cohort sql variables
    new_script = replace_sql_script_variables(sql_code, replacement)
    # Replace cohort id variables
    new_script = new_script.replace("@target_cohort_id", str(cohort_definition_id))
    # Create cohort tables script
    init_script = create_cohort_table_script(cohort_definition_id)
    # Create cohort definition script
    final_script = init_script + new_script

    return final_script


def create_cohort_table_script(cohort_definition_id):
    cohort_init_script = get_script_by_connection_type("cohort_init_script")
    replacement = {
        "@cohort": get_sql_path("cohort"),
        "@cohort_definition_id": str(cohort_definition_id),
    }
    return replace_sql_script_variables(cohort_init_script, replacement)


def create_cohort_definition_table_script(cohort_ids, row_values, uploaded_row_values):
    cohort_definition_script = get_script_by_connection_type("cohort_definition_script")
    cohort_ids = ", ".join(cohort_ids)
    row_values = ",\n".join(row_values)
    uploaded_row_values = ",\n".join(uploaded_row_values)
    replacement = {
        "@cohort_ids": cohort_ids,
        "@row_values": row_values,
        "@uploaded_row_values": uploaded_row_values,
        "@cohort_definition": get_sql_path("cohort_definition"),
        "@uploaded_cohort_definition": get_sql_path("uploaded_cohort_definition"),
    }
    return replace_sql_script_variables(cohort_definition_script, replacement)


def create_cohort_log_script(row_values):
    cohort_log_script = get_script_by_connection_type("cohort_log_script")
    row_values = ",\n".join(row_values)
    replacement = {
        "@cohort_building_log": get_sql_path("cohort_building_log"),
        "@cohort_log": row_values,
    }
    return replace_sql_script_variables(cohort_log_script, replacement)


def get_script_by_connection_type(script_name):
    # Connection type = project main connection
    _, dataset_settings_dict = get_dataset_settings_and_dictionary(PROJECT, "cohort")
    connection_type = dataset_settings_dict.get("type", "")
    script = SQL_SCRIPT[connection_type][script_name]
    return script


def create_cdm_table_map(key_map):
    cdm_standard_table = {}
    for k, v in key_map.items():
        if k in OMOP_KEYS and v:
            cdm_standard_table[v] = k
    return cdm_standard_table


def create_temp_table_map(sql_code):
    replacement = {}
    pattern = re.compile(r"@temp_database_schema\.\w*", re.IGNORECASE)
    for table_name in set(pattern.findall(sql_code)):
        replacement[table_name.lower()] = table_name.split(".")[1]
    return replacement


def return_script_cdm_tables(sql_code, key_map):
    """Extract CDM table names from SQL code.
    
    Args:
        sql_code (str): The SQL code to analyze
        key_map (dict): Optional mapping of standard OMOP table names to custom names
    
    Returns:
        list: List of unique CDM table names found in the SQL code
    """
    # use standard OMOP table name if no key map provided
    if key_map:
        cdm_standard_table = create_cdm_table_map(key_map)
        pattern = re.compile(
            r"(?<!\S)(" + "|".join(re.escape(key) for key in cdm_standard_table.keys()) + r")\b",
            re.IGNORECASE,
        )
        script_cdm_table_names = [
            cdm_standard_table[k.lower()] for k in set(pattern.findall(sql_code))
    ]
        script_cdm_table_names = list(set(script_cdm_table_names))
    else:
        pattern = re.compile(
            r"(?<!\S)(" + "|".join(re.escape(key) for key in OMOP_KEYS) + r")\b",
            re.IGNORECASE,
        )
        script_cdm_table_names = [k.lower() for k in list(set(pattern.findall(sql_code)))]      
    return script_cdm_table_names


def get_sql_path(table):
    _, dataset_settings_dict = get_dataset_settings_and_dictionary(PROJECT, table)
    connection_type = dataset_settings_dict.get("type", "")
    dataset_params = dataset_settings_dict.get("params", {})
    return set_table_variables(connection_type, dataset_params)


# Check if all connection types are included here !!!
def set_table_variables(connection_type, dataset_params):
    custom_variables = dataiku.get_custom_variables()
    table_name = dataset_params.get("table", "")

    if connection_type == "Snowflake":
        schema = dataset_params.get("schema", "")
        replacement = {
            "${TENANT}": custom_variables.get("TENANT", ""),
            "${NODE}": custom_variables.get("NODE", ""),
            "${projectKey}": custom_variables.get("projectKey", ""),
        }

        def replace_match(match):
            return replacement[match.group(0)]

        pattern = re.compile("|".join(re.escape(key) for key in replacement.keys()))
        table_name = pattern.sub(replace_match, table_name)
        table_path = f'"{table_name}"' if not schema else f'"{schema}"."{table_name}"'
        return table_path

    elif connection_type == "Databricks":
        schema = dataset_params.get("schema", "")
        replacement = {
            "${catalog}": custom_variables.get("catalog", ""),
            "${projectKey}": custom_variables.get("projectKey", ""),
        }

        def replace_match(match):
            return replacement[match.group(0)]

        pattern = re.compile("|".join(re.escape(key) for key in replacement.keys()))
        table_name = pattern.sub(replace_match, table_name)
        table_path = f"`{table_name}`" if not schema else f"`{schema}`.`{table_name}`"
        return table_path
    
    elif connection_type == "Redshift":
        replacement = {
            "${projectKey}": custom_variables.get("projectKey", ""),
        }

        def replace_match(match):
            return replacement[match.group(0)]

        pattern = re.compile("|".join(re.escape(key) for key in replacement.keys()))
        table_name = pattern.sub(replace_match, table_name)
    return table_name


def create_cdm_table_paths(key_map, script_cdm_table_names):
    cdm_table_map = {}
    
    # use standard OMOP table name if no key map provided
    for table in script_cdm_table_names:
        if key_map:
            cdm_table_map[key_map[table]] = get_sql_path(table)
        else:
            cdm_table_map[table] = get_sql_path(table)
    return cdm_table_map


def replace_sql_script_variables(sql_script, replacement):
    def replace_with_dictionary(match):
        return replacement[match.group(1).lower()]

    pattern = re.compile(
        r"(?<!\S)(" + "|".join(re.escape(key) for key in replacement.keys()) + r")\b", re.IGNORECASE
        ) 

    new_script = pattern.sub(replace_with_dictionary, sql_script)
    return new_script


def create_clear_temp_tables_script(sql_script):
    clear_temp_tables_script = ""

    pattern = re.compile(r"(DROP TABLE) (\W?\w*;)", re.IGNORECASE)
    for table_name in set(pattern.findall(sql_script)):
        clear_temp_tables_script += " IF EXISTS ".join(table_name)
        clear_temp_tables_script += "\n"
    return clear_temp_tables_script


def create_sql_script_scenario_step(connection_type, sql_script):    
    scenario_steps = [
        {'id': 'sql_null',
        'type': 'exec_sql',
        'name': 'Step #1',
        'enabled': True,
        'runConditionType': 'RUN_IF_STATUS_MATCH',
        'runConditionStatuses': ['SUCCESS', 'WARNING'],
        'runConditionExpression': '',
        'resetScenarioStatus': False,
        'delayBetweenRetries': 10,
        'maxRetriesOnFail': 0,
        'params': {'connection': connection_type,
        'sql': sql_script,
        'overrideDefaultLimit': False,
        'extraConf': [],
        'proceedOnFailure': False}}]
    return scenario_steps


def validate_cdm_tables(script_cdm_table_names, project, cohort_info=None):
    """Validate that all required CDM tables exist in the project.
    
    Args:
        script_cdm_table_names (list): List of CDM table names to validate
        project (DSSProject): Dataiku project object
        cohort_info (dict, optional): Dictionary containing cohort information with keys 'id' and 'name'
    
    Raises:
        ValueError: If no tables are mapped or if required tables are missing
    """
    logger.info(f"Validating {len(script_cdm_table_names)} CDM tables for cohort {cohort_info['id'] if cohort_info else 'unknown'}")
    
    if not script_cdm_table_names:
        error_msg = "No OMOP tables were mapped from the script! Please verify the OMOP table names from your scripts and adjust the setting in the previous step, 'OMOP CDM Custom Table Name Mapping,' accordingly."
        if cohort_info:
            error_msg = f"Cohort {cohort_info['id']} ({cohort_info['name']}): {error_msg}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    required_input_cdm_table_missing = set(script_cdm_table_names).difference(set(get_all_project_dataset_names(project)))
    if required_input_cdm_table_missing:
        required_input_cdm_table_missing_string = ', '.join(required_input_cdm_table_missing)
        error_msg = f"Expecting input OMOP table(s) '{required_input_cdm_table_missing_string}' for cohort script! Please add all required OMOP CDM tables to the Connect OMOP Common Data Model Standard Tables section"
        if cohort_info:
            error_msg = f"Cohort {cohort_info['id']} ({cohort_info['name']}): {error_msg}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info(f"All required CDM tables are present for cohort {cohort_info['id'] if cohort_info else 'unknown'}")
