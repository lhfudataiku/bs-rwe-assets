## Case Study: first-line antihypertensive drugs treatment effect on cardiovascular outcomes
This project replicates part of the [LEGEND HTN study](https://pmc.ncbi.nlm.nih.gov/articles/PMC6924620/), a large-scale comparative effectiveness observational health research published in the Lancet in 2019. 


### Project Background
A research team at a medical center (one of the multiple centers affiliated with a large hospital system in the US) is intrigued by the discrepancy between the US, European, and Asian guidelines on first-line hypertensive drugs for newly diagnosed patients. They want to replicate the methodology from the LEGEND HTN study to investigate the treatment effects on the patient population within the hospital system. By leveraging Dataiku's RWD Cohort Discovery Solution, the resident can easily reuse the cohorts and clinical covariates built by the real-world evidence team to construct observational health research at their fingertips. 

### Initial Situation
 **Current workflow and challenge:** 
 The hospital system encourages all clinical research teams to share their methodology and codes on the internal code repository. However, the codes from observational health research that construct the clinical cohorts are often very complicated and not easy to reuse. 
 Most studies save their code on Jupyter Notebooks or R Studio. It's difficult to validate them even within the organization, let alone externally.
 
 **Data:** 
Thanks to the OMOP initiatives led by the RWE team, they have adopted the OMOP CDM for their  **patient claims data**  covered by the organization and deployed  **Dataiku's RWD Cohort Discovery Solution**. The RWE team has pre-built a set of commonly requested clinical phenotypes (clinical cohorts) into the Solution. All researchers within the organization can access this Solution and export the cohort and clinical covariates for analysis.

**Goals:** 
- Create a real-world evidence project to host an observational health research
- Import cohort and clinical covariates datasets from Dataiku's RWD Cohort Discovery Solution
- Identify the control/treatment group, outcomes, and clinical features; define the temporal constrain to construct the final cohort for statistical analysis
- Estimate the propensity score-adjusted COX survival analysis of first-line antihypertensive drug treatment effect on cardiovascular outcomes using the VisualML and Python recipe.
- Visualize the research result via the Dashboard

### Insights and Analytics
**Setup the Project** 
Create a new project and import the deliverable datasets from the **Dataiku's RWD Cohort Discovery Solution**. 

| Dataset name               | Domain                         |
|----------------------------|--------------------------------|
| cohort                     | OMOP result schema             |
| cohort_definition          | OMOP result schema             |
| concept                    | OMOP standardized vocabularies |
| concept_ancestor           | OMOP standardized vocabularies |
| visit_occurrence_labeled   | OMOP clinical covariates       |
| person_location_joined     | OMOP clinical covariates       |
| drug_exposure_grouped      | OMOP clinical covariates       |
| condition_group_occurrence | OMOP clinical covariates       |
| charlson_score_occurrence  | OMOP clinical covariates       |

**Identify the Control/Treatment Group, Outcomes, and Baseline Clinical Features for Survival Model**
Select cohorts from the cohort dataset and define the control/treatment group, outcomes, and baseline clinical features, respectively, for survival analysis.

| Clinical phenotype name                                        | Definition                                                                                                                                                                                                                         | Function type            |
|----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------|
| Untreated hypertension                                         | patients with at least two records of hypertension without any antihypertensive drugs exposure                                                                                                                                      | Control group            |
| Firstline monotherapy angiotensin-converting enzyme inhibitors | New users of ACE inhibitors as first-line monotherapy for hypertension                                                                                                                                                             | Treatment group          |
| Inpatient heart failure                                        | a heart failure diagnosis during an ER/IP encounter                                                                                                                                                                                | Cardiovascular outcome   |
| Inpatient stroke                                               | a diagnosis of cerebrovascular events during an ER/IP encounter                                                                                                                                                                    | Cardiovascular outcome   |
| Inpatient acute myocardial infarction                          | an acute myocardial infarction diagnosis during an ER/IP encounter                                                                                                                                                                 | Cardiovascular outcome   |
| CV death                                                       | Death record with at least one cardiovascular-related condition record (myocardial infarction, ischemic stroke, intracranial hemorrhage, sudden cardiac death, hospitalization for heart failure) in 30 days before death          | Cardiovascular outcome   |
| Acute GI bleeding                                              | A GI bleeding diagnosis during an ER/IP encounter                                                                                                                                                                                  | Clinical characteristics |
| Acute respiratory disease                                      | an acute respiratory disease diagnosis                                                                                                                                                                                             | Clinical characteristics |
| Atrial fibrillation                                            | First diagnosis at ER/IP, or one diagnosis followed by another diagnosis, or at least two records of anticoagulants, or proceeded by an EKG procedure                                                                              | Clinical characteristics |
| Anemia                                                         | first diagnosis of anemia                                                                                                                                                                                                          | Clinical characteristics |
| Cardiovascular events                                          | One diagnosis of AMI, HF, or sudden cardiac death between the date of start and the date end of an ER or IP visit.                                                                                                            | Clinical characteristics |
| Cerebrovascular events                                         | One diagnosis of ischemic stroke, hemorrhagic stroke, or TIA between the date start and the date end of an ER or IP visit.                                                                                                 | Clinical characteristics |
| Chronic liver diseases                                         | First diagnosis of chronic liver disease (alcoholic, non-alcoholic, autoimmune hepatitis, or cirrhosis)                                                                                                                            | Clinical characteristics |
| Chronic kidney disease                                         | First diagnosis followed by at least two records of dialysis procedures or observations throughout records, or second diagnosis at least 30 days apart.                                                                             | Clinical characteristics |
| Chronic obstructive pulmonary disease                          | first diagnosis of COPD                                                                                                                                                                                                            | Clinical characteristics |
| Coronary arteriosclerosis                                      | first diagnosis                                                                                                                                                                                                                    | Clinical characteristics |
| Dementia                                                       | first diagnosis                                                                                                                                                                                                                    | Clinical characteristics |
| Depression                                                     | first diagnosis followed by at least two records of antidepressant or depression procedure within 30 days, or second diagnosis in the following history.                                                                            | Clinical characteristics |
| Diabetes mellitus type 2                                       | The first condition record of Type 2 Diabetes Mellitus, which is followed by another Type 2 Diabetes Mellitus condition record, at least two drugs used to treat Type 2 diabetes, or at least 2 HbA1c measurements with value > 6.5% | Clinical characteristics |
| Gastroesophageal reflux disease                                | First diagnosis followed by at least another diagnosis or having at least two GERD medication records at any time.                                                                                                                 | Clinical characteristics |
| HIV infection                                                  | first diagnosis followed by at least another diagnosis or at least two GERD medication records.                                                                                                                                    | Clinical characteristics |
| Hyperlipidemia                                                 | first diagnosis                                                                                                                                                                                                                    | Clinical characteristics |
| Non-skin malignant neoplasms                                   | First, non-skin cancer malignant malignancy followed by at least two diagnoses of the same neoplasm type.                                                                                                                           | Clinical characteristics |
| Obesity                                                        | first diagnosis                                                                                                                                                                                                                    | Clinical characteristics |
| Osteoarthritis                                                 | first diagnosis                                                                                                                                                                                                                    | Clinical characteristics |
| Peripheral vascular disease                                    | first diagnosis                                                                                                                                                                                                                    | Clinical characteristics |
| Rheumatoid arthritis                                           | first diagnosis                                                                                                                                                                                                                    | Clinical characteristics |
| Schizophrenia                                                  | one diagnosis followed by at least one diagnosis or two records of antipsychotics or psychiatric procedures.                                                                                                                      | Clinical characteristics |
| Urinary tract infection                                        | one diagnosis                                                                                                                                                                                                                      | Clinical characteristics |
| Venous thromboembolic events                                   | One diagnosis of pulmonary embolism or deep vein thrombosis                                                                                                                                                                        | Clinical characteristics |
| Drug exposure: anti-acid agents                                | ATC drug group: A02                                                                                                                                                                                                                | Clinical characteristics |
| Drug exposure: antidepressant                                  | ATC drug group: N06A                                                                                                                                                                                                               | Clinical characteristics |
| Drug exposure: antiepileptics                                  | ATC drug group: N03                                                                                                                                                                                                                | Clinical characteristics |
| Drug exposure: anti-inflammatory & anti-rheumatoid             | ATC drug group: H02 & M01A                                                                                                                                                                                                         | Clinical characteristics |
| Drug exposure: antineoplastics                                 | ATC drug group: L01                                                                                                                                                                                                                | Clinical characteristics |
| Drug exposure: insulin & blood sugar lowering agents           | ATC drug group: A10A, A10B                                                                                                                                                                                                         | Clinical characteristics |
| Drug exposure: lipid modifying agents                          | ATC drug group: C10                                                                                                                                                                                                                | Clinical characteristics |
| Drug exposure: med for obstructive airways                     | ATC drug group: R03                                                                                                                                                                                                                | Clinical characteristics |
| Drug exposure: opioid                                          | ATC drug group: N02A                                                                                                                                                                                                               | Clinical characteristics |
| Drug exposure: psycholeptics                                   | ATC drug group: N05                                                                                                                                                                                                                | Clinical characteristics |
| Drug exposure: systemic antibacterials                         | ATC drug group: J01                                                                                                                                                                                                                | Clinical characteristics |
| Demographics                                                   | Sex & Age                                                                                                                                                                                                                          | Clinical characteristics |
| Clinical encounters                                            | clinical visits within 365 days                                                                                                                                                                                                    | Clinical characteristics    |

![flow-cohorts.png](JpuxbJd8KfQs)

**Extract Clinical Covariates for Propensity Score Estimation**
Use the most frequent clinical covariates as potential confounders.

| Covariates type               | Constrains                                                                                                                            |
|-------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| OMOP condition concept groups | At least one occurrence within 365 days before cohort entry. ^Top four levels of SNOMED concepts of medical conditions and observations. |
| OMOP drug groups              | At least one occurrence within 365 days before cohort entry. ^ATC level 3 drug class                                                   |
| OMOP clinical encounters      | At least one occurrence within 30 days before cohort entry. OMOP encounter types                                                      |
| OMOP demographic features     | Sex and Age group                                                                                                                     |

![flow-covariates.png](ubSiND19Hf5a)

**Construct the Final Cohort for Statistical Analysis**
Join the control/treatment group, outcomes, baseline clinical features, and clinical covariates into final cohort datasets for statistical estimation.
![flow-final-cohort.png](UrW4Knoj86pq)

**Estimate the Propensity Score Adjusted COX Survival Model**
Estimate the Propensity Score using the [VisualML recipe](saved_model:s5JNBi55). The propensity score represents the probability of receiving the intervention. Once we have the propensity score, we can calculate the inverted probability weight to balance the biases between the control and treatment groups to estimate the actual treatment effect. 
Then, we use the COX survival model from the Python package "lifelines" to estimate the hazard ratio of the treatment effect of the select first-line hypertension drugs on cardiovascular outcomes. 
![flow-survival-model.png](Q3trOyXrWLg0)

**Review the Results on the Dashboard**
Review the control and treatment cohorts' descriptive statistics.
![dashboard-general.png](13Xvbvvj8A17)

Review the results of the propensity score-adjusted COX survival analysis. 
![dashboard-survival-analysis.png](ZesVOFuzRfoI)

### Conclusion
By leveraging Dataiku's RWD Cohort Discovery Solution, the clinical research team can:
- Create a dynamic pipeline to compile clinical phenotypes (e.g., the "cohorts" from the cohort datasets) easily into datasets ready for advanced analytics to answer clinical research questions.
- The modulated clinical phenotypes allow the decomposition of complex code into Dataiku flow components, which facilitates research method validation and communications
- Promote generalizability and replicability for observational health research.


