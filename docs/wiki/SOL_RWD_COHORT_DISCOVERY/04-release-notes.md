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