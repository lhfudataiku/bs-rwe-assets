"""Choices for the Project Setup (app homepage) select boxes.

The app manifest's tiles call these through thin wrappers in `app_manifest/tiles/`, so the logic is
versioned and tested here instead of living as inline Python in one project's manifest. Each function
returns the `{"choices": [...]}` payload that a PROJECT_VARIABLES_EDIT tile's `do()` must return, and
never raises for a project that is not configured yet: the select box shows one explanatory choice
instead of an error.
"""
import logging

logger = logging.getLogger(__name__)

NO_PREP_PROJECT = {"value": "", "label": "Select a data preparation project first"}
NO_MAIN_CONNECTION = {"value": "", "label": "Set main_connection to a readable connection first"}


def _dataiku():
    import dataiku  # deferred, so the module imports offline
    return dataiku


def _client(client):
    return client if client is not None else _dataiku().api_client()


def _current_project_key(project_key):
    return project_key or _dataiku().get_custom_variables()["projectKey"]


def scoped_variable(variables, name):
    """Return a project variable from the `local` scope, falling back to `standard`.

    Project Setup writes `local`, which the solution code reads; `standard` may still hold an older
    value. Missing and empty values both return None.
    """
    for scope in ("local", "standard"):
        value = (variables.get(scope) or {}).get(name)
        if value:
            return value
    return None


def _options(values):
    return {"choices": [{"value": v, "label": v} for v in sorted(values)]}


def project_choices(client=None):
    """Project keys the user can pick as the data preparation project."""
    return _options(_client(client).list_project_keys())


def omop_table_choices(client=None, project_key=None):
    """Datasets of the data preparation project stored on the same connection type as main_connection.

    The solution imports in-database, so only tables on main_connection's connection type can be
    mapped to an OMOP table.
    """
    client = _client(client)
    variables = client.get_project(_current_project_key(project_key)).get_variables()

    prep_key = scoped_variable(variables, "data_preparation_project_key")
    if not prep_key or prep_key not in set(client.list_project_keys()):
        return {"choices": [NO_PREP_PROJECT]}

    main_connection = scoped_variable(variables, "main_connection")
    if not main_connection:
        return {"choices": [NO_MAIN_CONNECTION]}
    try:
        connection_type = client.get_connection(main_connection).get_info()["type"]
    except Exception as exc:  # missing connection or no permission to read it
        logger.warning("cannot read connection %s: %s", main_connection, exc)
        return {"choices": [NO_MAIN_CONNECTION]}

    datasets = client.get_project(prep_key).list_datasets()
    return _options(d["name"] for d in datasets if d.get("type") == connection_type)


def cohort_definition_choices(dataset=None):
    """Cohorts in `cohort_definition`, matched on column names in any case.

    Returns no choices while the dataset is unbuilt or unreadable.
    """
    if dataset is None:
        dataset = _dataiku().Dataset("cohort_definition")
    try:
        names = [c["name"] for c in dataset.read_schema()]
        index = {n.upper(): i for i, n in enumerate(names)}
        id_col, name_col = index["COHORT_DEFINITION_ID"], index.get("COHORT_DEFINITION_NAME")
        choices = []
        for row in dataset.iter_tuples():
            label = row[name_col] if name_col is not None else row[id_col]
            choices.append({"value": row[id_col], "label": label})
    except Exception as exc:  # unbuilt, unreadable, or without the id column
        logger.warning("cohort_definition has no readable cohorts: %s", exc)
        return {"choices": []}
    choices.sort(key=lambda c: str(c["value"]))
    return {"choices": choices}
