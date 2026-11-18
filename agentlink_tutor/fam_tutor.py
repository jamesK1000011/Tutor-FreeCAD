# SPDX-License-Identifier: LGPL-2.1-or-later
# The tutor tools for agents: their definitions in data/tools.json (Agent
# Link's tool-data format), bound here to the handlers. Loaded by Agent Link
# only (agentlink_families). Not in the lean list: a session that never
# teaches pays for the group's one row in tool_groups.
import os

from agentlink import hooks

from . import lessons, live, point, tool

GROUP = "tutor"
INFO = "Teach FreeCAD in the person's window: lessons in demo or guided mode, each step checked; point at controls with numbered rings and a callout, light faces in 3D; never the cursor, menus or focus."
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# The live echo: the tutor tools draw in the window themselves, so the echo
# shows nothing for them (no bench, button or caption); Activity lists them.
NO_ECHO = ("tutor",)
NO_BUTTON = ("tutor",)
AREAS = {"tutor": "Tutor"}


def _timer(ms, fn):
    """tutor_point's ms: the lit faces taken away later (later.py: owned by
    the Tutor's long-lived QObject, never fired once that is gone)."""
    try:
        from . import later

        return later.after(int(ms), fn)
    except Exception:  # noqa: BLE001  (no Qt: nothing to take away later)
        return None


def library():
    """The Tutor's lessons and every installed add-on's (lessons/ beside
    its agentlink_families module, or its LESSONS)."""
    return lessons.installed_library()


class LessonsService:
    """hooks.service("lessons"): what an add-on (or Agent Link core) uses to
    hand the Tutor a lessons folder by name; without the Tutor nothing
    reads them."""

    @staticmethod
    def register_folder(folder, owner):
        lessons.register_folder(folder, owner)

    @staticmethod
    def ids():
        return sorted(library().lessons())


if hasattr(hooks, "provide"):
    hooks.provide("lessons", LessonsService())


# The lesson in hand follows the agent's and the person's calls (re-checked
# after each), and its state rides on the agent's answers while it runs.
# An older Agent Link without these hooks: the lesson is checked on Next.
def follow():
    hooks.on("call_done", live.call_done)
    # Before doc_close closes the lesson's document: the lesson stops (62).
    hooks.on("document_closing", live.document_closing)
    if hasattr(hooks, "register_rider"):
        hooks.register_rider("tutor", live.rider)
    if hasattr(hooks, "register_thread_tool"):
        # A long poll: answered on the window link's socket thread.
        hooks.register_thread_tool("tutor_watch")


follow()


def tools(session):
    from .window import Window

    follow()

    def tutor_point(a):
        from . import bubble

        return point.point(a, Window(session, hands=True), hooks=hooks, bindings=live.bindings(), timer=_timer, bubble=bubble)

    def tutor(a):
        return tool.tutor(a, session, library())

    return hooks.tools_from_data(DATA, GROUP, {"tutor_point": tutor_point, "tutor": tutor, "tutor_watch": tool.watch}, "Tutor")
