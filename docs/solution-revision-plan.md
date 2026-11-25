# RWD Cohort Discovery — Solution Revision Plan (E5)

> **Lifecycle:** Planning (active until phase 4 of the migration plan closes) · **Part:** 2 ·
> **Audience:** solution developers, asset owners and coding agents · **Authority:** scope, design and
> order of the `SOL_RWD_COHORT_DISCOVERY` revision before the demo suite is recreated · **Update when:**
> an item's design, status or verification changes.

## Summary

`SOL_RWD_COHORT_DISCOVERY` passes the migration plan's E gate: it runs the `v1-2` library from this
repo, Project Setup shows no errors, and E4 gave identical cohort counts on `PREP_RWD_SF_1K`,
`PREP_RWD_DB_1K` and `PREP_RWD_RS_1K` (611, 593, 247). It is not ready to release. Three backlog tickets
change Project Setup, and the review behind this plan found defects in how the solution writes cohorts.

This revision is phase 4 of the [migration plan](migration-revision-plan.md#sequencing-gates-and-risks),
between the data layer (phase 3) and the demo suite (phase 5). D1 copies the released solution into
`DEMO_SF_RWD`, so revising first avoids building the demo twice. D2 steps 3–7 (the RWE Cox report) do not
depend on this work and can run in parallel. `v1-2` is merged into `main` and closed (2026-11-20). The
revision is on branch `solution-revision-v1-2`, cut from `main` at `c0a1b01`, and ships as 1.2.0, which
has not been released yet. The solution pulls `python/solution` from `solution-revision-v1-2` (public
repo, no stored credentials since 2026-11-23); each resync needs the owner's approval.

A later v2.0, the Cohort Workbench webapp, is proposed separately in
[`proposal-v2-cohort-workbench.md`](proposal-v2-cohort-workbench.md). It builds on R4–R7 and would
supersede R2 and R3. This plan stays the scope of 1.2 until the owner decides otherwise.

| Item | Topic | Source |
| --- | --- | --- |
| [R1](#r1-cohort-script-table-naming-ticket-1) | Cohort script table naming replaces the custom JSON mapping | Ticket 1 |
| [R2](#r2-cohort-registration-ticket-2) | Cohort registration: repeated submissions, list of built cohorts, guard against id overwrite | Ticket 2 |
| [R3](#r3-dashboard-for-all-cohorts-ticket-3) | Cohort characterization in FeatureExtraction's format, each cohort precomputed against the population, two chosen cohorts compared on request, with standardized differences; dashboard filtered by cohort; dashboard section removed from Setup (revised 2026-11-24) | Ticket 3 |
| [R4](#r4-resolved-table-paths) | `sql_script_function.py`: table paths resolved by DSS | Review |
| [R5](#r5-cohort-build-as-one-static-recipe) | Cohort build as one static recipe instead of the `create_cohort` scenario chain | Review |
| [R6](#r6-databricks-temporary-tables) | Databricks temporary tables left behind | Review |
| [R7](#r7-project-variables) | Project variables: one scope per purpose | Review |
| [R8](#r8-code-environment) | Code environment: instance default | Review |

The review read the live Setup manifest, all 16 scenarios, the library references, the project variables,
the flow (64 recipes, 66 datasets, 30 insights) and this repo's `solution/` code on 2026-11-20. Nothing in
DSS was changed for it.

## Current Project Setup

| Section | Tiles | What the user does today |
| --- | --- | --- |
| S1 Connection Reconfiguration | connections, SQL pipeline toggle, "Reconfigure" | One-time |
| S2 Connect OMOP CDM Standard Tables | prep project, table multiselects, 30 table selects, "Import" | One-time |
| S3 OMOP CDM Custom Table Name Mapping (optional) | upload a JSON file, type its filename, "Verify" | One-time, by hand |
| S5 Upload Cohort SQL Scripts & Cohort Metadata | upload scripts, upload a 4-column CSV, "Create cohort definition and scripts", link to mapped scripts | Per submission |
| S6 Write Cohort to Datasets | "Write Cohort", links to explore `cohort`, `cohort_definition`, `cohort_building_log` | Per submission |
| S8 Create Cohort Dashboard | pick one cohort, "Rebuild Cohort Dashboard", dashboard link | Per cohort viewed |

## R1. Cohort script table naming (ticket 1)

**Today.** The rewriting step needs to know how uploaded scripts name OMOP tables. The user uploads a JSON
file mapping 37 table keys to placeholders (the shipped `omop_cdm_atlas.json`), types its filename into
`cdm_standard_tables_map`, and runs "Verify OMOP Table Variables Mapping", which only checks that every key
is present. Without a file, scripts must use bare table names. In practice there are two styles: Atlas
placeholders (`@cdm_database_schema.<table>`, `@vocabulary_database_schema.<table>`,
`@target_database_schema.@target_cohort_table`) and bare OMOP names.

**Proposal.** A one-time choice in S2, next to the table mapping:

- `cohort_script_table_naming` (SELECT): **OHDSI Atlas placeholders** (default), **Plain OMOP table
  names**, or **Custom prefix**; with `cohort_script_table_prefix` (STRING) for the third, applied to every
  CDM table (for example `cdm.`).
- `solution/setup/table_naming.py` (new, pure, unit-tested) builds the key map from the choice. The Atlas
  style reproduces `omop_cdm_atlas.json` exactly; a test compares them.
- Script ingestion (R2) scans each script for `@<schema>.<table>` references the map does not cover and
  names them in the error, so a wrong choice fails with a readable message before any SQL runs.
- Remove S3, the "OMOP CDM table variable mapping" folder (`4ktqvA1F`), `cdm_standard_tables_map` and the
  "Check OMOP Table Variables Mapping" scenario (and its call from "Create Cohort Scripts").

**Not proposed.** Per-table overrides. No script in `cohort_scripts/` needs one. If a customer does, a
MAP parameter can be added to the same tile later.

## R2. Cohort registration (ticket 2)

**Today.** Scripts go into "Original Scripts" (`PqOBn6B3`); a CSV with `cohort_definition_id`,
`cohort_definition_name`, `cohort_definition_description` and `cohort_sql_script_filename` goes into the
uploaded dataset `cohort_metadata`. "Create Cohort Scripts" copies it, checks columns, nulls and filenames,
writes mapped scripts and rewrites the runtime SQL recipe `compute_cohort_definition`. Its SQL does
`DELETE FROM cohort_definition WHERE id IN (...)` then inserts, and recreates `uploaded_cohort_definition`
with the current batch only. "Write Cohort" then builds that batch.

What this means for repeated submissions:

- They mostly work: `cohort_definition`, `cohort` and `cohort_building_log` accumulate across batches.
- **A reused id silently replaces a cohort.** Its definition row is deleted and reinserted, and each Atlas
  script starts with `DELETE FROM @target_database_schema.@target_cohort_table WHERE cohort_definition_id
  = @target_cohort_id`, so the old cohort's rows go too. Re-uploading a file with an existing name
  overwrites it in "Original Scripts" with no warning either.
- **Names and descriptions are pasted into SQL inside single quotes without escaping**
  (`map_cohort_script_paths.py`, `write_cohorts.py`). A cohort named "Crohn's disease" breaks the
  definition and log SQL.
- Nothing in Setup shows which cohorts already exist; the S6 links open the raw datasets.

**Proposal.** Replace the CSV upload with two custom tiles (the HTML/JS + Python `do()` pattern the
prep-project select box already uses; the Python is inlined by `tools/app_manifest.py`, since tiles
cannot import the project library on DSS 15.2).

1. **Upload cohort SQL scripts** (unchanged).
2. **Register cohorts** (new). `do()` lists the scripts in "Original Scripts" and matches them against
   `cohort_definition` and the last submission. One row per script:

   | Column | Behaviour |
   | --- | --- |
   | File | Read-only. Marked *new*, *registered as cohort N* or *changed since registration* |
   | Cohort id | Suggested: the next free id. Editable |
   | Name | Prefilled from a `-- name:` comment in the script, else from the filename. Required |
   | Description | Prefilled from `-- description:` if present. Optional |
   | Submit | Ticked for new files, unticked for registered ones |
   | Replace | Only offered when the id already exists. Unticked by default |

   Inline checks: unique ids in the batch, positive integers, a name on every submitted row, and a
   conflicting id needs **Replace**. Saving writes the batch to the project variable `cohort_submission`
   (JSON). Then the existing button runs ingestion.
3. **Built cohorts** (new, read-only). `do()` reads `cohort_definition` and the latest
   `cohort_building_log` row per id: id, name, description, script, subject count, status, last built. This
   answers "can we display the built cohorts' metadata": yes, the same way the cohort select box reads
   `cohort_definition` today.

Ingestion repeats every check against the data, because the tile is a convenience and the scenario is the
authority. An id that exists in `cohort_definition` without **Replace** fails the run and names the
conflicting cohorts. A Python recipe materialises `cohort_submission` into a dataset, replacing the
uploaded `cohort_metadata` and its copy. Every literal written into SQL goes through one dialect-aware
helper (`''` on Snowflake and Redshift, `\'` on Databricks), with unit tests on names containing quotes.

**Open question.** Keep the CSV as a hidden bulk-import path feeding the same validation, or drop it.
Recommendation: drop it; the 45-cohort demo library can be registered once by a helper script in
`tools/`.

## R3. Dashboard for all cohorts (ticket 3)

**Today.** One recipe, `compute_cohort_definition_filtered`, keeps the cohort chosen in
`${cohort_definition_id}`. 30 datasets depend on it; the dashboard "Cohort Discovery Insights" (2 pages)
shows 25 charts and 5 statistics cards from 11 of them. Switching cohorts means picking one in S8 and
force-rebuilding about 20 datasets.

**Proposal (superseded on 2026-11-24 by [R3 as decided](#r3-as-decided-owner-2026-11-24)).** Precompute
every cohort and filter on the dashboard.

- Drop the `${cohort_definition_id}` filter. Carry `COHORT_DEFINITION_ID` and `COHORT_DEFINITION_NAME`
  through the 30 downstream datasets. Four chart datasets lose the id today
  (`cohort_condition_group_prevalence_prepared`, `cohort_drug_group_prevalence_prepared`,
  `cohort_location_prepared`, `popoulation_cohort_charlson_score`). Recipes to change, at least:
  - groupings `compute_cohort_count`, `compute_cohort_location`,
    `compute_cohort_condition_group_first_by_CONCEPT_NAME`,
    `compute_cohort_condition_group_first_by_CONCEPT_NAME_1`, `compute_cohort_charlson_score`,
    `compute_population_cohort_charlson_event_count`: add the cohort id to the keys;
  - window `compute_population_w_cohort_first_occurrence`: partition by cohort id and `PERSON_ID`, since
    one person can belong to several cohorts;
  - joins that match on `PERSON_ID` alone: add the cohort id;
  - prevalence denominators: per cohort.
- Add a single-select, required dashboard filter on `COHORT_DEFINITION_NAME` to both pages.
- Build the dashboard datasets at the end of "Write Cohort" (R5), so a new cohort appears without a manual
  step. Rename "Build Cohort Dashboard" to "Refresh Dashboard" and keep it for manual use.
- Remove S7/S8, the `cohort_definition_id` variable and its select tile.

**Costs and checks.**

- Person-level datasets grow with total cohort membership (sum over cohorts), not with population size.
  This all runs in-database. If a full rebuild becomes slow at 2.3M with 45 cohorts, partition the
  datasets by cohort id and rebuild only new partitions.
- Dashboard filters do not filter statistics cards (spike, 2026-11-20). Replace the 5 statistics cards
  with charts on the same columns, and frequency tables with dataset-table tiles on a per-cohort summary
  dataset. Charts and dataset tables are the only filterable tile types in DSS 15.
- Prevalence and covariate figures must equal today's single-cohort results for the same cohort; compare
  the three E4 cohorts before and after.

**Step 4 findings (2026-11-24, read from SOL's flow, dashboard and 30 insights; nothing changed).**

- **Cohort against control needs the whole population per cohort.**
  - Five dashboard figures compare the cohort with everyone else in the population:
    - sex and race (`population_cohort_demographic_prepared`);
    - Charlson score (`popoulation_cohort_charlson_score`);
    - age (`population_w_cohort_first_occurrence`);
    - incidence by county (`cohort_location_prepared`).
  - Each is a left join of the population on the one filtered cohort, then `COHORT_FLAG`.
  - With every cohort precomputed, "control" differs per cohort. Carrying the cohort id through
    these joins means one copy of the population per cohort.
  - At 2.3M persons and 50 cohorts, that is over 100M rows per person-level dataset, several
    times that for the covariate rows. The cost estimate above ("grows with total cohort
    membership") holds only for the cohort-side datasets.
- **The charts sample.**
  - All 22 charts run on the DSS engine, 14 of them on a head sample of the dataset (the first
    10,000 rows by default) and 8 on the full dataset.
  - With all cohorts in one dataset, a head sample holds the first cohorts only, so a filtered
    chart would be wrong or empty for later cohorts.
  - On the 2.3M population the person-level charts already read only the first rows today.
- **Recommended design: per-cohort aggregates.** Each dashboard dataset becomes a small table
  keyed by cohort, for example (cohort id, cohort name, group, category, persons).
  - The population totals are computed once, the cohort counts per cohort, and control = total
    − cohort.
  - Rows grow with cohorts × categories, not with the population. The charts read the full
    dataset, so the filter is exact. The 5 statistics cards become charts or dataset tables on
    these aggregates.
  - Cohort-only figures (prevalence by quarter, condition, drug and visit covariates) keep
    person- or event-level rows with the cohort id added, as planned.
- **Alternative: per-cohort copies of the population (as R3 reads now).**
  - Fewer recipe changes, but the dataset size above applies.
  - The charts would have to move to the full dataset or to in-database aggregation.

### R3 as decided (owner, 2026-11-24)

**Discussion summary (2026-11-24).**

- **Dialect check.** Registration did not check that a script's SQL fits the connection. It now does
  (step 3, `solution/setup/sql_dialect.py`).
- **Atlas sample.** Five atlas-demo cohorts were rendered for Snowflake, Databricks and Redshift.
  - The three dialects share one statement skeleton and the same placeholders. They differ only in
    scratch tables, date arithmetic and a few clauses.
  - A cohort built here is therefore exactly an Atlas cohort, and Atlas-style characterization
    applies to it.
- **Pairwise comparison (owner's point 1).** Atlas recomputes for each characterization job, but
  the standardized difference itself is arithmetic on two cohorts' stored figures. Stored per
  cohort, any pair is a join, with nothing rebuilt.
- **Our covariates against Atlas's (point 2).** Today's dashboard is a hand-built subset of what
  FeatureExtraction, the covariate library behind Atlas, computes:

  | Today | FeatureExtraction preset |
  | --- | --- |
  | Sex, race | DemographicsGender, DemographicsRace |
  | Age | DemographicsAge, DemographicsAgeGroup |
  | Cohort duration, prior and follow-up observation | DemographicsTimeInCohort, DemographicsPriorObservationTime, DemographicsPostObservationTime |
  | Charlson score (own categories; fewer than 2 occurrences counts 0) | CharlsonIndex (Romano adaptation) |
  | Condition groups | ConditionGroupEra, in windows before index |
  | Drug groups | DrugGroupEra, in windows before index |
  | Visits by type | VisitConceptCount, in windows before index |
  | Before and after cohort start | no preset looks after index |

- **Downstream (point 3).** `DEMO_SF_RWE` reads 9 datasets, today from `DEMO_DB_RWD2` and after D2
  from `DEMO_SF_RWD`:
  - `cohort`, `cohort_definition`, `concept` and `concept_ancestor`;
  - the 5 person-level covariate tables `charlson_score_occurrence`, `condition_group_occurrence`,
    `drug_class_exposure`, `person_location_joined` and `visit_occurrence_labeled`.

  It reads none of the 30 dashboard datasets. Its propensity and Cox models need person-level
  features, which FeatureExtraction's aggregated output does not give.
- **v2.0 (point 4).** The v2.0 proposal already plans FeatureExtraction presets, results stored per
  cohort and a two-cohort comparison. Tables in that format let v2.0 change only what fills them.

**Decisions (owner, 2026-11-24).**

1. **Reference group: the population.** The cohort is compared with the whole population, not with
   "everyone else". The population is characterized once per import and shared by every cohort.
   There is no per-cohort copy of the population.
2. **Format and definitions: FeatureExtraction's.** The results are written as FeatureExtraction's
   aggregated output:
   - binary covariates: cohort, covariate, sum and average;
   - continuous covariates: cohort, covariate, count, minimum, maximum, average, standard
     deviation, median and the 10th, 25th, 75th and 90th percentiles;
   - `covariate_ref` and `analysis_ref`, with covariate ids as FeatureExtraction defines them.
3. **Standardized differences are added.** Each cohort is compared with the population:
   - binary: `(p1 − p2) / sqrt((p1(1−p1) + p2(1−p2)) / 2)`;
   - continuous: `(m1 − m2) / sqrt((s1² + s2²) / 2)`.
4. **Covariates: FeatureExtraction presets only.** No hand-built covariates and no after-index views
   on the dashboard.
5. **The population** is every person with at least 365 days of observation. Their index date is one
   year after the start of their first observation period, and the end is the end of that period,
   so every long-term window is a full year.
6. **Presets and windows:**
   - DemographicsGender, DemographicsRace, DemographicsAge, DemographicsAgeGroup,
     DemographicsTimeInCohort, DemographicsPriorObservationTime and
     DemographicsPostObservationTime;
   - CharlsonIndex;
   - ConditionGroupEra and DrugGroupEra, in the long-term window (365 days before index) and any
     time prior;
   - VisitConceptCount in the long-term window only (owner, 2026-11-25): FeatureExtraction has no
     any-time-prior visit preset.
7. **Prevalence by quarter and incidence by county stay** as cohort-level views. They are not
   covariates, and the v2.0 proposal keeps them too.
8. **Standardized differences between two cohorts are added**, as well as against the population.
9. **What is precomputed, and what is computed on request** (owner, 2026-11-24). Results that every
   comparison reuses are precomputed, incrementally. A comparison between two chosen cohorts is
   computed on request. The earlier draft precomputed every pair, which grows with the square of
   the number of cohorts.
10. **A requested comparison runs as a scenario and is cached** (owner, 2026-11-24), in
    `covariate_balance` next to the precomputed rows against the population. The table keeps every pair computed so far. A pair already in the cache is not
    computed again.
11. **Project Setup has no dashboard section** (owner, 2026-11-24; R3 as first proposed). Neither
    the dashboard nor the comparison is driven from Setup.
12. **A code webapp requests comparisons** (owner, 2026-11-24). It selects the cohorts, runs the
    scenario, and is inserted into the dashboard as a webapp tile.
13. **Cohort B defaults to the population** (owner, 2026-11-24). That pair is precomputed, so the
    default never runs a scenario.

**Design.**

- **Engine.** FeatureExtraction's SQL templates (Apache-2.0) for the chosen presets are rendered
  offline, once per dialect, and checked into the repo like `cohort_scripts/`.
  - The table names stay as placeholders, mapped as in R1.
  - They run with the R5 build machinery: statement splitter, Databricks scratch tables, one
    session with its commit.
  - No SQL renderer runs inside DSS; the renderer port stays in v2.0 (its M3).
  - Rendering needs Java (available locally, OpenJDK 21) and the SqlRender jar.
- **When.**
  - After "Build cohorts", for the cohorts of the batch only: delete and insert by cohort id, as
    the cohort build does.
  - The population, after "Import Datasets".
  - Standardized differences against the population, for the batch's cohorts.
- **Precomputed (reused by every comparison), incrementally:**

  | Result | Computed | Size |
  | --- | --- | --- |
  | Covariates of each cohort (`covariate`, `covariate_continuous`) | once per cohort, when its batch is built | cohorts × covariates |
  | Covariates of the population | once per import | covariates |
  | Balance of each cohort against the population (`covariate_balance`, comparator −1) | with the cohort's covariates | cohorts × covariates |
  | `covariate_ref`, `analysis_ref` | added to as new covariates appear | covariates |

  - A cohort is never recomputed unless it is rebuilt, and the population only when the data is
    re-imported.
  - Everything grows linearly with the number of cohorts. As an estimate, 50 cohorts at about
    2,000 covariates each give about 100,000 rows per table.
- **On request: a comparison between two chosen cohorts.**
  - The standardized differences of a pair are arithmetic on the two cohorts' stored aggregates:
    one SQL statement that joins about 2 × 2,000 rows. It never reads person-level data.
  - One library function builds that statement, `pair_balance_sql(cohort_a, cohort_b)`. The 1.2
    mechanism calls it now, and the v2.0 webapp later calls the same function at query time.
  - In 1.2 it runs as a scenario, "Compare cohorts", whose results are cached in
    `covariate_balance` (decision 10). The request does not come from Setup (decision 11).
  - **One balance table.** `covariate_balance` has one row per cohort, comparator and covariate:
    the two values and the standardized difference. The comparator is −1 for the population
    (precomputed) or a cohort id (computed on request). Every comparison, the default one
    included, is read the same way.
  - **Request: the "Compare cohorts" webapp** (decision 12). It is a standard DSS code webapp: HTML
    and JS, with a Python backend. It is inserted into dashboard page 2.
    - It lists the built cohorts from `cohort_definition` and `cohort_building_log`. The user
      picks cohort A, and cohort B, which defaults to "Population" (decision 13).
    - If the pair is already in `covariate_balance`, as the population always is, the webapp says
      so, and no scenario runs.
    - Otherwise the backend appends the pair to `comparison_requests` (who asked, and when), runs
      "Compare cohorts", and polls the run. It shows "computing", then "done: select the pair in
      the page filter", or the run's error as a sentence.
    - The logic lives in the project library (`solution/compare/`). Webapp backends, unlike Setup
      tiles, can import it.
    - The backend stays thin, so the v2.0 Cohort Workbench (FastAPI) can reuse the same services.
  - **Cache.**
    - "Compare cohorts" computes only the requested pairs that are missing from
      `covariate_balance`, and writes them by delete and insert per pair.
    - When a cohort is rebuilt (Replace), its rows against the population are recomputed with it,
      and its rows against other cohorts are deleted, to be recomputed on the next request. When
      the data is re-imported, everything is recomputed and the rows against other cohorts are
      cleared.
- **Dashboard.**
  - One single-select filter on the cohort. Its page shows the cohort against the population
    (precomputed), plus the quarterly prevalence and county incidence views.
  - A second page shows the requested comparison of two cohorts.
  - Every chart reads a small table in full, so no chart samples.
  - The 5 statistics cards become charts or dataset tables.
  - "Build Cohort Dashboard" becomes "Refresh Dashboard", for manual use.
- **Removed.**
  - The 29 recipes and 30 datasets downstream of `compute_cohort_definition_filtered`, after a
    backup;
  - Setup's dashboard section;
  - `cohort_definition_id` and its tile wrapper `section8_tile1.py`.
- **Kept.** The 5 person-level covariate tables, unchanged, as the contract with `DEMO_SF_RWE`.
- **For the decision register** (meets its admission rule; to add when the owner agrees): the
  FeatureExtraction result format as the contract between 1.2, the demo copy and v2.0, and the 5
  person-level tables as the contract with `DEMO_SF_RWE`.

### Step 4 part 0: today's figures mapped to the presets (2026-11-25)

Read from SOL's dashboard "Cohort Discovery Insights", its 30 insights and the recipes behind them,
and compared with FeatureExtraction's `PrespecAnalyses.csv`, `DomainConceptGroup.sql`,
`CharlsonIndex.sql`, `DemographicsTime.sql` and `DemographicsAgeGroup.sql` from its `main` branch.
Part 1 pins a release, and part 2 checks these findings again against it. Nothing was changed.
`${days_prior_to_cohort_startdate}` is 365 on SOL.

**Page 1, "Cohort Descriptive Statistics".**

| Today's figure (dataset) | How it is computed today | Becomes | Differs because |
| --- | --- | --- | --- |
| Sex, chart and frequency card (`population_cohort_demographic_prepared`, `population_cohort_sex`) | distinct persons per gender concept, cohort against control (everyone else) | DemographicsGender (1): share per gender concept | the reference is the population (decision 5), not "everyone else"; FeatureExtraction counts cohort entries, today persons |
| Race, chart and frequency card (same datasets, `population_cohort_race`) | as sex, per race concept | DemographicsRace (4) | as sex. Ethnicity is computed today but shown nowhere; no preset is chosen for it |
| Age, chart and summary card (`population_w_cohort_first_occurrence`) | years from birth to the start of the person's observation period, first cohort entry per person | DemographicsAge (2), continuous; DemographicsAgeGroup (3), 5-year groups | FeatureExtraction takes the age at cohort start (year of index minus year of birth). Today's figure is the age at the start of observation, which is not the cohort's age |
| Cohort duration, prior observation, follow-up: one 3-variable summary card (`cohort_observation`) | cohort start to end; cohort start minus observation start; observation end minus cohort start, each floored at 0 | DemographicsTimeInCohort (10), DemographicsPriorObservationTime (8), DemographicsPostObservationTime (9) | same definitions, but FeatureExtraction uses the observation period that contains the index date. Today joins every period of the person, so a person with two periods counts twice |
| Charlson Comorbidity Index, chart and summary card (`popoulation_cohort_charlson_score`) | 17 categories, weights 1–6; a category counts only with at least 2 condition occurrences; all eras, with no time limit | CharlsonIndex (901, Romano adaptation), eras up to index | same 17 concept sets (identical ancestor lists) and weights. FeatureExtraction counts a category from one era and ignores eras after index; today's "at least 2" rule and post-index eras go |
| Dataset Population, card (`population_w_cohort_prepared`) | distinct persons with an observation period | population size: the count of the population pseudo-cohort (−1) | the population needs 365 days of observation (decision 5), so it is smaller |
| Population Prevalence, card | cohort persons over all persons | cohort-level view: cohort persons over the population | the denominator is the population (decision 5) |
| Cohort ID, Created Date, Name, Total Occurrence, Distinct Patient Count: 5 statistics cards | from `cohort_definition_filtered` and `cohort_observation`, on a head sample | a per-cohort summary table (id, name, created, entries, persons), shown as a dataset table | not covariates. Cards are not filtered by the dashboard filter (spike, 2026-11-20), so they become a table |
| Cohort Prevalence by Quarter and Ave Quarterly Occurrence (`cohort_prevalence`) | per quarter, distinct cohort persons spanning it over persons observed in it | kept (decision 7), keyed by cohort | the same figures per cohort |
| Incidence by County, chart and table (`cohort_location_prepared`) | per county, cohort persons over observed person-years, × 1,000 | kept (decision 7), keyed by cohort; person-years per county computed once | the same figures per cohort. It counts cohort members, not new cases, so it is closer to a rate of membership than an incidence; the name stays |
| One tile whose insight `t0koor2` no longer exists | — | dropped | broken today |

**Page 2, "Cohort Covariates".**

| Today's figure (dataset) | How it is computed today | Becomes | Differs because |
| --- | --- | --- | --- |
| Condition Group Prevalence, chart and table (`cohort_condition_group_prevalence_prepared`) | from `condition_occurrence`, grouped under SNOMED clinical finding (441840); the condition starts before cohort start and ends at most 365 days before it; share of cohort entries | ConditionGroupEraLongTerm (210) and ConditionGroupEraAnyTimePrior (209) | FeatureExtraction reads `condition_era`, includes the index day, and has an any-time-prior window too. Its groups take levels of separation `> 2` (today `>= 2`) and 3 fewer name exclusions (`%at anatomical site`, `%of specific body system%`, `%of specific body organ%`), so its group list differs slightly |
| Drug Group Prevalence, chart and table (`cohort_drug_group_prevalence_prepared`) | from `drug_exposure`, grouped under ATC classes (code length 1, 3, 4, 5) and ingredients; the same 365-day window | DrugGroupEraLongTerm (410) and DrugGroupEraAnyTimePrior (409) | the same group rule (FeatureExtraction's `drug_era` variant). FeatureExtraction reads `drug_era`, whose eras merge exposures, and includes the index day |
| Visit Occurrence in Relation to Cohort, pivot table (`cohort_visit_joined`) | visits per visit type, before cohort start, during the cohort and after it ends | VisitConceptCountLongTerm (923): visits per visit concept in the 365 days up to index, as a continuous covariate | only the before-index part has a preset; "during" and "after" go (decision 4). See the open point below |
| Cohort ID, Created Date, Name, Total Occurrence, Distinct Patient Count: 5 cards | as on page 1 | the per-cohort summary table | as on page 1 |

**New, with no figure today.** Each covariate gets its standardized difference against the
population (decision 3) and, on request, against another cohort (decision 8).

**Decided (owner, 2026-11-25).**

- **Visits: long-term window only.** Decision 6 named VisitConceptCount "in the long-term window and
  any time prior", but FeatureExtraction has no any-time-prior visit preset (the visit presets are
  VisitCount and VisitConceptCount in the long, medium and short-term windows, 920–925). Only
  VisitConceptCountLongTerm (923) is used, which matches the other long-term presets. Decision 6 is
  updated.
- **Charlson: the preset's rules.** Today's "at least 2 occurrences" rule and post-index eras go,
  as decision 4 rules out hand-built covariates. Scores fall for cohorts with single-era diagnoses
  and rise for none.

## R4. Resolved table paths

**Today.** `get_sql_path()` and `set_table_variables()` in `solution/recipes/sql_script_function.py`
rebuild each table's SQL name from dataset parameters by hand:

| Connection | Defect |
| --- | --- |
| Snowflake | Ignores the dataset's database (`catalog`); only `${TENANT}`, `${NODE}`, `${projectKey}` expanded |
| Databricks | Ignores `catalog`; `${catalog}` read from a project variable that does not exist |
| Redshift | Ignores the schema and does not quote, so mixed-case or hyphenated names fail |
| Any other | Returns the raw table name, so failures surface later as SQL errors |

E4 passed because all three test connections use their default database, catalog and schema.

**Proposal.** Ask DSS for the name it uses itself:
`dataiku.Dataset(name).get_location_info()["info"]["quotedResolvedTableName"]`. This resolves catalog,
schema, variables and quoting per dialect. `set_table_variables()` goes. An unsupported connection type
raises with the supported list. Unit tests stub the location info. The spike confirmed that, on all three
connections, the returned names equal what DSS's own recipes generate (see Spike results).

## R5. Cohort build as one static recipe

**Today.** For each cohort in the batch, `write_cohorts()`:

1. rewrites the inputs and script of a single runtime SQL recipe, `create_cohort`, created on first use;
2. rewrites the steps of the "Drop SQL Temporary Tables" scenario and runs it, polling every 5 s;
3. runs "Build Cohort Dataset" and polls it;
4. counts the cohort with a separate query and appends a log row.

At the end it rewrites the runtime SQL recipe `compute_cohort_building_log` and builds it.
`compute_cohort_definition` is created the same way. The flow therefore changes at run time, scenarios
start other scenarios, and every cohort rewrites the same shared objects.

**Proposal.** Two static Python recipes. The solution stays single-user per project; this design makes
that explicit instead of fragile.

- `register_cohorts`: input `cohort_submission`. Outputs `cohort_definition` and
  `uploaded_cohort_definition`, written in-database through `SQLExecutor2` with escaped literals (R2).
- `build_cohorts`:
  - inputs: the mapped scripts folder, the batch, and every imported OMOP table (declared for lineage);
  - outputs: `cohort` (written in-database by the scripts) and `cohort_building_log` (appended).
  - For each cohort it splits the mapped script into statements (outside quotes and comments; tested on
    all scripts in `cohort_scripts/`) and runs them in one session with `SQLExecutor2.query_to_df(count
    query, pre_queries=statements, post_queries=commit)`, where `commit` is `["COMMIT"]` on Snowflake and
    Redshift and empty on Databricks. Session temporary tables (Snowflake `TEMP`, Redshift `#`) live until
    the count is read.
  - It records status, count and error per cohort, continues past failures, writes the log, then fails
    the recipe if any cohort failed.
- "Write Cohort" becomes: build `build_cohorts`'s outputs, then refresh the dashboard (R3).
- Remove `create_cohort`, `compute_cohort_definition`, `compute_cohort_building_log`, "Drop SQL Temporary
  Tables", "Build Cohort Dataset", "Build Cohort Metadata Dataset" and "Build Cohort Log Dataset", and the
  "Move recipe to zone" steps.

**What this gives.**

- The flow is fixed at design time, so bundles and copies match what runs.
- No nested scenarios or polling loops.
- DSS refuses a second job that writes the same dataset while one is running, which is the right
  behaviour for a single-user project: a concurrent run is rejected instead of corrupting shared objects.

**Cost.** Per-cohort lineage is no longer a recipe; `cohort_building_log` carries it (cohort, script,
input tables, status, count). The spike confirmed that `pre_queries` share the session on all three
dialects, and that an E4 script run this way gives the E4 count (see Spike results).

## R6. Databricks temporary tables

**Today.** Atlas renders Databricks temporary tables as real Delta tables
(`CREATE TABLE @temp_database_schema.<random8><name> USING DELTA`). `@temp_database_schema.x` becomes a
bare `x` in the connection's default schema. Each script drops its tables at the end, and a pre-run step
drops those of the same script. A run that fails midway leaves them until that cohort runs again. Snowflake
(`CREATE TEMP TABLE`) and Redshift (`#table`) use session tables and are not affected.

**Proposal**, inside `build_cohorts` (R5):

- Map `@temp_database_schema.<name>` to `<scratch schema>.rwdtmp_<project key>_<cohort id>_<name>`. The
  scratch schema is the main connection's default schema unless the optional variable `temp_schema` names
  another. Names are then attributable and unique per project and cohort.
- Drop that cohort's tables before the run, and again in a `finally` block after it.
- At the start of every build, drop any `rwdtmp_<project key>_*` table left in the scratch schema by an
  earlier crash (`SHOW TABLES IN <schema> LIKE 'rwdtmp_<project key>_*'`).
- Note for later: Databricks SQL has a temporary-table feature in preview. When it is generally available,
  rendering Databricks scripts with session temp tables would remove the problem at source.

## R7. Project variables

**Today.**

- Project Setup writes the `local` scope, and the repo code reads `local`.
- "Update project variables" copies `local` into `standard`. Four scenarios call it, and two scenarios then
  read `standard` (`enable_pipeline`, the two import lists).
- `${...}` references in recipes already resolve with `local` overriding `standard`, so the copy is not
  needed for them.
- `standard` also carries keys nothing reads:
  - `advanced_file_format` and `condition_count_for_charlson_score`;
  - `connection_type` (set to "PostgreSQL");
  - `cohort_build_error`, which is written but never read;
  - 22 OMOP table keys that Setup never maps, `cost` among them with the value `"cost table:"`.

**Proposal.**

| Scope | Holds | Keys after the revision |
| --- | --- | --- |
| `standard` | Shipped defaults and tunables, documented in the wiki | `days_prior_to_cohort_startdate` (365), `enable_pipeline` (false), `cohort_script_table_naming` (atlas), `temp_schema` (empty) |
| `local` | Whatever Project Setup writes | connections, prep project, import lists, table mapping, `cohort_script_table_prefix`, `cohort_submission` |

- Values stay in the project's variables (owner, 2026-11-23). The library holds the reader and the
  contract of keys, not the values: Setup writes `local`, and `${...}` in recipes and scenarios
  resolves only project variables.
- One reader, `solution/utils/variables.py:get_setting(name)` (moved from `setup/choices.py:scoped_variable`):
  `local`, then `standard`. Use it in all repo code and scenario steps.
- Delete "Update project variables" and its four call sites.
- Delete the unused keys. `cohort_definition_id` and `cdm_standard_tables_map` go with R3 and R1.
- `tests/test_variables.py` fails when code or the Setup manifest uses a key that is not in the table above.

**Decided 2026-11-23 (owner).** `condition_count_for_charlson_score` is unused: the Charlson recipes do
not read it. It is dropped with the other unused keys.

## R8. Code environment

The project inherits the instance default Python environment, and the one Python recipe also inherits.
Every third-party module the solution loads is `dataiku`, `dataikuapi`, `pandas` or `numpy`. That covers:

- the repo code;
- the 16 scenarios;
- the Python recipe;
- the 18 `dku_utils` modules reached from those imports in `bs-commons` `v2-3-1`.

`bs-commons` also imports `PIL`, `cv2`, `skimage` and Google client libraries, but only in modules the
solution never loads. **Keep the instance default.** The DSS built-in environment provides pandas and
numpy. State that requirement in the wiki's technical requirements article. `tests/test_imports.py` gains a
check that `solution/` imports nothing outside the standard library and those four packages.

## Accepted as is

By the owner's decision, these stay unchanged. The built-in project macro test run before publication
covers part of them.

- Library sources: `python/solution` from this repo (`solution-revision-v1-2` once repointed), `bs-commons`
  and the previews.
- Scenario run-as user.
- Shipped variable values. R7 changes which keys exist, not this.
- The "⚠️ Format Solution⚠️" scenario. Its two reads of `standard` switch to `get_setting()` so it keeps
  working after R7. No other change.
- Bundle and Project Setup export settings.

Also noted, no action in this revision:

- `PREP_RWD_S3_1K` and `PREP_RWD_S3_100K` still repeat visit ids; 2.3M has one row per visit since
  2026-11-20.
- Setup tiles carry an inlined copy of `solution/setup/`. `tools/app_manifest.py --check` belongs in the
  release check.

## Spike results (step 0)

Run on 2026-11-20 on DSS 15.2.0, in the scratch project `TMP_RWD_SPIKE_R`, created for the spike with
the owner's approval and deleted afterwards. Nothing in `SOL_RWD_COHORT_DISCOVERY` or the `PREP_RWD_*`
projects changed; they were only read. The `bs-snowflake`, `bs-databricks` and `redshift-solutions`
connections were all usable by the owner's account; no OAuth grant was blocked. Python ran inside DSS as a
custom Python scenario step.

**R4: resolved table names.** On each connection, one external dataset pointed at the 1K prep `person`
table and one managed output was built by a group recipe on the in-database engine. The Redshift output
was given the mixed-case, hyphenated table name `${projectKey}_Out-RS`. The spike compared
`get_location_info()["info"]["quotedResolvedTableName"]` with the names in the build job's SQL and with
today's `set_table_variables()`:

| Connection | `quotedResolvedTableName` = job SQL | Today's `get_sql_path()` |
| --- | --- | --- |
| Snowflake | Yes, `"DKU_SOLUTION_DESIGN"."SOL_DESIGN"."PREP_RWD_SF_1K_PERSON_SF"` | Drops the database: `"SOL_DESIGN"."PREP_RWD_SF_1K_PERSON_SF"` |
| Databricks | Yes, `` `se-sandbox`.`business_solutions`.`PREP_RWD_DB_1K_person_db` `` | Drops the catalog: `` `business_solutions`.`PREP_RWD_DB_1K_person_db` `` |
| Redshift | Yes, `"PREP_RWD_RS_1K_person_rs"`, `"TMP_RWD_SPIKE_R_Out-RS"` | Unquoted: `TMP_RWD_SPIKE_R_Out-RS` |

- The key is present for all three connection types.
- `info` also carries `catalog` and `schema` only when the dataset sets them, plus `table`,
  `connectionName` and `databaseType`.
- `${projectKey}` is expanded in all three.
- The prep datasets set a catalog explicitly (`DKU_SOLUTION_DESIGN`, `se-sandbox`), so today's code works
  only because those catalogs are the connection defaults. The Databricks catalog contains a hyphen and
  needs the quoting.
- Redshift folds even quoted names to lowercase (`tmp_rwd_spike_r_out-rs`).

*Design consequence:* R4 unchanged.

**R5: session temporary tables through `pre_queries`.** `SQLExecutor2(connection=...).query_to_df(query,
pre_queries=..., post_queries=...)` was called on each connection, using names prefixed `rwdspike_`.

| Behaviour | Snowflake | Redshift | Databricks |
| --- | --- | --- | --- |
| Temp table created in `pre_queries` is visible to the count query | Yes (`CREATE TEMPORARY TABLE`) | Yes (`#table`) | `CREATE TEMPORARY TABLE` is rejected; `CREATE TEMPORARY VIEW` works, chained views too |
| Temp object visible in the next call | No | No | No |
| Failing statement | Exception naming it: `During pre-query '<statement>': ...` | Same | Same |
| Several statements in one string | Rejected (`Actual statement count 2 did not match the desired statement count 1`) | Accepted | Rejected (parse error) |
| DML in `pre_queries` without `COMMIT` | Lost (the DDL persists, the rows do not) | Lost (DDL rolled back too) | Kept (auto-commit) |
| `post_queries=["COMMIT"]` | Rows kept | Rows kept | Fails: `COMMIT` is not a statement |

Stretch on Snowflake: the solution's mapped E4 script for cohort 1 (Anemia) was split outside quotes and
comments into 22 statements. Its target table was redirected to `"SOL_DESIGN"."rwdspike_cohort"`; it read
the solution's imported tables only. It was run as `pre_queries` with `COMMIT`. The count in the same
call and in a new session was 611, equal to E4.

*Design consequences for R5:*

- Commit per dialect, as now written in R5: `post_queries=["COMMIT"]` on Snowflake and Redshift, none on
  Databricks.
- The statement splitter is required, not optional: Snowflake and Databricks reject multi-statement
  strings.
- Atomicity differs by dialect:
  - Redshift: a cohort's statements run as one transaction, so a failure keeps the previous rows.
  - Snowflake: each DDL commits. The `DELETE` and `INSERT` of the cohort rows are only committed by the
    `TRUNCATE` after them, so a failure before that keeps the previous rows too.
  - Databricks: every statement commits on its own. A failure after the `DELETE` leaves that cohort empty
    until the next run. `cohort_building_log` must record it as failed, which R5 already does.
- R6 unchanged. Atlas Databricks scripts `INSERT` into their temporary tables, so temporary views cannot
  replace them; the `rwdtmp_` Delta tables stay.

**R3: dashboard filters on statistics cards.** The DSS 15 documentation lists charts and dataset tables as
the filterable insights ([dashboard filters](https://doc.dataiku.com/dss/15/dashboards/filters.html)). The
15.x release notes add nothing on statistics cards. Live test:
- A synthetic 60-row Snowflake table `rwdspike_syn` (no SYNPUF data) with `GRP` A/B/C, `CAT2` X/Y and
  `V` numeric.
- A dashboard with one chart (count by `CAT2`) and one statistics card (frequency table on `CAT2`,
  summary of `V`).
- A dashboard filter on `GRP` = A, set by the owner on dataset `syn_sf`.

The chart changed, and the statistics card did not. The card has its own sample (`dataSpec`) and ignores
page filters. *Design consequence:* R3 as now written: charts for the distributions, and dataset-table
tiles for the frequency tables. Open question 4 is closed.

**R2: custom Setup tile that reads a dataset and writes a variable.** One `PROJECT_VARIABLES_EDIT` tile
(HTML/JS plus Python `do()`, the select-box pattern) was added to the scratch project's Setup:

- **Read.** `do()` read the first rows of `syn_sf` with `dataiku.Dataset(...).iter_tuples()` and the
  tile rendered them as an editable table.
- **Write.** "Save" sent the edited rows to `do()`, which wrote them as a JSON list to the `local`
  variable `rwdspike_submission` with `api_client().get_project(...).set_variables()`. The value showed
  after a page reload, and `dku project get-variables` read it back.
- **Validation.** A row without a name was refused through a returned `{"ok": false, "errors": [...]}`.
  The tile showed the message.
- **Exception.** An exception raised in `do()` reached the tile's failure callback as the full Python
  traceback from `dataiku/customui/server.py`, ending with the message.
- **Setup section.** A project only gets a Setup page through the App Designer action "Add a setup
  section". The public API cannot set it; `useAppHomepage` alone is not enough. This does not affect the
  solution, which already has one, nor its copies.

*Design consequences for R2:*
- The tile's `do()` catches its own errors and returns `{"ok": false, "errors": [...]}`, so the user sees
  a sentence and not a traceback.
- Saving through `do()` (read, merge, `set_variables`) is the write path, so the batch is validated in
  Python before it is stored.

**Scratch objects.** All were removed, and the removals were verified on 2026-11-20:
- **Project.** `TMP_RWD_SPIKE_R` was deleted, with no data dropped. It held:
  - datasets `src_sf`, `src_db`, `src_rs`, `out_sf`, `out_db`, `out_rs` and `syn_sf`;
  - recipes `grp_sf`, `grp_db` and `grp_rs`;
  - scenario `rwdspike`;
  - insights `dJru2KM` and `RIEbMKn`;
  - dashboard `4PsEojE`;
  - the R2 Setup tile, whose manifest was restored before deletion;
  - the variable `rwdspike_submission`.
- **Tables dropped by exact name, then checked absent:**
  - `TMP_RWD_SPIKE_R_out_sf` and `rwdspike_syn` (Snowflake);
  - `TMP_RWD_SPIKE_R_out_db` (Databricks);
  - `tmp_rwd_spike_r_out-rs` and an empty `tmp_rwd_spike_r_out_rs`, created when the dataset still had
    its first name (Redshift);
  - `rwdspike_commit_a`, `rwdspike_commit_b` and `rwdspike_cohort`, dropped in the probes themselves.
- **Prep data.** The three 1K prep `person` tables still hold 1,000 rows and show as built.

## Order, verification and gate

| Step | Work | Verified by |
| --- | --- | --- |
| 0. Spike (about 2 days) | `get_location_info()` names on SF, DB and RS; `pre_queries` session temp tables on all three; dashboard filter on statistics cards; a custom tile that reads datasets and writes a variable | Done 2026-11-20: [Spike results](#spike-results-step-0) |
| 1. Foundation | R4, R7, R8 | Offline tests; E4 counts unchanged |
| 2. Cohort build | R5, R6 | Offline tests (statement splitter on every script in `cohort_scripts/`, literal escaping); E4 rerun; a forced failure on Databricks leaves no `rwdtmp_` table |
| 3. Setup | R1, R2; regenerate tiles with `tools/app_manifest.py` | Two submissions in a row; a reused id is refused without **Replace** and accepted with it; "Built cohorts" lists both batches |
| 4. Characterization and dashboard | R3 as decided | Same results on SF, DB and RS for the E4 cohorts; independent SQL checks of a binary, a continuous and a concept covariate; standardized differences (precomputed against the population, on request between two cohorts) equal a hand calculation; a batch computes only its own cohorts; all cohorts selectable by filter; the 9 `DEMO_SF_RWE` inputs unchanged. See the [step 4 work session](#step-4-work-session-draft-2026-11-24) |
| 5. Release check | Project macro test; `tools/app_manifest.py --check`; wiki articles 03, 09, 16, 17, 18, 23, 24, 28 and Release Notes 1.2.0, pushed with the owner's approval | Gate below |

**Step 1 status (2026-11-23): repo part done (`d0a11e9`, fix `e41c6d3`); DSS part done; E4 passed on SF, DB and RS. Step 1 is done.**

- **R4.** `get_sql_path()` returns `quotedResolvedTableName`, and `set_table_variables()` is gone. A
  dataset that is not on Snowflake, Databricks or Redshift raises with the supported list
  (`tests/test_sql_paths.py`).
- **R7.** `solution/utils/variables.py:get_setting(name, variables=None, default=None)` is the one
  reader. A key that is absent, None or `""` falls through to the next scope; `False`, `0` and `[]`
  count as values. All repo reads use it.
  - The contract (`STANDARD_DEFAULTS`, `LOCAL_KEYS`, `RETIRING_KEYS`) is in `solution/variables.py`.
    `tests/test_variables.py` fails on a key outside it and on direct scope access.
    `tools/app_manifest.py --check` also names Setup parameters outside it; the live manifest has none.
  - `write_cohorts()` no longer writes `cohort_build_error`.
  - `tools/app_manifest.py` inlines `get_setting` into the tiles, so the live tiles now differ from the
    repo until the manifest is reapplied.
- **R8.** `tests/test_imports.py` fails if `solution/` imports anything outside the standard library,
  `dataiku`, `dataikuapi`, `pandas`, `numpy` and the project libraries. The technical requirements
  draft (wiki 03) states the default-environment requirement.

DSS part, approved by the owner on 2026-11-23:

1. **Bundle export.** None separately; the owner leaves it to the project macro test.
2. **Library.** Resynced to `d0a11e9`.
   - **Manifest: reapplied.** Only the Python of the 4 tiles changed, and `tools/app_manifest.py --check`
     on the refetched manifest passes, variable contract included.
   - The deployed code of section 2 tiles 0, 3 and 5 was run outside DSS against the live project. It
     lists `PREP_RWD_SF_1K`, and the prep project's 15 Snowflake tables for both table tiles.
   - Not checked: the Setup page in the browser, and the cohort tile (section 8 tile 1), which needs
     DSS's own Python process.
3. **Scenarios: done.**
   - "Update project variables" is deleted, along with its call steps in "Build Cohort Dashboard",
     "Create Cohort Scripts", "Import Datasets from DataPrep Project" and "Reconfigure Connections".
   - Five scope reads now use `get_setting()`:
     - "Reconfigure Connections": `main_connection`, `folder_connection` and `enable_pipeline`;
     - "⚠️ Format Solution⚠️": the prep project key and the two import lists.
   - No scenario reads a scope directly any more.
4. **Variables: done.**
   - Only `days_prior_to_cohort_startdate` (4 recipes) and `cohort_definition_id` (1 recipe) are used
     as `${...}`. No dataset, recipe, scenario, insight, dashboard or folder uses any other key.
   - `standard` now holds `days_prior_to_cohort_startdate`, `enable_pipeline`,
     `cohort_script_table_naming`, `temp_schema`, `cdm_standard_tables_map` and `cohort_definition_id`.
   - `local` lost `cohort_build_error`, and nothing outside the contract remains.
   - The values from before the change are kept outside the repo.
5. **Verify: E4 passes on SF, DB and RS (2026-11-23).**
   - On `e41c6d3`, cohorts 1 / 2 / 3 give 611 / 593 / 247 on all three databases.
     - Checksums are identical everywhere and equal to 11-19: subject-id sums 321170 / 313922 / 129590,
       plus the summed start and end offsets.
     - Snowflake ran in SOL; Databricks and Redshift ran in TMP, whose `python/solution` now follows
       `solution-revision-v1-2`.
     - "Create Cohort Scripts", "Write Cohort to Datasets" and "Build Covariate Datasets" succeeded on
       each; the covariate build ends in WARNING on DB and RS (bad-date warnings below).
   - **The new mapped scripts use `quotedResolvedTableName`.** That is their only difference from the
     11-19 scripts:
     - Snowflake gains the database;
     - Databricks gains the catalog;
     - Redshift gains quotes.

     Atlas scratch names stay bare.
   - **First rerun on `d0a11e9` failed (R4 regression, fixed in `e41c6d3`).** "Create mapped scripts"
     raised `Dataset cohort cannot be used : declare it as input or output of your recipe`.
     - The mapping runs in the Python recipe `compute_lMM00YKr`, which declares no CDM or cohort
       tables. `get_sql_path()` now opens datasets with `ignore_flow=True`.
     - The spike had called `get_location_info()` from a scenario step, so it did not catch this.
   - **Databricks moved to `bs-databricks-per-user`.** `bs-databricks` refused every query (`403 API
     tokens are disabled for your organization`). With the owner's approval, `PREP_RWD_DB_1K` was
     repointed and rebuilt on `bs-databricks-per-user` (migration plan, B3).
     - The solution's DB run used `main_connection` = `bs-databricks-per-user`.
     - No Atlas or `rwdtmp_` scratch table was left behind.
     - TMP is back on `PREP_RWD_RS_1K` / `redshift-solutions`, with its variables restored.
   - **Open findings:**
     - `OUTPUT_DATA_BAD_DATE` warnings in the covariate build: 22,590 on DB and RS, 0 on SF (11,295 on
       11-19). Unexplained.
     - "Reconfigure Connections" moves datasets but does not drop their old tables. TMP's DB run left 34
       managed `tmp_rwd_sol_v112_test_*` tables in `business_solutions.default` on
       `bs-databricks-per-user`. Dropped with the owner's approval on 2026-11-23; each was then
       checked absent by name (`information_schema` still listed them for a while afterwards).
     - `map_cohort_script_paths.py` reports every per-cohort error as "Missing required OMOP tables
       across cohorts". R2 rewrites ingestion.

**Step 2 status (2026-11-23): repo part done (`0c4b88a`, error cleanup `a764faa`); DSS part done, both projects on `a764faa`; E4 and the Databricks forced failure passed. Step 2 is done.**

- **R5.** `solution/pipelines/build_cohorts.py:build_cohorts()` is the body of a static Python recipe
  `build_cohorts`. `write_cohorts.py` and its scenario helpers are gone.
  - It reads the batch from `uploaded_cohort_definition` and each mapped script from the folder.
  - Per cohort, one `SQLExecutor2.query_to_df(count, pre_queries=statements, post_queries=commit)`.
    `commit` is `["COMMIT"]` on Snowflake and Redshift and empty on Databricks.
  - A failed cohort is logged with the table's current count and the error (1,000 characters at most).
    The build continues, appends every row to `cohort_building_log` in one session, then raises.
  - `register_cohorts` is not in this step. It needs `cohort_submission` (R2), so it lands in step 3
    with the removal of `compute_cohort_definition` and "Build Cohort Metadata Dataset".
- **Splitter and literals.** `solution/recipes/sql_text.py` holds both, with no imports.
  - `split_statements()` splits on `;` outside quotes, backticks and comments. Tests cover every
    script in `cohort_scripts/{snowflake,databricks,redshift,postgre}`; the E4 Anemia script gives
    the spike's 21 statements.
  - `sql_literal()` doubles backslashes on all three dialects. It doubles quotes on Snowflake and
    Redshift and escapes them as `\'` on Databricks.
  - The ingestion (`map_cohort_script_paths.py`) already uses it for names, descriptions and
    filenames. The rest of R2 is unchanged.
- **R6.** Mapped scripts now keep `@temp_database_schema.<name>`. `build_cohorts` renders it:
  - the bare name on Snowflake and Redshift;
  - `<scratch>.rwdtmp_<project key>__c<id>_<name>` on Databricks.

  The scratch schema is `temp_schema` if set, else the schema of the `cohort` table. A cohort's
  scratch tables are dropped first and again in `finally`. Every build starts by dropping
  `rwdtmp_<project key>__c*` tables left by a crash, using `SHOW TABLES ... LIKE`; this sweep never
  fails the build. Scripts mapped before this change hold bare names and still run, but without R6.
  Rerun "Create Cohort Scripts" first.
- **Not tested offline:**
  - that DSS accepts a Python recipe whose SQL outputs are written only through `SQLExecutor2`;
  - `SHOW TABLES ... LIKE` through `SQLExecutor2` on Databricks.

  Both are checked in the DSS part.

DSS part, approved by the owner on 2026-11-23, on `SOL_RWD_COHORT_DISCOVERY` and `TMP_RWD_SOL_V112_TEST`:

1. **Library.** Both resynced to `0c4b88a`.
2. **Flow.**
   - `build_cohorts` is in zone "Cohorts" on the inherited code env.
     - Inputs: `lMM00YKr`, `uploaded_cohort_definition` and the 15 imported OMOP tables.
     - Outputs: `cohort` and `cohort_building_log`, both in append mode.
   - `create_cohort` and `compute_cohort_building_log` are deleted, and their datasets kept.
   - DSS accepts a Python recipe whose SQL outputs are written only through `SQLExecutor2`.
3. **Scenarios.**
   - "Write Cohort to Datasets" is one non-recursive forced build of the two outputs.
   - "Drop SQL Temporary Tables", "Build Cohort Dataset" and "Build Cohort Log Dataset" are deleted.
   - In "⚠️ Format Solution⚠️", step 8 deletes only `compute_cohort_definition`, and only if it exists.
     The step that cleared "Drop SQL Temporary Tables" is removed.
   - The pre-change definitions are kept outside the repo.
4. **Verify: E4 passes on SF, DB and RS.** Counts are 611 / 593 / 247, and checksums equal step 1 on
   every database. Every log row says SUCCESS with an empty error.
   - Snowflake ran in SOL; the covariate build after it succeeded.
   - Redshift ran in TMP, before and after the Databricks leg.
   - Databricks ran in TMP on `PREP_RWD_DB_1K` / `bs-databricks-per-user`; TMP is back on Redshift.
   - The mapped scripts keep `@temp_database_schema.`.
   - The start-of-build sweep ran `SHOW TABLES IN `business_solutions`.`default` LIKE
     'rwdtmp_tmp_rwd_sol_v112_test__c*'` through `SQLExecutor2` and found nothing to drop.
5. **Forced failure on Databricks.** `SELECT * FROM rwd_forced_failure_missing_table` was inserted
   into cohort 2's mapped script, right after its Codesets temp table was filled.
   - The build logged cohort 2 FAILED with the `TABLE_OR_VIEW_NOT_FOUND` error, and cohorts 1 and 3
     SUCCESS. The recipe then failed.
   - All 18 expected `rwdtmp_` tables of the three cohorts were probed by name. None exists.
   - Rerunning "Create Cohort Scripts" restored the script, and the next build gave 611 / 593 / 247.
6. **Findings.**
   - The stored error first kept the `None: b"..."` wrapper and Java stack lines. `clean_error()`
     removes them (`a764faa`, resynced; not yet seen in a live failure).
   - A FAILED row carries the cohort's current count. Cohort 2 kept 593 rows from the previous run,
     because the script failed before its `DELETE`.
   - **Open, for step 5.** "⚠️ Format Solution⚠️" step 8 still syncs `cohort` and
     `cohort_building_log` to the filesystem and back through a sync recipe. That would give them a
     second producer next to `build_cohorts`. The project macro test runs it.
   - "Reconfigure Connections" again left 34 managed `TMP_RWD_SOL_V112_TEST_*` tables in
     `business_solutions.default` on `bs-databricks-per-user`. Dropped with the owner's approval and
     checked absent by name.
   - TMP still has stale `sync_*` recipes reading `PREP_RWD_S3_1K`; they log graph errors in jobs.
     TMP is deleted in D3 step 6.

**Step 3 status (2026-11-23): repo part done (`e3ddcbf`); DSS part done on both projects, except the checks in a browser.**

- **R1.** `solution/setup/table_naming.py:key_map(naming, prefix)` builds the key map from
  `cohort_script_table_naming` (`atlas`, `plain` or `prefix`) and `cohort_script_table_prefix`.
  - The `atlas` and `plain` maps equal `omop_cdm_atlas.json` and `omop_cdm_standard.json`.
  - `unmapped_references()` names every `@schema.table` the choice does not cover, except
    `@temp_database_schema`. Every shipped script is covered under `atlas`.
  - `cdm_standard_tables_map` left the contract. `check_omop_table_names.py` and
    `utils/folder_utils.py` are gone.
- **R2, registration.** `solution/setup/registration.py` is import-free, so it can be inlined into the
  Setup tiles.
  - It builds the tile rows (*new*, *registered*, *changed*, or *submitted, not ingested*), checks a
    batch, and builds the "Built cohorts" listing.
  - The script and its SHA-256 are stored as JSON in `cohort_definition_syntax`. That is how a script
    is recognised as registered or changed. The cohort table's schema is unchanged.
  - **Deviation from the text above:** cohort id 0 is accepted (whole numbers, 0 or more), because
    the 45-cohort demo library uses it.
- **R2, ingestion.** `solution/pipelines/register_cohorts.py:register_cohorts()` is the body of one
  static Python recipe. It replaces the CSV copy, `compute_lMM00YKr`, `compute_cohort_definition` and
  `map_cohort_script_paths.py`.
  - It reads `cohort_submission` and checks the whole batch before writing anything: the tile's
    checks against `cohort_definition`, R1 coverage, and the OMOP tables.
  - Every error of the batch is reported at once, and each names its cohort. This also replaces the
    misleading "Missing required OMOP tables" message.
  - It then writes the mapped scripts and the escaped definitions in one session.
  - R5's separate `register_cohorts` and mapping steps are merged into this one recipe.
- **Tiles.** In `app_manifest/tiles/`:
  - `register_cohorts.{py,html,js}`: load and save. `save` writes `cohort_submission` through
    `set_local()`, the one writer next to `get_setting()`. Errors come back as sentences.
  - `built_cohorts.{py,html,js}`: read-only.
- **Manifest tool.** `tools/app_manifest.py` applies a declared layout. It finds tiles by module or
  first parameter, not position, and inlines any `solution.*` import. On the step 1 manifest it:
  - removes S3 and the CSV tile;
  - renames S5 and its button ("Ingest registered cohorts");
  - adds the naming, register and built tiles;
  - refreshes the 4 wrapper tiles, whose inlined variables module gained `set_local`.

  A second run makes no change.
- **Bulk path.** `tools/register_cohorts.py <metadata.csv>` prints the submission. With
  `--project KEY --apply` it writes it; the demo library gives 45 cohorts.
- **Not tested offline:**
  - the HTML and JS in DSS's Setup page;
  - the naming tile's `visibilityCondition` syntax;
  - folder and dataset access from a tile process.

DSS results (2026-11-23, library `e3ddcbf` in both projects):

- **Changes, as listed below, on SOL and TMP.**
  - Backups of the manifest, scenarios, recipes and variables are kept outside the repo.
  - `register_cohorts` is in the "Cohort SQL Scripts" zone. "Create Cohort Scripts" is one forced
    build, "Ingest registered cohorts".
  - The three scenarios, three recipes, two metadata datasets, folder `4ktqvA1F` and
    `cdm_standard_tables_map` (both scopes) are gone.
  - "Format Solution" no longer names `cohort_metadata_copy`, the mapping folder or
    `compute_cohort_definition`. "Reconfigure Connections" no longer names `cohort_metadata` or the
    mapping folder.
  - TMP's "Create Cohort Scripts" also lost its "Update project variables" step.
  - Setup was applied with `dku app-designer set-definition -P KEY -d @file`, and `--check` is clean.
    DSS adds `allowDuplicates: true` to each parameter, so the tool now writes it.
- **Snowflake (SOL).**
  - The E4 batch without Replace was refused, with all three ids named and nothing written.
  - With Replace it was accepted, and E4 gives 611 / 593 / 247 with the E4 checksums.
  - A second batch, cohort 4 "Anemia (Crohn's test)" (a copy of the Anemia script), was ingested and
    built alone; cohorts 1–3 kept their build.
  - The tile functions, run on the live tables, list all four scripts as *registered* and all four
    cohorts as built.
  - Cohort 4 and `step3_quote_test.sql` are left in SOL for the browser check.
- **Redshift (TMP):** E4 gives 611 / 593 / 247 with the checksums.
- **Databricks (TMP, `PREP_RWD_DB_1K` / `bs-databricks-per-user`):**
  - E4 gives 611 / 593 / 247 with the checksums.
  - Cohort 4 "Anemia (Crohn's test)" was written with `\'` and built (611).
  - TMP was then switched back to Redshift.
- **Not done: the browser checks.** The built-in browser cannot open the design instance
  (organisation policy). Still open for the owner, in SOL's Setup:
  - the prefix field shows only for "Custom prefix";
  - "Register cohorts" loads, saves and shows errors as sentences;
  - "Built cohorts" lists cohorts 1–4.
- **Finding:** "Reconfigure Connections" moves the "Original Scripts" folder with the other folders.
  Scripts uploaded under one connection are not seen under the other, so each switch needs a
  re-upload. TMP's folder was empty after the switch back to Redshift, and the E4 scripts were
  uploaded again; E4 on Redshift still gives 611 / 593 / 247.
- **Leftovers:** as in step 2, switching back left 33 TMP tables in `business_solutions.default` on
  `bs-databricks-per-user`, and no `rwdtmp_` scratch table. Dropped with the owner's approval on
  2026-11-24; each was then confirmed gone by name.

**Setup revision after the owner's review (2026-11-24).** Applied to both projects' Setup;
`--check` is clean. The library change, the `mapping` choice in `register_cohorts`, reaches DSS
with the next resync.

- **Table naming.**
  - Four choices: Atlas placeholders, plain names, one prefix for every table, and a custom
    mapping table. Atlas scripts use several prefixes, which one prefix cannot express.
  - The mapping table lists every OMOP table and starts from the Atlas names. A blank row means
    the scripts do not use that table. It is stored as `cohort_script_table_map`, which joins the
    variable contract.
  - The choice is now a custom tile, saved as it changes, in its own section "Cohort Script Table
    Naming", right after **Cohort Ingestion**. The section text explains what to choose and when.
- **Register cohorts.**
  - The table refreshes itself when the pointer returns to the tile or the window regains focus
    (at most every 3 seconds); edited rows keep their edits. The upload tile raises no event, so
    a "Refresh list" button at the top of the tile, next to the upload, covers a missed refresh.
    A refresh takes a few seconds: it starts the tile's Python, reads every script and
    `cohort_definition`. The tile shows "Reading the uploaded scripts…" meanwhile.
  - Columns have fixed widths inside the tile, and the name and description are text areas that
    grow with their text.
- **Wording: three verbs.** Scripts are *uploaded*, a batch is *registered*, and the batch is
  *written* to cohort definition; then cohorts are *built*.
  - Tile button: "Register batch". Ingestion button: "Write batch to cohort definition". Statuses: *New*,
    *In batch, not written*, *Written*, *Changed since written*.
  - The "Write Cohort to Datasets" section became "Build Cohorts" (button "Build cohorts"), and
    the folder "Mapped Scripts" (`lMM00YKr`) was renamed "Written Scripts", with "Format Solution"'s
    folder list, and its link became "View written scripts".
  - The Pipeline Configuration text no longer mentions a mapping file. The Cohort Ingestion text
    names the three sections in order.

**Dialect check (2026-11-24).** `solution/setup/sql_dialect.py` tells which SQL dialect an Atlas
script was exported for, from markers Atlas always writes.

- **Markers.** They were sampled from five atlas-demo cohorts (1791177, 1662241, 1770910, 99278,
  2978) rendered by WebAPI 2.14 for each dialect:
  - Snowflake: `CREATE TEMP TABLE` with `DATEADD(day, ...)`;
  - Databricks: `USING DELTA` or `date_add(...)`;
  - Redshift: `#` tables with `DISTKEY`, `DISTSTYLE` or `ANALYZE`;
  - not supported: the untranslated template (`SELECT ... INTO #t`), and PostgreSQL (`INTERVAL`
    without `DATEADD`).
- **Accuracy.** It classifies all 111 shipped scripts and all 20 sampled renderings correctly.
- **Where it applies.**
  - The tile marks such a script in its status column and leaves it unticked.
  - The batch check and the ingestion refuse it, naming the dialect it was exported for.
  - Hand-written SQL without markers is not judged.
- **Shared structure.** The three dialects share one statement skeleton and the same Atlas
  placeholders. The sampled scripts render with no placeholder left in our build code.

DSS part as run, on `SOL_RWD_COHORT_DISCOVERY` and `TMP_RWD_SOL_V112_TEST`:

1. **Backups:** export the manifest, scenarios, recipes and variables.
2. **Library:** resync both projects.
3. **Flow:**
   - Create the Python recipe `register_cohorts`. Its input is "Original Scripts" (`PqOBn6B3`); its
     outputs are `lMM00YKr`, `cohort_definition` and `uploaded_cohort_definition`, in append mode.
   - Delete the recipes `compute_lMM00YKr`, `compute_cohort_definition` and the one that builds
     `cohort_metadata_copy`.
   - Delete the datasets `cohort_metadata` and `cohort_metadata_copy`, and the folder `4ktqvA1F`.
4. **Scenarios:**
   - "Create Cohort Scripts" becomes one non-recursive forced build of `register_cohorts`'s outputs.
   - Delete "Check OMOP Table Variables Mapping", "Check Uploaded Cohort Metadata Schema" and
     "Build Cohort Metadata Dataset".
   - Check "⚠️ Format Solution⚠️" for references to the removed objects.
5. **Variables:** remove `cdm_standard_tables_map`.
6. **Manifest:** build it with `tools/app_manifest.py --out`, apply it to SOL, and check it with
   `--check`.
7. **Verify on SOL (Snowflake):**
   - In the browser, the naming tile's prefix field shows only for "Custom prefix".
   - The E4 scripts come up as *new*. Ids 1–3 are refused without Replace and accepted with it.
     Ingest, write, then E4 must give 611 / 593 / 247.
   - A second batch, one more script named with a quote, ingests as a new id.
   - "Built cohorts" lists both batches.
8. **Verify on TMP:** E4 on Redshift and Databricks through `tools/register_cohorts.py --apply`.
   This covers the Databricks literal escaping.

### Step 4 work session (draft, 2026-11-24)

The repo part comes first, with offline tests. The DSS part follows, with the owner's approval.

0. **Map today's figures to the decided presets.** Decisions 5–8 settle the open items. Output: a
   mapping table in this plan, from each of today's figures to its preset and window (or to the
   quarterly and county views), noting where figures will differ and why.
   *Drafted 2026-11-25:* [part 0 mapping](#step-4-part-0-todays-figures-mapped-to-the-presets-2026-11-25),
   accepted by the owner on 2026-11-25 with its two points (visits long-term only, the preset's
   Charlson rules).
1. **Rendering toolchain.**
   - `tools/render_feature_extraction.py` pins a FeatureExtraction release (templates and
     `PrespecAnalyses.csv`) and the SqlRender jar.
   - It renders the chosen presets with fixed parameters and translates them to Snowflake, Spark
     and Redshift.
   - It writes `solution/characterization/sql/<dialect>/` with a NOTICE. A rerun reproduces the
     files byte for byte.
2. **Offline checks of the rendered SQL.**
   - Every file splits into statements, its placeholders are covered by the R1 mapping, and its
     scratch tables render.
   - The dialect fingerprint matches its folder.
3. **Engine.** `solution/pipelines/characterize_cohorts.py`, the body of one static recipe:
   - characterize the batch's cohorts and the population pseudo-cohort (reserved id −1, never
     written to `cohort`);
   - write `covariate`, `covariate_continuous`, `covariate_ref`, `analysis_ref`;
   - delete and insert by cohort id, in one session; a failed cohort is logged and does not stop
     the others, as in R5.
4. **Standardized differences.**
   - Precomputed: `covariate_balance`, each cohort of the batch against the population.
   - On request: `pair_balance_sql(cohort_a, cohort_b)`, which builds one statement over the stored
     aggregates, and `compare_cohorts()`, the scenario's recipe body. The latter reads
     `comparison_requests`, computes only the pairs missing from `covariate_balance`, and skips
     with a sentence any pair naming an unknown or unbuilt cohort.
   - `solution/compare/` also holds the webapp's services: the list of built cohorts, the cache
     lookup, appending a request, and starting and polling the run. Each is unit-tested with DSS
     stubbed.
   - Unit tests cover the formulas, zero variance, the antisymmetry of A–B against B–A, and a
     covariate present in only one of the two cohorts.
5. **Flow and scenarios.** No Setup tile is added, and Setup's dashboard section goes (part 7).
   - New:
     - the `comparison_requests` table (appended by the webapp);
     - the "Compare cohorts" recipe and scenario, run by the webapp, with no trigger;
     - `covariate_balance`, holding both the population rows and the cached pairs;
     - the "Compare cohorts" code webapp, with its backend started automatically.
   - Rebuilding a cohort deletes its cached pairs; "Import Datasets" clears the cache.
   - New recipes: characterization after `build_cohorts`, and the population after the import.
   - "Build cohorts" also builds the characterization of the batch.
   - "Import Datasets" also builds the population.
   - "Refresh Dashboard" rebuilds everything.
6. **Dashboard.**
   - A new "Cohort Characterization" dashboard.
   - Page 1, filtered by cohort: the cohort against the population. It shows prevalence of binary
     covariates, distributions of continuous covariates, the covariates with the largest absolute
     standardized differences, and the quarterly prevalence and county incidence views.
   - Page 2: the "Compare cohorts" webapp tile at the top, with cohort B set to "Population" by
     default. Below it, the charts of `covariate_balance`, filtered by cohort and comparator.
   - Every chart reads a small table in full.
   - It is built first, next to the old dashboard.
7. **Retirement**, after a backup:
   - the 29 recipes and 30 datasets, and the old dashboard and its 30 insights;
   - Setup's dashboard section, `cohort_definition_id` and `section8_tile1.py`;
   - `RETIRING_KEYS` empties.
8. **Verification.**
   - E4 on SOL (Snowflake) and TMP (Redshift, Databricks): identical results across the three.
   - Independent SQL checks: share of women, mean age, one condition group in the long-term
     window.
   - Standardized differences against a hand calculation, for the population and for one pair of
     E4 cohorts requested on demand.
   - A new batch computes only its own cohorts, which is checked in the job log.
   - The cache: a second request for the same pair computes nothing, and rebuilding one of its
     cohorts makes the next run recompute it.
   - The webapp, from the dashboard: request a pair, see it computed, then select it in the filter.
     An unbuilt cohort is not offered. With cohort B left at "Population", nothing runs and the
     result shows at once.
   - The filter shows each E4 cohort.
   - The schemas of the 9 `DEMO_SF_RWE` inputs are unchanged.
   - Timing of one batch, with population size and cohort count recorded.
9. **Write-up.** Results in this plan; wiki articles listed for step 5.

Risks:

- **Speed at 2.3M with 50 cohorts.** The population is characterized once per import, and cohorts
  once per batch. Partition the result tables by cohort id if needed.
- **Waiting for a comparison.** The arithmetic takes seconds, but a scenario adds about a minute of
  DSS job overhead. The time from request to chart is measured in part 8.
- **The webapp backend acts for the viewer.** It runs as one configured identity. A dashboard reader
  without the right to run scenarios could still start one through it, so the backend checks the
  caller's rights on the project before it runs anything. The webapp's "run as" user must be able
  to run "Compare cohorts".
- **The backend must be running.** It is set to start automatically. If it is down, the tile says so
  in a sentence, and the dashboard's precomputed page 1 is unaffected.
- **The presets differ from today's figures** (Charlson variant, windows). Step 0's mapping
  documents each difference rather than hiding it.
- **The renderer is an offline dependency.** It is pinned, and its output is checked in, so DSS
  never needs it.

**Gate to exit phase 4:**

- E4 rerun gives identical counts on SF, DB and RS and equals 611, 593 and 247;
- the multi-submission test passes;
- the dashboard shows every built cohort against the population without a rebuild, and a requested
  comparison of two cohorts;
- the project macro test passes;
- Setup has no custom-mapping, metadata-CSV or dashboard section.

**Execution sequence (draft, 2026-11-25).** Each stage ends at a gate. The next stage starts only
after the gate passes and the owner approves it.

- **Tools.**
  - The repo and `dku` carry parts 1–5 and 7. The library, the rendered SQL, the recipes, the
    scenarios and the webapp code live in the repo with offline tests. They reach DSS as in step 3
    and E4: library resync, recipe code, scenario steps.
  - Dataiku Headless (the `dataiku-headless@dataiku` plugin, through Cobuild) carries part 6: the
    charts and dataset tables, the two dashboard pages, their filters and the webapp tile. Its read
    tools (`list_dashboards`, `get_dashboard_settings`, `list_insights`, `get_insight_settings`)
    change nothing. Every change goes through a Cobuild conversation.
  - Neither tool renders the dashboard, and the organisation's browser policy blocks
    `design.solutions.dataiku-dss.io` in both Claude browsers (built-in and Claude in Chrome,
    2026-11-25). The owner checks every page visually. `dku dashboard validate` pre-checks a layout.
  - Cobuild is not used for the flow: it prefers visual recipes, and Headless forbids falling back
    to raw API calls.
- **Stages.**
  1. **Repo only (parts 0–4).** Nothing changes on DSS.
     Gate: the owner accepts the mapping table, the tests pass, and the rendering reproduces byte
     for byte. Commit with the owner's approval.
  2. **Backup.**
     Gate: a bundle export of SOL, and saved copies of its Setup and its old dashboard definition.
  3. **Flow on SOL only (part 5).** Each new object is named before it is created, and sits next to
     the old ones; nothing is deleted. "Build cohorts" and "Compare cohorts" run once on the E4
     batch.
     Gate: the independent SQL checks and the hand-calculated standardized differences (population
     and one pair) match, and a second request for the same pair computes nothing.
  4. **Dashboard with Cobuild, on SOL (part 6).** One unit of work per Cobuild turn, in this order:
     page 1 insights; page 1 layout and cohort filter; the webapp insight; page 2 and its filters.
     - Each turn names the datasets and insights read beforehand.
     - Inspection turns use `allow_edit_project=false`, building turns `true`.
     - A deletion confirmation from Cobuild is never answered: it goes to the owner, since this
       stage deletes nothing.
     - After each turn the dashboard definition is read again, and the owner looks at the page.
     - Cobuild conversations live only in the Headless server process, so the stage runs in one
       session. Nobody builds in the UI on SOL meanwhile.
     Gate: the owner accepts both pages visually, and the webapp works from the dashboard: request a
     pair, see it computed, filter to it; with cohort B left at "Population", nothing runs.
  5. **TMP: Redshift, then Databricks.** The E4 round trip, without the dashboard.
     Gate: the same results as Snowflake, and the 9 `DEMO_SF_RWE` input schemas unchanged.
  6. **Retirement (part 7).** With `dku`, from an explicit list the owner approves, not through
     Cobuild.
     Gate: the gate to exit phase 4 above.
- **Before stage 4.** The owner enables the plugin (it is registered as the `dataiku` marketplace but
  not enabled) and starts a new session, whose setup skill connects it to the design instance.
  Stages 1–3 do not need it.

Then D1 copies the solution on the head of `solution-revision-v1-2`.

## Open questions

- [x] R3 design. Decided (owner, 2026-11-24): the population is the reference, FeatureExtraction's
  format and presets only, standardized differences added. See
  [R3 as decided](#r3-as-decided-owner-2026-11-24)
- [x] Population reference. Decided (owner, 2026-11-24): every person with at least 365 days of
  observation, indexed one year after the start of their first observation period (R3 decision 5)
- [x] Presets and windows. Decided (owner, 2026-11-24): the proposal as written (R3 decision 6)
- [x] Prevalence by quarter and incidence by county. Kept as cohort-level views (owner, 2026-11-24;
  R3 decision 7)
- [x] Standardized differences between two cohorts. Added in 1.2 (owner, 2026-11-24; R3 decision 8).
  Computed on request, not precomputed (owner, 2026-11-24; R3 decision 9)
- [x] How 1.2 runs a requested comparison of two cohorts. A scenario with a cache (owner,
  2026-11-24; R3 decision 10), with no Setup section (R3 decision 11)
- [x] Where the user asks for a comparison. A "Compare cohorts" code webapp, inserted into the
  dashboard (owner, 2026-11-24; R3 decision 12)
- [x] Keep the metadata CSV as a hidden bulk-import path, or drop it. Dropped (owner, 2026-11-23);
  `tools/register_cohorts.py` registers a library from a metadata CSV (R2)
- [x] `condition_count_for_charlson_score`: wire into the Charlson logic or drop. Dropped (owner,
  2026-11-23; R7)
- [ ] Databricks scratch schema: the connection default, or a dedicated `temp_schema`
- [x] If dashboard filters do not reach statistics cards: charts or a summary table instead. They do not
  (spike, 2026-11-20): charts for the distributions, dataset-table tiles for the frequency tables (R3)
