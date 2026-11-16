# SPDX-License-Identifier: LGPL-2.1-or-later
# Courses and batches: a lesson's setup.after starts it where the chapter
# before ended (the document in front when it passes that chapter's result,
# else the chapters before done through the tools), for stored chapters and
# for the agent's inline batches alike; add-ons' lessons found beside their
# agentlink_families module or given to the lessons service.
import copy
import json
import os
import shutil
import tempfile
import types
import unittest

from test_engine import World

from agentlink_tutor import engine, lessons
from agentlink_tutor.engine import Engine, TutorError

ONE = {
    "schema": 1, "id": "test.course.one", "version": "1.0.0", "title": "Chapter one",
    "course": {"id": "demo", "title": "A demo course", "chapter": 1},
    "setup": {"calls": [{"tool": "doc_new", "args": {"name": "Course"}}, {"tool": "pd_body_new"}],
              "bind": {"body": {"exists": "PartDesign::Body"}}},
    "vars": {"len": 10},
    "result": {"exists": {"type": "PartDesign::Pad", "where": {"Length": 10}}},
    "steps": [
        {"id": "sk", "say": "Make a sketch.", "check": {"new": "Sketcher::SketchObject"}, "bind": {"sk": {"new": "Sketcher::SketchObject"}},
         "do": [{"tool": "sketch_new", "args": {}}, {"tool": "sketch_add", "args": {"sketch": "$sk"}}]},
        {"id": "pad", "say": "Push **Pad**. Set **Length** to 10 mm.", "check": {"new": "PartDesign::Pad"}, "bind": {"pad": {"new": "PartDesign::Pad"}},
         "do": [{"tool": "pd_pad", "args": {"length": "$len"}}]},
        {"id": "look", "say": "Look at the block.", "check": {"exists": "$pad"}},
    ],
}

TWO = {
    "schema": 1, "id": "test.course.two", "version": "1.0.0", "title": "Chapter two",
    "course": {"id": "demo", "title": "A demo course", "chapter": 2},
    "setup": {"after": "test.course.one", "bind": {"pad": {"exists": "PartDesign::Pad"}}},
    "steps": [
        {"id": "deeper", "say": "Set the **Length** of the pad to 15 mm.",
         "check": {"prop": "$pad", "name": "Length", "eq": 15},
         "do": [{"tool": "feature_edit", "args": {"feature": "$pad", "set": {"Length": 15}}}]},
    ],
}

THREE = dict(copy.deepcopy(TWO), id="test.course.three", title="Chapter three",
             course={"id": "demo", "chapter": 3}, setup={"after": "test.course.two", "bind": {"pad": {"exists": "PartDesign::Pad"}}})


def library(*ls):
    have = {l["id"]: copy.deepcopy(l) for l in ls}
    for l in have.values():
        l["_after"] = lessons.chain(l, have.get)
    return have


class Chain(unittest.TestCase):
    def test_chapters_in_order_and_errors(self):
        have = library(ONE, TWO, THREE)
        self.assertEqual([l["id"] for l in have["test.course.three"]["_after"]], ["test.course.one", "test.course.two"])
        self.assertEqual(have["test.course.one"]["_after"], [])
        with self.assertRaises(lessons.LessonError) as e:
            lessons.chain(TWO, {}.get)
        self.assertIn("no lesson test.course.one", str(e.exception))
        loop = dict(copy.deepcopy(ONE), setup={"after": "test.course.two"})
        with self.assertRaises(lessons.LessonError):
            lessons.chain(TWO, {"test.course.one": loop, "test.course.two": TWO}.get)

    def test_valid_and_the_rules(self):
        for l in (ONE, TWO, THREE):
            self.assertEqual(lessons.check(l), [], l["id"])
        bad = copy.deepcopy(ONE)
        bad["result"] = {"exists": "$pad"}
        self.assertTrue(any("result:" in p for p in lessons.check(bad)))
        bad = copy.deepcopy(TWO)
        bad["setup"]["after"] = TWO["id"]
        self.assertIn("setup.after: a lesson does not come after itself", lessons.check(bad))
        bad["setup"]["calls"] = [{"tool": "doc_new"}]
        self.assertIn("setup: one of doc, fixture, calls or after", lessons.check(bad))

    def test_library_refuses_a_missing_chapter(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for l in (dict(TWO, id="mine.course.two", setup={"after": "mine.course.one", "bind": {"pad": {"exists": "PartDesign::Pad"}}}),):
            with open(os.path.join(d, "two.lesson.json"), "w", encoding="utf-8") as f:
                json.dump(l, f)
        lib = lessons.Library()
        lib.add_folder(d, "mine")
        self.assertEqual(lib.lessons(), {})
        self.assertIn("no lesson mine.course.one", lib.refused[0][1])


class AfterSetup(unittest.TestCase):
    def engine(self, lesson_id, world, have=None):
        have = have or library(ONE, TWO, THREE)
        return Engine(copy.deepcopy(have[lesson_id]), call=world, doc=lambda: world.doc, gui=lambda: world.gui)

    def test_fresh_document_replays_the_chapters_before(self):
        for lid, length in (("test.course.two", 10), ("test.course.three", 15)):
            with self.subTest(lesson=lid):
                w = World()
                e = self.engine(lid, w)
                st = e.start("guided")
                done = [c[0] for c in w.calls]
                want = ["pd_body_new", "sketch_new", "sketch_add", "pd_pad"]  # in the open empty document
                if lid.endswith("three"):
                    want += ["feature_edit"]  # chapter two's step, done for the person
                self.assertEqual(done, want)
                self.assertEqual(e.bindings, {"pad": "Pad"})  # this chapter's own bindings
                self.assertEqual(w.doc.getObject("Pad").Length.Value, length)
                self.assertEqual((st["step"], st["check"]), ("1/1", "pending"))
                if lid.endswith("two"):
                    self.assertEqual(e.do()["check"], "pass")

    def test_goes_on_in_the_document_that_ends_the_chapter_before(self):
        w = World()
        one = Engine(copy.deepcopy(ONE), call=w, doc=lambda: w.doc)
        one.start("demo")
        while one.state == "step":
            if one.step.get("do"):
                one.do()
            one.next()
        n = len(w.calls)
        e = self.engine("test.course.two", w)
        e.start("guided")
        self.assertEqual(len(w.calls), n)  # nothing made again: the person's own block goes on
        self.assertEqual(e.bindings["pad"], "Pad")

    def test_without_the_chapter_before_it_says_so(self):
        w = World()
        e = Engine(dict(copy.deepcopy(TWO), _after=[]), call=w, doc=lambda: w.doc)
        with self.assertRaises(TutorError) as err:
            e.start("guided")
        self.assertIn("test.course.one", str(err.exception))


class InlineBatches(unittest.TestCase):
    def test_a_long_job_in_batches(self):
        steps = [{"id": f"s{i}", "say": "Make a body.", "check": {"exists": "PartDesign::Body"}} for i in range(30)]
        first = lessons.inline({"id": "inline.first", "title": "First batch", "result": {"exists": "PartDesign::Body"},
                                "setup": {"calls": [{"tool": "pd_body_new"}]}, "steps": steps})
        seen = {first["id"]: first}
        second = lessons.inline({"id": "inline.second", "title": "Second batch", "setup": {"after": "inline.first"},
                                 "steps": steps[:5]}, lookup=seen.get)
        self.assertEqual([l["id"] for l in second["_after"]], ["inline.first"])
        with self.assertRaises(lessons.LessonError):
            lessons.inline({"id": "inline.third", "title": "Third", "setup": {"after": "inline.nope"}, "steps": steps[:1]}, lookup=seen.get)
        # A stored chapter may come before an inline batch too.
        have = library(ONE)
        got = lessons.inline({"id": "inline.more", "title": "More", "setup": {"after": "test.course.one"}, "steps": steps[:1]},
                             lookup=have.get)
        self.assertEqual(got["_after"][0]["id"], "test.course.one")


class AddonLessons(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.addCleanup(lessons._REGISTERED.clear)
        self.addCleanup(lessons._INSTALLED.clear)

    def addon(self, pkg, lesson_ids=(), folder="lessons", attr=None):
        here = os.path.join(self.root, pkg)
        os.makedirs(os.path.join(here, folder) if lesson_ids else here)
        for lid in lesson_ids:
            l = dict(copy.deepcopy(ONE), id=lid)
            l.pop("result")
            with open(os.path.join(here, folder, lid.rpartition(".")[2] + lessons.SUFFIX), "w", encoding="utf-8") as f:
                json.dump(l, f)
        mod = types.SimpleNamespace(__file__=os.path.join(here, "agentlink_families.py"))
        if attr is not None:
            mod.LESSONS = attr
        return mod

    def test_found_beside_each_addons_families_module(self):
        mods = {
            "workshop.agentlink_families": self.addon("workshop", ["workshop.make.hole"]),
            "texturizer.agentlink_families": self.addon("texturizer", ["texturizer.tx.bumps"], folder="tutor_lessons", attr="tutor_lessons"),
            "scanrulerfc.agentlink_families": self.addon("scanrulerfc"),  # no lessons: nothing
            "agentlink_tutor.agentlink_families": types.SimpleNamespace(__file__=os.path.join(lessons.HERE, "agentlink_families.py")),
            "workshop.other": types.SimpleNamespace(__file__="x"),
        }
        got = lessons.addon_folders(mods)
        self.assertEqual([o for _f, o in got], ["texturizer", "workshop"])
        lib = lessons.installed_library(refresh=True, modules=mods)
        ids = set(lib.lessons())
        self.assertIn("workshop.make.hole", ids)
        self.assertIn("texturizer.tx.bumps", ids)
        self.assertIn("agentlink_tutor.pd.pad-sketch", ids)
        row = next(r for r in lib.listing() if r["id"] == "workshop.make.hole")
        self.assertEqual(row["from"], "workshop")
        self.assertEqual(row["course"], "demo 1")

    def test_an_addon_cannot_use_another_ones_name(self):
        mods = {"workshop.agentlink_families": self.addon("workshop", ["texturizer.tx.sneaky"])}
        lib = lessons.installed_library(refresh=True, modules=mods)
        self.assertNotIn("texturizer.tx.sneaky", lib.lessons())
        self.assertIn("does not start with workshop.", lib.refused[-1][1])

    def test_lessons_service_takes_a_folder(self):
        mod = self.addon("kicadbridge", ["kicadbridge.pcb.first"])
        lib = lessons.installed_library(refresh=True, modules={})
        self.assertNotIn("kicadbridge.pcb.first", lib.lessons())
        lessons.register_folder(os.path.join(os.path.dirname(mod.__file__), "lessons"), "kicadbridge")
        self.assertIn("kicadbridge.pcb.first", lib.lessons())
        self.assertIn("kicadbridge.pcb.first", lessons.installed_library(refresh=True, modules={}).lessons())
        with self.assertRaises(lessons.LessonError):
            lessons.register_folder(self.root, "not a name")


if __name__ == "__main__":
    unittest.main()
