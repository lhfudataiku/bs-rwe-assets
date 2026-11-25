"""Which comparisons to compute (solution-revision-plan.md, R3 decisions 9, 10, 12, 13).

A comparison is a pair (cohort A, comparator B), B being another cohort or the population (-1). It
can be computed when both sides have stored aggregates: their latest characterization succeeded.

- A pair against the population is precomputed by "Characterize cohorts".
- Another pair is computed on request by the webapp backend and kept in `covariate_balance`;
  re-characterizing either cohort deletes it, until it is requested again.
- Each computed request is recorded in `comparison_requests`: when, the pair, and who asked, since
  the backend writes with its own identity.

Pure: tested offline, and used by the webapp services.
"""
from solution.setup.batch import as_int, latest_by_id

POPULATION_ID = -1
POPULATION_LABEL = "Population"
REQUESTS_TABLE = "comparison_requests"
REQUEST_COLUMNS = {"request_timestamp": "REQUEST_TIMESTAMP", "id": "COHORT_DEFINITION_ID",
                   "comparator": "COMPARATOR_ID", "requested_by": "REQUESTED_BY"}
REQUEST_KINDS = [("request_timestamp", "short"), ("cohort_definition_id", "bigint"), ("comparator_id", "bigint"),
                 ("requested_by", "short")]


def _succeeded(log):
    return str(log.get("status") or "").upper() == "SUCCESS"


def comparable(characterization_logs):
    """{cohort id: time of its latest characterization} for every id whose latest attempt succeeded.

    The population (-1) is included when characterized. A cohort whose latest attempt failed is left
    out: on Databricks its stored rows may already be gone.
    """
    return {i: str(log.get("run_timestamp") or "") for i, log in latest_by_id(characterization_logs).items()
            if _succeeded(log)}


def label(cohort_id, names):
    if cohort_id == POPULATION_ID:
        return POPULATION_LABEL
    name = (names or {}).get(cohort_id)
    return "%s (cohort %d)" % (name, cohort_id) if name else "Cohort %d" % cohort_id


def pair_problem(cohort_a, cohort_b, characterized, names=None):
    """Why the pair cannot be compared, as a sentence, or None when it can."""
    a, b = as_int(cohort_a), as_int(cohort_b)
    if a is None or b is None:
        return "Choose cohort A and cohort B."
    if a == POPULATION_ID:
        return "Cohort A must be one of your cohorts; the population can only be cohort B."
    if a == b:
        return "Cohort A and cohort B are the same: choose two different cohorts."
    for cohort_id in (a, b):
        if cohort_id not in characterized:
            if cohort_id == POPULATION_ID:
                return "The population is not characterized yet. Run Characterize cohorts in Project Setup."
            return ("%s is not characterized. Characterize it in Project Setup first." % label(cohort_id, names))
    return None


def cohort_choices(definitions, characterization_logs):
    """The webapp's lists: cohort A from the characterized cohorts; cohort B adds the population first.

    definitions: [{"id", "name"}] from `cohort_definition`. Returns {"cohorts": [{"id", "label"}],
    "comparators": [...]} with the population as cohort B's default (decision 13).
    """
    names = {as_int(d.get("id")): d.get("name") or "" for d in definitions}
    characterized = comparable(characterization_logs)
    cohorts = [{"id": i, "label": label(i, names)} for i in sorted(characterized) if i >= 0 and i in names]
    comparators = cohorts[:]
    if POPULATION_ID in characterized:
        comparators.insert(0, {"id": POPULATION_ID, "label": POPULATION_LABEL})
    return {"cohorts": cohorts, "comparators": comparators,
            "default_comparator": POPULATION_ID if POPULATION_ID in characterized else None}
