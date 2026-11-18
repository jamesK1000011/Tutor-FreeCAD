# SPDX-License-Identifier: LGPL-2.1-or-later
# The lesson engine without FreeCAD: a stand-in world answers the tool calls
# on a plain document, so the state machine, bindings, hints and branches
# are tested here; tests/test_replay_fc.py does the same against FreeCAD.
import json
import os
import types
import unittest

from fakes import Doc, Quantity, Shape, Wire

from agentlink_tutor import engine, lessons
from agentlink_tutor.checks import GuiState
from agentlink_tutor.engine import Engine, TutorError, resolve


class World:
    """Just enough of Agent Link's tools for the pad lesson, on a Doc."""

    def __init__(self):
        self.doc = Doc()
        self.gui = None
        self.calls = []
        self.undo = []
        # As Agent Link's echo in the window: a new sketch is opened in the Sketcher.
        self.opens_sketch = False

    def body(self):
        return next(o for o in self.doc.Objects if o.TypeId == "PartDesign::Body")

    def refresh(self):
        b = self.body()
        L = sum(o.Length.Value for o in b.Group if o.TypeId == "PartDesign::Pad")
        D = sum(o.Length.Value for o in b.Group if o.TypeId == "PartDesign::Pocket")
        b.Shape = Shape(40 * 20 * (L - D), (40, 20, L - D))
        for o in b.Group:
            if o.TypeId.startswith("PartDesign::"):
                o.Shape = b.Shape

    def __call__(self, name, args):
        self.calls.append((name, args))
        if name == "doc_new":
            self.doc = Doc()
            return False, {"document": args.get("name")}
        if name == "pd_body_new":
            self.doc.add("Body", "PartDesign::Body", shape=Shape(0, solids=0))
            return False, {"body": "Body"}
        if name == "sketch_new":
            sk = self.doc.add("Sketch", "Sketcher::SketchObject", inside=self.body(), shape=Shape(0, solids=0), DoF=0)
            sk.solve = lambda: 0
            if self.opens_sketch and self.gui is not None:
                self.gui.editing, self.gui.task = sk.Name, "Sketcher_SketchObject"
            return False, {"sketch": sk.Label}
        if name == "sketch_add":
            sk = next(o for o in self.doc.Objects if o.TypeId == "Sketcher::SketchObject")
            sk.Shape = Shape(0, solids=0, wires=[Wire(True)])
            return False, {"sketch": sk.Label}
        if name in ("pd_pad", "pd_pocket"):
            kind = "Pad" if name == "pd_pad" else "Pocket"
            f = self.doc.add(kind, f"PartDesign::{kind}", inside=self.body(), Length=Quantity(float(args["length"])))
            self.undo.append(f.Name)
            self.refresh()
            return False, {"feature": f.Label}
        if name == "feature_edit":
            f = self.doc.getObject(args["feature"])
            for k, v in args["set"].items():
                setattr(f, k, Quantity(float(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
            self.refresh()
            return False, {"feature": f.Label}
        if name == "history_undo":
            n = self.undo.pop()
            self.body().Group = [o for o in self.body().Group if o.Name != n]
            self.doc.remove(n)
            self.refresh()
            return False, {"undone": 1}
        if name in ("workbench", "selection"):
            if self.gui is None:
                return True, {"error": {"code": "unavailable", "message": "This FreeCAD has no window"}}
            if name == "workbench":
                self.gui.workbench = "PartDesignWorkbench"
            else:
                self.gui.selection = [(n, []) for n in args["objects"]]
            return False, {}
        return True, {"error": {"code": "not_found", "message": f"no tool {name}"}}


def pad_lesson():
    with open(os.path.join(lessons.CORE_DIR, "pad-sketch.lesson.json"), encoding="utf-8") as f:
        return json.load(f)


def make(world=None, **kw):
    w = world or World()
    e = Engine(pad_lesson(), call=w, doc=lambda: w.doc, gui=lambda: w.gui, **kw)
    return w, e


class Resolve(unittest.TestCase):
    def test_vars_swapped_types_kept(self):
        b = {"pad": "Pad001", "length": 15}
        self.assertEqual(resolve({"feature": "$pad", "set": {"Length": "$length"}, "x": ["$pad", "$pad2", "a$pad"]}, b),
                         {"feature": "Pad001", "set": {"Length": 15}, "x": ["Pad001", "$pad2", "a$pad"]})


class StateMachine(unittest.TestCase):
    def test_setup_binds_and_enters_first_step(self):
        w, e = make()
        w.doc.Name = w.doc.Label = "Unnamed"
        st = e.start("demo")
        # The open document is empty: the lesson works in it (no doc_new).
        self.assertEqual([c[0] for c in w.calls], ["pd_body_new", "sketch_new", "sketch_add"])
        self.assertEqual(st["document"], "the lesson works in Unnamed: it was open and empty")
        self.assertEqual(e.bindings, {"length": 15, "sketch": "Sketch", "body": "Body"})
        self.assertEqual((st["step"], st["id"], st["check"], st["hint"]), ("1/5", "bench", "pending", 0))
        e.next()
        self.assertNotIn("document", e.status())  # said once, at the first step
        self.assertEqual(st["targets"], 1)

    def test_demo_walk_with_a_window(self):
        w, e = make()
        w.gui = GuiState("StartWorkbench")
        e.start("demo")
        seen = []
        while e.state == "step":
            st = e.do() if e.step.get("do") else e.check()
            self.assertEqual(st["check"], "pass", st)
            seen.append(st["id"])
            e.next()
        self.assertEqual(seen, ["bench", "pick", "pad", "length", "see"])
        self.assertEqual(e.bindings["pad"], "Pad")
        self.assertEqual(e.status(), {"lesson": "agentlink_tutor.pd.pad-sketch", "mode": "demo", "explain": "on", "step": "done",
                                      "finished": "lesson complete", "final": {"step": "see", "check": "pass"}, "skipped": [],
                                      "done_for": ["bench", "length", "pad", "pick"]})

    def test_headless_window_steps_wait_and_the_rest_pass(self):
        w, e = make()
        e.start("demo")
        st = e.check()
        self.assertEqual((st["check"], st["why"]), ("pending", "needs the FreeCAD window"))
        with self.assertRaises(TutorError):
            e.do()  # workbench is refused without a window
        e.next()
        e.next()
        self.assertEqual(e.do()["check"], "pass")  # pad
        e.next()
        self.assertEqual(e.do()["check"], "pass")  # length: task_open null holds without a window
        e.next()
        self.assertEqual(e.check()["check"], "pass")
        e.next()
        self.assertEqual(e.state, "done")
        self.assertEqual(e.status()["skipped"], ["bench", "pick"])

    def test_wrong_value_fails_with_why(self):
        w, e = make()
        e.start("guided")
        e.next(), e.next()
        w("pd_pad", {"length": 10})  # the person presses Pad
        self.assertEqual(e.check()["check"], "pass")
        e.next()
        w("feature_edit", {"feature": "Pad", "set": {"Length": 20}})
        st = e.check()
        self.assertEqual(st["check"], "fail")
        self.assertEqual(st["why"], "Length is 20 mm; the step wants 15 mm")

    def test_bindings_follow_what_the_person_made(self):
        w, e = make()
        e.start("guided")
        w.doc.add("Pad", "PartDesign::Pad", shape=Shape(1))  # a Pad left over from before the step
        e.next(), e.next()
        w("pd_pad", {"length": 10})
        e.check()
        self.assertEqual(e.bindings["pad"], "Pad001")
        e.next()
        w("feature_edit", {"feature": "Pad001", "set": {"Length": 15}})
        self.assertEqual(e.check()["check"], "pass")

    def test_back_and_position(self):
        w, e = make()
        e.start("guided")
        e.next()
        self.assertEqual(e.status()["step"], "2/5")
        e.back()
        self.assertEqual(e.status()["id"], "bench")
        e.back()  # nothing before the first step
        self.assertEqual(e.status()["id"], "bench")

    def test_branch_to_detour_and_back(self):
        w, e = make()
        e.start("guided")
        e.next(), e.next()
        w("pd_pocket", {"length": 5})  # the wrong button
        st = e.check()
        self.assertEqual((st["id"], st["say"], st["step"]), ("undo-pocket", "That was Pocket, which cuts. Undo it.", "3/5"))
        self.assertEqual(e.check()["check"], "fail")
        w("history_undo", {})
        self.assertEqual(e.check()["check"], "pass")
        st = e.next()
        self.assertEqual((st["id"], st["say"]), ("pad", "Push **Pad**."))
        w("pd_pad", {"length": 10})
        self.assertEqual(e.check()["check"], "pass")

    def test_detours_are_not_on_the_main_path(self):
        w, e = make()
        e.start("guided")
        ids = []
        while e.state == "step":
            ids.append(e.step["id"])
            e.next()
        self.assertNotIn("undo-pocket", ids)

    def test_hint_ladder(self):
        w, e = make()
        e.start("guided")
        e.next()  # pick: two hints, a do
        e.check()
        st = e.raise_hint()
        self.assertEqual((st["hint"], st["hint_text"]), (1, "Look under Body in the Model tab, on the left."))
        self.assertNotIn("do_it", st)
        st = e.raise_hint()
        self.assertEqual((st["hint"], st["hint_text"]), (2, "The ring shows its row."))
        st = e.raise_hint()
        self.assertEqual(st["hint"], 3)
        self.assertTrue(st["do_it"])
        self.assertEqual(e.raise_hint()["hint"], 3)  # the top rung
        e.next()
        self.assertEqual(e.status()["hint"], 0)  # each step starts again

    def test_hint_without_hints_uses_the_why(self):
        w, e = make()
        e.start("guided")
        for _ in range(4):
            e.next()
        e.check()
        self.assertEqual(e.raise_hint()["hint_text"], e.result.why + ".")

    def test_progress_marked_when_done(self):
        p = lessons.Progress(params=lessons._Memory())
        w, e = make(progress=p)
        e.start("guided")
        while e.state == "step":
            e.next()
        self.assertTrue(p.done("agentlink_tutor.pd.pad-sketch", "1.0.0"))

    def test_status_stays_small(self):
        w, e = make()
        e.start("guided")
        e.lesson["steps"][0]["say"] = "x" * 240
        e.lesson["steps"][0]["hints"] = ["y" * 240]
        e.check()
        e.raise_hint()
        st = e.status(detail=True)
        self.assertLessEqual(len(json.dumps(st, ensure_ascii=False)), engine.STATE_MAX)
        self.assertIn("say", st)

    def test_modes(self):
        with self.assertRaises(TutorError):
            make()[1].start("lecture")
        self.assertEqual(Engine().start("watch"), {"state": "watch", "mode": "watch"})
        with self.assertRaises(TutorError):
            Engine().start("guided")
        w, e = make()
        e.start("guided")
        self.assertEqual(e.stop(), {"state": "stopped", "mode": "guided"})
        with self.assertRaises(TutorError):
            e.next()

    def test_setup_refusal_stops_the_start(self):
        w, e = make()
        e.lesson["setup"]["calls"].insert(0, {"tool": "nope", "args": {}})
        with self.assertRaises(TutorError) as x:
            e.start("demo")
        self.assertIn("no tool nope", str(x.exception))

    def test_inline_lesson_runs(self):
        l = lessons.inline({"id": "inline.pad", "title": "Pad it", "setup": {"calls": [{"tool": "pd_body_new"}]},
                            "steps": [{"id": "s", "say": "Make a body.", "check": {"exists": "PartDesign::Body"}}]})
        w = World()
        e = Engine(l, call=w, doc=lambda: w.doc)
        self.assertEqual(e.start("guided")["step"], "1/1")
        self.assertEqual(e.check()["check"], "pass")


class ElseCalls(unittest.TestCase):
    """A call's else: done instead when the call is refused (a newer tool
    this Agent Link lacks, or a document made the other way)."""

    def lesson(self):
        return lessons.inline({"id": "inline.else", "title": "Else", "setup": {"calls": [
            {"tool": "varset_new", "args": {"name": "VarSet", "properties": {"size": "55 mm"}},
             "else": [{"tool": "pd_body_new"}]}]},
            "steps": [{"id": "s", "say": "Make a body.", "check": {"exists": "PartDesign::Body"}}]})

    def test_refused_call_runs_its_else(self):
        w = World()
        e = Engine(self.lesson(), call=w, doc=lambda: w.doc)
        e.start("guided")
        self.assertEqual([c[0] for c in w.calls], ["varset_new", "pd_body_new"])
        self.assertEqual(e.check()["check"], "pass")

    def test_answered_call_skips_its_else(self):
        w = World()
        calls = []

        def call(name, args):
            calls.append(name)
            if name == "varset_new":
                w.doc.add("Body", "PartDesign::Body")
                return False, {"varset": "VarSet"}
            return w(name, args)
        e = Engine(self.lesson(), call=call, doc=lambda: w.doc)
        e.start("guided")
        self.assertEqual(calls, ["varset_new"])

    def test_else_refused_too_stops(self):
        l = self.lesson()
        l["setup"]["calls"][0]["else"] = [{"tool": "nope"}]
        w = World()
        with self.assertRaises(TutorError) as x:
            Engine(l, call=w, doc=lambda: w.doc).start("demo")
        self.assertIn("else of varset_new", str(x.exception))
        self.assertIn("no tool nope", str(x.exception))

    def test_checked(self):
        l = self.lesson()
        tools = {"pd_body_new"}  # an Agent Link without varset_new: its else stands in
        self.assertEqual(lessons.check(l, tools), [])
        self.assertEqual(lessons.check(l, set()), ["setup.calls[0]: no tool varset_new", "setup.calls[0].else[0]: no tool pd_body_new"])
        l["setup"]["calls"][0]["else"] = [{"tool": "pd_body_new", "else": [{"tool": "x"}]}, {"args": {}}]
        got = lessons.check(l)
        self.assertIn("setup.calls[0].else[0]: an else call holds tool and args only (not else)", got)
        self.assertIn("setup.calls[0].else[1]: a call {tool, args}", got)


class PartialDo(unittest.TestCase):
    """Live finding 53: a step's do refused after its first call ran was
    run again on each Next, and added that call's geometry every time."""

    def lesson(self):
        return lessons.inline({"id": "inline.partial", "title": "Partial", "setup": {"doc": "new"}, "vars": {"edge": 17},
                               "steps": [{"id": "s", "say": "Make a body.", "check": {"exists": "PartDesign::Pad"},
                                          "do": [{"tool": "pd_body_new"}, {"tool": "nope"}]}]})

    def test_refused_partway_is_not_run_again(self):
        w = World()
        e = Engine(self.lesson(), call=w, doc=lambda: w.doc)
        e.start("demo")
        n = len(w.calls)
        with self.assertRaises(TutorError) as x:
            e.do()
        self.assertIn("ran and stay", str(x.exception))
        self.assertEqual([c[0] for c in w.calls[n:]], ["pd_body_new", "nope"])
        for _ in range(3):
            with self.assertRaises(TutorError) as x:
                e.do()
            self.assertIn("not run again", str(x.exception))
        self.assertEqual(len(w.calls), n + 2)  # no call ran twice

    def test_a_do_that_ran_is_checked_again_not_run_again(self):
        l = self.lesson()
        l["steps"][0]["do"] = [{"tool": "pd_body_new"}]
        l["steps"][0]["check"] = {"exists": "PartDesign::Body"}
        w = World()
        e = Engine(l, call=w, doc=lambda: w.doc)
        e.start("demo")
        n = len(w.calls)
        e.do()
        e.result = types.SimpleNamespace(status="pending")  # the window could not tell yet
        e.do()
        self.assertEqual(len(w.calls), n + 1)

    def test_a_binding_named_like_a_variable_is_refused(self):
        l = self.lesson()
        l["steps"][0]["bind"] = {"edge": {"new": "Sketcher::SketchObject"}}
        self.assertIn("steps.s.bind.edge: a binding has the name of a variable (the object then takes the variable's place)", lessons.check(l))


if __name__ == "__main__":
    unittest.main()
