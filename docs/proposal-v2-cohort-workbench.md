# RWD Cohort Discovery v2.0 — Cohort Workbench (proposal)

> **Lifecycle:** Proposal (not accepted; future work after the migration plan closes) · **Part:** 2 ·
> **Audience:** asset owners, solution developers and coding agents · **Authority:** scope, design,
> milestones and estimate for v2.0 of `SOL_RWD_COHORT_DISCOVERY` · **Update when:** the proposal is
> accepted, rejected or re-scoped, or a milestone's design or estimate changes.

## Summary

v2.0 moves cohort work out of Project Setup and into a webapp inside the solution, the **Cohort
Workbench**. Users register cohorts, build them, characterize them, compare two of them and browse the
library in one place.

- **Project Setup** keeps only the one-time configuration (S1–S3): connections, the OMOP table mapping,
  and how uploaded scripts name tables.
- **Backend:** the OHDSI backend components are reused, but the Java WebAPI service is not deployed.
  Concretely: Circe through **Circepy** (Python), SqlRender through Circepy's translator, the
  **FeatureExtraction** SQL templates, and the **WebAPI** vocabulary and characterization SQL.
- **UI:** built on the team's webapp framework, **bs-blueprint** (Vue 3 on `@dataiku/ea-ui-kit`,
  FastAPI backend).
- **Build:** the MVP is estimated at **7–9 calendar weeks** as a controlled build by a coding assistant
  with gated human review.
- **Go/no-go:** milestone M0, a one-week feasibility check, decides whether to go ahead.
- **Release line:** v1.2 ([`solution-revision-plan.md`](solution-revision-plan.md)) stays the release
  the demo suite is recreated from. v2.0 starts after the migration plan closes, unless the owner
  starts M0 earlier, and the demo is rebuilt on it afterwards (migration plan, Workstream D).

## Why

| Today (v1.x) | Consequence |
| --- | --- |
| Cohort upload, metadata CSV, building and dashboard selection all live in Project Setup tiles and scenarios | Setup mixes one-time configuration with day-to-day work; every step is a separate button and scenario |
| Cohorts arrive only as SQL rendered by an external Atlas, with a separate metadata CSV | No way to see or check a definition inside the solution; filenames and ids are matched by hand |
| The dashboard shows one cohort at a time and is rebuilt to switch | No side-by-side comparison |
| Our characteristics are a hand-built subset of Atlas's | No standardized difference between cohorts, the core of Atlas-style cohort validation; no time windows |

What the live Atlas reference does: characterization 1071 ("LEGEND HTN Demo 1", `atlas-demo.ohdsi.org`,
WebAPI 2.14) runs 52 preset feature analyses over 2 cohorts. Its results are one row per covariate:
either a prevalence (count, proportion) or a distribution (mean, sd, min, p10, p25, median, p75, p90,
max), per cohort, stratum and time window, with a standardized difference when two cohorts are
compared. The server holds 408 feature analyses, 106 of them presets.

## Scope of v2.0 (MVP)

| Area | In v2.0 |
| --- | --- |
| Project Setup | S1–S3 only: connections and SQL pipeline toggle; prep project, OMOP table mapping and import; cohort script table naming |
| Cohort library | List all cohorts with id, name, description, source (Atlas JSON or SQL), status, subject count and last build; cohort detail with Circepy's readable description |
| Registration | Upload Atlas cohort JSON (compiled by Circepy) or rendered SQL (today's path); one form for id, name and description; repeated submissions; an existing id is refused unless **Replace** is chosen |
| Build | Runs as a DSS job, never inside the webapp process. Per-cohort status, count and error; temporary tables cleaned up; one build at a time per project |
| Characterization | Today's characteristics re-expressed as FeatureExtraction presets: gender, race, age, age group, time in cohort, prior and post observation, Charlson, condition groups, drug groups, visit counts, with time windows. Results stored per cohort |
| Comparison | Two cohorts side by side: prevalence and distribution tables, standardized difference, a balance scatter plot |
| Our own views | Quarterly prevalence and the county map, which FeatureExtraction does not cover |
| Data contract | The 9 datasets `DEMO_SF_RWE` reads are still produced, same names and columns: `cohort`, `cohort_definition`, `concept`, `concept_ancestor`, `charlson_score_occurrence`, `condition_group_occurrence`, `drug_class_exposure`, `person_location_joined`, `visit_occurrence_labeled` |
| Dialects | Snowflake, Databricks and Redshift, as in v1.x |

**Later (v2.x), not in the MVP:**

- Concept search and concept-set editor (M5).
- Cohort definition editor (M6). Until then, definitions are written in any Atlas and imported as JSON.
- The full 106-preset catalogue, measurement values, the CHADS2, CHA2DS2-VASc, DCSI and HFRS scores,
  strata, and custom criteria features.
- Incidence rates and pathways.

**Out of scope:** deploying Atlas or WebAPI themselves; sharing cohorts between projects;
multiple users editing one project at the same time.

## Architecture

```text
Project Setup (S1–S3)           Cohort Workbench webapp (bs-blueprint)
  connections, prep project,      Vue 3 + @dataiku/ea-ui-kit  ──REST──  FastAPI backend
  table mapping, naming                                                   │
                                                  ┌───────────────────────┼─────────────────────┐
                                                  │                       │                     │
                                          registry (SQLite:      Circepy: JSON → SQL     job runner → DSS job
                                          definitions, versions)  + dialect translation   (static recipe)
                                                                  FeatureExtraction port       │
                                                                  WebAPI SQL (vocab, CC)       ▼
                                                                                    main_connection (SF/DB/RS):
                                                                                    cohort, cohort_definition,
                                                                                    cc_results, feature datasets
```

- **Backend.** The starter's layout: routes parse HTTP and services hold the logic. DSS is reached
  through `get_project()` and `SQLExecutor2` on `main_connection`, and table names are resolved by DSS
  (`get_location_info()`, v1.2 R4). Settings come from the Setup variables.
- **State.** Definitions, versions and job records live in SQLite, as the blueprint prescribes: single
  writer, one uvicorn worker. Cohort and result tables live in-database on the main connection.
- **Builds.** The webapp starts a DSS job on a static recipe (v1.2 R5) and polls it. DSS refuses a
  second job on the same outputs, so concurrent builds are rejected rather than mixed. Databricks
  temporary tables follow v1.2 R6.
- **Frontend.** The starter's shell, hash routing and `apiUrl()`. The doctor, design lint and typecheck
  must be clean.
- **Deploy.** `dku` CLI into the solution project's library and webapp, as the blueprint prescribes.

## Reused OHDSI components

| Component | What we take | Size | Licence |
| --- | --- | --- | --- |
| [Circepy](https://github.com/OHDSI/Circepy) v0.3.0 | Cohort expression models, SQL generation, 40+ validation checks, readable descriptions, dialect translation (`circe.sqlrender`: Snowflake, Spark, Redshift and others), batch generation with checksum skipping | Python library, used as a dependency | Apache-2.0 |
| [FeatureExtraction](https://github.com/OHDSI/FeatureExtraction) v3.14.0 | `inst/sql/sql_server/*.sql` (27 templates) and `inst/csv/PrespecAnalyses.csv`; the Java layer only renders them, and we port that renderer to Python | 33 SQL files | Apache-2.0 |
| [WebAPI](https://github.com/OHDSI/WebAPI) v3.0.1 | `resources/vocabulary/sql` (27 files: search, ancestors, related, mapped codes, concept-set resolution; needed from M5) and `resources/cohortcharacterizations/sql` (10 files) | 37 SQL files | Apache-2.0 |

Ported SQL keeps its upstream licence header, and the solution adds a NOTICE entry. Atlas and Atlas3 UI
code is not reused.

## Milestones, acceptance and estimate

The build is done by a coding assistant under these controls. Each milestone:

1. starts from a written spec with acceptance tests written before the code;
2. passes the automated checks;
3. is deployed to a scratch DSS project with the owner's approval;
4. is verified on all three dialects;
5. ends with the owner's review and a merged PR.

| Milestone | Scope | Acceptance | Calendar |
| --- | --- | --- | --- |
| **M0 Feasibility (go/no-go)** | Circepy on the 3 E4 cohorts; one FeatureExtraction template rendered and translated; starter deployed to a scratch project; Snowflake query time for the characterization of one cohort at 2.3M | Counts 611, 593, 247 on SF, DB and RS; the template runs on all three; deploy round trip works | 1 week |
| M1 Backend core | DSS executor and table resolution, settings, SQLite registry, registration with the id guard, JSON and SQL paths, job runner with temp-table cleanup | pytest; E4 counts reproduced through the webapp API | 1.5–2 weeks |
| M2 Library UI | Browse, register, build progress, cohort detail | Doctor, design lint and typecheck clean; owner UI review | 1 week |
| M3 Characterization engine | FeatureExtraction port, presets for today's characteristics, result tables, standardized difference | E4 cohorts' figures equal today's dashboard (same windows and definitions) | 2 weeks |
| M4 Characterization UI | Results tables, comparison, balance plot, quarterly prevalence and county views | Owner review; parity with today's dashboard | 1.5 weeks |
| M7a Release | Code env, Setup cut to S1–S3, the 9-dataset contract for `DEMO_SF_RWE`, project macro test, wiki | v2.0 gate below | 1 week |
| **v2.0 total** | | | **7–9 weeks** |
| M5 (v2.x) | Vocabulary service and concept-set editor | Resolution equals WebAPI's for sample concept sets | 2 weeks |
| M6 (v2.x) | Cohort editor, common subset; Atlas JSON round trip; SQL preview | Round trip unchanged; generated SQL equals reference SQL | 2.5–3 weeks |
| M7b (v2.x) | 2.3M performance, permissions | | 1 week |

**Assumptions behind the estimate:**

- one assistant session per working day;
- 1–2 hours a day of owner review;
- DSS deploy approvals within a day.

Long 2.3M builds and slower reviews stretch it. Writing code is not the bottleneck; verification on
three dialects and review are.

**v2.0 gate:**

- E4 counts unchanged on all three dialects;
- characterization of the E4 cohorts equals the v1.2 dashboard;
- a two-cohort comparison renders with standardized differences;
- repeated submissions work and a reused id is refused without **Replace**;
- `DEMO_SF_RWE` builds unchanged against the v2.0 outputs;
- the project macro test passes;
- the blueprint checks are clean.

## Controls for an assistant-led build

The blueprint checks the frontend (doctor, design lint, typecheck) but has no backend tests or CI. Add
these before M1:

- pytest for the backend, run with the repo's offline tests.
- A parity suite with fixed reference answers:
  - E4 counts;
  - characterization figures against the v1.2 dashboard;
  - generated SQL against reference SQL from the public `api.ohdsi.org/WebAPI/cohortdefinition/sql`
    (only test cohort definitions are sent, never data);
  - concept-set resolution (M5).
- A dialect matrix (SF, DB, RS) run in a scratch DSS project.
- One branch and PR per milestone, merged after owner review.
- The existing rules hold:
  - no DSS project change, build or deploy without approval;
  - SYNPUF data never leaves internal instances;
  - the interactive GitHub Packages login is run by a person.

## Risks

| Risk | Mitigation |
| --- | --- |
| Circepy is v0.3 and states it is under active development | M0 counts decide go/no-go; pin the version; the SQL-upload path stays as a fallback |
| Circepy's translation differs from Java SqlRender on a dialect | Reference-SQL parity tests; E4 matrix on SF, DB and RS |
| FeatureExtraction presets differ from today's hand-built features (windows, Charlson variant) | M3 parity defines the mapping explicitly; differences are documented, not hidden |
| Webapp limits: one backend process, single SQLite writer, one service identity | Builds run as DSS jobs; the backend checks each caller's project rights; one uvicorn worker |
| Characterization cost at 2.3M with many cohorts | Results computed once per build and stored; M0 times one cohort; partition by cohort if needed |
| New dependencies: FastAPI, Circepy, pydantic, jinja2 | A dedicated code env. This reverses v1.2's "instance default" (R8) for v2.0 only |
| UI scope creep toward full Atlas | MVP excludes the editors; definitions come from any Atlas as JSON until M6 |
| The 45-cohort demo library exists only as SQL, without Atlas JSON | The SQL path stays first-class; recovering the JSON is optional |

## Relationship to v1.2

- **Carried into v2.0:**
  - R4 table resolution;
  - R5 static build recipe;
  - R6 Databricks temp tables;
  - R7 variables.

  They are designed so v2.0 builds on them.
- **Superseded by the webapp:**
  - R2 registration tiles;
  - R3 dashboard precompute.

  If v2.0 is accepted before v1.2's Setup work starts, the owner can drop those two from v1.2 and keep
  only the Setup simplification.
- **Narrowed:** R1 (table naming) applies only to the SQL path, since Circepy generates fully qualified
  SQL from JSON.

## Decisions needed

- [ ] Accept v2.0 as defined here, and when to run M0
- [ ] Keep the v1.x DSS dashboard in v2.0 alongside the webapp, or retire it
- [ ] Minimum Circepy version to pin after M0
- [ ] Whether v1.2 still ships R2 and R3, or only the Setup simplification, once v2.0 is accepted
