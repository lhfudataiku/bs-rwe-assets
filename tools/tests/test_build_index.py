"""Offline tests for tools/build_index.py: the schema rules and the issue detection."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import build_index as b  # noqa: E402

PERSON_OK = [["person_id", "int"], ["gender_concept_id", "int"], ["year_of_birth", "int"],
             ["birth_datetime", "datetimenotz"], ["race_concept_id", "int"], ["ethnicity_concept_id", "int"]]


class SchemaRules(unittest.TestCase):
    def test_compliant_table_passes(self):
        self.assertEqual(b.check_table("person", PERSON_OK), (True, ""))

    def test_uppercase_names_and_bigint_are_accepted_like_the_solution(self):
        cols = [[n.upper(), "bigint" if t == "int" else t] for n, t in PERSON_OK]
        self.assertTrue(b.check_table("person", cols)[0])

    def test_legacy_date_type_fails(self):
        cols = [c if c[0] != "birth_datetime" else ["birth_datetime", "date"] for c in PERSON_OK]
        ok, reason = b.check_table("person", cols)
        self.assertFalse(ok)
        self.assertIn("birth_datetime date≠datetimenotz", reason)

    def test_missing_required_column_fails(self):
        ok, reason = b.check_table("person", PERSON_OK[1:])
        self.assertFalse(ok)
        self.assertIn("person_id missing", reason)

    def test_wrong_optional_type_fails_but_absent_optional_passes(self):
        self.assertTrue(b.check_table("person", PERSON_OK)[0])
        ok, reason = b.check_table("person", PERSON_OK + [["location_id", "string"]])
        self.assertFalse(ok)
        self.assertIn("(optional)", reason)


def ds(columns=None, built=None):
    d = {"type": "Snowflake", "managed": True, "connection": "c", "columns": columns or []}
    if built:
        d["probe"] = {"built": built, "rows": 3 if built == "yes" else None, "source": "sql", "error": ""}
    return d


def entry(key, **kw):
    e = {"key": key, "part": 1, "role": "canonical", "sample_size": "1K", "connections": [], "upstream": [],
         "owner": "data-foundation", "personas": [], "library": None, "lifecycle": "active", "decision": "",
         "omop_sets": {}}
    e.update(kw)
    return e


def project(datasets=None, standard=None, local=None, flow_sources=()):
    return {"exists": True, "name": "", "variables": {"standard": standard or {}, "local": local or {}},
            "git_references": {}, "flow_sources": list(flow_sources), "wiki_articles": [], "wiki_version": "",
            "datasets": datasets or {}}


class Issues(unittest.TestCase):
    def setUp(self):
        self.reg = {"projects": [entry("PREP"), entry("CONSUMER", part=3, role="demo", owner="rwe-demo")],
                    "out_of_scope": {}, "owners": {}}
        self.snap = {"refreshed_at": "x", "discovered": ["PREP", "CONSUMER"], "external_projects": {},
                     "projects": {"PREP": project({"t": ds(built="yes")}),
                                  "CONSUMER": project(flow_sources=["PREP.t", "local_input"])}}

    def ids(self, reg=None, snap=None):
        return sorted(i["id"] for i in b.analyse(reg or self.reg, snap or self.snap)["issues"])

    def test_clean_suite_has_no_issues(self):
        self.assertEqual(self.ids(), [])

    def test_local_flow_sources_are_not_cross_project(self):
        rows = b.analyse(self.reg, self.snap)["lineage"]
        self.assertEqual([r["source_project"] for r in rows], ["PREP"])

    def test_unbuilt_shared_input_is_a_broken_share(self):
        snap = copy.deepcopy(self.snap)
        snap["projects"]["PREP"]["datasets"]["t"] = ds(built="no")
        self.assertEqual(self.ids(snap=snap), ["SHARE_BROKEN:CONSUMER:PREP"])

    def test_prep_key_is_checked_in_both_scopes(self):
        snap = copy.deepcopy(self.snap)
        snap["projects"]["CONSUMER"]["variables"] = {"standard": {"data_preparation_project_key": "PREP"},
                                                     "local": {"data_preparation_project_key": "GONE"}}
        snap["external_projects"] = {"GONE": False}
        self.assertEqual(self.ids(snap=snap), ["PREP_KEY_DANGLING:CONSUMER:local"])

    def test_registered_project_missing_from_dss(self):
        snap = copy.deepcopy(self.snap)
        snap["projects"]["PREP"] = {"exists": False}
        self.assertIn("PROJECT_MISSING:PREP", self.ids(snap=snap))

    def test_unregistered_discovered_project(self):
        snap = copy.deepcopy(self.snap)
        snap["discovered"].append("NEW_RWD_COPY")
        self.assertIn("UNREGISTERED:NEW_RWD_COPY", self.ids(snap=snap))

    def test_omop_set_with_null_dataset_is_incomplete(self):
        reg = copy.deepcopy(self.reg)
        tables = {t: "t" for t in b.OMOP_TABLES}
        tables["concept_ancestor"] = None
        reg["projects"][0]["omop_sets"] = {"s3": tables}
        found = self.ids(reg=reg)
        self.assertIn("SET_INCOMPLETE:PREP:s3", found)
        self.assertIn("SCHEMA_FAIL:PREP:s3", found)  # dataset "t" has no OMOP columns


class Baseline(unittest.TestCase):
    def test_probe_failures_are_informational(self):
        reg = {"projects": [entry("PREP")], "out_of_scope": {}, "owners": {}}
        tables = {t: "t" for t in b.OMOP_TABLES}
        reg["projects"][0]["omop_sets"] = {"s3": tables}
        cols = []
        snap = {"refreshed_at": "x", "discovered": [], "external_projects": {},
                "projects": {"PREP": project({"t": ds(cols, built="unknown")})}}
        _, data = b.render(reg, snap, {})
        status = {i["id"]: i["status"] for i in data["issues"]}
        self.assertEqual(status["UNREADABLE:PREP:s3"], "info")
        self.assertEqual(status["SCHEMA_FAIL:PREP:s3"], "NEW")


if __name__ == "__main__":
    unittest.main()
