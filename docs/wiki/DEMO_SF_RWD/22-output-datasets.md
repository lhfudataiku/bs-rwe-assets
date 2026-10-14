This Solution creates several output datasets that other projects can share for further analysis: 

## OMOP Results Schema 
The OMOP results schema table [cohort](dataset:cohort) and [cohort_definition](dataset:cohort_definition) are located in the zone [Cohorts](flow_zone:UhRhvSG). They store and index the cohorts uploaded through project setup. Users can use them in future RWD/RWE analyses. These datasets are the products of the [Cohort Ingestion](article:29) in the project setup.
![flow-cohorts.png](NripyMmYzlzJ)


## Cohort Feature Tables
The zone [Cohort Features](flow_zone:9ty9xEO) produces four datasets (-[cohort_demographics](dataset:cohort_demographics), [cohort_visit_events](dataset:cohort_visit_events), [cohort_condition_group_events](dataset:cohort_condition_group_events), [cohort_drug_group_events](dataset:cohort_drug_group_events)) containing demographics and clinical events of **one selected cohort** . These datasets are the results of the [Dashboard Creation](article:30). 
![flow-cohort-features .png](saP4ER10PqTG)