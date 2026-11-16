# SPDX-License-Identifier: LGPL-2.1-or-later
# The tutor tools for agents: their definitions in data/tools.json (Agent
# Link's tool-data format), bound here to the handlers. Loaded by Agent Link
# only (agentlink_families). Not in the lean list: a session that never
# teaches pays for the group's one row in tool_groups.
import os

from agentlink import hooks

from . import live, point

GROUP = "tutor"
INFO = "Teach FreeCAD in the person's window: point at controls with numbered rings and a callout, light faces in 3D; never the cursor, menus or focus."
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# The live echo: the tutor tools draw in the window themselves, so the echo
# shows nothing for them (no bench, button or caption); Activity lists them.
NO_ECHO = ("tutor",)
NO_BUTTON = ("tutor",)
AREAS = {"tutor": "Tutor"}


def _timer(ms, fn):
    try:
        from PySide import QtCore

        QtCore.QTimer.singleShot(ms, fn)
    except Exception:
        pass


def tools(session):
    from .window import Window

    def tutor_point(a):
        return point.point(a, Window(session), hooks=hooks, bindings=live.bindings(), timer=_timer)

    return hooks.tools_from_data(DATA, GROUP, {"tutor_point": tutor_point}, "Tutor")
