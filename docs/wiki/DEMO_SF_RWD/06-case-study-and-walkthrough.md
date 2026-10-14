# Real-World Data (RWD)
RWD refers to health-related information collected outside controlled clinical trials, often gathered from electronic health records, insurance claims, and patient registries. Using RWD to assess real-world evidence (RWE) is one of the top priority applications for AI transformations/initiatives in healthcare (payer/provider/public or federal health systems) and life science companies. However, a complex ETL process involves collecting, normalizing, and harmonizing patient data from heterogeneous sources (e.g., patient registry, electronic health record system(s), insurance claims) even within one healthcare organization. A few global common data models provide a framework to standardize these complex ETL processes. This Solution assumes the [Observational Medical Outcomes Partnership (OMOP) Common Data Model (CDM)](https://www.ohdsi.org/data-standardization/) and requires the input datasets to conform to OMOP.  _Transforming source data to OMOP is not within the scope of this Solution. _ [Learn more about OMOP](https://www.ohdsi.org/open-source-tutorials/)
![Solution_blueprint.png](hwZwj6D8WBVg)


## OMOP CDM
The Observational Medical Outcomes Partnership (OMOP) Common Data Model (CDM) is an open community data standard designed to standardize the structure and content of observational data and enable efficient analyses to produce reliable evidence. A central component of the OMOP CDM is the OHDSI standardized vocabularies. The OHDSI vocabularies allow organization and standardization of medical terms to be used across the various clinical domains of the OMOP CDM and enable standardized analytics that leverage the knowledge base when constructing exposure and outcome phenotypes and other features within characterization, population-level effect estimation, and patient-level prediction studies.   (reference: https://www.ohdsi.org/data-standardization/)
![OMOP-CDM.png](8PtiTwVCJDUy)

# User Story
A  **biomedical informaticist**  has a medical background and a deep understanding of biomedical ontology and clinical datasets. This profession interprets the eligibility criteria from a study design or an observational research question in human natural language. It reconstructs patient cohorts from an observation healthcare database (a.k.a. real-world data). The term  **Clinical electronic phenotyping**  describes this process of constructing "cohorts" with patient data. The eligibility criteria for clinical research questions are often very complex. It could involve multiple clinical concepts with complex temporal relationships, translating into lengthy SQL scripts, which are challenging to manage and reuse. The Solution provides a centralized space to store cohorts created by biomedical informaticists, which can be further used by clinical researchers, statisticians, or data scientists for advanced analytics and clinical modeling. 
Clinical electronic phenotyping requires frequent collaborations between informaticists and clinical experts. While informaticists help create the cohort scripts, clinical experts supervise and validate the script's results (lists of patient IDs) by reviewing its descriptive statistics and clinical feature distributions. The Solution dashboard aims to facilitate this iterative process of building and validating cohort SQL script by visualizing descriptive statistics for a selected cohort.

# Data
## Input Datasets
This Solution requires that the database assumes [OMOP CDM v5.3](https://ohdsi.github.io/CommonDataModel/cdm53.html) or a later version. It translates the OMOP CDM schema into a DSS-compatible schema, which can be found in the Solution library repository (python/solution/utils/cdm_schema.py). 

This Solution requires a minimum subset of OMOP CDM tables:
 - person
 - observation_period
 - visit_occurrence
 - condition_occurrence
 - drug_exposure
 - death
 - location
 - condition_era
 - concept
 - concept_ancestor

Users can add additional OMOP tables to the Solution based on their needs. For more details about the data model, please read [Data Model article](article:3).

## OMOP CDM Table Name Mapping (Optional)
This Solution requires an OMOP table name mapping json file if the cohort script(s) use custom table names other than the standard OMOP table names. This Solution pre-packaged a mapping json for cohort scripts exported from the Atlas tool. ([Example](https://atlas-demo.ohdsi.org/#/cohortdefinition/1770034/export))
Please read [Required Files article](article:5) for more details about the OMOP CDM table name mapping file.

## Cohort SQL Scripts
<div class="alert">
This version currently supports only SQL language for Snowflake and Databricks.
</div>

The Solution also requires one or more SQL scripts to construct "cohorts." A cohort SQL script is valid as long as it follows the naming convention of OMOP CDM. 
<div class="alert">
In OMOP CDM, "cohort" is sometimes interchangeable with "clinical phenotype." Therefore, a cohort SQL script can produce a simple "cohort" representing all anti-hypertensive prescriptions. A more complicated cohort SQL script can represent eligibility criteria for a clinical research question like a "cohort" with hypertension on first-time monotherapy of angiotensin-converting enzyme inhibitors (ACEIs).
</div>

Users can also facilitate cohort construction with the accessible tool [Atlas](https://atlas-demo.ohdsi.org/#/cohortdefinitions), which provides a no-code user interface for building and exporting cohort SQL scripts in the language of choice.

Please read [Required Files article](article:5) for more details about the cohort SQL scripts.

## Cohort Metadata
The cohort metadata file provides a list of cohorts and metadata to indicate which cohorts should be uploaded or revised to the "cohort" table and "cohort_definition" OMOP table. 

Please read [Required Files article](article:5)  for more details about the cohort metadata.

# Insights
- Providing a generalizable RWD data pipeline for cohort identification/selection/discovery for patient insights will accelerate population, digital, and clinical health insights across the broader healthcare ecosystem




