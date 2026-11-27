"""Cohort registration (solution-revision-plan.md, R2): the rows the "Register cohorts" tile shows,
the checks on a submitted batch, and the "Built cohorts" listing.

The tile is a convenience; the `register_cohorts` recipe repeats every check against the data and is
the authority. Both call the functions here.

Imports only the pure `batch` and `sql_dialect` modules (hashlib and json are imported inside the
functions that need them): `tools/app_manifest.py` inlines them into the Setup tiles, which cannot
import the project library. The batch rules shared with the characterization tile are in `batch`.
"""

from solution.setup.batch import as_int, batch_errors, latest_by_id
from solution.setup.sql_dialect import dialect_error

NEW, REGISTERED, CHANGED, PENDING = "new", "registered", "changed", "pending"
MAX_NAME_LENGTH = 255


def script_header(text):
    """`-- name:` and `-- description:` values from the script's leading comment lines."""
    header = {}
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("--"):
            break
        body = stripped[2:].strip()
        for key in ("name", "description"):
            if body.lower().startswith(key + ":") and key not in header:
                header[key] = body[len(key) + 1:].strip()
    return header


def script_digest(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def provenance(filename, digest):
    """What `cohort_definition_syntax` holds for a registered cohort: its script and the script's hash."""
    import json
    return json.dumps({"script": filename, "sha256": digest}, sort_keys=True)


def parse_provenance(value):
    import json
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def default_name(filename):
    stem = filename.rsplit("/", 1)[-1]
    stem = stem[:-4] if stem.lower().endswith(".sql") else stem
    words = stem.replace("_", " ").replace("-", " ").split()
    return " ".join(words)[:1].upper() + " ".join(words)[1:] if words else stem


def registration_rows(files, registered, submission=None, connection_type=None):
    """One row per uploaded script, for the "Register cohorts" tile.

    files: {filename: script text}; registered: [{"id", "name", "description", "syntax"}] from
    `cohort_definition`; submission: the last `cohort_submission` (a list of rows).
    A file already registered keeps its id, name and description, is unticked, and is marked
    `changed` when its text differs from the registered script. A file in the last submission but
    not registered (the ingestion failed) keeps what was typed. A new file gets the next free id and
    the header's name and description, and is ticked unless it was exported for another SQL dialect
    than `connection_type`. Every row carries `dialect_issue`: that sentence, or None.
    """
    by_file = {}
    for cohort in registered:
        meta = parse_provenance(cohort.get("syntax"))
        if meta.get("script"):
            by_file[meta["script"]] = (cohort, meta)
    pending = {row.get("file"): row for row in (submission or []) if row.get("file")}
    used = {as_int(c.get("id")) for c in registered} | {as_int(r.get("id")) for r in pending.values()}
    used.discard(None)
    next_id = max(used | {0}) + 1

    rows = []
    for filename in sorted(files):
        text = files[filename]
        header = script_header(text)
        issue = dialect_error(text, connection_type, filename)
        if filename in by_file:
            cohort, meta = by_file[filename]
            changed = meta.get("sha256") != script_digest(text)
            rows.append({"file": filename, "status": CHANGED if changed else REGISTERED,
                         "id": as_int(cohort.get("id")), "name": cohort.get("name") or "",
                         "description": cohort.get("description") or "", "submit": False, "replace": False,
                         "dialect_issue": issue})
        elif filename in pending:
            row = pending[filename]
            rows.append({"file": filename, "status": PENDING, "id": as_int(row.get("id")),
                         "name": row.get("name") or "", "description": row.get("description") or "",
                         "submit": True, "replace": bool(row.get("replace")), "dialect_issue": issue})
        else:
            rows.append({"file": filename, "status": NEW, "id": next_id,
                         "name": header.get("name") or default_name(filename),
                         "description": header.get("description", ""), "submit": issue is None,
                         "replace": False, "dialect_issue": issue})
            next_id += 1
    return rows


def validate_batch(rows, registered_ids, files=None, connection_type=None):
    """Errors in the submitted rows, as sentences. Empty when the batch can be ingested.

    rows: tile rows (only those with `submit` count); registered_ids: ids in `cohort_definition`;
    files: names in "Original Scripts", or {name: script text}, when known. With the texts and the
    project's connection type, a script exported for another SQL dialect is refused.
    """
    errors, valid = batch_errors(rows, registered_ids, lambda r: r.get("file") or "a row", "script",
                                 "already exists", "rebuild it from this script, or choose another id")
    for row, _ in valid:
        label = row.get("file") or "a row"
        name = (row.get("name") or "").strip()
        if not name:
            errors.append("%s: the cohort needs a name." % label)
        elif len(name) > MAX_NAME_LENGTH:
            errors.append("%s: the name is longer than %d characters." % (label, MAX_NAME_LENGTH))
        if files is not None and row.get("file") not in files:
            errors.append("%s: the script is not in Original Scripts." % label)
        elif isinstance(files, dict) and connection_type:
            issue = dialect_error(files[row["file"]], connection_type, label)
            if issue:
                errors.append(issue)
    return errors


def submission(rows):
    """The `cohort_submission` value for the ticked rows."""
    return [{"id": as_int(r.get("id")), "name": (r.get("name") or "").strip(),
             "description": (r.get("description") or "").strip(), "file": r.get("file"),
             "replace": bool(r.get("replace"))}
            for r in rows if r.get("submit")]


def built_cohort_rows(definitions, logs):
    """The "Built cohorts" listing: every registered cohort with its latest build.

    definitions: [{"id", "name", "description", "syntax"}]; logs: [{"run_timestamp", "id", "count",
    "status"}] from `cohort_building_log`, in any order.
    """
    latest = latest_by_id(logs)
    rows = []
    for cohort in definitions:
        cohort_id = as_int(cohort.get("id"))
        log = latest.get(cohort_id, {})
        rows.append({"id": cohort_id, "name": cohort.get("name") or "",
                     "description": cohort.get("description") or "",
                     "script": parse_provenance(cohort.get("syntax")).get("script", ""),
                     "subjects": log.get("count"), "status": log.get("status") or "not built",
                     "last_built": log.get("run_timestamp") or ""})
    rows.sort(key=lambda r: (r["id"] is None, r["id"]))
    return rows


DEFINITION_COLUMNS = {"id": "COHORT_DEFINITION_ID", "name": "COHORT_DEFINITION_NAME",
                      "description": "COHORT_DEFINITION_DESCRIPTION", "syntax": "COHORT_DEFINITION_SYNTAX"}
LOG_COLUMNS = {"run_timestamp": "RUN_TIMESTAMP", "id": "COHORT_DEFINITION_ID", "count": "COHORT_COUNT",
               "status": "STATUS"}


def read_rows(dataset, columns):
    """Rows of a DSS dataset as dicts keyed as in `columns` ({key: column name, any case}).

    Returns [] while the dataset is unbuilt or unreadable, which is the normal state before the
    first registration or build.
    """
    try:
        index = {c["name"].upper(): i for i, c in enumerate(dataset.read_schema())}
        if columns["id"] not in index:
            return []
        return [{key: (row[index[col]] if col in index else None) for key, col in columns.items()}
                for row in dataset.iter_tuples()]
    except Exception:
        return []


def folder_texts(folder):
    """{file name: text} of every file in a DSS managed folder."""
    texts = {}
    for path in folder.list_paths_in_partition():
        with folder.get_download_stream(path) as f:
            texts[path.lstrip("/")] = f.read().decode("utf-8")
    return texts
