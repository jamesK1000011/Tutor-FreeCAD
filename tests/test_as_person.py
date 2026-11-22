# SPDX-License-Identifier: LGPL-2.1-or-later
# Two agents on one Agent Link: a teaching agent (tutor, tutor_watch) and a
# student agent who stands in for the person through gui_input's dev-only
# as: "person". The student's window events (selection, a command used, a
# workbench switch, a task panel opened and closed, an object made, Ask
# Claude) are the person's and reach tutor_watch, numbered in order; a
# milestone ends a waiting tutor_watch early; a guided `used` check passes
# as the person's, not as done for them. The teaching agent's own calls,
# before, between and during the student's, stay left out.
import json
import os
import sys
import threading
import time
import types
import unittest

from test_engine import World

from agentlink_tutor import live, observe, run, tool
from agentlink_tutor.checks import GuiState
from agentlink_tutor.engine import Engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_agentlink_tools  # noqa: E402

AL = gen_agentlink_tools.source()
if AL and os.path.dirname(AL) not in sys.path:
    sys.path.append(os.path.dirname(AL))
try:
    from agentlink import gui_events, hooks

    HAVE = hasattr(hooks, "person_input") and hasattr(hooks, "register_thread_tool")
except ImportError:
    HAVE = False


def fresh():
    observe.BUF = observe.Buffer()
    observe._NEED.clear()
    observe._ATTACHED.update(on=False, doc=None, gui=None, sel=None)
    live.WATCH["on"] = False


class Sess:
    def __init__(self):
        self.tx, self.doc, self.by = 0, None, "agent"


# What a step of gui_input sets off in the window: FreeCAD's own observer
# calls (observe.py's) and Agent Link's window events (gui_events), on the
# thread the call runs on, as the real ones are.
def _sel(o, s=None):
    observe._Sel().addSelection("Doc", o, s or "", None)


def _cmd(c):
    gui_events._emit("command_used", c)


def _wb(w):
    gui_events._emit("workbench_activated", w)


def _edit(o):
    observe._GuiDoc().slotInEdit(types.SimpleNamespace(Object=types.SimpleNamespace(Name=o)))


def _done(o):
    observe._GuiDoc().slotResetEdit(types.SimpleNamespace(Object=types.SimpleNamespace(Name=o)))


def _new(o, ty):
    observe._Doc().slotCreatedObject(types.SimpleNamespace(Name=o, TypeId=ty))


def _ask(q):
    observe.record("ask", q=q)  # the Tutor tab's Ask the agent, with watch mode on


EFFECTS = {"sel": _sel, "cmd": _cmd, "wb": _wb, "edit": _edit, "done": _done, "new": _new, "ask": _ask}


def student_tool():
    """gui_input in small: the same as: "person" wrapping as Agent Link's
    (families/dev.py), its steps the window effects above."""
    from agentlink.protocol import Tool

    def gui_input(a):
        def steps():
            for st in a.get("steps") or ():
                EFFECTS[st[0]](*st[1:])
                if a.get("inner") and st is a["steps"][0]:
                    a["inner"]()  # a teaching agent's call taken inside it

        if a.get("as") == "person":
            s = SRV["srv"].session
            with hooks.person_input():
                try:
                    steps()
                finally:
                    s.done_by = hooks.PERSON
            return {"as": "person", "steps": len(a.get("steps") or ())}
        steps()
        return {"steps": len(a.get("steps") or ())}

    schema = {"type": "object", "properties": {"steps": {"type": "array"}, "as": {"type": "string", "enum": ["person"]},
                                               "inner": {}}}
    return Tool("gui_input", "Window input.", schema, gui_input)


SRV = {}


@unittest.skipUnless(HAVE, "needs Agent Link's person_input (gui_input as: \"person\")")
class TwoAgents(unittest.TestCase):
    def setUp(self):
        fresh()
        self.saved = hooks.saved()
        hooks.reset()
        from agentlink.protocol import Server

        from agentlink_tutor import fam_tutor

        tools = fam_tutor.tools(types.SimpleNamespace(doc=None)) + [student_tool()]
        self.srv = Server("t", "0", tools, "")
        self.srv.session = Sess()
        SRV["srv"] = self.srv
        # observe._attach joins these only where there is a window.
        hooks.on("command_used", observe._cmd)
        hooks.on("workbench_activated", observe._wb)

    def tearDown(self):
        hooks.restore(self.saved)
        hooks.THREAD_TOOLS.discard("tutor_watch")
        SRV.clear()
        fresh()

    def call(self, name, args=None, light=False):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}
        r = (self.srv.handle_light if light else self.srv.handle)(msg)
        return json.loads(r["result"]["content"][0]["text"])

    def student(self, steps, **kw):
        return self.call("gui_input", {"steps": steps, "as": "person", **kw})

    def test_the_students_input_is_the_persons(self):
        out = self.call("tutor", {"action": "watch", "on": True})
        self.assertTrue(live.watching())
        w = self.call("tutor_watch", {"wait": 0}, light=True)
        self.assertEqual((w["watching"], w["events"]), (True, []))
        # Without as: the agent's own input, left out (the live finding).
        self.call("gui_input", {"steps": [["sel", "Pad", "Face6"]]})
        self.assertEqual(self.call("tutor_watch", {"wait": 0}, light=True)["events"], [])
        a = self.student([["sel", "Pad", "Face6"], ["wb", "SketcherWorkbench"], ["cmd", "Sketcher_NewSketch"], ["edit", "Sketch"]])
        self.assertEqual(a["as"], "person")
        self.call("tutor", {"action": "status"})  # the teaching agent between: not the person's
        b = self.student([["done", "Sketch"]])
        self.assertEqual(b["as"], "person")
        w = self.call("tutor_watch", {"since": 0}, light=True)
        self.assertEqual([e["k"] for e in w["events"]], ["sel", "wb", "cmd", "edit", "done"])
        ns = [e["n"] for e in w["events"]]
        self.assertEqual(ns, sorted(ns))
        self.assertEqual(w["next"], ns[-1])
        self.assertEqual(w["events"][0], {"n": ns[0], "k": "sel", "o": "Pad", "s": "Face6"})
        self.assertEqual(w["events"][-1].get("m"), 1)  # the panel closed: a milestone
        self.assertEqual(self.call("tutor_watch", {"since": w["next"]}, light=True)["events"], [])
        self.assertFalse(hooks.agent_acting())
        self.call("tutor", {"action": "watch", "on": False})
        self.assertEqual(self.call("tutor_watch", {}, light=True)["watching"], False)
        self.assertIsNotNone(out)

    def test_a_teaching_call_inside_the_students_is_the_agents(self):
        self.call("tutor", {"action": "watch", "on": True})

        def inner():
            # The teaching agent's call while the student's steps run (as a
            # call taken while a step's dialog holds the window): its own
            # window effects stay the agent's.
            with hooks.acting():
                _cmd("Std_ViewFitAll")

        self.student([["sel", "Pad", "Face6"], ["cmd", "PartDesign_Pad"]], inner=inner)
        w = self.call("tutor_watch", {}, light=True)
        self.assertEqual([e.get("c") or e.get("o") for e in w["events"]], ["Pad", "PartDesign_Pad"])

    def test_a_milestone_ends_a_waiting_watch_early(self):
        self.call("tutor", {"action": "watch", "on": True})
        got = {}

        def poll():  # the teaching agent's long poll, on the link's socket thread
            t0 = time.monotonic()
            got["w"] = self.call("tutor_watch", {"since": 0, "wait": 5, "until": "milestone"}, light=True)
            got["s"] = time.monotonic() - t0

        th = threading.Thread(target=poll)
        th.start()
        time.sleep(0.1)
        self.student([["sel", "Sketch"], ["cmd", "PartDesign_Pad"]])  # no milestone yet
        time.sleep(0.2)
        self.assertTrue(th.is_alive())
        self.student([["new", "Pad", "PartDesign::Pad"], ["done", "Pad"]])  # the person's Pad, OK
        th.join(3)
        self.assertFalse(th.is_alive())
        self.assertLess(got["s"], 3)
        ks = [e["k"] for e in got["w"]["events"]]
        self.assertIn("new", ks)
        self.assertEqual(ks[:2], ["sel", "cmd"])

    def test_ask_claude_is_an_ask_event(self):
        self.call("tutor", {"action": "watch", "on": True})
        self.student([["ask", "Why a pad here?"]])
        w = self.call("tutor_watch", {"wait": 1, "until": "milestone"}, light=True)
        self.assertEqual(w["events"][-1]["k"], "ask")
        self.assertEqual(w["events"][-1]["q"], "Why a pad here?")


LESSON = {"schema": 1, "id": "inline.used", "version": "0.0.0", "title": "Use a command",
          "steps": [{"id": "a", "say": "Push **Pad**.", "check": {"used": "PartDesign_Pad"}},
                    {"id": "b", "say": "Push **Pocket**.", "check": {"used": "PartDesign_Pocket"}}]}


@unittest.skipUnless(HAVE, "needs Agent Link's person_input (gui_input as: \"person\")")
class GuidedUsed(unittest.TestCase):
    """A guided `used` check on the student's command: it passes as the
    person's (no done_for); the same input as the agent's does not count."""

    def setUp(self):
        fresh()
        self.saved = hooks.saved()
        hooks.reset()
        from agentlink.protocol import Server

        self.srv = Server("t", "0", [student_tool()], "")
        self.srv.session = Sess()
        SRV["srv"] = self.srv
        hooks.on("command_used", observe._cmd)
        w = World()
        self.e = Engine(json.loads(json.dumps(LESSON)), call=w, doc=lambda: w.doc, gui=lambda: GuiState())
        self.c = run.Controller(self.e)
        self.e._events = self.c.step_events
        self.c.start("guided")
        observe._ATTACHED["on"] = True  # the window's observers (GUI only)
        observe.need(("lesson", id(self.c)), self.c.poke)
        self.by = []
        hooks.on("call_done", lambda s, t, ok, ch: (self.by.append(s.by), self.c.call_done(s, t, ok, ch)))

    def tearDown(self):
        hooks.restore(self.saved)
        SRV.clear()
        fresh()

    def call(self, args):
        r = self.srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "gui_input", "arguments": args}})
        return json.loads(r["result"]["content"][0]["text"])

    def test_passes_as_the_persons(self):
        self.call({"steps": [["cmd", "PartDesign_Pad"]]})  # the agent's: not seen
        self.assertEqual(self.e.step["id"], "a")
        self.assertEqual(self.by, ["agent"])
        self.call({"steps": [["cmd", "PartDesign_Pad"]], "as": "person"})
        self.assertEqual(self.by, ["agent", "person"])
        self.assertEqual(self.e.step["id"], "b")  # passed and on (no timer: at once)
        self.assertEqual(self.e.done_for, set())  # the person's own, not done for them
        self.call({"steps": [["cmd", "PartDesign_Pocket"]], "as": "person"})
        self.assertEqual(self.e.state, "done")
        self.assertEqual(self.e.done_for, set())


if __name__ == "__main__":
    unittest.main()
