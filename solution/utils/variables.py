"""The one reader of project variables: `local` first, then `standard`.

Project Setup writes the `local` scope; `standard` holds the shipped defaults and tunables. Which key
belongs to which scope is fixed in `solution.variables` (VARIABLE_CONTRACT) and enforced by
`tests/test_variables.py`.

This module imports nothing at load time: `tools/app_manifest.py` inlines it into the Project Setup
tiles, whose Python process cannot import the project library.
"""


def _is_set(value):
    return value is not None and value != ""


def get_setting(name, variables=None, default=None):
    """Return project variable `name` from `local`, falling back to `standard`, else `default`.

    `variables` is the dict `get_variables()` returns (`{"standard": {...}, "local": {...}}`); when
    omitted, the current project's variables are read. A key that is absent, None or "" in a scope
    counts as unset there; False, 0 and [] are values and win.
    """
    if variables is None:
        import dataiku  # deferred, so the module imports offline
        variables = dataiku.api_client().get_default_project().get_variables()
    for scope in ("local", "standard"):
        value = (variables.get(scope) or {}).get(name)
        if _is_set(value):
            return value
    return default
