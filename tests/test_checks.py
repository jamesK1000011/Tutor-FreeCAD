# SPDX-License-Identifier: LGPL-2.1-or-later
# The check vocabulary against a plain stand-in document, no FreeCAD.
import os
import tempfile
import unittest

from fakes import Doc, Obj, Quantity, Shape, Wire

from agentlink_tutor import checks
from agentlink_tutor.checks import Context, GuiState, evaluate


def block():
    doc = Doc()
    body = doc.add("Body", "PartDesign::Body", shape=Shape(12000, (40, 20, 15)))
    sk = doc.add("Sketch", "Sketcher::SketchObject", inside=body, shape=Shape(0, solids=0, wires=[Wire(True)]), DoF=0)
    sk.solve = lambda: 0
    pad = doc.add("Pad", "PartDesign::Pad", inside=body, shape=Shape(12000, (40, 20, 15)), Length=Quantity(15.0))
    return doc, body, sk, pad


class Vocabulary(unittest.TestCase):
    def setUp(self):
        self.doc, self.body, self.sk, self.pad = block()
        self.ctx = Context(doc=self.doc)

    def st(self, check, ctx=None):
        return evaluate(check, ctx or self.ctx)

    def test_exists_and_absent(self):
        self.assertEqual(self.st({"exists": "Pad"}).status, "pass")
        self.assertEqual(self.st({"exists": "PartDesign::Pad"}).status, "pass")
        self.assertEqual(self.st({"exists": {"type": "PartDesign::Pad", "in": "Body"}}).status, "pass")
        r = self.st({"exists": "PartDesign::Pocket"})
        self.assertEqual(r.status, "fail")
        self.assertEqual(r.why, "there is no pocket yet")
        self.assertEqual(self.st({"absent": "PartDesign::Pocket"}).status, "pass")
        r = self.st({"absent": {"type": "PartDesign::Pad"}})
        self.assertEqual((r.status, r.why), ("fail", "Pad is still there"))

    def test_new_counts_only_what_the_step_made(self):
        ctx = Context(doc=self.doc, before={"Body", "Sketch", "Pad"})
        self.assertEqual(self.st({"new": "PartDesign::Pad"}, ctx).status, "fail")
        self.doc.add("Pad", "PartDesign::Pad", shape=Shape(1))
        self.assertEqual(self.st({"new": "PartDesign::Pad"}, ctx).status, "pass")

    def test_prop_with_tolerance_and_why(self):
        self.assertEqual(self.st({"prop": "Pad", "name": "Length", "eq": 15, "tol": 0.01}).status, "pass")
        r = self.st({"prop": "Pad", "name": "Length", "eq": 10, "tol": 0.01, "unit": "mm"})
        self.assertEqual(r.status, "fail")
        self.assertEqual(r.why, "Length is 15 mm; the step wants 10 mm")
        self.assertEqual(self.st({"prop": "Pad", "name": "Length", "gt": 10}).status, "pass")
        self.assertIn("under", self.st({"prop": "Pad", "name": "Length", "lt": 10}).why)
        self.assertIn("has no Depth", self.st({"prop": "Pad", "name": "Depth", "eq": 1}).why)
        self.assertIn("not in the document", self.st({"prop": "Nope", "name": "Length", "eq": 1}).why)
        # A label reaches the object too: the person's Pad001 renamed "Base" passes.
        self.pad.Label = "Base"
        self.assertEqual(self.st({"prop": "Base", "name": "Length", "eq": 15}).status, "pass")

    def test_valid(self):
        self.assertEqual(self.st({"valid": "Pad"}).status, "pass")
        self.pad.State = ["Invalid"]
        self.assertIn("error", self.st({"valid": "Pad"}).why)
        self.pad.State = ["Touched"]
        self.assertEqual(self.st({"valid": "Pad"}).status, "pending")
        self.pad.State = []
        self.pad.Shape = Shape(0, solids=0)
        self.assertEqual(self.st({"valid": "Pad"}).why, "Pad is not a solid")
        self.assertEqual(self.st({"valid": "Sketch"}).status, "pass")  # a sketch is not a solid, and needs not be
        self.assertEqual(self.st({"valid": "Sketch", "solid": True}).status, "fail")

    def test_volume_and_bbox(self):
        self.assertEqual(self.st({"volume": "Body", "eq": 12000, "tol": 1}).status, "pass")
        self.assertIn("volume is 12000 mm³", self.st({"volume": "Body", "eq": 8000, "tol": 1}).why)
        self.assertEqual(self.st({"bbox": "Body", "size": [40, 20, 15]}).status, "pass")
        self.assertIn("40 × 20 × 15 mm", self.st({"bbox": "Body", "size": [40, 20, 10]}).why)

    def test_sketch(self):
        self.assertEqual(self.st({"sketch": "Sketch", "closed": True, "full": True}).status, "pass")
        self.sk.Shape = Shape(0, solids=0, wires=[Wire(False)])
        self.assertIn("open outline", self.st({"sketch": "Sketch", "closed": True}).why)
        self.sk.DoF = 2
        self.assertIn("2 degrees of freedom", self.st({"sketch": "Sketch", "dof": 0}).why)
        self.sk.Shape = Shape(0, solids=0)
        self.assertIn("no profile", self.st({"sketch": "Sketch", "closed": True}).why)

    def test_file_in_the_session_folder(self):
        d = tempfile.mkdtemp()
        ctx = Context(doc=self.doc, out_dir=d)
        self.assertEqual(evaluate({"file": "Part.stl"}, ctx).status, "fail")
        with open(os.path.join(d, "Part.stl"), "wb") as f:
            f.write(b"x" * 10)
        self.assertIn("only 10 bytes", evaluate({"file": "Part.stl", "min_bytes": 84}, ctx).why)
        self.assertEqual(evaluate({"file": "Part.stl", "min_bytes": 8}, ctx).status, "pass")
        self.assertEqual(evaluate({"file": "Part.stl"}, Context(doc=self.doc)).status, "pending")

    def test_window_checks_wait_without_a_window(self):
        for c in ({"workbench": "PartDesignWorkbench"}, {"selected": "Sketch"}, {"editing": "Sketch"}, {"task_open": "PartDesign_Pad"}):
            r = self.st(c)
            self.assertEqual(r.status, "pending", c)
            self.assertEqual(r.why, checks.NO_WINDOW)
        # No window has no dialog open and nothing in edit.
        self.assertEqual(self.st({"task_open": None}).status, "pass")
        self.assertEqual(self.st({"editing": None}).status, "pass")

    def test_window_checks_with_a_window(self):
        gui = GuiState("SketcherWorkbench", [("Sketch", ["Edge1"])], editing="Sketch", task="Sketcher_SketchObject")
        ctx = Context(doc=self.doc, gui=gui)
        self.assertEqual(evaluate({"workbench": "PartDesignWorkbench"}, ctx).why, "Sketcher is the active workbench, not Part Design")
        self.assertEqual(evaluate({"workbench": "SketcherWorkbench"}, ctx).status, "pass")
        self.assertEqual(evaluate({"selected": "Sketch"}, ctx).status, "pass")
        self.assertEqual(evaluate({"selected": "Sketch", "sub": "Edge"}, ctx).status, "pass")
        self.assertEqual(evaluate({"selected": "Sketch", "sub": "Face"}, ctx).why, "Sketch (face) is not selected")
        self.assertEqual(evaluate({"selected": "Pad"}, ctx).status, "fail")
        self.assertEqual(evaluate({"editing": "Sketch"}, ctx).status, "pass")
        self.assertIn("still open for editing", evaluate({"editing": None}, ctx).why)
        self.assertEqual(evaluate({"task_open": True}, ctx).status, "pass")
        self.assertEqual(evaluate({"task_open": "PartDesign_Pad"}, ctx).status, "fail")
        self.assertIn("still open", evaluate({"task_open": None}, ctx).why)

    def test_used_reads_the_events(self):
        self.assertEqual(self.st({"used": "Std_Export"}).status, "pending")
        ctx = Context(doc=self.doc, events=[{"k": "cmd", "c": "PartDesign_Pad"}])
        self.assertEqual(evaluate({"used": "PartDesign_Pad"}, ctx).status, "pass")
        self.assertEqual(evaluate({"used": "Std_Export"}, ctx).status, "fail")

    def test_combinators(self):
        ok, bad, wait = {"exists": "Pad"}, {"exists": "Nope"}, {"workbench": "X"}
        self.assertEqual(self.st({"all": [ok, ok]}).status, "pass")
        self.assertEqual(self.st({"all": [ok, wait]}).status, "pending")
        self.assertEqual(self.st({"all": [wait, bad]}).status, "fail")  # a failure outranks waiting
        self.assertEqual(self.st({"any": [bad, ok]}).status, "pass")
        self.assertEqual(self.st({"any": [bad, wait]}).status, "pending")
        self.assertIn("; or ", self.st({"any": [bad, {"exists": "Other"}]}).why)
        self.assertEqual(self.st({"not": bad}).status, "pass")
        self.assertEqual(self.st({"not": ok}).status, "fail")
        self.assertEqual(self.st({"not": wait}).status, "pending")

    def test_unknown_kind_fails_without_an_add_on(self):
        r = self.st({"glow": "Pad"})
        self.assertEqual(r.status, "fail")
        self.assertIn("glow", r.why)

    def test_a_check_never_changes_the_document(self):
        before = [(o.Name, o.Label) for o in self.doc.Objects]
        for c in ({"exists": "Pad"}, {"prop": "Pad", "name": "Length", "eq": 1}, {"volume": "Body", "eq": 1}, {"sketch": "Sketch", "closed": True, "full": True}):
            self.st(c)
        self.assertEqual(before, [(o.Name, o.Label) for o in self.doc.Objects])

    def test_needs_window(self):
        self.assertTrue(checks.needs_window({"workbench": "X"}))
        self.assertTrue(checks.needs_window({"all": [{"exists": "Pad"}, {"selected": "Pad"}]}))
        self.assertFalse(checks.needs_window({"any": [{"file": "a.stl"}, {"used": "Std_Export"}]}))
        self.assertFalse(checks.needs_window({"all": [{"prop": "Pad"}, {"task_open": None}, {"editing": None}]}))
        self.assertTrue(checks.needs_window({"task_open": "PartDesign_Pad"}))


class Problems(unittest.TestCase):
    def test_vocabulary_is_closed(self):
        self.assertEqual(checks.problems({"exists": "Pad"}, "c"), [])
        self.assertIn("unknown check kind", checks.problems({"glow": 1}, "c")[0])
        self.assertEqual(checks.problems({"glow": 1}, "c", extra_kinds=("glow",)), [])
        self.assertTrue(checks.problems({"exists": "Pad", "absent": "Pad"}, "c"))
        self.assertTrue(checks.problems({"prop": "$p", "eq": 1}, "c"))  # no name
        self.assertTrue(checks.problems({"prop": "$p", "name": "Length"}, "c"))  # nothing to compare
        self.assertTrue(checks.problems({"volume": "$b", "eq": 1, "size": 2}, "c"))
        self.assertTrue(checks.problems({"file": "../etc/passwd"}, "c"))
        self.assertTrue(checks.problems({"file": "/tmp/x.stl"}, "c"))
        self.assertTrue(checks.problems({"all": []}, "c"))
        self.assertIn("c.all[1]", checks.problems({"all": [{"exists": "a"}, {"nope": 1}]}, "c")[0])


# ---- parameters and features (T5/T6): where, expr, follows, sketch options ------------


class Sheet(Obj):
    """A spreadsheet with the alias size in A1, its value read as FreeCAD
    reads an alias (sheet.size)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.cells = {"A1": "55 mm"}

    def getCellFromAlias(self, alias):
        return "A1" if alias == "size" else None

    def getContents(self, cell):
        return self.cells[cell]

    def set(self, cell, value):
        self.cells[cell] = value

    @property
    def size(self):
        return Quantity(float(self.cells["A1"].split()[0]))


class ParamDoc(Doc):
    """A document whose body's length follows a parameter (size + 47 mm along
    X), with FreeCAD's transaction calls: openTransaction keeps the values,
    abortTransaction puts them back."""

    def __init__(self, holder="varset", follow=True, breaks_at=None):
        super().__init__()
        self.follow, self.breaks_at = follow, breaks_at
        if holder == "varset":
            self.h = self.add("VarSet", "App::VarSet", size=Quantity(55.0))
        else:
            self.h = Sheet("Params", "Spreadsheet::Sheet")
            self.Objects.append(self.h)
        self.body = self.add("Body", "PartDesign::Body")
        self.sketch = self.add("Sketch", "Sketcher::SketchObject",
                               ExpressionEngine=[("Constraints.place", "VarSet.size"), ("Constraints.front", "<<VarSet>>.size + 20 mm"),
                                                 ("Constraints.other", "sizeX + 1")])
        self.txn = None
        self.recomputes = 0
        self.recompute()

    def size(self):
        return checks.number(self.h.size)

    def recompute(self):
        self.recomputes += 1
        x = self.size() + 47 if self.follow else 102
        self.body.Shape = Shape(1000, (x, 22, 47))
        self.body.valid = not (self.breaks_at is not None and self.size() >= self.breaks_at)

    def openTransaction(self, name):
        self.txn = (name, self.size(), dict(getattr(self.h, "cells", {}) or {}))

    def abortTransaction(self):
        _name, size, cells = self.txn
        if cells:
            self.h.cells = cells
        else:
            self.h.size = Quantity(size)
        self.txn = None


class Parameters(unittest.TestCase):
    def st(self, check, doc, gui=None):
        return evaluate(check, Context(doc=doc, gui=gui))

    def test_where_finds_a_feature_by_its_values(self):
        doc = Doc()
        doc.add("Hole", "PartDesign::Hole", ThreadSize="M4", HoleCutType="Countersink", Diameter=Quantity(4.5))
        ok = {"exists": {"type": "PartDesign::Hole", "where": {"ThreadSize": "M4", "HoleCutType": "Countersink", "Diameter": {"ge": 4.3, "le": 5}}}}
        self.assertEqual(self.st(ok, doc).status, "pass")
        bad = {"exists": {"type": "PartDesign::Hole", "where": {"ThreadSize": "M5"}}}
        r = self.st(bad, doc)
        self.assertEqual((r.status, r.why), ("fail", "there is no hole with Thread size M5 yet"))
        self.assertEqual(self.st({"exists": {"type": "PartDesign::Hole", "where": {"Diameter": 4.5}}}, doc).status, "pass")
        self.assertEqual(self.st({"exists": {"type": "PartDesign::Hole", "where": {"Nope": 1}}}, doc).status, "fail")
        self.assertEqual(checks.problems(ok, "c"), [])
        self.assertTrue(checks.problems({"exists": {"type": "X::Y", "where": {"A": {"near": 1}}}}, "c"))
        self.assertTrue(checks.problems({"exists": {"type": "X::Y", "where": []}}, "c"))

    def test_expr_counts_values_bound_to_the_parameter(self):
        doc = ParamDoc()
        self.assertEqual(self.st({"expr": "Sketch", "uses": "size", "count": 2}, doc).status, "pass")
        r = self.st({"expr": "Sketch", "uses": "size", "count": 3}, doc)
        self.assertEqual(r.why, "2 values of Sketch use size; the step wants 3")  # sizeX + 1 is not size
        doc.sketch.ExpressionEngine = []
        self.assertIn("no value of Sketch uses size", self.st({"expr": "Sketch", "uses": "size"}, doc).why)
        self.assertEqual(self.st({"expr": "Sketch", "uses": "size", "path": "front"}, ParamDoc()).status, "pass")
        self.assertTrue(checks.problems({"expr": "Sketch"}, "c"))
        self.assertTrue(checks.problems({"expr": "Sketch", "uses": "size", "count": 0}, "c"))

    def test_follows_tries_the_parameter_and_puts_it_back(self):
        for holder in ("varset", "sheet"):
            with self.subTest(holder=holder):
                doc = ParamDoc(holder)
                seen = []
                doc.recompute_was = doc.recompute
                doc.recompute = lambda d=doc: (seen.append(checks.in_trial()), d.recompute_was())
                c = {"follows": "size", "object": "Body", "by": 5, "axis": "x", "change": 5}
                self.assertEqual(self.st(c, doc).status, "pass")
                self.assertEqual(doc.size(), 55.0)  # put back
                self.assertEqual(doc.body.Shape.BoundBox.XLength, 102)
                self.assertTrue(seen and all(seen))  # the window's signals in the trial are not the person's
                self.assertFalse(checks.in_trial())
                if holder == "sheet":
                    self.assertEqual(doc.h.cells["A1"], "55 mm")  # its unit kept
        r = self.st({"follows": "size", "object": "Body"}, ParamDoc(follow=False))
        self.assertEqual(r.why, "Body does not follow size: it keeps its size when size changes")
        r = self.st({"follows": "size", "object": "Body", "axis": "x", "change": 10}, ParamDoc())
        self.assertIn("grows 5 mm along X", r.why)
        r = self.st({"follows": "size", "object": "Body"}, ParamDoc(breaks_at=60))
        self.assertEqual(r.why, "with size at 60 mm, Body has an error")
        doc = ParamDoc()
        doc.remove("VarSet")
        self.assertIn("no parameter size", self.st({"follows": "size", "object": "Body"}, doc).why)

    def test_follows_waits_for_an_open_panel_and_needs_freecad(self):
        doc = ParamDoc()
        r = self.st({"follows": "size", "object": "Body"}, doc, gui=GuiState(editing="Sketch"))
        self.assertEqual(r.status, "pending")
        self.assertEqual(doc.recomputes, 1)  # nothing tried
        plain = Doc()
        plain.add("VarSet", "App::VarSet", size=Quantity(55.0))
        plain.add("Body", "PartDesign::Body", shape=Shape(1, (1, 1, 1)))
        self.assertEqual(self.st({"follows": "size", "object": "Body"}, plain).status, "pending")
        self.assertTrue(checks.problems({"follows": "size"}, "c"))  # no object
        self.assertTrue(checks.problems({"follows": "size", "object": "B", "change": 5}, "c"))  # change needs axis
        self.assertTrue(checks.problems({"follows": "size", "object": "B", "axis": "w"}, "c"))
        self.assertEqual(checks.problems({"follows": "size", "object": "$body", "by": 5, "axis": "x", "change": 5}, "c"), [])

    def test_sketch_external_and_radii(self):
        doc = Doc()
        g = [type("Arc", (), {"Radius": 14.5})(), type("Circle", (), {"Radius": 10.5})(), type("Line", (), {})()]
        sk = doc.add("Inset", "Sketcher::SketchObject", Geometry=g, ExternalGeometry=[(object(), ("Edge3", "Edge7"))])
        sk.getConstruction = lambda i: False
        self.assertEqual(self.st({"sketch": "Inset", "external": 2, "radii": [14.5, 10.5]}, doc).status, "pass")
        self.assertIn("2 outside edges", self.st({"sketch": "Inset", "external": 3}, doc).why)
        self.assertEqual(self.st({"sketch": "Inset", "radii": [14]}, doc).why, "Inset has no circle or arc of radius 14 mm")
        sk.getConstruction = lambda i: i == 0  # a construction arc does not count
        self.assertEqual(self.st({"sketch": "Inset", "radii": [14.5]}, doc).status, "fail")
        self.assertTrue(checks.problems({"sketch": "S", "radii": [-1]}, "c"))
        self.assertTrue(checks.problems({"sketch": "S", "external": 0}, "c"))

    def test_sketch_progress_count_and_dimensions(self):
        doc = Doc()
        con = lambda t, v, driving=True: type("C", (), {"Type": t, "Value": v, "Driving": driving})()  # noqa: E731
        sk = doc.add("Base", "Sketcher::SketchObject", DoF=3,
                     Geometry=[type("Circle", (), {"Radius": 10.5})(), type("Line", (), {})(), type("Point", (), {})()],
                     Constraints=[con("Coincident", 0), con("DistanceY", 47.0), con("DistanceX", -27.0), con("Distance", 9.0, False)])
        sk.solve = lambda: 0
        sk.getConstruction = lambda i: False
        st = lambda c: self.st(c, doc)  # noqa: E731
        self.assertEqual(st({"sketch": "Base", "dof_max": 3}).status, "pass")
        self.assertEqual(st({"sketch": "Base", "dof_max": 2}).why, "Base has 3 degrees of freedom; the step wants 2 or fewer")
        self.assertEqual(st({"sketch": "Base", "count": 2}).status, "pass")  # the point is not a line or curve
        self.assertIn("has 2 lines or curves", st({"sketch": "Base", "count": 3}).why)
        self.assertEqual(st({"sketch": "Base", "dims": [47, 27]}).status, "pass")  # its sign does not matter
        self.assertEqual(st({"sketch": "Base", "dims": [9]}).why, "Base has no dimension of 9 mm yet")  # a reference one does not count
        self.assertTrue(checks.problems({"sketch": "S", "dof_max": -1}, "c"))
        self.assertTrue(checks.problems({"sketch": "S", "dims": ["a"]}, "c"))

    def test_where_set(self):
        doc = Doc()
        doc.add("GroundedJoint", "App::FeaturePython", ObjectToGround=object())
        doc.add("Fixed", "App::FeaturePython", JointType="Fixed", ObjectToGround=None)
        self.assertEqual(len(checks.find(Context(doc=doc), {"type": "App::FeaturePython", "where": {"ObjectToGround": {"set": True}}})), 1)
        self.assertEqual(self.st({"exists": {"type": "App::FeaturePython", "where": {"JointType": "Fixed"}}}, doc).status, "pass")
        self.assertEqual(checks.problems({"exists": {"type": "A::B", "where": {"X": {"set": True}}}}, "c"), [])
        self.assertTrue(checks.problems({"exists": {"type": "A::B", "where": {"X": {"set": "yes"}}}}, "c"))

    def test_trial_signals_are_not_the_persons(self):
        from agentlink_tutor import observe

        n = observe.BUF.seq
        checks.TRIAL[0] += 1
        try:
            self.assertIsNone(observe.record("rc"))
        finally:
            checks.TRIAL[0] -= 1
        self.assertEqual(observe.BUF.seq, n)


if __name__ == "__main__":
    unittest.main()
