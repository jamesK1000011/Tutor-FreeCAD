# SPDX-License-Identifier: LGPL-2.1-or-later
# The Pad lesson end to end against the real FreeCAD through Agent Link's
# server and the tutor tool: guided mode by the test flag AGENTLINK_AS_USER
# (the agent's own calls taken as the person's), and demo mode. Headless, so
# the two steps only the window can tell (the workbench, the selection) are
# skipped. Skipped where FreeCAD or an Agent Link checkout is not found.
import os
import unittest

from _fc import HAVE, WHY, caller, server

from agentlink_tutor import checks, live

QUIET = {"all": [{"task_open": None}, {"editing": None}]}


@unittest.skipUnless(HAVE, WHY)
class PadByFlag(unittest.TestCase):
    def setUp(self):
        from agentlink import hooks

        self.hooks = hooks
        self.env = os.environ.pop(hooks.AS_USER_ENV, None)
        self.session, self.srv = server()
        self.call = caller(self.srv)

    def tearDown(self):
        live.set_controller(None)
        os.environ.pop(self.hooks.AS_USER_ENV, None)
        if self.env is not None:
            os.environ[self.hooks.AS_USER_ENV] = self.env

    def tutor(self, **a):
        refused, st = self.call("tutor", a)
        self.assertFalse(refused, st)
        return st

    def test_guided_by_the_test_flag(self):
        os.environ[self.hooks.AS_USER_ENV] = "1"
        st = self.tutor(action="start", lesson="pad-sketch", mode="guided")
        self.assertEqual((st["step"], st["check"]), ("1/5", "pending"))
        self.assertEqual(checks.evaluate(QUIET, live.engine().context()).status, "pass")  # nothing left open
        self.tutor(action="skip")  # the workbench: the window's
        self.tutor(action="skip")  # the selection: the window's
        refused, out = self.call("pd_pad", {"sketch": live.bindings()["sketch"], "length": 10})
        self.assertFalse(refused, out)
        self.assertEqual(out.get("rider"), "tutor: step 3/5 passed; now step 4/5 pending")
        refused, out = self.call("feature_edit", {"feature": live.bindings()["pad"], "set": {"Length": 15}})
        self.assertFalse(refused, out)
        self.assertEqual(out.get("rider"), "tutor: step 4/5 passed; now step 5/5 pending")
        st = self.tutor(action="next")
        self.assertEqual((st["step"], st["skipped"]), ("done", ["bench", "pick"]))
        self.assertNotIn("done_for", st)

    def test_demo(self):
        self.tutor(action="start", lesson="pad-sketch", mode="demo")
        refused, out = self.call("tutor", {"action": "next"})
        self.assertTrue(refused)  # workbench needs the window
        self.tutor(action="skip"), self.tutor(action="skip")
        self.assertEqual(self.tutor(action="next")["id"], "length")
        self.assertEqual(self.tutor(action="next")["id"], "see")
        st = self.tutor(action="next")
        self.assertEqual((st["step"], st["done_for"]), ("done", ["length", "pad"]))


if __name__ == "__main__":
    unittest.main()
