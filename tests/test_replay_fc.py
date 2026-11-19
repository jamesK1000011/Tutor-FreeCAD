# SPDX-License-Identifier: LGPL-2.1-or-later
# Replay of every lesson against the real FreeCAD through Agent Link's
# tools: its setup, then each step's do, then its check must pass (or wait
# for the window, for a step only the window can tell). A deliberately wrong
# value makes the step fail with a why. Skipped where FreeCAD or an Agent
# Link checkout is not found (tests/_fc.py). Run it with FreeCAD's Python
# (FreeCADCmd, or FREECAD_LIB pointing at FreeCAD's lib folder) and
# AGENTLINK_SRC at an Agent Link checkout; each lesson's end state (its
# objects, each visible solid's volume and box) is printed to stderr, so a
# check value that FreeCAD 1.1.3 does not reach shows what it does reach.
import copy
import json
import unittest

from _fc import HAVE, WHY, caller, server

from agentlink_tutor import checks, lessons
from agentlink_tutor.engine import Engine, TutorError

# (step, the do's new args, words of the why) per lesson: a value the step
# must not accept.
WRONG = {
    "agentlink_tutor.pd.pad-sketch": ("length", {"feature": "$pad", "set": {"Length": 20}}, "Length is 20"),
    "agentlink_tutor.pd.pocket-hole": ("depth", {"feature": "$pocket", "set": {"Length": 6}}, "Length is 6"),
    "agentlink_tutor.io.export-stl": ("export", {"objects": ["$body"], "format": "stl", "path": "Other.stl"}, "Part.stl"),
    "agentlink_tutor.wiki.basic-part-design": ("pad", {"sketch": "$profile", "length": 50, "sides": "symmetric"}, "50 × 26 × 26"),
    "agentlink_tutor.wiki.basic-techdraw": ("scale", {"object": "$page", "values": {"Scale": 3}}, "is 3"),
    "agentlink_tutor.wiki.film-hinge-sketch": ("radius", {"sketch": "$sketch", "constraints": [
        {"type": "radius", "refs": [0], "value": 6, "name": "neutral_radius"}]}, "5 mm"),
    "agentlink_tutor.wiki.basic-attachment": ("offset", {"object": "$base", "values": {"AttachmentOffset": {"at": [80, 80, 0]}}}, "lowest corner"),
    "agentlink_tutor.wiki.whiffle-ball": ("cube", {"kind": "box", "size": [80, 90, 90], "at": [-45, -45, -45], "name": "Cube"}, "80 × 90 × 90"),
}

# What the main session's agent-to-agent test scores, read after each replay
# (tests/test_replay_fc.py prints it): the objects, and the volume and size
# of the last solid.
REPORT = {}


def core():
    """Every stored lesson, as the library loads it (a chapter knows the
    chapters before it)."""
    lib = lessons.core_library()
    return [lib.get(i) for i in sorted(lib.lessons())]


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
        import sys

        for lesson in core():
            with self.subTest(lesson=lesson["id"]):
                e, _ = self.replay(lesson)
                self.assertEqual(e.state, "done")
                REPORT[lesson["id"]] = end_state(self.session.doc)
                sys.stderr.write(f"\nreplay {lesson['id']}: {json.dumps(REPORT[lesson['id']])}")

    def test_a_wrong_value_fails_with_why(self):
        have = {l["id"]: l for l in core()}
        for lid, (step, args, said) in sorted(WRONG.items()):
            lesson = have.get(lid)
            if lesson is None:
                continue
            with self.subTest(lesson=lid):
                bad = copy.deepcopy(lesson)
                s = next(x for x in bad["steps"] if x["id"] == step)
                s["do"][0]["args"] = args
                _, st = self.replay(bad, stop_at=step)
                self.assertEqual(st["check"], "fail", st)
                self.assertIn(said, st["why"])

    def test_calls_use_the_tools_own_argument_names(self):
        # Every tool the server has, listed or not (Agent Link's default
        # tools/list holds only its base tools; the rest are found by name).
        props = {n: set((t.schema or {}).get("properties", {})) for n, t in self.srv.tools.items()}
        for lesson in core():
            for where, c in lessons._calls(lesson):
                self.assertIn(c["tool"], props, f"{lesson['id']} {where}")
                extra = set(c.get("args") or {}) - props[c["tool"]]
                self.assertFalse(extra, f"{lesson['id']} {where}: {c['tool']} has no {sorted(extra)}")


def end_state(doc):
    """The document's objects by type, and the volume and box of each
    visible solid (mm³, mm): what a scored run compares."""
    out = {"objects": {}, "solids": []}
    for o in getattr(doc, "Objects", None) or ():
        out["objects"][o.TypeId] = out["objects"].get(o.TypeId, 0) + 1
        sh = getattr(o, "Shape", None)
        try:
            if sh is None or sh.isNull() or not sh.Solids or not getattr(o, "Visibility", True):
                continue
        except Exception:  # noqa: BLE001
            continue
        bb = sh.BoundBox
        out["solids"].append({"label": o.Label, "volume": round(sh.Volume, 3),
                              "size": [round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)],
                              "min": [round(bb.XMin, 3), round(bb.YMin, 3), round(bb.ZMin, 3)]})
    return out


if __name__ == "__main__":
    unittest.main()
