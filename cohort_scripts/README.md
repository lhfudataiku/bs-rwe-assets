# Cohort scripts

> **Lifecycle:** Canonical · **Part:** 2 · **Audience:** solution developers, QA and coding agents ·
> **Authority:** the cohort SQL scripts and metadata used to test the solution and configure the demo ·
> **Update when:** a script, metadata file or dialect folder is added, moved or retired.

Atlas cohort definitions rendered as SQL, one folder per SQL dialect, with the metadata files the
solution's "Create Cohort Scripts" scenario reads (`cohort_metadata` dataset + "Original Scripts"
folder). Upload a metadata file together with the scripts from the **same** folder: a script only
runs on the connection type its folder names. No file here holds patient data.

## Layout

| Folder | Dialect | Runs on | Contents |
| --- | --- | --- | --- |
| `snowflake/` | Snowflake | `bs-snowflake` | 52 scripts: `feature_condition_*`, `feature_drug_*`, `cohort_script_*` (monotherapy, inpatient outcomes, mortality, acute events), `cohort_untreated_htn` |
| `databricks/` | Databricks (Delta) | `bs-databricks` | 53 scripts: `features_cond_*`, `features_med_*`, `firstline_monotherapy_*`, `outcome_*`, `control_untreated_htn`, `cohort_script_*_db[_std]` |
| `redshift/` | Redshift | `redshift-solutions` | `c_anemia`, `c_dmt2`, `c_depression` |
| `postgre/` | PostgreSQL | none in this suite | Same three cohorts as `redshift/`; kept for reference |
| `mssql/` | SQL Server (Atlas default) | none | `cohort_script_acute_pancreatitis`; must be re-rendered from Atlas before use |

Root files:

- `omop_cdm_atlas.json`: the key map the solution uses (`cdm_standard_tables_map = omop_cdm_atlas`).
  It maps each OMOP table to the Atlas placeholder (`@cdm_database_schema.person`, …).
- `omop_cdm_test.json`: the same map without `cohort`, `cohort_definition`, `concept_ancestor` and
  `source_to_concept_map`.
- `omop_cdm_standard.json`: maps each table to its bare name, for scripts without Atlas placeholders.
- `us_sdoh_county_measure.csv`, `US States.csv`: public reference data (county SDOH measures, state
  abbreviations). `databricks/peak_flow_meter_codes.csv`: HCPCS codes.

## Metadata files

| File | Cohorts | Use |
| --- | --- | --- |
| `<dialect>/cohort_metadata_e4.csv` (snowflake, databricks, redshift) | 1 Anemia, 2 Diabetes mellitus type 2, 3 Depression | **Solution test set** (E4). Same ids, names and descriptions in every dialect, so counts compare across SF, DB and RS |
| `snowflake/cohort_metadata_demo.csv` | 1 Chronic kidney disease, 2 Depression, 3 Diabetes mellitus type 2 | Demo sample cohorts (as in `DEMO_SF_RWD`) |
| `snowflake/cohort_metadata_sf.csv` | 45 cohorts (101–135 features, 0–10 treatments and outcomes) | Demo cohort library on Snowflake |
| `snowflake/cohort_metadata_test.csv` | 133 opioid exposure, 10 untreated hypertension | Ad-hoc Snowflake tests |
| `databricks/cohort_metadata_test.csv` | 999 T2DM, 998 CKD (`cohort_script_*_db.sql`) | Ad-hoc Databricks tests |

The concept sets of the three test cohorts are identical in every dialect (anemia 7 concepts, T2DM
29, depression 19). Anemia keeps the **first** diagnosis per person.

## Rules and caveats

- The solution replaces a placeholder only when it follows whitespace
  (`return_script_cdm_tables`); write `FROM @cdm_database_schema.person`, never
  `(@cdm_database_schema.person`. Every script here passes that check.
- `@temp_database_schema.<prefix><name>` becomes the bare `<prefix><name>`. On Databricks those are
  real Delta tables in the connection's default catalog and schema. Scripts drop them at the end, so
  a failed run can leave them behind.
- Cohort ids must be unique within a metadata file, and filenames must match exactly: values are
  not trimmed.
- Not listed in any metadata file: `snowflake/feature_drug_antithrombotics.sql` (it references 8 ATC
  classes, not only B01A antithrombotic agents, so its definition needs checking), the Databricks
  feature/outcome library (no Databricks metadata for it yet) and the `_db_std` variants.
