import re
import logging

import dataiku
from dku_utils.projects.project_commons import get_current_project_and_variables, get_all_project_dataset_names
from dku_utils.projects.datasets.dataset_commons import (
    get_dataset_settings_and_dictionary,
)

from solution.variables import OMOP_CDM_KEYS, SQL_SCRIPT

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
    # Atlas temporary tables (@temp_database_schema.<name>) stay as placeholders: build_cohorts renders
    # them per dialect at run time (R6).
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



def cohort_connection_type():
    """Connection type of the `cohort` dataset, which sits on the project's main connection."""
    _, dataset_settings_dict = get_dataset_settings_and_dictionary(PROJECT, "cohort")
    return dataset_settings_dict.get("type", "")


def get_script_by_connection_type(script_name):
    return SQL_SCRIPT[cohort_connection_type()][script_name]


def create_cdm_table_map(key_map):
    cdm_standard_table = {}
    for k, v in key_map.items():
        if k in OMOP_KEYS and v:
            cdm_standard_table[v] = k
    return cdm_standard_table



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
    """Return the table's SQL name exactly as DSS writes it in its own recipes.

    DSS resolves the catalog or database, the schema, variables such as ${projectKey} and the
    quoting of each dialect (spike 2026-11-20, solution-revision-plan.md R4). Works in recipes that do
    not declare the dataset as an input or output. Only the connection
    types in SQL_SCRIPT are supported; any other raises before SQL is built.
    """
    _, dataset_settings_dict = get_dataset_settings_and_dictionary(PROJECT, table)
    connection_type = dataset_settings_dict.get("type", "")
    if connection_type not in SQL_SCRIPT:
        raise ValueError(
            f"Dataset '{table}' is on a {connection_type or 'unknown'} connection; the solution supports "
            f"{', '.join(sorted(SQL_SCRIPT))}. Run 'Reconfigure' in Project Setup on a supported connection."
        )
    # ignore_flow: the mapping runs inside a Python recipe that does not declare the CDM and cohort
    # tables, and dataiku.Dataset refuses undeclared datasets there (E4 rerun, 2026-11-23).
    info = dataiku.Dataset(table, ignore_flow=True).get_location_info().get("info", {})
    table_path = info.get("quotedResolvedTableName")
    if not table_path:
        raise ValueError(f"DSS returned no resolved table name for dataset '{table}' ({connection_type})")
    return table_path


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
        error_msg = ("No OMOP table was found in the script. Check that 'Cohort script table naming' in "
                     "Project Setup matches how the script names OMOP tables.")
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
