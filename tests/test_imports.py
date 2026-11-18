"""Every solution module imports with only the repo root on sys.path.

DSS puts both `python` and `python/solution` on the library path, so a bare `from variables import`
works there while loading the module a second time under another name. Importing each module here,
with only `solution.<module>` resolvable, keeps the imports package-qualified.
"""
import importlib
import os
import sys
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


if __name__ == "__main__":
    unittest.main()
