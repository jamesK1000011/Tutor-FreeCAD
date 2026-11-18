# SPDX-License-Identifier: LGPL-2.1-or-later
# Finding 78: the Draft lessons want real Draft objects. The draft, shape and
# count query keys of the checks, and the Draft tutorial and the Surface
# examples run for the person (demo) against the Draft stand-in
# (_draft_standin: the objects FreeCAD 1.1's Draft makes). Each step's check
# must pass on what the step made, and fail on a plain shape in place of a
# Draft object, and on an Upgrade that leaves an open wire or two wires. The real check is
# the live replay.
import copy
import unittest

import _draft_standin as D
from fakes import Doc, Quantity
from test_general import World, controller, starters

from agentlink_tutor import checks
from agentlink_tutor.checks import Context, evaluate


def lesson(suffix):
    return next(l for l in starters() if l["id"].endswith(suffix))


class Keys(unittest.TestCase):
    def setUp(self):
        self.doc = Doc()
        w = type("W", (), {"doc": self.doc})()
        self.arc = D.make(w, "draft_shape", {"kind": "arc", "radius": 30, "start": 60, "end": 120})
        self.line = D.make(w, "draft_shape", {"kind": "wire", "points": [[0, 0, 0], [5, 0, 0]]})
        self.plain = self.doc.add("Shape", "Part::Feature", shape=D.DShape([D.Edge([(0, 0, 0), (1, 0, 0)])]))
        self.ctx = Context(doc=self.doc)

    def st(self, check):
        return evaluate(check, self.ctx)

    def test_draft_kind_and_plain(self):
        self.assertEqual(checks.draft_kind(self.arc), "Circle")
        self.assertEqual(checks.draft_kind(self.plain), "")
        self.assertEqual(self.st({"exists": {"type": "Part::Part2DObjectPython", "draft": "Circle"}}).status, "pass")
        self.assertEqual(self.st({"exists": {"draft": "Polygon"}}).status, "fail")
        self.assertEqual([o.Name for o in checks.find(self.ctx, {"type": "Part::Feature", "draft": False})], ["Shape"])
        r = self.st({"exists": {"draft": "Polygon"}})
        self.assertEqual(r.why, "there is no Draft polygon yet")

    def test_shape_and_count(self):
        self.assertEqual(self.st({"exists": {"draft": "Wire", "shape": {"edges": 1, "wires": 1, "closed": False}}}).status, "pass")
        self.assertEqual(self.st({"exists": {"draft": "Wire", "shape": {"closed": True}}}).status, "fail")
        self.assertEqual(self.st({"exists": {"type": "Part::Feature", "count": 3}}).status, "pass")
        r = self.st({"exists": {"type": "Part::Feature", "count": 4}})
        self.assertEqual(r.status, "fail")
        self.assertIn("3 of the 4 wanted", r.why)
        self.assertEqual(self.st({"new": {"type": "Part::Feature", "count": 2}}).status, "pass")

    def test_validation(self):
        self.assertEqual(checks.problems({"exists": {"draft": "Circle", "shape": {"edges": 4, "closed": True}, "count": 2}}, "c"), [])
        self.assertEqual(checks.problems({"bbox": {"draft": False}, "size": [1, 1, 0]}, "c"), [])
        self.assertTrue(checks.problems({"exists": {"draft": 3}}, "c"))
        self.assertTrue(checks.problems({"exists": {"shape": {"faces": 1}}}, "c"))
        self.assertTrue(checks.problems({"exists": {"shape": {"closed": "yes"}}}, "c"))
        self.assertTrue(checks.problems({"absent": {"draft": "Wire", "count": 2}}, "c"))
        self.assertTrue(checks.problems({"exists": {"type": "Part::Feature", "count": 0}}, "c"))
        self.assertTrue(checks.problems({"exists": {"type": "Part::Feature", "where": {}}}, "c"))


def demo(l, world=None):
    """Each step's check result after its do, in demo; the workbench steps
    are left out (the stand-in world has no Draft workbench)."""
    w, c = controller(l, mode="demo", world=world)
    got = {}
    for _ in range(40):
        if c.e.state != "step":
            break
        st = c.e.step
        if st.get("do") and "workbench" not in str(st.get("check")):
            c.e.do()
            got[st["id"]] = c.e.result
        c.e.next()
    return w, got


class DraftTutorial(unittest.TestCase):
    def test_each_step_passes_on_real_draft_objects(self):
        w, got = demo(lesson("draft-tutorial"))
        for sid, r in got.items():
            with self.subTest(step=sid):
                self.assertEqual(r.status, "pass", r.why)
        self.assertEqual(len(got), 11)
        wires = [o for o in w.doc.Objects if o.TypeId == "Part::Feature"]
        self.assertEqual(len(wires), 1)
        self.assertEqual((len(wires[0].Shape.Edges), wires[0].Shape.Wires[0].isClosed()), (4, True))

    def test_a_plain_shape_in_place_of_a_draft_arc_fails(self):
        class Plain(World):
            def generic(self, name, args):
                if name == "draft_shape" and args.get("kind") == "arc":
                    self.calls.append((name, args))
                    o = D.make(self, name, args)
                    o.TypeId, o.Proxy = "Part::Feature", None
                    return False, {"made": o.Name}
                return super().generic(name, args)

        _w, got = demo(lesson("draft-tutorial"), world=Plain())
        self.assertEqual(got["arc30"].status, "fail")
        self.assertIn("Draft circle", got["arc30"].why)

    def test_an_upgrade_that_leaves_an_open_wire_fails(self):
        l = copy.deepcopy(lesson("draft-tutorial"))
        tie = next(s for s in l["steps"] if s["id"] == "tie1")
        tie["do"][0]["args"]["points"][0] = [15.000001, 25.980762, 0]  # six decimals: apart from the arc end
        w, got = demo(l)
        self.assertEqual(got["upgrade"].status, "fail")
        wires = [x for o in w.doc.Objects if o.TypeId == "Part::Feature" for x in o.Shape.Wires]
        self.assertFalse(all(x.isClosed() for x in wires))  # an open wire, or two wires: not the page's one closed wire


class SurfaceExamples(unittest.TestCase):
    def test_the_curve_steps_want_draft_curves(self):
        _w, got = demo(lesson("surface-examples"))
        for sid in ("edges", "profiles", "ends"):
            with self.subTest(step=sid):
                self.assertEqual(got[sid].status, "pass", got[sid].why)

    def test_plain_curves_fail(self):
        class Plain(World):
            def generic(self, name, args):
                if name == "draft_shape":
                    self.calls.append((name, args))
                    o = self.doc.add("Curve", "Part::Feature", shape=D.DShape([D.Edge([(0, 0, 0), (1, 0, 0)])]))
                    return False, {"made": o.Name}
                return super().generic(name, args)

        _w, got = demo(lesson("surface-examples"), world=Plain())
        self.assertEqual(got["edges"].status, "fail")


if __name__ == "__main__":
    unittest.main()
