OMOP_CDM_KEYS = [
    'person', 'observation_period', 'visit_occurrence', 'visit_detail', 'condition_occurrence', 
    'drug_exposure', 'procedure_occurrence', 'device_exposure', 'measurement', 'observation', 
    'death', 'note', 'note_nlp', 'specimen', 'fact_relationship', 'location', 'care_site', 
    'provider', 'payer_plan_period', 'cost', 'drug_era', 'dose_era', 'condition_era', 'episode', 
    'episode_event', 'metadata', 'cdm_source', 'concept', 'vocabulary', 'domain', 'concept_class', 
    'concept_relationship', 'relationship', 'concept_synonym', 'concept_ancestor', 
    'source_to_concept_map', 'drug_strength'
    ]

OMOP_RESULTS_SCHEMA_KEYS = ["cohort", "cohort_definition"]

MANDATORY_TABLES = [
    "person", "observation_period", "visit_occurrence", "condition_occurrence", "drug_exposure",
    "death", "location", "condition_era"]

MANDATORY_VOCABULARY = ["concept_ancestor", "concept"]

SNOWFLAKE_COHORT_INIT_SCRIPT = """            
CREATE TABLE IF NOT EXISTS @cohort (
			cohort_definition_id integer NOT NULL,
			subject_id integer NOT NULL,
			cohort_start_date date NOT NULL,
			cohort_end_date date NOT NULL );
"""


SNOWFLAKE_COHORT_DEFINITAION_SCRIPT = """
CREATE TABLE IF NOT EXISTS @cohort_definition (
            cohort_definition_id integer NOT NULL,
            cohort_definition_name varchar(255) NOT NULL,
            cohort_definition_description TEXT NULL,
            definition_type_concept_id integer NOT NULL,
            cohort_definition_syntax TEXT NULL,
            subject_concept_id integer NOT NULL,
            cohort_initiation_date date NULL );

DROP TABLE IF EXISTS @uploaded_cohort_definition ;
CREATE TABLE @uploaded_cohort_definition (
            cohort_definition_id integer NOT NULL,
            cohort_definition_name varchar(255) NOT NULL,
            cohort_definition_description TEXT NULL,
            cohort_input_tables varchar(255) NOT NULL,
            original_script_filename varchar(255) NOT NULL );
        

DELETE FROM @cohort_definition where cohort_definition_id IN ( @cohort_ids );
INSERT INTO @cohort_definition
(cohort_definition_id, cohort_definition_name, cohort_definition_description, definition_type_concept_id, cohort_definition_syntax, subject_concept_id, cohort_initiation_date)
VALUES
@row_values ;

INSERT INTO @uploaded_cohort_definition
(cohort_definition_id, cohort_definition_name, cohort_definition_description, cohort_input_tables, original_script_filename)
VALUES
@uploaded_row_values ;
"""

SNOWFLAKE_COHORT_LOG_SCRIPT = """
CREATE TABLE IF NOT EXISTS @cohort_building_log (
            run_timestamp varchar(255) NOT NULL,
            cohort_definition_id integer NOT NULL,
            cohort_definition_name varchar(255) NOT NULL,
            cohort_count integer NOT NULL,
            status varchar(255) NOT NULL,
            error TEXT NULL,
            original_script_filename varchar(255) NOT NULL);

INSERT INTO @cohort_building_log
(run_timestamp, cohort_definition_id, cohort_definition_name, cohort_count, status, error, original_script_filename)
VALUES
@cohort_log ;
"""

REDSHIFT_COHORT_DEFINITAION_SCRIPT = """
CREATE TABLE IF NOT EXISTS @cohort_definition (
            cohort_definition_id integer NOT NULL,
            cohort_definition_name varchar(255) NOT NULL,
            cohort_definition_description VARCHAR(MAX) NULL,
            definition_type_concept_id integer NOT NULL,
            cohort_definition_syntax VARCHAR(MAX) NULL,
            subject_concept_id integer NOT NULL,
            cohort_initiation_date date NULL );

DROP TABLE IF EXISTS @uploaded_cohort_definition ;
CREATE TABLE @uploaded_cohort_definition (
            cohort_definition_id integer NOT NULL,
            cohort_definition_name varchar(255) NOT NULL,
            cohort_definition_description VARCHAR(MAX) NULL,
            cohort_input_tables VARCHAR(MAX) NOT NULL,
            original_script_filename varchar(255) NOT NULL );
        

DELETE FROM @cohort_definition where cohort_definition_id IN ( @cohort_ids );
INSERT INTO @cohort_definition
(cohort_definition_id, cohort_definition_name, cohort_definition_description, definition_type_concept_id, cohort_definition_syntax, subject_concept_id, cohort_initiation_date)
VALUES
@row_values ;

INSERT INTO @uploaded_cohort_definition
(cohort_definition_id, cohort_definition_name, cohort_definition_description, cohort_input_tables, original_script_filename)
VALUES
@uploaded_row_values ;
"""

REDSHIFT_COHORT_LOG_SCRIPT = """
CREATE TABLE IF NOT EXISTS @cohort_building_log (
            run_timestamp varchar(255) NOT NULL,
            cohort_definition_id integer NOT NULL,
            cohort_definition_name varchar(255) NOT NULL,
            cohort_count integer NOT NULL,
            status varchar(255) NOT NULL,
            error VARCHAR(MAX) NULL,
            original_script_filename varchar(255) NOT NULL);

INSERT INTO @cohort_building_log
(run_timestamp, cohort_definition_id, cohort_definition_name, cohort_count, status, error, original_script_filename)
VALUES
@cohort_log ;
"""

DATABRICKS_COHORT_INIT_SCRIPT = """            
CREATE TABLE IF NOT EXISTS @cohort (
			`COHORT_DEFINITION_ID` INT NOT NULL,
			`SUBJECT_ID` INT NOT NULL,
			`COHORT_START_DATE` DATE NOT NULL,
			`COHORT_END_DATE` DATE NOT NULL );
"""


DATABRICKS_COHORT_DEFINITAION_SCRIPT = """
CREATE TABLE IF NOT EXISTS @cohort_definition (
            `COHORT_DEFINITION_ID` INT NOT NULL,
            `COHORT_DEFINITION_NAME` STRING NOT NULL,
            `COHORT_DEFINITION_DESCRIPTION` STRING,
            `DEFINITION_TYPE_CONCEPT_ID` INT NOT NULL,
            `COHORT_DEFINITION_SYNTAX` STRING,
            `SUBJECT_CONCEPT_ID` INT NOT NULL,
            `COHORT_INITIATION_DATE` DATE );

DROP TABLE IF EXISTS @uploaded_cohort_definition ;
CREATE TABLE @uploaded_cohort_definition (
            `COHORT_DEFINITION_ID` INT NOT NULL,
            `COHORT_DEFINITION_NAME` STRING NOT NULL,
            `COHORT_DEFINITION_DESCRIPTION` STRING,
            `COHORT_INPUT_TABLES` STRING NOT NULL,
            `ORIGINAL_SCRIPT_FILENAME` STRING NOT NULL );
        

DELETE FROM @cohort_definition where `COHORT_DEFINITION_ID` IN ( @cohort_ids );
INSERT INTO @cohort_definition
(`COHORT_DEFINITION_ID`, `COHORT_DEFINITION_NAME`, `COHORT_DEFINITION_DESCRIPTION`, `DEFINITION_TYPE_CONCEPT_ID`, `COHORT_DEFINITION_SYNTAX`, `SUBJECT_CONCEPT_ID`, `COHORT_INITIATION_DATE`)
VALUES
@row_values ;

INSERT INTO @uploaded_cohort_definition
(`COHORT_DEFINITION_ID`, `COHORT_DEFINITION_NAME`, `COHORT_DEFINITION_DESCRIPTION`, `COHORT_INPUT_TABLES`, `ORIGINAL_SCRIPT_FILENAME`)
VALUES
@uploaded_row_values ;
"""

DATABRICKS_COHORT_LOG_SCRIPT = """
CREATE TABLE IF NOT EXISTS @cohort_building_log (
            run_timestamp STRING NOT NULL,
            cohort_definition_id INT NOT NULL,
            cohort_definition_name STRING NOT NULL,
            cohort_count INT NOT NULL,
            status STRING NOT NULL,
            error STRING,
            original_script_filename varchar(255) NOT NULL);

INSERT INTO @cohort_building_log
(run_timestamp, cohort_definition_id, cohort_definition_name, cohort_count, status, error, original_script_filename)
VALUES
@cohort_log ;
"""


SQL_SCRIPT = {
    "Snowflake": {
        "cohort_init_script": SNOWFLAKE_COHORT_INIT_SCRIPT,
        "cohort_definition_script": SNOWFLAKE_COHORT_DEFINITAION_SCRIPT,
        "cohort_log_script": SNOWFLAKE_COHORT_LOG_SCRIPT
    },
    "Redshift": {
        "cohort_init_script": SNOWFLAKE_COHORT_INIT_SCRIPT, #same syntax
        "cohort_definition_script": REDSHIFT_COHORT_DEFINITAION_SCRIPT,
        "cohort_log_script": REDSHIFT_COHORT_LOG_SCRIPT
    },
    "Databricks": {
        "cohort_init_script": DATABRICKS_COHORT_INIT_SCRIPT,
        "cohort_definition_script": DATABRICKS_COHORT_DEFINITAION_SCRIPT,
        "cohort_log_script": DATABRICKS_COHORT_LOG_SCRIPT
    }
}
