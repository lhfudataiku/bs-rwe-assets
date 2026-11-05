import logging
from typing import Dict, List, Set, Tuple

from dku_utils.projects.project_commons import get_current_project_and_variables, get_project_and_variables
from dku_utils.projects.datasets.dataset_commons import get_dataset_schema
from solution.schema.cdm_schema import CDM_SCHEMA
from solution.variables import MANDATORY_TABLES, MANDATORY_VOCABULARY

# Setup logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def _normalize_data_type(data_type: str) -> str:
    """Normalize data types to handle variations."""
    if data_type == 'bigint':
        return 'int'
    if data_type == 'double':
        return 'float'
    return data_type

def _get_imported_schema(source_project, imported_table_name: str, optional_schema: Dict[str, str]) -> Tuple[Set[Tuple[str, str]], List[Tuple[str, str]]]:
    """Get schema from imported dataset and check optional column datatypes."""
    schema_from_import = set()
    optional_datatype_error = []
    
    for col in get_dataset_schema(source_project, imported_table_name):
        col_name = col.get('name').lower()
        data_type = _normalize_data_type(col.get('type'))
        schema_from_import.add((col_name, data_type))
        
        # Check optional column datatype
        optional_col_datatype = optional_schema.get(col_name)
        if optional_col_datatype and data_type != optional_col_datatype:
            optional_datatype_error.append((col_name, optional_col_datatype))
            
    return schema_from_import, optional_datatype_error

def _check_table_schema(dataset: str, imported_table_name: str, source_project, 
                       required_schema: Set[Tuple[str, str]], optional_schema: Dict[str, str],
                       new_data_prep_project_key: str) -> Tuple[str, str]:
    """Check schema for a single table."""
    error_message = ""
    optional_column_error_message = ""
    
    # Validate imported table name
    if not imported_table_name:
        raise ValueError(f"Expecting OMOP table '{dataset}' for import! All OMOP tables displayed in the Connect OMOP Common Data Model Standard Tables section require a source dataset.")
    
    # Get and check schema
    schema_from_import, optional_datatype_error = _get_imported_schema(source_project, imported_table_name, optional_schema)
    
    # Check required columns
    required_columns_mismatched = required_schema.difference(schema_from_import)
    if required_columns_mismatched:
        error_message += (f"Required column(s) missing or mismatched in import dataset '{imported_table_name}' "
                         f"from Project '{new_data_prep_project_key}'!! Expect column(s) '{required_columns_mismatched}' "
                         f"for CDM Table '{dataset}'. \n")
    
    # Check optional columns
    if optional_datatype_error:
        optional_column_error_message += (f"Optional column datatype error in import dataset '{imported_table_name}' "
                                        f"from Project '{new_data_prep_project_key}'!! Expect column(s) "
                                        f"'{optional_datatype_error}' for CDM Table '{dataset}'. \n")
    
    return error_message, optional_column_error_message

def check_omop_schemas() -> None:
    """Main function to check OMOP schemas."""
    project, variables = get_current_project_and_variables()
    new_data_prep_project_key = variables['local']['data_preparation_project_key']
    
    # Load selected datasets
    datasets_included = list(set(MANDATORY_TABLES + variables['local']['omop_cdm_standard_tables_import']))
    vocabulary_included = list(set(MANDATORY_VOCABULARY + variables['local']['omop_standardised_vocabulary_tables_import']))
    
    omop_tables = {'standard_tables': datasets_included, 'standard_vocabulary': vocabulary_included}
    source_project, _ = get_project_and_variables(new_data_prep_project_key)
    
    error_message = ""
    optional_column_error_message = ""
    has_errors = False
    
    try:
        for category, tables in omop_tables.items():
            for dataset in tables:
                # Get required and optional schemas
                required_schema = set([t[:2] for t in CDM_SCHEMA[dataset] if t[2]])
                optional_schema = {t[0]: t[1] for t in CDM_SCHEMA[dataset] if not t[2]}
                
                imported_table_name = variables['local'].get(dataset, "")
                
                # Check schema for this table
                table_error, table_optional_error = _check_table_schema(
                    dataset, imported_table_name, source_project,
                    required_schema, optional_schema, new_data_prep_project_key
                )
                
                error_message += table_error
                optional_column_error_message += table_optional_error
                
                if table_error or table_optional_error:
                    has_errors = True
                    
    except Exception as e:
        logger.error(f"Error during schema validation: {str(e)}", exc_info=True)
        has_errors = True
        error_message += f"Unexpected error during schema validation: {str(e)}\n"
    
    if error_message:
        raise ValueError(error_message)
    if optional_column_error_message:
        raise ValueError(optional_column_error_message)
    
    if has_errors:
        raise Exception("Schema validation completed with one or more errors. Check logs above for details.")
    
    logger.info("Schema validation completed successfully.")

if __name__ == "__main__":
    check_omop_schemas()
