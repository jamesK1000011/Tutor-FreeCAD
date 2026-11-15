# SPDX-License-Identifier: LGPL-2.1-or-later
# For the tests that need FreeCAD and Agent Link: both found or not, and a
# server on a session of its own. Agent Link's source: $AGENTLINK_SRC, else
# a checkout beside this one (tools/gen_agentlink_tools.py source()).
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
if os.environ.get("FREECAD_LIB"):
    sys.path.append(os.environ["FREECAD_LIB"])

import gen_agentlink_tools  # noqa: E402

PKG = gen_agentlink_tools.source()
if PKG:
    sys.path.append(os.path.dirname(PKG))
try:
    import FreeCAD  # noqa: F401
    import Part  # noqa: F401
    import PartDesign  # noqa: F401
    import Sketcher  # noqa: F401

    HAVE = PKG is not None
except ImportError:
    HAVE = False
WHY = "needs FreeCAD (with PartDesign) and an Agent Link checkout ($AGENTLINK_SRC)"


def server():
    from agentlink.tools import Session, build_server

    session = Session(out_dir=tempfile.mkdtemp())
    return session, build_server(session, lean=False)


def caller(srv):
    def call(name, args=None):
        r = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args or {}}})["result"]
        return r.get("isError", False), json.loads(r["content"][0]["text"])

    return call
