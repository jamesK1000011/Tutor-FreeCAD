#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Refresh tests/data/agentlink_tools.txt: the tool names Agent Link for
FreeCAD defines, read from its source without running it (every
Tool("name", ...) under agentlink/, and the entries of its data/tools.json).
The lessons' tool calls are checked against this list.

    python3 tools/gen_agentlink_tools.py [path to an Agent Link checkout]

Without a path: $AGENTLINK_SRC, else an AgentLink-FreeCAD checkout beside
this one (../agentlink-freecad or ../AgentLink-FreeCAD).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tests", "data", "agentlink_tools.txt")
TOOL = re.compile(r'\bTool\(\s*"([a-z][a-z0-9_]*)"')


def source(arg=None):
    """The agentlink/ package folder of an Agent Link checkout, or None."""
    cands = [arg, os.environ.get("AGENTLINK_SRC")]
    up = os.path.dirname(ROOT)
    cands += [os.path.join(up, n) for n in ("agentlink-freecad", "AgentLink-FreeCAD")]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "agentlink", "tools.py")):
            return os.path.join(c, "agentlink")
    return None


def names(pkg):
    out = set()
    for d, _, files in os.walk(pkg):
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    out |= set(TOOL.findall(fh.read()))
    data = os.path.join(pkg, "data", "tools.json")
    if os.path.isfile(data):
        with open(data, encoding="utf-8") as fh:
            out |= set(json.load(fh).get("entries", {}))
    return sorted(out)


def render(pkg):
    return "# Agent Link for FreeCAD's tool names (tools/gen_agentlink_tools.py)\n" + "\n".join(names(pkg)) + "\n"


def vendored():
    with open(OUT, encoding="utf-8") as fh:
        return {ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")}


if __name__ == "__main__":
    pkg = source(sys.argv[1] if len(sys.argv) > 1 else None)
    if pkg is None:
        sys.exit("No Agent Link checkout found: give its path.")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(render(pkg))
    print(f"{len(vendored())} tool names written to {os.path.relpath(OUT, ROOT)}")
