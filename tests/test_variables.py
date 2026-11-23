"""R7: one reader of project variables (`get_setting`) and one contract of keys.

Fails when solution code or a Setup tile wrapper reads or writes a key outside
`solution.variables.VARIABLE_CONTRACT`, or reads a scope directly instead of through `get_setting`.
The Setup manifest itself is checked by `tools/app_manifest.py --check`.
"""
import ast
import os
import re
import unittest

import stubs

stubs.install()
from solution import variables as v  # noqa: E402
from solution.utils.variables import get_setting  # noqa: E402

READER = os.path.join("solution", "utils", "variables.py")
SCOPE_ACCESS = re.compile(r"""\[\s*['"](local|standard)['"]\s*\]|\.get\(\s*['"](local|standard)['"]""")
WRITERS = {"update_variables", "set_variables"}


def sources():
    for top in ("solution", os.path.join("app_manifest", "tiles")):
        for dirpath, _, files in os.walk(os.path.join(stubs.ROOT, top)):
            for name in sorted(files):
                if name.endswith(".py"):
                    path = os.path.join(dirpath, name)
                    yield os.path.relpath(path, stubs.ROOT), open(path).read()


def keys_used(code):
    """String keys passed to get_setting, and dict keys written with update/set_variables."""
    keys = set()
    for node in ast.walk(ast.parse(code)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if func == "get_setting" and node.args and isinstance(node.args[0], ast.Constant):
            keys.add(node.args[0].value)
        elif func == "set_local" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            keys.add(node.args[1].value)
        elif func in WRITERS:
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    keys.update(k.value for k in arg.keys if isinstance(k, ast.Constant))
    return keys


class GetSetting(unittest.TestCase):
    def test_local_then_standard_then_default(self):
        variables = {"local": {"a": "L", "b": "", "c": None}, "standard": {"a": "S", "b": "S", "c": "S"}}
        self.assertEqual([get_setting(k, variables) for k in "abcd"], ["L", "S", "S", None])
        self.assertEqual(get_setting("d", variables, default=7), 7)

    def test_false_zero_and_empty_list_are_values(self):
        variables = {"local": {"flag": False, "n": 0, "tables": []},
                     "standard": {"flag": True, "n": 9, "tables": ["person"]}}
        self.assertEqual([get_setting(k, variables) for k in ("flag", "n", "tables")], [False, 0, []])

    def test_missing_scopes(self):
        self.assertIsNone(get_setting("a", {}))
        self.assertIsNone(get_setting("a", {"local": None, "standard": None}))


class SetLocal(unittest.TestCase):
    def test_writes_local_only(self):
        from unittest import mock
        from solution.utils.variables import set_local
        project = mock.MagicMock()
        project.get_variables.return_value = {"standard": {"a": 1}, "local": {}}
        self.assertEqual(set_local(project, "cohort_submission", [1]), [1])
        project.set_variables.assert_called_once_with({"standard": {"a": 1}, "local": {"cohort_submission": [1]}})

    def test_set_local_keys_are_checked(self):
        self.assertEqual(keys_used("set_local(p, 'cohort_submission', [])"), {"cohort_submission"})


class Contract(unittest.TestCase):
    def test_scopes_do_not_overlap(self):
        self.assertFalse(set(v.STANDARD_DEFAULTS) & v.LOCAL_KEYS)
        self.assertFalse(set(v.RETIRING_KEYS) & (set(v.STANDARD_DEFAULTS) | v.LOCAL_KEYS))

    def test_code_uses_only_contract_keys(self):
        for path, code in sources():
            with self.subTest(path=path):
                unknown = keys_used(code) - v.VARIABLE_CONTRACT
                self.assertFalse(unknown, "keys outside solution.variables.VARIABLE_CONTRACT: %s" % sorted(unknown))

    def test_scopes_are_read_only_through_get_setting(self):
        for path, code in sources():
            if path == READER:
                continue
            with self.subTest(path=path):
                self.assertIsNone(SCOPE_ACCESS.search(code), "read variables with get_setting()")

    def test_dropped_keys_are_gone(self):
        dropped = {"advanced_file_format", "condition_count_for_charlson_score", "connection_type",
                   "cohort_build_error", "cdm_standard_tables_map"}
        self.assertFalse(dropped & v.VARIABLE_CONTRACT)


if __name__ == "__main__":
    unittest.main()
