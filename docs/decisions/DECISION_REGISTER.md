# Decision register

> **Lifecycle:** Canonical · **Part:** all · **Audience:** asset owners, contributors and coding agents ·
> **Authority:** current durable choices for the RWD/RWE suite and their consequences ·
> **Update when:** a choice meeting the admission rule is accepted, superseded or rejected ·
> **Excludes:** open questions, migration steps, naming, scheduling and anything Git or `.index/` records.

This register is intentionally small. Add a record only when the choice meets **all** of these:

1. It fixes a contract, architecture or safety rule that other projects or teams build on.
2. Reversing it later would mean rework across more than one DSS project or repository.
3. A real alternative was weighed, or an assumption was tested, and the reason is not obvious from the result.
4. The rationale cannot be recovered cheaply from Git, the migration plan or the generated index.

Open questions stay in the [migration plan](../migration-revision-plan.md) until they are decided. A
decision is superseded, never edited away: add the new record and fill both **Supersedes** fields.

## DEC-RWD-001 — The solution keeps uppercasing OMOP columns on Snowflake

- **Date:** 2026-09-23
- **Status:** accepted
- **Decision:** `sync_omop_datasets` keeps renaming imported OMOP columns to uppercase. Prep projects and their connection variants keep lowercase names; the uppercase contract belongs to the solution's import step. The function's silent-failure bugs are fixed separately (migration plan, Workstream C).
- **Rationale:** DSS stores lowercase source columns as quoted lowercase identifiers on Snowflake. Atlas cohort SQL references columns unquoted, which Snowflake resolves as uppercase, so it fails against lowercase tables. 36 of the 46 visual recipes also hard-code uppercase names.
- **Alternatives rejected:** `QUOTED_IDENTIFIERS_IGNORE_CASE = TRUE` makes Atlas SQL work, but it also folds the quoted mixed-case table names that `get_sql_path` produces, so every dataset table would need renaming. Dropping the uppercase step breaks Atlas SQL outright.
- **Evidence:** Column-case test of 2026-09-23 (tests 0–7) and the code review in the [migration plan, Workstream C](../migration-revision-plan.md#workstream-c--sync_omop_datasets-column-case-investigation).
- **Consequences:** Any new connection variant or prep project must not uppercase columns itself. The uppercase contract is documented in the function docstring and the wiki's Data Model article. The scratch project behind the test, `TMP_RWD_SF_COLCASE_TEST`, was deleted before the fix landed, so the regression check must be rebuilt from the test table.
- **Supersedes:** —
- **Superseded by:** —

## DEC-RWD-002 — One canonical S3 project per sample size; database copies are sync-only projects

- **Date:** 2026-10-13
- **Status:** accepted
- **Decision:** Each sample size (1K, 100K, 2.3M) has one canonical prep project on S3 that does all ingestion and harmonisation. Every database copy is a separate project, `PREP_RWD_<storage>_<size>`, that shares in the 15 canonical tables and holds 15 sync recipes and nothing else.
- **Rationale:** Seven prep projects had drifted into at least two workflows, with copies of copies, and three fail the v1.1 schema check. A single transformation path per size means a failed solution run is a solution bug, not a data bug. Separate variant projects isolate sharing and can be dropped or rebuilt without touching the canonical layer.
- **Alternatives rejected:** Connection variants as flow zones inside the canonical project, the layout `SYNPUFOMOP1KDATAPREPRWDV11` uses today. It couples every variant's build and permissions to the canonical project, and is how that project ended up with an unbuilt Snowflake zone.
- **Evidence:** [Project scoping, Part 1](../project-scoping.md#part-1--omop-data-foundation); [migration plan, Workstream B](../migration-revision-plan.md#workstream-b--rebuild-the-data-prep-layer). Accepted with the migration plan on 2026-10-13.
- **Consequences:** No transformation logic in a variant project. A canonical change is followed by rebuilding its variants. Consumers point `data_preparation_project_key` at a variant (or at the S3 project), never at a retired prep project.
- **Supersedes:** the seven overlapping prep projects listed in the migration plan.
- **Superseded by:** —

## DEC-RWD-003 — Prep projects export the solution's v1.1 CDM schema, with no legacy `date` type

- **Date:** 2026-10-13
- **Status:** accepted
- **Decision:** Every canonical prep project exposes the 15 OMOP tables with lowercase column names and types matching `CDM_SCHEMA` of the solution at `v1-1-1`: `dateonly` for OMOP DATE, `datetimenotz` for DATETIME, integer ids and concept ids. The legacy DSS `date` type is not allowed. Nothing downstream is built until the index shows 15/15 pass for that project.
- **Rationale:** The legacy `date` type is why `SYNPUFOMOP23DATAPREPARATION`, `DATABRICKSSYNPUFOMOP23DATAPREPERATION` and `DEMO_SF_OMOP2M_DATAPREP` fail 13 of 15 tables. Making the solution's own check the contract, enforced by the index, stops the prep layer from drifting from the solution again.
- **Alternatives rejected:** Relaxing the solution's schema check to accept `date`. The release and demo would then run on different column types, the drift this revision removes, and the legacy type carries a timezone where OMOP DATE has none.
- **Evidence:** 2026-09-23 audit in the [migration plan](../migration-revision-plan.md#current-state-audit); `.index/schema_compliance.tsv`; `tools/vendor/cdm_schema.py`.
- **Consequences:** CDM v5.2 sources (the 2.3M lzo files) are mapped to v5.3 columns in the canonical project. Ids that exceed 32-bit range stay `bigint`; the solution's check reads `bigint` as `int` and must keep doing so (Workstream C, change 4). A change to `CDM_SCHEMA` in the solution repo is re-vendored here in the same release.
- **Supersedes:** —
- **Superseded by:** —
