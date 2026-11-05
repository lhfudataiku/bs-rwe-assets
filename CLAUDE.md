<!-- GENERATED FILE: edit harness/PROJECT_INSTRUCTIONS.md, then run python3 tools/sync_harness.py --write. -->

# bs-rwe-assets

Suite repository for the RWD/RWE solution demo assets on the Dataiku design instance: the OMOP data
prep projects (Part 1), the RWD Cohort Discovery solution and its demo copy (Part 2), and the Real
World Evidence demo (Part 3). The solution library lives in `solution/` (moved from
`dataiku/bs-rwd-cohort-discovery` at `v1-1-2`); DSS pulls it as `python/solution`. The Project
Setup callbacks are thin wrappers in `app_manifest/tiles/` over `solution/setup/choices.py`;
`tools/app_manifest.py` inlines that module into each tile, because tiles cannot import the project
library.
Route documentation tasks through `docs/README.md`.

## Route before reading

- "Which project is canonical, is it built, does it pass v1.1, who owns it, what does it read":
  query `.index/` (`projects.tsv`, `schema_compliance.tsv`, `lineage.tsv`, `issues.tsv`) with bounded
  searches. Do not open `.index/dss_snapshot.json` whole; it is large.
- Scope, personas and business value: `docs/project-scoping.md`. Steps, order and gates:
  `docs/migration-revision-plan.md`. Durable choices: `docs/decisions/DECISION_REGISTER.md`.
- Live DSS state: the index is a snapshot. When the answer or the change depends on current state,
  confirm with `dku` and say when the snapshot was taken (`refreshed_at` in the snapshot).

## Non-negotiable boundaries

- Never commit or push without the user's explicit approval after a change summary.
- Do not create, build, delete or repoint a DSS project, and do not run `tools/push_wiki.py --push`,
  as a side effect of other work. Name the project and get approval first. Project deletion drops
  managed data: a bundle export comes first, and the retirement order in the migration plan holds.
- SYNPUF data must not leave internal instances. Never download it into this repo or attach it to
  an issue, a PR or a bundle stored outside Dataiku.
- `.index/` is generated: edit `registry/` and rerun `python3 tools/build_index.py`. Use `--refresh`
  only when DSS changed; it takes several minutes.
- `registry/known_issues.json` only shrinks. Delete an entry when the index shows it fixed; add one
  only when the user accepts a newly found problem as migration work, naming the plan step.
- Add to the decision register only when its admission rule is met. Open questions stay in the plan.
- New prep project keys follow `PREP_RWD_<storage>_<size>` (storage `S3`, `SF`, `DB`, `RS`; size `1K`,
  `100K`, `2M3`). The demo suite is the exception: `DEMO_SF_PREP_OMOP_2M3`,
  `DEMO_SF_RWD`, `DEMO_SF_RWE`.

## Traps that return plausible results

- DSS `project.get_variables()` returns `standard` and `local` separately, and the solution code
  reads `local` only. A project can look wired in `standard` while its `local` scope names a
  prep project that does not exist. `lineage.tsv` lists both scopes.
- `dku dataset count` and `dataset query` do not quote resolved table names. Managed Snowflake
  tables carry a `${TENANT}`/`${NODE}` suffix with `-`, so they fail with a syntax error rather than
  "does not exist". `build_index.py` retries with the quoted name.
- A non-SQL row count comes from the DSS metric, which is stale until metrics are recomputed. Treat
  `row_source=metric` as indicative. On the 2.3M S3 tables the count can time out (`built=unknown`).
- `UNREADABLE` issues are informational: the probe could not see the data (per-user Databricks OAuth
  expired, cold Databricks warehouse, Redshift refusing connections, a busy DSS). They never gate
  `--check` and cannot be baselined. Rerun `--reprobe` later before reading anything into them.
- Never use `dku dataset count` on a large non-SQL dataset: without a cached metric it starts a
  server-side computation that outlives the client timeout and stalls later reads of that project.
- The solution imports in-database: its prep tables must sit on the same type of SQL connection as
  `main_connection` (Snowflake prep tables for a Snowflake solution). Never test it against an S3 or
  filesystem prep set: a project whose datasets were reset to filesystem storage then runs the Atlas
  SQL filters in the DSS engine ("Incorrect formula"), and on Snowflake the S3 vocabulary is copied
  by row-by-row JDBC inserts (72M `concept_ancestor` rows, about 5 hours).
- The legacy DSS `date` type fails the v1.1 check. `bigint` is read as `int` and `double` as `float`,
  as the solution's `check_schema.py` does.

## Commands

    python3 tools/build_index.py --refresh   # DSS -> snapshot -> .index/ (needs dku auth, ~15 min)
    python3 tools/build_index.py --reprobe   # re-run only the built/row-count probes (after a build)
    python3 tools/build_index.py --check     # offline; what CI and the pre-commit hook run
    python3 tools/push_wiki.py               # wiki drift report (read-only)
    python3 tools/sync_harness.py --write    # regenerate CLAUDE.md and AGENTS.md from this file
    python3 -m unittest discover -s tests    # offline solution tests (DSS modules are stubbed)
    python3 tools/app_manifest.py <fetched.json> --check   # do a project's Setup tiles match the repo?
