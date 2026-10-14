Scenarios allow for automating the computation of the flow and are triggered through the [Project Setup](article 8).

### Scenarios supporting  **Pipeline Configuration**
![scenario-pipeline.png](p0jTHVO3dTYl)
 
 **Main scenarios** :
- [Reconfigure Connections](scenario:RECONFIGURECONNECTIONS): changes datasets and folders connection.
- [Import Datasets from DataPrep Project](scenario:IMPORTDATASETSFROMDATAPREPPROJECT): imports OMOP tables from source project.
- [Check OMOP Table Variables Mapping](scenario:CHECKOMOPTABLEVARIABLESMAPPING): checks OMOP custom table name mapping file schema.

**Supporting scenarios** :
- [Check OMOP CDM Schema](scenario:CHECKOMOPCDMSCHEMA): checks imported OMOP tables schema.
- [Build Covariate Datasets](scenario:BUILDCOVARIATEDATASETS): builds datasets in flow zone [Covariates: Clinical Concepts](flow_zone:iFsjUYk) and [Covariates: Demography](flow_zone:FEj187R)

<br>
### Scenarios supporting **Cohort Ingestion**
![scenario-cohorts.png](wiezyrtuBY3d)
 
 **Main scenarios** :
- [Create Cohort Scripts](scenario:CREATECOHORTSCRIPTS): maps table paths to original cohort SQL scripts and creates cohort metadata for cohort ingestion. 
- [Write Cohort to Datasets](scenario:WRITECOHORTTODATASETS): ingests cohorts to OMOP tables [cohort](dataset:cohort) and [cohort_definition](dataset:cohort_definition) and logs jobs to [cohort_building_log](dataset:cohort_building_log). 

**Supporting scenarios** :
- [Check Uploaded Cohort Metadata Schema](scenario:CHECKUPLOADEDCOHORTMETADATASCHEMA): verifies uploaded cohort metadata schema and data quality.
- [Build Cohort Log Dataset](scenario:BUILDCOHORTLOGDATASET): saves logs to [cohort_building_log](dataset:cohort_building_log).
- [Drop SQL Temporary Tables](scenario:DROPSQLTEMPORARYTABLES): clears SQL temporary tables from the SQL server.
- [Build Cohort Dataset](scenario:WRITECOHORTDATA): ingests cohort to [cohort](dataset:cohort).
- [Build Cohort Metadata Dataset](scenario:WRITECOHORTMETADATA): ingests cohort metadata to [cohort_definition](dataset:cohort_definition).

<br>
### Scenario support **Dashboard Creation**
![scenario-dashboard.png](bGo63JTMKdcP)
[Build Cohort Dashboard](scenario:BUILDCOHORTDASHBOARD): builds datasets feeding the dashboards and regenerates plots, metrics, and tables. 