# SPDX-License-Identifier: LGPL-2.1-or-later
# Lesson files without FreeCAD: the schema, the rules a schema cannot say,
# namespacing, what the listing hides, inline lessons and progress.
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

import fakes  # noqa: F401  (puts the repository on the path)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import gen_agentlink_tools  # noqa: E402

from agentlink_tutor import lessons  # noqa: E402

PACKAGE = "agentlink_tutor"


def core_files():
    return sorted(n for n in os.listdir(lessons.CORE_DIR) if n.endswith(lessons.SUFFIX))


def load(name):
    with open(os.path.join(lessons.CORE_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def tiny(**over):
    l = {"schema": 1, "id": "agentlink_tutor.t.tiny", "version": "1.0.0", "title": "Tiny one",
         "setup": {"doc": "new"},
         "steps": [{"id": "a", "say": "Make a pad.", "check": {"new": "PartDesign::Pad"}, "bind": {"pad": {"new": "PartDesign::Pad"}}},
                   {"id": "b", "say": "Set it.", "check": {"prop": "$pad", "name": "Length", "eq": 5}}]}
    l.update(over)
    return l


class CoreLessons(unittest.TestCase):
    def test_starter_lessons_and_the_course(self):
        ids = {load(n)["id"] for n in core_files()}
        self.assertEqual(ids, {"agentlink_tutor.pd.pad-sketch", "agentlink_tutor.pd.pocket-hole",
                               "agentlink_tutor.io.export-stl", "agentlink_tutor.sk.constrain-rectangle",
                               "agentlink_tutor.pd.fillet-chamfer", "agentlink_tutor.param.parameter-depth",
                               "agentlink_tutor.td.drawing-page", "agentlink_tutor.asm.fixed-joint",
                               "agentlink_tutor.wiki.basic-part-design", "agentlink_tutor.wiki.basic-techdraw",
                               "agentlink_tutor.wiki.film-hinge-sketch", "agentlink_tutor.wiki.basic-attachment",
                               "agentlink_tutor.wiki.whiffle-ball", "agentlink_tutor.wiki.basic-sketcher",
                               "agentlink_tutor.wiki.configuration-tables", "agentlink_tutor.wiki.crank-slider-assembly",
                               "agentlink_tutor.wiki.crank-slider-parts", "agentlink_tutor.wiki.arch-house",
                               "agentlink_tutor.wiki.draft-tutorial", "agentlink_tutor.wiki.fem-cantilever"})

    def test_each_fits_the_schema_and_the_rules(self):
        tools = gen_agentlink_tools.vendored()
        for n in core_files():
            with self.subTest(lesson=n):
                self.assertEqual(lessons.check(load(n), tools), [])

    def test_techdraw_dimensions_from_one_edge(self):
        """Live finding 51: a vertex dot on a TechDraw page is hard to hit.
        Steps 5 and 6 ask for one edge; the two points stay as a hint; the
        check takes any dimension of the right type (one edge or two points)."""
        steps = {s["id"]: s for s in load("wiki-basic-techdraw.lesson.json")["steps"]}
        for sid, typ in (("vertical", "DistanceY"), ("horizontal", "DistanceX")):
            with self.subTest(step=sid):
                st = steps[sid]
                self.assertIn("edge of the view", st["say"])
                self.assertNotIn("point", st["say"])
                self.assertTrue(any("point" in h for h in st["hints"]))
                self.assertEqual(st["check"], {"new": {"type": "TechDraw::DrawViewDimension", "where": {"Type": typ}}})

    def test_ids_carry_the_package_name(self):
        for n in core_files():
            self.assertTrue(load(n)["id"].startswith(PACKAGE + "."), n)

    def test_every_tool_called_exists_in_agent_link(self):
        tools = gen_agentlink_tools.vendored()
        self.assertGreater(len(tools), 300)
        for n in core_files():
            for where, c in lessons._calls(load(n)):
                self.assertIn(c["tool"], tools, f"{n} {where}")

    def test_vendored_tool_list_matches_agent_link(self):
        pkg = gen_agentlink_tools.source()
        if pkg is None:
            self.skipTest("no Agent Link checkout beside this one ($AGENTLINK_SRC)")
        self.assertEqual(set(gen_agentlink_tools.names(pkg)), gen_agentlink_tools.vendored(),
                         "run python3 tools/gen_agentlink_tools.py")

    def test_every_main_path_step_can_be_done_for_the_person(self):
        # "Do it for me" is always there: each step that has a check has a do,
        # except the last (a look at the result).
        for n in core_files():
            l = load(n)
            main = [s for s in l["steps"] if s["id"] not in lessons.detours(l)]
            for s in main[:-1]:
                self.assertTrue(s.get("do"), f"{n}: {s['id']}")

    def test_library_loads_them(self):
        lib = lessons.core_library(gen_agentlink_tools.vendored())
        self.assertEqual(len(lib.lessons()), len(core_files()))
        self.assertEqual(lib.refused, [])
        self.assertEqual(lib.get("agentlink_tutor.pd.pad-sketch")["title"], "Pad a sketch into a solid")
        with self.assertRaises(lessons.LessonError):
            lib.get("agentlink_tutor.nope")


class Rules(unittest.TestCase):
    def test_tiny_is_fine(self):
        self.assertEqual(lessons.check(tiny()), [])

    def test_schema_problems(self):
        self.assertTrue(any("missing steps" in p for p in lessons.check({k: v for k, v in tiny().items() if k != "steps"})))
        self.assertTrue(any("unexpected colour" in p for p in lessons.check(tiny(colour="red"))))
        self.assertTrue(any("version" in p for p in lessons.check(tiny(version="1.0"))))
        self.assertTrue(any("schema" in p for p in lessons.check(tiny(schema=2))))
        bad = tiny()
        bad["steps"][0]["hints"] = ["a", "b", "c", "d"]
        self.assertTrue(any("more than 3" in p for p in lessons.check(bad)))
        bad = tiny()
        bad["steps"][0]["say"] = "x" * 300
        self.assertTrue(any("longer than 240" in p for p in lessons.check(bad)))

    def test_one_setup_kind(self):
        self.assertIn("setup: one of doc, fixture, calls or after", lessons.check(tiny(setup={"doc": "new", "calls": [{"tool": "doc_new"}]})))
        self.assertTrue(lessons.check(tiny(setup={"fixture": "../x.FCStd"})))

    def test_vars_must_be_defined(self):
        bad = tiny()
        bad["steps"][1]["check"]["prop"] = "$pud"
        self.assertTrue(any("$pud is used but never defined" in p for p in lessons.check(bad)))
        ok = tiny(vars={"len": 5})
        ok["steps"][1]["check"]["eq"] = "$len"
        self.assertEqual(lessons.check(ok), [])

    def test_step_ids_next_and_goto(self):
        bad = tiny()
        bad["steps"][1]["id"] = "a"
        self.assertTrue(any("used twice" in p for p in lessons.check(bad)))
        bad = tiny()
        bad["steps"][0]["next"] = "zz"
        self.assertTrue(any("no step zz" in p for p in lessons.check(bad)))
        bad = tiny()
        bad["steps"][0]["branches"] = [{"when": {"new": "PartDesign::Pocket"}, "goto": "zz"}]
        self.assertTrue(any("goto: no step zz" in p for p in lessons.check(bad)))

    def test_check_vocabulary(self):
        bad = tiny()
        bad["steps"][0]["check"] = {"glow": "$pad"}
        self.assertTrue(any("unknown check kind 'glow'" in p for p in lessons.check(bad)))
        self.assertEqual(lessons.check(bad, extra_kinds=("glow",)), [])

    def test_unknown_tool(self):
        l = tiny()
        l["steps"][0]["do"] = [{"tool": "sketch_rect", "args": {}}]
        self.assertIn("steps.a.do[0]: no tool sketch_rect", lessons.check(l, tools={"pd_pad"}))

    def test_targets_parsed(self):
        for t in ({"cmd": "PartDesign_Pad"}, {"menu": ["Part Design", "Pad"]}, {"wb": "PartDesignWorkbench"},
                  {"task": {"name": "lengthEdit", "label": "Length"}}, {"task": "Length"}, {"tree": "$pad"},
                  {"face": {"normal": [0, 0, 1], "largest": True}, "of": "$pad"}, {"sub": "Face6", "of": "$pad"},
                  {"dock": "Report view"}, {"view": "3d"}, {"ext": "snapshot", "pin": 2}):
            self.assertIn(lessons.target_kind(t), lessons.TARGET_KINDS, t)
        for t in ({}, {"cmd": "A", "wb": "B"}, {"face": {"largest": True}}, {"menu": []}, {"cmd": "A", "say": "x"}, {"task": {"colour": 1}}):
            with self.assertRaises(lessons.LessonError, msg=t):
                lessons.target_kind(t)
        l = tiny()
        l["steps"][0]["targets"] = [{"glow": "x"}]
        self.assertTrue(any("targets[0]" in p for p in lessons.check(l)))

    def test_bind_specs(self):
        l = tiny()
        l["steps"][0]["bind"] = {"pad": {"made": "PartDesign::Pad"}}
        self.assertTrue(any("bind.pad" in p for p in lessons.check(l)))


class Namespacing(unittest.TestCase):
    def setUp(self):
        self.a = tempfile.mkdtemp()
        self.b = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.a)
        shutil.rmtree(self.b)

    def put(self, folder, name, lesson):
        with open(os.path.join(folder, name + lessons.SUFFIX), "w", encoding="utf-8") as f:
            json.dump(lesson, f)

    def test_ids_belong_to_their_folder_and_never_collide(self):
        self.put(self.a, "mine", tiny(id="addon_a.x.one"))
        self.put(self.a, "stolen", tiny(id="addon_b.x.two"))
        self.put(self.b, "dup", tiny(id="addon_a.x.one"))
        self.put(self.b, "two", tiny(id="addon_b.x.two"))
        self.put(self.b, "broken", {"schema": 1})
        with open(os.path.join(self.b, "junk" + lessons.SUFFIX), "w") as f:
            f.write("{")
        lib = lessons.Library()
        lib.add_folder(self.a, "addon_a")
        lib.add_folder(self.b, "addon_b")
        self.assertEqual(sorted(lib.lessons()), ["addon_a.x.one", "addon_b.x.two"])
        refused = dict(lib.refused)
        self.assertIn("does not start with addon_a.", refused["stolen.lesson.json"])
        self.assertIn("does not start with addon_b.", refused["dup.lesson.json"])
        self.assertIn("broken.lesson.json", refused)
        self.assertIn("cannot be read", refused["junk.lesson.json"])

    def test_listing_hides_what_cannot_run_here(self):
        self.put(self.a, "pd", tiny(id="addon_a.pd", requires={"freecad": ">=1.1", "workbenches": ["PartDesignWorkbench"]}))
        self.put(self.a, "new", tiny(id="addon_a.new", requires={"freecad": ">=9", "agentlink_api": ">=2"}))
        lib = lessons.Library()
        lib.add_folder(self.a, "addon_a")
        ids = lambda **kw: [x["id"] for x in lib.listing(**kw)]  # noqa: E731
        self.assertEqual(ids(), ["addon_a.new", "addon_a.pd"])  # nothing known hides nothing
        self.assertEqual(ids(freecad="1.1.3"), ["addon_a.pd"])
        self.assertEqual(ids(freecad="1.1.3", workbenches=["SketcherWorkbench"]), [])
        self.assertEqual(ids(api=1), ["addon_a.pd"])
        row = lib.listing(freecad="1.1.3")[0]
        self.assertEqual(set(row), {"id", "title", "minutes", "done", "from"})  # an add-on's: which one
        self.assertEqual(row["from"], "addon_a")


class Inline(unittest.TestCase):
    def test_inline_capped_named_and_session_only(self):
        steps = [{"id": f"s{i}", "say": "Do it.", "check": {"exists": "PartDesign::Body"}} for i in range(lessons.INLINE_MAX_STEPS)]
        self.assertEqual(lessons.INLINE_MAX_STEPS, 30)  # a chapter of a video course (10 to 30 steps)
        got = lessons.inline({"id": "inline.quick", "title": "Quick one", "steps": steps})
        self.assertEqual(got["schema"], 1)
        with self.assertRaises(lessons.LessonError) as e:
            lessons.inline({"id": "inline.long", "title": "Long one", "steps": steps + [dict(steps[0], id="s99")]})
        self.assertIn("30 steps or fewer", str(e.exception))
        self.assertIn("batches", str(e.exception))
        with self.assertRaises(lessons.LessonError) as e:
            lessons.inline({"id": "agentlink_tutor.pd.pad-sketch", "title": "Shadow", "steps": steps[:1]})
        self.assertIn("inline.", str(e.exception))
        with self.assertRaises(lessons.LessonError):
            lessons.inline({"id": "inline.f", "title": "Fixture", "setup": {"fixture": "a.FCStd"}, "steps": steps[:1]})
        with self.assertRaises(lessons.LessonError):
            lessons.inline({"id": "inline.bad", "title": "Bad tool", "steps": [dict(steps[0], do=[{"tool": "rm_rf"}])]}, tools={"pd_pad"})


class Progress(unittest.TestCase):
    def test_kept_as_id_at_version(self):
        p = lessons.Progress(params=lessons._Memory())
        self.assertFalse(p.done("agentlink_tutor.pd.pad-sketch", "1.0.0"))
        p.mark("agentlink_tutor.pd.pad-sketch", "1.0.0")
        p.mark("agentlink_tutor.io.export-stl", "1.0.0")
        self.assertTrue(p.done("agentlink_tutor.pd.pad-sketch", "1.0.0"))
        self.assertEqual(p.entries(), ["agentlink_tutor.pd.pad-sketch@1.0.0", "agentlink_tutor.io.export-stl@1.0.0"])
        # A new version of a lesson is not done until it is done again; one line per lesson.
        self.assertFalse(p.done("agentlink_tutor.pd.pad-sketch", "1.1.0"))
        p.mark("agentlink_tutor.pd.pad-sketch", "1.1.0")
        self.assertEqual(p.entries(), ["agentlink_tutor.io.export-stl@1.0.0", "agentlink_tutor.pd.pad-sketch@1.1.0"])
        p.mark("inline.quick", "0.0.0")
        self.assertNotIn("inline.quick@0.0.0", p.entries())

    def test_listing_shows_done(self):
        p = lessons.Progress(params=lessons._Memory())
        p.mark("agentlink_tutor.io.export-stl", "1.0.0")
        lib = lessons.core_library()
        done = {x["id"]: x["done"] for x in lib.listing(progress=p)}
        self.assertEqual(done["agentlink_tutor.io.export-stl"], True)
        self.assertEqual(done["agentlink_tutor.pd.pad-sketch"], False)


class Versions(unittest.TestCase):
    def test_satisfies(self):
        self.assertTrue(lessons.satisfies(">=1.1", "1.1.3"))
        self.assertFalse(lessons.satisfies(">=1.1", "1.0.2"))
        self.assertTrue(lessons.satisfies(">=1,<2", 1))
        self.assertFalse(lessons.satisfies(">=1,<2", "2.0"))
        with self.assertRaises(ValueError):
            lessons.satisfies("~1", "1")


if __name__ == "__main__":
    unittest.main()
