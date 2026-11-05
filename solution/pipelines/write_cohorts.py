import dataiku
from dataiku import SQLExecutor2
import time
import logging

from dku_utils.projects.project_commons import get_current_project_and_variables, get_all_project_recipe_names
from dku_utils.projects.recipes.sql_recipes import set_sql_recipe_inputs, set_sql_recipe_script, instantiate_sql_recipe
from dku_utils.projects.scenarios.scenario_commons import set_scenario_steps
from dku_utils.projects.datasets.dataset_commons import get_dataset_settings_and_dictionary

from solution.recipes.sql_script_function import (
    create_cohort_log_script, 
    get_sql_path, 
    create_clear_temp_tables_script, 
    create_sql_script_scenario_step,
    validate_cdm_tables
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_cohort_recipe(project, recipe_name, input_cdm_table_names, script, main_connection):
    """Set up the cohort creation recipe with inputs and script."""
    logger.info(f"Setting up cohort recipe: {recipe_name}")
    if recipe_name not in get_all_project_recipe_names(project):
        logger.info(f"Creating new SQL recipe: {recipe_name}")
        instantiate_sql_recipe(project, recipe_name, "sql_script", "person", "cohort", main_connection)
    
    set_sql_recipe_inputs(project, recipe_name, input_cdm_table_names)
    set_sql_recipe_script(project, recipe_name, script)
    logger.info("Cohort recipe setup completed")

def clear_temp_tables(project, script, main_connection):
    """Clear temporary tables using a scenario."""
    logger.info("Clearing temporary tables")
    clear_temp_tables_script = create_clear_temp_tables_script(script)
    scenario_step = create_sql_script_scenario_step(main_connection, clear_temp_tables_script)
    
    scenario_id = "DROPSQLTEMPORARYTABLES"
    set_scenario_steps(project, scenario_id, scenario_step)
    
    scenario = project.get_scenario(scenario_id)
    trigger_fire = scenario.run()
    scenario_run = trigger_fire.wait_for_scenario_run()
    
    while True:
        scenario_run.refresh()
        if scenario_run.running:
            logger.info("Scenario Drop Temp Tables is still running ...")
        else:
            logger.info("Scenario Drop Temp Tables is not running anymore")
            break
        time.sleep(5)

def build_cohort_dataset(project, cohort_definition_id):
    """Build the cohort dataset using a scenario."""
    logger.info(f"Building cohort dataset for cohort #{cohort_definition_id}")
    scenario = project.get_scenario("WRITECOHORTDATA")
    trigger_fire = scenario.run()
    scenario_run = trigger_fire.wait_for_scenario_run()
    
    while True:
        scenario_run.refresh()
        if scenario_run.running:
            logger.info("Scenario is still running ...")
        else:
            logger.info("Scenario is not running anymore")
            return process_scenario_result(scenario, cohort_definition_id)
        time.sleep(5)

def process_scenario_result(scenario, cohort_definition_id):
    """Process the scenario result and collect error messages if any."""
    scenario_details = scenario.get_last_finished_run().get_details()
    scenario_timestamp = scenario_details['scenarioRun']['runId']
    scenario_result = scenario_details['scenarioRun']['result']['outcome']
    message = []
    
    if scenario_result != "SUCCESS":
        logger.warning(f"Cohort #{cohort_definition_id} warning message. Please review cohort building log file for more detail!")
        
        for step in scenario_details['stepRuns']:
            for report in step['additionalReportItems']:
                if 'thrown' in report.keys():
                    error_message = report['thrown'].get('message').replace('\n', ' ').replace("'", '"')
                    message.append(error_message)
        
        if len(message) > 1:
            message = ";  ".join(message)
        else:
            message = message[0] if message else ""
        
        if len(message) > 1000:
            message = message[:1000] + "..."
    else:
        logger.info(f"Cohort #{cohort_definition_id} written to cohort table!")
    
    return scenario_timestamp, scenario_result, message

def get_cohort_row_count(project, main_connection, cohort_definition_id, connection_type):
    """Get the row count for a specific cohort."""
    logger.info(f"Getting row count for cohort #{cohort_definition_id}")
    executor = SQLExecutor2(connection=main_connection)
    if project.get_dataset("cohort").exists():
        cohort_table = get_sql_path('cohort')
        df = executor.query_to_df(f"""
        SELECT COUNT(subject_id) AS COHORT_COUNT
        FROM {cohort_table}
        WHERE cohort_definition_id = {cohort_definition_id}
        """)
        cohort_count_colname = "cohort_count" if connection_type == "Redshift" else "COHORT_COUNT"
        return df[cohort_count_colname].values[0]
    return 0

def setup_log_recipe(project, log_recipe_name, main_connection):
    """Set up the logging recipe."""
    logger.info(f"Setting up log recipe: {log_recipe_name}")
    if log_recipe_name not in get_all_project_recipe_names(project):
        instantiate_sql_recipe(project, log_recipe_name, "sql_script", "cohort_metadata_copy", "cohort_building_log", main_connection)
        set_sql_recipe_inputs(project, log_recipe_name, [])
    logger.info("Log recipe setup completed")

def write_cohorts():
    """Main function to write cohorts and create logs."""
    logger.info("Starting cohort writing process")
    try:
        # Initialize project and variables
        project, variables = get_current_project_and_variables()
        main_connection = variables['local']['main_connection']
        
        # Get dataset settings
        _, dataset_settings_dict = get_dataset_settings_and_dictionary(project, "cohort_metadata_copy")
        connection_type = dataset_settings_dict.get("type", "")
        
        # Reset cohort build error
        project.update_variables({'cohort_build_error': 0}, type='local')
        
        # Initialize folders and datasets
        handle = dataiku.Folder("lMM00YKr")
        uploaded_cohort_definition_df = project.get_dataset("uploaded_cohort_definition")
        
        # Setup log recipe
        log_recipe_name = "compute_cohort_building_log"
        setup_log_recipe(project, log_recipe_name, main_connection)
        
        cohort_logs = []
        recipe_name = 'create_cohort'
        error_messages=[]
        
        for row in uploaded_cohort_definition_df.iter_rows():
            cohort_definition_id = row[0]
            cohort_definition_name = row[1]
            mapped_script_filename = f"cohort_{cohort_definition_id}"
            input_cdm_table_names = row[3].split("|")
            original_script_filename = row[4]
            
            logger.info(f"Processing cohort #{cohort_definition_id}...")
            
            # Validate input tables using the combined function
            cohort_info = {'id': cohort_definition_id, 'name': cohort_definition_name}
            validate_cdm_tables(input_cdm_table_names, project, cohort_info)
            
            # Read and process script
            with handle.get_download_stream(mapped_script_filename) as f:
                data = f.read()
                script = data.decode('utf-8')
            
            # Setup cohort recipe
            setup_cohort_recipe(project, recipe_name, input_cdm_table_names, script, main_connection)
            
            # Clear temp tables
            clear_temp_tables(project, script, main_connection)
            
            # Build cohort dataset
            scenario_timestamp, scenario_result, message = build_cohort_dataset(project, cohort_definition_id)
            
            # Get cohort row count
            cohort_row_count = get_cohort_row_count(project, main_connection, cohort_definition_id, connection_type)
            
            # Add to logs
            log_values = [
                scenario_timestamp,
                cohort_definition_id,
                cohort_definition_name,
                cohort_row_count,
                scenario_result,
                message,
                original_script_filename
            ]
            cohort_logs.append("(" + ", ".join(f"'{str(v)}'" for v in log_values) + ")")
            logger.info(f"Cohort #{cohort_definition_id} logged")
        
            if scenario_result != "SUCCESS":
                error_messages.append(f"Cohort {cohort_definition_id} ({cohort_definition_name}): {message}")
        # Write cohort building log
        log_script = create_cohort_log_script(cohort_logs)
        set_sql_recipe_script(project, log_recipe_name, log_script)
        
        logger.info("Cohort writing process completed")
        if error_messages:
            error_msg = (
                "Cohort building failed for the following cohorts:\n\n"
                "Details by cohort:\n" + "\n".join(error_messages) + "\n\n"
                "Please review cohort_building_log_history for more info"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
    except Exception as e:
        logger.error(f"Error in cohort writing process: {str(e)}")
        raise

if __name__ == "__main__":
    write_cohorts()
