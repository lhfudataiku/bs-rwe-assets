"""R1: the table naming choice replaces the uploaded JSON key map."""
import json
import os
import unittest

import stubs

stubs.install()
from solution.setup import table_naming as n  # noqa: E402
from solution.variables import OMOP_CDM_KEYS  # noqa: E402


def shipped(name):
    with open(os.path.join(stubs.ROOT, "cohort_scripts", name)) as fh:
        return json.load(fh)


class KeyMap(unittest.TestCase):
    def test_atlas_reproduces_the_shipped_map_exactly(self):
        self.assertEqual(n.key_map("atlas"), shipped("omop_cdm_atlas.json"))

    def test_plain_reproduces_the_shipped_standard_map(self):
        self.assertEqual(n.key_map("plain"), shipped("omop_cdm_standard.json"))

    def test_prefix_applies_to_every_table(self):
        mapping = n.key_map("prefix", " cdm. ")
        self.assertEqual(mapping["person"], "cdm.person")
        self.assertEqual(mapping["cohort"], "cdm.cohort")
        self.assertEqual(set(mapping), set(OMOP_CDM_KEYS) | {"cohort", "cohort_definition"})

    def test_mapping_keeps_the_named_tables_only(self):
        mapping = n.key_map("mapping", mapping={"person": " cdm.person ", "cohort": "res.cohort", "death": ""})
        self.assertEqual(mapping, {"person": "cdm.person", "cohort": "res.cohort"})

    def test_mapping_errors_are_sentences(self):
        self.assertEqual(n.naming_errors("mapping", mapping={}),
                         ["Give the name used in the scripts for at least one OMOP table."])
        errors = n.naming_errors("mapping", mapping={"persons": "p", "person": "x.t", "concept": "X.T"})
        self.assertEqual(errors, ["Not OMOP tables: persons.", "concept and person are both named x.t in the scripts."])
        with self.assertRaises(ValueError):
            n.key_map("mapping", mapping={})

    def test_mapping_from_atlas_covers_atlas_scripts(self):
        self.assertEqual(n.key_map("mapping", mapping=n.key_map("atlas")), n.key_map("atlas"))

    def test_bad_choices_raise(self):
        with self.assertRaises(ValueError):
            n.key_map("json")
        with self.assertRaises(ValueError):
            n.key_map("prefix", "  ")


class UnmappedReferences(unittest.TestCase):
    SCRIPT = ("DELETE FROM @target_database_schema.@target_cohort_table WHERE x;\n"
              "SELECT * FROM @cdm_database_schema.CONDITION_OCCURRENCE co\n"
              "JOIN @vocabulary_database_schema.concept c ON 1=1\n"
              "JOIN @temp_database_schema.ab12cd34Codesets cs ON 1=1\n"
              "JOIN @results_schema.cohort_inclusion r ON 1=1;")

    def test_atlas_covers_cdm_vocabulary_target_and_ignores_scratch(self):
        self.assertEqual(n.unmapped_references(self.SCRIPT, n.key_map("atlas")), ["@results_schema.cohort_inclusion"])

    def test_atlas_script_under_plain_naming_names_every_placeholder(self):
        self.assertEqual(n.unmapped_references(self.SCRIPT, n.key_map("plain")), [
            "@cdm_database_schema.CONDITION_OCCURRENCE", "@results_schema.cohort_inclusion",
            "@target_database_schema.@target_cohort_table", "@vocabulary_database_schema.concept"])

    def test_every_shipped_atlas_script_is_covered(self):
        for folder in ("snowflake", "databricks", "redshift", "postgre"):
            path = os.path.join(stubs.ROOT, "cohort_scripts", folder)
            for name in sorted(os.listdir(path)):
                if name.endswith(".sql"):
                    with self.subTest(script=folder + "/" + name), open(os.path.join(path, name)) as fh:
                        self.assertEqual(n.unmapped_references(fh.read(), n.key_map("atlas")), [])


if __name__ == "__main__":
    unittest.main()
