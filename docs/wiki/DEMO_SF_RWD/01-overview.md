<span id="version" style="color: grey; float: right">Version 0.1.0</span><br/>

<div class="alert">
This project is demo only and, thus, should not be installed on customer instances.
</div>

### RWD/RWE Solution Demo Assets in Snowflake
- Part 1: OMOP Patient Datasets Preparation 
- Part 2: RWD Cohort Discovery Solution
- Part 3: RWE Advanced Analytics

This project is part 2 of the RWD/RWE demo assets.

# Real-World Data (RWD) Cohort Discovery

This solution provides a centralized repository to store and manage cohorts (clinical electronic phenotyping) from real-world data (e.g., electronic health records, medical claims data), adopting the [Observational Medical Outcomes Partnership (OMOP) Common Data Model (CDM)](https://www.ohdsi.org/data-standardization/) [Case Study & Walkthrough](article:2). It turns complex cohort SQL scripts into generalizable and reusable clinical electronic phenotyping for future advanced analytics. It also offers a quick dashboard to review the descriptive statistics and some of the clinical characterizations of a given cohort. 

Key beneficiaries include:
 - Biomedical informaticists: ingest and manage cohorts (clinical electronic phenotyping)
 - Clinical researchers: review and validate cohorts
 - Epidemiologists and health outcomes researchers: derive insights from the cohorts and extend their use for further advanced statistical or machine learning outcomes analysis (for example, in real-world evidence studies). 



# Key Outcomes
## Shareable and Reusable Datasets
The RWD pipeline creates the centralized  **cohort repository, clinical covariates, and cohort features** . These datasets can support independent analytic projects, including business analysis, statistical estimation, and clinical modeling. Wiki [Output Datasets](article:26) for more details.

### Centralized Cohort Repository 
The OMOP standardized results schema table " **cohort** " and " **cohort_definition** "store patient cohorts that are shareable and reusable for future analysis. For example, users can select and join cohorts to create a population of interest (eligible patients, clinical features, and outcomes) for statistical analysis and clinical prediction modeling. 

### Clinical Covariates
The pipeline generates critical characteristics, including demographic, geographic, and OMOP clinical group concepts, on a population level. They are the standard concepts from the OMOP Standardized Vocabularies hierarchy. These covariates can generate population descriptive statistics and are useful for fast feature generation in advanced analytics. 

### Cohort Features
These datasets are filtered down to a selected cohort (as part of the cohort dashboard's outputs). They are ready-to-use materials for business analytic projects on a cohort of interest.

## Cohort Dashboard
The dashboard visualizes descriptive statistics and clinical characterizations of a cohort to facilitate communication and validation of a cohort query. 

### Cohort Descriptive Statistics
The first part of the dashboard provides general statistics of a selected cohort: incidence and prevalence, demographics, and disease burden. 

![overview-dashboard-cohort-stats.png](LDq12lZcK0l3)
![overview-dashboard-cohort-demo.png](CenZdBrCZZQO)
![overview-dashboard-cohort-others.png](p05Wa2u8VM3n)


### Cohort Covariates
The second slide describes the distribution of three predefined clinical covariates (clinical condition groups, drug groups, and clinical visits).

![overview-dashboard-covariates-1.png](nPtHDGyekNqA)
![overview-dashboard-covariates-2.png](Sjep6M01Tiq5)