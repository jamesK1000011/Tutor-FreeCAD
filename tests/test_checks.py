# SPDX-License-Identifier: LGPL-2.1-or-later
# The check vocabulary against a plain stand-in document, no FreeCAD.
import os
import tempfile
import unittest

from fakes import Doc, Quantity, Shape, Wire

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
        self.assertIn("Pocket", r.why)
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
        self.assertIn("SketcherWorkbench workbench is active", evaluate({"workbench": "PartDesignWorkbench"}, ctx).why)
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


if __name__ == "__main__":
    unittest.main()
