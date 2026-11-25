"""What the Setup batch tiles share (solution-revision-plan.md, R2 and R3 decisions 14-15).

"Register cohorts" and "Characterization batch" both show a table of rows with an *In batch* tick
and a *Replace* tick, check the ticked rows as one batch, and save it to a project variable for a
scenario to run. The rules they share live here, so both batches refuse the same things with the
same sentences: nothing ticked, the same id twice, and an id already done without *Replace*.

Pure, with no imports: `tools/app_manifest.py` inlines it into the Setup tiles.
"""


def as_int(value):
    """`value` as an int when it is written as a whole number ("12", 12, " 12 "); else None."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if str(number) == str(value).strip() else None


def ticked(rows):
    return [r for r in rows if r.get("submit")]


def latest_by_id(logs, time_key="run_timestamp", id_key="id", keep=None):
    """{id: the log row with the latest `time_key`} over rows for which `keep(row)` is true.

    Timestamps are ISO strings (`%Y-%m-%dT%H:%M:%SZ`), so they compare as text.
    """
    latest = {}
    for log in logs:
        row_id = as_int(log.get(id_key))
        if row_id is None or (keep is not None and not keep(log)):
            continue
        if str(log.get(time_key) or "") >= str(latest.get(row_id, {}).get(time_key) or ""):
            latest[row_id] = log
    return latest


def batch_errors(rows, done_ids, label, item, already_done, redo):
    """The shared checks on a batch, as sentences. Empty when they pass.

    rows: tile rows (only those with `submit` count); done_ids: ids that would be overwritten;
    label(row): how a sentence names the row; item: what a row is ("script", "cohort");
    already_done / redo: the words for an id in done_ids ("already exists", "rebuild it from this
    script"). Returns (errors, [(row, id)] for the ticked rows whose id is valid).
    """
    submitted = ticked(rows)
    if not submitted:
        return ["Tick In batch on at least one %s." % item], []
    errors, seen, valid = [], {}, []
    done_ids = {as_int(i) for i in done_ids}
    for row in submitted:
        name = label(row)
        row_id = as_int(row.get("id"))
        if row_id is None or row_id < 0:  # 0 is valid: the demo library uses it
            errors.append("%s: the cohort id must be a whole number, 0 or more, not %r." % (name, row.get("id")))
            continue
        if row_id in seen:
            errors.append("%s: cohort id %d is also given to %s." % (name, row_id, seen[row_id]))
        seen[row_id] = name
        if row_id in done_ids and not row.get("replace"):
            errors.append("%s: cohort %d %s. Tick Replace to %s." % (name, row_id, already_done, redo))
        valid.append((row, row_id))
    return errors, valid
