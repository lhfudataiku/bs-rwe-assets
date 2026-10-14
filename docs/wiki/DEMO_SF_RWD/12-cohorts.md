This flow zone contains the main operations that populate the OMOP tables ' **cohort** ' and ' **cohort_definition** ' and the log file. 

![flow-cohorts.png](w5ma5VlVPRlM)

Zone Outputs: 
- [cohort](dataset:cohort) stores all ingested cohorts.
- [cohort_definition](dataset:cohort_definition) stores the metadata of all ingested cohorts.
- [cohort_building_log](dataset:cohort_building_log) keeps the logs of cohort building jobs. Useful for debugging and tracking.


⚠️  The three SQL recipes only appear after completing the Project Setup for the first time. 
The project setup [Upload Cohort SQL Scripts & Cohort Metadata](scenario:CREATECOHORTSCRIPTS) creates recipe [compute_cohort_definition](recipe:compute_cohort_definition) and [Write Cohort](scenario:WRITECOHORTTODATASETS) creates recipe [create_cohort](recipe:create_cohort) and [compute_cohort_building_log](recipe:compute_cohort_building_log).