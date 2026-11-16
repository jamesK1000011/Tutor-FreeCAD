# SPDX-License-Identifier: LGPL-2.1-or-later
# The lesson engine's rules hold for every lesson, not only the Pad lesson:
# each is run over the three starter lessons and three synthetic lessons on
# other workbenches with other targets (a Part primitive set in the Property
# view, a TechDraw page, a sketch constraint whose task panel puts its OK
# button before a field named differently). Covered: the hint-ladder lint,
# the second rung's field, the closed-panel recovery, the view set after
# setup and per step, the last rings held once a lesson is done, demo
# opening the panel a step's controls are in, and Model-tree rows found in
# the lesson's own document.
import copy
import json
import os
import types
import unittest

from fakes import Doc, Quantity, Shape
from test_point import Hooks, Overlay, Ann, Win
from test_engine import World as PadWorld
from test_run import Clock, FakeUI

from agentlink_tutor import checks, engine, lessons, point, run, targets, window
from agentlink_tutor.checks import GuiState
from agentlink_tutor.engine import Engine


def starters():
    """Every stored lesson as its file has it, with the chapters before it
    (a course's chapter 2 starts where chapter 1 ended)."""
    out = []
    for n in sorted(os.listdir(lessons.CORE_DIR)):
        if n.endswith(lessons.SUFFIX):
            with open(os.path.join(lessons.CORE_DIR, n), encoding="utf-8") as f:
                out.append(json.load(f))
    have = {l["id"]: l for l in out}
    return [dict(l, _after=lessons.chain(l, have.get)) for l in out]


# What the stand-in world makes for the tools no test spells out: an object
# of the type the tool makes, or nothing (a constraint, a binding, a view).
MAKES = {"pd_fillet": ("Fillet", "PartDesign::Fillet"), "pd_chamfer": ("Chamfer", "PartDesign::Chamfer"),
         "pd_hole": ("Hole", "PartDesign::Hole"), "hw_hole": ("Hole", "PartDesign::Hole"),
         "td_view": ("View", "TechDraw::DrawViewPart"), "asm_new": ("Assembly", "Assembly::AssemblyObject"),
         "param_set": ("Params", "Spreadsheet::Sheet")}


PART_BOX = {
    "schema": 1, "id": "test.part.box", "version": "1.0.0", "title": "A box in Part",
    "setup": {"calls": [{"tool": "doc_new", "args": {"name": "BoxLesson"}}]},
    "vars": {"len": 30},
    "steps": [
        {"id": "bench", "say": "Select the **Part** workbench.", "targets": [{"wb": "PartWorkbench"}],
         "check": {"workbench": "PartWorkbench"}, "do": [{"tool": "workbench", "args": {"activate": "Part"}}]},
        {"id": "box", "say": "Push **Cube**.", "targets": [{"cmd": "Part_Box"}, {"menu": "Part_Box"}],
         "check": {"new": "Part::Box"}, "bind": {"box": {"new": "Part::Box"}},
         "do": [{"tool": "part_box", "args": {}}]},
        {"id": "size", "say": "Set the **Length** of the box to 30 mm in the Property view.",
         "targets": [{"dock": "Property view"}, {"tree": "$box"}],
         "check": {"prop": "$box", "name": "Length", "eq": "$len", "tol": 0.01, "unit": "mm"},
         "hints": ["Find the Property view below the tree.", "Its Length row sets the size along X.", "Length = 30 mm."],
         "do": [{"tool": "obj_set", "args": {"object": "$box", "set": {"Length": "$len"}}}]},
        {"id": "see", "say": "Done: a 30 mm box. Its top face shows in colour.", "targets": [{"face": {"normal": [0, 0, 1]}, "of": "$box"}],
         "check": {"bbox": "$box", "size": [30, 10, 10], "tol": 0.01}},
    ],
}

TD_PAGE = {
    "schema": 1, "id": "test.td.page", "version": "1.0.0", "title": "A TechDraw page", "view": "keep",
    "setup": {"calls": [{"tool": "doc_new", "args": {"name": "PageLesson"}}]},
    "steps": [
        {"id": "bench", "say": "Select the **TechDraw** workbench.", "targets": [{"wb": "TechDrawWorkbench"}],
         "check": {"workbench": "TechDrawWorkbench"}, "do": [{"tool": "workbench", "args": {"activate": "TechDraw"}}]},
        {"id": "page", "say": "Push **Insert Default Page**.", "targets": [{"cmd": "TechDraw_PageDefault"}, {"menu": "TechDraw_PageDefault"}],
         "check": {"exists": "TechDraw::DrawPage"}, "hints": ["Look at the first button of the TechDraw toolbar.", "The ring shows the button."],
         "do": [{"tool": "td_page", "args": {}}]},
    ],
}

CONSTRAINT = {
    "schema": 1, "id": "test.sk.constraint", "version": "1.0.0", "title": "Set a distance", "view": "top",
    "setup": {"calls": [{"tool": "doc_new", "args": {"name": "SketchLesson"}}, {"tool": "sketch_new", "args": {}}],
              "bind": {"sketch": {"exists": "Sketcher::SketchObject"}}},
    "vars": {"d": 12},
    "steps": [
        {"id": "datum", "say": "Set the length of the line to 12 mm. Push **OK**.",
         # OK listed first, the field second and named its own way.
         "targets": [{"task": {"button": "ok"}}, {"task": {"name": "labelEdit", "label": "Datum"}}],
         "check": {"all": [{"prop": "$sketch", "name": "Datum", "eq": "$d", "tol": 0.01, "unit": "mm"}, {"task_open": None}]},
         "hints": ["Look at the dialog of the constraint.", "Its Datum box holds the length.", "Datum = 12 mm."],
         "do": [{"tool": "sketch_constrain", "args": {"sketch": "$sketch", "value": "$d"}}]},
    ],
}

SYNTHETIC = [PART_BOX, TD_PAGE, CONSTRAINT]


class World(PadWorld):
    """The stand-in tools of test_engine (Part Design) and enough more for the
    synthetic lessons, on a plain document."""

    def __init__(self):
        super().__init__()
        self.gui = GuiState("StartWorkbench")

    def __call__(self, name, args):
        mine = ("workbench", "part_box", "obj_set", "td_page", "sketch_constrain")
        if name not in mine and not (name == "sketch_new" and not any(o.TypeId == "PartDesign::Body" for o in self.doc.Objects)):
            refused, out = super().__call__(name, args)
            if refused and (out.get("error") or {}).get("code") == "not_found":
                self.calls.pop()
                return self.generic(name, args)
            return refused, out
        self.calls.append((name, args))
        if name == "workbench":
            self.gui.workbench = {"Part": "PartWorkbench", "TechDraw": "TechDrawWorkbench"}.get(args.get("activate"), "PartDesignWorkbench")
        elif name == "part_box":
            self.doc.add("Box", "Part::Box", Length=Quantity(10.0), shape=Shape(1000, (10, 10, 10)))
        elif name == "obj_set":
            o = self.doc.getObject(args["object"])
            for k, v in args["set"].items():
                setattr(o, k, Quantity(float(v)))
            o.Shape = Shape(o.Length.Value * 100, (o.Length.Value, 10, 10))
        elif name == "td_page":
            self.doc.add("Page", "TechDraw::DrawPage")
        elif name == "sketch_new":
            self.doc.add("Sketch", "Sketcher::SketchObject", Datum=Quantity(5.0))
            self.gui.editing, self.gui.task = "Sketch", "Sketcher_SketchObject"  # as the echo opens it
        elif name == "sketch_constrain" and "value" in args:
            self.doc.getObject(args["sketch"]).Datum = Quantity(float(args["value"]))
            self.gui.editing = self.gui.task = None
        return False, {}

    def generic(self, name, args):
        """Any other tool: it goes through, making what it makes."""
        self.calls.append((name, args))
        made = MAKES.get(name)
        if made and not (name == "param_set" and self.doc.getObject("Params")):
            o = self.doc.add(made[0], made[1], shape=Shape(1, (1, 1, 1)))
            return False, {"made": o.Name}
        return False, {}


def controller(lesson, mode="guided", show=None, world=None, timer=None):
    w = world or World()
    e = Engine(copy.deepcopy(lesson), call=w, doc=lambda: w.doc, gui=lambda: w.gui)
    c = run.Controller(e, timer=timer, show=show, ui=FakeUI(w))
    c.start(mode)
    return w, c


def at_step(c, sid):
    while c.e.step["id"] != sid:
        c.act("skip")


def task_steps(lesson):
    return [s for s in lesson["steps"] if run.task_targets(s)]


class Lint(unittest.TestCase):
    def test_every_lesson_is_valid_and_keeps_the_ladder(self):
        for lesson in starters() + SYNTHETIC:
            with self.subTest(lesson=lesson["id"]):
                self.assertEqual(lessons.check(lesson), [])
                self.assertEqual(lessons.hint_problems(lesson), [])

    def test_installed_lessons_are_all_loaded(self):
        lib = lessons.core_library()
        self.assertEqual(lib.refused, [])
        self.assertEqual(len(lib.lessons()), len(starters()))
        self.assertGreaterEqual(len(lib.lessons()), 11)

    def test_rung_two_giving_the_value_away_is_refused(self):
        for lesson, sid, i, leak in ((PART_BOX, "size", 1, "Type 30 into its Length row."),
                                     (CONSTRAINT, "datum", 0, "Make it 12.0 long."),
                                     (next(l for l in starters() if l["id"].endswith("export-stl")), "export", 1, "Call it Part.stl.")):
            bad = copy.deepcopy(lesson)
            step = next(s for s in bad["steps"] if s["id"] == sid)
            step["hints"][i] = leak
            with self.subTest(lesson=lesson["id"]):
                problems = lessons.check(bad)
                self.assertTrue(any(f"hints[{i}]" in p and "gives away" in p for p in problems), problems)
        # Other numbers are fine: "Step 2", 1.5 and 300 are not 30.
        self.assertEqual(lessons.reveals("Step 2 of the 300 mm, 1.5 turns", {30.0}), [])

    def test_the_library_leaves_a_leaking_lesson_out(self):
        import shutil
        import tempfile

        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        bad = copy.deepcopy(PART_BOX)
        bad["id"] = "mine.part.box"
        next(s for s in bad["steps"] if s["id"] == "size")["hints"][1] = "Type 30."
        with open(os.path.join(d, "box.lesson.json"), "w", encoding="utf-8") as f:
            json.dump(bad, f)
        lib = lessons.Library()
        lib.add_folder(d, "mine")
        self.assertEqual(lib.lessons(), {})
        self.assertIn("gives away 30", lib.refused[0][1])


class SecondRung(unittest.TestCase):
    def test_the_field_only_whatever_its_name_or_place(self):
        for lesson in starters() + SYNTHETIC:
            for s in lesson["steps"]:
                if not s.get("targets"):
                    continue
                with self.subTest(lesson=lesson["id"], step=s["id"]):
                    got = engine.field_target(s["targets"])
                    tasks = [t for t in s["targets"] if "task" in t and not (isinstance(t["task"], dict) and t["task"].get("button"))]
                    self.assertEqual(got, tasks[0] if tasks else s["targets"][0])
        w, c = controller(CONSTRAINT)
        for _ in range(2):
            c.act("hint")
        self.assertEqual(c.e.hint_targets(), [{"task": {"name": "labelEdit", "label": "Datum"}}])
        self.assertEqual(c.act("hint")["hint_text"], "Datum = 12 mm.")


class ClosedPanel(unittest.TestCase):
    def check_recovery(self, lesson, sid, obj_name, label):
        w, c = controller(lesson)
        at_step(c, sid)
        doc = c.e._doc()
        if doc.getObject(obj_name) is None:
            doc.add(obj_name, "Some::Feature", label=label)
        # The step's objects (its bindings, whatever the lesson calls them) are the feature.
        c.e.bindings.update({k: obj_name for k in lessons.refs(c.e.step) if k not in (lesson.get("vars") or {})})
        w.gui.task = None  # OK pressed with another value: the panel is gone
        tg, words = c.shown()
        self.assertEqual(tg[0], {"tree": obj_name})
        self.assertFalse(any("task" in t for t in tg))
        self.assertEqual(words, f"Double-click {label} in the tree to change it.")
        self.assertIn(words, c.callout())
        w.gui.task = "Something_Open"  # the person opened it again
        self.assertEqual(c.shown()[0], c.e.hint_targets())

    def test_every_task_panel_step(self):
        cases = [(l, s["id"]) for l in starters() + SYNTHETIC for s in task_steps(l)]
        self.assertGreaterEqual(len(cases), 3)  # pad's length, pocket's depth, the constraint's datum
        for lesson, sid in cases:
            with self.subTest(lesson=lesson["id"], step=sid):
                self.check_recovery(lesson, sid, "Feat", "My Feature")

    def test_no_feature_no_recovery_and_demo_opens_instead(self):
        w, c = controller(CONSTRAINT)
        w.doc.remove("Sketch")
        w.gui.task = None
        self.assertEqual(c.shown(), (c.e.hint_targets(), None))
        w, c = controller(CONSTRAINT, mode="demo")
        self.assertIn(("open", "Sketch"), c.ui.log)  # demo opens the sketch's panel (its do names the sketch)
        self.assertEqual(c.shown()[1], None)

    def test_edit_target_from_the_check_when_there_is_no_do(self):
        lesson = copy.deepcopy(CONSTRAINT)
        lesson["steps"][0].pop("do")
        lesson["steps"][0]["hints"] = lesson["steps"][0]["hints"][:2]
        w, c = controller(lesson)
        self.assertEqual(run.edit_target(c.e), "Sketch")


class Views(unittest.TestCase):
    def frames(self, c):
        return [x[1] for x in c.ui.log if isinstance(x, tuple) and x[0] == "frame"]

    def test_setup_frames_the_part_for_every_lesson(self):
        for lesson in starters() + SYNTHETIC:
            with self.subTest(lesson=lesson["id"]):
                w, c = controller(lesson, mode="demo")
                want = lesson.get("view", "isometric")
                self.assertEqual(c.ui.log[0], "settle")
                if want == "keep":
                    self.assertEqual(self.frames(c), [])
                else:
                    self.assertEqual(self.frames(c)[0], want)

    def test_steps_lighting_faces_take_the_lessons_view(self):
        for lesson in starters() + SYNTHETIC:
            for s in lesson["steps"]:
                spatial = any(k in t for t in s.get("targets") or () for k in run.SPATIAL)
                with self.subTest(lesson=lesson["id"], step=s["id"]):
                    v = run.step_view(lesson, s)
                    want = s.get("view") or (lesson.get("view", "isometric") if spatial else None)
                    self.assertEqual(v, None if want == "keep" else want)
        w, c = controller(PART_BOX)
        at_step(c, "see")
        self.assertEqual(self.frames(c)[-1], "isometric")

    def test_a_steps_own_view(self):
        lesson = copy.deepcopy(TD_PAGE)
        lesson["steps"][1]["view"] = "front"
        w, c = controller(lesson)
        self.assertEqual(self.frames(c), [])
        c.act("skip")
        self.assertEqual(self.frames(c), ["front"])
        self.assertIn("view", lessons.schema()["definitions"]["step"]["properties"])


class Held(unittest.TestCase):
    def test_last_rings_held_until_stop_or_hold_time(self):
        for lesson in starters() + SYNTHETIC:
            with self.subTest(lesson=lesson["id"]):
                shows = []
                clock = Clock()
                w, c = controller(lesson, show=lambda ctl: shows.append(ctl if ctl is None else ctl.e.step["id"]) or {"resolved": 1, "missing": []},
                                  timer=clock)
                while c.e.state == "step":
                    c.act("skip")
                last = shows[-1]
                self.assertIsNotNone(last)  # done: not cleared at once
                self.assertEqual([ms for ms, _fn in clock.due if ms == run.HOLD_MS], [run.HOLD_MS])
                clock.flush()
                self.assertIsNone(shows[-1])  # 10 s later
        w, c = controller(TD_PAGE, show=lambda ctl: shows.append(ctl) or {}, timer=Clock())
        while c.e.state == "step":
            c.act("skip")
        c.act("stop")
        self.assertIsNone(shows[-1])  # Stop clears at once


class TreeInLessonDoc(unittest.TestCase):
    def setUp(self):
        from test_point import FakeTree, LiveItem

        self.FakeTree, self.Item = FakeTree, LiveItem
        self.was = window._qt
        window._qt = lambda: (None, None, types.SimpleNamespace(QTreeWidget=object))

    def tearDown(self):
        window._qt = self.was

    def test_the_lesson_documents_row_never_another_documents(self):
        for label in ("Sketch", "Box", "Page"):  # any object, any workbench
            with self.subTest(label=label):
                mine, other = self.Item(label), self.Item(label)
                app = self.Item("Application", self.Item("WindowTest", self.Item("Body", other)), self.Item("Lesson", self.Item("Body", mine)))
                tree = self.FakeTree(app)
                tree.visualItemRect = lambda it, m=mine: types.SimpleNamespace(x=lambda: 0, y=lambda: 40 if it is m else 0,
                                                                               width=lambda: 100, height=lambda: 18)
                mw = types.SimpleNamespace(findChildren=lambda cls: [tree])
                ldoc = types.SimpleNamespace(Label="Lesson", getObject=lambda n: obj if n == label else None, Objects=[])
                obj = types.SimpleNamespace(Name=label, Label=label, Document=ldoc)
                win = window.Window(gui=types.SimpleNamespace(getMainWindow=lambda: mw), hooks=object(), doc=lambda: ldoc)
                self.assertIs(win.obj(label), obj)
                got, note = win.tree_row(obj)
                self.assertEqual(got["rect"](), (0, 40, 100, 18))
                # Not in the lesson's document at all: not found, never the other one's row.
                gone = types.SimpleNamespace(Name="X", Label=label, Document=types.SimpleNamespace(Label="Lesson"))
                mine.t = "Renamed"
                self.assertEqual(win.tree_row(gone), (None, f"{label} is not in the Model tree under Lesson (Lesson holds: Body)"))

    def test_hidden_tree_rings_the_model_tab(self):
        tree = self.FakeTree(self.Item("Application"), visible=False)
        win = window.Window(gui=types.SimpleNamespace(getMainWindow=lambda: types.SimpleNamespace(findChildren=lambda c: [tree])), hooks=object())
        win._tab_header = lambda w: {"widget": "model-tab"}
        obj = types.SimpleNamespace(Name="Box", Label="Box", Document=types.SimpleNamespace(Label="Lesson"))
        self.assertEqual(win.tree_row(obj), ({"widget": "model-tab"}, window.MODEL_TAB))

    def test_the_callout_says_open_the_model_tab(self):
        w = Win(rows={"Sketch": ({"widget": "model-tab"}, window.MODEL_TAB)})
        out = point.point({"targets": [{"tree": "Sketch"}], "say": "Click it."}, w, hooks=Hooks(Overlay(), Ann()))
        self.assertEqual(out["shown"][0]["kind"], "tree")
        f = targets.resolve({"tree": "Sketch"}, 1, w, {})
        self.assertEqual(f.text, "Open the Model tab.")


class NoPadShortcuts(unittest.TestCase):
    def test_engine_names_no_lesson_object_or_command(self):
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agentlink_tutor")
        for n in ("engine.py", "run.py", "live.py", "tool.py", "gui_run.py"):
            with open(os.path.join(here, n), encoding="utf-8") as f:
                src = f.read()
            for word in ("PartDesign_Pad", "PartDesign::Pad", "lengthEdit", "pad-sketch", '"Pad"', "'Pad'"):
                with self.subTest(file=n, word=word):
                    self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
