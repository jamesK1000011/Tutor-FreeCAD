# SPDX-License-Identifier: LGPL-2.1-or-later
# The Tutor tab, read as code (no Qt, no FreeCAD): every control it makes is
# in CONTROLS (so _access gives it a tooltip, a name and a description),
# each tooltip is short STE that ends with a full stop, and the tab and the
# window code have no fixed "#rrggbb" colour in a function (the callout's
# colours come from bubble.colours, which keeps 4.5:1 on light and dark).
import ast
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agentlink_tutor import tab  # noqa: E402

CONTROL_CLASSES = {"QPushButton", "QToolButton", "QLineEdit", "QSpinBox", "QDoubleSpinBox", "QComboBox",
                   "QCheckBox", "QRadioButton", "QSlider", "QPlainTextEdit", "QTextEdit"}
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def _name(f):
    return getattr(f, "attr", None) or getattr(f, "id", None)


class TabControls(unittest.TestCase):
    def test_every_control_is_in_controls(self):
        keys = {k for k, _n, _d in tab.CONTROLS}
        tree = ast.parse(open(os.path.join(ROOT, "agentlink_tutor", "tab.py"), encoding="utf-8").read())
        made = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and _name(n.value.func) in CONTROL_CLASSES:
                for t in n.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                        made.add(t.attr)
        made |= {"back", "next", "hint", "skip", "do", "stop"}  # the grid of lesson buttons (self.b)
        self.assertEqual(sorted(made - keys), [])

    def test_each_tooltip_is_short_ste(self):
        for key, _name_, desc in tab.CONTROLS:
            self.assertTrue(desc.endswith("."), key)
            self.assertLessEqual(len(desc), 170, key)
            for sentence in re.split(r"(?<=\.) ", desc):
                self.assertLessEqual(len(sentence.split()), 20, (key, sentence))


class TabColours(unittest.TestCase):
    def test_no_fixed_hex_colour_in_a_function(self):
        found = []
        for rel in ("agentlink_tutor/tab.py", "agentlink_tutor/window.py"):
            tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
            for f in ast.walk(tree):
                if isinstance(f, (ast.FunctionDef, ast.Lambda)):
                    for n in ast.walk(f):
                        if isinstance(n, ast.Constant) and isinstance(n.value, str) and HEX.search(n.value):
                            found.append(f"{rel}:{n.lineno}")
        self.assertEqual(sorted(set(found)), [])


if __name__ == "__main__":
    unittest.main()
