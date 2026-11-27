"""How uploaded cohort scripts name OMOP tables (solution-revision-plan.md, R1).

One Setup choice, `cohort_script_table_naming`, replaces the uploaded JSON key map:

- `atlas`: OHDSI Atlas placeholders (`@cdm_database_schema.person`, ...). Reproduces the shipped
  `cohort_scripts/omop_cdm_atlas.json` exactly (tests/test_table_naming.py).
- `plain`: bare OMOP table names (`person`).
- `prefix`: `cohort_script_table_prefix` + the bare name (`cdm.person`), for every table.
- `mapping`: `cohort_script_table_map`, {OMOP table: name in the scripts}, typed in a table in
  Project Setup. For scripts whose tables sit under several prefixes, as Atlas exports do.

Pure: no DSS module is imported, so the Setup tile can inline it.
"""
import re

ATLAS, PLAIN, PREFIX, MAPPING = "atlas", "plain", "prefix", "mapping"
NAMINGS = (ATLAS, PLAIN, PREFIX, MAPPING)
LABELS = {ATLAS: "OHDSI Atlas placeholders", PLAIN: "Plain OMOP table names",
          PREFIX: "One prefix for every table", MAPPING: "Custom mapping table"}

CDM_TABLES = [
    "person", "observation_period", "visit_occurrence", "visit_detail", "condition_occurrence",
    "drug_exposure", "procedure_occurrence", "device_exposure", "measurement", "observation", "death",
    "note", "note_nlp", "specimen", "fact_relationship", "location", "care_site", "provider",
    "payer_plan_period", "cost", "drug_era", "dose_era", "condition_era", "episode", "episode_event",
    "metadata", "cdm_source"]
VOCABULARY_TABLES = [
    "concept", "vocabulary", "domain", "concept_class", "concept_relationship", "relationship",
    "concept_synonym", "concept_ancestor", "source_to_concept_map", "drug_strength"]
RESULTS_TABLES = ["cohort", "cohort_definition"]

ATLAS_SCHEMA = {
    **{t: "@cdm_database_schema" for t in CDM_TABLES},
    **{t: "@vocabulary_database_schema" for t in VOCABULARY_TABLES},
    "cohort_definition": "@target_database_schema",
}
ATLAS_COHORT = "@target_database_schema.@target_cohort_table"

# Atlas references the map never covers: scratch tables are rendered by build_cohorts (R6).
IGNORED_SCHEMAS = ("@temp_database_schema",)
ATLAS_REFERENCE = re.compile(r"@\w+\.@?\w+")


def naming_errors(naming=ATLAS, prefix="", mapping=None):
    """What is wrong with the naming settings, as sentences. Empty when key_map() can be built."""
    if naming not in NAMINGS:
        return ["The table naming must be one of %s, not %r." % (", ".join(NAMINGS), naming)]
    if naming == PREFIX and not (prefix or "").strip():
        return ["Type the prefix the scripts write before every OMOP table name."]
    if naming != MAPPING:
        return []
    mapping = mapping or {}
    if not isinstance(mapping, dict):
        return ["The custom mapping must be a table of OMOP table and name in the scripts."]
    errors, seen = [], {}
    known = set(CDM_TABLES + VOCABULARY_TABLES + RESULTS_TABLES)
    unknown = sorted(k for k in mapping if k not in known)
    if unknown:
        errors.append("Not OMOP tables: %s." % ", ".join(unknown))
    for table in sorted(mapping):
        name = (mapping[table] or "").strip()
        if not name:
            continue
        if name.lower() in seen:
            errors.append("%s and %s are both named %s in the scripts." % (seen[name.lower()], table, name))
        seen.setdefault(name.lower(), table)
    if not seen:
        errors.append("Give the name used in the scripts for at least one OMOP table.")
    return errors


def key_map(naming=ATLAS, prefix="", mapping=None):
    """{OMOP table key: name used in the scripts}.

    Every OMOP CDM, vocabulary and results table for `atlas`, `plain` and `prefix`; only the tables
    given a name for `mapping` (a blank name means the scripts do not use that table).
    """
    errors = naming_errors(naming, prefix, mapping)
    if errors:
        raise ValueError(" ".join(errors))
    tables = CDM_TABLES + VOCABULARY_TABLES + RESULTS_TABLES
    if naming == PLAIN:
        return {t: t for t in tables}
    if naming == PREFIX:
        return {t: prefix.strip() + t for t in tables}
    if naming == MAPPING:
        return {t: mapping[t].strip() for t in tables if (mapping.get(t) or "").strip()}
    return {t: ATLAS_COHORT if t == "cohort" else "%s.%s" % (ATLAS_SCHEMA[t], t) for t in tables}


def table_groups():
    """The OMOP tables as Setup lists them: (group label, tables)."""
    return [("Results", RESULTS_TABLES), ("Clinical data", CDM_TABLES), ("Vocabulary", VOCABULARY_TABLES)]


def unmapped_references(script, mapping):
    """Atlas-style `@schema.table` references in the script that the key map does not cover.

    Sorted, as written in the script. A script written for Atlas placeholders under the `plain` or
    `prefix` choice reports every one of them, so a wrong choice fails with a readable message.
    """
    covered = {v.lower() for v in mapping.values()}
    found = set()
    for ref in ATLAS_REFERENCE.findall(script):
        if ref.lower().startswith(tuple(s + "." for s in IGNORED_SCHEMAS)):
            continue
        if ref.lower() not in covered:
            found.add(ref)
    return sorted(found, key=str.lower)
