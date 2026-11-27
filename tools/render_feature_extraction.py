#!/usr/bin/env python3
"""Render FeatureExtraction's covariate SQL for the solution's presets (solution-revision-plan.md, step 4 part 1; R9).

The characterization runs FeatureExtraction's own SQL, as Atlas does: `FeatureExtraction.createSql`
assembles the presets from its templates, and SqlRender translates the result to each dialect. Both
are Java and run here, offline, never in DSS. The output is checked in, like `cohort_scripts/`, and
the recipes only read it. The same presets are rendered in two modes (MODES):
- aggregated, one row per cohort and covariate, for the characterization:
  `solution/characterization/sql/<connection>/`;
- person, FeatureExtraction's non-aggregated mode, one row per cohort entry and covariate, for the
  patient-level extract (R9): `solution/characterization/sql/<connection>/person/`. Its scratch
  tables hold one analysis each (PERSON_TABLES), and its analysis and covariate ids are checked equal
  to the aggregated render's before anything is written.

    python3 tools/render_feature_extraction.py --fetch   # download the pinned jars once (needs network)
    python3 tools/render_feature_extraction.py           # render and write the SQL files
    python3 tools/render_feature_extraction.py --check   # exit 1 unless a rerun gives the same bytes

Needs Java 11 or later. The jars live in `~/.cache/bs-rwe-assets/jars/` (or `$BS_RWE_JAR_DIR`), are
pinned by SHA-256 and are never committed.

Placeholders left in the SQL, filled at run time:
- `@cdm_database_schema.<table>`: every OMOP table, vocabulary included, as FeatureExtraction writes
  it. This is a fixed token of the solution's own SQL, not a naming the user chooses: the engine
  replaces each with the resolved name of the project dataset of that table, whatever the
  `cohort_script_table_naming` setting (which describes only the uploaded cohort scripts) says. A
  bare table name could not be replaced safely, since the SQL also uses table names as aliases
  (`person.person_id`);
- `@characterization_cohort` (aggregated): the table of cohorts to characterize (subject_id,
  cohort_definition_id, cohort_start_date, cohort_end_date), all of whose cohorts are characterized;
- `@extraction_cohort` (person): the table of cohort entries to extract, with the same columns plus
  `row_id`, one per entry, which the SQL writes in place of the entry;
- Databricks only: `@temp_database_schema.<session><name>`, the scratch tables (R6), as in Atlas's
  Databricks exports. Snowflake and Redshift use session temporary tables.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "solution", "characterization", "sql")
LAUNCHER = os.path.join(ROOT, "tools", "feature_extraction", "Render.java")
JAR_DIR = os.environ.get("BS_RWE_JAR_DIR", os.path.expanduser("~/.cache/bs-rwe-assets/jars"))

FEATURE_EXTRACTION = "3.14.0"
SQL_RENDER = "1.19.7"
JARS = [  # (file, source, SHA-256)
    ("featureExtraction-3.14.0.jar",
     "https://raw.githubusercontent.com/OHDSI/FeatureExtraction/v3.14.0/inst/java/featureExtraction-3.14.0.jar",
     "148c135b5461287933e45215d633318bd0a81778989061930bcde3604096ccd5"),
    ("json-20231013.jar",
     "https://raw.githubusercontent.com/OHDSI/FeatureExtraction/v3.14.0/inst/java/json-20231013.jar",
     "0f18192df289114e17aa1a0d0a7f8372cc9f5c7e4f7e39adcf8906fe714fa7d3"),
    ("SqlRender-1.19.7.jar",
     "https://raw.githubusercontent.com/OHDSI/SqlRender/v1.19.7/inst/java/SqlRender.jar",
     "dc152542636e6f48d689a17b71cce31ce2d77160b76ce599b76f1e06a7e4d211"),
]

# R3 decision 6 (owner, 2026-11-24; visits long-term only, 2026-11-25; any-time-prior dropped,
# 2026-11-25: the population has exactly one year of history, so any-time-prior equals long-term for
# it and inflates every cohort against it).
PRESETS = [
    "DemographicsGender", "DemographicsRace", "DemographicsAge", "DemographicsAgeGroup",
    "DemographicsTimeInCohort", "DemographicsPriorObservationTime", "DemographicsPostObservationTime",
    "CharlsonIndex",
    "ConditionGroupEraLongTerm", "DrugGroupEraLongTerm",
    "VisitConceptCountLongTerm",
]
WINDOWS = {"longTermStartDays": -365, "mediumTermStartDays": -180, "shortTermStartDays": -30, "endDays": 0}

CDM_SCHEMA = "@cdm_database_schema"
SESSION_ID = "rwdfeatx"  # fixed, so the scratch table names (and the files) are reproducible
# Connection type (folder) -> SqlRender dialect, with the temp emulation schema where tables are real.
DIALECTS = {"snowflake": "snowflake", "databricks": "spark=@temp_database_schema", "redshift": "redshift"}
# createSql part -> file
PARTS = {
    "sqlConstruction": "construction.sql",
    "sqlQueryFeatures": "query_covariates.sql",
    "sqlQueryContinuousFeatures": "query_covariates_continuous.sql",
    "sqlQueryFeatureRef": "query_covariate_ref.sql",
    "sqlQueryAnalysisRef": "query_analysis_ref.sql",
    "sqlCleanup": "cleanup.sql",
}
# The non-aggregated mode has no continuous query: binary and continuous rows share the columns
# row_id, covariate_id, covariate_value.
PERSON_PARTS = {part: name for part, name in PARTS.items() if part != "sqlQueryContinuousFeatures"}
# Mode -> how createSql is called, where its files go (under each connection folder), its cohort table.
MODES = {
    "aggregated": {"aggregated": True, "row_id_field": "subject_id", "cohort_table": "@characterization_cohort",
                   "subfolder": "", "files": PARTS},
    "person": {"aggregated": False, "row_id_field": "row_id", "cohort_table": "@extraction_cohort",
               "subfolder": "person", "files": PERSON_PARTS},
}
# Person mode: the scratch table holding each analysis's rows (R9), by its bare name. The extract
# writes each preset's dataset from its table; the render fails if FeatureExtraction lays them out
# differently. Snowflake and Databricks prefix the name with SESSION_ID; Redshift keeps `#cov_N`.
PERSON_TABLES = {"cov_1": 210, "cov_2": 10, "cov_3": 1, "cov_4": 4, "cov_5": 9, "cov_6": 923, "cov_7": 901,
                 "cov_8": 3, "cov_9": 2, "cov_10": 8, "cov_11": 410}
HEADER = ("-- Generated by tools/render_feature_extraction.py from FeatureExtraction %s and SqlRender %s\n"
          "-- (Apache-2.0, see %sNOTICE) for %s. Do not edit; rerun the tool.\n")
NOTICE = """FeatureExtraction SQL rendered for the RWD Cohort Discovery solution

The SQL files in this folder are generated by tools/render_feature_extraction.py from the SQL
templates of FeatureExtraction %s (https://github.com/OHDSI/FeatureExtraction) and translated with
SqlRender %s (https://github.com/OHDSI/SqlRender). Both are Copyright Observational Health Data
Sciences and Informatics and licensed under the Apache License, Version 2.0:
https://www.apache.org/licenses/LICENSE-2.0

Changes: the templates are rendered for the presets listed in MANIFEST.json, in the modes listed
there (aggregated, and non-aggregated in the person/ folders), with the placeholders described there
left for the solution to fill, and translated to each folder's dialect.
""" % (FEATURE_EXTRACTION, SQL_RENDER)


def settings():
    """FeatureExtraction's covariate settings, as its R function createCovariateSettings writes them."""
    value = {"temporal": False, "temporalSequence": False}
    value.update({name: True for name in PRESETS})
    value.update(WINDOWS)
    value.update({"includedCovariateConceptIds": [], "addDescendantsToInclude": False,
                  "excludedCovariateConceptIds": [], "addDescendantsToExclude": False,
                  "includedCovariateIds": []})
    return value


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def jar_paths(fetch=False):
    paths = []
    for name, url, digest in JARS:
        path = os.path.join(JAR_DIR, name)
        if not os.path.exists(path):
            if not fetch:
                raise SystemExit("%s is missing; run with --fetch to download the pinned jars" % path)
            os.makedirs(JAR_DIR, exist_ok=True)
            with urllib.request.urlopen(url) as response, open(path + ".part", "wb") as fh:
                shutil.copyfileobj(response, fh)
            os.replace(path + ".part", path)
        if sha256(path) != digest:
            raise SystemExit("%s does not match its pinned SHA-256; delete it and run --fetch" % path)
        paths.append(path)
    return paths


def render(jars, mode="aggregated"):
    """{folder relative to OUT_DIR: {file name: SQL}} from one run of the Java launcher in `mode`."""
    spec_mode = MODES[mode]
    with tempfile.TemporaryDirectory() as tmp:
        settings_path = os.path.join(tmp, "settings.json")
        with open(settings_path, "w") as fh:
            json.dump(settings(), fh)
        cmd = ["java", "-cp", os.pathsep.join(jars), LAUNCHER, settings_path,
               "true" if spec_mode["aggregated"] else "false", spec_mode["row_id_field"],
               ",".join(spec_mode["files"]), spec_mode["cohort_table"], CDM_SCHEMA, SESSION_ID] + list(DIALECTS.values())
        done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit("rendering failed:\n" + done.stderr)
    out = json.loads(done.stdout)
    files = {}
    for folder, spec in DIALECTS.items():
        dialect = spec.split("=")[0]
        target = os.path.join(folder, spec_mode["subfolder"]) if spec_mode["subfolder"] else folder
        files[target] = {spec_mode["files"][part]: HEADER % (FEATURE_EXTRACTION, SQL_RENDER, "../" * (target.count(os.sep) + 1), target)
                         + sql.replace("\r\n", "\n").strip() + "\n" for part, sql in out[dialect].items()}
    return files


_COVARIATE_ID = re.compile(r"([^\n]*\b1000\s*\+\s*\d+[^\n]*?)\s+AS\s+covariate_id\b", re.I)
_ANALYSIS_ID = re.compile(r"INSERT\s+INTO\s+\S*analysis_ref\s*\(.*?SELECT\s+(\d+)\s+AS\s+analysis_id", re.I | re.S)


def id_signature(construction):
    """(covariate id expressions, analysis ids), in order, of a construction script. Two renders
    with the same signature write the same analysis and covariate ids."""
    expressions = [" ".join(e.split()) for e in _COVARIATE_ID.findall(construction)]
    return expressions, [int(a) for a in _ANALYSIS_ID.findall(construction)]


def person_tables(construction):
    """{scratch table: analysis id} of a person-mode construction script: each `cov_N` table is
    created, then its analysis registered, before the next one."""
    found = {}
    pattern = re.compile(r"CREATE\s+(?:TEMP\s+)?TABLE\s+(?:#|@temp_database_schema\.)?(?:%s)?(cov_\d+)\b" % SESSION_ID, re.I)
    starts = [(m.start(), m.group(1).lower()) for m in pattern.finditer(construction)]
    for (start, table), (end, _) in zip(starts, starts[1:] + [(len(construction), None)]):
        ids = _ANALYSIS_ID.findall(construction[start:end])
        if len(ids) != 1:
            raise SystemExit("person mode: %s registers %d analyses, not one" % (table, len(ids)))
        found[table] = int(ids[0])
    return found


def check_modes(files):
    """Fail unless each dialect's person render writes the aggregated render's ids, with one
    analysis per scratch table as PERSON_TABLES says (R9)."""
    for folder in DIALECTS:
        aggregated = files[os.path.join(folder, PARTS["sqlConstruction"])]
        person = files[os.path.join(folder, "person", PERSON_PARTS["sqlConstruction"])]
        if id_signature(person) != id_signature(aggregated):
            raise SystemExit("%s: the person render's analysis or covariate ids differ from the aggregated render's" % folder)
        if person_tables(person) != PERSON_TABLES:
            raise SystemExit("%s: person-mode scratch tables %s, expected %s" % (folder, person_tables(person), PERSON_TABLES))


def manifest():
    return {
        "feature_extraction": FEATURE_EXTRACTION, "sql_render": SQL_RENDER,
        "jars": {name: digest for name, _, digest in JARS},
        "presets": PRESETS, "settings": settings(),
        "min_characterization_mean": 0, "min_characterization_count": 0,
        "placeholders": {"cdm_database_schema": CDM_SCHEMA + " (every OMOP table; fixed, not the user's naming)",
                         "temp_database_schema": "@temp_database_schema (databricks only)",
                         "session_id": SESSION_ID},
        "dialects": DIALECTS,
        "modes": {
            "aggregated": dict(MODES["aggregated"], folder="<connection>/",
                               rows="one per cohort and covariate (characterization)"),
            "person": dict(MODES["person"], folder="<connection>/person/",
                           rows="one per cohort entry (row_id) and covariate (patient-level extract, R9)",
                           scratch_tables=PERSON_TABLES),
        },
    }


def expected_files(jars):
    """{path relative to OUT_DIR: text} for everything the tool writes."""
    out = {"NOTICE": NOTICE, "MANIFEST.json": json.dumps(manifest(), indent=1) + "\n"}
    for mode in MODES:
        for folder, parts in render(jars, mode).items():
            for name, text in parts.items():
                out[os.path.join(folder, name)] = text
    check_modes(out)
    return out


def read_raw(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--fetch", action="store_true", help="download missing pinned jars, then render")
    mode.add_argument("--check", action="store_true", help="exit 1 unless the checked-in files match a rerun")
    args = ap.parse_args(argv)
    files = expected_files(jar_paths(fetch=args.fetch))
    if args.check:
        differ = []
        for rel, text in sorted(files.items()):
            path = os.path.join(OUT_DIR, rel)
            if not os.path.exists(path) or read_raw(path) != text:
                differ.append(rel)
        print("\n".join("differs: " + d for d in differ) or "the rendered SQL matches a rerun (%d files)" % len(files))
        return 1 if differ else 0
    for rel, text in sorted(files.items()):
        path = os.path.join(OUT_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    print("wrote %d files to %s" % (len(files), os.path.relpath(OUT_DIR, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
