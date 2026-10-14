#!/usr/bin/env python3
"""Generate CLAUDE.md and AGENTS.md from harness/PROJECT_INSTRUCTIONS.md, so the two never drift."""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "harness", "PROJECT_INSTRUCTIONS.md")
TARGETS = ["CLAUDE.md", "AGENTS.md"]
HEADER = ("<!-- GENERATED FILE: edit harness/PROJECT_INSTRUCTIONS.md, then run "
          "python3 tools/sync_harness.py --write. -->\n\n")


def expected():
    with open(SOURCE) as fh:
        return HEADER + fh.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = expected()
    if args.write:
        for t in TARGETS:
            with open(os.path.join(ROOT, t), "w") as fh:
                fh.write(text)
            print("wrote %s" % t)
        return 0
    stale = [t for t in TARGETS
             if not os.path.isfile(os.path.join(ROOT, t)) or open(os.path.join(ROOT, t)).read() != text]
    if stale:
        print("stale: %s (run python3 tools/sync_harness.py --write)" % ", ".join(stale), file=sys.stderr)
        return 1
    print("harness copies are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
