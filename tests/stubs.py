"""Stand-ins for the DSS-only modules the solution imports, so its logic runs offline.

`install()` puts MagicMock modules for `dataiku` and every `dku_utils` submodule the solution
imports into sys.modules. Tests then patch the names they care about on the imported solution module.
"""
import os
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DSS_MODULES = [
    "dataiku", "dataiku.pandasutils",
    "dku_utils", "dku_utils.projects", "dku_utils.projects.project_commons",
    "dku_utils.projects.recipes", "dku_utils.projects.recipes.recipe_commons",
    "dku_utils.projects.recipes.prepare_recipe", "dku_utils.projects.recipes.sql_recipes",
    "dku_utils.projects.security", "dku_utils.projects.security.sharing",
    "dku_utils.projects.flow_graph", "dku_utils.projects.flow_graph.flow_zones",
    "dku_utils.projects.datasets", "dku_utils.projects.datasets.dataset_commons",
    "dku_utils.projects.scenarios", "dku_utils.projects.scenarios.scenario_commons",
    "dku_utils.type_checking",
]


def install():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    for name in DSS_MODULES:
        sys.modules.setdefault(name, mock.MagicMock(name=name))
