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
| [R9](#r9-patient-level-covariates) | Patient-level covariates: `extract_patient_covariates`, on request, from the same 11 FeatureExtraction presets; one dataset per preset and an own reference, shareable to Part 3 (added 2026-11-26) | Owner |

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
   - ConditionGroupEra and DrugGroupEra, in the long-term window (365 days before index). Any time
     prior was dropped (owner, 2026-11-25): the population has exactly one year of history, so for
     it any time prior equals long-term (identical counts on SOL), and a cohort with years of history
     looks inflated against it;
   - VisitConceptCount in the long-term window only (owner, 2026-11-25): FeatureExtraction has no
     any-time-prior visit preset.
7. **Prevalence by quarter and incidence by county stay** as cohort-level views. They are not
   covariates, and the v2.0 proposal keeps them too.
8. **Standardized differences between two cohorts are added**, as well as against the population.
9. **What is precomputed, and what is computed on request** (owner, 2026-11-24). Results that every
   comparison reuses are precomputed, incrementally. A comparison between two chosen cohorts is
   computed on request. The earlier draft precomputed every pair, which grows with the square of
   the number of cohorts.
10. **A requested comparison is computed by the webapp backend and cached** (owner, 2026-11-24;
    revised 2026-11-25), in `covariate_balance` next to the precomputed rows against the population.
    The table keeps every pair computed so far. A pair already in the cache is not computed again.
    - Revised 2026-11-25: no "Compare cohorts" scenario. The pair's arithmetic runs in the database in
      about a second, while a scenario adds about a minute of DSS job overhead. The backend runs
      `pair_balance_sql` itself.
    - Accepted in exchange: the flow shows no recipe for the cached pairs, and the backend writes
      with its own identity, so it checks the viewer's project rights first and records who asked in
      `comparison_requests`.
    - The precomputed rows against the population stay (decision 9): they cost seconds and a few MB
      per batch, and page 1 then reads a table with no wait.
11. **Project Setup has no dashboard section** (owner, 2026-11-24; R3 as first proposed). Neither
    the dashboard nor the comparison is driven from Setup.
12. **A code webapp requests comparisons** (owner, 2026-11-24). It selects the cohorts, has the pair
    computed (decision 10), and is inserted into the dashboard as a webapp tile.
13. **Cohort B defaults to the population** (owner, 2026-11-24). That pair is precomputed, so the
    default never computes anything.
14. **Characterization has its own Setup section** (owner, 2026-11-25), "Characterize Cohorts",
    after "Build Cohorts", with its own button.
    - "Build cohorts" no longer characterizes. Building stays one cohort at a time; characterizing
      is one set-based run over many cohorts.
    - Its tile reuses the "Register cohorts" pattern (owner, 2026-11-25): a table of built
      cohorts with their status, an *In batch* tick to include a cohort and a *Replace* tick to
      redo one, checked and saved as a batch, then run by the section's button.
    - Cohorts not yet characterized are ticked *In batch* by default, so one click still
      characterizes everything new, across several build batches.
15. **A characterized cohort is never recomputed without an explicit request** (owner,
    2026-11-25). As with registering an existing id, a characterized cohort ticked *In batch* is
    refused unless *Replace* is ticked too. Rebuilding a cohort or re-importing the data marks its
    characterization out of date in the tile but leaves it as it is.
16. **Minimum cell count of 5** (owner, 2026-11-25). No binary covariate held by 1 to 4 people is
    stored or shown. It is a privacy rule, as in OHDSI's tools, not a way to save space.
    - On SOL (1K) about half the group covariates were held by fewer than 5 people. At 2.3M almost
      none are: the 8,251 condition concepts in `condition_era` give about 9,800 condition groups
      and about 2,400 drug groups (FeatureExtraction's filter applied to the 1K ratios), and only 126
      concepts are held by fewer than 5 people. Expect about 12,000 rows per cohort and per table
      there, about 600,000 at 50 cohorts: a few tens of MB.
    - Readability is the dashboard's job (part 6): rank by absolute standardized difference, show
      the top covariates, filter by prevalence. The run time at 2.3M, not storage, is the open risk,
      measured in stage 5 before any trimming is considered.
    - "Characterize cohorts" computes each cohort's balance against the population from the full
      aggregates, then deletes the stored binary rows under 5. A balance row is kept only when each
      side has 0 or at least 5 people.
    - A pair requested later reads the censored rows, so a covariate under 5 on one side counts as 0
      there: the difference is approximate by at most 4 people's worth of prevalence on that side.
    - Continuous covariates (11 per cohort) are kept whole.

**Design.**

- **Engine.** FeatureExtraction's SQL templates (Apache-2.0) for the chosen presets are rendered
  offline, once per dialect, and checked into the repo like `cohort_scripts/`.
  - The table names stay as one fixed token, `@cdm_database_schema.<table>`, resolved to the project's
    datasets. The R1 naming setting does not apply: it describes only the uploaded cohort scripts
    (owner, 2026-11-25).
  - They run with the R5 build machinery: statement splitter, Databricks scratch tables, one
    session with its commit.
  - No SQL renderer runs inside DSS; the renderer port stays in v2.0 (its M3).
  - Rendering needs Java (available locally, OpenJDK 21) and the SqlRender jar.
- **When** (decisions 14 and 15). Everything is computed by "Characterize cohorts", in the
  "Characterize Cohorts" section of Setup. It runs one FeatureExtraction pass (about 200 statements)
  over:
  - the saved batch (`characterization_submission`): the cohorts ticked *In batch*, by default
    every built cohort with no characterization yet, and characterized ones only with *Replace*
    (delete and insert by cohort id);
  - the population, when it has none yet or the data was re-imported since. The population is not a
    user cohort and follows the data. When it changes, every cohort's balance against it is
    recomputed from the stored aggregates (arithmetic only, no FeatureExtraction run), so balances
    always use the current population.

  Standardized differences against the population come with each cohort characterized.
- **Precomputed (reused by every comparison), incrementally:**

  | Result | Computed | Size |
  | --- | --- | --- |
  | Covariates of each cohort (`covariate`, `covariate_continuous`) | once per cohort, by "Characterize cohorts"; again only when ticked | cohorts × covariates |
  | Covariates of the population | by "Characterize cohorts", first time and after each import | covariates |
  | Balance of each cohort against the population (`covariate_balance`, comparator −1) | with the cohort's covariates | cohorts × covariates |
  | `covariate_ref`, `analysis_ref` | added to as new covariates appear | covariates |

  - A cohort is never recomputed unless the user ticks *In batch* and *Replace* (decision 15). The
    population is recomputed only when the data was re-imported.
  - `characterization_log` records each run: run time, cohort id, the build time of the cohort
    characterized, entries counted, status and error. Setup compares it with
    `cohort_building_log` to show what is out of date.
  - Everything grows linearly with the number of cohorts. As an estimate, 50 cohorts at about
    2,000 covariates each give about 100,000 rows per table. Measured on SOL (part 5): about
    15,000–19,000 covariates per cohort, so about a million rows per table at 50 cohorts.
- **On request: a comparison between two chosen cohorts.**
  - The standardized differences of a pair are arithmetic on the two cohorts' stored aggregates:
    one SQL statement that joins about 2 × 2,000 rows. It never reads person-level data.
  - One library function builds that statement, `pair_balance_sql(cohort_a, cohort_b)`. The 1.2
    webapp backend runs it, and the v2.0 Cohort Workbench can call the same function.
  - Estimated time (not measured yet; part 8 measures it): under a second on a warm Snowflake
    warehouse or Redshift, one to three seconds on a running Databricks SQL warehouse. A cold
    warehouse adds its start-up time.
  - The backend runs it directly, with no scenario, and caches the result in `covariate_balance`
    (decision 10 as revised). The request does not come from Setup (decision 11).
  - **One balance table.** `covariate_balance` has one row per cohort, comparator and covariate:
    the two values and the standardized difference. The comparator is −1 for the population
    (precomputed) or a cohort id (computed on request). Every comparison, the default one
    included, is read the same way.
  - **Request: the "Compare cohorts" webapp** (decision 12). It is a standard DSS code webapp: HTML
    and JS, with a Python backend. It is inserted into dashboard page 2.
    - It lists the built cohorts from `cohort_definition` and `cohort_building_log`. The user
      picks cohort A, and cohort B, which defaults to "Population" (decision 13).
    - If the pair is already in `covariate_balance`, as the population always is, the webapp says
      so, and nothing runs.
    - Otherwise the backend checks the viewer's project rights, then computes the pair in the
      background, in one session: it records the request in `comparison_requests` (who asked, and
      when), then deletes and inserts the pair. The tile polls the backend and shows "computing",
      then "done: select the pair in the page filter", or the database error as a sentence.
    - One backend process serves every viewer. A lock lets each pair be computed once at a time, and
      a second request for a pair being computed joins it.
    - The logic lives in the project library (`solution/compare/`). Webapp backends, unlike Setup
      tiles, can import it.
    - The backend stays thin, so the v2.0 Cohort Workbench (FastAPI) can reuse the same services.
  - **Cache.**
    - The backend computes a requested pair only when it is missing from `covariate_balance`, and
      writes it by delete and insert.
    - When a cohort is re-characterized, its rows against the population are recomputed with it,
      and its rows against other cohorts are deleted, to be recomputed on the next request.
      Rebuilding a cohort alone changes nothing here: its stored figures, and the pairs computed
      from them, stay consistent until it is re-characterized.
    - When the population is recomputed, all population rows are recomputed and the pairs are
      kept, since pairs do not involve the population.
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
- **Patient-level covariates** for studies downstream: see [R9](#r9-patient-level-covariates).

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

## R9. Patient-level covariates

**Today.** `characterize_cohorts` renders FeatureExtraction in aggregated mode
(`solution/characterization/sql/MANIFEST.json`, `"aggregated": true`): it writes one row per cohort
and covariate. The per-person rows exist only in its scratch tables (`rwdfeatxcov_N`), which
`cleanup.sql` drops. `DEMO_SF_RWE` reads person-level features from the 5 hand-built tables
(`charlson_score_occurrence`, `condition_group_occurrence`, `drug_class_exposure`,
`person_location_joined`, `visit_occurrence_labeled`), whose definitions differ from the presets.

**What a study downstream needs** (LEGEND-HTN, Suchard et al., *Lancet* 2019;394:1816–26, author
manuscript NIHMS1546136, Methods):
- Every eligible new user in each database; nothing is sampled, and no sample size is set
  beforehand. Power is reported afterwards as a minimum detectable relative risk.
- A regularized propensity model per comparison over 7,515 to 70,784 baseline characteristics,
  stratification or variable-ratio matching, Cox models, then calibration with 76 negative-control
  outcomes.
- Estimates are trusted on diagnostics: empirical equipoise (most patients with preference scores
  between 0.3 and 0.7) and every characteristic's absolute standardized difference below 0.1 after
  adjustment. The unadjusted difference (its Table 2 "before") is what `covariate_balance` holds.
- So effect estimation is Part 3's work. Part 2 supplies complete cohorts, their patient-level
  covariates, feasibility counts and unadjusted balance.

**Decided (owner, 2026-11-26).**

1. **A separate function, `extract_patient_covariates`,** run on request for the cohorts a study
   needs, never as part of characterization.
2. **Option A for 1.2: it runs in SOL**, in its own zone "Patient Covariates", and its outputs are
   shared to Part 3. A study extraction application owned by the data team (option C) is reserved
   for v2.0 ([proposal](proposal-v2-cohort-workbench.md#study-extraction-option-c)). The boundary
   between Part 2 and Part 3 is to be discussed with the team; nothing goes to the decision
   register before that.
3. **One row per cohort entry**, not per person: the study decides first entry or all entries.
4. **No minimum cell count.** Decision 16 applies to aggregates shown or stored for review only.
   The extract stays internal; the SYNPUF rules are unchanged.
5. **Geolocation is not a preset.** `person_location_joined` stays outside FeatureExtraction.
6. **Presets: today's 11, fixed.** The extraction uses the 11 presets of R3 decision 6, as
   characterization does. Choosing presets, for characterization or extraction, is reserved for
   v2.0.
7. **One output dataset per preset.** An extract holds thousands of covariates, so each preset
   gets its own dataset, which analysts find by name. Characterization keeps its single
   `covariate` and `covariate_continuous` tables, since only the dashboard reads them.
8. **Its own reference dataset.** The extract does not use `covariate_ref` or `analysis_ref`. It
   writes its own reference, so it can be shared to the analytic team with the covariates, and it
   names only covariates found in extracted cohorts.
9. **Setup: its own part,** designed like "Cohort Characterization" and "Characterize Cohorts": a
   part heading **Patient Covariates** and a section "Extract Patient Covariates".

**Design.**

- **Rendering.** `tools/render_feature_extraction.py` renders the same 11 presets a second time in
  FeatureExtraction's non-aggregated mode, for each dialect, into
  `solution/characterization/sql/<dialect>/person/`. `MANIFEST.json` records both modes, and
  `--check` covers both.
  - Analysis ids come from FeatureExtraction's `PrespecAnalyses.csv`, and covariate ids are concept
    id × 1000 + analysis id, so they equal the characterization's ids. Checked on the rendered SQL
    before the engine changes.
  - The non-aggregated mode needs a `row_id` on the scratch cohort table; the engine adds it with
    `ROW_NUMBER()`.
- **Engine.** `solution/pipelines/extract_patient_covariates.py`, the body of one static recipe, like
  `characterize_cohorts`. It builds the scratch cohort table for the batch, runs the
  non-aggregated construction, then writes each preset's rows from that preset's scratch table, all
  in-database.
  - Complete cohorts only: no sampling, matching or trimming. Those belong to the analysis.
  - Rows are replaced per extracted cohort (delete, then insert) in every output.
- **Outputs**, zone "Patient Covariates", managed on the main connection, all with the prefix
  `patient_cov_` so the set reads as one:
  - **One dataset per preset**, named after FeatureExtraction's analysis name in snake case:

    | Dataset | Preset (analysis id) | Kind |
    | --- | --- | --- |
    | `patient_cov_demographics_gender` | DemographicsGender (1) | binary |
    | `patient_cov_demographics_age` | DemographicsAge (2) | continuous |
    | `patient_cov_demographics_age_group` | DemographicsAgeGroup (3) | binary |
    | `patient_cov_demographics_race` | DemographicsRace (4) | binary |
    | `patient_cov_demographics_prior_observation_time` | DemographicsPriorObservationTime (8) | continuous |
    | `patient_cov_demographics_post_observation_time` | DemographicsPostObservationTime (9) | continuous |
    | `patient_cov_demographics_time_in_cohort` | DemographicsTimeInCohort (10) | continuous |
    | `patient_cov_condition_group_era_long_term` | ConditionGroupEraLongTerm (210) | binary |
    | `patient_cov_drug_group_era_long_term` | DrugGroupEraLongTerm (410) | binary |
    | `patient_cov_charlson_index` | CharlsonIndex (901) | continuous |
    | `patient_cov_visit_concept_count_long_term` | VisitConceptCountLongTerm (923) | continuous |

    Each has `cohort_definition_id`, `subject_id`, `cohort_start_date`, `covariate_id` and
    `covariate_value`. Binary covariates are present only where true (value 1); continuous ones carry
    their value. Each dataset's description names its preset, window and kind.
  - **`patient_cov_ref`**, the extract's own reference: one row per covariate found in an extracted
    cohort, with `covariate_id`, `covariate_name`, `concept_id`, `analysis_id`, `analysis_name`,
    `domain_id`, `start_day`, `end_day`, `is_binary` and `dataset` (the per-preset dataset that holds
    it). It joins FeatureExtraction's covariate and analysis references into one table, so analysts
    search one place and go to the dataset it names. New ids are inserted; existing ones are kept.
  - **`patient_cov_log`**: one row per cohort and run, with row counts per preset, status and timing.
  - Sharing to Part 3 covers the 11 datasets and `patient_cov_ref`; the log stays in SOL.
  - Size grows with entries × covariates (about 50 to 500 rows per entry with today's presets), most
    of it in the condition and drug group datasets. Partition those by cohort id if 2.3M needs it.
- **Setup: "Patient Covariates".**
  - A part heading **Patient Covariates** with a short text, after "Cohort Characterization"
    (`HEADINGS` in `tools/app_manifest.py`).
  - A section "Extract Patient Covariates":
    - a short text: what is extracted, for which use, that results are kept until redone;
    - an "Extraction batch" custom tile on the "Characterization batch" pattern: built cohorts with
      their extraction status, *In batch* and *Replace*. Nothing is ticked by default, since an
      extract is requested for a study. "Save batch" checks it and saves `extraction_submission`
      (added to the variable contract), or lists every problem;
    - an "Extract patient covariates" button that runs the new scenario `Extract_Patient_Covariates`
      on the saved batch, and a link to `patient_cov_log`.
  - Shared parts of the two batch tiles move to the one template the characterization part
    anticipated (step 4 part 5).
- **Part 3 in 1.2.** `DEMO_SF_RWE` keeps reading the 5 hand-built tables; they stay unchanged
  (R3). Moving it to the `patient_cov_` datasets is Part 3 work after 1.2, with its models checked on
  the new features. In 1.2 the boundary is project sharing only: whoever can read the shared
  datasets reads every extracted cohort.

**Verification.**

- The renderer reproduces every file byte for byte, in both modes; analysis and covariate ids in the
  non-aggregated render equal the aggregated render's.
- An extract of one E4 cohort is identical on SF, DB and RS.
- Every covariate in a per-preset dataset belongs to that preset's analysis id, and every one appears
  in `patient_cov_ref` with that dataset's name.
- Aggregate parity: per binary covariate, the count of rows with value 1 equals `covariate.sum_value`
  for that cohort (before the minimum cell count); per continuous covariate, the mean of
  `covariate_value` equals `covariate_continuous`'s mean.
- An extracted cohort is redone only with *Replace*; a run with nothing ticked extracts nothing.
- Characterization's outputs and `covariate_ref` are unchanged by an extraction.

### Step 4b execution sequence (draft, 2026-11-27)

Each stage ends at a gate. The next stage starts only after the gate passes and the owner approves
it. Every DSS change names its project and objects first; every commit and push is approved
separately. Tools as in step 4: the repo and `dku`; Setup and tile checks in the owner's browser.

**Before stage 1: offline render trial (2026-11-27, scratchpad only).** FeatureExtraction 3.14.0's
`createSql` in non-aggregated mode (`rowIdField = row_id`), with the same settings:
- returns five parts, not six: construction, one query over all covariates (a `UNION ALL` of the
  scratch tables), `covariate_ref`, `analysis_ref` and cleanup. There is no continuous query; binary
  and continuous rows share the columns `row_id`, `covariate_id`, `covariate_value`;
- builds `rwdfeatxcov_1` to `rwdfeatxcov_11` in the aggregated render's order, one analysis each
  (210, 10, 1, 4, 9, 923, 901, 3, 2, 8, 410), with the same covariate id expressions, so the ids are
  the characterization's;
- does not filter by cohort id, and joins on `cohort.row_id`, which the engine adds with
  `ROW_NUMBER()`.

**Stages.**

1. **Rendering (repo only).**
   - `tools/render_feature_extraction.py` also renders the 11 presets in non-aggregated mode into
     `solution/characterization/sql/<dialect>/person/`.
   - `MANIFEST.json` records both modes and, for the person mode, the analysis id each scratch table
     holds; `--check` covers both.
   - Tests: ids equal in both modes; the 20 aggregated files unchanged byte for byte; the person
     files split, render their scratch tables and read only the 7 OMOP tables.

   Gate: `--check` passes in both modes, the aggregated files are unchanged, the tests pass.
   Commit with the owner's approval.

   *Done (2026-11-27), repo only:*
   - **Launcher.** `tools/feature_extraction/Render.java` takes the mode (aggregated or not), the
     row id field and the parts to translate; the tool runs it once per mode.
   - **Output.** 15 new files, `solution/characterization/sql/<dialect>/person/`: construction (87
     statements in each dialect), `query_covariates.sql` (the union of the 11 scratch tables, kept
     for reference), the two reference queries and cleanup. Their cohort table is
     `@extraction_cohort`, which needs `row_id`. The 18 aggregated SQL files are unchanged byte for
     byte; only `MANIFEST.json` and `NOTICE` changed.
   - **Scratch tables.** Redshift keeps FeatureExtraction's bare `#cov_N`; Snowflake and Databricks
     prefix the session id (`rwdfeatxcov_N`). So `MANIFEST.json` records them by bare name, under
     `modes.person.scratch_tables`: `cov_1` 210, `cov_2` 10, `cov_3` 1, `cov_4` 4, `cov_5` 9,
     `cov_6` 923, `cov_7` 901, `cov_8` 3, `cov_9` 2, `cov_10` 8, `cov_11` 410.
   - **Ids.** Before writing, the tool checks, for each dialect, that the person render has the
     aggregated render's covariate id expressions and analysis ids in the same order, and one
     analysis per scratch table as recorded; a mismatch stops it.
   - **`MANIFEST.json`** now has `modes` (aggregated and person: call, folder, cohort table, files)
     in place of the top-level `aggregated`, `files` and `placeholders.cohort_table`. Nothing in
     `solution/` reads it.
   - **Tests.** `tests/test_characterization_sql.py` runs every check on both modes and adds the
     ids, the scratch table map, a changed id that fails the check, and the rows keyed by `row_id`
     (169 tests in all). `--check` passes (35 files), twice.
2. **Engine (repo only).**
   - `solution/setup/extraction.py`: the batch rules on `solution/setup/batch.py`. Rows of built
     cohorts with their extraction status (Not extracted, In batch, Extracted, Rebuilt since
     extracted, Data re-imported since extracted, Extraction failed); nothing ticked by default; an
     extracted cohort is redone only with *Replace*; saved entries carry `saved` and expire once
     extracted after it (the part 8 rule of `live_submission`).
   - The SQL of one run, in one session: the scratch cohort table with `row_id`, the person-mode
     construction, then per preset delete and insert by cohort id from that preset's scratch table
     joined on `row_id`; `patient_cov_ref` gains new ids only, with its `dataset` column; the
     cleanup. Every read runs before the first delete. No minimum cell count (decision 4).
   - `solution/pipelines/extract_patient_covariates.py` and `dss/recipes/extract_patient_covariates.py`:
     the saved batch checked again as the authority, `patient_cov_log` (one row per cohort and run:
     status, error, timing, a row count per preset), the batch cleared after a success.
   - Databricks scratch tables `rwdtmp_<key>__pc_<name>`, with a sweep that leaves the build's and
     the characterization's alone.
   - `extraction_submission` added to the variable contract.

   Gate: offline tests pass. Commit with the owner's approval.

   *Done (2026-11-27), repo only:*
   - **What to extract: `solution/setup/extraction.py`.** Pure, for the tile to inline. Rows of
     built cohorts (no population row) with their status and, once extracted, their entries;
     nothing ticked by default; the batch check (an extracted cohort needs *Replace*; no successful
     build is refused); `extraction_submission` entries stamped with `saved` and expired through
     characterization's `live_submission`. Its top-level names differ from characterization's, which
     the inliner requires.
   - **The SQL of one extract: `solution/characterization/extraction.py`.** 151 statements in each dialect:
     `CREATE TABLE IF NOT EXISTS` for the 13 outputs; the entry table (`rwdpcov_cohort`, `#` on
     Redshift, `rwdtmp_<key>__pc_cohort` on Databricks) with `row_id` from `ROW_NUMBER()`; the
     person-mode construction; per preset, delete the run's cohorts then insert from its scratch
     table joined on `row_id`; new ids into `patient_cov_ref` (FeatureExtraction's covariate and
     analysis references joined, with the dataset name); the cleanup. Every read runs before the
     first delete. No minimum cell count, and no statement names a characterization table.
     `statements.fill()` takes the cohort token as a parameter; the characterization's calls are
     unchanged.
   - **Columns.** Preset datasets: `cohort_definition_id`, `subject_id`, `cohort_start_date` (date),
     `covariate_id`, `covariate_value` (float). `patient_cov_ref`: `covariate_id`, `covariate_name`,
     `concept_id`, `analysis_id`, `analysis_name`, `domain_id`, `start_day`, `end_day`, `is_binary`,
     `dataset`. `patient_cov_log`: `run_timestamp`, `cohort_definition_id`, `build_timestamp`,
     `entry_count`, `status`, `error`, `seconds` (whole seconds of the run), and `rows_<preset>` for
     each of the 11 datasets, read back from the outputs in the same session.
   - **The recipe body: `solution/pipelines/extract_patient_covariates.py`** (recipe code in
     `dss/recipes/extract_patient_covariates.py`). Checks the saved batch again as the authority, runs
     everything in one session, logs SUCCESS with counts or FAILED with the error for every cohort,
     clears the batch after a success, and does nothing, without failing, when nothing is ticked.
     Databricks scratch tables `rwdtmp_<key>__pc_<name>` (`sql_text.extraction_scratch_prefix`),
     swept before a run; the build's and the characterization's sweeps never match them.
   - **Tests: `tests/test_extract_patient_covariates.py`** (22 tests; 191 in all). Rows, statuses,
     *Replace*, expired entries; the presets, scratch tables and token against the renderer and
     `MANIFEST.json`; the kinds against FeatureExtraction's `is_binary`; statement order per
     dialect; the scratch names against what the construction creates; OMOP columns in scope; the
     prefixes apart. The SQL this module writes runs in SQLite on stand-in scratch tables: one row
     per entry (two entries of one subject kept apart), each in its preset's dataset, the reference
     with its dataset, a redo that replaces only its cohort without duplicates, and the counts and
     log row.
3. **Setup (repo only).**
   - A part heading **Patient Covariates** after "Cohort Characterization"; a section "Extract
     Patient Covariates" with its text, the "Extraction batch" tile, the "Extract patient
     covariates" button (scenario `Extract_Patient_Covariates`) and a link to `patient_cov_log`
     (`HEADINGS`, `OWN_SECTIONS`, `CUSTOM_TILES`).
   - "Refresh list" keeps only the user's ticks; status and times are read fresh (part 8).
   - The shared parts of the two batch tiles move to one template filled by `tools/app_manifest.py`.

   Gate: the inlined tiles run in the tests; the characterization tile behaves as before. Commit and
   push with the owner's approval.

   *Done (2026-11-27), repo only:*
   - **One template for both batch tiles:** `app_manifest/tiles/batch_tile.template.{html,js}`, filled
     by `tools/app_manifest.py` from `BATCH_TILES` (controller, column and button names, the status
     labels read from each tile's library module). `characterization_batch.{html,js}` are no longer
     checked in: the template renders them byte for byte as deployed on SOL (part 8), and a test pins
     their SHA-256. Both tiles share the part 8 "Refresh list" merge that keeps only the ticks.
   - **The "Extraction batch" tile:** `app_manifest/tiles/extraction_batch.py` over
     `solution/setup/extraction.py`, inlined with characterization, registration, batch and variables
     (no shared top-level name). One row per built cohort with its status, when it was extracted and
     its entries; nothing ticked; "Save batch" saves `extraction_submission` or lists every problem.
   - **Setup layout:** after "Characterize Cohorts", the heading **Patient Covariates** and the section
     "Extract Patient Covariates": its text, the tile, the "Extract patient covariates" button
     (scenario `Extract_Patient_Covariates`) and "Review Extraction Log" (`patient_cov_log`, new tab).
   - **Tests:** 196 in all. The extraction tile loads, refuses an empty batch and an extracted cohort
     without *Replace*, and saves stamped entries; its HTML and JS hold no characterization wording
     or unfilled key; a missing template value is refused.
   - **Against SOL's live Setup** (fetched read-only, 2026-11-27), `--check` lists only the new
     section with its tile and the new heading; the characterization tile shows no difference.
4. **SOL (Snowflake).**
   - Backup outside the repo: Setup manifest, variables, scenarios. Library resync.
   - Zone "Patient Covariates": the 11 `patient_cov_*` datasets, `patient_cov_ref` and
     `patient_cov_log`, managed on `bs-snowflake` (`managed: true` and a sibling's params); the recipe
     `extract_patient_covariates`; the scenario "Extract Patient Covariates" (one forced,
     non-recursive build, no trigger). Setup applied with `app-designer`, then `--check`.
   - The owner saves cohorts 1–3 in the tile and runs the extract.

   Gate, read with `dku`:
   - every row of a per-preset dataset has that preset's analysis id, and every covariate is in
     `patient_cov_ref` with that dataset's name;
   - binary: rows per covariate equal `covariate.sum_value`; ids in `covariate_censored` have 1 to
     4 rows; no other ids;
   - continuous: the mean over the cohort's entries equals `covariate_continuous`'s mean;
   - characterization unchanged: aggregate fingerprints of `covariate`, `covariate_continuous`,
     `covariate_ref`, `analysis_ref`, `covariate_balance` and `covariate_censored` equal before and
     after;
   - *Replace*: cohort 1 ticked without it is refused and nothing is saved; with it, its rows are
     replaced without duplicates; a run with nothing ticked extracts nothing; the saved batch has
     expired after the run;
   - timing recorded.
5. **TMP: Redshift, then Databricks.** Objects as on SOL, without Setup; the E4 batch saved in
   `extraction_submission` directly. Extract cohorts 1–3 on Redshift; switch to Databricks as in
   stage 5 of step 4, rebuild E4, extract, check no `rwdtmp_` table is left; switch back and
   register and build the Redshift E4 scripts again.

   Gate: identical to Snowflake, compared only through aggregates computed in each database
   (rows, distinct ids, value sums per dataset and cohort; `patient_cov_ref` rows).
6. **Write-up.** Results in this plan, the step table row, the registry pin. Commit and push with
   the owner's approval.

**For the owner, before the stage that needs it.**
- Continuous parity (stage 4): FeatureExtraction writes no row where a Charlson or visit count is
  0, so the mean is taken over the cohort's entries with missing rows as 0, not over the rows
  present. The verification bullet above would say so.
- Sharing the 11 datasets and `patient_cov_ref` to Part 3: not in the gate, and `DEMO_SF_RWE` keeps
  its 5 tables in 1.2. Proposed for step 5 or D1.
- The shared tile template (stage 3) changes the characterization tile that passed part 8.
  Proposed in stage 3, with tests that it behaves as before; or deferred.

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
| 4b. Patient-level covariates | R9 (after step 4's gate) | Rendering check in both modes; one E4 extract identical on SF, DB and RS; per-preset datasets match `patient_cov_ref`; aggregate parity with `covariate` and `covariate_continuous`; *Replace* rule; characterization unchanged |
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

   *Done (2026-11-25):*
   - **How it renders.** FeatureExtraction's own assembler, `FeatureExtraction.createSql`, does the
     rendering. It is the same Java call the FeatureExtraction R package makes, in aggregated mode
     with no minimum mean or count. SqlRender then translates the result.
     - A 50-line launcher, `tools/feature_extraction/Render.java`, makes both calls.
     - `tools/render_feature_extraction.py` runs it.
   - **Pins.**
     - FeatureExtraction 3.14.0, with its templates inside its jar, and SqlRender 1.19.7.
     - The three jars (FeatureExtraction, its `json` dependency and SqlRender, 240 KB in all) come from
       OHDSI's GitHub tags. They are pinned by SHA-256 and kept in `~/.cache/bs-rwe-assets/jars/`,
       never committed. `--fetch` downloads them, with the owner's approval of 2026-11-25.
   - **Output.**
     - `solution/characterization/sql/{snowflake,databricks,redshift}/`, six files each: construction,
       the four result queries (binary and continuous covariates, `covariate_ref`, `analysis_ref`),
       and cleanup.
     - `MANIFEST.json` (versions, jar hashes, presets, settings, placeholders) and `NOTICE`
       (Apache-2.0).
     - `--check` reruns the tool and compares bytes. Five reruns gave identical files.
   - **Dialects.** Each `construction.sql` fingerprints as its folder's dialect (the step 3 check).
     The scratch tables take the forms of Atlas's exports:
     - Snowflake: `CREATE TEMP TABLE`;
     - Redshift: `#` tables with `DISTKEY`;
     - Databricks: Delta tables named `@temp_database_schema.rwdfeatx<name>`.

     The session id is fixed (`rwdfeatx`), so the names are reproducible.
   - **Placeholders left:**
     - `@cdm_database_schema.<table>` for all seven OMOP tables read: `person`,
       `observation_period`, `visit_occurrence`, `condition_era`, `drug_era`, `concept` and
       `concept_ancestor`. This is FeatureExtraction's own form, kept as a fixed token of the
       solution's SQL (owner, 2026-11-25).
       - Customised schemas never reach the SQL. The project imports the OMOP tables as datasets
         with standard names, and each token becomes that dataset's resolved SQL name, which
         carries the user's catalog, schema, prefix or suffix.
       - The R1 setting `cohort_script_table_naming` describes only how uploaded cohort scripts
         spell table names, so it does not apply here. Tying this SQL to it would break it for any
         user who picks plain names or a prefix.
       - The token is kept rather than bare names, because the SQL also uses table names as
         aliases (`person.person_id`, `cohort.subject_id`) that a bare-name replacement would
         corrupt;
     - `@characterization_cohort`, the cohorts to characterize. All of its cohorts are characterized,
       and its rows per cohort are the denominator, so cohort entries, not persons, are counted
       (part 0);
     - `@temp_database_schema`, on Databricks only.
   - **Tests.** `tests/test_characterization_sql.py` checks the folders, the manifest, that nothing
     is left unrendered, the placeholders, the dialects and the tables read. Reproduction needs Java,
     so it is `--check`, not a unit test.
2. **Offline checks of the rendered SQL.**
   - Every file splits into statements, every `@cdm_database_schema.<table>` names an OMOP table the
     project imports as a dataset, and its scratch tables render.
   - The dialect fingerprint matches its folder.

   *Done (2026-11-25), in `tests/test_characterization_sql.py`:*
   - **Statements.** Each construction script splits with the R5 splitter: 197 statements on
     Snowflake and Redshift, 221 on Databricks. Each of the four result queries is one `SELECT`,
     which the recipe wraps in `INSERT INTO <result table>`.
   - **Scratch tables.** All 34 per dialect are created before any file reads them. Each is dropped
     in the construction script or in `cleanup.sql`, so a run leaves none behind. A test with a
     leaked table confirmed the check fails.
   - **Databricks.** The scratch tables render through `render_temp_tables` (R6). They become
     `<scratch schema>.rwdtmp_<prefix>rwdfeatx<name>`, leaving only `@cdm_database_schema` and
     `@characterization_cohort`.
   - **Dialects.** Each construction script fingerprints as its folder's dialect (part 1).
   - **Tables read.** `person`, `observation_period`, `visit_occurrence`, `condition_era`, `drug_era`,
     `concept` and `concept_ancestor`.
     - `drug_era` was optional, imported only when chosen in Setup. It is now in
       `MANDATORY_TABLES` (`solution/variables.py`), so "Import Datasets" always brings it, and
       the schema check covers it.
     - Every active prep project has a v1.1-compliant `drug_era` (index), and SOL, TMP and
       `DEMO_SF_RWD` import it already.
     - The wiki's list of imported tables needs it (step 5).
   - **For part 3.** The Databricks scratch prefix must be swept like the cohort build's
     (`rwdtmp_<key>__c<id>_`). The characterization is not per cohort, so it needs its own prefix
     that the sweep also matches.
3. **Engine.** `solution/pipelines/characterize_cohorts.py`, the body of one static recipe:
   - choose what to characterize (decisions 14, 15): the saved batch, `characterization_submission`
     (cleared after a successful run), checked again against the data as the cohort ingestion
     does, and the population pseudo-cohort (reserved id −1, never written to `cohort`) when it
     has none or the data was re-imported since;
   - copy their rows into one scratch cohort table, the `@characterization_cohort`, and run the
     rendered SQL once for all of them;
   - replace each `@cdm_database_schema.<table>` with the resolved name of that table's dataset
     (`get_sql_path`), through a fixed map, never the user's `cohort_script_table_naming`;
   - write `covariate`, `covariate_continuous`, `covariate_ref`, `analysis_ref`;
   - delete and insert by cohort id, in one session, and append to `characterization_log`. One
     set-based run cannot fail per cohort as the build does, so a failed run writes nothing,
     logs every cohort it held as failed, and leaves them to the next click;
   - give the Databricks scratch tables their own prefix, which the crash sweep also matches
     (part 2);
   - the status of each built cohort for Setup: Not characterized, In batch (saved, not run yet),
     Characterized (when), Rebuilt since characterized, Data re-imported since characterized,
     Characterization failed. A cohort whose latest build failed is not offered.
   - **Shared with registration.** `solution/setup/registration.py` already builds rows with a
     status and the two ticks, checks a batch ("already exists: tick Replace") and turns it into a
     submission. That logic moves to one module used by both tiles, so the two batches follow the
     same rules and sentences; each keeps only what is its own (scripts and dialect for
     registration, build and characterization logs here).

   *Done offline (2026-11-25):*
   - **Shared batch rules: `solution/setup/batch.py`.** It holds the whole-number id, the duplicate
     id, "Tick In batch on at least one …" and "already done: tick Replace". Registration now uses it;
     its messages and behaviour are unchanged, and the inlined Setup tiles still pass.
   - **What to characterize: `solution/setup/characterization.py`.** It is pure, so the tile will
     inline it.
     - Rows: the population first, then every registered cohort whose latest build succeeded, with
       its status. A cohort whose latest characterization attempt failed shows "Characterization
       failed", even after an earlier success, since a failed redo on Databricks may already have
       deleted its rows.
     - Defaults: a cohort not characterized yet is ticked; a characterized one is not.
     - The batch check (characterized needs *Replace*, no successful build is refused) and the
       saved value, `characterization_submission` (added to the variable contract).
     - The population is needed when it was never characterized or "Import Datasets" succeeded
       since; that time comes from the scenario's last successful run.
   - **The SQL of one run: `solution/characterization/statements.py`.** Pure; about 240 statements on
     Snowflake.
     - `CREATE TABLE IF NOT EXISTS` for the five result tables, with types per dialect. Part 5 still
       creates the DSS datasets over them.
     - The run's cohort table: the chosen cohorts from `cohort`, plus the population (first
       observation period of 365 days or more, index one year after its start).
     - The construction script, with every `@cdm_database_schema.<table>` replaced by its resolved
       name. A table it cannot resolve raises before anything runs.
     - Then delete and insert per cohort id for `covariate` and `covariate_continuous`, inserts of
       new ids only for `covariate_ref` and `analysis_ref`, and the cleanup. Everything that reads
       the data runs before the first delete, so a run that fails there changes no result.
   - **The recipe body: `solution/pipelines/characterize_cohorts.py`.**
     - Checks the saved batch again, as the authority.
     - Runs everything in one session, then reads the entries per cohort from the run's cohort
       table, and appends to `characterization_log`. The log gets SUCCESS with counts, or FAILED
       with the error for every cohort of a failed run.
     - Clears the saved batch after a success, and does nothing, without failing, when there is
       nothing to do.
   - **Databricks scratch tables** are `rwdtmp_<key>__ch_<name>`. The characterization sweeps only
     its own leftovers and the build only its own, so the two can run at the same time.
   - **Tests: `tests/test_characterize_cohorts.py`** (20 tests; 125 in all).
   - **Left for part 5:** the five DSS datasets, the recipe and scenario, the Setup section and tile,
     and the first run on SOL.
4. **Standardized differences.**
   - Precomputed: `covariate_balance`, each cohort of the batch against the population.
   - On request: `pair_balance_sql(cohort_a, cohort_b)`, which builds one statement over the stored
     aggregates, run by the webapp backend (decision 10 as revised).
   - `solution/compare/` also holds the webapp's services: the list of characterized cohorts, the
     cache lookup, the rights check, and computing a pair in the background and reporting its
     state. Each is unit-tested with DSS stubbed.
   - Unit tests cover the formulas, zero variance, the antisymmetry of A–B against B–A, and a
     covariate present in only one of the two cohorts.

   **Part 4 done (2026-11-25), offline.**
   - **The SQL: `solution/compare/balance.py`.** One SELECT of `covariate_balance` rows (cohort,
     comparator, covariate, its name and analysis, binary or not, both means and standard
     deviations, the standardized difference and its absolute value), for one or many cohorts
     against one comparator. `pair_balance_sql(paths, a, b)` is the one-pair case. The text uses only
     what Snowflake, Databricks and Redshift share, so one text serves all three.
     - A covariate on one side only: binary is 0 (FeatureExtraction stores no row for a covariate
       nobody has); continuous is 0 when its analysis says `missing_means_zero = 'Y'` (Charlson,
       visit counts), and otherwise NULL, with no difference.
     - Both standard deviations 0: the difference is NULL.
     - Ids are checked as whole numbers, and a cohort compared with itself is refused.
   - **Precomputed, inside "Characterize cohorts".** After the result inserts, the run deletes the
     cached pairs naming its cohorts and recomputes the balance against the population for its
     cohorts. When the population itself is recomputed, every cohort whose latest characterization
     succeeded is rebalanced, and the pairs are kept. `covariate_balance` joins the tables the run
     creates if missing.
   - **Which pairs: `solution/compare/comparison.py`.** A pair can be compared when both sides'
     latest characterization succeeded; cohort A is never the population, nor the same as B.
     Re-characterizing a cohort drops its pairs until someone requests them again.
   - **The webapp's services: `solution/compare/services.py`** (revised the same day, decision 10:
     no scenario).
     - The choices: cohort B defaults to the population.
     - The request: a cached pair answers at once. Otherwise the viewer's project rights are
       checked (owner, admin, write or run-scenarios), then the pair is computed in a background
       thread, in one session: `comparison_requests` gets the request (time, pair, who asked;
       created on first use), then the pair is deleted and inserted.
     - The state: running, done, or failed with the database error, each as a sentence for the
       tile. A second request for a pair being computed joins it; a lock keeps two computations of
       one pair from doubling its rows on Databricks, which commits per statement.
   - **Tests: `tests/test_compare_cohorts.py`** (18 tests; 143 in all). The SQL runs in SQLite
     against a hand calculation of both formulas, plus the antisymmetry, the one-sided covariates,
     zero variance, and many cohorts in one statement against one at a time.
   - **Left for part 5:** the `covariate_balance` and `comparison_requests` datasets, and the webapp
     itself (HTML, JS and a thin backend over these services).
5. **Flow and scenarios.** Setup's dashboard section goes (part 7). A "Characterize Cohorts"
   section comes after "Build Cohorts" (decision 14):
   - a short text: what is characterized, that existing results are kept, how to redo one;
   - a "Characterization batch" custom tile, built on the "Register cohorts" tile (decision 14):
     - the same table: fixed height with a scrollbar and a sticky header, a count line
       ("N cohort(s), M in batch"), a "Refresh list" button, and refresh on hover and focus that
       keeps the user's edits;
     - one row per built cohort: id, name, subjects, built on, status (part 3), *In batch* and
       *Replace*. The population is a fixed first row, ticked automatically when it needs
       computing;
     - a "Save batch" button that checks the batch (a characterized cohort needs *Replace*; a
       cohort whose latest build failed cannot be included) and saves it to the local variable
       `characterization_submission` (added to the variable contract), or lists every problem;
   - the "Characterize cohorts" button, which runs the new scenario on the saved batch.
   - The HTML and JS start from `register_cohorts.{html,js}`. If the two tiles stay alike, the
     shared parts move to one template that `tools/app_manifest.py` fills for each.
   - New:
     - the `comparison_requests` table (appended by the webapp);
     - `covariate_balance`, holding both the population rows and the cached pairs;
     - the "Compare cohorts" code webapp, with its backend started automatically. It computes
       requested pairs itself; there is no "Compare cohorts" recipe or scenario (decision 10).
   - Re-characterizing a cohort deletes its cached pairs (part 4).
   - New recipe and scenario: "Characterize cohorts" (reads `cohort`, `cohort_building_log` and the
     OMOP tables; writes the four FeatureExtraction tables, the population rows of
     `covariate_balance` and `characterization_log`), run from Setup only.
   - "Build cohorts" and "Import Datasets" are unchanged: neither characterizes.
   - "Refresh Dashboard" refreshes the dashboard's datasets only; it never characterizes.

   **Part 5, repo side done (2026-11-25).**
   - **Setup: the "Characterize Cohorts" section** (`tools/app_manifest.py`), placed after "Build
     Cohorts": a short text, the "Characterization batch" tile, the "Characterize cohorts" button
     (scenario `Characterize_Cohorts`) and a link to `characterization_log`. The Cohort Ingestion
     text now points to it.
   - **The tile:** `app_manifest/tiles/characterization_batch.{py,html,js}`, built on "Register
     cohorts": the same fixed-height table, count line, refresh and kept edits. The population is a
     fixed, greyed first row, ticked automatically when it needs computing. "Save batch" checks and
     saves `characterization_submission`.
   - **Inlining fix.** The tile inlines `characterization` and `registration` into one namespace,
     and both defined `submission()`, so registration's silently replaced the characterization's.
     The characterization's is now `batch_submission()`, and `tools/app_manifest.py` refuses any
     two inlined modules that share a top-level name.
   - **Shared helpers** moved into `solution/setup/characterization.py` (the log columns,
     `imported_at`, `batch_ids`), so the tile and the recipe check against the same ids.
   - **DSS code kept in the repo:** `dss/recipes/characterize_cohorts.py` (the recipe body) and
     `dss/webapps/compare_cohorts/` (HTML, JS, CSS and the Flask backend over
     `solution/compare/services.py`).
   - **Tests:** 149 in all; the tile is run inlined, and the backend's routes with Flask stubbed.
   - **Applying it to SOL needs, in order:** the backup (stage 2); the library resync; the six
     result datasets and `comparison_requests`; the `characterize_cohorts` recipe; the scenario;
     the Setup manifest; the webapp.

   **Part 5 on SOL (owner-approved, 2026-11-25).**
   - **Backup.** Saved outside the repo: the Setup manifest, the old dashboard (`4OpJPy0`) and the
     "Write Cohort to Datasets" scenario. No new bundle: SOL's bundle exports dataset data, two old
     dashboard datasets had no table (`cohort_condition_group_count`, `cohort_definition_filtered`;
     both built, with the owner's approval), and the bundle content still lists `cohort_metadata`,
     deleted in step 3. **Open, for step 5:** fix SOL's bundle content settings. A failed export
     left the id `step4-part5-pre-2026-11-25` in the list; it is not a usable backup. The owner
     chose to go on, since stage 3 only adds objects; `e4-rerun-pre-2026-11-19` is the last bundle.
   - **Library** resynced to `5dfb54b`, then `69a9ec0` (the fix below).
   - **Flow**, in zone "Cohorts": managed Snowflake datasets `covariate`, `covariate_continuous`,
     `covariate_ref`, `analysis_ref`, `characterization_log`, `covariate_balance` and
     `comparison_requests` on `bs-snowflake` (tables `${projectKey}_<NAME>`, upper case by the
     connection's naming rule); the Python recipe `characterize_cohorts` (inputs `cohort`,
     `cohort_definition`, `cohort_building_log` and the 7 OMOP tables it reads; the first six
     datasets as outputs, append mode).
   - **Scenario** "Characterize Cohorts": one non-recursive forced build of those outputs, no
     trigger. DSS gave it the id `Characterize_Cohorts`, and the Setup button uses that id.
   - **Setup** applied and checked: the "Characterize Cohorts" section, the Cohort Ingestion text,
     and the refreshed inlined code of "Register cohorts" and "Built cohorts".
   - **First run: failed, fixed.** FeatureExtraction reads some tables without an alias and
     qualifies their columns by the bare table name (`condition_era.person_id`); the quoted full
     name broke that. Nothing was deleted: the run failed in the construction script, and the log
     recorded FAILED for 1, 2, 3 and −1. `fill()` now keeps the bare name as alias (`69a9ec0`), with a
     test over every dialect's rendered SQL.
   - **Second run: success in about 3.5 minutes.** Entries 611 / 593 / 247 (the E4 counts) and 935
     for the population; the saved batch was cleared. DSS reads the new tables with their lowercase
     schemas, as for `cohort_building_log`, so no schema reload was needed.
   - **Sizes.** About 15,000–19,000 binary and 11 continuous covariates per cohort, 20,605 in
     `covariate_ref` and 13 analyses: about ten times the 2,000 estimated above. `covariate_balance`
     holds about 20,000 rows per cohort against the population.
   - **Independent SQL checks, cohort 1:** share of women 0.520458 and mean age 72.942717, both
     equal to the stored values; "Inflammatory disorder of the respiratory tract" in the long-term
     window, 267 people both ways.
   - **Standardized differences by hand:** cohort 3 against the population (a covariate present on
     one side only, −0.11365), and the pair cohort 1 against cohort 2 through `pair_balance_sql`
     (age 0.0280, women 0.00888, the condition group above 0.1843), all equal.
   - **Pair timing:** the full pair query (17,448 rows) takes about 0.3–1 s on Snowflake, measured
     against a 1.3 s client round trip.
   - **Webapp** "Compare cohorts" (`c9UUBDz`): standard, Flask backend, single process, started
     automatically, running. Its backend cannot be called with an API key (API access is off, and
     stays off), so the request, the cache and "a second request computes nothing" are the owner's
     browser check.
   - **Rerun after decisions 6 (revised) and 16** (owner-approved, 2026-11-25). Library at
     `b4b1400`; the six result tables emptied (rows only); cohorts 1–3 and the population
     characterized again in about 3 minutes.
     - Entries 611 / 593 / 247 and 935 again; the saved batch cleared.
     - 11 analyses; no any-time-prior row; the smallest stored count is 5, and no balance row shows
       a side held by 1 to 4 people.
     - Binary covariates stored: 4,872 for the population, 3,595 / 2,839 / 2,725 for the cohorts,
       down from about 15,000–19,000. Balance rows against the population: 3,611 / 2,987 / 2,923.
   - **Browser check passed (owner, 2026-11-26).** The "Compare cohorts" webapp works as expected:
     a pair against the population answers at once, a new pair computes then reports done, and a
     repeat request computes nothing. The batch tile and the "Cohort Characterization" heading are
     in place. **Stage 3 gate passed.** The registry pins SOL's library at `b4b1400`.
6. **Dashboard.** *Done (2026-11-27): stage 4 gate passed, part closed below.*
   - A new "Cohort Characterization" dashboard.
   - Page 1, filtered by cohort: the cohort against the population. It shows prevalence of binary
     covariates, distributions of continuous covariates, the covariates with the largest absolute
     standardized differences, and the quarterly prevalence and county incidence views.
   - Page 2: the "Compare cohorts" webapp tile at the top, with cohort B set to "Population" by
     default. Below it, the charts of `covariate_balance`, filtered by cohort and comparator.
   - Every chart reads a small table in full.
   - It is built first, next to the old dashboard.

   **Stage 4 inventory (read only, 2026-11-26).** Headless connected to the design instance
   (profile "BS Design", DSS 15.2.0). Nothing changed on SOL.
   - Old dashboard `4OpJPy0` "Cohort Discovery Insights": 2 pages, 45 tiles, version 390 (last
     modified 2025-06-25). It is checked against that version at the end of the stage.
   - `covariate_balance`: per cohort against the population, 11 continuous and 2,912–3,600 binary
     rows (cohort 1: 425 with |d| ≥ 0.1, 7 with |d| ≥ 0.2); one cached pair (1 against 2).
     Analyses 1, 2, 3, 4, 8, 9, 10, 210, 410, 901, 923.
   - `covariate` and `covariate_continuous` hold ids only; names come from `covariate_ref`.
     Covariate names carry FeatureExtraction's long prefix ("condition_era group
     (ConditionGroupEraLongTerm) during day -365 through 0 days relative to index: …").
   - The physical Snowflake columns are upper case and the DSS schemas lower case: DSS reads them,
     but an in-database chart quotes the lower-case names and fails. `cohort_definition` is upper
     case in DSS too, so its column does not match `cohort_definition_id` for a dashboard filter.
   - Quarterly prevalence and county incidence have no per-cohort table: `cohort_prevalence` and
     `cohort_location_prepared` are the old single-cohort datasets (the latter has no cohort id).
     Part 5 did not add them (decision 7 says "keyed by cohort").
   - `cohort_definition` also lists cohort 4, which is not characterized.

   **Decided (owner, 2026-11-26).** Page 1 reads tables the flow builds from the precomputed
   characterization; nothing creates datasets from the backend. Page 2 reads `covariate_balance`
   itself, so a pair the webapp writes shows at once (long covariate names and ids accepted there).
   The quarterly prevalence and county incidence views are deferred to a repo change of the
   characterization recipe (decision 7 still holds); page 1 leaves room for them. An interim
   attempt with SQL query datasets, then with library-generated queries, was dropped (never
   committed).

   **Result tables: upper-case DSS schemas (owner, 2026-11-26).** The library creates `covariate`,
   `covariate_continuous`, `covariate_ref`, `analysis_ref`, `characterization_log` and
   `covariate_balance` with unquoted columns, which Snowflake stores in upper case; their DSS
   schemas were lower case, so any SQL DSS generates on them (visual recipes, in-database charts)
   quoted names Snowflake does not hold. Their DSS schemas are now upper case, as the OMOP tables'
   are. Redshift and Databricks ignore the case. The library is unaffected: it writes with its own
   SQL, and `read_rows` matches columns in any case. The previous definitions are kept outside the
   repo.

   **Display flow (`dku`, 2026-11-26)**, zone "Cohorts", every recipe on the SQL engine, outputs
   managed on the main connection with lower-case columns:

   | Recipe | Type | Input → output | What it does |
   | --- | --- | --- | --- |
   | `compute_covariate_ref_display` | Prepare | `covariate_ref` → `covariate_ref_display` | `covariate` label by pattern replacement: regex `^.* relative to index: ` → empty (condition, drug and visit groups), `^age group:\s+(\d+)\s+-\s+(\d+)$` → `Age $1-$2`; `domain` from `analysis_id` (Demographics ≤ 10, Condition group 210, Drug group 410, Charlson index 901, Visits 923) |
   | `compute_cohort_label` | Prepare | `cohort_definition` → `cohort_label` | `cohort` = "id · name", lower-case columns |
   | `compute_characterization_latest` | Top N | `characterization_log` → `characterization_latest` | latest SUCCESS row per cohort, population included |
   | `compute_covariate_balance_display` | Join | `covariate_balance` + `covariate_ref_display` + `cohort_label` (twice) → `covariate_balance_display` | labels for covariate, cohort and comparator; `comparator` = "Population" for −1 |
   | `compute_covariate_continuous_display` | Join | `characterization_latest` (cohort ids) × `covariate_continuous` (cross) + `covariate_ref_display` + `cohort_label` → `covariate_continuous_display` | long form: one row per shown cohort, covariate and group; post-filter keeps the cohort's own rows and the population's (−1), and `group_label` says "Cohort" or "Population". The population rows repeat under each cohort id, so the cohort filter keeps them (reshaped 2026-11-26; was one wide row with `cohort_*` and `population_*` columns) |
   | `compute_cohort_filter` | Prepare | `cohort_summary` → `cohort_filter` | `cohort_definition_id` and `cohort` of characterized cohorts: the dashboard filter's values, read by no tile (added 2026-11-27) |
   | `compute_cohort_summary` | Join | `cohort_label` + `characterization_latest` (inner) + `characterization_latest` (−1, cross) → `cohort_summary` | entries, population entries, last characterization |

   - The three display datasets keep the names, and the columns, the insights read; they were
     turned from query datasets into managed tables (not deleted). Built on SOL: 13,203 / 33 / 3
     rows, every row labelled.
   - Visual recipes generate their SQL for the connection they sit on, and "Reconfigure
     Connections" moves their outputs like any managed dataset.
   - The "Characterize Cohorts" scenario has two more steps, each a forced non-recursive build (a
     recursive one could re-run the Python recipe): "Display: labels and latest runs", then
     "Display: dashboard datasets". Not run yet: the saved batch holds cohorts 4, 6 and 7, so a
     run would characterize them.
   - Dashboard-only READ is granted on the three display datasets (Cobuild asked; the project
     grants it on every old dashboard dataset the same way).

   **Page 1 insights (Cobuild, 2026-11-26).** All charts on the SQL engine, whole table:
   `la2qdJ1` Cohort summary (table); `bQK6isp` Largest differences vs population (horizontal
   bars, top 20 by max |d|, coloured by domain); `IiqXkfk` Demographics, `KqOCUkX` Condition
   groups and `KpOrTiJ` Drug groups vs population (grouped columns, cohort and population side by
   side; the last two top 20 by max |d|; DSS has no horizontal grouped bars); `Tuy4BOP` Covariate
   balance table vs population; `3tuEGAn` Continuous covariates vs population (table). The old
   dashboard is unchanged (version 390, 45 tiles).

   **How insights are built (owner, 2026-11-26).** An insight on one dataset is built as a chart in
   that dataset's Charts tab, then published. KPI figures use chart custom aggregations (as the old
   Prevalence card does), not new flow columns; the flow changes only for data no single dataset
   holds. Page 1 is mapped insight by insight from the old page 1 (approved).

   **Page 1 mapping, built (Cobuild, 2026-11-26).** Dataset charts published as insights, SQL
   engine, whole table; the old insight each replaces is in brackets.
   - Cohort statistics, KPI on `cohort_summary`: `RGxgbsb` Cohort ID (`fomAco8`), `Wt8i6Hp` Cohort
     Name (`F5eprpJ`), `Kdk4yEF` Cohort Created Date (`tfptKTs`), `0iW8jiX` Cohort Entries
     (`L5X1u3e`), `3dXg8Nb` Population (`rWJ8sZP`), `9ffUAnI` Population Prevalence, custom
     aggregation `sum(entries)/sum(population_entries)` (`HLkoVom`). KPI on `cohort`: `B7pTaIj`
     Distinct Patients, COUNTD(`SUBJECT_ID`) (`GuQHWHu`); `cohort` is authorized for dashboard
     users. Its column is upper case (`COHORT_DEFINITION_ID`), so whether one dashboard cohort
     filter reaches it is checked with the layout.
   - Demographics, grouped columns on `covariate_balance_display` (comparator −1, cohort share
     next to population share): `jA2lcxJ` Sex, analysis 1 (`KYmld44`, `APZqNnq`); `uZo0VHH` Race,
     analysis 4 (`wcP3ndC`, `zQjpyjn`); `xkqhHqa` Age groups, analysis 3 (`AJxSRT8`). KPI on
     `covariate_continuous_display`, analysis 2: `x37NrzF` mean age (cohort), `nJkGql3` median age
     (cohort), `OSezm7a` mean age (population) (`ca7H0gj`).
   - `iszrTW6` Charlson index, analysis 901: P10, P25, median, P75, P90, cohort next to population
     (`IVpIey8`, `BBCEm32`); the preset has no score bins, so no histogram.
   - `uEYMBcb` Observation time, pivot table, analyses 8–10 (`4iq4qRR`).
   - Kept: `bQK6isp` Largest differences, `Tuy4BOP` Balance table. Move to page 2: `KqOCUkX`,
     `KpOrTiJ`. Unused, to retire: `IiqXkfk` (split into the three demographic charts), `3tuEGAn`
     (replaced by `uEYMBcb`), `la2qdJ1` (replaced by the KPI cards). Dropped: `t0koor2` (broken).
     Deferred: `Xxqqxab`, `BOifR20`, `g5qMw28`, `MLL8Fq0`.
   - `dku insight validate` flags `Kdk4yEF` (MIN of a date), `9ffUAnI` (custom measure) and
     `uEYMBcb` (pivot rows in `yDimension`). The old dashboard renders all three patterns, so
     these are taken as validator limits; the owner's visual check decides.

   **Page 1 review (owner, 2026-11-26).**
   - **Observation time against the population says nothing.** The population's index is one year
     after the start of observation, so its prior observation is 365 days for everyone, and its post
     observation and time in cohort are both the rest of its observation (730 days on SYNPUF). Shown
     for the cohort only.
   - **No box plots (owner, 2026-11-26).** DSS's box-plot chart computes quartiles from rows,
     which the display datasets do not hold. A matplotlib figure drawn from the precomputed
     statistics was tried locally, but a static insight cannot follow the dashboard's cohort filter,
     and refreshing it per selection would need a webapp and a scenario, with one image shared by
     every viewer. Dropped, never deployed; the statistics tables carry the distributions.
   - **Statistics tables** (Cobuild, pivot tables, SQL engine, whole table): `mIgsl1z` and `ps9exwQ`
     Charlson (cohort, population); `vBKBS8Y` and `31npsjI` Age (cohort, population); `wKmqPnF`
     Observation time (cohort); `3k4rL4P` Sex, `Fz2AbQs` Race, `yEQwNOL` Age groups (cohort %,
     population %, std diff).
   - **Cohort and population in one table (owner, 2026-11-26)** for Charlson and Age: `8Lg0Bno`
     Charlson index statistics and `U9D7ap3` Age statistics, on the long form of
     `covariate_continuous_display`. Pivot tables with rows = `group_label` (Cohort, then
     Population) and columns N, mean, SD, min, P10, P25, median, P75, P90, max. `wKmqPnF`
     Observation time: rows = covariate, cohort only. All three rely on the dashboard's single-select
     cohort filter; without it they average across cohorts.
   - N is FeatureExtraction's `count_value`. For Charlson it is below the entry count (556 of 611 for
     cohort 1) while the minimum is 0: to confirm in step 8 whether it counts entries with a
     non-zero score.
   - Replaced, to retire: `iszrTW6` (Charlson columns), `uEYMBcb` (observation pivot with the
     population), `x37NrzF`, `nJkGql3`, `OSezm7a` (age KPI cards), and `mIgsl1z`, `ps9exwQ`,
     `vBKBS8Y`, `31npsjI` (the separate cohort and population tables). After the reshape, Cobuild moved
     every chart on `covariate_continuous_display` to the long form (12 in its Charts tab, 9
     published insights): `cohort_<stat>` became `<stat>` filtered to group "Cohort", `population_<stat>`
     the same with "Population", and side-by-side charts use `group_label` as the dimension. No
     insight references a removed column; `3tuEGAn` (dataset table) follows the schema.

   **Page 1 layout (2026-11-26).** New dashboard `yBMGZvP` "Cohort Characterization", page
   `4khRR12` "Cohort vs Population", built next to `4OpJPy0` (unchanged: version 390, 45 tiles).
   - Tiles (Cobuild, 28, `dku dashboard validate` passes): an introduction; Cohort Statistics (the
     7 KPI cards, then `bQK6isp`); Cohort Demographics (`U9D7ap3` with a note, then the age group,
     sex and race charts each beside its table); Cohort Disease Burden (`8Lg0Bno` with a note);
     Cohort Observation Duration (`wKmqPnF` with a note); All covariates (`Tuy4BOP`).
   - Dropped (owner): the county views `g5qMw28` and `MLL8Fq0`. The quarterly views (`Xxqqxab`,
     `BOifR20`) stay deferred, with no tile.
   - **Cohort filter** (`dku`, since Cobuild cannot write dashboard filters): one single-select
     page filter on `cohort` ("id · name"), values from `cohort_summary`, default "1 · Anemia".
     `cohort_summary`, `covariate_balance_display` and `covariate_continuous_display` all carry
     `cohort`; `cohort` (Distinct Patients, `B7pTaIj`) does not, so that card is expected not to
     follow the filter. To confirm visually.
   - **Owner's first look (2026-11-26).** The KPI cards do not follow the cohort filter (Distinct
     Patients shows 849 for every cohort); `bQK6isp` removed from the page (`dku`, tiles below moved
     up; 27 tiles). The DSS 15 filter page names charts and dataset tables as filterable and says
     nothing on KPI charts. The cards on `cohort_summary` in fact show "Loading Failed", while their
     chart data computes correctly with and without the filter (Cobuild, read only). The filter
     panel ran on the DSS engine (`LINO`, copied from the page default) while the charts run in
     Snowflake; it is now set to SQL. To confirm visually.
   - The Age statistics row (`U9D7ap3` and its note) removed from the page (owner; 25 tiles).
   - **Everything in-database (owner, 2026-11-26).** Every chart and KPI on the page runs on the SQL
     engine over the whole table. The dataset table `Tuy4BOP` could not: it read the first 10,000
     rows and filtered and sorted them in DSS. It is replaced on the page by `1BC5xDO` "All
     covariates vs population", a pivot table on `covariate_balance_display` (SQL, whole table,
     comparator −1, rows domain then covariate by |std diff| descending, up to 5,000 per domain,
     columns cohort %, population %, std diff, |std diff|). `Tuy4BOP` joins the list to retire.
   - **Second look (owner, 2026-11-27).** Distinct Patients (`B7pTaIj`) removed; the remaining three
     cards of that row widened to 12 columns (24 tiles). `9ffUAnI` renamed "Characterization:
     Incidence", tile "Incidence" (it is still entries over population entries). The KPI cards on
     `cohort_summary` still failed with the panel on SQL; as a test the filter panel now takes its
     values from `covariate_balance_display` (same `cohort` column), so no tile reads the panel's own
     dataset except the balance charts that already loaded.
   - **Cause found (owner, 2026-11-27).** With the panel on `covariate_balance_display` the KPI cards
     loaded and the charts on that dataset failed instead. The `cohort` labels are byte-identical in
     every dataset, so the rule is: a tile fails when it reads the filter panel's own source
     dataset. The panel now takes its values from `cohort_label`, which no tile reads. It lists
     every registered cohort, so a cohort not yet characterized (4, 6, 7 today) showed empty tiles.
   - **Filter source of its own.** A Prepare recipe `compute_cohort_filter` (SQL, zone "Dashboard")
     keeps `cohort_definition_id` and `cohort` from `cohort_summary` into `cohort_filter` (managed on
     the main connection, 3 rows today: characterized cohorts only). No tile reads it; the filter
     panel takes its values from it. The "Characterize Cohorts" scenario builds it in a fourth step,
     "Display: dashboard filter" (forced, non-recursive), after the display datasets.
     Dashboard-only users may need READ on `cohort_filter`; to check.
   - **Page 1 accepted (owner, 2026-11-27):** every tile loads and follows the filter, which lists
     the characterized cohorts only. Rule for page 2: each page's filter takes its values from a
     dataset no tile on that page reads.

   **Page 2 reads the display copy, rebuilt after each pair (owner, 2026-11-27).** Page 2's tables
   read `covariate_balance_display` (labels, domain), not raw `covariate_balance`, which supersedes
   the 2026-11-26 choice. So a pair the webapp writes must reach that copy before the tile says done.
   - **Repo (`d17047c`):** `solution/compare/services.py` takes a `refresh` callable. After writing
     a pair it reports "Computed …; updating the dashboard", rebuilds, then "Done: select … in the
     page filters". A pair in `covariate_balance` but missing from the copy (a failed rebuild, or
     one written before this change) is rebuilt without being computed again. The population pair
     (cohort B left at "Population") is already in the copy, so nothing runs. Rebuilds take their
     own lock, since DSS refuses two jobs on the same outputs.
   - `dss/webapps/compare_cohorts/backend.py` rebuilds, in order and each alone (forced,
     non-recursive), `covariate_balance_display` and `comparison_filter` (page 2's filter values, to
     create with page 2), as the webapp's run-as identity. `balance.display_pair_query` quotes the
     copy's lower-case columns per dialect.
   - Tests: 161 offline, including a new pair (compute, then rebuild), a pair already shown (nothing
     runs), a cached pair missing from the copy (rebuild only; refused without rights), a failed
     rebuild as a sentence, and the backend's build order.
   - **Applied on SOL (owner-approved, 2026-11-27).**
     - `compute_comparison_filter` (Group, SQL, zone "Dashboard"): distinct `cohort_definition_id`,
       `cohort`, `comparator_id`, `comparator` of `covariate_balance_display` into
       `comparison_filter` (4 rows: cohorts 1, 2 and 3 against the population, 1 against 2). The
       scenario's last step, now "Display: dashboard filters", builds `cohort_filter` and
       `comparison_filter`.
     - Library `python/solution` reset to `d17047c` (DSS's library reset, through the dataikuapi
       client `dku` ships with; `dku` has no command for it).
     - Webapp `c9UUBDz`: backend code replaced from the repo (the live code equalled the previous
       repo version; backup outside the repo), restarted; it started without errors.

   **Page 2 (2026-11-27).** Page `kB8Z5m6` "Cohort vs Cohort" on `yBMGZvP`, 7 tiles,
   `dku dashboard validate` passes; page 1 and `4OpJPy0` (version 390, 45 tiles) unchanged.
   - `4JKB47c` "Characterization: Compare cohorts": the webapp insight for `c9UUBDz` (`dku`; Cobuild
     cannot create webapp insights), full width at the top, titled "Request a comparison".
   - `4O5IvG9` Pair, binary covariates (rows domain then covariate by |std diff| descending; cohort %,
     comparator %, std diff, |std diff|) and `YgJfYlq` Pair, continuous covariates (cohort and
     comparator mean and SD, std diff): pivot tables on `covariate_balance_display`, SQL engine,
     whole table (Cobuild), each under a heading. An introduction says how to request a pair and
     select it.
   - Filters (`dku`): single-select `cohort` (default "1 · Anemia") and `comparator` (default
     "Population"), values from `comparison_filter`, which no tile reads (page 1's rule). The
     comparator list shows only pairs already computed.
   - **Owner's check (2026-11-27): the tables did not follow page 2's filters.** The definitions match
     page 1's working filter and the data supports them (Cobuild, read only: 3,600 binary rows for
     Anemia against the population, 3,671 against diabetes). Page 1's working filter carries a DSS id
     (`<epoch ms>_<n>`) because the owner re-created it in the UI; page 2's were hand-written
     (`p2_cohort`). They now carry DSS-style ids. If the tables still do not follow, the filters are
     re-created in the dashboard editor (Edit → page filters), as page 1's was. With DSS-style ids
     they follow (owner, 2026-11-27): hand-written filter ids must have DSS's form.
   - **Webapp follows and sets the page (owner, 2026-11-27; `b89f27e`, on SOL: library reset,
     webapp HTML, JS and backend replaced from the repo, restarted without errors).** The rebuild is
     done by the backend through the API (two forced, non-recursive dataset builds), not a scenario.
     DSS 15 documents two hooks this uses:
     - a standard webapp in a dashboard receives the page filters as `message` events
       (`event.data.type === 'filters'`): the tile's cohort A and B lists now follow the page's
       `cohort` and `comparator` filters;
     - a dashboard URL takes `pageFilters` (`cohort:in("1 · Anemia");comparator:in("Population")`):
       once a pair is ready (`cached` or `done`) and the page does not already show it, the tile
       reloads the page with that pair selected, which also refreshes the comparator list. If the
       dashboard does not let the tile navigate it, a "Show this pair on the dashboard" link stays.
     - `comparison.filter_label` and `page_filters` give the dashboard's labels ("id · name",
       "Population"); `choices` and the `cached` and `done` answers carry them. The tile's sentences
       no longer say "select … in the page filters".
     - The message schema is not documented, so the tile accepts any object naming the column
       with one selected value. Tests: 162 offline; the two browser helpers were run in node.

   **Stage 4 gate passed (owner, 2026-11-27).** Both pages accepted visually. From page 2 the tile
   follows the page filters, a pair is requested, computed, added to the dashboard and selected by
   the page reload; with cohort B at "Population" nothing runs. The old dashboard `4OpJPy0` is
   unchanged (version 390, 45 tiles). Left for stage 6 (retirement, from an approved list): the
   insights replaced during this stage (`IiqXkfk`, `3tuEGAn`, `la2qdJ1`, `iszrTW6`, `uEYMBcb`,
   `x37NrzF`, `nJkGql3`, `OSezm7a`, `mIgsl1z`, `ps9exwQ`, `vBKBS8Y`, `31npsjI`, `Tuy4BOP`, and the
   tiles dropped from page 1: `bQK6isp`, `B7pTaIj`, `U9D7ap3`). Next: stage 5, the TMP round trip on
   Redshift and Databricks.

   **Part 6 closed (owner, 2026-11-27).**
   - **Dashboard-only access.** `cohort_filter`, `comparison_filter` and the webapp `c9UUBDz` were
     not authorized for dashboard-only users (read from the project permissions); READ is now
     granted on all three, the other 35 grants unchanged (backup outside the repo). The READ on
     `cohort`, needed only by the dropped Distinct Patients card, goes in part 7.
   - **Readability items of the stage brief.** Ranking is kept: every covariate table is sorted by
     |std diff| descending. The top-N chart was dropped by the owner (`bQK6isp`), and no prevalence
     filter is added. Accepted as covered by the ranking.
   - **Moved out of part 6.** Quarterly prevalence (decision 7, a change of the characterization
     recipe) to the open questions; the county views are dropped. The meaning of Charlson's N to
     part 8. The replaced insights to part 7.
   - **`Tuy4BOP`**: a "keep comparator_id = −1" step in its table script and a sort by
     `abs_std_diff` descending (`dku`), so cached pairs do not appear on page 1.

   **Stage 5 on TMP (owner-approved, 2026-11-27).** On `TMP_RWD_SOL_V112_TEST` only, without the
   Setup, the webapp or the dashboard.
   - **Objects.** Library resynced to `8d4d282`; the 7 datasets, the recipe `characterize_cohorts`
     and the scenario "Characterize Cohorts" (id `Characterize_Cohorts`, its first step only) created
     as on SOL. The E4 batch was saved in `characterization_submission` directly; each run cleared it.
     Variables and scenarios were saved outside the repo first.
   - **Redshift** (`PREP_RWD_RS_1K`): cohorts 1–3 and the population characterized in 50 s.
   - **Databricks** (`PREP_RWD_DB_1K` on `bs-databricks-per-user`, switched as in step 2): the E4
     cohorts rebuilt to 611 / 593 / 247 with the step 2 checksums, then characterized in about 6
     minutes. No `rwdtmp_` table was left. TMP is back on Redshift; "Reconfigure Connections" empties
     the script folders, so the Redshift E4 scripts were registered and built again (same counts and
     checksums).
   - **Same results as Snowflake.** Compared through aggregates computed in each database (no rows
     left the instances):
     - binary covariates: the same ids, counts and sums per cohort (4,872 / 3,595 / 2,839 / 2,725);
       `covariate_ref` 10,292 rows and 11 analyses everywhere;
     - balance against the population: the same rows (3,611 / 2,987 / 2,923, same covariate ids);
       the pairs 1–2 and 2–3 computed on Redshift with `pair_balance_sql` give SOL's cached rows
       (3,682 and 3,147);
     - continuous covariates: the same counts and means.
   - **Rounding differs by dialect, accepted (owner, 2026-11-27).** FeatureExtraction writes
     `1.0 * x`, a decimal literal, and SqlRender keeps it. Snowflake stores binary prevalences to 6
     decimals; Redshift divides to 4 decimals before the square root of a variance, so its standard
     deviations of count covariates are low by up to 0.12% (checked against an exact recomputation);
     Databricks casts results to its 32-bit `FLOAT`. A standardized difference moves by about 10⁻⁵
     for a binary covariate and by up to about 0.1% for a count covariate on Redshift. The rendered
     SQL stays exactly SqlRender's output; a cast to double, tried in the renderer, was reverted.
   - **The 9 `DEMO_SF_RWE` inputs** (read from `DEMO_DB_RWD2`): schemas unchanged against the
     snapshot of 2026-11-18.
   - **2.3M timing deferred to D1** (owner): no project reads `DEMO_SF_PREP_OMOP_2M3` with this flow
     yet; it is measured when the demo copy is made from this branch.
   - **Left on Databricks:** 39 managed `tmp_rwd_sol_v112_test_*` tables in
     `business_solutions.default` (33 of the flow's datasets plus the characterization's 6), as in
     step 2. Dropping them waits for the owner.

7. **Retirement**, after a backup:
   - the 29 recipes and 30 datasets, and the old dashboard and its 30 insights;
   - Setup's dashboard section, `cohort_definition_id` and `section8_tile1.py`;
   - `RETIRING_KEYS` empties.

   **Part 7 on SOL (owner-approved list, 2026-11-27).** With `dku`, on SOL only.
   - **Backup.** No bundle: the owner leaves the export to the project macro test. Saved outside the
     repo: the definitions of every retired recipe, dataset, insight and scenario step, both
     dashboards, the Setup manifest, the variables and the permissions.
   - **Flow.** 30 recipes (the plan's 29 and `compute_cohort_definition_filtered`, whose output went
     too) and 30 datasets, everything downstream of it; the 4 zones they left empty ("Covariate
     Visualisation", "Cohort Features", "Cohort Selection", "Cohort Visualization"). Nothing kept read
     them. The flow check passes (104 OK, 2 unchecked, no error).
   - **Dashboard.** `4OpJPy0` and its 30 insights, and the 18 insights on no dashboard (part 6's 16,
     plus `KpOrTiJ` and `KqOCUkX`, owner). The 18 left are exactly those of `yBMGZvP`.
   - **Scenarios.** "Update Dashboard Metrics" deleted. "Build Cohort Dashboard" (id kept) is now
     "Refresh Dashboard": the SQL-engine step and a chart-cache refresh of `cohort_summary`,
     `covariate_balance_display` and `covariate_continuous_display`; a refresh by dashboard fails on
     `yBMGZvP` ("Cannot read field selection"), so it names the datasets. It ran: SUCCESS. "Format
     Solution" lost its 5 steps on the old zones and datasets; "Reconfigure Connections" no longer
     materializes the 4 retired intermediates.
   - **Setup.** The "Dashboard Creation" heading and "Create Cohort Dashboard" section removed through
     `tools/app_manifest.py`; `--check` passes on the live manifest. `section8_tile1.py`,
     `cohort_definition_choices` and `cohort_definition_id` are gone; `RETIRING_KEYS` is empty.
   - **Permissions.** 15 dashboard READ grants removed: `cohort` and the 14 retired datasets that
     still had one. 23 remain.
   - **Registry.** SOL's library pin corrected to `b89f27e`, which DSS had since part 6.
   - **Snowflake tables.** Deleting the datasets did not drop their tables; the 30 retired
     `SOL_RWD_COHORT_DISCOVERY_<name>` tables in `DKU_SOLUTION_DESIGN.SOL_DESIGN` were dropped by name
     (owner). None remains; SOL keeps 48 tables there.
8. **Verification.**
   - E4 on SOL (Snowflake) and TMP (Redshift, Databricks): identical results across the three.
   - Independent SQL checks: share of women, mean age, one condition group in the long-term
     window.
   - Standardized differences against a hand calculation, for the population and for one pair of
     E4 cohorts requested on demand.
   - After two build batches, the tile ticks every new cohort *In batch*, and one run
     characterizes both batches, which is checked in `characterization_log` and the job log. Run
     again with nothing ticked, it characterizes nothing.
   - A characterized cohort ticked *In batch* without *Replace* is refused with a sentence, and
     nothing is saved.
   - Rebuilding a characterized cohort with Replace shows it as "Rebuilt since characterized" and
     leaves its figures. Ticked *In batch* and *Replace*, it is re-characterized alone, and its
     cached pairs are deleted.
   - A cohort whose build failed is not offered.
   - The cache: a second request for the same pair computes nothing, and re-characterizing one of
     its cohorts makes the next request recompute it.
   - The webapp, from the dashboard: request a pair, see it computed, then select it in the filter.
     An unbuilt cohort is not offered. With cohort B left at "Population", nothing runs and the
     result shows at once.
   - The filter shows each E4 cohort.
   - The schemas of the 9 `DEMO_SF_RWE` inputs are unchanged.
   - Timing of one batch, with population size and cohort count recorded.

   **Part 8 on SOL (owner-approved, 2026-11-27).** Setup tile and webapp checks in the owner's
   browser; tables and logs read with `dku` after each step.
   - **Across databases:** stage 5 (above). TMP was not run again after the fixes below; they do not
     change a run that characterizes the population with its cohorts, as stage 5's did.
   - **Independent SQL, cohort 1:** women 0.520458, mean age 72.942717, "Inflammatory disorder of
     the respiratory tract" in the long-term window 267: equal to the stored values.
   - **Standardized differences by hand:** every balance row, against the population and for the
     cached pairs, equals the formula on the stored covariates (largest difference 2×10⁻¹⁶).
   - **Multi-batch:** the tile ticked cohorts 4 (built 2026-11-24 15:04) and 6, 7 (15:43); one run
     characterized the three in 191 s, the population untouched. Cohort 4, a copy of cohort 1,
     gave cohort 1's covariates exactly. A run with nothing ticked characterized nothing (30 s).
   - **Refusal:** cohort 1 ticked without *Replace* was refused with a sentence; nothing was saved.
   - **Rebuild and Replace:** cohort 3 rebuilt with *Replace* (247 again) showed "Rebuilt since
     characterized" and kept its figures; ticked *In batch* and *Replace*, it was characterized
     alone, and its cached pairs 2–3 and 3–2 left `covariate_balance`. `comparison_requests` keeps
     the request history; the cache is `covariate_balance`.
   - **Cache and webapp:** pair 2–3 requested from the dashboard computed once; the repeat
     computed nothing (one new request row). The filter lists cohorts 1–4, 6, 7.
   - **A failed build is not offered:** test cohort 8 ("Failing build (part 8 test)",
     `part8_failing_build.sql`, a first statement reading a missing column) failed at build with 0
     subjects and no `cohort` rows, and the tile does not list it. It stays registered, with test
     cohort 4, until they are removed.
   - **The 9 `DEMO_SF_RWE` inputs:** SOL's columns and types equal those of `DEMO_DB_RWD2`, which
     `DEMO_SF_RWE` reads.
   - **Timing (1K, whole scenario with its display steps):** the population (935) and 6 cohorts in
     one run, 203 s; 3 cohorts, 191 s; cohort 3 alone, 182 s. Most of it is fixed cost.
   - **Found and fixed during part 8:**
     - *An open Setup page writes its old copy of the project variables back* while a scenario it
       started runs (seen 14:16:25 and 14:16:28 after the recipe cleared the batch at 14:16:22), so
       the next run would have refused the batch just run. Saved entries now carry `saved` and
       expire once their cohort is characterized after it (`90a35f7`).
     - *"Refresh list" kept a clicked row whole*, so cohort 3 kept its old build time and status;
       it now keeps only the ticks (`09ed6ae`).
     - *Balance against the population depended on the order of runs.* A cohort characterized
       after the population read its trimmed rows, so a covariate held there by 1 to 4 people read
       as 0 instead of hiding the row (cohort 4 had 32 rows cohort 1 did not, |std diff| up to
       0.20). Owner's choice: hide them everywhere. Each run records the ids it trims in the new
       dataset `covariate_censored` (SOL and TMP, an output of `characterize_cohorts`), and every
       balance, requested pairs included, leaves out a binary row whose side is listed (`09ed6ae`).
       SOL's result tables were emptied and everything characterized again; recomputing every
       balance against the population from the stored rows now gives the run's 21,691 rows
       exactly. Pairs lose the approximation noted in step 4 part 4: pair 2–3 has 2,453 rows
       (3,147 before), equal to a recomputation, none with a trimmed side.
   - **Libraries:** SOL and TMP at `09ed6ae`; SOL's webapp restarted.
9. **Write-up.** Results in this plan; wiki articles listed for step 5.

Risks:

- **Speed at 2.3M with 50 cohorts.** The population is characterized once per import, and cohorts
  once per batch. Partition the result tables by cohort id if needed.
- **Waiting for a comparison.** The arithmetic takes about a second and runs in the backend, with
  no scenario (decision 10 as revised). A cold warehouse adds its start-up time; the tile polls, so
  the request does not time out. The time from request to chart is measured in part 8.
- **The webapp backend acts for the viewer.** It runs as one configured identity. A dashboard reader
  without the right to change the project could still have a pair written through it, so the
  backend checks the caller's rights on the project before it writes anything, and records who
  asked. The webapp's "run as" user must be able to write `covariate_balance` and
  `comparison_requests` on the main connection.
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
- Setup has no custom-mapping, metadata-CSV or dashboard section, and has a "Characterize Cohorts"
  section whose batch tile includes new cohorts by default and redoes a characterized one only
  with *Replace*;
- Setup has a "Patient Covariates" part whose "Extract Patient Covariates" section extracts the
  batch's cohorts into the per-preset datasets and `patient_cov_ref` (R9).

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
     the old ones; nothing is deleted. "Characterize cohorts" runs once on the E4 batch, and one
     pair is requested through the webapp.
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
- [ ] Boundary between Part 2 and Part 3 (R9): option A in 1.2, option C reserved for v2.0; to
  discuss with the team before the decision register
- [ ] Quarterly prevalence per cohort (R3 decision 7): a change of the characterization recipe; the
  dashboard has no tile for it yet (part 6 closed without it, 2026-11-27). The county views are dropped
- [ ] When `DEMO_SF_RWE` moves from the 5 hand-built tables to the `patient_cov_` datasets, and with which
  presets for its propensity models (LEGEND used thousands of characteristics; today's 11 presets
  are a review set)
- [x] If dashboard filters do not reach statistics cards: charts or a summary table instead. They do not
  (spike, 2026-11-20): charts for the distributions, dataset-table tiles for the frequency tables (R3)
