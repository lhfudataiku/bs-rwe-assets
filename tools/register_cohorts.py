#!/usr/bin/env python3
"""Turn a cohort metadata CSV into a `cohort_submission` (solution-revision-plan.md, R2).

The metadata CSV upload left Project Setup in 1.2.0. This helper registers a library of cohorts in
one go (the 45-cohort demo library, `cohort_scripts/snowflake/cohort_metadata_sf.csv`), with the
same checks as the "Register cohorts" tile. The CSV keeps its columns: `cohort_definition_id`,
`cohort_definition_name`, `cohort_definition_description`, `cohort_sql_script_filename`.

    python3 tools/register_cohorts.py cohort_scripts/snowflake/cohort_metadata_e4.csv        # print it
    python3 tools/register_cohorts.py <csv> --project KEY --apply [--replace]               # store it

`--apply` writes the project's `local` variable `cohort_submission` (needs `dku` auth). It does not
upload scripts or run anything: upload the scripts to "Original Scripts" and run "Ingest registered
cohorts" as in Setup. `--replace` marks every row Replace, for ids already registered. Writing to a
DSS project is a change to that project: get the owner's approval first.
"""
import argparse
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from solution.setup.registration import submission, validate_batch  # noqa: E402
from solution.utils.variables import set_local  # noqa: E402

COLUMNS = ("cohort_definition_id", "cohort_definition_name", "cohort_definition_description",
           "cohort_sql_script_filename")


def rows_from_csv(path, replace=False):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit("%s lacks column(s) %s" % (path, ", ".join(missing)))
        return [{"id": r["cohort_definition_id"], "name": r["cohort_definition_name"],
                 "description": r["cohort_definition_description"], "file": r["cohort_sql_script_filename"],
                 "submit": True, "replace": replace} for r in reader]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("csv")
    ap.add_argument("--project", help="DSS project key to write cohort_submission to (with --apply)")
    ap.add_argument("--apply", action="store_true", help="write the submission to the project")
    ap.add_argument("--replace", action="store_true", help="tick Replace on every row")
    args = ap.parse_args(argv)
    rows = rows_from_csv(args.csv, args.replace)
    # Offline the registered ids are unknown: the ingestion checks them against cohort_definition.
    errors = validate_batch(rows, [])
    if errors:
        raise SystemExit("not a valid submission:\n- " + "\n- ".join(errors))
    value = submission(rows)
    if not args.apply:
        print(json.dumps(value, indent=1))
        return 0
    if not args.project:
        raise SystemExit("--apply needs --project")
    from dku_cli.client import get_client  # the dku CLI's Python environment
    set_local(get_client().get_project(args.project), "cohort_submission", value)
    print("%s: cohort_submission holds %d cohorts (%s)" % (args.project, len(value),
                                                         ", ".join(str(r["id"]) for r in value)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
