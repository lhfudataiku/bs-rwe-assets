"""Every solution module imports with only the repo root on sys.path, and needs no extra packages.

DSS puts both `python` and `python/solution` on the library path, so a bare `from variables import`
works there while loading the module a second time under another name. Importing each module here,
with only `solution.<module>` resolvable, keeps the imports package-qualified.
"""
import ast
import importlib
import importlib.util
import os
import sys
import sysconfig
import unittest

import stubs

stubs.install()


class SolutionImports(unittest.TestCase):
    def test_every_module_imports(self):
        root = os.path.join(stubs.ROOT, "solution")
        bare = {n[:-3] for n in os.listdir(root) if n.endswith(".py")} | {
            n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))}
        for dirpath, _, files in os.walk(root):
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, f), stubs.ROOT)[:-3]
                with self.subTest(module=rel):
                    for name in bare:  # a bare import must not be satisfied by a leftover module
                        sys.modules.pop(name, None)
                    importlib.import_module(rel.replace(os.sep, "."))


# R8: the solution runs on the instance's default Python environment, which provides these.
# dku_utils is bs-commons, pulled as the project library python/ds_common.
THIRD_PARTY = {"dataiku", "dataikuapi", "pandas", "numpy"}
PROJECT_LIBRARIES = {"solution", "dku_utils"}


def is_stdlib(name):
    if name in sys.builtin_module_names or name == "__future__":
        return True
    if hasattr(sys, "stdlib_module_names"):  # Python 3.10+
        return name in sys.stdlib_module_names
    spec = importlib.util.find_spec(name)
    origin = (spec and spec.origin) or ""
    stdlib = sysconfig.get_paths()["stdlib"]
    return origin in ("built-in", "frozen") or (origin.startswith(stdlib) and "site-packages" not in origin)


class CodeEnvironment(unittest.TestCase):
    def test_solution_imports_only_stdlib_and_the_default_env_packages(self):
        allowed = THIRD_PARTY | PROJECT_LIBRARIES
        for dirpath, _, files in os.walk(os.path.join(stubs.ROOT, "solution")):
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue
                path = os.path.join(dirpath, f)
                tops = set()
                for node in ast.walk(ast.parse(open(path).read())):
                    if isinstance(node, ast.Import):
                        tops.update(a.name.split(".")[0] for a in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.level == 0:
                        tops.add(node.module.split(".")[0])
                with self.subTest(module=os.path.relpath(path, stubs.ROOT)):
                    extra = sorted(t for t in tops if t not in allowed and not is_stdlib(t))
                    self.assertFalse(extra, "not in the instance default environment: %s" % extra)


if __name__ == "__main__":
    unittest.main()
