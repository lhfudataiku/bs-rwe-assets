#!/usr/bin/env python3
"""Build the solution's app manifest with the Project Setup callbacks from app_manifest/tiles/.

Offline: reads a manifest fetched with `dku app-designer get -P <KEY> -o json`, replaces the inline
Python of the tiles listed in TILES with the repo's wrappers, and writes the result. Each tile is
identified by its section and position and confirmed by its module or first parameter name, so a
reordered manifest fails instead of patching the wrong tile. Applying the output to DSS is a separate,
approved step: `dku app-designer set-definition -P <KEY> <out.json>`.

    python3 tools/app_manifest.py manifest.json --out patched.json   # write the patched manifest
    python3 tools/app_manifest.py manifest.json --check              # exit 1 if any tile differs

Each tile gets solution/setup/choices.py inlined ahead of its wrapper: a tile's Python process does
not see the project library (tested on DSS 15.2, 2026-11-05: wrappers that import solution.setup fail
with "Failed to get test result for ui" even when the library has it). --import writes the bare
wrappers instead, for re-testing that on a later DSS version.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES_DIR = os.path.join(ROOT, "app_manifest", "tiles")
CHOICES = os.path.join(ROOT, "solution", "setup", "choices.py")
IMPORT = "from solution.setup.choices import "

# (section index, tile index) -> (wrapper file, how the tile is recognised)
TILES = {
    (2, 0): ("section2_tile0.py", {"module": "input_data_source_project_selectbox"}),
    (2, 3): ("section2_tile3.py", {"first_param": "person"}),
    (2, 5): ("section2_tile5.py", {"first_param": "concept"}),
    (8, 1): ("section8_tile1.py", {"first_param": "cohort_definition_id"}),
}


def locate(manifest, section, tile, expect):
    try:
        t = manifest["homepageSections"][section]["tiles"][tile]
    except (KeyError, IndexError):
        raise SystemExit("manifest has no section %d tile %d" % (section, tile))
    if "module" in expect and t.get("module") != expect["module"]:
        raise SystemExit("section %d tile %d is not module %s" % (section, tile, expect["module"]))
    if "first_param" in expect:
        params = t.get("params") or [{}]
        if params[0].get("name") != expect["first_param"]:
            raise SystemExit("section %d tile %d does not start with parameter %s" % (section, tile, expect["first_param"]))
    return t


def tile_code(fname, inline=True):
    with open(os.path.join(TILES_DIR, fname)) as fh:
        code = fh.read()
    if not inline:
        return code
    lines = code.split("\n")
    if not lines[0].startswith(IMPORT):
        raise SystemExit("%s does not start with %r" % (fname, IMPORT))
    with open(CHOICES) as fh:
        library = fh.read()
    return "# Inlined from solution/setup/choices.py by tools/app_manifest.py --inline\n" + library \
        + "\n\n# Tile wrapper (" + fname + ")\n" + "\n".join(lines[1:]).lstrip("\n")


def patch(manifest, inline=True):
    """Return the tiles whose Python differs from the repo wrappers, after replacing it."""
    changed = []
    for (section, tile), (fname, expect) in sorted(TILES.items()):
        t = locate(manifest, section, tile, expect)
        code = tile_code(fname, inline)
        if t.get("python") != code:
            t["python"] = code
            changed.append("section %d tile %d (%s)" % (section, tile, fname))
    return changed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("manifest", help="manifest JSON from dku app-designer get -o json")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", help="write the patched manifest here")
    mode.add_argument("--check", action="store_true", help="exit 1 if any tile differs from the repo")
    ap.add_argument("--import", dest="import_", action="store_true",
                    help="write wrappers that import solution.setup (fails in DSS 15.2 tiles)")
    args = ap.parse_args()
    with open(args.manifest) as fh:
        manifest = json.load(fh)
    changed = patch(manifest, inline=not args.import_)
    if args.check:
        print("\n".join("differs: " + c for c in changed) or "all Setup tiles match app_manifest/tiles/")
        return 1 if changed else 0
    with open(args.out, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print("wrote %s; replaced %d tiles: %s" % (args.out, len(changed), ", ".join(changed) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
