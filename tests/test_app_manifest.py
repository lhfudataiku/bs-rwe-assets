"""tools/app_manifest.py: the repo's Project Setup layout (R1, R2), applied by identity, inline."""
import copy
import importlib.util
import io
import os
import sys
import unittest
from unittest import mock

import stubs

stubs.install()


def load_tool():
    path = os.path.join(stubs.ROOT, "tools", "app_manifest.py")
    spec = importlib.util.spec_from_file_location("app_manifest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scenario(sid):
    return {"type": "SCENARIO_RUN", "scenarioId": sid, "prompt": sid}


# The live layout before step 3, reduced to what the tool looks at.
MANIFEST = {"homepageSections": [
    {"sectionTitle": "**Pipeline Configuration** (One-time)"},
    {"sectionTitle": "Connections", "tiles": [{"type": "PROJECT_VARIABLES_EDIT", "params": [{"name": "main_connection"}]}]},
    {"sectionTitle": "Connect OMOP", "tiles": [
        {"type": "PROJECT_VARIABLES_EDIT", "module": "input_data_source_project_selectbox", "python": "old"},
        {"type": "PROJECT_VARIABLES_EDIT", "params": [{"name": "person"}], "python": "old"},
        {"type": "PROJECT_VARIABLES_EDIT", "params": [{"name": "concept"}], "python": "old"},
        scenario("IMPORTDATASETSFROMDATAPREPPROJECT")]},
    {"sectionTitle": "Custom mapping", "tiles": [
        {"type": "MANAGED_FOLDER_ADD_FILE"}, {"type": "PROJECT_VARIABLES_EDIT", "params": [{"name": "cdm_standard_tables_map"}]},
        scenario("CHECKOMOPTABLEVARIABLESMAPPING")]},
    {"sectionTitle": "**Cohort Ingestion**"},
    {"sectionTitle": "Upload scripts and metadata", "tiles": [
        {"type": "MANAGED_FOLDER_ADD_FILE"}, {"type": "UPLOAD_DATASET_SET_FILE"}, scenario("CREATECOHORTSCRIPTS"),
        {"type": "MANAGED_FOLDER_LINK", "folderId": "lMM00YKr", "prompt": "View Mapped Scripts"}]},
    {"sectionTitle": "Write", "tiles": [scenario("WRITECOHORTTODATASETS"),
        {"type": "PROJECT_VARIABLES_EDIT", "prompt": "Review Cohort", "html": "<button>"},
        {"type": "PROJECT_VARIABLES_EDIT", "prompt": "Review Cohort Definition", "html": "<button>"},
        {"type": "PROJECT_VARIABLES_EDIT", "prompt": "Review Cohort Log", "html": "<button>"}]},
    {"sectionTitle": "**Dashboard Creation**"},
    {"sectionTitle": "Create Cohort Dashboard", "tiles": [
        {"type": "PROJECT_VARIABLES_EDIT", "params": [{"name": "cohort_definition_id"}], "python": "old"},
        scenario("BUILDCOHORTDASHBOARD"), {"type": "DASHBOARD_LINK"}]},
]}


def by_title(manifest, title):
    return next(s for s in manifest["homepageSections"] if s.get("sectionTitle") == title)


class Apply(unittest.TestCase):
    def setUp(self):
        self.tool, self.m = load_tool(), copy.deepcopy(MANIFEST)
        self.changes = self.tool.apply(self.m)

    def test_step3_layout(self):
        titles = [s.get("sectionTitle") for s in self.m["homepageSections"]]
        self.assertNotIn("Custom mapping", titles)  # R1: S3 is gone
        # The naming tile has its own section, right after the Cohort Ingestion heading.
        self.assertEqual(titles[titles.index("**Cohort Ingestion**") + 1], "Cohort Script Table Naming")
        self.assertEqual([t["module"] for t in by_title(self.m, "Cohort Script Table Naming")["tiles"]], ["table_naming"])
        upload = by_title(self.m, "Upload and Register Cohort SQL Scripts")
        self.assertEqual([t.get("type") if not t.get("module") else t["module"] for t in upload["tiles"]],
                         ["MANAGED_FOLDER_ADD_FILE", "register_cohorts", "SCENARIO_RUN", "PROJECT_VARIABLES_EDIT"])
        self.assertEqual(upload["tiles"][2]["prompt"], "Write batch to cohort definition")
        folder = upload["tiles"][3]
        self.assertEqual(folder["prompt"], "View written scripts")
        self.assertIn("/managedfolder/lMM00YKr/view/", folder["html"])
        build = by_title(self.m, "Build Cohorts")
        self.assertEqual([t.get("prompt") for t in build["tiles"]],
                         ["Build cohorts", "Review Cohort", "Review Cohort Definition", "Review Cohort Log",
                          "Built cohorts"])
        for tile, name in zip(build["tiles"][1:4], ("cohort", "cohort_definition", "cohort_building_log")):
            self.assertIn("/datasets/%s/explore/" % name, tile["html"])
            self.assertIn('target="_blank"', tile["html"])
            self.assertNotIn("SOL_", tile["html"])  # the key comes from the page URL
        # R3, decision 14: characterization has its own section after Build Cohorts, with its button.
        titles = [s.get("sectionTitle") for s in self.m["homepageSections"]]
        # A part heading of its own, like **Cohort Ingestion**: a stand-alone operation.
        self.assertEqual(titles[titles.index("Build Cohorts") + 1:titles.index("Build Cohorts") + 3],
                         ["**Cohort Characterization**", "Characterize Cohorts"])
        self.assertEqual(by_title(self.m, "**Cohort Characterization**")["tiles"], [])
        self.assertIn("**Cohort Characterization**", by_title(self.m, "**Cohort Ingestion**")["sectionText"])
        char = by_title(self.m, "Characterize Cohorts")["tiles"]
        self.assertEqual([t.get("module") or t.get("scenarioId") or t.get("prompt") for t in char],
                         ["characterization_batch", "Characterize_Cohorts", "Review Characterization Log"])
        self.assertIn("/datasets/characterization_log/explore/", char[2]["html"])
        omop = by_title(self.m, "Connect OMOP")["tiles"]
        self.assertEqual(omop[3]["scenarioId"], "IMPORTDATASETSFROMDATAPREPPROJECT")
        self.assertNotIn("mapping file", by_title(self.m, "**Pipeline Configuration** (One-time)")["sectionText"])
        self.assertEqual(self.tool.unknown_variables(self.m), [])

    def test_first_step3_layout_moves_the_naming_tile(self):
        m = copy.deepcopy(self.m)
        naming = m["homepageSections"].pop(m["homepageSections"].index(by_title(m, "Cohort Script Table Naming")))
        by_title(m, "Connect OMOP")["tiles"].insert(3, {"type": "PROJECT_VARIABLES_EDIT", "params": [
            {"name": "cohort_script_table_naming"}, {"name": "cohort_script_table_prefix"}]})
        self.assertIn("removed the tile with parameter cohort_script_table_naming", self.tool.apply(m))
        self.assertEqual(m, self.m)
        self.assertTrue(naming)

    def test_idempotent(self):
        self.assertTrue(self.changes)
        self.assertEqual(self.tool.apply(self.m), [])

    def test_python_tiles_are_found_after_sections_move(self):
        self.assertIn("omop_table_choices()", by_title(self.m, "Connect OMOP")["tiles"][1]["python"])

    def test_old_dashboard_section_goes(self):
        # R3, part 7: its heading, its section, and with it the cohort_definition_id tile.
        titles = [s.get("sectionTitle") for s in self.m["homepageSections"]]
        self.assertFalse({"**Dashboard Creation**", "Create Cohort Dashboard"} & set(titles))
        self.assertEqual(titles[-1], "Characterize Cohorts")
        self.assertNotIn("cohort_definition_id", str(self.m))

    def test_ambiguous_tile_is_refused(self):
        m = copy.deepcopy(MANIFEST)
        m["homepageSections"][2]["tiles"][2]["params"][0]["name"] = "person"
        with self.assertRaises(SystemExit):
            self.tool.apply(m)

    def test_check_names_setup_keys_outside_the_contract(self):
        m = {"homepageSections": [{"tiles": [
            {"type": "PROJECT_VARIABLES_EDIT", "params": [{"name": "main_connection"}, {"name": "connection_type"}]},
            {"type": "SCENARIO_RUN", "params": [{"name": "anything"}]}]}]}
        self.assertEqual(self.tool.unknown_variables(m), ["section 0 tile 0: connection_type"])


class InlineTiles(unittest.TestCase):
    """Inlined tile code runs with only `dataiku` available, as in a DSS tile process."""

    def setUp(self):
        self.tool = load_tool()
        self.m = copy.deepcopy(MANIFEST)
        self.tool.apply(self.m)

    def tile(self, module):
        code = next(t for _, _, t in self.tool.all_tiles(self.m) if t.get("module") == module)["python"]
        self.assertNotIn("from solution.", code)
        ns = {}
        exec(compile(code, module, "exec"), ns)
        return ns["do"]

    def fake_dataiku(self, registered_rows=(), variables=None):
        dk = mock.MagicMock()
        folder = dk.Folder.return_value
        folder.list_paths_in_partition.return_value = ["/a.sql"]
        folder.get_download_stream.side_effect = lambda p: mock.MagicMock(
            __enter__=lambda s: io.BytesIO(b"-- name: Crohn's\nSELECT 1;"), __exit__=lambda *a: None)
        ds = dk.Dataset.return_value
        ds.read_schema.return_value = [{"name": "COHORT_DEFINITION_ID"}, {"name": "COHORT_DEFINITION_NAME"}]
        ds.iter_tuples.side_effect = lambda: iter(registered_rows)
        project = dk.api_client.return_value.get_default_project.return_value
        project.get_variables.return_value = variables or {"standard": {}, "local": {}}
        return dk, project

    def test_register_tile_loads_and_saves(self):
        do = self.tile("register_cohorts")
        dk, project = self.fake_dataiku(registered_rows=[(1, "Old")])
        with mock.patch.dict(sys.modules, {"dataiku": dk}):
            loaded = do({"action": "load"}, {}, {}, [])
            self.assertEqual(loaded["registered_ids"], [1])
            self.assertEqual([(r["file"], r["id"], r["name"]) for r in loaded["rows"]], [("a.sql", 2, "Crohn's")])
            refused = do({"action": "save", "rows": [dict(loaded["rows"][0], id=1)]}, {}, {}, [])
            self.assertFalse(refused["ok"])
            self.assertIn("already exists", refused["errors"][0])
            project.set_variables.assert_not_called()
            self.assertEqual(do({"action": "save", "rows": loaded["rows"]}, {}, {}, []), {"ok": True, "saved": 1})
        saved = project.set_variables.call_args.args[0]["local"]["cohort_submission"]
        self.assertEqual(saved, [{"id": 2, "name": "Crohn's", "description": "", "file": "a.sql", "replace": False}])

    def test_register_tile_returns_sentences_not_tracebacks(self):
        do = self.tile("register_cohorts")
        dk, _ = self.fake_dataiku()
        dk.Folder.side_effect = Exception("folder missing")
        with mock.patch.dict(sys.modules, {"dataiku": dk}):
            self.assertEqual(do({"action": "load"}, {}, {}, []),
                             {"ok": False, "errors": ["Could not read the scripts or registered cohorts: folder missing"]})

    def test_naming_tile_loads_and_saves(self):
        do = self.tile("table_naming")
        dk, project = self.fake_dataiku()
        with mock.patch.dict(sys.modules, {"dataiku": dk}):
            loaded = do({"action": "load"}, {}, {}, [])
            self.assertEqual((loaded["naming"], loaded["atlas"]["person"]), ("atlas", "@cdm_database_schema.person"))
            self.assertEqual([c["value"] for c in loaded["choices"]], ["atlas", "plain", "prefix", "mapping"])
            refused = do({"action": "save", "naming": "prefix", "prefix": " "}, {}, {}, [])
            self.assertFalse(refused["ok"])
            project.set_variables.assert_not_called()
            mapping = {"person": "cdm.person", "concept": " vocab.concept ", "death": ""}
            self.assertEqual(do({"action": "save", "naming": "mapping", "mapping": mapping}, {}, {}, []), {"ok": True})
        local = project.set_variables.call_args.args[0]["local"]
        self.assertEqual(local["cohort_script_table_map"], {"person": "cdm.person", "concept": "vocab.concept"})

    def test_built_tile_lists_cohorts(self):
        do = self.tile("built_cohorts")
        dk, _ = self.fake_dataiku(registered_rows=[(1, "A")])
        with mock.patch.dict(sys.modules, {"dataiku": dk}):
            result = do({}, {}, {}, [])
        self.assertTrue(result["ok"])
        self.assertEqual([(r["id"], r["name"]) for r in result["rows"]], [(1, "A")])

    def test_characterization_tile_loads_and_saves(self):
        do = self.tile("characterization_batch")
        tables = {
            "cohort_definition": (["COHORT_DEFINITION_ID", "COHORT_DEFINITION_NAME"], [(1, "Anemia"), (2, "Crohn's")]),
            "cohort_building_log": (["RUN_TIMESTAMP", "COHORT_DEFINITION_ID", "COHORT_COUNT", "STATUS"],
                                    [("2026-11-20T10:00:00Z", 1, 611, "SUCCESS"), ("2026-11-20T10:00:00Z", 2, 593, "SUCCESS")]),
            "characterization_log": (["RUN_TIMESTAMP", "COHORT_DEFINITION_ID", "BUILD_TIMESTAMP", "COHORT_COUNT", "STATUS"],
                                     [("2026-11-21T10:00:00Z", 1, "2026-11-20T10:00:00Z", 611, "SUCCESS"),
                                      ("2026-11-21T10:00:00Z", -1, "", 900, "SUCCESS")]),
        }
        dk, project = self.fake_dataiku()

        def dataset(name, **kwargs):
            ds = mock.MagicMock()
            columns, rows = tables[name]
            ds.read_schema.return_value = [{"name": c} for c in columns]
            ds.iter_tuples.side_effect = lambda: iter(rows)
            return ds
        dk.Dataset.side_effect = dataset
        project.get_scenario.return_value.get_last_successful_run.return_value = None
        with mock.patch.dict(sys.modules, {"dataiku": dk}):
            loaded = do({"action": "load"}, {}, {}, [])
            self.assertTrue(loaded["ok"], loaded)
            self.assertEqual(loaded["characterized_ids"], [-1, 1])
            self.assertEqual([(r["id"], r["status"], r["submit"]) for r in loaded["rows"]],
                             [(-1, "characterized", False), (1, "characterized", False), (2, "not characterized", True)])
            rows = loaded["rows"]
            rows[1]["submit"] = True  # characterized, without Replace
            refused = do({"action": "save", "rows": rows}, {}, {}, [])
            self.assertEqual(refused["errors"],
                             ["Anemia: cohort 1 is already characterized. Tick Replace to characterize it again."])
            project.set_variables.assert_not_called()
            rows[1]["replace"] = True
            self.assertEqual(do({"action": "save", "rows": rows}, {}, {}, []), {"ok": True, "saved": 2})
        saved = project.set_variables.call_args.args[0]["local"]["characterization_submission"]
        self.assertEqual([{k: r[k] for k in ("id", "replace")} for r in saved],
                         [{"id": 1, "replace": True}, {"id": 2, "replace": False}])
        self.assertEqual(saved[0]["saved"], saved[1]["saved"])  # stamped, so a written-back batch expires

    def test_inlined_modules_never_share_a_top_level_name(self):
        # One namespace: a second `submission` would silently replace the first (found in part 5).
        self.assertEqual(self.tool.name_clashes(["solution.setup.characterization", "solution.setup.registration",
                                                 "solution.setup.batch", "solution.utils.variables",
                                                 "solution.setup.sql_dialect"]), [])
        with mock.patch.object(self.tool, "top_level_names", return_value={"submission"}):
            self.assertEqual(self.tool.name_clashes(["solution.setup.batch", "solution.setup.registration"]),
                             ["submission (solution.setup.batch, solution.setup.registration)"])

    def test_wrappers_compile_and_define_do(self):
        tiles = os.path.join(stubs.ROOT, "app_manifest", "tiles")
        for fname in sorted(os.listdir(tiles)):
            if fname.endswith(".py"):
                ns = {}
                with open(os.path.join(tiles, fname)) as fh:
                    exec(compile(fh.read(), fname, "exec"), ns)
                self.assertTrue(callable(ns["do"]), fname)


if __name__ == "__main__":
    unittest.main()
