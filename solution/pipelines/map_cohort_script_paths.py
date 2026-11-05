import dataiku
import json
import logging

from dku_utils.projects.project_commons import get_current_project_and_variables, get_all_project_recipe_names
from dku_utils.projects.recipes.sql_recipes import instantiate_sql_recipe, set_sql_recipe_script, set_sql_recipe_outputs
from dku_utils.projects.datasets.dataset_commons import get_dataset_settings_and_dictionary

from solution.recipes.sql_script_function import (
    return_script_cdm_tables, 
    create_cohort_sql_script, 
    create_cohort_definition_table_script,
    validate_cdm_tables
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_key_map(map_handle, key_map_name):
    """Load the key mapping JSON file."""
    logger.info(f"Loading key map from {key_map_name}")
    if not key_map_name:
        logger.warning("No key map name provided, returning empty dictionary")
        return {}
    
    if ".json" not in key_map_name:
        key_map_name += ".json"
        
    try:
        with map_handle.get_download_stream(key_map_name) as m:
            data = m.read()
            key_map = json.loads(data.decode('utf-8'))
            logger.info(f"Successfully loaded key map with {len(key_map)} entries")
            return key_map
    except Exception as e:
        logger.error(f"Failed to load key map: {str(e)}")
        raise

def process_cohort_metadata(metadata, handle, output, key_map, project):
    """Process cohort metadata and create corresponding SQL scripts."""
    logger.info("Starting cohort metadata processing")
    cohort_ids = []
    row_values = []
    uploaded_row_values = []
    missing_tables_by_cohort = {}
    
    for row in metadata.iter_rows():    
        cohort_definition_id = row['cohort_definition_id']
        cohort_name = row['cohort_definition_name']
        cohort_description = row['cohort_definition_description']
        filename = row['cohort_sql_script_filename']
        
        logger.info(f"Processing cohort {cohort_definition_id}: {cohort_name}")
        cohort_info = {'id': cohort_definition_id, 'name': cohort_name}
        
        # Process script
        try:
            with handle.get_download_stream(filename) as f:
                data = f.read()
                script = data.decode('utf-8')
                script_cdm_table_names = return_script_cdm_tables(script, key_map)
                input_cdm_table_names = [table for table in script_cdm_table_names if table != 'cohort']
                
                try:
                    validate_cdm_tables(input_cdm_table_names, project, cohort_info)
                except ValueError as e:
                    missing_tables_by_cohort[cohort_definition_id] = {
                        'name': cohort_name,
                        'error': str(e)
                    }
                    logger.error(f"Validation failed for cohort {cohort_definition_id}: {str(e)}")
                    continue
                
                new_script = create_cohort_sql_script(script, script_cdm_table_names, cohort_definition_id, key_map)
                logger.info(f"Cohort script #{cohort_definition_id} mapped to table paths")
            
            # Save processed script
            output_filename = f"cohort_{cohort_definition_id}"
            output.upload_data(output_filename, new_script.encode('utf-8'))
            logger.info(f"Mapped cohort script #{cohort_definition_id} saved to folder")
            
            # Collect metadata
            input_cdm_table = "|".join(set(input_cdm_table_names))
            cohort_ids.append(cohort_definition_id)
            
            # Get timestamp based on connection type
            timestamp = "GETDATE()" if connection_type == "Redshift" else "CURRENT_TIMESTAMP()"
            
            row_values.append(f"({cohort_definition_id}, '{cohort_name}', '{cohort_description}', 0, '', 0, {timestamp})")
            uploaded_row_values.append(f"({cohort_definition_id}, '{cohort_name}', '{cohort_description}','{input_cdm_table}','{filename}')")
            
        except Exception as e:
            error_msg = f'Error processing script: {str(e)}'
            logger.error(f"Error processing cohort {cohort_definition_id}: {error_msg}")
            missing_tables_by_cohort[cohort_definition_id] = {
                'name': cohort_name,
                'error': error_msg
            }
    
    # If there are any missing tables, raise an error with detailed information
    if missing_tables_by_cohort:
        error_messages = []
        for cohort_id, info in missing_tables_by_cohort.items():
            error_messages.append(f"Cohort {cohort_id} ({info['name']}): {info['error']}")
        
        error_msg = (
            "Missing required OMOP tables across cohorts:\n\n"
            "Details by cohort:\n" + "\n".join(error_messages)
        )
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info(f"Successfully processed {len(cohort_ids)} cohorts")
    return cohort_ids, row_values, uploaded_row_values

def setup_sql_recipe(project, recipe_name, cohort_definition_script, main_connection):
    """Set up the SQL recipe for cohort definition."""
    logger.info(f"Setting up SQL recipe: {recipe_name}")
    project_recipes = get_all_project_recipe_names(project)
    if recipe_name not in project_recipes:
        logger.info(f"Creating new SQL recipe: {recipe_name}")
        instantiate_sql_recipe(project, recipe_name, "sql_script", "cohort_metadata_copy", "cohort_definition", main_connection)
        set_sql_recipe_outputs(project, recipe_name, ["cohort_definition", "uploaded_cohort_definition"])
    set_sql_recipe_script(project, recipe_name, cohort_definition_script)
    logger.info(f"SQL recipe {recipe_name} setup completed")

def map_cohort_script_paths():
    """Main function to map cohort paths and set up SQL recipes."""
    logger.info("Starting cohort path mapping process")
    try:
        # Initialize project and variables
        project, variables = get_current_project_and_variables()
        main_connection = variables['local']['main_connection']
        logger.info(f"Initialized project with main connection: {main_connection}")
        
        # Get dataset settings
        _, dataset_settings_dict = get_dataset_settings_and_dictionary(project, "cohort_metadata_copy")
        global connection_type
        connection_type = dataset_settings_dict.get("type", "")
        logger.info(f"Connection type: {connection_type}")
        
        # Initialize folders and datasets
        metadata = dataiku.Dataset("cohort_metadata_copy")
        handle = dataiku.Folder("PqOBn6B3")
        map_handle = dataiku.Folder("4ktqvA1F")
        output = dataiku.Folder("lMM00YKr")
        logger.info("Initialized all required folders and datasets")
        
        # Load key map
        key_map_name = variables['local']['cdm_standard_tables_map']
        key_map = load_key_map(map_handle, key_map_name)
        
        # Process cohort metadata
        cohort_ids, row_values, uploaded_row_values = process_cohort_metadata(
            metadata, handle, output, key_map, project
        )
        
        # Create cohort definition script
        cohort_definition_script = create_cohort_definition_table_script(
            cohort_ids, row_values, uploaded_row_values
        )
        
        # Set up SQL recipe
        recipe_name = "compute_cohort_definition"
        setup_sql_recipe(project, recipe_name, cohort_definition_script, main_connection)
        
        logger.info("Cohort path mapping process completed successfully")
        
    except Exception as e:
        logger.error(f"Error in cohort path mapping process: {str(e)}")
        raise

if __name__ == "__main__":
    map_cohort_script_paths()
