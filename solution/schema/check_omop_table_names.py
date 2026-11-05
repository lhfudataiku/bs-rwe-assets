import dataiku
import json
import logging
from typing import List

from dku_utils.projects.project_commons import get_current_project_and_variables

from solution.utils.folder_utils import get_folder_item_names, check_item_in_folder
from solution.variables import OMOP_CDM_KEYS, OMOP_RESULTS_SCHEMA_KEYS

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _normalize_key_map_name(key_map_name: str) -> str:
    """Normalize the key map file name by adding .json extension and / prefix if needed."""
    if ".json" not in key_map_name:
        key_map_name += ".json"
    if "/" not in key_map_name:
        key_map_name = '/' + key_map_name
    return key_map_name

def _load_key_map(folder_id: str, key_map_name: str) -> dict:
    """Load and parse the key map JSON file."""
    map_handle = dataiku.Folder(folder_id)
    with map_handle.get_download_stream(key_map_name) as m:
        data = m.read()
        return json.loads(data.decode('utf-8'))

def _get_omop_keys_v53() -> List[str]:
    """Get list of OMOP CDM v5.3 keys excluding certain tables."""
    OMOP_KEYS = OMOP_CDM_KEYS + OMOP_RESULTS_SCHEMA_KEYS
    excluded_tables = ['episode', 'episode_event', 'metadata', 'cdm_source', 'cohort_definition']
    return [key for key in OMOP_KEYS if key not in excluded_tables]

def check_omop_table_names() -> None:
    """Main function to check OMOP table names against the mapping file."""
    project, variables = get_current_project_and_variables()
    key_map_name = variables['local']['cdm_standard_tables_map']
    folder_id = "4ktqvA1F"
    
    has_errors = False
    error_message = ""
    
    try:
        if not key_map_name:
            raise ValueError("No key map name provided in variables")
            
        # Get folder items for error message
        folder_items = get_folder_item_names(project, folder_id)
        folder_item_names = ", ".join(folder_items)
        
        # Normalize and validate key map name
        key_map_name = _normalize_key_map_name(key_map_name)
        if not check_item_in_folder(project, folder_id, key_map_name):
            raise ValueError(f"Expecting an OMOP Table variables mapping file from '{folder_item_names}' but get '{key_map_name}'")
        
        # Load and validate key map
        key_map = _load_key_map(folder_id, key_map_name)
        omop_keys_v53 = _get_omop_keys_v53()
        
        # Check for missing tables
        omop_table_missing = set(omop_keys_v53).difference(set(key_map.keys()))
        if omop_table_missing:
            omop_table_missing_string = ', '.join(omop_table_missing)
            raise ValueError(f"Expecting OMOP table variable(s) '{omop_table_missing_string}' for mapping! "
                           f"Please verify all OMOP CDM and standardized vocabulary tables are included in "
                           f"the select OMOP CDM tables mapping file in the OMOP Common Data Model Table Mapping section.")
            
    except Exception as e:
        logger.error(f"Error during table name validation: {str(e)}", exc_info=True)
        has_errors = True
        error_message = str(e)
    
    if has_errors:
        raise Exception(f"Table name validation completed with errors: {error_message}")
    
    logger.info("Table name validation completed successfully.")

if __name__ == "__main__":
    check_omop_table_names() 