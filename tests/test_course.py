# SPDX-License-Identifier: LGPL-2.1-or-later
# The stored lessons and the bike-stem course, as rules for every lesson:
# each passes the validator (Simplified Technical English included); each
# also passes as a lesson the agent writes on the fly (inline, 30 steps or
# fewer, after a stored chapter); each runs end to end in demo mode on the
# stand-in world; chapters 2 and 3 start from the chapters before. The
# Workshop lesson in docs/examples is checked as Workshop would ship it.
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
COURSE = ["agentlink_tutor.course.bike-stem-1", "agentlink_tutor.course.bike-stem-2", "agentlink_tutor.course.bike-stem-3"]


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

    def test_chapters_start_from_the_chapters_before(self):
        have = by_id()
        one = [c for s in have[COURSE[0]]["steps"] for c in s.get("do") or ()]
        two = [c for s in have[COURSE[1]]["steps"] for c in s.get("do") or ()]
        for lid, before in ((COURSE[1], one), (COURSE[2], one + two)):
            with self.subTest(lesson=lid):
                w, c = controller(have[lid])
                made = [name for name, _a in w.calls]
                self.assertEqual(made[:1], ["pd_body_new"])  # chapter 1's setup, in the open empty document
                self.assertEqual(made[1:], [x["tool"] for x in before])  # then each step done for the person
                self.assertEqual(c.e.state, "step")

    def test_course_chapters_in_order(self):
        have = by_id()
        self.assertEqual([have[i]["course"]["chapter"] for i in COURSE], [1, 2, 3])
        self.assertEqual(have[COURSE[2]]["setup"]["after"], COURSE[1])
        for i in COURSE:
            self.assertTrue(have[i].get("result"), i)  # the next chapter goes on from it
            n = len([s for s in have[i]["steps"] if s["id"] not in lessons.detours(have[i])])
            self.assertLessEqual(n, lessons.INLINE_MAX_STEPS)

    def test_bike_stem_checks_what_the_course_asks(self):
        have = by_id()
        text = json.dumps(have[COURSE[0]])
        for want in ('"plane": "XZ"', '"dia": 21', '"height": 47', '"rear": 27', '"size": 55', '"pad": 22',
                     '"full": true', '"uses": "size", "count": 2', '"follows": "size"'):
            self.assertIn(want, text)
        text = json.dumps(have[COURSE[1]])
        for want in ('"Two distances"', '"s1": 8', '"s2": 5'):
            self.assertIn(want, text)
        text = json.dumps(have[COURSE[2]])
        for want in ('"external": 2', '"r": 14.5', '"radii": ["$r"]', '"equal"', '"pad": 2.5', '"follows": "size"'):
            self.assertIn(want, text)


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
