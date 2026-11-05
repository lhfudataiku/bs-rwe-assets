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
- **Decision:** `sync_omop_datasets` keeps renaming imported OMOP columns to uppercase. Prep projects and their connection variants keep lowercase names; the uppercase contract belongs to the solution's import step. The function's silent-failure bugs are fixed separately (migration plan, Workstream E import fixes).
- **Rationale:** DSS stores lowercase source columns as quoted lowercase identifiers on Snowflake. Atlas cohort SQL references columns unquoted, which Snowflake resolves as uppercase, so it fails against lowercase tables. 36 of the 46 visual recipes also hard-code uppercase names.
- **Alternatives rejected:** `QUOTED_IDENTIFIERS_IGNORE_CASE = TRUE` makes Atlas SQL work, but it also folds the quoted mixed-case table names that `get_sql_path` produces, so every dataset table would need renaming. Dropping the uppercase step breaks Atlas SQL outright.
- **Evidence:** Column-case test of 2026-09-23 (tests 0–7) and the code review in the [migration plan, appendix](../migration-revision-plan.md#appendix--column-case-test-evidence-for-dec-rwd-001).
- **Consequences:** Any new connection variant or prep project must not uppercase columns itself. The uppercase contract is documented in the function docstring and the wiki's Data Model article. The scratch project behind the test, `TMP_RWD_SF_COLCASE_TEST`, was deleted early and recreated on 2026-10-15; tests 0–4 and 6 reproduce, and E3 turns tests 1, 3 and 6 into an index check.
- **Supersedes:** —
- **Superseded by:** —

## DEC-RWD-002 — One canonical S3 project per sample size; database copies are sync-only projects

- **Date:** 2026-10-13
- **Status:** accepted
- **Decision:** Each sample size (1K, 100K, 2.3M) has one canonical prep project on S3 that does all ingestion and harmonisation. Every database copy is a separate project, `PREP_RWD_<storage>_<size>`, that shares in the 15 canonical tables and holds 15 sync recipes and nothing else.
- **Rationale:** Seven prep projects had drifted into at least two workflows, with copies of copies, and three fail the v1.1 schema check. A single transformation path per size means a failed solution run is a solution bug, not a data bug. Separate variant projects isolate sharing and can be dropped or rebuilt without touching the canonical layer.
- **Alternatives rejected:** Connection variants as flow zones inside the canonical project, the layout `SYNPUFOMOP1KDATAPREPRWDV11` uses today. It couples every variant's build and permissions to the canonical project, and is how that project ended up with an unbuilt Snowflake zone.
- **Evidence:** [Project scoping, Part 1](../project-scoping.md#part-1--omop-data-foundation); [migration plan, Workstream B](../migration-revision-plan.md#workstream-b--rebuild-the-data-prep-layer). Accepted with the migration plan on 2026-10-13.
- **Consequences:** No transformation logic in a variant project. A canonical change is followed by rebuilding its variants. Consumers point `data_preparation_project_key` at a variant (or at the S3 project), never at a retired prep project. One exception: the demo suite's 2.3M Snowflake set is a full copy (DEC-RWD-004).
- **Supersedes:** the seven overlapping prep projects listed in the migration plan.
- **Superseded by:** —

## DEC-RWD-003 — Prep projects export the solution's v1.1 CDM schema, with no legacy `date` type

- **Date:** 2026-10-13
- **Status:** accepted
- **Decision:** Every canonical prep project exposes the 15 OMOP tables with lowercase column names and types matching `CDM_SCHEMA` of the solution at `v1-1-1`: `dateonly` for OMOP DATE, `datetimenotz` for DATETIME, integer ids and concept ids. The legacy DSS `date` type is not allowed. Nothing downstream is built until the index shows 15/15 pass for that project.
- **Rationale:** The legacy `date` type is why `SYNPUFOMOP23DATAPREPARATION`, `DATABRICKSSYNPUFOMOP23DATAPREPERATION` and `DEMO_SF_OMOP2M_DATAPREP` fail 13 of 15 tables. Making the solution's own check the contract, enforced by the index, stops the prep layer from drifting from the solution again.
- **Alternatives rejected:** Relaxing the solution's schema check to accept `date`. The release and demo would then run on different column types, the drift this revision removes, and the legacy type carries a timezone where OMOP DATE has none.
- **Evidence:** 2026-09-23 audit in the [migration plan](../migration-revision-plan.md#current-state-audit); `.index/schema_compliance.tsv`; `tools/vendor/cdm_schema.py`.
- **Consequences:** CDM v5.2 sources (the 2.3M lzo files) are mapped to v5.3 columns in the canonical project. Prep projects may store ids as `bigint`; the solution's check reads `bigint` as `int` and its import narrows them to `int`, as its Data Model article documents. The largest ids at 2.3M (289,182,385) and in the Athena vocabulary (46,369,944) fit in `int`. A change to `CDM_SCHEMA` in the solution repo is re-vendored here in the same release.
- **Supersedes:** —
- **Superseded by:** —

## DEC-RWD-004 — The demo suite's 2.3M prep project is a full copy of `PREP_RWD_S3_2M3`

- **Date:** 2026-10-16
- **Status:** accepted
- **Decision:** `DEMO_SF_PREP_OMOP_2M3`, the 2.3M Snowflake set that was planned as `PREP_RWD_SF_2M3`, is a duplicate of `PREP_RWD_S3_2M3`: the same zones, recipes and dataset names, with its managed datasets on Snowflake. It is the one exception to DEC-RWD-002. `PREP_RWD_SF_1K`, `PREP_RWD_DB_1K` and `PREP_RWD_RS_1K` stay sync-only variants.
- **Rationale:** The demo suite (`DEMO_SF_PREP_OMOP_2M3`, `DEMO_SF_RWD`, `DEMO_SF_RWE`) has to stand alone, so that it can be bundled, moved or rebuilt without its S3 canonical project. A sync-only variant always needs its canonical project next to it at run time.
- **Alternatives rejected:** A sync-only `PREP_RWD_SF_2M3` (DEC-RWD-002), which ties the demo suite to `PREP_RWD_S3_2M3` at run time. Full copies for every database project, which would give up the single transformation path per size that the solution's test variants rely on.
- **Evidence:** Owner's revision of the [migration plan](../migration-revision-plan.md#workstream-b--rebuild-the-data-prep-layer) on 2026-10-16 (Workstream B).
- **Consequences:** This one copy can drift from its canonical project. It passes the schema gate itself (DEC-RWD-003), and its row counts must equal those of `PREP_RWD_S3_2M3`. A change to `PREP_RWD_S3_2M3` is applied to the copy, which is then rebuilt. The copy reruns the 2.3M download and parse. DEC-RWD-001 still holds: the copy keeps lowercase columns.
- **Supersedes:** —
- **Superseded by:** —

## DEC-RWD-005 — `bs-snowflake` hosts the suite's Snowflake prep data and demo suite

- **Date:** 2026-11-05
- **Status:** accepted
- **Decision:** `PREP_RWD_SF_1K`, `DEMO_SF_PREP_OMOP_2M3` and the recreated `DEMO_SF_RWD` put their managed Snowflake datasets on `bs-snowflake` (database `DKU_SOLUTION_DESIGN`, schema `SOL_DESIGN`). `managed-snowflake` is not used for the suite.
- **Rationale:** Owner's choice. `bs-snowflake` is the connection that held the suite's only built Snowflake table (`visit_occurrence_sf`) and that the column-case tests (DEC-RWD-001) and `TMP_RWD_SOL_V112_TEST` ran on. The solution imports in-database, so the prep sets and the consuming solution projects must share one Snowflake connection type.
- **Alternatives rejected:** `managed-snowflake`, a global key-pair connection (database `BS_PLATFORM_DESIGN`). It tested as working on 2026-11-05 and does not depend on a user's OAuth grant, but none of the suite's tables on it were ever built.
- **Evidence:** `dku connection get` and `dku connection test` on 2026-11-05 (DSS 15.2): `bs-snowflake` is `OAUTH2_APP` with per-user credentials; `managed-snowflake` is `KEY_PAIR` with global credentials; both work.
- **Consequences:** Builds and scenarios on these projects run with the run-as user's Snowflake grant. An expired grant fails builds and makes the index report `UNREADABLE`, as with `bs-databricks-per-user`. Scenarios run as a named user with a current grant, and the grant is renewed before phase 3 and 4 builds. Moving to `managed-snowflake` later means rebuilding all three projects.
- **Supersedes:** —
- **Superseded by:** —
