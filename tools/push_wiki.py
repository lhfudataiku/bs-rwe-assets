#!/usr/bin/env python3
"""Keep DSS project wikis and their drafts in docs/wiki/<PROJECT>/ in step.

The demo suite's wiki set is five numbered articles (Overview, Walkthrough, Technical Requirements,
Release Notes, Legal). Drafts live here so they can be reviewed in Git; DSS stays the place people
read them. Bodies are stored byte-for-byte, so a drift report is an exact comparison.

    python3 tools/push_wiki.py                       # drift report for every project in docs/wiki/
    python3 tools/push_wiki.py --pull DEMO_SF_RWE    # overwrite the drafts with what DSS has
    python3 tools/push_wiki.py --push DEMO_SF_RWE    # write changed drafts to DSS (one project at a time)

The default never writes anywhere. --push changes a live wiki, so run it only for a project whose
owner has approved the drafts; it updates articles that differ and creates ones DSS lacks, and never
deletes an article.
"""

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI = os.path.join(ROOT, "docs", "wiki")
STANDARD = ["Overview", "Walkthrough", "Technical Requirements", "Release Notes", "Legal"]


def dku(args, stdin=None):
    res = subprocess.run(["dku", "--format", "json"] + args, capture_output=True, text=True, input=stdin)
    if res.returncode != 0:
        raise RuntimeError(" ".join((res.stderr or res.stdout).split())[:300])
    return json.loads(res.stdout) if res.stdout.strip() else None


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def local_articles(project):
    """{title: (path, body)} from docs/wiki/<project>/index.json."""
    folder = os.path.join(WIKI, project)
    with open(os.path.join(folder, "index.json")) as fh:
        index = json.load(fh)
    out = {}
    for fname, title in index.items():
        with open(os.path.join(folder, fname)) as fh:
            out[title] = (os.path.join(folder, fname), fh.read())
    return out


def remote_articles(project):
    """{title: (id, body)} from DSS."""
    out = {}
    for art in dku(["wiki", "list", "-P", project]) or []:
        got = dku(["wiki", "get", art["id"], "-P", project])
        out[art["title"]] = (art["id"], got.get("body", "") or "")
    return out


def pull(project):
    remote = remote_articles(project)
    folder = os.path.join(WIKI, project)
    os.makedirs(folder, exist_ok=True)
    order = [t for t in STANDARD if t in remote] + sorted(t for t in remote if t not in STANDARD)
    index = {}
    for n, title in enumerate(order, 1):
        fname = "%02d-%s.md" % (n, slug(title))
        with open(os.path.join(folder, fname), "w") as fh:
            fh.write(remote[title][1])
        index[fname] = title
    with open(os.path.join(folder, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)
        fh.write("\n")
    print("%s: pulled %d articles" % (project, len(index)))


def report(project):
    local, remote = local_articles(project), remote_articles(project)
    rows = []
    for title in sorted(set(local) | set(remote), key=lambda t: (t not in STANDARD, STANDARD.index(t) if t in STANDARD else 0, t)):
        if title not in remote:
            state = "draft only"
        elif title not in local:
            state = "DSS only"
        else:
            state = "same" if local[title][1] == remote[title][1] else "differs"
        rows.append((title, state))
    missing = [t for t in STANDARD if t not in local]
    for title, state in rows:
        print("%s\t%s\t%s" % (project, title, state))
    if missing:
        print("%s\t(standard set)\tmissing drafts: %s" % (project, ", ".join(missing)))
    return sum(state != "same" for _, state in rows)


def push(project):
    if project.startswith("_"):
        raise SystemExit("%s is a template, not a DSS project" % project)
    local, remote = local_articles(project), remote_articles(project)
    for title, (path, body) in local.items():
        if title in remote and remote[title][1] == body:
            continue
        if title in remote:
            dku(["wiki", "update", remote[title][0], "-P", project, "--body", "-"], stdin=body)
            print("%s: updated %s" % (project, title))
        else:
            dku(["wiki", "create", title, "-P", project, "--body", "-"], stdin=body)
            print("%s: created %s" % (project, title))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--pull", nargs="+", metavar="PROJECT", help="overwrite drafts from DSS")
    mode.add_argument("--push", metavar="PROJECT", help="write changed drafts of one project to DSS")
    args = ap.parse_args()
    if args.pull:
        for project in args.pull:
            pull(project)
        return 0
    if args.push:
        push(args.push)
        return 0
    projects = sorted(d for d in os.listdir(WIKI)
                      if not d.startswith("_") and os.path.isfile(os.path.join(WIKI, d, "index.json")))
    drift = sum(report(p) for p in projects)
    print("%d article(s) differ from DSS" % drift, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
