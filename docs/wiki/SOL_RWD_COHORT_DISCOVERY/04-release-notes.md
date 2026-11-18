# Version 1.2.0 - Minor Release - [2026-11]
- Solution library moved to the `bs-rwe-assets` repository (`solution/`), with offline tests
- Project Setup: the OMOP table select boxes no longer show errors. They read the data preparation project and main connection from the setup variables, show "Select a data preparation project first" until one is chosen, and list only datasets on the main connection's type
- Project Setup: the cohort select box reads column names in any case and stays empty, without an error, until cohorts are written
- Create Cohort Scripts: read the table name mapping variable from the project setup (local) variables
- Import Datasets from DataPrep Project: fail immediately when the data preparation project does not exist
- Import Datasets from DataPrep Project: rename every column that is not uppercase, mixed-case names included
- Import Datasets from DataPrep Project: build all imported tables in one job and fail the step if the build fails
- Read the main connection from the project setup (local) variables, like the other pipeline steps
- Document the uppercase column-name contract in the Data Model article


# Version 1.1.0 - Upgrade Release - [2025-07]
- Expand SQL connection support to Redshift
- Revise data type mapping between OMOP CDM and DSS schema. OMOP "date" : DSS "dateonly"; OMOP "datetime": DSS "datetimenotz"
- Aligne input data schema's columns requirement  to OMOP CDM v5.3
- Attach the pre-packaged OMOP table name variation mapping json file to solution library
- Revise deliverable datasets - clinical covariate tables.
- Relax SQL connection restriction in project setup to allow the input OMOP dataset sharing the same type of SQL connection
- Change default zone name to "OMOP Input"
- Fix cohort log script
- Revise and migrate the python functions from the project scenarios to the project library. 
- Improve Project Setup UI
- Update Wiki


# Version 1.0.0 - Initial Release - [2024-11]
 - Establish an OMOP data pipeline to ingest cohorts
 - Dashboard for cohort validation