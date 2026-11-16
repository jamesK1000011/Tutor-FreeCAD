# SPDX-License-Identifier: LGPL-2.1-or-later
# The tutor tool through Agent Link's own server (agentlink.protocol) on a
# stand-in world: the Pad lesson end to end in guided mode with the test flag
# AGENTLINK_AS_USER (the agent's calls taken as the person's), and without it;
# in demo mode; branches, the hint ladder, inline lessons, the rider line on
# the agent's other answers, and every answer under 600 characters.
# Needs an Agent Link checkout ($AGENTLINK_SRC or ../agentlink-freecad);
# not FreeCAD.
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gen_agentlink_tools  # noqa: E402
from test_engine import World  # noqa: E402

from agentlink_tutor import engine, lessons, live  # noqa: E402
from agentlink_tutor.checks import GuiState  # noqa: E402

AL = gen_agentlink_tools.source()
if AL and os.path.dirname(AL) not in sys.path:
    sys.path.append(os.path.dirname(AL))
try:
    from agentlink import hooks
    from agentlink.protocol import Server, Tool, ToolError

    HAVE = hasattr(hooks, "register_rider")
except ImportError:
    HAVE = False
WHY = "needs an Agent Link checkout with the T3 hooks ($AGENTLINK_SRC or ../agentlink-freecad)"

CHANGES = {"doc_new", "pd_body_new", "sketch_new", "sketch_add", "pd_pad", "pd_pocket", "feature_edit", "history_undo"}


class Session:
    def __init__(self, world):
        self.world = world
        self.by = "agent"
        self.tx = 0
        self.out_dir = tempfile.mkdtemp()
        self.server = None

    @property
    def doc(self):
        return self.world.doc


def build(world):
    """Agent Link's server: the world's tools and the Tutor's, as build_server
    joins them (server.session set, so call_done and the flag work)."""
    from agentlink_tutor import fam_tutor

    session = Session(world)

    def bind(name):
        def fn(a):
            refused, out = world(name, a)
            if refused:
                raise ToolError(out["error"]["code"], out["error"]["message"])
            if name in CHANGES:
                session.tx += 1
            return out

        return fn

    tools = [Tool(n, n, {"type": "object", "properties": {k: {} for k in ("name", "plane", "items", "sketch", "length", "feature", "set", "activate", "objects")}},
                  bind(n), changes=n in CHANGES)
             for n in sorted(CHANGES | {"workbench", "selection"})]
    tools += fam_tutor.tools(session)
    srv = Server("t", "0", tools, "")
    srv.session = session
    session.server = srv
    return session, srv


@unittest.skipUnless(HAVE, WHY)
class ToolCase(unittest.TestCase):
    def setUp(self):
        self.saved = hooks.saved()
        hooks.reset()
        self.env = os.environ.pop(hooks.AS_USER_ENV, None)
        self.world = World()
        self.world.gui = GuiState("StartWorkbench")
        live.GUI = lambda: self.world.gui
        self.world.opens_sketch = True  # as the echo does in the window
        from test_run import FakeUI

        live.UI = FakeUI(self.world)
        self.session, self.srv = build(self.world)
        self.progress = lessons.Progress(params=lessons._Memory())
        from agentlink_tutor import fam_tutor

        lessons.installed_library(refresh=True)

    def tearDown(self):
        live.set_controller(None)
        live.GUI = None
        live.UI = None
        hooks.restore(self.saved)
        os.environ.pop(hooks.AS_USER_ENV, None)
        if self.env is not None:
            os.environ[hooks.AS_USER_ENV] = self.env

    def call(self, name, **args):
        r = self.srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})["result"]
        text = r["content"][0]["text"]
        body = json.loads(text)
        if name == "tutor":
            self.assertLessEqual(len(text), engine.STATE_MAX + 40, text)  # the state, and ms
        return r.get("isError", False), body

    def tutor(self, **a):
        refused, body = self.call("tutor", **a)
        self.assertFalse(refused, body)
        return body

    def sketch(self):
        return live.bindings()["sketch"]

    def walk_by_hand(self):
        """The person's (or, under the flag, the agent's) own calls do each
        step of the Pad lesson; the lesson follows them."""
        st = self.tutor(action="start", lesson="pad-sketch", mode="guided")
        self.assertEqual((st["step"], st["id"], st["check"]), ("1/5", "bench", "pending"))
        self.assertEqual((self.world.gui.editing, self.world.gui.task), (None, None))  # setup left nothing open
        riders = []
        for tool, args in (("workbench", {"activate": "Part Design"}), ("selection", {"objects": [self.sketch()]}),
                           ("pd_pad", {"sketch": self.sketch(), "length": 10}), ("feature_edit", {"feature": "Pad", "set": {"Length": 15}})):
            refused, body = self.call(tool, **args)
            self.assertFalse(refused, body)
            riders.append(body.get("rider"))
        st = self.tutor(action="status")
        self.assertEqual((st["step"], st["id"]), ("5/5", "see"))
        st = self.tutor(action="next")
        self.assertEqual(st["step"], "done")
        return st, riders

    def test_pad_lesson_guided_end_to_end_with_the_test_flag(self):
        os.environ[hooks.AS_USER_ENV] = "1"
        st, riders = self.walk_by_hand()
        self.assertEqual(st["skipped"], [])
        self.assertNotIn("done_for", st)  # every step counted as the person's
        self.assertEqual(riders, ["tutor: step 1/5 passed; now step 2/5 pending", "tutor: step 2/5 passed; now step 3/5 pending",
                                  "tutor: step 3/5 passed; now step 4/5 pending", "tutor: step 4/5 passed; now step 5/5 pending"])
        self.assertTrue(self.progress is not None)

    def test_without_the_flag_the_agents_calls_are_done_for_the_person(self):
        st, riders = self.walk_by_hand()
        self.assertEqual(st["done_for"], ["bench", "length", "pad", "pick"])

    def test_pad_lesson_demo_end_to_end(self):
        st = self.tutor(action="start", lesson="agentlink_tutor.pd.pad-sketch", mode="demo")
        did = []
        while st["step"] != "done":
            st = self.tutor(action="next")
            did.append(st.get("id"))
        self.assertEqual(did, ["pick", "pad", "length", "see", None])
        self.assertEqual([c[0] for c in self.world.calls][4:], ["workbench", "selection", "pd_pad", "feature_edit"])
        self.assertEqual(self.world.body().Shape.BoundBox.ZLength, 15)

    def test_branch_through_the_agents_answers(self):
        os.environ[hooks.AS_USER_ENV] = "1"
        self.tutor(action="start", lesson="pad-sketch")
        self.tutor(action="skip"), self.tutor(action="skip")
        _, body = self.call("pd_pocket", sketch=self.sketch(), length=5)
        self.assertEqual(body["rider"], "tutor: step 3/5 pending")
        st = self.tutor(action="status")
        self.assertEqual(st["id"], "undo-pocket")
        _, body = self.call("history_undo")
        self.assertEqual(self.tutor(action="status")["id"], "pad")

    def test_hints_mode_switch_and_do(self):
        self.tutor(action="start", lesson="pad-sketch")
        self.tutor(action="next")
        for _ in range(3):
            st = self.tutor(action="hint")
        self.assertEqual((st["hint"], st["hint_text"], st["do_it"]), (3, "select Sketch.", True))
        st = self.tutor(action="do")  # "show me this one"
        self.assertEqual(st["id"], "pad")
        st = self.tutor(action="next", mode="demo")
        self.assertEqual((st["mode"], st["id"]), ("demo", "length"))

    def test_inline_lesson(self):
        st = self.tutor(action="start", lesson={"id": "inline.body", "title": "Make a body",
                                                "steps": [{"id": "b", "say": "Make a body.", "check": {"exists": "PartDesign::Body"},
                                                           "do": [{"tool": "pd_body_new"}]}]}, mode="demo")
        self.assertEqual(st["step"], "1/1")
        self.assertEqual(self.tutor(action="next")["step"], "done")
        refused, body = self.call("tutor", action="start", lesson={"id": "inline.x", "title": "Thirty-one", "steps": [
            {"id": f"s{i}", "say": "x"} for i in range(31)]})
        self.assertTrue(refused)
        self.assertIn("30 steps or fewer", body["error"]["message"])
        # A longer job in batches: the second comes after the first (its result
        # holds in the document in front, so it goes on there).
        st = self.tutor(action="start", lesson={"id": "inline.batch2", "title": "Batch two", "setup": {"after": "inline.body"},
                                                "steps": [{"id": "c", "say": "Look at the body.", "check": {"exists": "PartDesign::Body"}}]})
        self.assertEqual(st["step"], "1/1")
        refused, body = self.call("tutor", action="start", lesson={"id": "inline.batch3", "title": "Batch three",
                                                                   "setup": {"after": "inline.nothing"}, "steps": [{"id": "a", "say": "x"}]})
        self.assertTrue(refused)
        self.assertIn("no lesson inline.nothing", body["error"]["message"])
        refused, body = self.call("tutor", action="start", lesson={"id": "inline.y", "title": "Bad tool",
                                                                   "steps": [{"id": "a", "say": "x", "do": [{"tool": "nope"}]}]})
        self.assertIn("no tool nope", body["error"]["message"])
        refused, body = self.call("tutor", action="start", lesson=json.dumps({"id": "inline.z", "title": "As text", "steps": [{"id": "a", "say": "x"}]}))
        self.assertFalse(refused, body)

    def test_list_and_refusals(self):
        got = self.tutor(action="list", query="pad a sketch")
        self.assertEqual([r["id"] for r in got["lessons"]], ["agentlink_tutor.pd.pad-sketch"])
        got = self.tutor(action="list", query="bike-stem")  # a course's chapters, by its tag, in order
        self.assertEqual([r["course"] for r in got["lessons"]], ["bike-stem 1", "bike-stem 2", "bike-stem 3"])
        refused, body = self.call("tutor", action="next")
        self.assertEqual((refused, body["error"]["code"]), (True, "invalid_state"))
        refused, body = self.call("tutor", action="start", lesson="no-such")
        self.assertEqual(body["error"]["code"], "not_found")
        self.tutor(action="start", lesson="pad-sketch")
        self.assertEqual(self.tutor(action="list")["running"], "agentlink_tutor.pd.pad-sketch step 1/5")
        st = self.tutor(action="stop")
        self.assertEqual((st["state"], st["mode"]), ("stopped", "guided"))
        _, body = self.call("workbench", activate="Part Design")
        self.assertNotIn("rider", body)  # over: nothing rides

    def test_explain_round_trip(self):
        from agentlink_tutor import prefs

        self.addCleanup(prefs._MEM.values.clear)
        self.assertEqual(self.tutor(action="explain", on=False)["explain"], "off")
        st = self.tutor(action="start", lesson="pad-sketch")
        self.assertEqual(st["explain"], "off")
        self.tutor(action="skip"), self.tutor(action="skip")
        st = self.tutor(action="status")
        self.assertNotIn("because", st)
        self.assertIn("because", self.tutor(action="status", detail=True))
        st = self.tutor(action="explain", on=True)
        self.assertEqual((st["explain"], st["because"]), ("on", "Pad pushes a closed sketch out to make a solid."))
        refused, body = self.call("tutor", action="explain")
        self.assertTrue(refused)

    def test_refused_demo_step_says_why(self):
        self.world.gui = None  # no window: workbench is refused
        self.tutor(action="start", lesson="pad-sketch", mode="demo")
        refused, body = self.call("tutor", action="next")
        self.assertTrue(refused)
        self.assertIn("workbench was refused", body["error"]["message"])


if __name__ == "__main__":
    unittest.main()
