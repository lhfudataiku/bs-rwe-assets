import dataiku
from dataiku import pandasutils as pdu
import pandas as pd
import logging

from dku_utils.projects.project_commons import get_current_project_and_variables, get_all_project_dataset_names, get_all_project_recipe_names
from dku_utils.projects.recipes.recipe_commons import get_recipe_input_datasets, set_recipe_input_datasets
from dku_utils.projects.recipes.prepare_recipe import instantiate_prepare_recipe, reset_prepare_recipe_steps
from dku_utils.projects.security.sharing import share_object_with_name, unshare_object_with_name
from dku_utils.projects.flow_graph.flow_zones import move_dataset_in_flow_zone
from dku_utils.projects.datasets.dataset_commons import get_dataset_schema, set_dataset_schema
from dku_utils.type_checking import check_project_key_exists

from solution.variables import OMOP_CDM_KEYS, MANDATORY_TABLES, MANDATORY_VOCABULARY

# Constants
OBJECT_TYPE_DATASET = "DATASET"
FLOW_ZONE_STANDARD_TABLE = "OMOP CDM Standard Table"
FLOW_ZONE_VOCABULARY = "OMOP Standardised Vocabulary"

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _get_source_dataset_details(data_prep_project, dataset_source_name_in_prep):
    """Gets schema and FQN for a source dataset."""
    source_dataset_schema = get_dataset_schema(data_prep_project, dataset_source_name_in_prep)
    source_dataset_fqn = f"{data_prep_project.project_key}.{dataset_source_name_in_prep}"
    return source_dataset_schema, source_dataset_fqn

def _transform_schema(source_schema):
    """Uppercases column names, normalizes types, and returns the renamings the prepare recipe must apply.

    Every column whose name is not already uppercase is renamed, mixed case included: a column such
    as 'Person_Id' must not be declared as PERSON_ID in the schema while its data keeps the old name.
    bigint becomes int and double becomes float, the ingestion types documented in the Data Model article.
    """
    new_schema = []
    renaming_steps_params = []
    for col_spec in source_schema:
        original_name = col_spec['name']
        transformed_col = col_spec.copy()
        transformed_col['name'] = original_name.upper()

        if original_name != transformed_col['name']:
            renaming_steps_params.append({'from': original_name, 'to': transformed_col['name']})

        data_type = transformed_col.get('type')
        if data_type == 'bigint':
            transformed_col['type'] = 'int'
        elif data_type == 'double':
            transformed_col['type'] = 'float'
        new_schema.append(transformed_col)
    return new_schema, renaming_steps_params

def _create_or_update_prepare_recipe(project, recipe_name, input_dataset_fqn, output_dataset_name,
                                   connection_name, existing_recipes_names, current_project_key, client):
    """Creates a new prepare recipe or updates an existing one."""
    recipe_updated = False
    if recipe_name in existing_recipes_names:
        logger.info(f"Recipe {recipe_name} already exists. Updating input.")
        old_input_fqns = get_recipe_input_datasets(project, recipe_name)

        set_recipe_input_datasets(project, recipe_name, [input_dataset_fqn])
        logger.info(f"Recipe {recipe_name} input dataset updated to {input_dataset_fqn}")
        recipe_updated = True

        if old_input_fqns and old_input_fqns[0] != input_dataset_fqn:
            remove_shared_dataset_from_project(client, old_input_fqns[0], current_project_key)
    else:
        instantiate_prepare_recipe(project, recipe_name, input_dataset_fqn, output_dataset_name, connection_name)
        logger.info(f"New recipe {recipe_name} created with input {input_dataset_fqn} and output {output_dataset_name}")
    return project.get_recipe(recipe_name), recipe_updated

def _configure_recipe_and_output_schema(project, recipe, output_dataset_name, source_dataset_schema):
    """Sets output dataset schema, configures recipe steps."""
    transformed_schema, renaming_params = _transform_schema(source_dataset_schema)
    set_dataset_schema(project, output_dataset_name, transformed_schema)
    logger.info(f"Schema for dataset {output_dataset_name} formatted.")

    reset_prepare_recipe_steps(project, recipe.name)
    recipe_settings = recipe.get_settings()
    if renaming_params:
        params = {'renamings': renaming_params}
        recipe_settings.add_processor_step("ColumnRenamer", params)
        logger.info(f"Added ColumnRenamer step to recipe {recipe.name}.")
    recipe_settings.save()

    required_updates = recipe.compute_schema_updates()
    if required_updates.any_action_required():
        logger.info(f"Schema updates required for recipe {recipe.name}. Applying.")
        required_updates.apply()
    else:
        logger.info(f"No schema updates required for recipe {recipe.name} after configuration.")

def _cleanup_unused_omop_assets(project, client, datasets_to_import, all_cdm_keys, 
                              current_project_datasets_names, current_project_recipe_names, current_project_key):
    """Removes datasets and recipes not in the datasets_to_import list."""
    cdm_datasets_not_included = set(all_cdm_keys).difference(set(datasets_to_import))
    logger.info(f"Cleaning up datasets not included: {cdm_datasets_not_included}")

    for dataset_name_to_remove in cdm_datasets_not_included:
        recipe_name_to_remove = f"format_{dataset_name_to_remove}"

        if recipe_name_to_remove in current_project_recipe_names:
            try:
                recipe_to_delete = project.get_recipe(recipe_name_to_remove)
                input_fqns_of_deleted_recipe = get_recipe_input_datasets(project, recipe_name_to_remove)

                recipe_to_delete.delete()
                logger.info(f"Recipe {recipe_name_to_remove} deleted.")
                current_project_recipe_names.remove(recipe_name_to_remove)

                if input_fqns_of_deleted_recipe:
                    remove_shared_dataset_from_project(client, input_fqns_of_deleted_recipe[0], current_project_key)

            except Exception as e:
                logger.warning(f"Error deleting recipe {recipe_name_to_remove}: {e}")

        if dataset_name_to_remove in current_project_datasets_names:
            try:
                dataset_to_delete = project.get_dataset(dataset_name_to_remove)
                dataset_to_delete.delete(drop_data=True)
                logger.info(f"Dataset {dataset_name_to_remove} dropped from project.")
                current_project_datasets_names.remove(dataset_name_to_remove)
            except Exception as e:
                logger.warning(f"Error deleting dataset {dataset_name_to_remove}: {e}")

def sync_omop_datasets():
    """Imports the selected OMOP tables from the data preparation project into this project.

    For each table, the source dataset is shared from the prep project and a `format_<table>` prepare
    recipe writes it to `main_connection` with every column name UPPERCASED. Source columns may use
    any case. The uppercase contract is required on Snowflake: Atlas cohort SQL and the solution's
    visual recipes reference columns unquoted (resolved as uppercase), so lowercase quoted columns
    would fail with "invalid identifier". bigint and double are normalized to int and float.

    Reads `data_preparation_project_key`, `main_connection` and the table variables from the local
    variable scope. Fails before changing anything if the prep project does not exist, and fails
    after building if any table could not be imported or built.
    """
    client = dataiku.api_client()
    project, variables = get_current_project_and_variables()
    current_project_key = project.project_key

    new_data_prep_project_key = variables['local']['data_preparation_project_key']
    connection_name = variables['local']['main_connection']

    datasets_included = list(set(MANDATORY_TABLES + variables['local']['omop_cdm_standard_tables_import']))
    vocabulary_included = list(set(MANDATORY_VOCABULARY + variables['local']['omop_standardised_vocabulary_tables_import']))

    omop_tables_config = {'standard_tables': datasets_included, 'standard_vocabulary': vocabulary_included}
    datasets_to_import_names = datasets_included + vocabulary_included

    has_errors = False

    # client.get_project() returns a handle without contacting DSS, so check existence explicitly,
    # before any share, recipe or build is touched.
    check_project_key_exists(new_data_prep_project_key)
    new_data_prep_project = client.get_project(new_data_prep_project_key)

    current_project_datasets_names = get_all_project_dataset_names(project)
    current_project_recipe_names = get_all_project_recipe_names(project)

    datasets_to_build = []

    for category, dataset_output_names_list in omop_tables_config.items():
        for target_output_dataset_name in dataset_output_names_list:
            logger.info(f"Processing dataset {target_output_dataset_name} in category {category}")

            source_dataset_name_in_prep = variables['local'][target_output_dataset_name]

            try:
                share_object_with_name(new_data_prep_project, source_dataset_name_in_prep, OBJECT_TYPE_DATASET, current_project_key, True)
                logger.info(f"Shared {source_dataset_name_in_prep} from {new_data_prep_project_key} with {current_project_key}")

                source_dataset_schema, source_dataset_fqn = _get_source_dataset_details(new_data_prep_project, source_dataset_name_in_prep)
                recipe_name = f"format_{target_output_dataset_name}"

                recipe_obj, updated = _create_or_update_prepare_recipe(
                    project, recipe_name, source_dataset_fqn, target_output_dataset_name,
                    connection_name, current_project_recipe_names, current_project_key, client
                )
                if not updated and recipe_name not in current_project_recipe_names:
                    current_project_recipe_names.append(recipe_name)
                if target_output_dataset_name not in current_project_datasets_names:
                    current_project_datasets_names.append(target_output_dataset_name)

                if not updated:
                    zone_name = FLOW_ZONE_STANDARD_TABLE if category == "standard_tables" else FLOW_ZONE_VOCABULARY
                    move_dataset_in_flow_zone(project, target_output_dataset_name, zone_name)
                    logger.info(f"Moved dataset {target_output_dataset_name} to flow zone {zone_name}")

                _configure_recipe_and_output_schema(project, recipe_obj, target_output_dataset_name, source_dataset_schema)
                datasets_to_build.append(target_output_dataset_name)

            except Exception as e:
                logger.error(f"Failed to process dataset {target_output_dataset_name}: {e}", exc_info=True)
                has_errors = True
                continue

    # Build every formatted dataset in one job and wait for it, so a failed build fails this step
    # and nothing downstream starts before the imports are complete.
    if datasets_to_build:
        try:
            job_builder = project.new_job("NON_RECURSIVE_FORCED_BUILD")
            for dataset_name in datasets_to_build:
                job_builder.with_output(dataset_name, object_type="DATASET")
            logger.info(f"Building {len(datasets_to_build)} datasets: {datasets_to_build}")
            job_builder.start_and_wait()
            logger.info("All OMOP datasets built.")
        except Exception as e:
            logger.error(f"Failed to build OMOP datasets: {e}", exc_info=True)
            has_errors = True

    # Cleanup
    _cleanup_unused_omop_assets(project, client, datasets_to_import_names, OMOP_CDM_KEYS,
                              current_project_datasets_names, current_project_recipe_names, current_project_key)

    logger.info("OMOP dataset synchronization process completed.")
    
    if has_errors:
        raise Exception("Main function completed with one or more errors. Check logs above for details.")

def remove_shared_dataset_from_project(client, previous_input_dataset_name, current_project_key):
    if not previous_input_dataset_name or '.' not in previous_input_dataset_name:
        logger.warning(f"Invalid dataset name for unsharing: {previous_input_dataset_name}")
        return
        
    old_data_prep_project_key, previous_input_dataset_name = previous_input_dataset_name.split(".")
    try:
        old_data_prep_project = client.get_project(old_data_prep_project_key)
        unshare_object_with_name(old_data_prep_project, previous_input_dataset_name, "DATASET", current_project_key)
        logger.info(f"Dataset {previous_input_dataset_name} from Project {old_data_prep_project_key} unshared!")
    except Exception as e:
        logger.warning(f"Error unsharing dataset {previous_input_dataset_name}: {str(e)}")
        pass

if __name__ == "__main__":
    sync_omop_datasets()
    