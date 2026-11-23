#!/usr/bin/env python3
"""Build the solution's Project Setup (app manifest) from the repo.

Offline: reads a manifest fetched with `dku app-designer get -P <KEY> -o json` and applies the repo's
layout to it. Applying the output to DSS is a separate, approved step:
`dku app-designer set-definition -P <KEY> <out.json>`.

    python3 tools/app_manifest.py manifest.json --out patched.json   # write the patched manifest
    python3 tools/app_manifest.py manifest.json --check              # exit 1 if anything differs,
                                                                     # or a Setup key is outside the
                                                                     # variable contract

What the repo owns (solution-revision-plan.md, R1 and R2):
- the Python of the tiles in PYTHON_TILES, found by what they are, not by position;
- the whole of the custom tiles in CUSTOM_TILES (Python, HTML and JS in app_manifest/tiles/);
- the "Cohort script table naming" tile;
- what LAYOUT removes, renames and relabels.

A tile's Python process does not see the project library (DSS 15.2, 2026-11-05: wrappers that
import solution.* fail with "Failed to get test result for ui"). So every `from solution.<module>
import ...` line in a wrapper, and in the modules it pulls in, is replaced by that module's source,
once. --import writes the bare wrappers instead, for re-testing that on a later DSS version.
"""
import argparse
import copy
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
    ("section8_tile1.py", {"first_param": "cohort_definition_id"}),
]

# Tiles the repo defines entirely: module -> prompt, help, and where the tile goes.
CUSTOM_TILES = {
    "register_cohorts": {
        "prompt": "Register cohorts",
        "help": "One row per uploaded script. Check the id, name and description of each script to "
                "submit, tick Replace to rebuild an existing cohort, then save and run the ingestion.",
        "section_of": "CREATECOHORTSCRIPTS", "before": "CREATECOHORTSCRIPTS"},
    "built_cohorts": {
        "prompt": "Built cohorts",
        "help": "Every registered cohort with its latest build.",
        "section_of": "WRITECOHORTTODATASETS", "before": None},
}

NAMING_TILE = {
    "type": "PROJECT_VARIABLES_EDIT",
    "behavior": "INLINE_AUTO_SAVE",
    "prompt": "Cohort script table naming",
    "help": "How your cohort SQL scripts name OMOP tables. Atlas exports use placeholders such as "
            "@cdm_database_schema.person.",
    "params": [
        {"name": "cohort_script_table_naming", "type": "SELECT", "label": "Scripts name OMOP tables with",
         "defaultValue": "atlas", "mandatory": True,
         "selectChoices": [{"value": "atlas", "label": "OHDSI Atlas placeholders"},
                           {"value": "plain", "label": "Plain OMOP table names"},
                           {"value": "prefix", "label": "Custom prefix"}]},
        {"name": "cohort_script_table_prefix", "type": "STRING", "label": "Prefix",
         "description": "Written before every OMOP table name in the scripts, for example cdm.",
         "mandatory": False, "visibilityCondition": "model.cohort_script_table_naming == 'prefix'"},
    ],
}
NAMING_PLACE = {"section_of": "IMPORTDATASETSFROMDATAPREPPROJECT", "before": "IMPORTDATASETSFROMDATAPREPPROJECT"}

LAYOUT = {
    # R1: the custom table mapping goes (its section holds this scenario's button).
    "remove_sections_with_scenario": ["CHECKOMOPTABLEVARIABLESMAPPING"],
    # R2: the metadata CSV upload goes.
    "remove_tile_types": ["UPLOAD_DATASET_SET_FILE"],
    "scenario_prompts": {"CREATECOHORTSCRIPTS": "Ingest registered cohorts"},
    "sections": {
        "CREATECOHORTSCRIPTS": {
            "sectionTitle": "Upload and Register Cohort SQL Scripts",
            "sectionText": "Upload one or more cohort SQL scripts, each defining one cohort. Register "
                           "them below: every script gets a cohort id, a name and an optional "
                           "description, prefilled from `-- name:` and `-- description:` comments at "
                           "the top of the script. Then run the ingestion, which checks the batch "
                           "again and writes the cohort definitions."},
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
    library = library.replace("# Inlined from ", "# Inlined from ", 1).replace(
        "\n", " by tools/app_manifest.py --inline\n", 1)
    return library + "\n\n# Tile wrapper (" + fname + ")\n" + "\n".join(lines[len(head):]).lstrip("\n")


def read_tile_file(name):
    with open(os.path.join(TILES_DIR, name)) as fh:
        return fh.read()


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
    for scenario_id, values in LAYOUT["sections"].items():
        update(section_of_scenario(manifest, scenario_id), values, changes, "section of %s" % scenario_id)


def apply_naming_tile(manifest, changes):
    found = [t for _, _, t in all_tiles(manifest) if matches(t, {"first_param": "cohort_script_table_naming"})]
    if not found:
        place(manifest, copy.deepcopy(NAMING_TILE), NAMING_PLACE, changes, "the table naming tile")
    else:
        update(found[0], copy.deepcopy(NAMING_TILE), changes, "table naming tile")


def apply_custom_tiles(manifest, changes, inline_library):
    for module, spec in CUSTOM_TILES.items():
        values = {"type": "PROJECT_VARIABLES_EDIT", "behavior": "INLINE_AUTO_SAVE", "module": module,
                  "params": [], "prompt": spec["prompt"], "help": spec["help"],
                  "python": tile_code(module + ".py", inline_library),
                  "html": read_tile_file(module + ".html"), "js": read_tile_file(module + ".js")}
        found = [t for _, _, t in all_tiles(manifest) if t.get("module") == module]
        if not found:
            place(manifest, values, {"section_of": spec["section_of"], "before": spec["before"]}, changes,
                  "tile %s" % module)
        else:
            update(found[0], values, changes, "tile %s" % module)


def apply_python_tiles(manifest, changes, inline_library):
    for fname, expect in PYTHON_TILES:
        i, j, tile = find_tile(manifest, expect)
        update(tile, {"python": tile_code(fname, inline_library)}, changes, "section %d tile %d (%s)" % (i, j, fname))


def apply(manifest, inline_library=True):
    """Bring the manifest to the repo's Setup, in place. Returns what changed (empty when it matched)."""
    changes = []
    apply_layout(manifest, changes)
    apply_naming_tile(manifest, changes)
    apply_custom_tiles(manifest, changes, inline_library)
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
