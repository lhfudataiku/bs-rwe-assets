# Document set

> **Lifecycle:** Canonical · **Part:** all · **Audience:** asset owners, contributors and coding agents ·
> **Authority:** router for the suite's documents · **Update when:** a document is added, moved or
> changes role.

Factual questions (which project, built or not, passes v1.1 or not, what reads what) go to
`.index/` first; [`.index/SUMMARY.md`](../.index/SUMMARY.md) is the one-page view. Read the documents
below for scope, method and rationale.

## Start

| | |
|---|---|
| [`project-scoping.md`](project-scoping.md) | The three parts and the index: scope, business value, personas, owners, success criteria |
| [`migration-revision-plan.md`](migration-revision-plan.md) | Per-project decisions, the 2026-09-23 audit, Workstreams A, B, D and E (C folded into E), phases and gates |
| [`decisions/DECISION_REGISTER.md`](decisions/DECISION_REGISTER.md) | Durable choices only (`DEC-RWD-###`), with the admission rule |
| [`governance-mvp-proposal.md`](governance-mvp-proposal.md) | Proposal: Govern workflow, controls and gated deployment for the suite (not yet accepted) |

## Part 1 — OMOP Data Foundation

| | |
|---|---|
| [`project-scoping.md` § Part 1](project-scoping.md#part-1--omop-data-foundation) | Canonical S3 projects, connection variants, schema contract |
| [`.index/schema_compliance.tsv`](../.index/schema_compliance.tsv) | Each prep project's OMOP tables against `CDM_SCHEMA` v1-1-1 |
| `wiki/PREP_RWD_*/` | Not created yet; drafts follow [`wiki/_template/`](wiki/_template/) when the projects exist |

## Part 2 — RWD Cohort Discovery

| | |
|---|---|
| [`wiki/SOL_RWD_COHORT_DISCOVERY/`](wiki/SOL_RWD_COHORT_DISCOVERY/) | Mirror of the release project's wiki |
| [`wiki/DEMO_SF_RWD/`](wiki/DEMO_SF_RWD/) | Mirror of the demo project's wiki |

## Part 3 — Real World Evidence

| | |
|---|---|
| [`wiki/DEMO_SF_RWE/`](wiki/DEMO_SF_RWE/) | Mirror of the RWE demo's wiki |

## Generated and hand-written sources

| | |
|---|---|
| [`../registry/projects.json`](../registry/projects.json) | Hand-written: one entry per DSS project (part, role, lifecycle, owner, OMOP sets) |
| [`../registry/known_issues.json`](../registry/known_issues.json) | Hand-written baseline of accepted problems; only shrinks |
| [`../.index/index_metadata.tsv`](../.index/index_metadata.tsv) | Every generated index, its owner, freshness command and scope |

## Wiki drafts

`wiki/<PROJECT>/` holds article bodies byte-for-byte as DSS stores them, with `index.json` mapping
files to titles. `python3 tools/push_wiki.py` reports drift; `--push <PROJECT>` writes to DSS and
needs the project owner's approval. Doc headers are not added inside wiki drafts, since they would
be published.
