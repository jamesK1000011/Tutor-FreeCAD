# SPDX-License-Identifier: LGPL-2.1-or-later
# Simplified Technical English for every lesson's words (ste.py and its
# rules in data/ste_rules.json), and the explanations switch: the person's
# preference kept across restarts, the callout and the agent's answers with
# and without the why line.
import json
import os
import unittest

from test_engine import World, pad_lesson
from test_general import SYNTHETIC, starters

from agentlink_tutor import engine, lessons, prefs, run, ste
from agentlink_tutor.checks import GuiState
from agentlink_tutor.engine import Engine


def reasons(text, kind="instruction", **kw):
    return " | ".join(ste.problems(text, kind, "say", **kw))


class Rules(unittest.TestCase):
    def test_good_instructions_pass(self):
        for t in ("Push **Pad**.", "Set **Length** to 15 mm. Push **OK**.", "Select the top face of the block.",
                  "Draw a circle at x = 15 mm, y = 15 mm.", "Select **File › Export**.", "Double-click Pad in the tree to change it."):
            with self.subTest(text=t):
                self.assertEqual(ste.problems(t), [])

    def test_long_sentence(self):
        long = "Select the face " + " ".join(["of the block"] * 7) + "."
        self.assertIn("at most 20", reasons(long))
        self.assertIn("at most 15", reasons("This " + "word " * 15 + "ends.", "why"))

    def test_two_instructions(self):
        self.assertIn("two instructions", reasons("Type 15 mm and push **OK**."))
        self.assertIn("two instructions", reasons("Select the face, push **Create sketch**."))
        self.assertIn("no “then”", reasons("Set **Length** to 15 mm, then push **OK**."))
        self.assertIn("no “first”", reasons("First select the sketch."))

    def test_passive(self):
        self.assertIn("passive", reasons("The face is selected.", "hint"))
        self.assertIn("passive", reasons("Its row is ringed.", "hint"))
        self.assertIn("passive", reasons("The top face is lit.", "hint"))

    def test_ing_words(self):
        self.assertIn("-ing", reasons("Start sketching on the face."))
        self.assertEqual(reasons("Nothing changes.", "hint"), "")

    def test_fillers(self):
        for f in ("Please push **OK**.", "Just push **OK**.", "Simply push **OK**."):
            with self.subTest(text=f):
                self.assertIn("no “", reasons(f))

    def test_verbs_and_units(self):
        self.assertIn("use “push”", reasons("Press **Pad**."))
        self.assertIn("use “select”", reasons("Choose **File › Export**."))
        self.assertIn("action verb", reasons("The Length box sets the depth."))
        self.assertEqual(reasons("The Length box sets the depth.", may_describe=True), "")
        self.assertIn("its unit", reasons("Set **Length** to 15."))
        self.assertEqual(reasons("Done: a 40 × 20 × 15 mm block.", may_describe=True), "")

    def test_ui_names_in_bold_are_not_checked(self):
        self.assertEqual(reasons("Push **Create sketch then Pad 15 Pressing**."), "")

    def test_why_is_one_sentence(self):
        self.assertIn("one sentence", reasons("Pad adds. It makes a solid.", "why"))

    def test_rules_are_data_with_their_source(self):
        r = ste.rules()
        self.assertIn("ASD-STE100", r["source"])
        self.assertIn("Issue 9", r["source"])
        self.assertIn("push", r["action_verbs"])
        self.assertLess(len(r["action_verbs"]), 60)  # our short list, not the standard's dictionary


class Lessons(unittest.TestCase):
    def test_every_starter_and_synthetic_lesson_passes(self):
        for lesson in starters() + SYNTHETIC:
            with self.subTest(lesson=lesson["id"]):
                self.assertEqual(ste.lesson_problems(lesson), [])

    def test_why_lines_are_short(self):
        for lesson in starters():
            for s in lesson["steps"]:
                if s.get("why"):
                    self.assertLessEqual(len(ste.words(s["why"])), 15)

    def test_an_inline_lesson_breaking_ste_is_refused_with_reasons(self):
        bad = {"id": "inline.bad", "title": "Bad words", "steps": [
            {"id": "a", "say": "Please press Pad and then the part is padded.", "do": [{"tool": "pd_pad"}]}]}
        with self.assertRaises(lessons.LessonError) as x:
            lessons.inline(bad)
        msg = str(x.exception)
        for want in ("no “please”", "use “push”"):
            self.assertIn(want, msg)
        good = dict(bad, steps=[{"id": "a", "say": "Push **Pad**.", "why": "Pad makes a solid.", "do": [{"tool": "pd_pad"}]}])
        self.assertEqual(lessons.inline(good)["id"], "inline.bad")


def make(params, show=None):
    w = World()
    w.gui = GuiState("StartWorkbench")
    e = Engine(pad_lesson(), call=w, doc=lambda: w.doc, gui=lambda: w.gui)
    c = run.Controller(e, prefs=params, show=show)
    c.start("guided")
    at = 0
    while c.e.step["id"] != "pad":
        c.act("skip")
        at += 1
    return w, c


class Explainers(unittest.TestCase):
    WHY = "Pad pushes a closed sketch out to make a solid."

    def test_on_by_default_and_kept_across_restarts(self):
        p = prefs.Memory()
        self.assertTrue(prefs.explainers(p))
        w, c = make(p)
        self.assertEqual(c.state()["because"], self.WHY)
        c.act("explain", on=False)
        w2, c2 = make(p)  # FreeCAD started again: the same parameters
        self.assertFalse(c2.e.explain)
        self.assertEqual(p.values, {prefs.EXPLAIN: False})

    def test_callout_and_answers_with_and_without(self):
        p = prefs.Memory()
        w, c = make(p)
        self.assertEqual(c.callout().split("\n\n")[:2], ["Push Pad.", self.WHY])
        st = c.act("explain", on=False)
        self.assertEqual(st["explain"], "off")
        self.assertNotIn("because", st)
        self.assertEqual(c.callout(), "Push Pad.")
        self.assertEqual(c.state(detail=True)["because"], self.WHY)  # asked for
        c.act("hint")
        self.assertIn("Find the yellow block", c.callout())  # hints still work
        self.assertEqual(c.act("explain", on=True)["because"], self.WHY)

    def test_demo_the_same(self):
        p = prefs.Memory()
        w, c = make(p)
        c.act("explain", on=False, mode="demo")
        self.assertNotIn(self.WHY, c.callout())
        c.act("explain", on=True)
        self.assertIn(self.WHY, c.callout())

    def test_compact_both_ways(self):
        for on in (True, False):
            p = prefs.Memory()
            w, c = make(p, show=lambda ctl: {"resolved": 0, "missing": ["a long reason why it is not shown here " * 3] * 4})
            c.e.step["say"] = "Push " + "**Pad** " * 30 + "."
            c.e.step["why"] = "w " * 60
            c.act("explain", on=on)
            for _ in range(3):
                c.act("hint")
            st = c.state(detail=True)
            with self.subTest(on=on):
                self.assertLessEqual(len(json.dumps(st, ensure_ascii=False)), engine.STATE_MAX)
                self.assertEqual(st["explain"], "on" if on else "off")

    def test_needs_on(self):
        w, c = make(prefs.Memory())
        with self.assertRaises(engine.TutorError):
            c.act("explain")


class EveryLessonWord(unittest.TestCase):
    """Every word of every lesson (says, why lines, hints, branch words, the
    agent's longer notes and pictures' words) passes the Tutor's rules and
    the tool cards' rule (at most 20 words a sentence: Agent Link's
    scripts/ste_check.py when a checkout is at hand, else the same count
    here)."""

    @staticmethod
    def texts(lesson):
        for s in lesson["steps"]:
            for key in ("say", "why", "explain"):
                if isinstance(s.get(key), str):
                    yield f"{s['id']}.{key}", s[key]
            for i, h in enumerate(s.get("hints") or []):
                yield f"{s['id']}.hints[{i}]", h
            for i, b in enumerate(s.get("branches") or []):
                if b.get("say"):
                    yield f"{s['id']}.branches[{i}]", b["say"]
            if isinstance(s.get("picture"), dict):
                yield f"{s['id']}.picture", s["picture"]["alt"]

    @staticmethod
    def card_lint():
        import importlib.util
        import sys as _sys

        _sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
        import gen_agentlink_tools

        pkg = gen_agentlink_tools.source()
        script = os.path.join(os.path.dirname(pkg), "scripts", "ste_check.py") if pkg else None
        if script and os.path.isfile(script):
            spec = importlib.util.spec_from_file_location("agentlink_ste_check", script)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return lambda t: [(s, n) for s, n in mod.lint(t)[0]]
        return lambda t: [(s, len(ste.words(s))) for s in ste.sentences(t) if len(ste.words(s)) > 20]

    def test_tool_card_rule_and_tutor_rules(self):
        lint = self.card_lint()
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workshop = os.path.join(here, "docs", "examples", "workshop", "lessons")
        extra = []
        for n in sorted(os.listdir(workshop)):
            with open(os.path.join(workshop, n), encoding="utf-8") as f:
                extra.append(json.load(f))
        for lesson in starters() + extra:
            with self.subTest(lesson=lesson["id"]):
                self.assertEqual(ste.lesson_problems(lesson), [])
                long = [(w, got) for w, t in self.texts(lesson) for got in lint(t)]
                self.assertEqual(long, [])

    def test_explain_and_picture_words_are_checked(self):
        l = {"steps": [{"id": "a", "say": "Push **Pad**.", "explain": "The face is selected by the tool.",
                        "picture": {"file": "pictures/x.png", "alt": "Something shown being drawn."}}]}
        got = " | ".join(ste.lesson_problems(l))
        self.assertIn("a.explain", got)
        self.assertIn("passive", got)
        self.assertIn("a.picture.alt", got)


if __name__ == "__main__":
    unittest.main()
