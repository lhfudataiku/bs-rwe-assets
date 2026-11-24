"""Cohort registration (solution-revision-plan.md, R2): the rows the "Register cohorts" tile shows,
the checks on a submitted batch, and the "Built cohorts" listing.

The tile is a convenience; the `register_cohorts` recipe repeats every check against the data and is
the authority. Both call the functions here.

Import-free on purpose (hashlib and json are imported inside the functions that need them):
`tools/app_manifest.py` inlines this module into the Setup tiles, which cannot import the project
library.
"""

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


def _as_int(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if str(number) == str(value).strip() else None


def registration_rows(files, registered, submission=None):
    """One row per uploaded script, for the "Register cohorts" tile.

    files: {filename: script text}; registered: [{"id", "name", "description", "syntax"}] from
    `cohort_definition`; submission: the last `cohort_submission` (a list of rows).
    A file already registered keeps its id, name and description, is unticked, and is marked
    `changed` when its text differs from the registered script. A file in the last submission but
    not registered (the ingestion failed) keeps what was typed. A new file gets the next free id and
    the header's name and description, and is ticked.
    """
    by_file = {}
    for cohort in registered:
        meta = parse_provenance(cohort.get("syntax"))
        if meta.get("script"):
            by_file[meta["script"]] = (cohort, meta)
    pending = {row.get("file"): row for row in (submission or []) if row.get("file")}
    used = {_as_int(c.get("id")) for c in registered} | {_as_int(r.get("id")) for r in pending.values()}
    used.discard(None)
    next_id = max(used | {0}) + 1

    rows = []
    for filename in sorted(files):
        text = files[filename]
        header = script_header(text)
        if filename in by_file:
            cohort, meta = by_file[filename]
            changed = meta.get("sha256") != script_digest(text)
            rows.append({"file": filename, "status": CHANGED if changed else REGISTERED,
                         "id": _as_int(cohort.get("id")), "name": cohort.get("name") or "",
                         "description": cohort.get("description") or "", "submit": False, "replace": False})
        elif filename in pending:
            row = pending[filename]
            rows.append({"file": filename, "status": PENDING, "id": _as_int(row.get("id")),
                         "name": row.get("name") or "", "description": row.get("description") or "",
                         "submit": True, "replace": bool(row.get("replace"))})
        else:
            rows.append({"file": filename, "status": NEW, "id": next_id,
                         "name": header.get("name") or default_name(filename),
                         "description": header.get("description", ""), "submit": True, "replace": False})
            next_id += 1
    return rows


def validate_batch(rows, registered_ids, files=None):
    """Errors in the submitted rows, as sentences. Empty when the batch can be ingested.

    rows: tile rows (only those with `submit` count); registered_ids: ids in `cohort_definition`;
    files: names in "Original Scripts", when known.
    """
    submitted = [r for r in rows if r.get("submit")]
    if not submitted:
        return ["Tick In batch on at least one script."]
    errors, seen = [], {}
    registered_ids = {_as_int(i) for i in registered_ids}
    for row in submitted:
        label = row.get("file") or "a row"
        cohort_id = _as_int(row.get("id"))
        if cohort_id is None or cohort_id < 0:  # 0 is valid: the demo library uses it
            errors.append("%s: the cohort id must be a whole number, 0 or more, not %r." % (label, row.get("id")))
            continue
        if cohort_id in seen:
            errors.append("%s: cohort id %d is also given to %s." % (label, cohort_id, seen[cohort_id]))
        seen[cohort_id] = label
        name = (row.get("name") or "").strip()
        if not name:
            errors.append("%s: the cohort needs a name." % label)
        elif len(name) > MAX_NAME_LENGTH:
            errors.append("%s: the name is longer than %d characters." % (label, MAX_NAME_LENGTH))
        if cohort_id in registered_ids and not row.get("replace"):
            errors.append("%s: cohort %d already exists. Tick Replace to rebuild it from this script, "
                          "or choose another id." % (label, cohort_id))
        if files is not None and row.get("file") not in files:
            errors.append("%s: the script is not in Original Scripts." % label)
    return errors


def submission(rows):
    """The `cohort_submission` value for the ticked rows."""
    return [{"id": _as_int(r.get("id")), "name": (r.get("name") or "").strip(),
             "description": (r.get("description") or "").strip(), "file": r.get("file"),
             "replace": bool(r.get("replace"))}
            for r in rows if r.get("submit")]


def built_cohort_rows(definitions, logs):
    """The "Built cohorts" listing: every registered cohort with its latest build.

    definitions: [{"id", "name", "description", "syntax"}]; logs: [{"run_timestamp", "id", "count",
    "status"}] from `cohort_building_log`, in any order.
    """
    latest = {}
    for log in logs:
        cohort_id = _as_int(log.get("id"))
        if cohort_id is not None and str(log.get("run_timestamp")) >= str(latest.get(cohort_id, {}).get("run_timestamp", "")):
            latest[cohort_id] = log
    rows = []
    for cohort in definitions:
        cohort_id = _as_int(cohort.get("id"))
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
