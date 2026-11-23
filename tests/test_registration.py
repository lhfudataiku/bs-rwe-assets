"""R2: the "Register cohorts" rows, the batch checks, and the "Built cohorts" listing."""
import io
import unittest
from unittest import mock

import stubs

stubs.install()
from solution.setup import registration as r  # noqa: E402

SCRIPT_A = "-- name: Crohn's disease\n-- description: first diagnosis\nSELECT 1;"
SCRIPT_B = "SELECT 2;"


def registered(cohort_id, name, filename, text):
    return {"id": cohort_id, "name": name, "description": "d",
            "syntax": r.provenance(filename, r.script_digest(text))}


class Header(unittest.TestCase):
    def test_reads_leading_comments_only(self):
        self.assertEqual(r.script_header(SCRIPT_A), {"name": "Crohn's disease", "description": "first diagnosis"})
        self.assertEqual(r.script_header("SELECT 1;\n-- name: late"), {})

    def test_default_name_from_filename(self):
        self.assertEqual(r.default_name("feature_condition_anemia.sql"), "Feature condition anemia")


class Rows(unittest.TestCase):
    def test_new_registered_changed_and_pending(self):
        files = {"a.sql": SCRIPT_A, "b.sql": SCRIPT_B, "c.sql": "SELECT 3;", "d.sql": "SELECT 4;"}
        reg = [registered(5, "B", "b.sql", SCRIPT_B), registered(7, "C", "c.sql", "SELECT old;")]
        last = [{"id": 9, "name": "Typed", "description": "", "file": "d.sql", "replace": False}]
        rows = {row["file"]: row for row in r.registration_rows(files, reg, last)}
        self.assertEqual(rows["a.sql"], {"file": "a.sql", "status": "new", "id": 10, "name": "Crohn's disease",
                                         "description": "first diagnosis", "submit": True, "replace": False})
        self.assertEqual((rows["b.sql"]["status"], rows["b.sql"]["id"], rows["b.sql"]["submit"]), ("registered", 5, False))
        self.assertEqual(rows["c.sql"]["status"], "changed")
        self.assertEqual((rows["d.sql"]["status"], rows["d.sql"]["name"]), ("pending", "Typed"))

    def test_first_registration_starts_at_one(self):
        self.assertEqual([x["id"] for x in r.registration_rows({"a.sql": "", "b.sql": ""}, [])], [1, 2])


class Validate(unittest.TestCase):
    def row(self, **kw):
        base = {"file": "a.sql", "id": 1, "name": "A", "submit": True, "replace": False}
        base.update(kw)
        return base

    def test_valid_batch(self):
        self.assertEqual(r.validate_batch([self.row(), self.row(file="b.sql", id=0)], [], {"a.sql", "b.sql"}), [])

    def test_existing_id_needs_replace(self):
        errors = r.validate_batch([self.row(id=3)], [3])
        self.assertEqual(len(errors), 1)
        self.assertIn("cohort 3 already exists", errors[0])
        self.assertEqual(r.validate_batch([self.row(id=3, replace=True)], [3]), [])

    def test_every_problem_is_reported(self):
        rows = [self.row(id="x"), self.row(file="b.sql", id=2, name=" "), self.row(file="c.sql", id=2),
                self.row(file="gone.sql", id=4), self.row(file="e.sql", id=5, name="n" * 256)]
        errors = r.validate_batch(rows, [], {"a.sql", "b.sql", "c.sql", "e.sql"})
        self.assertEqual(len(errors), 5, errors)

    def test_nothing_ticked(self):
        self.assertEqual(len(r.validate_batch([self.row(submit=False)], [])), 1)

    def test_submission_keeps_ticked_rows_only(self):
        rows = [self.row(name=" A "), self.row(file="b.sql", id="2", submit=False)]
        self.assertEqual(r.submission(rows), [{"id": 1, "name": "A", "description": "", "file": "a.sql", "replace": False}])


class Built(unittest.TestCase):
    def test_latest_log_per_cohort(self):
        defs = [registered(2, "B", "b.sql", SCRIPT_B), {"id": 1, "name": "A", "description": None, "syntax": ""}]
        logs = [{"run_timestamp": "2026-11-23T10:00:00Z", "id": "2", "count": 5, "status": "SUCCESS"},
                {"run_timestamp": "2026-11-23T11:00:00Z", "id": 2, "count": 0, "status": "FAILED"}]
        rows = r.built_cohort_rows(defs, logs)
        self.assertEqual([x["id"] for x in rows], [1, 2])
        self.assertEqual(rows[0]["status"], "not built")
        self.assertEqual((rows[1]["status"], rows[1]["subjects"], rows[1]["script"]), ("FAILED", 0, "b.sql"))


class Readers(unittest.TestCase):
    def test_read_rows_any_case_and_unbuilt(self):
        ds = mock.MagicMock()
        ds.read_schema.return_value = [{"name": "cohort_definition_id"}, {"name": "cohort_definition_name"}]
        ds.iter_tuples.return_value = iter([(1, "A")])
        self.assertEqual(r.read_rows(ds, r.DEFINITION_COLUMNS),
                         [{"id": 1, "name": "A", "description": None, "syntax": None}])
        ds.read_schema.side_effect = Exception("not built")
        self.assertEqual(r.read_rows(ds, r.DEFINITION_COLUMNS), [])

    def test_folder_texts(self):
        folder = mock.MagicMock()
        folder.list_paths_in_partition.return_value = ["/a.sql"]
        folder.get_download_stream.return_value.__enter__.return_value = io.BytesIO(b"SELECT 1;")
        self.assertEqual(r.folder_texts(folder), {"a.sql": "SELECT 1;"})


if __name__ == "__main__":
    unittest.main()
