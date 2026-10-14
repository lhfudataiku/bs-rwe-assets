# Cohort Ingestion
Once the pipeline configuration is completed, users can start ingesting cohorts with their cohort SQL scripts. This process is repeatable; however, the two steps  **Upload Cohort SQL Scripts & Cohort Metadata**  and   **Write Cohort** must be executed in sequence for each ingestion. This section populates the two OMOP results schema table [cohort](dataset:cohort) and [cohort_definition](dataset:cohort_definition). 

## Upload Cohort SQL Scripts & Cohort Metadata
The Solution requires cohort SQL scripts and cohort metadata to write data into OMOP tables" **cohort** " and " **cohort_definition**." The cohort SQL scripts define the SQL recipe for writing cohorts into the two OMOP tables, whereas the cohort metadata indicates which cohort(s) to be batch-processed. 

### Step 1: Upload cohort SQL scripts
Users can upload and store multiple SQL scripts. The "[Original Scripts](managed_folder:PqOBn6B3)" stores all uploaded original scripts. 

### Step 2: Upload cohort metadata

The cohort metadata file lists the cohort(s) to be batch-processed. It must contain four columns:  **cohort_definition_id** ,  **cohort_definition_name** ,  **cohort_definition_description** ,  **cohort_sql_script_filename** . Please read [Required Files](article:5) for information on the required schema.

<div class="alert">
⚠️ The Solution processes only the cohort(s) listed in the cohort metadata. Therefore, the cohort metadata should contain only the file(s) containing cohorts for upload/update and should also match the file(s) in the 'Original Script' folder. The 'Original Script' folder has no constraints on the original scripts it saves. We encourage users to keep all the original scripts there.
</div> 

![project_setup-scripts.png](a1C1UMHo5A7C)

### Section outputs
 1.  [cohort_definition](dataset:cohort_definition): An OMOP table, stores cohort metadata.
 2. [Mapped Scripts](managed_folder:lMM00YKr) stores the cohort SQL scripts mapped to OMOP tables' paths. These scripts can be used for debugging in SQL notebook if corrupted. 
 3. [Upload cohorts info](dataset:uploaded_cohort_definition) lists the cohort(s) to be uploaded or updated.
 

### Troubleshoot 🔧 
1. Missing required OMOP tables for the cohort scripts
 - Error message:  ValueError(f"Expecting input OMOP table(s) '{required_input_cdm_table_missing_string}' for cohort script '{cohort_name}'! Please add all required OMOP CDM tables to the Connect OMOP Common Data Model Standard Tables section")
 -  **Solution** :   add required OMOP tables at the section  **Connect OMOP Common Data Model Standard Tables**.
2. Cohort metadata schema violation 
  - Error message: ValueError(f"Expecting column(s) '{mismatched_columns_string}' for cohort metadata. Please check 'Upload cohort metadata' at 'Upload Cohort SQL Scripts' section.")
  - **Solution**:   check column names in the uploaded CSV file. 
3. Missing values in cohort metadata
  - Error message: ValueError(f"Column(s) '{error_column_string}' contains null values! Please check 'Upload cohort metadata' at 'Upload Cohort SQL Scripts' section.")
  - **Solution**:  check the data in the uploaded CSV file.
4. File not found in 'Original Script' folder
  - Error message: ValueError(f"File(s) '{files_not_found_string}' not found in the 'Original Script' folder. Please drop the missing file names from the cohort metadata or upload the corresponding files.")
  - **Solution**: check files in the 'Original Script' folder
  5. No OMOP tables mapped from the script. 
    - Error message: ValueError("No OMOP tables mapped from the script! Please verify the OMOP table names in your scripts and adjust the setting in the previous step 'OMOP CDM Custom Table Name Mapping' accordingly.")
    - **Solution**: The previous step, 'OMOP CDM Custom Table Name Mapping,' most likely causes the problem. Verify the OMOP table names in the uploaded cohort scripts. If your scripts use standard table names, leave the "Custom mapping filename" field empty. If Atlas table names, fill in "omop_cdm_atlas." If custom table names, upload a custom table name mapping json file and fill in the filename. 

<br> 
## Write Cohort
<div class="alert">
⚠️ The previous section, Upload Cohort SQL Scripts & Cohort Metadata, must be done before running this section! 
  </div> 
  
Once the cohort scripts and the cohort metadata are in place, users can write the cohort(s) into the OMOP tables "cohort" and "cohort_definition ."The pipeline writes the cohort(s) in sequence based on the [upload cohorts info](dataset:uploaded_cohort_definition). The pipeline will proceed even if a job run for cohort writing fails. For example, if one of the five cohort scripts is corrupted, the pipeline will finish the four other cohort writing. However, it will show a failed status and log the error message in the [cohort_building_log](dataset:cohort_building_log)


<div class="alert">
The data in datasets "cohort" and "cohort_definition" persist. This process will only overwrite the cohort_definition_id(s) already listed in the two OMOP tables while preserving the others.  
</div> 

Users can review cohort-building logs [cohort_building_log](dataset:cohort_building_log), which log all jobs writing the cohorts. 

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


![project_setup-write.png](TgjD4Tcqzo2t)
⚠️  After arriving at the dataset page, Click on the tab "Explore" to review the data.

### Section outputs
1. [cohort](dataset:cohort): An OMOP table, stores cohorts.
2. [cohort_building_log](dataset:cohort_building_log): Stores all job runs on cohort writing. Useful for debugging and tracking.

### Troubleshoot 🔧 
1. Job failure of cohort writing
  - Error message: "Cohort build error occurred; please review cohort_building_log_history for more info." 
  -  **Solution** : Review [cohort_building_log](dataset:cohort_building_log) and identified the correpted scirpt(s) that caused the error. Return to the section  **Upload Cohort SQL Scripts & Cohort Metadata** and replace the original corrupted SQL script with a good one. Rerun both sections **Upload Cohort SQL Scripts & Cohort Metadata** and  **Write Cohort** 