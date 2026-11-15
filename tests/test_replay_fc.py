# SPDX-License-Identifier: LGPL-2.1-or-later
# Replay of every lesson against the real FreeCAD through Agent Link's
# tools: its setup, then each step's do, then its check must pass (or wait
# for the window, for a step only the window can tell). A deliberately wrong
# value makes the step fail with a why. Skipped where FreeCAD or an Agent
# Link checkout is not found (tests/_fc.py).
import copy
import json
import os
import unittest

from _fc import HAVE, WHY, caller, server

from agentlink_tutor import checks, lessons
from agentlink_tutor.engine import Engine, TutorError

# (step, the do's new args) per lesson: a value the step must not accept.
WRONG = {
    "agentlink_tutor.pd.pad-sketch": ("length", {"feature": "$pad", "set": {"Length": 20}}, "Length is 20"),
    "agentlink_tutor.pd.pocket-hole": ("depth", {"feature": "$pocket", "set": {"Length": 6}}, "Length is 6"),
    "agentlink_tutor.io.export-stl": ("export", {"objects": ["$body"], "format": "stl", "path": "Other.stl"}, "Part.stl"),
}


def core():
    out = []
    for n in sorted(os.listdir(lessons.CORE_DIR)):
        if n.endswith(lessons.SUFFIX):
            with open(os.path.join(lessons.CORE_DIR, n), encoding="utf-8") as f:
                out.append(json.load(f))
    return out


@unittest.skipUnless(HAVE, WHY)
class Replay(unittest.TestCase):
    def setUp(self):
        # A session (and folder) of its own per test, so one test's files
        # never pass another's check.
        self.session, self.srv = server()
        self.call = caller(self.srv)

    def engine(self, lesson):
        return Engine(lesson, call=self.call, doc=lambda: self.session.doc, gui=lambda: None,
                      events=lambda: [], out_dir=self.session.out_dir)

    def replay(self, lesson, stop_at=None):
        e = self.engine(lesson)
        e.start("demo")
        while e.state == "step":
            s = e.step
            if s.get("do"):
                try:
                    st = e.do()
                except TutorError as x:
                    # Only a step the window alone can tell may have a do the window alone runs.
                    self.assertTrue(checks.needs_window(s["check"]), f"{lesson['id']} {s['id']}: {x}")
                    self.assertIn("window", str(x))
                    st = e.check()
            else:
                st = e.check()
            if s["id"] == stop_at:
                return e, st
            want = "pending" if checks.needs_window(s.get("check", {})) else "pass"
            self.assertEqual(st["check"], want, f"{lesson['id']} {s['id']}: {st}")
            e.next()
        return e, None

    def test_every_lesson_replays(self):
        for lesson in core():
            with self.subTest(lesson=lesson["id"]):
                e, _ = self.replay(lesson)
                self.assertEqual(e.state, "done")

    def test_a_wrong_value_fails_with_why(self):
        for lesson in core():
            step, args, said = WRONG[lesson["id"]]
            with self.subTest(lesson=lesson["id"]):
                bad = copy.deepcopy(lesson)
                s = next(x for x in bad["steps"] if x["id"] == step)
                s["do"][0]["args"] = args
                _, st = self.replay(bad, stop_at=step)
                self.assertEqual(st["check"], "fail", st)
                self.assertIn(said, st["why"])

    def test_calls_use_the_tools_own_argument_names(self):
        listed = self.srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})["result"]["tools"]
        props = {t["name"]: set((t.get("inputSchema") or {}).get("properties", {})) for t in listed}
        for lesson in core():
            for where, c in lessons._calls(lesson):
                self.assertIn(c["tool"], props, f"{lesson['id']} {where}")
                extra = set(c.get("args") or {}) - props[c["tool"]]
                self.assertFalse(extra, f"{lesson['id']} {where}: {c['tool']} has no {sorted(extra)}")


if __name__ == "__main__":
    unittest.main()
