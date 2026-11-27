#!/usr/bin/env python3
"""Build the solution's Project Setup (app manifest) from the repo.

Offline: reads a manifest fetched with `dku app-designer get -P <KEY> -o json` and applies the repo's
layout to it. Applying the output to DSS is a separate, approved step:
`dku app-designer set-definition -P <KEY> -d @<out.json>`.

    python3 tools/app_manifest.py manifest.json --out patched.json   # write the patched manifest
    python3 tools/app_manifest.py manifest.json --check              # exit 1 if anything differs,
                                                                     # or a Setup key is outside the
                                                                     # variable contract

What the repo owns (solution-revision-plan.md, R1 and R2):
- the Python of the tiles in PYTHON_TILES, found by what they are, not by position;
- the whole of the custom tiles in CUSTOM_TILES (Python, HTML and JS in app_manifest/tiles/); the
  batch tiles in BATCH_TILES share one HTML and JS template, `batch_tile.template.{html,js}`;
- the "Cohort Script Table Naming" section and the section texts of the cohort ingestion;
- what LAYOUT removes, renames and relabels.

A tile's Python process does not see the project library (DSS 15.2, 2026-11-05: wrappers that
import solution.* fail with "Failed to get test result for ui"). So every `from solution.<module>
import ...` line in a wrapper, and in the modules it pulls in, is replaced by that module's source,
once. --import writes the bare wrappers instead, for re-testing that on a later DSS version.
"""
import argparse
import ast
import copy
import importlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES_DIR = os.path.join(ROOT, "app_manifest", "tiles")
SOLUTION_IMPORT = re.compile(r"^from (solution(?:\.\w+)+) import .*$", re.M)

# Existing tiles whose Python is the repo's wrapper: (wrapper file, how the tile is recognised).
PYTHON_TILES = [
    ("section2_tile0.py", {"module": "input_data_source_project_selectbox"}),
    ("section2_tile3.py", {"first_param": "person"}),
    ("section2_tile5.py", {"first_param": "concept"}),
]

# Tiles the repo defines entirely: module -> prompt, help, and where the tile goes.
# "section_of" places it in the section holding that scenario's button ("before" it, or at the end);
# "own_section" places it alone in that section, created after the section titled "after".
CUSTOM_TILES = {
    "table_naming": {
        "prompt": "How do your cohort scripts name OMOP tables?",
        "help": "Saved as you choose. Applies to every batch registered afterwards.",
        "own_section": "naming"},
    "register_cohorts": {
        "prompt": "Register cohorts",
        "help": "One row per uploaded script; scripts uploaded above appear here as you upload them. "
                "Tick In batch for the scripts to register, then click Register batch. Refresh list "
                "picks up scripts the automatic refresh missed.",
        "section_of": "CREATECOHORTSCRIPTS", "before": "CREATECOHORTSCRIPTS"},
    "built_cohorts": {
        "prompt": "Built cohorts",
        "help": "Every written cohort with its latest build.",
        "section_of": "WRITECOHORTTODATASETS", "before": None},
    "characterization_batch": {
        "prompt": "Characterization batch",
        "help": "One row per cohort whose latest build succeeded. New cohorts are ticked In batch. "
                "A characterized cohort is redone only with In batch and Replace. Click Save batch, "
                "then Characterize cohorts.",
        "own_section": "characterization"},
    "extraction_batch": {
        "prompt": "Extraction batch",
        "help": "One row per cohort whose latest build succeeded. Nothing is ticked: tick In batch for the "
                "cohorts a study needs. An extracted cohort is redone only with In batch and Replace. Click "
                "Save batch, then Extract patient covariates.",
        "own_section": "extraction"},
}

# Batch tiles built from one HTML and JS template (step 4 part 5 anticipated it; R9 stage 3). Each
# `[[key]]` in the template is replaced by the tile's value; `labels` comes from the status labels
# of its solution module, so the tile and the library name a status the same way.
BATCH_TEMPLATE = "batch_tile.template"
BATCH_TILES = {
    "characterization_batch": {
        "labels_from": ("solution.setup.characterization", "STATUS_LABELS"),
        "controller": "CharacterizationBatchController", "css_class": "rwd-characterization-batch",
        "done_header": "Characterized", "done_field": "characterized", "done_noun": "characterization",
        "done_ids": "characterizedIds", "done_ids_key": "characterized_ids", "is_done": "isCharacterized",
        "redo_verb": "Characterize", "run_button": "Characterize cohorts",
        "population_title": "{{row.population ? 'Characterized automatically when it has none yet or the data "
                            "was imported again' : ''}}",
        "population_note": " The population is characterized in the same run."},
    "extraction_batch": {
        "labels_from": ("solution.setup.extraction", "EXTRACTION_STATUS_LABELS"),
        "controller": "ExtractionBatchController", "css_class": "rwd-extraction-batch",
        "done_header": "Extracted", "done_field": "extracted", "done_noun": "extraction",
        "done_ids": "extractedIds", "done_ids_key": "extracted_ids", "is_done": "isExtracted",
        "redo_verb": "Extract", "run_button": "Extract patient covariates",
        "population_title": "", "population_note": ""},
}
TEMPLATE_KEY = re.compile(r"\[\[(\w+)\]\]")

COHORT_INGESTION = "**Cohort Ingestion**"

# A tile's HTML runs in the Setup page, whose URL names the project (/projects/KEY/...), so the
# link is built there: the manifest stays free of the project key and works in any copy.
LINK_TILE_HTML = """<div class="control-group">
    <label class="control-label"></label>
    <div class="controls">
        <a href="#" target="_blank" rel="noopener"
           onclick="var m = window.location.pathname.match(/\\/projects\\/([^\\/]+)/); if (m) { this.href = '/projects/' + m[1] + '/%s'; }">%s</a>
        <span class="muted">(opens in a new tab)</span>
    </div>
</div>"""


def link_tile(prompt, path, text):
    """A Setup tile holding one link that opens `path` of this project in a new tab."""
    return {"type": "PROJECT_VARIABLES_EDIT", "behavior": "INLINE_AUTO_SAVE", "params": [],
            "prompt": prompt, "html": LINK_TILE_HTML % (path, text)}
CHARACTERIZE_SCENARIO = "Characterize_Cohorts"
EXTRACT_SCENARIO = "Extract_Patient_Covariates"
OWN_SECTIONS = {
    "naming": {
        "after": COHORT_INGESTION,
        "sectionTitle": "Cohort Script Table Naming",
        "sectionText": "Set this once, before registering cohort scripts. Each script names the OMOP "
                       "tables it reads, and the solution replaces those names with this project's "
                       "tables, so it needs to know how your scripts write them. Pick the option that "
                       "matches your scripts below. If you change it later, register the affected "
                       "scripts again with Replace.",
    },
    # R3, decision 14: after "Build Cohorts", with its own button.
    "characterization": {
        "after": "Build Cohorts",
        "sectionTitle": "Characterize Cohorts",
        "sectionText": "Describes each built cohort with the FeatureExtraction covariates (demographics, "
                       "Charlson index, condition and drug groups, visits) and compares it with the "
                       "population: every person with at least 365 days of observation.\n\n"
                       "1. In **Characterization batch**, new cohorts are ticked *In batch*. Click "
                       "**Save batch**.\n"
                       "2. Click **Characterize cohorts**. One run covers the whole batch, and the "
                       "population when it has none yet or the data was imported again.\n\n"
                       "Existing results are kept: a characterized cohort is redone only when you tick "
                       "*In batch* and *Replace*. A rebuilt cohort shows as *Rebuilt since "
                       "characterized* until you do.",
        "extra_tiles": [
            {"type": "SCENARIO_RUN", "scenarioId": CHARACTERIZE_SCENARIO, "prompt": "Characterize cohorts"},
            link_tile("Review Characterization Log", "datasets/characterization_log/explore/",
                      "Explore the characterization log dataset"),
        ],
    },
    # R9 decision 9: after "Characterize Cohorts", under its own part heading.
    "extraction": {
        "after": "Characterize Cohorts",
        "sectionTitle": "Extract Patient Covariates",
        "sectionText": "Writes the covariates of every entry of the chosen cohorts, for a study downstream "
                       "(propensity models, outcome analyses): the same FeatureExtraction presets as the "
                       "characterization, one row per cohort entry and covariate. Each preset has its own "
                       "dataset, **patient_cov_**<preset>, and **patient_cov_ref** names every covariate "
                       "and the dataset that holds it.\n\n"
                       "1. In **Extraction batch**, tick *In batch* for the cohorts a study needs. Click "
                       "**Save batch**.\n"
                       "2. Click **Extract patient covariates**. One run covers the whole batch.\n\n"
                       "Extracts are kept until you redo them: an extracted cohort is redone only when you "
                       "tick *In batch* and *Replace*. Cohorts are extracted whole, with no minimum cell "
                       "count, so the datasets stay internal.",
        "extra_tiles": [
            {"type": "SCENARIO_RUN", "scenarioId": EXTRACT_SCENARIO, "prompt": "Extract patient covariates"},
            link_tile("Review Extraction Log", "datasets/patient_cov_log/explore/",
                      "Explore the patient covariate log dataset"),
        ],
    },
}

# Part headings: a section with a bold title, a text and no tiles, like **Cohort Ingestion**. Each is
# created right before the section titled "before", or its text kept up to date.
COHORT_CHARACTERIZATION = "**Cohort Characterization**"
HEADINGS = [
    {"sectionTitle": COHORT_CHARACTERIZATION, "before": "Characterize Cohorts",
     "sectionText": "A stand-alone part, run whenever cohorts have been built: describe each built cohort "
                    "with FeatureExtraction covariates and compare it with the population. It reads the "
                    "**cohort** table and never changes it, and existing results are kept unless you ask "
                    "for a cohort to be redone. Run **Characterize Cohorts** after one or several "
                    "batches of **Cohort Ingestion**."},
    {"sectionTitle": "**Patient Covariates**", "before": "Extract Patient Covariates",
     "sectionText": "A stand-alone part, run on request for the cohorts a study needs: extract the covariates "
                    "of each cohort entry, from the same presets as **Cohort Characterization**, into datasets "
                    "an analysis can use. It reads the **cohort** table and changes neither it nor the "
                    "characterization's results. Run **Extract Patient Covariates** after **Build Cohorts**."},
]

LAYOUT = {
    # R1: the custom table mapping goes (its section holds this scenario's button). R3, part 7: the
    # old dashboard's section goes with it, and its heading below.
    "remove_sections_with_scenario": ["CHECKOMOPTABLEVARIABLESMAPPING", "BUILDCOHORTDASHBOARD"],
    "remove_sections_titled": ["**Dashboard Creation**"],
    # R2: the metadata CSV upload goes.
    "remove_tile_types": ["UPLOAD_DATASET_SET_FILE"],
    # R1, first layout: the naming parameters sat in the OMOP section. Now a custom tile.
    "remove_tiles_with_first_param": ["cohort_script_table_naming"],
    "scenario_prompts": {"CREATECOHORTSCRIPTS": "Write batch to cohort definition",
                         "WRITECOHORTTODATASETS": "Build cohorts"},
    # Links that open in a new tab, each in the tile it was in. The folder tile was a
    # MANAGED_FOLDER_LINK, which opens in the same tab. Found by prompt, or by folder for that one.
    "link_tiles": [
        ({"type": "MANAGED_FOLDER_LINK", "folderId": "lMM00YKr"},
         link_tile("View written scripts", "managedfolder/lMM00YKr/view/", "Written Scripts folder")),
        ({}, link_tile("Review Cohort", "datasets/cohort/explore/", "Explore the cohort dataset")),
        ({}, link_tile("Review Cohort Definition", "datasets/cohort_definition/explore/",
                       "Explore the cohort definition dataset")),
        ({}, link_tile("Review Cohort Log", "datasets/cohort_building_log/explore/",
                       "Explore the cohort building log dataset")),
    ],
    # Three verbs for the ingestion: upload scripts, register a batch, write it to cohort definition.
    # The cohorts are then built.
    "sections": {
        "CREATECOHORTSCRIPTS": {
            "sectionTitle": "Upload and Register Cohort SQL Scripts",
            "sectionText": "1. **Upload** your cohort SQL scripts, one cohort per script.\n"
                           "2. **Register** a batch in the table below. Each uploaded script gets a "
                           "cohort id, a name and a description, prefilled from its `-- name:` and "
                           "`-- description:` comments. Tick *In batch* for the scripts to register, "
                           "then click **Register batch**.\n"
                           "3. Click **Write batch to cohort definition**. The batch is checked against "
                           "the data, then written to the **cohort definition** dataset and its scripts "
                           "to the **Written Scripts** folder. If any check fails, nothing is written "
                           "and every problem is listed.\n\n"
                           "Then build the cohorts in **Build Cohorts**."},
        "WRITECOHORTTODATASETS": {
            "sectionTitle": "Build Cohorts",
            "sectionText": "Runs the scripts of the last written batch on the OMOP tables and fills "
                           "the **cohort** table. **Built cohorts** lists every written cohort with its "
                           "latest build."},
    },
    "sections_by_title": {
        "**Pipeline Configuration** (One-time)": {
            "sectionText": "A one-time configuration of the data pipeline: choose the project's "
                           "connections, then import the OMOP CDM tables from the source project. Run "
                           "**Connection Reconfiguration**, then **Connect OMOP Common Data Model "
                           "Standard Tables**. [Instructions](article:8)"},
        COHORT_INGESTION: {
            "sectionText": "Once the pipeline is configured, ingest cohorts from SQL scripts. Set "
                           "**Cohort Script Table Naming** once. Then, for each batch of scripts, run "
                           "**Upload and Register Cohort SQL Scripts** and **Build Cohorts**, in that "
                           "order. Then characterize the built cohorts in **Cohort Characterization**. "
                           "[Instructions](article:8)"},
    },
}


# ---------------------------------------------------------------- code

def module_path(module):
    return os.path.join(ROOT, *module.split(".")) + ".py"


def inline(code, seen):
    """Replace each `from solution.x import ...` line with module x's source (inlined itself), once."""
    def substitute(match):
        module = match.group(1)
        if module in seen:
            return ""
        seen.add(module)
        with open(module_path(module)) as fh:
            source = fh.read()
        return "# Inlined from %s\n" % os.path.relpath(module_path(module), ROOT) + inline(source, seen)
    return SOLUTION_IMPORT.sub(substitute, code)


def top_level_names(source):
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for leaf in (target.elts if isinstance(target, ast.Tuple) else [target]):
                    if isinstance(leaf, ast.Name):
                        names.add(leaf.id)
    return names


def name_clashes(modules):
    """Top-level names defined by more than one of the inlined modules, as "name (a, b)"."""
    owners = {}
    for module in modules:
        with open(module_path(module)) as fh:
            for name in top_level_names(fh.read()):
                owners.setdefault(name, []).append(module)
    return ["%s (%s)" % (n, ", ".join(m)) for n, m in sorted(owners.items()) if len(m) > 1]


def tile_code(fname, inline_library=True):
    with open(os.path.join(TILES_DIR, fname)) as fh:
        code = fh.read()
    if not inline_library:
        return code
    lines = code.split("\n")
    head = [line for line in lines if SOLUTION_IMPORT.match(line)]
    if not head or lines[:len(head)] != head:
        raise SystemExit("%s must start with its `from solution... import` lines" % fname)
    seen = set()
    library = "\n\n".join(inline(line, seen) for line in head)
    clashes = name_clashes(sorted(seen))
    if clashes:
        raise SystemExit("%s: inlined modules define the same top-level name, so one would silently replace "
                         "the other: %s" % (fname, "; ".join(clashes)))
    library = library.replace("# Inlined from ", "# Inlined from ", 1).replace(
        "\n", " by tools/app_manifest.py --inline\n", 1)
    return library + "\n\n# Tile wrapper (" + fname + ")\n" + "\n".join(lines[len(head):]).lstrip("\n")


def read_tile_file(name):
    module, ext = os.path.splitext(name)
    if module in BATCH_TILES:
        return batch_tile_file(module, ext)
    with open(os.path.join(TILES_DIR, name)) as fh:
        return fh.read()


def js_labels(labels):
    """The `$scope.labels` block of a batch tile, from a {status: label} dict, in its order."""
    lines = ",\n".join("        '%s': '%s'" % (k, v.replace("'", "\\'")) for k, v in labels.items())
    return "    $scope.labels = {\n%s\n    };\n" % lines


def batch_tile_file(module, ext):
    """A batch tile's HTML or JS: the shared template filled with its values."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    spec = dict(BATCH_TILES[module], module=module)
    source, attribute = spec.pop("labels_from")
    spec["labels"] = js_labels(getattr(importlib.import_module(source), attribute))
    with open(os.path.join(TILES_DIR, BATCH_TEMPLATE + ext)) as fh:
        template = fh.read()
    missing = sorted(set(TEMPLATE_KEY.findall(template)) - set(spec))
    if missing:
        raise SystemExit("%s%s: no value for %s" % (BATCH_TEMPLATE, ext, ", ".join(missing)))
    return TEMPLATE_KEY.sub(lambda m: spec[m.group(1)], template)


# ---------------------------------------------------------------- manifest

def sections(manifest):
    return manifest.setdefault("homepageSections", [])


def all_tiles(manifest):
    for i, section in enumerate(sections(manifest)):
        for j, tile in enumerate(section.get("tiles") or []):
            yield i, j, tile


def matches(tile, expect):
    if "module" in expect:
        return tile.get("module") == expect["module"]
    params = tile.get("params") or []
    return bool(params) and params[0].get("name") == expect["first_param"]


def find_tile(manifest, expect):
    found = [(i, j, t) for i, j, t in all_tiles(manifest) if matches(t, expect)]
    if len(found) != 1:
        raise SystemExit("expected one Setup tile matching %s, found %d" % (expect, len(found)))
    return found[0]


def section_of_scenario(manifest, scenario_id):
    for i, j, tile in all_tiles(manifest):
        if tile.get("type") == "SCENARIO_RUN" and tile.get("scenarioId") == scenario_id:
            return sections(manifest)[i]
    raise SystemExit("no Setup section has a button for scenario %s" % scenario_id)


def place(manifest, tile, where, changes, label):
    """Put `tile` in the section holding `where['section_of']`, before its button or at the end."""
    section = section_of_scenario(manifest, where["section_of"])
    tiles = section.setdefault("tiles", [])
    index = len(tiles)
    if where.get("before"):
        index = next(k for k, t in enumerate(tiles) if t.get("scenarioId") == where["before"])
    tiles.insert(index, tile)
    changes.append("added %s" % label)


def update(tile, values, changes, label):
    diff = sorted(k for k, v in values.items() if tile.get(k) != v)
    if diff:
        tile.update(values)
        changes.append("%s: %s" % (label, ", ".join(diff)))


def apply_layout(manifest, changes):
    for scenario_id in LAYOUT["remove_sections_with_scenario"]:
        kept = [s for s in sections(manifest)
                if not any(t.get("scenarioId") == scenario_id for t in s.get("tiles") or [])]
        if len(kept) != len(sections(manifest)):
            changes.append("removed the section of scenario %s" % scenario_id)
            manifest["homepageSections"] = kept
    for title in LAYOUT["remove_sections_titled"]:
        kept = [s for s in sections(manifest) if s.get("sectionTitle") != title]
        if len(kept) != len(sections(manifest)):
            changes.append("removed the section %s" % title)
            manifest["homepageSections"] = kept
    for section in sections(manifest):
        tiles = section.get("tiles") or []
        kept = [t for t in tiles if t.get("type") not in LAYOUT["remove_tile_types"]]
        if len(kept) != len(tiles):
            changes.append("removed %d tile(s) of type %s" % (len(tiles) - len(kept), "/".join(LAYOUT["remove_tile_types"])))
            section["tiles"] = kept
    for scenario_id, prompt in LAYOUT["scenario_prompts"].items():
        for _, _, tile in all_tiles(manifest):
            if tile.get("scenarioId") == scenario_id:
                update(tile, {"prompt": prompt}, changes, "button of %s" % scenario_id)
    for section in sections(manifest):
        tiles = section.get("tiles") or []
        kept = [t for t in tiles if not any(matches(t, {"first_param": p})
                                            for p in LAYOUT["remove_tiles_with_first_param"])]
        if len(kept) != len(tiles):
            changes.append("removed the tile with parameter %s" % "/".join(LAYOUT["remove_tiles_with_first_param"]))
            section["tiles"] = kept
    for old_tile, values in LAYOUT["link_tiles"]:
        found = [t for _, _, t in all_tiles(manifest)
                 if (old_tile and all(t.get(k) == v for k, v in old_tile.items()))
                 or (t.get("type") == values["type"] and t.get("prompt") == values["prompt"])]
        if len(found) != 1:
            raise SystemExit("expected one Setup tile %r, found %d" % (values["prompt"], len(found)))
        if found[0] != values:
            found[0].clear()
            found[0].update(values)
            changes.append("tile %r: a link that opens in a new tab" % values["prompt"])
    for scenario_id, values in LAYOUT["sections"].items():
        update(section_of_scenario(manifest, scenario_id), values, changes, "section of %s" % scenario_id)
    for title, values in LAYOUT["sections_by_title"].items():
        update(section_titled(manifest, title), values, changes, "section %s" % title)


def section_titled(manifest, title):
    found = [s for s in sections(manifest) if s.get("sectionTitle") == title]
    if len(found) != 1:
        raise SystemExit("expected one Setup section titled %r, found %d" % (title, len(found)))
    return found[0]


def apply_custom_tiles(manifest, changes, inline_library):
    for module, spec in CUSTOM_TILES.items():
        values = {"type": "PROJECT_VARIABLES_EDIT", "behavior": "INLINE_AUTO_SAVE", "module": module,
                  "params": [], "prompt": spec["prompt"], "help": spec["help"],
                  "python": tile_code(module + ".py", inline_library),
                  "html": read_tile_file(module + ".html"), "js": read_tile_file(module + ".js")}
        found = [(i, t) for i, _, t in all_tiles(manifest) if t.get("module") == module]
        if spec.get("own_section"):
            own = OWN_SECTIONS[spec["own_section"]]
            header = {k: own[k] for k in ("sectionTitle", "sectionText")}
            if not found:
                index = sections(manifest).index(section_titled(manifest, own["after"])) + 1
                tiles = [values] + [dict(t) for t in own.get("extra_tiles", [])]
                sections(manifest).insert(index, dict(header, tiles=tiles))
                changes.append("added section %s with tile %s" % (own["sectionTitle"], module))
                continue
            section = sections(manifest)[found[0][0]]
            update(section, header, changes, "section %s" % own["sectionTitle"])
            apply_extra_tiles(section, own.get("extra_tiles", []), changes)
        if not found:
            place(manifest, values, {"section_of": spec["section_of"], "before": spec["before"]}, changes,
                  "tile %s" % module)
        else:
            update(found[0][1], values, changes, "tile %s" % module)


def same_tile(tile, expect):
    if tile.get("type") != expect["type"]:
        return False
    if expect["type"] == "SCENARIO_RUN":
        return tile.get("scenarioId") == expect["scenarioId"]
    return tile.get("prompt") == expect.get("prompt")


def apply_extra_tiles(section, extra_tiles, changes):
    """Make the section hold each of `extra_tiles` (a button, a link), added at the end if missing."""
    tiles = section.setdefault("tiles", [])
    for expect in extra_tiles:
        found = [t for t in tiles if same_tile(t, expect)]
        if not found:
            tiles.append(dict(expect))
            changes.append("section %s: added %s" % (section.get("sectionTitle"),
                                                     expect.get("prompt") or expect.get("scenarioId")))
        else:
            update(found[0], expect, changes, "section %s tile %s" % (section.get("sectionTitle"),
                                                                       expect.get("prompt")))


def apply_headings(manifest, changes):
    for heading in HEADINGS:
        values = {k: heading[k] for k in ("sectionTitle", "sectionText")}
        found = [s for s in sections(manifest) if s.get("sectionTitle") == heading["sectionTitle"]]
        if found:
            update(found[0], values, changes, "section %s" % heading["sectionTitle"])
            continue
        index = sections(manifest).index(section_titled(manifest, heading["before"]))
        sections(manifest).insert(index, dict(values, tiles=[]))
        changes.append("added heading %s" % heading["sectionTitle"])


def apply_python_tiles(manifest, changes, inline_library):
    for fname, expect in PYTHON_TILES:
        i, j, tile = find_tile(manifest, expect)
        update(tile, {"python": tile_code(fname, inline_library)}, changes, "section %d tile %d (%s)" % (i, j, fname))


def apply(manifest, inline_library=True):
    """Bring the manifest to the repo's Setup, in place. Returns what changed (empty when it matched)."""
    changes = []
    apply_layout(manifest, changes)
    apply_custom_tiles(manifest, changes, inline_library)
    apply_headings(manifest, changes)
    apply_python_tiles(manifest, changes, inline_library)
    return changes


def unknown_variables(manifest):
    """Setup parameters outside solution.variables.VARIABLE_CONTRACT, as 'section i tile j: key'."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from solution.variables import VARIABLE_CONTRACT
    found = []
    for i, j, tile in all_tiles(manifest):
        if tile.get("type") != "PROJECT_VARIABLES_EDIT":
            continue
        for param in tile.get("params") or []:
            if param.get("name") and param["name"] not in VARIABLE_CONTRACT:
                found.append("section %d tile %d: %s" % (i, j, param["name"]))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("manifest", help="manifest JSON from dku app-designer get -o json")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", help="write the patched manifest here")
    mode.add_argument("--check", action="store_true", help="exit 1 if the Setup differs from the repo")
    ap.add_argument("--import", dest="import_", action="store_true",
                    help="write wrappers that import solution.* (fails in DSS 15.2 tiles)")
    args = ap.parse_args()
    with open(args.manifest) as fh:
        manifest = json.load(fh)
    target = manifest.get("manifest", manifest)  # accept the raw or the wrapped dku output
    changes = apply(target, inline_library=not args.import_)
    if args.check:
        unknown = unknown_variables(target)
        print("\n".join("differs: " + c for c in changes) or "the Setup matches the repo")
        print("\n".join("not in the variable contract: " + u for u in unknown)
              or "all Setup variables are in the variable contract")
        return 1 if changes or unknown else 0
    with open(args.out, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print("wrote %s; %d change(s):\n  %s" % (args.out, len(changes), "\n  ".join(changes) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
