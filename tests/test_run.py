# SPDX-License-Identifier: LGPL-2.1-or-later
# A lesson running (run.Controller) without FreeCAD: demo and guided modes,
# the debounced re-check and the auto-advance on a stand-in timer, the hint
# ladder, branches, mode switches mid-lesson and the rider line.
import json
import unittest

from test_engine import World, pad_lesson

from agentlink_tutor import engine, run
from agentlink_tutor.checks import GuiState
from agentlink_tutor.engine import Engine, TutorError


class Clock:
    """timer(ms, fn) kept until flush()."""

    def __init__(self):
        self.due = []

    def __call__(self, ms, fn):
        self.due.append((ms, fn))

    def flush(self):
        n = 0
        while self.due:
            _ms, fn = self.due.pop(0)
            fn()
            n += 1
        return n


class FakeUI:
    """The lesson's window hands on the stand-in world's window state."""

    def __init__(self, world):
        self.w = world
        self.log = []

    def settle(self):
        self.log.append("settle")
        g = self.w.gui
        if g is not None:
            g.editing = g.task = None
            g.selection = []

    def frame(self, view, doc=None):
        self.log.append(("frame", view))

    def open_task(self, e):
        name = run.edit_target(e)
        self.log.append(("open", name))
        if self.w.gui is not None and self.w.gui.task is None and name:
            self.w.gui.editing, self.w.gui.task = name, "PartDesign_Pad"

    def close_task(self):
        self.log.append("close")
        if self.w.gui is not None:
            self.w.gui.editing = self.w.gui.task = None


class Who:
    def __init__(self, by):
        self.by = by


AGENT, PERSON = Who("agent"), Who("person")


def make(timer=None, show=None, window=True):
    w = World()
    if window:
        w.gui = GuiState("StartWorkbench")
    e = Engine(pad_lesson(), call=w, doc=lambda: w.doc, gui=lambda: w.gui)
    return w, run.Controller(e, timer=timer, show=show)


def act(w, c, tool, args, who=PERSON):
    """A call through the tools, then Agent Link's call_done for it."""
    refused, _ = w(tool, args)
    c.call_done(who, tool, not refused, True)


class Guided(unittest.TestCase):
    def test_walk_by_hand_advances_itself(self):
        clock = Clock()
        w, c = make(timer=clock)
        c.start("guided")
        act(w, c, "workbench", {"activate": "Part Design"})
        self.assertEqual(c.state()["check"], "pass")
        self.assertEqual(c.e.step["id"], "bench")  # not yet: 600 ms later
        self.assertEqual([ms for ms, _ in clock.due], [run.ADVANCE_MS])
        clock.flush()
        self.assertEqual(c.e.step["id"], "pick")
        act(w, c, "selection", {"objects": ["Sketch"]})
        clock.flush()
        act(w, c, "pd_pad", {"sketch": "Sketch", "length": 10})
        clock.flush()
        act(w, c, "feature_edit", {"feature": "Pad", "set": {"Length": 15}})
        clock.flush()
        self.assertEqual(c.e.step["id"], "see")
        st = c.act("next")
        self.assertEqual(st["step"], "done")
        self.assertEqual(st["skipped"], [])
        self.assertNotIn("done_for", st)  # every step the person's

    def test_the_agents_own_call_is_done_for_the_person(self):
        w, c = make()
        c.start("guided")
        c.act("next"), c.act("next")  # bench, pick: left (skipped)
        act(w, c, "pd_pad", {"sketch": "Sketch", "length": 10}, who=AGENT)
        self.assertEqual(c.e.step["id"], "length")  # no timer: on at once
        self.assertEqual(c.e.done_for, {"pad"})

    def test_debounced_poke(self):
        clock = Clock()
        w, c = make(timer=clock)
        c.start("guided")
        w.gui.workbench = "PartDesignWorkbench"  # the person picks it in the selector
        for _ in range(5):
            c.poke()
        self.assertEqual([ms for ms, _ in clock.due], [run.DEBOUNCE_MS])
        clock.due.pop(0)[1]()
        self.assertEqual(c.state()["check"], "pass")
        self.assertEqual([ms for ms, _ in clock.due], [run.ADVANCE_MS])
        clock.flush()
        self.assertEqual(c.e.step["id"], "pick")
        c.poke()
        self.assertEqual(len(clock.due), 1)  # a new round once the last fired

    def test_advance_dropped_when_the_person_moves_or_undoes(self):
        clock = Clock()
        w, c = make(timer=clock)
        c.start("guided")
        act(w, c, "workbench", {})
        c.act("hint")  # any move drops the waiting advance
        clock.flush()
        self.assertEqual(c.e.step["id"], "bench")
        c.act("next"), c.act("next")
        act(w, c, "pd_pad", {"sketch": "Sketch", "length": 10})
        w("history_undo", {})  # undone before the 600 ms
        clock.flush()
        self.assertEqual((c.e.step["id"], c.state()["check"]), ("pad", "fail"))

    def test_nothing_while_the_engine_calls_or_for_the_tutors_own(self):
        w, c = make()
        c.start("guided")
        w.gui.workbench = "PartDesignWorkbench"
        c.call_done(AGENT, "tutor", True, False)
        c.call_done(AGENT, "pd_pad", False, False)  # refused
        self.assertEqual(c.state()["check"], "pending")
        c.busy = True
        c.call_done(PERSON, "workbench", True, False)
        c.poke()
        self.assertEqual(c.state()["check"], "pending")

    def test_branch_and_back(self):
        w, c = make()
        c.start("guided")
        c.act("next"), c.act("next")
        act(w, c, "pd_pocket", {"length": 5})
        st = c.state()
        self.assertEqual((st["id"], st["step"]), ("undo-pocket", "3/5"))
        self.assertIn("Pocket", st["say"])
        act(w, c, "history_undo", {})
        self.assertEqual(c.e.step["id"], "pad")  # the detour passed: back where it came from
        act(w, c, "pd_pad", {"sketch": "Sketch", "length": 10})
        self.assertEqual(c.e.step["id"], "length")


class Demo(unittest.TestCase):
    def test_next_does_the_step_then_waits(self):
        calls = []
        w, c = make(show=lambda ctl: calls.append(ctl.callout()) or {"resolved": 1, "missing": []})
        st = c.start("demo")
        self.assertEqual((st["id"], st["check"]), ("bench", "pending"))
        st = c.act("next")
        self.assertEqual((st["did"] if "did" in st else None, st["id"], st["check"]), (None, "pick", "pending"))
        self.assertEqual(w.gui.workbench, "PartDesignWorkbench")
        seen = ["bench"]
        while c.e.state == "step":
            seen.append(c.e.step["id"])
            c.act("next")
        self.assertEqual(seen, ["bench", "pick", "pad", "length", "see"])
        st = c.state()
        self.assertEqual((st["step"], st["skipped"]), ("done", []))
        self.assertEqual(st["done_for"], ["bench", "length", "pad", "pick"])
        self.assertIn("Pad pushes a closed sketch", "\n".join(x or "" for x in calls))  # demo says why

    def test_a_refused_do_stays_with_why(self):
        w, c = make(window=False)
        c.start("demo")
        with self.assertRaises(TutorError) as x:
            c.act("next")
        self.assertIn("workbench was refused", str(x.exception))
        self.assertEqual(c.e.step["id"], "bench")
        self.assertEqual(c.act("skip")["id"], "pick")

    def test_agents_own_call_in_demo_passes_and_waits(self):
        w, c = make()
        c.start("demo")
        act(w, c, "workbench", {}, who=AGENT)
        self.assertEqual((c.e.step["id"], c.state()["check"]), ("bench", "pass"))  # waits for Next
        self.assertEqual(c.act("next")["id"], "pick")


class QuietWindow(unittest.TestCase):
    QUIET = {"all": [{"task_open": None}, {"editing": None}]}

    def test_setup_leaves_no_sketch_open(self):
        from agentlink_tutor import checks

        w, c = make()
        w.opens_sketch = True
        c.ui = FakeUI(w)
        c.start("demo")
        self.assertEqual(w.gui.editing, None)
        self.assertEqual(checks.evaluate(self.QUIET, c.e.context()).status, "pass")
        self.assertEqual(c.ui.log[0], "settle")

    def test_without_settling_the_sketch_stays_open(self):
        from agentlink_tutor import checks

        w, c = make()
        w.opens_sketch = True
        c.start("demo")
        self.assertEqual(checks.evaluate(self.QUIET, c.e.context()).status, "fail")

    def test_demo_opens_the_task_panel_its_targets_are_in(self):
        rung = []
        w, c = make(show=lambda ctl: rung.append((ctl.e.step["id"], w.gui.task)) or {"resolved": 2, "missing": []})
        w.opens_sketch = True
        c.ui = FakeUI(w)
        c.start("demo")
        for _ in range(3):
            c.act("next")  # bench, pick, pad: now at length, waiting
        self.assertEqual(c.e.step["id"], "length")
        self.assertIn(("open", "Pad"), c.ui.log)
        self.assertEqual(rung[-1], ("length", "PartDesign_Pad"))  # ringed with the panel open
        st = c.act("next")  # closes the panel, sets 15 mm: passes
        self.assertEqual(st["id"], "see")
        self.assertIn("close", c.ui.log)
        self.assertEqual(w.body().Shape.BoundBox.ZLength, 15)

    def test_guided_opens_nothing(self):
        w, c = make()
        c.ui = FakeUI(w)
        c.start("guided")
        for _ in range(3):
            c.act("next")
        self.assertNotIn("open", [x[0] for x in c.ui.log if isinstance(x, tuple)])

    def test_edit_target(self):
        w, c = make()
        c.start("guided")
        self.assertIsNone(run.edit_target(c.e))  # bench: workbench has none
        c.e.bindings["pad"] = "Pad001"
        c.act("next"), c.act("next"), c.act("next")
        self.assertEqual(run.edit_target(c.e), "Pad001")


class Switching(unittest.TestCase):
    def test_show_me_this_one_then_guided_goes_on(self):
        w, c = make()
        c.start("guided")
        st = c.act("do")  # "Do it for me": done, and guided goes on
        self.assertEqual(st["id"], "pick")
        self.assertEqual(c.e.done_for, {"bench"})

    def test_mode_switches_mid_lesson(self):
        w, c = make()
        c.start("guided")
        st = c.act("status", mode="demo")
        self.assertEqual((st["mode"], st["id"]), ("demo", "bench"))
        c.act("next")  # demo: does bench, waits at pick
        self.assertEqual(w.gui.workbench, "PartDesignWorkbench")
        st = c.act("next", mode="guided")  # guided: pick is not done, so it is skipped
        self.assertEqual((st["mode"], st["id"]), ("guided", "pad"))
        self.assertEqual(c.e.skipped, {"pick"})
        with self.assertRaises(TutorError):
            c.act("status", mode="watch")
        with self.assertRaises(TutorError):
            c.act("dance")


class Hints(unittest.TestCase):
    def test_ladder_narrows_targets_and_gives_the_value(self):
        shown = []
        w, c = make(show=lambda ctl: shown.append((ctl.e.hint_targets(), ctl.callout())) or {"resolved": 1, "missing": []})
        c.start("guided")
        for _ in range(3):
            c.act("next")
        self.assertEqual(c.e.step["id"], "length")
        self.assertEqual(len(shown[-1][0]), 2)  # the Length field and OK
        st = c.act("hint")
        self.assertEqual((st["hint"], st["hint_text"]), (1, "The Length box is in the Tasks panel."))
        self.assertIn("The Length box", shown[-1][1])
        c.act("hint")
        self.assertEqual(shown[-1][0], [{"task": {"name": "lengthEdit", "label": "Length"}}])  # the exact field only
        st = c.act("hint")
        self.assertEqual((st["hint"], st["hint_text"], st.get("do_it")), (3, "Length = 15 mm.", True))

    def test_top_rung_without_a_hint_says_the_exact_value(self):
        w, c = make()
        c.start("guided")
        c.act("next")  # pick: two hints
        for _ in range(3):
            st = c.act("hint")
        self.assertEqual(st["hint_text"], "select Sketch.")
        c.act("next"), c.act("next")  # pad (skipped), length
        e = c.e
        e.step.pop("hints")
        for _ in range(3):
            st = c.act("hint")
        self.assertEqual(st["hint_text"], "Length = 15 mm; then press OK.")


class Rider(unittest.TestCase):
    def test_lines(self):
        w, c = make()
        self.assertIsNone(c.rider("pd_pad"))  # idle: nothing
        c.start("guided")
        self.assertEqual(c.rider("pd_pad"), "tutor: step 1/5 pending")
        self.assertIsNone(c.rider("pd_pad"))  # said already
        self.assertIsNone(c.rider("tutor"))  # the tutor's own answer has the state
        act(w, c, "workbench", {})
        self.assertEqual(c.rider("workbench"), "tutor: step 1/5 passed; now step 2/5 pending")
        act(w, c, "selection", {"objects": ["Pad"]})
        self.assertEqual(c.rider("selection"), "tutor: step 2/5 not yet (Sketch is not selected)")
        c.act("stop")
        self.assertIsNone(c.rider("x"))

    def test_done_once(self):
        w, c = make()
        c.start("guided")
        while c.e.state == "step":
            c.act("skip")
        self.assertEqual(c.rider("x"), "tutor: lesson done, skipped bench, length, pad, pick, see")
        self.assertIsNone(c.rider("x"))


class State(unittest.TestCase):
    def test_compact_under_600_with_targets(self):
        w, c = make(show=lambda ctl: {"resolved": 0, "missing": ["toolbar hidden: Part Design is not the active workbench; call workbench activate first" * 2] * 6})
        c.start("guided")
        c.e.lesson["steps"][0]["say"] = "x" * 240
        c.e.lesson["steps"][0]["hints"] = ["y" * 240]
        c.act("hint")
        st = c.state(detail=True)
        self.assertLessEqual(len(json.dumps(st, ensure_ascii=False)), engine.STATE_MAX)
        self.assertIn("targets", st)
        self.assertLessEqual(len(st["targets"]["missing"]), 3)

    def test_headless_targets_say_why(self):
        w, c = make(window=False)
        st = c.start("guided")
        self.assertEqual(st["targets"], {"resolved": 0, "missing": [run.NO_WINDOW]})

    def test_a_failing_show_never_stops_the_lesson(self):
        def boom(ctl):
            raise RuntimeError("no overlay")

        w, c = make(show=boom)
        st = c.start("guided")
        self.assertEqual(st["targets"]["missing"], ["not drawn: no overlay"])
        self.assertEqual(c.act("next")["id"], "pick")


if __name__ == "__main__":
    unittest.main()
