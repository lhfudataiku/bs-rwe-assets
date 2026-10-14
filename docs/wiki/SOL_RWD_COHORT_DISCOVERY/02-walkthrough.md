This Solution has two main components: Project Setup and Dashboard. The project setup configures the cohort ingestion pipeline, and the dashboard provides a quick visualization of cohort statistics and characteristics. 

# Project Setup
To configure and execute the pipeline, we will follow the steps in the [Project Setup](article:8). The project setup consists of three components:  **pipeline configuration**,  **cohort ingestion**, and  **dashboard creation**.
![project_setup-index.png](Z9Qc2ItgsoKs)

## Pipeline configuration
A one-time configuration to establish the data ETL pipeline. Users should select the connections for the project, connect OMOP CDM tables from the source project, and provide an OMOP custom table name mapping file if needed. [Pipeline Configuration](article:28)

<br>
### Connection Configuration
The Solution defaults in the filesystem once installed on the DSS instance. However, users must change the connection this Solution supports during the project setup. 

 **Step 1: Select connections** 
The Solution requires an SQL connection for the datasets and another for the project folders. The SQL connection  **must be one of the supported SQL connections (Snowflake, Databricks, and Redshift) **. 
<div class="alert">
We recommend that users use the built-in connection "dataiku-managed-storage" for the folders on **Dataiku Cloud**. The filesystem options are not compatible with this Solution on the cloud. 
</div>

 **Step 2: Activate/Deactivate data pipeline** 
<div class="alert">
Experimental feature: The SQL pipeline feature is considered experimental and not officially supported. In case of issues, you always have the option to turn off SQL pipelines on a per-project basis.
</div>

The Solution supports DSS SQL pipelines, which allow projects to execute long data pipelines with multiple steps without always having to write the intermediate data and re-read it at the next steps. The SQL pipeline function boosts performance and reduces storage and computation costs. Please read [DSS documentation on data pipeline](https://doc.dataiku.com/dss/13/sql/pipelines/index.html).   

 **Step 3: Run Scenario connection configuration** 

![project_setup-connection .png](OqbuWGhRQDnP)

#### Troubleshoot 🔧 
1. Unsupported connection type
 - **Error message** : 
 <div class="alert">
⚠️ValueError: '{connection_type}' is not supported in this version! This version supports Snowflake, Databricks, and Redshift"
 </div> 
 -  **Solution**: select Snowflake, Databricks, or Redshift connection.
 
<br><br>
### Connect OMOP Common Data Model Standard Tables
The Solution requires a connection to OMOP CDM source datasets.
<div class="alert">
We recommend that users conduct data preparation and feature engineering steps in a separate project to match the expected format of the input datasets. 
</div> 

 **Step 1: Select source project** 
Select the source project where users have all the required OMOP CDM datasets.

 **Step 2: Multi-select OMOP tables** 
Users must select all the OMOP tables required for the cohort SQL scripts for the Solution to run correctly.

 **Step 3: Map OMOP tables to source** 
<div class="alert">
⚠️  The source input datasets must use the same SQL connection type as selected in the project setup. 
</div> 

Select the corresponding source dataset to each OMOP table. The source datasets must respect the OMOP CDM v 5.3+ schema, so please review [Data Model & Files](article:3) for the complete information. 

The following OMOP tables are mandatory for the Solution:  **person** ,  **observation_period** ,  **visit_occurrence** ,  **condition_occurrence** ,  **drug_exposure** ,  **death** ,  **location** ,  **condition_era** ,  **concept** ,  **concept_ancestor** . These tables remain on the list regardless of the previous step's results. 

![project_setup-import.png](5jNdvtlQOimU)

#### Troubleshoot 🔧 
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

<br><br>
### OMOP CDM Custom Table Name Mapping (Optional)
This Solution requires an OMOP custom table name mapping json file if the cohort script(s) use custom table names other than the standard OMOP table names. This Solution pre-packaged a mapping json for cohort scripts exported from the Atlas tool. ([Example](https://atlas-demo.ohdsi.org/#/cohortdefinition/1770034/export)). Skip this step if cohort SQL scripts follow OMOP naming conventions.

 **Step 1: Upload custom OMOP table name mapping json file (optional)** 
Upload a text file containing a key-value pair, including tables from OMOP CDM v 5.3+. Skip this step if no custom mapping is required.

 **The pre-packaged mapping json file can be found in the solution library under the directory /python/solution/omop_cdm_atlas.json.** 

 - Standardized clinical data:   person, observation_period, visit_occurrence, visit_detail, condition_occurrence, drug_exposure, procedure_occurrence, device_exposure, measurement, observation, death, note, note_nlp, specimen, fact_relationship
 - Standardized health system: location, care_site, provider
 - Standardized health economics: payer_plan_period, cost
 - Standardized derived elements: drug_era, dose_era, condition_era, cohort, cohort_definition
 - Standardized vocabularies: concept, vocabulary, domain, concept_class, concept_relationship, relationship, concept_synonym, concept_ancestor, source_to_concept_map, drug_strength
 - Standardized metadata (optional): metadata, cdm_source
 
Please read [Required Files](article:5) for more details.

**Step 2: Fill in OMOP table name mapping filename (optional)**
Indicate the filename to be used. The field is empty by default. Skip this step if cohort SQl scripts use the standard OMOP naming conventions. Fill in " **omop_cdm_atlas** " if users use the cohort scripts exported from the Atlas tool. 
Please read [Required Files](article:5) for more details.
![project_setup-mapping.png](Rz7t2ArW5nl1)
 
#### Troubleshoot 🔧 
 1. Missing OMOP tables for the mapping file
  - Error Message: 
<div class="alert">
⚠️ Exception: Table name validation completed with errors: Expecting OMOP table variable(s) '{cdm tables}' for mapping! Please verify all OMOP CDM and standardized vocabulary tables are included in the select OMOP CDM tables mapping file in the OMOP Common Data Model Table Mapping section.
 </div> 
   - Solution: Include all required OMOP tables in the mapping json file. 
   
<br><br>
## Cohort Ingestion
Once the pipeline configuration is completed, users can start ingesting cohorts with their cohort SQL scripts. This part is repeatable; however, the two steps  **Upload Cohort SQL Scripts & Cohort Metadata**  and   **Write Cohort** must be executed in sequence for each ingestion. [Cohort Ingestion](article:29)

### Upload Cohort SQL Scripts & Cohort Metadata
The Solution requires cohort SQL scripts and cohort metadata to write data into OMOP tables" **cohort** " and " **cohort_definition**." The cohort SQL scripts define the SQL recipe for writing cohorts into the two OMOP tables, whereas the cohort metadata indicates which cohort(s) to be batch-processed. 

 **Step 1: Upload cohort SQL scripts** 
Users can upload and store multiple SQL scripts. The "[Original Scripts](managed_folder:PqOBn6B3)" stores all uploaded original scripts. 

 **Step 2: Upload cohort metadata** 

The cohort metadata file lists the cohort(s) to be batch-processed. It must contain four columns:  **cohort_definition_id** ,  **cohort_definition_name** ,  **cohort_definition_description** ,  **cohort_sql_script_filename** . Please read [Required Files](article:5) for information on the required schema.

<div class="alert">
⚠️ The Solution processes only the cohort(s) listed in the cohort metadata. Therefore, the cohort metadata should contain only the file(s) containing cohorts for upload/update and should also match the file(s) in the 'Original Script' folder. The 'Original Script' folder has no constraints on the original scripts it saves. We encourage users to keep all the original scripts there.
</div> 

![project_setup-scripts.png](a1C1UMHo5A7C)

#### Section outputs
 1.  [cohort_definition](dataset:cohort_definition): An OMOP table, stores cohort metadata.
 2. [Mapped Scripts](managed_folder:lMM00YKr) stores the cohort SQL scripts mapped to OMOP tables' paths. These scripts can be used for debugging in SQL notebook if corrupted. 
 3. [Upload cohorts info](dataset:uploaded_cohort_definition) lists the cohort(s) to be uploaded or updated.
 

#### Troubleshoot 🔧 
1. Missing required OMOP tables for the cohort scripts
 - Error message:  
 <div class="alert">
ValueError: Missing required OMOP tables across cohorts: <br>
  Details by cohort: <br>
  Cohort 0 ('{cohort name}'): Expecting input OMOP table(s) '{cdm tables}' for cohort script! Please add all required OMOP CDM tables to the Connect OMOP Common Data Model Standard Tables section
  </div> 
 -  **Solution** :   add required OMOP tables at the section  **Connect OMOP Common Data Model Standard Tables**.
2. Cohort metadata schema violation 
  - Error message: 
<div class="alert">
ValueError: Expecting column(s) '{column}' for cohort metadata. Please check 'Upload cohort metadata' at 'Upload Cohort SQL Scripts' section.
  </div> 
  - **Solution**:   check column names in the uploaded CSV file. 
3. Missing values in cohort metadata
  - Error message: 
<div class="alert">
ValueError: Column(s) '{columns}' contains null values! Please check 'Upload cohort metadata' at 'Upload Cohort SQL Scripts' section.
  </div> 
  - **Solution**:  check the data in the uploaded CSV file.
4. File not found in 'Original Script' folder
  - Error message: 
<div class="alert">
ValueError: File(s) '{files}' not found in the 'Original Script' folder. Please drop the missing file names from the cohort metadata or upload the corresponding files.
  </div> 
  - **Solution**: check files in the 'Original Script' folder
5. No OMOP tables mapped from the script. 
  - Error message: 
<div class="alert">
ValueError: No OMOP tables mapped from the script! Please verify the OMOP table names in your scripts and adjust the setting in the previous step 'OMOP CDM Custom Table Name Mapping' accordingly.
  </div> 
  - **Solution**: The previous step, 'OMOP CDM Custom Table Name Mapping,' most likely causes the problem. Verify the OMOP table names in the uploaded cohort scripts. If your scripts use standard table names, leave the "Custom mapping filename" field empty. If Atlas table names, fill in "omop_cdm_atlas." If custom table names, upload a custom table name mapping json file and fill in the filename. 

<br><br>
### Write Cohort
<div class="alert">
⚠️ The previous section Upload Cohort SQL Scripts & Cohort Metadata must be done before running this section! 
  </div> 
  
Once the cohort scripts and the cohort metadata are in place, users can write the cohort(s) into the OMOP tables "cohort" and "cohort_definition". The pipeline writes the cohort(s) in sequence based on the [upload cohorts info](dataset:uploaded_cohort_definition). The pipeline will loop through all cohort scripts listed in the "upload_cohort_definition" despite any job failure. For example, if one of the five cohort scripts is corrupted, the pipeline will finish the other four good ones. However, it will show a failed status and log the error message in the [cohort_building_log](dataset:cohort_building_log)


<div class="alert">
The data in the "cohort" and "cohort_definition" datasets will be retained. This process will overwrite only the cohort_definition_id(s) already present in the two OMOP tables, leaving all other data unaffected.
</div> 

Users can review cohort building logs [cohort_building_log](dataset:cohort_building_log). It logs all jobs writing the cohorts. 

| name                     | Description                                               | Datatype | Example                        |   |
|--------------------------|-----------------------------------------------------------|----------|--------------------------------|---|
| run_timestamp            | datetime of the job run                                   | string   | 2024-11-14-07-13-11-446        |   |
| cohort_definition_id     | unique cohort ID                                          | int      | 1                              |   |
| cohort_definition_name   | cohort label                                              | string   | acute kidney injury            |   |
| cohort_count             | total count of a cohort resulting from a given SQL script | int      | 3029                           |   |
| status                   | status of the job run                                     | string   | SUCCESS or Failure             |   |
| error                    | error message from a failed job run                       | string   |                                |   |
| original_script_filename | filename of the original cohort script                    | string   | cohort_script_chronic_t2dm.sql |   |
|                          |                                                           |          |                                |   |


![project_setup-write.png](RElN5gcxhnAM)

#### Section outputs
1. [cohort](dataset:cohort): An OMOP table, stores cohorts.
2. [cohort_building_log](dataset:cohort_building_log): Stores all job runs on cohort writing. Useful for debugging and tracking.

#### Troubleshoot 🔧 
1. Job failure of cohort writing
  - Error message
<div class="alert">
⚠️ ValueError: Cohort building failed for the following cohorts: <br>
Details by cohort:.... <br>
Please review cohort_building_log_history for more info
  </div> 
  -  **Solution** : Review [cohort_building_log](dataset:cohort_building_log) and identified the correpted scirpt(s) that caused the error. Return to the section  **Upload Cohort SQL Scripts & Cohort Metadata** and replace the corrupted SQL script with a good one. Rerun both sections **Upload Cohort SQL Scripts & Cohort Metadata** and  **Write Cohort** 

<br><br>
<br>
## Dashboard Creation
The cohort dashboard provides a quick review of the results from a cohort query to facilitate cohort validation. This part allows users to regenerate the dashboard.  [Dashboard Creation](article:30)

### Create Cohort Dashboard
Select a cohort to build descriptive statistics and clinical characteristics.

![project_setup-visualization.png](oMGgUp8w6Uo7)

#### Section outputs
1. [Cohort Discovery Insights](dashboard:4OpJPy0)

<br><br>
# Dashboard: Cohort Discovery Insights
In OMOP, a cohort can represent an electronic clinical phenotype. Therefore, a patient can meet the cohort criteria several times in a given observation period and thus be counted multiple times in a cohort.  [Dashboard](article:9)
## Slide 1: Cohort Descriptive Statistics
The first part of the dashboard provides general statistics of a selected cohort: incidence and prevalence, demographics, and disease burden. 

![dashboard-stats.png](nAklTtVKopZ7)
![dashboard-geo.png](3Gmma2TRHPIv)
The first part of the slide displays the descriptive statistics on the patients who met the cohort eligibility criteria.
- **Occurrence**: the number of times patients meet specified criteria to enter a cohort
- **Distinct patient count**: the number of unique patients who have ever entered a cohort.
- **Prevalence**:  the proportion of unique patients in a cohort relative to the observed population during a specific period (%).
- **Incidence Rate**: the ratio of new cases in an at-risk population over the observation period (new cases per 1,000 person-years).

![cohort_demographics.png](w3tMoPgqEYDF)
The second part describes the statistics on  **demographic variables**  (age, sex, race) between the cohort and control (patients illegible in the rest of the population.) 

![overview-dashboard-cohort-others.png](mp9NrwDB3ZgK)
The last part includes the disease burden index and cohort observations.
- **Charlson Comorbidity Index**  predicts the mortality for a patient who may have a range of concurrent conditions, such as heart disease, AIDS, or cancer. The higher the score, the higher the predicted mortality rate is.
- Cohort observation Duration gives a general description of the observed time for the at-risk population. 

 - **Cohort Duration**: The days between the cohort start and end dates. It represents the duration when a patient meets the eligibility criteria. It can also be described as "Time-at-risk."
 
 - **Prior Observation Time**: The days between the patient observation start date and the cohort start date. It represents the time before a patient entered the cohort.
 
 - **Follow-up Time**: The days between the cohort start date and the patient observation end date. It represents the duration from when the patient enters the cohort until the end of the observation. 


## Slide 2: Cohort Covariates
The second slide describes the distribution of three predefined OMOP clinical covariates (clinical condition groups, drug groups, and clinical visits) from the [Atlas tool](https://github.com/OHDSI/FeatureExtraction/blob/main/inst/sql/sql_server/DomainConceptGroup.sql).
**Prevalence**: The percentage of patients in the cohort who have at least one prescription of a given drug group  _within one year_ before the cohort start date.

![dashboard-conditions.png](jzBlJI6M1AUi)
-  **Condition group covariates**  include the condition concept groups represented by [SNOMED](https://www.nlm.nih.gov/healthit/snomedct/index.html). 

![dashboard-drugs.png](2GBWI4kv4i6K)
-  **Drug group covariates**  include drug concept groups represented by WHO [ATC](https://atcddd.fhi.no/atc/structure_and_principles/). 

![dashboard-visits.png](biDdvm87imuV)
-  **Clinical visit covariates**:  The OMOP concepts define the clinical visit type. The pivot table describes the temporal relationships between clinical utilization and the cohort.

# Project Output Datasets
This Solution creates several output datasets that other projects can share for further analysis. [Output Datasets](article:26)
- OMOP results schema table [cohort](dataset:cohort) and [cohort_definition](dataset:cohort_definition)
- Clinical covariate tables: [person_location_joined](dataset:person_location_joined), [charlson_score_occurrence](dataset:charlson_score_occurrence), [condition_group_occurrence](dataset:condition_group_occurrence), [drug_class_exposure](dataset:drug_class_exposure), [visit_occurrence_labeled](dataset:visit_occurrence_labeled)

<br><br>
# Conclusion
The project setup provides a no-code user interface to configure complex cohort ingesting pipelines. This pipeline creates centralized storage for cohort scripts, cohorts, and metadata, which is sharable and reusable across different projects. Once the pipeline is configured, users can grow their "cohort" repository over time by ingesting cohorts. The cohort dashboard gives a quick review of the results from a cohort query to facilitate cohort validation.  
