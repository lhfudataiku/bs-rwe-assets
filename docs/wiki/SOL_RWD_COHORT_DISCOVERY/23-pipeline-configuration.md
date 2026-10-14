# Pipeline configuration
A one-time configuration to establish the data ETL pipeline. Users should select the connections for the project, connect OMOP CDM tables from the source project, and provide an OMOP custom table name mapping file if needed. 


## Connection Configuration
<div class="alert">
⚠️  This version of the Solution supports only Snowflake, Databricks, and Redshift SQL connections.
</div> 

### Step 1: Select connections
The Solution requires an SQL connection for the datasets and another for the project folders. 
<div class="alert">
We recommend that users use the built-in connection "dataiku-managed-storage" for the folders on **Dataiku Cloud**. The filesystem options are not compatible with this Solution on the cloud. 
</div>

### Step 2: Activate/Deactivate data pipeline
<div class="alert">
Experimental feature: The SQL pipeline feature is considered experimental and not officially supported. In case of issues, you always have the option to turn off SQL pipelines on a per-project basis.
</div>

The Solution supports DSS SQL pipelines, which allow projects to execute long data pipelines with multiple steps without always having to write the intermediate data and re-read it at the next steps. The SQL pipeline function boosts performance and reduces storage and computation costs. Please read [DSS documentation on data pipeline](https://doc.dataiku.com/dss/13/sql/pipelines/index.html).   

### Step 3: Run Scenario connection configuration

![project_setup-connection .png](D5fUO5meR1e8)

### Troubleshoot 🔧 
1. Unsupported connection type
 - **Error message** : 
 <div class="alert">
⚠️ValueError: '{connection_type}' is not supported in this version! This version supports Snowflake, Databricks, and Redshift"
 </div> 
 -  **Solution**: select Snowflake, Databricks, or Redshift connection.

<br>
## Connect OMOP Common Data Model Standard Tables
The Solution requires a connection to OMOP CDM source datasets.
<div class="alert">
We recommend that users conduct data preparation and feature engineering steps in a separate project to match the expected format of the input datasets. 
</div> 

### Step 1: Select the source project
Select the source project where users have all the required OMOP CDM datasets.

### Step 2: Multi-select OMOP tables
Users must select all the OMOP tables required for the cohort SQL scripts for the Solution to run correctly.

### Step 3: Map OMOP tables to source
<div class="alert">
⚠️   The source input datasets must use the same SQL connection type as selected in the project setup. 
</div> 

Select the corresponding source dataset for each OMOP table. The source datasets must respect the OMOP CDM v 5.3 schema. Please review [Data Model & Files](article:3) for complete information. 

The following OMOP tables are mandatory for the Solution:  **person** ,  **observation_period** ,  **visit_occurrence** ,  **condition_occurrence** ,  **drug_exposure** ,  **death** ,  **location** ,  **condition_era** ,  **concept** ,  **concept_ancestor** . These tables remain on the list regardless of the previous step's results. 

![project_setup-import.png](UtxTZP8S6arA)

### Troubleshoot 🔧 
1. Missing OMOP table
 - **Error message**:
 <div class="alert">
⚠️  ValueError: Expecting OMOP table '{dataset}' for import! All OMOP tables displayed in the Connect OMOP Common Data Model Standard Tables section require a source dataset.
</div> 
 -  **Solution**: Check if all OMOP tables have selected source datasets
2. OMOP CDM schema violation for the source datasets
 - **Error message** :  
  <div class="alert">
⚠️Required column(s) missing or mismatched in import dataset '{imported_table_name}' from Project '{project_key}'!!   <br>
  Expect column(s) '{required_columns}' for CDM Table '{dataset}'. 
  </div> 
 - **Solution**:  fix required columns in datasets at the source project.
 - **Error message** : 
<div class="alert">
⚠️Optional column datatype error in import dataset '{imported_table_name}' from Project '{project_key}'!! <br>
  Expect column(s) '{optional_columns}' for CDM Table '{dataset}'.
 </div> 
 - **Solution**:  fix the data type of the optional columns in datasets at the source project.

<br>
## OMOP CDM Custom Table Name Mapping (Optional)
This Solution requires an OMOP custom table name mapping json file if the cohort script(s) use custom table names other than the standard OMOP table names. This Solution pre-packaged a mapping json for cohort scripts exported from the Atlas tool. ([Example](https://atlas-demo.ohdsi.org/#/cohortdefinition/1770034/export)). Skip this step if cohort SQL scripts follow OMOP naming conventions.

### Step 1: Upload custom OMOP table name mapping json file (optional)
Upload a text file containing a key-value pair, including tables from OMOP CDM v 5.3. Skip this step if no custom mapping is required.
 **The pre-packaged mapping json file can be found in the solution library under the directory /python/solution/omop_cdm_atlas.json.** 

 - Standardized clinical data:   person, observation_period, visit_occurrence, visit_detail, condition_occurrence, drug_exposure, procedure_occurrence, device_exposure, measurement, observation, death, note, note_nlp, specimen, fact_relationship
 - Standardized health system: location, care_site, provider
 - Standardized health economics: payer_plan_period, cost
 - Standardized derived elements: drug_era, dose_era, condition_era, cohort, cohort_definition
 - Standardized vocabularies: concept, vocabulary, domain, concept_class, concept_relationship, relationship, concept_synonym, concept_ancestor, source_to_concept_map, drug_strength
 - Standardized metadata (optional): metadata, cdm_source
 
Please read [Required Files](article:5) for more details.

### Step 2: Fill in OMOP table name mapping filename (optional)
Indicate the filename to be used. The field is empty by default. Skip this step if cohort SQl scripts use the standard OMOP naming conventions. Fill in " **omop_cdm_atlas** " if users use the cohort scripts exported from the Atlas tool. 

![project_setup-mapping.png](WVW7071J0rpU)
 
 ### Troubleshoot 🔧 
 1. Missing OMOP tables for the mapping file
  - Error Message: 
<div class="alert">
⚠️ Exception: Table name validation completed with errors: Expecting OMOP table variable(s) '{cdm tables}' for mapping! Please verify all OMOP CDM and standardized vocabulary tables are included in the select OMOP CDM tables mapping file in the OMOP Common Data Model Table Mapping section.
 </div> 
   - Solution: Include all required OMOP tables in the mapping json file. 