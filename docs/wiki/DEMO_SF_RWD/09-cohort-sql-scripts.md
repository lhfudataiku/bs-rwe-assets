This flow zone stores the uploaded OMOP CDM table name variation mapping file, original cohort scripts, and cohort metadata. It also includes mapping cohort scripts with table paths and populating the OMOP table 'cohort_definition.'

![flow-cohort-scripts.png](oGbgeVSzNJVl)

- [OMOP CDM table variables mapping](managed_folder:4ktqvA1F) folder saves the uploaded custom table names mapping json files
- [Original Scripts](managed_folder:PqOBn6B3) folder stores all uploaded original cohort SQL scripts
- [cohort_metadata](dataset:cohort_metadata) saves the uploaded cohort metadata
- [Mapped Scripts](managed_folder:lMM00YKr) folder stores all the mapped cohort SQL scripts in the format of which the DSS can execute. 