#!/usr/bin/env python3
"""Generate .index/ for the RWD/RWE suite: one place that says which project is canonical, whether
it is built, whether it passes the v1.1 schema check, and whether its cross-project inputs exist.

WHY THIS EXISTS. The 2026-09-23 audit answered those questions with ad-hoc scripts that were not
kept. Each failure it found (unbuilt Snowflake tables, a prep project that no longer exists, dropped
tables still shared into DEMO_SF_RWE) was invisible in DSS until someone went looking. This tool
makes them rows in a committed table, so a regression shows up in review and in CI.

MODES.
    python3 tools/build_index.py --refresh   # hits DSS, rewrites .index/dss_snapshot.json
    python3 tools/build_index.py --reprobe   # hits DSS for the built/row-count probes only
    python3 tools/build_index.py --refresh --project KEY [--project KEY2]
                                             # re-fetch only KEY and the projects it depends on
    python3 tools/build_index.py             # offline: rebuilds every .index/*.tsv from the snapshot
    python3 tools/build_index.py --check     # offline: fails if a TSV is stale or the issue baseline moved

HOW DSS IS READ. --refresh and --reprobe talk to DSS through one in-process dataikuapi client built
by the dku CLI's own factory (dku_cli.client.get_client), so they use the same profile and API key
as `dku`. The CLI lives in its own environment (a uv tool); when this interpreter cannot import it,
the script re-runs itself under the interpreter named on the `dku` launcher's shebang line. If that
fails too, or BUILD_INDEX_DKU=cli is set, every call goes through a `dku` subprocess instead (slow:
~0.8 s of CLI start-up per call). The offline modes never touch either.

PARTIAL REFRESH. --project KEY (repeatable) re-fetches or re-probes KEY plus everything it depends
on, transitively: registry `upstream`, the projects its shared-in datasets come from, and its
data_preparation_project_key targets (both variable scopes). Every other project's snapshot entry is
kept as it was. Each entry carries its own fetched_at (definitions) and probed_at (probes), so a
partial refresh leaves a mixed snapshot, and SUMMARY.md says so. The `project list` existence check
always covers every registered key: a project that disappeared is marked gone, and one that appeared
since the last fetch is fetched as well.

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
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading

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
WORKERS = 12          # concurrent dataset reads (definitions over the CLI, probes)
PROJECT_WORKERS = 4   # projects fetched at the same time
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

REEXEC_ENV = "BUILD_INDEX_REEXEC"
_API = None  # an InProcessDku once connect() succeeds; None means the subprocess path


def dku(args, timeout=TIMEOUT):
    """Run a dku command with JSON output. Returns (ok, parsed_or_error_text).

    In-process when connect() found the dku CLI's client; the same argument lists, the same JSON
    and (as far as the CLI's error rendering goes) the same error text as the subprocess."""
    if _API is not None:
        return _API.call(args, timeout)
    return dku_subprocess(args, timeout)


def dku_subprocess(args, timeout=TIMEOUT):
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


class InProcessDku(object):
    """The handful of dku commands this script uses, run on one shared dataikuapi client.

    Each method mirrors the CLI command of the same name (dku_cli/commands/*.py), reusing the CLI's
    own helpers where it has non-trivial logic (SQL table resolution, metric reading, wiki version
    tags). Results are passed through json the way `dku --format json` prints them, and errors are
    rendered by the CLI's own handle_api_error into a per-thread console, so the probe error text in
    the snapshot is the text the subprocess would have printed."""

    def __init__(self):
        import requests.adapters
        import rich.console
        import dku_cli.output as cli_output
        from dku_cli.client import get_client

        self._console_cls = rich.console.Console
        self._local = threading.local()
        cli_output._quiet = True  # no stale-metric hints or large-dataset warnings, as with --format json
        cli_output.err_console = _ThreadConsole(self)
        self.client = get_client()
        session = self.client._session
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4 * WORKERS * PROJECT_WORKERS)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        request = session.request

        def request_with_timeout(method, url, **kw):
            kw.setdefault("timeout", self._local.__dict__.get("timeout", TIMEOUT))
            return request(method, url, **kw)

        session.request = request_with_timeout

    def console(self):
        c = getattr(self._local, "console", None)
        if c is None:
            c = self._local.console = self._console_cls(file=io.StringIO(), soft_wrap=True, emoji=False,
                                                         color_system=None)
        return c

    def call(self, args, timeout=TIMEOUT):
        import requests.exceptions
        from dku_cli.errors import handle_api_error

        self._local.console = None
        self._local.timeout = timeout
        try:
            out = self.dispatch(list(args))
        except SystemExit:  # exit_with_error from a CLI helper
            return False, self.error_text()
        except requests.exceptions.Timeout:
            return False, "timeout after %ds" % timeout
        except Exception as e:  # noqa: BLE001 -- the CLI turns every API error into text, so do we
            try:
                handle_api_error(e, project_key=self._local.__dict__.get("project_key"))
            except SystemExit:
                pass
            return False, self.error_text()
        return True, out

    def error_text(self):
        c = getattr(self._local, "console", None)
        return " ".join(c.file.getvalue().split()) if c is not None else ""

    def dispatch(self, args):
        cmd, rest = tuple(args[:2]), args[2:]
        opts, pos = {}, []
        i = 0
        while i < len(rest):
            if rest[i].startswith("-"):
                opts[rest[i]] = rest[i + 1]
                i += 2
            else:
                pos.append(rest[i])
                i += 1
        self._local.project_key = None
        handler = {
            ("project", "list"): self.project_list,
            ("project", "inspect"): self.project_inspect,
            ("project", "get-variables"): self.project_get_variables,
            ("library", "read"): self.library_read,
            ("dataset", "get-definition"): self.dataset_get_definition,
            ("dataset", "query"): self.dataset_query,
            ("dataset", "info"): self.dataset_info,
            ("dataset", "head"): self.dataset_head,
            ("wiki", "get"): self.wiki_get,
        }.get(cmd)
        if handler is None:
            raise ValueError("build_index: no in-process dku %s" % " ".join(cmd))
        out = handler(pos, opts)
        if isinstance(out, (bytes, str)):
            text = out.decode("utf-8") if isinstance(out, bytes) else out
            try:
                return json.loads(text) if text.strip() else None
            except ValueError:
                return text
        return json.loads(json.dumps(out, default=str))  # what `dku --format json` prints

    def project(self, opts, pos=()):
        key = opts.get("-P") or (pos[0] if pos else None)
        self._local.project_key = key
        return key, self.client.get_project(key)

    def project_list(self, pos, opts):
        return [{"projectKey": p["projectKey"], "name": p.get("name", p["projectKey"])}
                for p in self.client.list_projects()]

    def project_inspect(self, pos, opts):
        """The parts of `dku project inspect` fetch_project reads, plus the full dataset definitions
        (DSS's dataset list already carries them, which saves one call per dataset)."""
        key, proj = self.project(opts, pos)
        meta = proj.get_metadata()
        items = [getattr(d, "_data", d) for d in proj.list_datasets()]
        try:
            graph = proj.get_flow().get_graph()
            downstream = set()
            for node in graph.nodes.values():
                downstream.update(node.get("successors", []))
            sources = [nid for nid, node in graph.nodes.items()
                       if nid not in downstream and node.get("type") == "COMPUTABLE_DATASET"]
        except Exception:  # noqa: BLE001 -- the CLI reports no sources when the flow cannot be read
            sources = []
        try:
            wiki = [{"id": a.article_id, "title": a.get_data().get_name()}
                    for a in proj.get_wiki().list_articles()]
        except Exception:  # noqa: BLE001 -- as the CLI: a wiki that cannot be read lists nothing
            wiki = []
        return {"key": key, "name": meta.get("label", key),
                "datasets": [{"name": d.get("name", d.get("id", "")), "type": d.get("type", "")} for d in items],
                "flow_sources": sources, "wiki_articles": wiki,
                "definitions": {d.get("name"): d for d in items}}

    def project_get_variables(self, pos, opts):
        return self.project(opts, pos)[1].get_variables()

    def library_read(self, pos, opts):
        return self.project(opts)[1].get_library().get_file(pos[0]).read(as_type="bytes")

    def dataset_get_definition(self, pos, opts):
        return self.project(opts)[1].get_dataset(pos[0]).get_definition()

    def dataset_query(self, pos, opts):
        from dku_cli.commands.dataset import _resolve_sql_table, _table_template_variables
        from dku_cli.errors import exit_with_error

        key, proj = self.project(opts)
        name = pos[0]
        ds_def = proj.get_dataset(name).get_definition()
        resolved = _resolve_sql_table(ds_def, key, _table_template_variables(self.client, key, ds_def))
        if resolved is None:
            exit_with_error("'%s' is not a SQL-table-backed dataset (type '%s') — cannot run SQL against it."
                            % (name, ds_def.get("type")))
        connection, table = resolved
        result = self.client.sql_query(opts["--sql"].replace("{{table}}", table), connection=connection)
        columns = [c["name"] for c in result.get_schema()]
        return [dict(zip(columns, row)) for row in result.iter_rows()]

    def dataset_info(self, pos, opts):
        from dku_cli.commands.dataset import _gather_dataset_info

        key, proj = self.project(opts)
        return _gather_dataset_info(proj.get_dataset(pos[0]), pos[0], key, recompute=False, fmt="json")[1]

    def dataset_head(self, pos, opts):
        """`dku dataset head --limit N`: the first N rows, then the stream is closed."""
        from dku_cli.errors import exit_with_error

        key, proj = self.project(opts)
        name = pos[0]
        ds = proj.get_dataset(name)
        columns = [c.get("name", "col_%d" % i)
                   for i, c in enumerate(ds.get_definition().get("schema", {}).get("columns", []))]
        if not columns:
            exit_with_error(
                "Dataset '%s' has no columns — it likely has never been built." % name,
                details=["An unbuilt managed dataset has zero columns; `head` cannot show data.",
                         "  dku dataset build %s -P %s --type RECURSIVE_BUILD --auto-update-schema --wait" % (name, key),
                         "  dku dataset head %s -P %s -n 10" % (name, key)])
        limit = int(opts.get("--limit", 10))
        rows = []
        it = ds.iter_rows()
        try:
            for row in it:
                if len(rows) >= limit:
                    break
                rows.append(dict(zip(columns, row)))
        finally:
            it.close()
        return rows

    def wiki_get(self, pos, opts):
        from dku_cli.commands._wiki_io import _modified_by, _modified_on, _version_tag

        data = self.project(opts)[1].get_wiki().get_article(pos[0]).get_data()
        tag = _version_tag(data)
        return {"id": pos[0], "name": data.get_name(), "body": data.get_body(),
                "version": tag.get("versionNumber"), "lastModifiedBy": _modified_by(tag),
                "lastModifiedOn": _modified_on(tag)}


class _ThreadConsole(object):
    """Stands in for the CLI's stderr console: each thread renders into its own buffer."""

    def __init__(self, owner):
        self._owner = owner

    def __getattr__(self, name):
        return getattr(self._owner.console(), name)


def dku_launcher_python():
    """The interpreter on the `dku` launcher's shebang line (a uv or pipx tool environment), or None."""
    exe = shutil.which("dku")
    if not exe:
        return None
    try:
        with open(exe, "rb") as fh:
            first = fh.readline().decode("utf-8", "replace")
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    interp = first[2:].strip().split()[0] if first[2:].strip() else ""
    return interp if os.path.isabs(interp) and os.access(interp, os.X_OK) else None


def connect():
    """Pick how DSS is read: in-process if the dku CLI's client can be imported here; else re-run
    this script under the dku launcher's interpreter; else the subprocess path."""
    global _API
    if os.environ.get("BUILD_INDEX_DKU") == "cli":
        print("BUILD_INDEX_DKU=cli: reading DSS through dku subprocesses", file=sys.stderr)
        return
    try:
        import dku_cli.client  # noqa: F401
    except ImportError:
        interp = dku_launcher_python()
        if interp and not os.environ.get(REEXEC_ENV) and \
                os.path.realpath(interp) != os.path.realpath(sys.executable):
            sys.stdout.flush()
            sys.stderr.flush()
            env = dict(os.environ)
            env[REEXEC_ENV] = "1"
            os.execve(interp, [interp, os.path.abspath(__file__)] + sys.argv[1:], env)
        print("dku_cli is not importable here; reading DSS through dku subprocesses (slow)", file=sys.stderr)
        return
    try:
        _API = InProcessDku()
    except Exception as e:  # noqa: BLE001 -- any failure means the subprocess path, which reports its own errors
        print("in-process dku client unavailable (%s); using dku subprocesses" % e, file=sys.stderr)


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


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def fetch_project(key):
    fetched_at = now_utc()
    ok, insp = dku(["project", "inspect", key])
    if not ok:
        return {"exists": False, "error": short_error(insp), "fetched_at": fetched_at}
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
    listed = insp.get("definitions") or {}  # in-process inspect returns them; the CLI does not

    def definition(name):
        if name in listed:
            ok, d = True, listed[name]
        else:
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

    if all(n in listed for n in names):
        datasets = dict(map(definition, names))
    else:
        with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
            datasets = dict(pool.map(definition, names))
    return {
        "exists": True,
        "fetched_at": fetched_at,
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


def dependencies(reg, projects, key):
    """Projects KEY reads from: registry upstream, its prep project in either variable scope, and
    the projects its shared-in datasets come from (as far as the snapshot entry knows)."""
    deps = set()
    for p in reg["projects"]:
        if p["key"] == key:
            deps.update(p["upstream"])
    proj = projects.get(key) or {}
    if proj.get("exists"):
        for scope in ("standard", "local"):
            ref = proj["variables"][scope].get("data_preparation_project_key")
            if ref:
                deps.add(ref)
        deps.update(s.partition(".")[0] for s in foreign_sources(proj))
    deps.discard(key)
    return deps


def closure(reg, projects, keys):
    """KEYS plus everything they depend on, transitively."""
    seen, stack = set(), list(keys)
    while stack:
        key = stack.pop()
        if key not in seen:
            seen.add(key)
            stack.extend(dependencies(reg, projects, key) - seen)
    return seen


def normalize_snapshot(snap):
    """Give a snapshot from before per-project timestamps its old refreshed_at on every entry."""
    legacy = snap.pop("refreshed_at", None)
    if legacy:
        for proj in snap["projects"].values():
            proj.setdefault("fetched_at", legacy)
            if proj.get("exists"):
                proj.setdefault("probed_at", legacy)
    return snap


def load_snapshot():
    with open(SNAP) as fh:
        return normalize_snapshot(json.load(fh))


def write_snapshot(snap):
    with open(SNAP, "w") as fh:
        fh.write(redact(json.dumps(snap, indent=1, sort_keys=True)) + "\n")


def merge_projects(reg, old, fetched, all_keys, now):
    """The snapshot's project entries after a refresh: freshly fetched entries win, a registered key
    missing from DSS is marked gone (the existence check covers every key on every run), and every
    other entry is kept as it was. Keys no longer registered are dropped, as a full refresh would."""
    merged = {}
    for p in reg["projects"]:
        key = p["key"]
        if key in fetched:
            merged[key] = fetched[key]
        elif key not in all_keys:
            merged[key] = {"exists": False, "error": "not on DSS", "fetched_at": now}
        elif key in old:
            merged[key] = old[key]
        else:
            raise ValueError("%s is on DSS but was neither fetched nor in the snapshot" % key)
    return merged


def must_fetch(reg, old, all_keys):
    """Registered keys on DSS whose snapshot entry has no definitions: new on DSS since the last fetch."""
    return {p["key"] for p in reg["projects"]
            if p["key"] in all_keys and not (old.get(p["key"]) or {}).get("exists")}


def external_projects(projects, registered, all_keys):
    """Keys referenced from DSS (prep project variables, flow sources) that are not registered."""
    referenced = set()
    for proj in projects.values():
        if not proj.get("exists"):
            continue
        for scope in ("standard", "local"):
            ref = proj["variables"][scope].get("data_preparation_project_key")
            if ref:
                referenced.add(ref)
        referenced.update(s.partition(".")[0] for s in foreign_sources(proj))
    return {k: (k in all_keys) for k in sorted(referenced - set(registered))}


def check_only(reg, only):
    registered = {p["key"] for p in reg["projects"]}
    unknown = sorted(set(only) - registered)
    if unknown:
        raise SystemExit("--project %s: not in registry/projects.json" % ", ".join(unknown))


def reprobe(reg, only=None):
    """Re-run only the probes, keeping the snapshot's project definitions (minutes, not a full refresh)."""
    snap = load_snapshot()
    scope = None
    if only:
        check_only(reg, only)
        scope = closure(reg, snap["projects"], only) & set(snap["projects"])
        print("re-probing %s" % ", ".join(sorted(scope)), file=sys.stderr)
    write_probes(reg, snap, scope)


def write_probes(reg, snap, scope=None):
    """Probe the datasets of the projects in SCOPE (all when None); other projects keep their probes.
    Targets are still chosen from the whole snapshot, so a consumer outside SCOPE that reads a
    dataset inside it gets that dataset probed."""
    projects = snap["projects"]
    scope = set(projects) if scope is None else set(scope)
    for key in scope:
        for ds in projects[key].get("datasets", {}).values():
            ds.pop("probe", None)
    targets = [t for t in probe_targets(reg, projects) if t[0] in scope]
    print("probing %d datasets" % len(targets), file=sys.stderr)

    def run(t):
        project, name = t
        return t, probe(project, name, projects[project]["datasets"][name].get("type"))

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for (project, name), result in pool.map(run, targets):
            projects[project]["datasets"][name]["probe"] = result
    now = now_utc()
    for key in scope:
        if projects[key].get("exists"):
            projects[key]["probed_at"] = now
    write_snapshot(snap)
    print("wrote %s (%d projects, %d probes)" % (os.path.relpath(SNAP, ROOT), len(projects), len(targets)))


def fetch_all(keys):
    """fetch_project for each key, PROJECT_WORKERS at a time."""
    def run(key):
        print("fetching %s" % key, file=sys.stderr)
        return key, fetch_project(key)

    with concurrent.futures.ThreadPoolExecutor(PROJECT_WORKERS) as pool:
        return dict(pool.map(run, sorted(keys)))


def refresh(reg, only=None):
    ok, listing = dku(["project", "list", "--fields", "projectKey,name"])
    if not ok:
        raise SystemExit("dku project list failed: " + listing)
    all_keys = {p["projectKey"] for p in listing}
    pattern = re.compile(reg["discovery_pattern"])
    discovered = sorted(k for k in all_keys if pattern.search(k))
    registered = {p["key"] for p in reg["projects"]}

    if only:
        check_only(reg, only)
        if not os.path.exists(SNAP):
            raise SystemExit("--project needs an existing snapshot: run a full --refresh first")
        old = load_snapshot()["projects"]
        appeared = must_fetch(reg, old, all_keys)
        if appeared:
            print("on DSS but not in the snapshot, fetching too: %s" % ", ".join(sorted(appeared)), file=sys.stderr)
        fetched, wanted = {}, closure(reg, old, only) | appeared
        # Fetched definitions can name dependencies the snapshot did not know (a new share, a
        # repointed prep key): recompute the closure on the merged view until it stops growing.
        while True:
            todo = (wanted & registered & all_keys) - set(fetched)
            if not todo:
                break
            fetched.update(fetch_all(todo))
            view = dict(old)
            view.update(fetched)
            wanted |= closure(reg, view, only)
        scope = set(fetched)
        projects = merge_projects(reg, old, fetched, all_keys, now_utc())
    else:
        scope = None
        projects = merge_projects(reg, {}, fetch_all(registered & all_keys), all_keys, now_utc())

    snap = {"dss_project_count": len(all_keys), "discovered": discovered,
            "external_projects": external_projects(projects, registered, all_keys), "projects": projects}
    write_probes(reg, snap, scope)


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
    (".index/dss_snapshot.json", "tools/build_index.py --refresh", "per project: fetched_at (definitions) and probed_at (probes) on each entry; --project refreshes a subset, SUMMARY.md gives the oldest","raw DSS state: variables, git references, flow sources, dataset schemas, probes"),
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


def snapshot_age(snap):
    """'the snapshot fetched T', or, after a partial refresh, the oldest project fetch and the newest."""
    times = sorted((p.get("fetched_at") or "unknown", k) for k, p in snap["projects"].items())
    if not times:
        return "an empty snapshot"
    (oldest, oldest_key), (newest, _) = times[0], times[-1]
    if oldest == newest:
        return "the snapshot fetched %s" % oldest
    stale = [k for t, k in times if t == oldest]
    names = ", ".join("`%s`" % k for k in stale[:3]) + (" and %d more" % (len(stale) - 3) if len(stale) > 3 else "")
    return "a mixed snapshot: projects fetched between %s (oldest: %s) and %s" % (oldest, names, newest)


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
        "> Generated by `tools/build_index.py` from %s. Do not edit." % snapshot_age(snap),
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
    ap.add_argument("--project", action="append", metavar="KEY",
                    help="with --refresh or --reprobe: only KEY and the projects it depends on (repeatable)")
    args = ap.parse_args()
    if args.project and not (args.refresh or args.reprobe):
        ap.error("--project needs --refresh or --reprobe")

    reg = load_registry()
    baseline = load_baseline()
    if args.refresh or args.reprobe:
        connect()
        started = datetime.datetime.now()
    if args.refresh:
        os.makedirs(INDEX, exist_ok=True)
        refresh(reg, args.project)
    elif args.reprobe:
        reprobe(reg, args.project)
    if args.refresh or args.reprobe:
        print("DSS read in %.0fs (%s)" % ((datetime.datetime.now() - started).total_seconds(),
                                         "in-process" if _API is not None else "dku subprocesses"), file=sys.stderr)
    if not os.path.exists(SNAP):
        raise SystemExit("no snapshot: run python3 tools/build_index.py --refresh")
    with open(SNAP) as fh:
        raw = fh.read()
    leaked = redact(raw) != raw
    snap = normalize_snapshot(json.loads(redact(raw)))
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
