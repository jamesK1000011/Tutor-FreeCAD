# SPDX-License-Identifier: LGPL-2.1-or-later
# Red team, 2026-11-18: a lesson is data from an add-on or an agent. Its
# calls never reach the tools that run or install code, change settings,
# hold the person's OK or drive the window's input.
import unittest

import fakes  # noqa: F401  (puts the repository on the path)

from agentlink_tutor import engine, lessons  # noqa: E402


def lesson(tool, where="do", **extra):
    steps = [{"id": "a", "say": "Make a pad.", "check": {"new": "PartDesign::Pad"}}]
    les = {"schema": 1, "id": "inline.trap", "version": "1.0.0", "title": "Trap", "setup": {"doc": "new"}, "steps": steps}
    call = {"tool": tool, "args": {"name": "x"}}
    if where == "do":
        steps[0]["do"] = [call]
    elif where == "setup":
        les["setup"] = {"calls": [call]}
    else:
        steps[0]["do"] = [{"tool": "pd_pad", "args": {}, "else": [call]}]
    les.update(extra)
    return les


class Lessons(unittest.TestCase):
    TRAPS = ("cookbook_approve", "cookbook_run", "macro_approve", "addon", "app_extensions", "gui_input", "dialog_answer", "pref_set",
             "batch", "job_start", "live_run", "agentlink_update", "addon_test", "port_scaffold")

    def test_dangerous_calls_are_refused_in_do_setup_and_else(self):
        for tool in self.TRAPS:
            for where in ("do", "setup", "else"):
                with self.subTest(tool=tool, where=where):
                    with self.assertRaises(lessons.LessonError) as e:
                        lessons.inline(lesson(tool, where))
                    self.assertIn("never calls", str(e.exception))

    def test_stored_lessons_hold_no_such_call(self):
        import json
        import os

        for n in os.listdir(lessons.CORE_DIR):
            if n.endswith(lessons.SUFFIX):
                with open(os.path.join(lessons.CORE_DIR, n), encoding="utf-8") as f:
                    les = json.load(f)
                self.assertEqual([p for p in lessons.check(les) if "never calls" in p], [], n)

    def test_engine_refuses_a_lesson_that_was_not_checked(self):
        ran = []
        e = engine.Engine.__new__(engine.Engine)
        e.call = lambda tool, args: (ran.append(tool), (False, {}))[1]
        with self.assertRaises(engine.TutorError):
            e._run([{"tool": "gui_input", "args": {}}], "step a")
        self.assertEqual(ran, [])

    def test_an_inline_lesson_cannot_set_the_loaders_keys(self):
        les = lessons.inline(dict(lesson("pd_pad"), _folder="/", _owner="agentlink_tutor"))
        self.assertNotIn("_folder", les)
        self.assertNotIn("_owner", les)


if __name__ == "__main__":
    unittest.main()
