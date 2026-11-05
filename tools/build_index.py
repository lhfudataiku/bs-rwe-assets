#!/usr/bin/env python3
"""Generate .index/ for the RWD/RWE suite: one place that says which project is canonical, whether
it is built, whether it passes the v1.1 schema check, and whether its cross-project inputs exist.

WHY THIS EXISTS. The 2026-09-23 audit answered those questions with ad-hoc scripts that were not
kept. Each failure it found (unbuilt Snowflake tables, a prep project that no longer exists, dropped
tables still shared into DEMO_SF_RWE) was invisible in DSS until someone went looking. This tool
makes them rows in a committed table, so a regression shows up in review and in CI.

THREE MODES.
    python3 tools/build_index.py --refresh   # hits DSS through `dku`, rewrites .index/dss_snapshot.json (~15 min)
    python3 tools/build_index.py --reprobe   # hits DSS for the built/row-count probes only
    python3 tools/build_index.py             # offline: rebuilds every .index/*.tsv from the snapshot
    python3 tools/build_index.py --check     # offline: fails if a TSV is stale or the issue baseline moved

HAND-WRITTEN vs GENERATED. registry/projects.json holds what DSS cannot tell us (part, role,
lifecycle, owner, which datasets form an OMOP set). registry/known_issues.json is the reviewed
baseline of accepted problems. Everything in .index/ is generated; never edit it by hand.

THE BASELINE RATCHET. --check compares the issues found in the snapshot with known_issues.json in
both directions. A new issue fails (a regression). A baseline entry that no longer occurs also fails,
so the entry must be deleted when the migration fixes it -- the baseline can only shrink, and its
remaining entries are the checklist of what the migration still has to turn green.

The schema rules are the solution's own: CDM_SCHEMA from solution/schema/cdm_schema.py, column
names compared lowercase, bigint read as int and double as float, exactly as check_schema.py does.
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, ".index")
SNAP = os.path.join(INDEX, "dss_snapshot.json")
REGISTRY = os.path.join(ROOT, "registry", "projects.json")
BASELINE = os.path.join(ROOT, "registry", "known_issues.json")

sys.path.insert(0, ROOT)
from solution.schema.cdm_schema import CDM_SCHEMA  # noqa: E402

# The 15 tables the solution maps (v1.1 omop_cdm_standard_tables_import + the vocabulary import).
OMOP_TABLES = [
    "person", "observation_period", "visit_occurrence", "condition_occurrence", "drug_exposure",
    "procedure_occurrence", "device_exposure", "measurement", "observation", "death", "location",
    "drug_era", "condition_era", "concept", "concept_ancestor",
]
ROLES = {"canonical", "variant", "release", "demo", "scratch"}
LIFECYCLES = {"active", "retiring", "planned", "deleted", "archived"}
OWNER_ROLES = {"data-foundation", "solution", "rwe-demo", "suite"}
# Dataset types whose rows can be counted with SQL. Anything else falls back to the DSS metric.
SQL_TYPES = {"Snowflake", "Redshift", "PostgreSQL", "Databricks", "BigQuery", "Synapse", "SQLServer"}
WORKERS = 12
TIMEOUT = 240
# A Git remote can carry a token as URL userinfo (https://<token>@github.com/...). The snapshot is
# committed, so userinfo is stripped before it is written, and --check fails if any is left.
URL_USERINFO = re.compile(r'(?<=://)[^/@\s"]+@')


def redact(text):
    return URL_USERINFO.sub("", text)


# ------------------------------------------------------------------------------------- registry

def load_registry():
    with open(REGISTRY) as fh:
        reg = json.load(fh)
    errors = []
    if reg.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    seen = set()
    required = {"key", "part", "role", "sample_size", "connections", "upstream", "owner", "personas",
                "library", "lifecycle", "decision", "omop_sets"}
    for p in reg.get("projects", []):
        key = p.get("key", "?")
        if set(p) != required:
            errors.append("%s: fields %s" % (key, sorted(set(p) ^ required)))
            continue
        if key in seen:
            errors.append("%s: duplicate" % key)
        seen.add(key)
        if p["part"] not in (1, 2, 3):
            errors.append("%s: part must be 1, 2 or 3" % key)
        if p["role"] not in ROLES:
            errors.append("%s: role %r" % (key, p["role"]))
        if p["lifecycle"] not in LIFECYCLES:
            errors.append("%s: lifecycle %r" % (key, p["lifecycle"]))
        if p["owner"] not in OWNER_ROLES:
            errors.append("%s: owner %r" % (key, p["owner"]))
        for name, tables in p["omop_sets"].items():
            if set(tables) != set(OMOP_TABLES) or not all(v is None or isinstance(v, str) for v in tables.values()):
                errors.append("%s/%s: OMOP set must map exactly the 15 tables (diff %s)"
                              % (key, name, sorted(set(tables) ^ set(OMOP_TABLES))))
    for key in reg.get("out_of_scope", {}):
        if key in seen:
            errors.append("%s: both registered and out of scope" % key)
    if errors:
        raise SystemExit("registry/projects.json is invalid:\n  " + "\n  ".join(errors))
    return reg


def load_baseline():
    if not os.path.exists(BASELINE):
        return {}
    with open(BASELINE) as fh:
        data = json.load(fh)
    for issue_id, entry in data.items():
        if not gating(issue_id):
            raise SystemExit("known_issues.json: %s is informational and cannot be baselined" % issue_id)
        if set(entry) != {"plan", "note"}:
            raise SystemExit("known_issues.json: %s needs exactly plan and note" % issue_id)
    return data


# ------------------------------------------------------------------------------------- refresh

def dku(args, timeout=TIMEOUT):
    """Run dku with JSON output. Returns (ok, parsed_or_error_text)."""
    try:
        res = subprocess.run(["dku", "--format", "json"] + args, capture_output=True, text=True,
                             timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "timeout after %ds" % timeout
    if res.returncode != 0:
        return False, " ".join((res.stderr or res.stdout).split())
    try:
        return True, json.loads(res.stdout) if res.stdout.strip() else None
    except ValueError:
        return True, res.stdout


def short_error(text):
    text = re.sub(r"^◆\s*", "", text)
    for marker in ("does not exist", "not authorized", "Table or view not found", "expired",
                   "Invalid OAuth", "timeout", "Unable to", "Not found"):
        if marker.lower() in text.lower():
            i = text.lower().index(marker.lower())
            return text[max(0, i - 60): i + 80].strip()
    return text[:160]


def probe(project, name, dtype):
    """Is the dataset's data there, and how many rows? Returns a dict for the snapshot.

    SQL datasets: SELECT COUNT(*) on the resolved table. `dku dataset query` does not quote the
    resolved name, so a name containing '-' (Snowflake's ${TENANT}/${NODE} suffix, the Databricks
    catalog se-sandbox) fails with a syntax error; retry with the name taken from the error, quoted.
    Other datasets: a one-row read decides built/empty; rows come from the cached COUNT_RECORDS
    metric when one exists (it is only as fresh as the last metrics computation) and stay blank otherwise.
    """
    if dtype in SQL_TYPES:
        sql = "SELECT COUNT(*) AS n FROM {{table}}"
        ok, out = dku(["dataset", "query", name, "-P", project, "--sql", sql])
        m = re.search(r"FROM (\S+?)'", out) if not ok else None
        if m and "-" in m.group(1):
            # Snowflake: "unexpected '-'"; Databricks: PARSE_SYNTAX_ERROR on a catalog such as se-sandbox.
            q = "`" if dtype == "Databricks" else '"'
            quoted = ".".join(q + part + q for part in m.group(1).split("."))
            ok, out = dku(["dataset", "query", name, "-P", project, "--sql",
                               "SELECT COUNT(*) AS n FROM %s" % quoted])
        if ok:
            row = (out or [{}])[0]
            rows = next(iter(row.values()), None) if row else None
            return {"built": "yes" if rows else "empty", "rows": rows, "source": "sql", "error": ""}
        missing = any(s in out for s in ("does not exist", "Table or view not found", "TABLE_OR_VIEW_NOT_FOUND"))
        return {"built": "no" if missing else "unknown", "rows": None, "source": "sql",
                "error": short_error(out)}
    # Never `dataset count` here: without a cached metric it starts a COUNT_RECORDS computation that
    # keeps running server-side after a client timeout and stalls every later read of that project.
    ok, info = dku(["dataset", "info", name, "-P", project])
    rows = info.get("rows") if ok and isinstance(info, dict) else None
    ok, out = dku(["dataset", "head", name, "-P", project, "--limit", "1"])
    if ok and isinstance(out, list):
        return {"built": "yes" if out else "empty", "rows": rows if out else 0,
                "source": "metric" if rows is not None else "head", "error": ""}
    if "Root path of the dataset does not exist" in out:  # managed file dataset never built
        return {"built": "no", "rows": None, "source": "head", "error": short_error(out)}
    return {"built": "unknown", "rows": None, "source": "head", "error": short_error(out)}


def wiki_version(project, articles):
    """First 'Version x.y[.z]' in the Overview or Release Notes article, or ''."""
    for art in articles:
        if art["title"].lower() in ("overview", "release notes"):
            ok, out = dku(["wiki", "get", art["id"], "-P", project])
            body = json.dumps(out) if ok else ""
            m = re.search(r"\bVersi?on\s*:?\s*\**\s*(\d+\.\d+(?:\.\d+)?)", body)  # SOL spells it "Verson"
            if m:
                return m.group(1)
    return ""


def fetch_project(key):
    ok, insp = dku(["project", "inspect", key])
    if not ok:
        return {"exists": False, "error": short_error(insp)}
    _, variables = dku(["project", "get-variables", "-P", key])
    ok, libs = dku(["library", "read", "external-libraries.json", "-P", key])
    git_refs = {}
    if ok and isinstance(libs, dict):
        for path, ref in sorted(libs.get("gitReferences", {}).items()):
            git_refs[path] = {"remote": ref.get("remote", ""),
                              "checkout": re.sub(r"^refs/heads/", "", ref.get("checkout", "")),
                              "hash": ref.get("lastHash", "")}
    articles = [{"id": str(a["id"]), "title": a["title"]} for a in insp.get("wiki_articles", [])]
    names = [d["name"] for d in insp.get("datasets", [])]

    def definition(name):
        ok, d = dku(["dataset", "get-definition", name, "-P", key])
        if not ok:
            return name, {"error": short_error(d)}
        params = d.get("params") or {}
        return name, {
            "type": d.get("type"),
            "managed": bool(d.get("managed")),
            "connection": params.get("connection", ""),
            "columns": [[c.get("name"), c.get("type")] for c in (d.get("schema") or {}).get("columns", [])],
        }

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        datasets = dict(pool.map(definition, names))
    return {
        "exists": True,
        "name": insp.get("name", ""),
        "variables": {"standard": (variables or {}).get("standard", {}),
                      "local": (variables or {}).get("local", {})},
        "git_references": git_refs,
        "flow_sources": sorted(insp.get("flow_sources", [])),
        "wiki_articles": articles,
        "wiki_version": wiki_version(key, articles),
        "datasets": dict(sorted(datasets.items())),
    }


def foreign_sources(proj):
    """Flow sources shared in from another project ('PROJECT.dataset'); the rest are local inputs."""
    return [s for s in proj.get("flow_sources", []) if "." in s]


def effective_vars(proj):
    """DSS resolution: local overrides standard."""
    merged = dict(proj["variables"]["standard"])
    merged.update(proj["variables"]["local"])
    return merged


def probe_targets(reg, projects):
    """Datasets whose data we need to see: every registry OMOP set, every consumer table mapping,
    every cross-project flow source. Everything else in datasets.tsv is listed without a probe."""
    targets = set()
    for p in reg["projects"]:
        for tables in p["omop_sets"].values():
            targets.update((p["key"], ds) for ds in tables.values() if ds)
    for key, proj in projects.items():
        if not proj.get("exists"):
            continue
        ev = effective_vars(proj)
        prep = ev.get("data_preparation_project_key")
        if prep in projects and projects[prep].get("exists"):
            targets.update((prep, ev[t]) for t in OMOP_TABLES if ev.get(t))
        for src in foreign_sources(proj):
            sp, _, sd = src.partition(".")
            if sp in projects and projects[sp].get("exists"):
                targets.add((sp, sd))
    return sorted(t for t in targets
                  if t[0] in projects and projects[t[0]].get("exists") and t[1] in projects[t[0]]["datasets"])


def reprobe(reg):
    """Re-run only the probes, keeping the snapshot's project definitions (minutes, not a full refresh)."""
    with open(SNAP) as fh:
        snap = json.load(fh)
    write_probes(reg, snap)


def write_probes(reg, snap):
    projects = snap["projects"]
    for proj in projects.values():
        for ds in proj.get("datasets", {}).values():
            ds.pop("probe", None)
    targets = probe_targets(reg, projects)
    print("probing %d datasets" % len(targets), file=sys.stderr)

    def run(t):
        project, name = t
        return t, probe(project, name, projects[project]["datasets"][name].get("type"))

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for (project, name), result in pool.map(run, targets):
            projects[project]["datasets"][name]["probe"] = result
    snap["refreshed_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    with open(SNAP, "w") as fh:
        fh.write(redact(json.dumps(snap, indent=1, sort_keys=True)) + "\n")
    print("wrote %s (%d projects, %d probes)" % (os.path.relpath(SNAP, ROOT), len(projects), len(targets)))


def refresh(reg):
    ok, listing = dku(["project", "list", "--fields", "projectKey,name"])
    if not ok:
        raise SystemExit("dku project list failed: " + listing)
    all_keys = {p["projectKey"] for p in listing}
    pattern = re.compile(reg["discovery_pattern"])
    discovered = sorted(k for k in all_keys if pattern.search(k))

    keys = [p["key"] for p in reg["projects"]]
    projects = {}
    for key in keys:
        if key not in all_keys:
            projects[key] = {"exists": False, "error": "not on DSS"}
            continue
        print("fetching %s" % key, file=sys.stderr)
        projects[key] = fetch_project(key)

    # Keys referenced from DSS (prep project variables, flow sources) that are not registered.
    referenced = set()
    for proj in projects.values():
        if not proj.get("exists"):
            continue
        for scope in ("standard", "local"):
            ref = proj["variables"][scope].get("data_preparation_project_key")
            if ref:
                referenced.add(ref)
        referenced.update(s.partition(".")[0] for s in foreign_sources(proj))
    external = {k: (k in all_keys) for k in sorted(referenced - set(keys))}

    snap = {"dss_project_count": len(all_keys), "discovered": discovered,
            "external_projects": external, "projects": projects}
    write_probes(reg, snap)


# ------------------------------------------------------------------------------------- analysis

def normalize_type(t):
    return {"bigint": "int", "double": "float"}.get(t, t)


def check_table(omop_table, columns):
    """Apply the solution's check_schema rules. Returns (pass, reason)."""
    imported = {}
    for name, dtype in columns:
        imported[(name or "").lower()] = normalize_type(dtype)
    problems = []
    for col, dtype, required in CDM_SCHEMA[omop_table]:
        got = imported.get(col)
        if required and got is None:
            problems.append("%s missing" % col)
        elif got is not None and got != dtype:
            problems.append("%s %s≠%s%s" % (col, got, dtype, "" if required else " (optional)"))
    return (not problems), "; ".join(problems)


def exists_on_dss(snap, key):
    proj = snap["projects"].get(key)
    if proj is not None:
        return proj.get("exists", False)
    return snap["external_projects"].get(key, False)


def dataset_state(snap, key, name):
    """(exists, built, rows) for a dataset in any snapshot project."""
    proj = snap["projects"].get(key) or {}
    ds = (proj.get("datasets") or {}).get(name)
    if ds is None:
        return "no", "-", ""
    pr = ds.get("probe")
    if not pr:
        return "yes", "-", ""
    return "yes", pr["built"], "" if pr["rows"] is None else str(pr["rows"])


def analyse(reg, snap):
    """Every table row and every issue, derived from registry + snapshot only."""
    regp = {p["key"]: p for p in reg["projects"]}
    rows = {"projects": [], "datasets": [], "schema": [], "lineage": [], "issues": []}
    issues = rows["issues"]

    def issue(issue_id, project, detail):
        issues.append({"id": issue_id, "project": project, "detail": detail})

    # Coverage: every discovered DSS project is registered or explicitly out of scope.
    for key in snap["discovered"]:
        if key not in regp and key not in reg["out_of_scope"]:
            issue("UNREGISTERED:%s" % key, key, "DSS project matches the discovery pattern but is not in the registry")

    for p in reg["projects"]:
        key = p["key"]
        proj = snap["projects"].get(key, {"exists": False})
        on_dss = proj.get("exists", False)
        if p["lifecycle"] in ("active", "retiring") and not on_dss:
            issue("PROJECT_MISSING:%s" % key, key, "registered as %s but not on DSS" % p["lifecycle"])
        if p["lifecycle"] in ("planned", "deleted", "archived") and on_dss:
            issue("LIFECYCLE_STALE:%s" % key, key, "registered as %s but exists on DSS" % p["lifecycle"])

        ev = effective_vars(proj) if on_dss else {}
        sol = proj.get("git_references", {}).get("python/solution", {}) if on_dss else {}
        com = proj.get("git_references", {}).get("python/ds_common", {}) if on_dss else {}
        rows["projects"].append({
            "key": key, "part": p["part"], "role": p["role"], "lifecycle": p["lifecycle"],
            "sample_size": p["sample_size"] or "", "on_dss": "yes" if on_dss else "no",
            "name": proj.get("name", ""), "owner": p["owner"],
            "owner_name": reg["owners"].get(p["owner"]) or "unassigned",
            "prep_key_standard": proj.get("variables", {}).get("standard", {}).get("data_preparation_project_key", "") if on_dss else "",
            "prep_key_local": proj.get("variables", {}).get("local", {}).get("data_preparation_project_key", "") if on_dss else "",
            "main_connection": ev.get("main_connection", ""),
            "solution_lib": ("%s@%s" % (sol["checkout"], sol["hash"][:7])) if sol else "",
            "commons_lib": ("%s@%s" % (com["checkout"], com["hash"][:7])) if com else "",
            "datasets": len(proj.get("datasets", {})) if on_dss else "",
            "wiki_articles": len(proj.get("wiki_articles", [])) if on_dss else "",
            "wiki_version": proj.get("wiki_version", "") if on_dss else "",
            "omop_sets": ",".join(sorted(p["omop_sets"])),
        })
        if not on_dss:
            continue

        # Library pins recorded in the registry vs what DSS has checked out.
        for path, pin in sorted((p["library"] or {}).items()):
            got = proj["git_references"].get(path)
            if not got:
                issue("LIBRARY_DRIFT:%s:%s" % (key, path), key, "registry pins %s but DSS has no such git reference" % path)
                continue
            if got["checkout"] != pin["branch"] or (pin["hash"] and not got["hash"].startswith(pin["hash"])):
                issue("LIBRARY_DRIFT:%s:%s" % (key, path), key, "registry %s@%s, DSS %s@%s"
                      % (pin["branch"], (pin["hash"] or "?")[:7], got["checkout"], got["hash"][:7]))

        # datasets.tsv: every dataset, with a probe result where one was taken.
        omop_of = {}
        for set_name, tables in p["omop_sets"].items():
            for t, ds in tables.items():
                if ds:
                    omop_of[ds] = (set_name, t)
        for name, ds in proj["datasets"].items():
            pr = ds.get("probe") or {}
            set_name, t = omop_of.get(name, ("", ""))
            rows["datasets"].append({
                "project": key, "dataset": name, "type": ds.get("type") or "",
                "connection": ds.get("connection", ""), "managed": "yes" if ds.get("managed") else "no",
                "columns": len(ds.get("columns", [])), "omop_set": set_name, "omop_table": t,
                "built": pr.get("built", "-"), "rows": "" if pr.get("rows") is None else pr["rows"],
                "row_source": pr.get("source", ""), "probe_error": pr.get("error", ""),
            })

        # schema_compliance.tsv: each registered OMOP set, table by table.
        for set_name, tables in sorted(p["omop_sets"].items()):
            fails, absent, unbuilt, unknown = [], [], [], []
            for t in OMOP_TABLES:
                name = tables[t]
                ds = proj["datasets"].get(name) if name else None
                if ds is None:
                    result, built = "missing", "-"
                    reason = "dataset %s does not exist" % name if name else "no dataset for this table"
                    absent.append(t)
                else:
                    passed, reason = check_table(t, ds.get("columns", []))
                    result = "pass" if passed else "fail"
                    built = (ds.get("probe") or {}).get("built", "-")
                    if not passed:
                        fails.append(t)
                    if built in ("no", "empty"):
                        unbuilt.append(t)
                    elif built == "unknown":
                        unknown.append(t)
                rows["schema"].append({"project": key, "omop_set": set_name, "omop_table": t,
                                       "dataset": name or "", "result": result, "built": built, "reason": reason})
            if absent:
                issue("SET_INCOMPLETE:%s:%s" % (key, set_name), key, "%d/15 datasets missing: %s" % (len(absent), ", ".join(absent)))
            if fails:
                issue("SCHEMA_FAIL:%s:%s" % (key, set_name), key, "%d/15 tables fail v1.1: %s" % (len(fails), ", ".join(fails)))
            if unbuilt:
                issue("UNBUILT:%s:%s" % (key, set_name), key, "%d/15 tables have no data: %s" % (len(unbuilt), ", ".join(unbuilt)))
            if unknown:
                issue("UNREADABLE:%s:%s" % (key, set_name), key, "%d/15 tables could not be read" % len(unknown))

        # lineage.tsv (1): the prep project each consumer names, in each variable scope.
        for scope in ("standard", "local"):
            ref = proj["variables"][scope].get("data_preparation_project_key")
            if not ref:
                continue
            ok = exists_on_dss(snap, ref)
            rows["lineage"].append({"consumer": key, "kind": "prep_key_" + scope, "name": "data_preparation_project_key",
                                    "source_project": ref, "source_dataset": "", "source_project_exists": "yes" if ok else "no",
                                    "source_dataset_exists": "", "source_built": ""})
            if not ok:
                issue("PREP_KEY_DANGLING:%s:%s" % (key, scope), key,
                      "%s variable data_preparation_project_key names %s, which is not on DSS" % (scope, ref))

        # lineage.tsv (2): the 15 table variables, resolved against the effective prep project.
        prep = ev.get("data_preparation_project_key")
        if prep:
            bad = []
            for t in OMOP_TABLES:
                name = ev.get(t)
                if not name:
                    continue
                pexists = exists_on_dss(snap, prep)
                dexists, built, _ = dataset_state(snap, prep, name) if pexists else ("no", "-", "")
                rows["lineage"].append({"consumer": key, "kind": "table_variable", "name": t, "source_project": prep,
                                        "source_dataset": name, "source_project_exists": "yes" if pexists else "no",
                                        "source_dataset_exists": dexists, "source_built": built})
                if pexists and (dexists == "no" or built in ("no", "empty")):
                    bad.append(t)
            if bad:
                issue("MAPPING_BROKEN:%s" % key, key, "%d table variables point at missing or unbuilt datasets in %s: %s"
                      % (len(bad), prep, ", ".join(bad)))

        # lineage.tsv (3): datasets shared in from other projects.
        broken = {}
        for src in foreign_sources(proj):
            sp, _, sd = src.partition(".")
            pexists = exists_on_dss(snap, sp)
            dexists, built, _ = dataset_state(snap, sp, sd) if pexists else ("no", "-", "")
            rows["lineage"].append({"consumer": key, "kind": "flow_source", "name": sd, "source_project": sp,
                                    "source_dataset": sd, "source_project_exists": "yes" if pexists else "no",
                                    "source_dataset_exists": dexists, "source_built": built})
            if not pexists or dexists == "no" or built in ("no", "empty"):
                broken.setdefault(sp, []).append(sd)
        for sp, names in sorted(broken.items()):
            issue("SHARE_BROKEN:%s:%s" % (key, sp), key, "%d shared inputs from %s are missing or unbuilt: %s"
                  % (len(names), sp, ", ".join(sorted(names))))

    return rows


# ------------------------------------------------------------------------------------- output

COLUMNS = {
    "projects.tsv": ["key", "part", "role", "lifecycle", "sample_size", "on_dss", "name", "owner", "owner_name",
                     "prep_key_standard", "prep_key_local", "main_connection", "solution_lib", "commons_lib",
                     "datasets", "wiki_articles", "wiki_version", "omop_sets"],
    "datasets.tsv": ["project", "dataset", "type", "connection", "managed", "columns", "omop_set", "omop_table",
                     "built", "rows", "row_source", "probe_error"],
    "schema_compliance.tsv": ["project", "omop_set", "omop_table", "dataset", "result", "built", "reason"],
    "lineage.tsv": ["consumer", "kind", "name", "source_project", "source_dataset", "source_project_exists",
                    "source_dataset_exists", "source_built"],
    "issues.tsv": ["id", "project", "status", "plan", "detail"],
}
SOURCE = {"projects.tsv": "projects", "datasets.tsv": "datasets", "schema_compliance.tsv": "schema",
          "lineage.tsv": "lineage", "issues.tsv": "issues"}

METADATA = [
    ("registry/projects.json", "suite owner", "hand-written; validated by --check", "one entry per DSS project: part, role, lifecycle, owner, OMOP sets"),
    ("registry/known_issues.json", "suite owner", "hand-written; --check fails if it differs from issues.tsv", "accepted problems the migration has still to fix"),
    (".index/dss_snapshot.json", "tools/build_index.py --refresh", "as of refreshed_at inside the file", "raw DSS state: variables, git references, flow sources, dataset schemas, probes"),
    (".index/projects.tsv", "tools/build_index.py", "python3 tools/build_index.py --check", "one row per registered project with live wiring"),
    (".index/datasets.tsv", "tools/build_index.py", "python3 tools/build_index.py --check", "every dataset of every registered project; built/rows for probed ones"),
    (".index/schema_compliance.tsv", "tools/build_index.py", "python3 tools/build_index.py --check", "each OMOP set table vs CDM_SCHEMA v1-1-1"),
    (".index/lineage.tsv", "tools/build_index.py", "python3 tools/build_index.py --check", "prep keys, table variables and shared-in datasets, with existence"),
    (".index/issues.tsv", "tools/build_index.py", "python3 tools/build_index.py --check", "every problem found, marked known or NEW against the baseline"),
    (".index/SUMMARY.md", "tools/build_index.py", "python3 tools/build_index.py --check", "counts and open issues for humans"),
]


def cell(v):
    return str(v).replace("\t", " ").replace("\n", " ")


# Probe failures say the index could not see the data (expired OAuth, cold warehouse, a busy DSS),
# not that the asset is wrong, so they are listed but never gate --check or enter the baseline.
INFORMATIONAL = ("UNREADABLE:",)


def gating(issue_id):
    return not issue_id.startswith(INFORMATIONAL)


def render(reg, snap, baseline):
    data = analyse(reg, snap)
    for it in data["issues"]:
        known = baseline.get(it["id"])
        it["status"] = "info" if not gating(it["id"]) else "known" if known else "NEW"
        it["plan"] = known["plan"] if known else ""
    data["issues"].sort(key=lambda r: r["id"])
    out = {}
    for fname, cols in COLUMNS.items():
        lines = ["\t".join(cols)]
        lines += ["\t".join(cell(r.get(c, "")) for c in cols) for r in data[SOURCE[fname]]]
        out[fname] = "\n".join(lines) + "\n"
    meta = ["path\towner\tfreshness\tscope"] + ["\t".join(m) for m in METADATA]
    out["index_metadata.tsv"] = "\n".join(meta) + "\n"
    out["SUMMARY.md"] = summary(reg, snap, data, baseline)
    return out, data


def summary(reg, snap, data, baseline):
    issues = data["issues"]
    new = [i for i in issues if i["status"] == "NEW"]
    current = {i["id"] for i in issues if gating(i["id"])}
    resolved = sorted(set(baseline) - current)
    sets = {}
    for r in data["schema"]:
        s = sets.setdefault((r["project"], r["omop_set"]), [0, 0])
        s[0] += r["result"] == "pass"
        s[1] += r["built"] == "yes"
    lines = [
        "# Index summary",
        "",
        "> Generated by `tools/build_index.py` from the snapshot taken %s. Do not edit." % snap["refreshed_at"],
        "",
        "- Registered projects: %d (%s)" % (len(reg["projects"]), ", ".join(
            "%d %s" % (sum(p["lifecycle"] == lc for p in reg["projects"]), lc)
            for lc in ("active", "retiring", "planned", "deleted") if any(p["lifecycle"] == lc for p in reg["projects"]))),
        "- Issues: %d (%d known, %d NEW, %d informational); baseline entries no longer occurring: %d" % (
            len(issues), sum(i["status"] == "known" for i in issues), len(new),
            sum(i["status"] == "info" for i in issues), len(resolved)),
        "",
        "## OMOP sets",
        "",
        "| Project | Set | v1.1 schema pass | Built |",
        "| --- | --- | --- | --- |",
    ]
    for (proj, set_name), (passed, built) in sorted(sets.items()):
        lines.append("| `%s` | %s | %d/15 | %d/15 |" % (proj, set_name, passed, built))
    lines += ["", "## Issues", "", "| Issue | Status | Plan | Detail |", "| --- | --- | --- | --- |"]
    for i in issues:
        lines.append("| `%s` | %s | %s | %s |" % (i["id"], i["status"], i["plan"], i["detail"].replace("|", "/")))
    if resolved:
        lines += ["", "## Baseline entries to delete (fixed)", ""] + ["- `%s`" % r for r in resolved]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="query DSS with dku and rewrite the snapshot first")
    mode.add_argument("--reprobe", action="store_true", help="re-run only the built/row-count probes against DSS")
    mode.add_argument("--check", action="store_true", help="offline: fail if .index/ is stale or the baseline moved")
    args = ap.parse_args()

    reg = load_registry()
    baseline = load_baseline()
    if args.refresh:
        os.makedirs(INDEX, exist_ok=True)
        refresh(reg)
    elif args.reprobe:
        reprobe(reg)
    if not os.path.exists(SNAP):
        raise SystemExit("no snapshot: run python3 tools/build_index.py --refresh")
    with open(SNAP) as fh:
        raw = fh.read()
    leaked = redact(raw) != raw
    snap = json.loads(redact(raw))
    missing = sorted({p["key"] for p in reg["projects"]} - set(snap["projects"]))
    if missing:
        raise SystemExit("snapshot predates registry entries %s: run --refresh" % ", ".join(missing))

    out, data = render(reg, snap, baseline)

    if args.check:
        failures = []
        if leaked:
            failures.append(".index/dss_snapshot.json holds URL credentials: run python3 tools/build_index.py")
        for fname, text in out.items():
            path = os.path.join(INDEX, fname)
            if not os.path.exists(path) or open(path).read() != text:
                failures.append(".index/%s is stale: run python3 tools/build_index.py" % fname)
        current = {i["id"] for i in data["issues"] if gating(i["id"])}
        for i in data["issues"]:
            if i["status"] == "NEW":
                failures.append("NEW issue %s: %s" % (i["id"], i["detail"]))
        for gone in sorted(set(baseline) - current):
            failures.append("fixed: delete %s from registry/known_issues.json" % gone)
        if failures:
            print("\n".join(failures), file=sys.stderr)
            return 1
        info = len(data["issues"]) - len(current)
        print("index current; %d known issues, none new; %d informational" % (len(current), info))
        return 0

    if leaked:
        with open(SNAP, "w") as fh:
            fh.write(redact(raw))
    for fname, text in out.items():
        with open(os.path.join(INDEX, fname), "w") as fh:
            fh.write(text)
    new = sum(i["status"] == "NEW" for i in data["issues"])
    print("wrote %d files to .index/; %d issues (%d NEW)" % (len(out), len(data["issues"]), new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
