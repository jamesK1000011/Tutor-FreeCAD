# SPDX-License-Identifier: LGPL-2.1-or-later
# The stored lessons and the wiki course, as rules for every lesson: each
# passes the validator (Simplified Technical English included); each also
# passes as a lesson the agent writes on the fly (inline, 30 steps or fewer,
# after a stored chapter); each runs end to end in demo mode on the stand-in
# world; the TechDraw chapter starts from the Part Design chapter. The
# lessons adapted from the FreeCAD wiki carry their credit, their pictures
# and their licence. The Workshop lesson in docs/examples is checked as
# Workshop would ship it.
import copy
import json
import os
import sys
import unittest

from test_general import controller, starters

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import gen_agentlink_tools  # noqa: E402

from agentlink_tutor import lessons, ste  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSHOP = os.path.join(ROOT, "docs", "examples", "workshop", "lessons")
COURSE = ["agentlink_tutor.wiki.basic-part-design", "agentlink_tutor.wiki.basic-techdraw"]
WIKI = ["agentlink_tutor.wiki.basic-part-design", "agentlink_tutor.wiki.basic-techdraw", "agentlink_tutor.wiki.film-hinge-sketch",
        "agentlink_tutor.wiki.basic-attachment", "agentlink_tutor.wiki.whiffle-ball", "agentlink_tutor.wiki.basic-sketcher",
        "agentlink_tutor.wiki.configuration-tables", "agentlink_tutor.wiki.crank-slider-assembly", "agentlink_tutor.wiki.crank-slider-parts"]


def by_id():
    return {l["id"]: l for l in starters()}


def workshop_lessons():
    out = []
    for n in sorted(os.listdir(WORKSHOP)):
        with open(os.path.join(WORKSHOP, n), encoding="utf-8") as f:
            out.append(json.load(f))
    return out


class Stored(unittest.TestCase):
    def test_every_word_is_ste_and_every_rule_holds(self):
        tools = gen_agentlink_tools.vendored()
        for l in starters():
            with self.subTest(lesson=l["id"]):
                self.assertEqual(ste.lesson_problems(l), [])
                self.assertEqual(lessons.check(l, tools), [])

    def test_the_same_lessons_written_on_the_fly(self):
        # What the agent writes inline is held to the same rules: each stored
        # lesson, renamed inline.<name>, is taken (a chapter after its stored
        # chapter before).
        have = by_id()
        for l in starters():
            mine = {k: v for k, v in copy.deepcopy(l).items() if not k.startswith("_")}
            for st in mine["steps"]:
                st.pop("picture", None)  # an inline lesson has no files
            mine["id"] = "inline." + l["id"].rpartition(".")[2]
            with self.subTest(lesson=mine["id"]):
                got = lessons.inline(mine, tools=gen_agentlink_tools.vendored(), lookup=have.get)
                self.assertEqual([p["id"] for p in got["_after"]], [p["id"] for p in l["_after"]])

    def test_each_steps_do_has_its_bindings(self):
        # Every step done for the person goes through the tools with each
        # $name bound (the stand-in world answers the tools; FreeCAD's own
        # replay is tests/test_replay_fc.py and the live check).
        for l in starters() + workshop_lessons():
            with self.subTest(lesson=l["id"]):
                w, c = controller(l, mode="demo")
                seen = 0
                for _ in range(40):
                    if c.e.state != "step":
                        break
                    if c.e.step.get("do"):
                        start = len(w.calls)
                        c.e.do()
                        for name, args in w.calls[start:]:
                            self.assertNotIn('"$', json.dumps(args), f"{c.e.step['id']}: {name} has an unbound name")
                        seen += 1
                    c.e.next()
                self.assertEqual(c.e.state, "done")
                self.assertGreater(seen, 0)

    def test_chapter_two_starts_from_chapter_one(self):
        # The TechDraw chapter builds the Part Design chapter's part through
        # its steps' calls (not from a file), leaving out the window-only
        # workbench switch.
        have = by_id()
        one = [c for s in have[COURSE[0]]["steps"] if s["id"] not in lessons.detours(have[COURSE[0]])
               and "workbench" not in json.dumps(s.get("check", {})) for c in s.get("do") or ()]
        w, c = controller(have[COURSE[1]])
        made = [name for name, _a in w.calls]
        self.assertEqual(made[:len(one)], [x["tool"] for x in one])
        self.assertNotIn("doc_open", made)
        self.assertEqual(c.e.state, "step")

    def test_course_chapters_in_order(self):
        have = by_id()
        self.assertEqual([have[i]["course"]["chapter"] for i in COURSE], [1, 2])
        self.assertEqual(have[COURSE[1]]["setup"]["after"], COURSE[0])
        self.assertTrue(have[COURSE[0]].get("result"))  # the next chapter goes on from it
        for i in COURSE:
            n = len([s for s in have[i]["steps"] if s["id"] not in lessons.detours(have[i])])
            self.assertLessEqual(n, lessons.INLINE_MAX_STEPS)

    def test_no_course_copies_a_creators_video(self):
        # The bike-stem course (after a video) is retired: no lesson, tag or
        # course of it is shipped.
        for l in starters():
            self.assertNotIn("bike", json.dumps(l).lower(), l["id"])
        self.assertFalse([n for n in os.listdir(lessons.CORE_DIR) if "stem" in n])


class Wiki(unittest.TestCase):
    """The lessons adapted from FreeCAD wiki tutorials: credit, licence,
    pictures, and checks of what is made."""

    def test_each_carries_its_credit(self):
        have = by_id()
        self.assertEqual(sorted(i for i in have if ".wiki." in i), sorted(WIKI))
        for lid in WIKI:
            c = have[lid]["credit"]
            with self.subTest(lesson=lid):
                self.assertEqual(c["authors"], "FreeCAD wiki contributors")
                self.assertIn(c["licence"], ("CC-BY-3.0", "CC-BY-4.0"))
                self.assertTrue(c["link"].startswith("https://wiki.freecad.org/"))
                self.assertIs(c["adapted"], True)
                self.assertIn("wiki", have[lid]["tags"])

    def test_pictures_are_beside_the_lessons_and_listed_for_reuse(self):
        reuse = open(os.path.join(ROOT, "REUSE.toml"), encoding="utf-8").read()
        used = set()
        for lid in WIKI:
            l = by_id()[lid]
            for f in lessons.pictures(l):
                used.add(f)
                self.assertTrue(os.path.isfile(os.path.join(lessons.CORE_DIR, f)), f)
                self.assertIn(f'"agentlink_tutor/lessons/{f}"', reuse)
            name = next(n for n in os.listdir(lessons.CORE_DIR) if n.endswith(lessons.SUFFIX) and json.load(
                open(os.path.join(lessons.CORE_DIR, n), encoding="utf-8"))["id"] == lid)
            self.assertIn(f'"agentlink_tutor/lessons/{name}"', reuse)
        shipped = {"pictures/" + n for n in os.listdir(os.path.join(lessons.CORE_DIR, "pictures"))}
        self.assertEqual(shipped, used)  # no picture without a lesson that shows it

    def test_licence_files(self):
        assets = open(os.path.join(ROOT, "LICENSE-Assets"), encoding="utf-8").read()
        self.assertIn("Attribution 3.0 Unported", assets)
        self.assertIn("FreeCAD wiki contributors", assets)
        code = open(os.path.join(ROOT, "LICENSE-Code"), encoding="utf-8").read()
        self.assertIn("LGPL-2.1-or-later", code)
        lgpl = open(os.path.join(ROOT, "LICENSES", "LGPL-2.1-or-later.txt"), encoding="utf-8").read()
        self.assertIn("LESSER GENERAL PUBLIC LICENSE", lgpl)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "LICENSE")))
        reuse = open(os.path.join(ROOT, "REUSE.toml"), encoding="utf-8").read()
        self.assertIn('SPDX-License-Identifier = "CC-BY-3.0"', reuse)
        self.assertIn('SPDX-FileCopyrightText = "FreeCAD wiki contributors', reuse)
        for f in ("LICENSES/CC-BY-3.0.txt", "LICENSES/LGPL-2.1-or-later.txt"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, f)), f)

    def test_end_states_the_agent_test_scores(self):
        # What the main session's agent-to-agent runs score: the last step's
        # check of each (volume, size, objects).
        have = by_id()
        last = lambda lid: [s for s in have[lid]["steps"] if s["id"] not in lessons.detours(have[lid])][-1]["check"]
        bpd = json.dumps(last(WIKI[0]))
        self.assertIn('"eq": 18465.686', bpd)
        self.assertIn('"size": [53, 26, 26]', bpd)
        td = json.dumps(last(WIKI[1]))
        for want in ('"DistanceX"', '"DistanceY"', '"TechDraw::DrawProjGroup"'):
            self.assertIn(want, td)
        hinge = json.dumps(last(WIKI[2]))
        self.assertIn('"full": true', hinge)
        self.assertIn('"uses": "neutral_radius"', hinge)


class Workshop(unittest.TestCase):
    def test_hole_for_hardware_as_workshop_ships_it(self):
        ls = workshop_lessons()
        self.assertEqual([l["id"] for l in ls], ["workshop.make.hole-for-hardware"])
        tools = gen_agentlink_tools.vendored() | {"hw_hole"}  # Workshop's own tool
        self.assertEqual(lessons.check(ls[0], tools), [])
        lib = lessons.Library(tools)
        lib.add_folder(WORKSHOP, "workshop")
        self.assertEqual(list(lib.lessons()), ["workshop.make.hole-for-hardware"])
        # Checked by the feature's type and size, not by how it was made.
        text = json.dumps(ls[0])
        for want in ('"PartDesign::Hole"', '"ThreadSize": "M4"', '"HoleCutType": "Countersink"', '"ge": 4.3'):
            self.assertIn(want, text)


if __name__ == "__main__":
    unittest.main()
