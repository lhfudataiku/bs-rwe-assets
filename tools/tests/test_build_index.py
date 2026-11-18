"""Offline tests for tools/build_index.py: the schema rules, the issue detection, and partial refresh."""

import copy
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

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


class DependencyClosure(unittest.TestCase):
    """--project KEY refreshes KEY and what it reads from, never what reads from it."""

    def setUp(self):
        self.reg = {"projects": [entry("S3"), entry("DB", upstream=["S3"]), entry("SOL"), entry("DEMO"),
                                 entry("OTHER")],
                    "out_of_scope": {}, "owners": {}}
        self.projects = {
            "S3": project(),
            "DB": project(),
            "SOL": project(local={"data_preparation_project_key": "DB"}),
            "DEMO": project(flow_sources=["SOL.cohort", "local_input"]),
            "OTHER": project(),
        }

    def test_registry_upstream(self):
        self.assertEqual(b.closure(self.reg, self.projects, ["DB"]), {"DB", "S3"})

    def test_prep_key_and_shares_are_followed_transitively(self):
        self.assertEqual(b.closure(self.reg, self.projects, ["DEMO"]), {"DEMO", "SOL", "DB", "S3"})

    def test_prep_key_in_standard_scope_counts_too(self):
        self.projects["OTHER"] = project(standard={"data_preparation_project_key": "S3"})
        self.assertEqual(b.closure(self.reg, self.projects, ["OTHER"]), {"OTHER", "S3"})

    def test_consumers_are_not_pulled_in(self):
        self.assertEqual(b.closure(self.reg, self.projects, ["S3"]), {"S3"})

    def test_missing_project_still_follows_registry_upstream(self):
        self.projects["DB"] = {"exists": False, "error": "not on DSS"}
        self.assertEqual(b.closure(self.reg, self.projects, ["DB"]), {"DB", "S3"})

    def test_several_keys_and_cycles(self):
        self.projects["S3"] = project(flow_sources=["DEMO.x"])
        self.assertEqual(b.closure(self.reg, self.projects, ["OTHER", "S3"]), {"OTHER", "S3", "DEMO", "SOL", "DB"})


class PartialRefresh(unittest.TestCase):
    """A partial refresh replaces the fetched entries and keeps every other one byte for byte."""

    def setUp(self):
        self.reg = {"projects": [entry("S3"), entry("DB", upstream=["S3"]), entry("SOL"),
                                 entry("PLANNED", lifecycle="planned")],
                    "out_of_scope": {}, "owners": {}, "discovery_pattern": "."}
        sol = project(local={"data_preparation_project_key": "DB", "person": "person_db"})
        db = project({"person_db": ds(built="yes")})
        s3 = project({"person_s3": ds(built="yes")})
        for key, proj in (("S3", s3), ("DB", db), ("SOL", sol)):
            proj["fetched_at"] = proj["probed_at"] = "2026-11-01T00:00Z"
            proj["name"] = key
        self.old = {"dss_project_count": 3, "discovered": ["DB", "S3", "SOL"], "external_projects": {},
                    "projects": {"S3": s3, "DB": db, "SOL": sol,
                                 "PLANNED": {"exists": False, "error": "not on DSS", "fetched_at": "2026-11-01T00:00Z"}}}

    def test_merge_keeps_untouched_entries(self):
        fresh = project({"person_db": ds()})
        merged = b.merge_projects(self.reg, self.old["projects"], {"DB": fresh}, {"S3", "DB", "SOL"}, "NOW")
        self.assertIs(merged["DB"], fresh)
        self.assertEqual(merged["S3"], self.old["projects"]["S3"])
        self.assertEqual(merged["SOL"], self.old["projects"]["SOL"])
        self.assertEqual(merged["PLANNED"], {"exists": False, "error": "not on DSS", "fetched_at": "NOW"})

    def test_merge_marks_a_vanished_project_and_drops_unregistered_keys(self):
        old = dict(self.old["projects"], RETIRED=project())
        merged = b.merge_projects(self.reg, old, {}, {"DB", "SOL"}, "NOW")
        self.assertFalse(merged["S3"]["exists"])
        self.assertNotIn("RETIRED", merged)

    def test_project_new_on_dss_must_be_fetched(self):
        self.assertEqual(b.must_fetch(self.reg, self.old["projects"], {"S3", "DB", "SOL", "PLANNED"}), {"PLANNED"})

    def run_refresh(self, only, dss_keys, fetched_defs):
        """refresh(only) against a fake DSS; returns (snapshot written, keys fetched, datasets probed)."""
        tmp = tempfile.mkdtemp()
        snap_path = os.path.join(tmp, "dss_snapshot.json")
        with open(snap_path, "w") as fh:
            json.dump(self.old, fh)
        fetched, probed, written = [], [], {}

        def fake_fetch(key):
            fetched.append(key)
            proj = copy.deepcopy(fetched_defs[key])
            proj["fetched_at"] = "NEW"
            return proj

        def fake_probe(project_key, name, dtype):
            probed.append((project_key, name))
            return {"built": "empty", "rows": 0, "source": "sql", "error": ""}

        listing = [{"projectKey": k, "name": k} for k in dss_keys]
        with mock.patch.object(b, "SNAP", snap_path), \
                mock.patch.object(b, "dku", return_value=(True, listing)), \
                mock.patch.object(b, "fetch_project", side_effect=fake_fetch), \
                mock.patch.object(b, "probe", side_effect=fake_probe), \
                mock.patch.object(b, "write_snapshot", side_effect=written.update), \
                mock.patch("sys.stderr", new_callable=io.StringIO), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            b.refresh(self.reg, only)
        return written, sorted(fetched), sorted(probed)

    def test_refresh_one_project_fetches_its_closure_only(self):
        defs = {"DB": project({"person_db": ds()}), "S3": project({"person_s3": ds()})}
        snap, fetched, probed = self.run_refresh(["DB"], ["S3", "DB", "SOL"], defs)
        self.assertEqual(fetched, ["DB", "S3"])
        # SOL was not fetched, but it reads DB.person_db, so that dataset is probed again.
        self.assertEqual(probed, [("DB", "person_db")])
        self.assertEqual(snap["projects"]["SOL"], self.old["projects"]["SOL"])
        self.assertEqual(snap["projects"]["DB"]["datasets"]["person_db"]["probe"]["built"], "empty")
        self.assertNotEqual(snap["projects"]["DB"]["probed_at"], "2026-11-01T00:00Z")
        self.assertEqual(snap["projects"]["SOL"]["probed_at"], "2026-11-01T00:00Z")
        self.assertIn("mixed snapshot", b.snapshot_age(snap))

    def test_refresh_follows_a_dependency_only_the_fresh_fetch_knows(self):
        # The snapshot has SOL unwired; it was pointed at DB since. DB, and DB's upstream S3, are
        # fetched in a second round.
        self.old["projects"]["SOL"]["variables"]["local"] = {}
        defs = {"SOL": project(local={"data_preparation_project_key": "DB", "person": "person_db"}),
                "DB": project({"person_db": ds()}), "S3": project({"person_s3": ds()})}
        snap, fetched, probed = self.run_refresh(["SOL"], ["S3", "DB", "SOL"], defs)
        self.assertEqual(fetched, ["DB", "S3", "SOL"])
        self.assertEqual(probed, [("DB", "person_db")])

    def test_refresh_keeps_projects_outside_the_closure(self):
        defs = {"S3": project({"person_s3": ds()})}
        snap, fetched, _ = self.run_refresh(["S3"], ["S3", "DB", "SOL"], defs)
        self.assertEqual(fetched, ["S3"])
        self.assertEqual(snap["projects"]["DB"], self.old["projects"]["DB"])
        self.assertEqual(snap["projects"]["SOL"], self.old["projects"]["SOL"])

    def test_refresh_fetches_a_project_that_appeared_on_dss(self):
        defs = {"S3": project({"person_s3": ds()}), "PLANNED": project()}
        _, fetched, _ = self.run_refresh(["S3"], ["S3", "DB", "SOL", "PLANNED"], defs)
        self.assertEqual(fetched, ["PLANNED", "S3"])

    def test_unregistered_project_key_is_refused(self):
        with self.assertRaises(SystemExit):
            b.check_only(self.reg, ["NOPE"])


class SnapshotAge(unittest.TestCase):
    def test_legacy_refreshed_at_becomes_per_project(self):
        snap = b.normalize_snapshot({"refreshed_at": "T0", "projects": {"A": project(), "B": {"exists": False}}})
        self.assertNotIn("refreshed_at", snap)
        self.assertEqual(snap["projects"]["A"]["fetched_at"], "T0")
        self.assertEqual(snap["projects"]["A"]["probed_at"], "T0")
        self.assertEqual(snap["projects"]["B"], {"exists": False, "fetched_at": "T0"})
        self.assertEqual(b.snapshot_age(snap), "the snapshot fetched T0")

    def test_mixed_snapshot_names_the_oldest(self):
        snap = {"projects": {"A": {"fetched_at": "T2"}, "B": {"fetched_at": "T1"}, "C": {"fetched_at": "T3"}}}
        self.assertEqual(b.snapshot_age(snap), "a mixed snapshot: projects fetched between T1 (oldest: `B`) and T3")


if __name__ == "__main__":
    unittest.main()
