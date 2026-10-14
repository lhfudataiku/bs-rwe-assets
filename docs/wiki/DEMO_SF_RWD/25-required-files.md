The Solution requires other files for project setup. 

# OMOP CDM Table Name Mapping Json (optional)

This Solution requires an OMOP table name mapping json file if the cohort script(s) use custom table names other than the standard OMOP table names. This Solution pre-packaged a mapping json for cohort scripts exported from the Atlas web app. ([Example](https://atlas-demo.ohdsi.org/#/cohortdefinition/1770034/export))

The mapping file requires the following columns included by [OMOP CDM V 5.3](https://ohdsi.github.io/CommonDataModel/cdm53.html):

| OMOP CDM Category             | Standard Tables                                                                                                                                                                                                      | Mandatory |   |   |
|-------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|---|---|
| Standardized clinical data    | person, observation_period, visit_occurrence, visit_detail, condition_occurrence, drug_exposure, procedure_occurrence, device_exposure, measurement, observation, death, note, note_nlp, specimen, fact_relationship | yes       |   |   |
| Standardized health system    | location, care_site, provider                                                                                                                                                                                        | yes       |   |   |
| Standardized health economics | payer_plan_period, cost                                                                                                                                                                                              | yes       |   |   |
| Standardized derived elements | drug_era, dose_era, condition_era, cohort, cohort_definition                                                                                                                                                         | yes       |   |   |
| Standardized vocabularies     | concept, vocabulary, domain, concept_class, concept_relationship, relationship, concept_synonym, concept_ancestor, source_to_concept_map, drug_strength                                                              | yes       |   |   |
| Standardized metadata         | metadata, cdm_source                                                                                                                                                                                                 | no        |   |   |

The uploaded file should contain valid json format as the following:
```
{
  "person":"@cdm_database_schema.person",
  "concept":"@vocabulary_database_schema.concept",
  "cohort":"@target_database_schema.@target_cohort_table",
  ......
}
```

<br>
# Cohort SQL Scripts
<div class="alert">
This version supports only SQL language Snowflake and Databricks.
</div>

The Solution also requires one or more SQL scripts to construct "cohorts."  **Each text file (e.g., .txt, .sql, ...) should contain one and only one cohort**. Each text file should have a unique file name while uploading. The Solution can execute a valid cohort SQL script following the naming convention of OMOP CDM. 

The Solution supports cohort SQL scripts exported from the Atlas tool. 
![required_files_Atlas.png](wS57Be4bGfxl)

<br>
# Cohort Metadata
The cohort metadata lists the cohort(s) and metadata to be batch-processed. The  **uploaded CSV file**  will populate the cohort metadata and must meet the following schema:

| Dataset name    | Description                                             | Granularity             | Mandatory |   |
|-----------------|---------------------------------------------------------|-------------------------|-----------|---|
| cohort metadata | a list the cohort(s) and metadata to be batch processed | 1 row = 1 cohort script | yes       |   |
|                 |                                                         |                         |           |   |



| name                          | Description              | Datatype | Example                                   | Mandatory |
|-------------------------------|--------------------------|----------|-------------------------------------------|-----------|
| cohort_definition_id          | cohort unique identifier | integer  | 1                                         | yes       |
| cohort_definition_name        | cohort name              | string   | acute myocardial infarction               | yes       |
| cohort_definition_description | description of a cohort  | string   | hospitalization for myocardial infarction | no        |
| cohort_sql_script_filename    | file name of the script  | string   | cohort_script_hospitalization_ami.sql     | yes       |
|                               |                          |          |                                           |           |
