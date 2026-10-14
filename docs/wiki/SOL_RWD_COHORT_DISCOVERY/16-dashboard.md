# Cohort Discovery Insights
The cohort dashboard gives a quick review of the results from a cohort query, facilitating cohort validation between biomedical informaticists and clinical experts.
In OMOP, a cohort can represent an electronic clinical phenotype. Therefore, a patient can meet the cohort criteria several times in a given observation period and thus be counted multiple times in a cohort. 

## Slide 1: Cohort Descriptive Statistics
The first part of the dashboard provides general statistics of a selected cohort: incidence and prevalence, demographics, and disease burden. 

![dashboard-stats.png](2p5YDMbpJ3Hp)
![dashboard-geo.png](jzK1QB66TvvR)
- **Occurrence**: the number of times patients meet specified criteria to enter a cohort
- **Distinct patient count**: the number of unique patients who have entered a cohort.
- **Prevalence**:  the proportion of unique patients in a cohort relative to the observed population during a specific period (%).
- **Incidence Rate**: the ratio of new cases in an at-risk population over the observation period (new cases per 1,000 person-years).
<br>
![cohort_demographics.png](IauRjqDjD8fF)

This section describes the statistics on demographic variables between the cohort and control (patients who did not meet the criteria for the cohort's creation in the rest of the population).

Only the  **first events**  are counted for the patients who had multiple occasions in the cohort. All counts are  **unique patient counts**  for both the cohort and control group. 
<br>
![overview-dashboard-cohort-others.png](FMpiExMh2PC5)
The last part includes the disease burden index and cohort observations.
- **Charlson Comorbidity Index**  predicts the mortality for a patient who may have a range of concurrent conditions, such as heart disease, AIDS, or cancer. The higher the score, the higher the predicted mortality rate is.
- Cohort observation Duration gives a general description of the observed time for the at-risk population. 

 - **Cohort Duration**: The days between the cohort start and end dates. It represents the duration when a patient meets the eligibility criteria. It can also be described as "Time-at-risk."
 
 - **Prior Observation Time**: The days between the patient observation start date and the cohort start date. It represents the time before a patient entered the cohort.
 
 - **Follow-up Time**: The days between the cohort start date and the patient observation end date. It represents the duration from when the patient enters the cohort until the end of the observation. 


## Slide 2: Cohort Covariates
The second slide describes the distribution of three predefined clinical covariates (clinical condition groups, drug groups, and clinical visits) from the [Atlas tool](https://github.com/OHDSI/FeatureExtraction/blob/main/inst/sql/sql_server/DomainConceptGroup.sql).
**Prevalence**: The percentage of patients in the cohort who have at least one prescription of a given drug group  _within one year_ before the cohort start date.

![dashboard-conditions.png](vYTLuyv4rMko)
-  **Condition group covariates**  include the condition concept groups represented by [SNOMED](https://www.nlm.nih.gov/healthit/snomedct/index.html). 

![dashboard-drugs.png](uEFHRhFIDsuX)
-  **Drug group covariates**  include drug concept groups represented by WHO [ATC](https://atcddd.fhi.no/atc/structure_and_principles/). 

![dashboard-visits.png](BiwIcAl6pOOD)
-  **Clinical visit covariates**:  The OMOP concepts define the clinical visit type. The pivot table describes the temporal relationships between clinical utilization and the cohort.