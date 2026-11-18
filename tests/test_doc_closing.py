# SPDX-License-Identifier: LGPL-2.1-or-later
# Live 62: doc_close on the running lesson's document. Agent Link emits
# document_closing(session, name) first; the Tutor stops that lesson, and
# leaves a lesson on another document alone.
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from agentlink_tutor import live  # noqa: E402


class Ctl:
    def __init__(self, doc):
        self.e = types.SimpleNamespace(doc_name=doc, state="step")
        self.listeners, self.acts, self.show = [], [], None

    def act(self, action):
        self.acts.append(action)
        self.e.state = "stopped"


class DocumentClosing(unittest.TestCase):
    def setUp(self):
        self.was = live.NOW["ctl"]
        self.addCleanup(live.NOW.__setitem__, "ctl", self.was)

    def test_the_lesson_document(self):
        c = Ctl("Film_hinge")
        live.NOW["ctl"] = c
        self.assertTrue(live.document_closing(None, "Film_hinge"))
        self.assertEqual(c.acts, ["stop"])
        self.assertIsNone(live.controller())

    def test_another_document(self):
        c = Ctl("Film_hinge")
        live.NOW["ctl"] = c
        self.assertFalse(live.document_closing(None, "M18Build"))
        self.assertEqual(c.acts, [])
        self.assertIs(live.controller(), c)

    def test_no_lesson(self):
        live.NOW["ctl"] = None
        self.assertFalse(live.document_closing(None, "Any"))


if __name__ == "__main__":
    unittest.main()
