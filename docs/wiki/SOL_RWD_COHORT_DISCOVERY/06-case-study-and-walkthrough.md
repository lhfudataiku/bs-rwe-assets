# Business Context
## Real-World Data (RWD)
RWD refers to health-related information collected outside controlled clinical trials, often gathered from electronic health records, insurance claims, and patient registries. Using RWD to assess real-world evidence (RWE) is one of the top priority applications for AI transformations/initiatives in healthcare (payer/provider/public or federal health systems) and life science companies. However, a complex ETL process involves collecting, normalizing, and harmonizing patient data from heterogeneous sources (e.g., patient registry, electronic health record system(s), insurance claims) even within one healthcare organization. A few global common data models provide a framework to standardize these complex ETL processes.  **This Solution assumes the [Observational Medical Outcomes Partnership (OMOP) Common Data Model (CDM)](https://www.ohdsi.org/data-standardization/) and requires the input datasets to conform to OMOP.**   _Transforming source data to OMOP is not within the scope of this Solution. _ [Learn more about OMOP](https://www.ohdsi.org/open-source-tutorials/)
![Solution_blueprint.png](hwZwj6D8WBVg)


### OMOP CDM
The OMOP CDM is an open community data standard designed to standardize the structure and content of observational data and enable efficient analyses to produce reliable evidence. A central component of the OMOP CDM is the OHDSI standardized vocabularies. The OHDSI vocabularies allow organization and standardization of medical terms to be used across the various clinical domains of the OMOP CDM and enable standardized analytics that leverage the knowledge base when constructing exposure and outcome phenotypes and other features within characterization, population-level effect estimation, and patient-level prediction studies.   (reference: https://www.ohdsi.org/data-standardization/)
![OMOP-CDM.png](8PtiTwVCJDUy)

# Case Study
## Establish a robust RWD pipeline for real-world evidence (RWE) team using Dataiku's RWD Cohort Discovery solution
This Solution gives the RWE team an efficient RWD pipeline to manage complex cohort queries and promote the generalisability and reproducibility of observational health research.

### Project Background
The RWE team at the leading pharmaceutical/biotech company conducts observational health research to facilitate clinical trial operations and evidence generation. The eligibility criteria in clinical studies are often very complex. It could involve multiple cohorts (e.g., a population with one or more clinical concepts) with complex temporal relationships, translating into lengthy, challenging SQL scripts to manage and reuse. By leveraging the Solution, the RWE team can establish an efficient pipeline connecting to their OMOP database and a centralized cohort repository to store cohort SQL scripts and query results. The cohort repository and the clinical covariate tables from the pipeline can further support projects in advanced analytics and clinical modeling by clinical researchers, statisticians, or data scientists. 
Clinical electronic phenotyping, a process of constructing cohorts, requires frequent collaborations between informaticists and clinical experts. While informaticists help create the cohort scripts, clinical experts supervise and validate the script's results (lists of patient IDs) by reviewing its descriptive statistics and clinical feature distributions. The Solution dashboard aims to facilitate this iterative process of building and validating cohort SQL script by visualizing descriptive statistics for a selected cohort.


### Initial Situation
 **Current workflow and challenge:** 
 - Cohort SQL scripts are scattered across different studies, which makes it challenging to manage and reuse
 - Complex study queries involve multiple clinical concepts with complex temporal relationships, translating into lengthy SQL scripts. It heavily depends on the SQL experts (i.e., clinical informaticists) to review the codes. 
 - The query auditing process requires frequent communication between the analytic teams and clinical experts. Ad-hoc codes in Jupyter Notebooks produce the report.
 
**Data** 
To implement this Solution, the RWE integrates several data sources:
- OMOP patient database: [OMOP CDM v5.3](https://ohdsi.github.io/CommonDataModel/cdm53.html) or a later version.
- OMOP CDM Table Name Mapping (Optional): a json file mapping the custom table names to the standard OMOP table names
- Cohort SQL Scripts: each SQL script represents a "cohort" to be constructed
- Cohort Metadata:  a list of cohorts and metadata to indicate which cohorts should be uploaded or revised

For more details about the data model and required files, please read [Data Model article](article:3) and [Required Files article](article:5).

 **Goals:** 
- Establish an efficient RWD data pipeline generalizable to all OMOP databases, allowing the RWE team to build up a centralized cohort repository iteratively 
- A cohort dashboard providing descriptive statistics and clinical characteristics for a given patient cohort to facilitate communication for query auditing
- The centralized cohort repository and clinical covariate tables to support clinical researchers, statisticians, or data scientists conducting independent projects for advanced analytics and clinical modeling. 


### Insights
 **Install the Solution with Project Setup:** 
 1. Establish the RWD Pipeline: connect to the OMOP database and build the pipeline
 2. Build the cohort repository iteratively: upload cohort SQL scripts and metadata, then store the query results in batches
 3. Select a cohort for review: create a cohort dashboard to facilitate cohort review and communication
Please review [Walkthrough](article:4) for setup details. 

**Cohort Dashboard**
The dashboard visualizes the descriptive statistics and critical clinical characteristics to facilitate the cohort review process. It helps the clinical research team to examine whether the query captures the intended population. 
 ![dashboard-prevalence.png](Og7GVyxI7IZ0)
 ![dashboard-incidence.png](E88grsNkU0cV)
 ![cohort_demographics.png](d2E1nUznCZAe)
 ![dashboard-conditions.png](qEM7nSN4WAtM)
 ![dashboard-drugs.png](rA5Gsoqflzjj)
 ![dashboard-visits.png](50gXryX7ROOB)


### Business Impact
By implementing Dataiku's RWD Cohort Discovery Solution, the RWE team can:
- Establish an RWD pipeline compatible with OMOP databases and cohort SQL queries confirming OMOP conventions. Adopting the industry standard makes it easy to install and reproduce the query results on external OMOP databases. 
- Build a centralized cohort repository to facilitate cohort SQL script management and to support future analysis. 
- Generate a cohort dashboard to help with the query audition process between clinical experts and the analytic team. 

### Conclusion
With Dataiku's RWD Cohort Discovery Solution, the RWE team has transformed its RWD data pipeline and research query management. The RWD pipeline and cohort repository allow the research and analytic teams to share and reuse cohort queries, which encourages study generalizability and reproducibility. Finally, the cohort dashboard has greatly reduced the time for the teams to review cohort queries. 
