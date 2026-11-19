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


class AllowList(unittest.TestCase):
    """Red team 3 (19 Nov 2026), R3-5: an allow list of lesson tools. A
    printer, slicer, pack or writer call from "Do it for me" would look like
    the person's own."""

    TRAPS = ("printer_send", "printer_stop", "printer_pause", "printer_add", "slice", "slice_with", "slicer_presets", "orca_project", "orca_slice",
             "orca_calibrate", "pack_setup", "library_pack", "own_pack", "texture_export", "texture_prepare", "drawing_make", "td_export",
             "doc_save", "export_file", "menu_run", "a_tool_from_later")

    def test_tools_off_the_list_are_refused(self):
        for tool in self.TRAPS:
            self.assertNotIn(tool, lessons.LESSON_TOOLS)
            for where in ("do", "setup", "else"):
                with self.subTest(tool=tool, where=where):
                    with self.assertRaises(lessons.LessonError) as e:
                        lessons.inline(lesson(tool, where))
                    self.assertIn("never calls", str(e.exception))

    def test_confirm_and_force_are_refused(self):
        for args in ({"confirm": "start Octo"}, {"force": True}, {"object": "Box", "set": {"confirm": "x"}}):
            les = lesson("object_set")
            les["steps"][0]["do"][0]["args"] = args
            with self.subTest(args=args):
                with self.assertRaises(lessons.LessonError) as e:
                    lessons.inline(les)
                self.assertIn("never", str(e.exception))
        # fea_load's force is a vector, not a gate: it stays.
        self.assertEqual(lessons.call_problems("fea_load", {"force": [0, 0, -9]}), [])

    def test_file_tools_take_a_plain_name(self):
        self.assertEqual(lessons.call_problems("export", {"objects": ["$body"], "format": "stl", "path": "Part.stl"}), [])
        for bad in ("~/.zshrc", "/tmp/x.stl", "../x.stl", "$path", ".hidden.stl", "a/b.stl"):
            with self.subTest(path=bad):
                self.assertTrue(lessons.call_problems("export", {"path": bad}))

    def test_cmd_run_takes_few_commands(self):
        self.assertEqual(lessons.call_problems("cmd_run", {"name": "Sketcher_LeaveSketch"}), [])
        self.assertEqual(lessons.call_problems("cmd_run", {"name": "Std_ViewFitAll"}), [])
        for bad in ("Std_DlgMacroExecuteDirect", "Std_Quit", "Std_DlgPreferences"):
            self.assertTrue(lessons.call_problems("cmd_run", {"name": bad}), bad)

    def test_every_shipped_lesson_passes(self):
        import glob
        import json
        import os

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        files = glob.glob(os.path.join(lessons.CORE_DIR, "*" + lessons.SUFFIX))
        files += glob.glob(os.path.join(here, "docs", "examples", "**", "*" + lessons.SUFFIX), recursive=True)
        self.assertGreater(len(files), 20)
        for f in files:
            with open(f, encoding="utf-8") as fh:
                les = json.load(fh)
            with self.subTest(lesson=os.path.basename(f)):
                self.assertEqual(lessons._never_problems(les), [])

    def test_engine_refuses_calls_off_the_list(self):
        ran = []
        e = engine.Engine.__new__(engine.Engine)
        e.call = lambda tool, args: (ran.append(tool), (False, {}))[1]
        with self.assertRaises(engine.TutorError):
            e._run([{"tool": "printer_send", "args": {}}], "step a")
        with self.assertRaises(engine.TutorError):
            e._run([{"tool": "object_set", "args": {"confirm": "yes"}}], "step a")
        self.assertEqual(ran, [])


class CleanText(unittest.TestCase):
    """R3-11: lesson text reaches the agent without invisible characters."""

    def test_clean(self):
        from agentlink_tutor import tool

        got = tool.clean({"say": "Push **Pad**.​‮\U000e0049\U000e0047", "list": ["a⁦b"], "n": 3})
        self.assertEqual(got, {"say": "Push **Pad**.", "list": ["ab"], "n": 3})
        self.assertEqual(tool.clean("× › ° ✓"), "× › ° ✓")

    def test_tutor_answers_are_cleaned(self):
        from unittest import mock

        from agentlink_tutor import point, tool

        with mock.patch.object(tool, "_tutor", return_value={"say": "Do‍ it\U000e0041"}):
            self.assertEqual(tool.tutor({}, None, None), {"say": "Do it"})
        with mock.patch.object(tool, "_tutor", side_effect=point.Refusal("invalid_input", "bad​ lesson")):
            with self.assertRaises(point.Refusal) as e:
                tool.tutor({}, None, None)
            self.assertEqual(e.exception.message, "bad lesson")
