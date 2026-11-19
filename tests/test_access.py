# SPDX-License-Identifier: LGPL-2.1-or-later
# Accessibility (T6): the Tutor tab works from the keyboard alone (Tab
# reaches every control in reading order, the lesson's buttons have keys),
# a screen reader has a name and a description for every control and hears
# the step when it changes, the callout keeps its contrast in light and dark
# themes, the words scale (100 to 200 %), and Reduce motion keeps the
# camera still between steps. The tab is built here on a stand-in Qt.
import copy
import types
import unittest

from test_general import CONSTRAINT, PART_BOX, TD_PAGE, World, starters

from agentlink_tutor import bubble, prefs, run, tab
from agentlink_tutor.engine import Engine


# ---- a stand-in Qt: every call recorded, enough answers for the tab ------------------

class Signal:
    def __init__(self):
        self.fns = []

    def connect(self, fn):
        self.fns.append(fn)

    def emit(self, *a):
        for fn in self.fns:
            fn(*a)


class Font:
    def __init__(self, other=None):
        self.size = getattr(other, "size", 13.0)
        self.bold = self.italic = False

    def pointSizeF(self):
        return self.size

    def setPointSizeF(self, v):
        self.size = v

    def setBold(self, b):
        self.bold = b

    def setItalic(self, b):
        self.italic = b


class Widget:
    made = []

    def __init__(self, *a, **kw):
        self.args = a
        self.calls = {}
        self.items = []
        self.index = 0
        self.enabled = True
        self.checked = False
        self.text_ = a[0] if a and isinstance(a[0], str) else ""
        self._font = Font()
        for sig in ("clicked", "toggled", "currentIndexChanged", "returnPressed", "destroyed", "activated"):
            setattr(self, sig, Signal())
        Widget.made.append(self)

    def __getattr__(self, name):
        def rec(*a, **kw):
            self.calls.setdefault(name, []).append(a)
            return None
        return rec

    def font(self):
        return self._font

    def setFont(self, f):
        self._font = f

    def addItem(self, text, data=None):
        self.items.append((text, data))

    def count(self):
        return len(self.items)

    def findData(self, d):
        return next((i for i, (_t, x) in enumerate(self.items) if x == d), -1)

    def setCurrentIndex(self, i):
        self.index = i

    def currentIndex(self):
        return self.index

    def currentData(self):
        return self.items[self.index][1] if 0 <= self.index < len(self.items) else None

    def itemData(self, *a):
        return None

    def setEnabled(self, on):
        self.enabled = on

    def isEnabled(self):
        return self.enabled

    def setChecked(self, on):
        self.checked = on

    def isChecked(self):
        return self.checked

    def click(self):
        self.calls.setdefault("click", []).append(())
        self.clicked.emit(False)

    def text(self):
        return self.text_

    def setText(self, t):
        self.text_ = t
        self.calls.setdefault("setText", []).append((t,))

    def last(self, name):
        return self.calls.get(name, [()])[-1]


ORDER = []


class QWidget(Widget):
    @staticmethod
    def setTabOrder(a, b):
        ORDER.append((a, b))


class KeySequence:
    NativeText = "native"

    def __init__(self, keys):
        self.keys = keys

    def toString(self, fmt=None):
        return self.keys.replace("Alt+", "⌥")


class Shortcut(Widget):
    pass


def fake_qt():
    Qt = types.SimpleNamespace(StrongFocus="strong", WidgetWithChildrenShortcut="tab-only", MarkdownText=1, ToolTipRole=3)
    QtCore = types.SimpleNamespace(Qt=Qt)
    acc = types.SimpleNamespace(NameChanged="name", told=[])
    acc.updateAccessibility = lambda ev: acc.told.append(ev)
    QtGui = types.SimpleNamespace(QFont=Font, QKeySequence=KeySequence, QShortcut=Shortcut, QAccessible=acc,
                                  QAccessibleEvent=lambda w, kind: (w, kind))
    names = ("QVBoxLayout", "QHBoxLayout", "QGridLayout", "QComboBox", "QPushButton", "QLabel", "QCheckBox", "QLineEdit")
    QtW = types.SimpleNamespace(QWidget=QWidget, QApplication=types.SimpleNamespace(font=lambda: Font()),
                                **{n: type(n, (Widget,), {}) for n in names})
    QtW.QComboBox.SizeAdjustPolicy = types.SimpleNamespace(AdjustToMinimumContentsLengthWithIcon=0)
    return QtCore, QtGui, QtW


class FakeTab(unittest.TestCase):
    def setUp(self):
        self.was = (tab._qt, dict(tab._CLS), dict(prefs._MEM.values))
        tab._qt = fake_qt
        tab._CLS.clear()
        ORDER.clear()
        Widget.made.clear()
        self.t = tab.TutorTab(types.SimpleNamespace())

    def tearDown(self):
        tab._qt = self.was[0]
        tab._CLS.clear()
        tab._CLS.update(self.was[1])
        prefs._MEM.values.clear()
        prefs._MEM.values.update(self.was[2])

    def test_every_control_has_a_name_a_description_and_tab_focus(self):
        for key, name, desc in tab.CONTROLS:
            with self.subTest(control=key):
                w = self.t._widget(key)
                self.assertEqual(w.last("setAccessibleName"), (name,))
                self.assertTrue(w.last("setAccessibleDescription")[0])
                self.assertEqual(w.last("setFocusPolicy"), ("strong",))
                self.assertIn(desc.split(":")[0], w.last("setToolTip")[0])
        for lab in (self.t.head, self.t.say, self.t.why, self.t.check, self.t.hint, self.t.line):
            self.assertTrue(lab.calls.get("setAccessibleName"), lab)

    def test_tab_order_is_reading_order(self):
        want = [self.t._widget(k) for k, _n, _d in tab.CONTROLS]
        self.assertEqual(ORDER, list(zip(want, want[1:])))

    def test_keys_work_anywhere_in_the_tab_and_are_in_the_tooltips(self):
        made = {sc.args[0].keys: sc for sc in self.t._keys}
        self.assertEqual(set(made), set(tab.SHORTCUTS.values()))
        for key, keys in tab.SHORTCUTS.items():
            with self.subTest(control=key):
                sc = made[keys]
                self.assertEqual(sc.last("setContext"), ("tab-only",))  # never the whole window's
                self.assertIn(keys.replace("Alt+", "⌥"), self.t._widget(key).last("setToolTip")[0])
        hint = self.t.b["hint"]
        hint.setEnabled(True)
        clicked = []
        hint.clicked.connect(lambda *_a: clicked.append(1))
        made["Alt+Shift+H"].activated.emit()
        self.assertEqual(clicked, [1])
        hint.setEnabled(False)
        made["Alt+Shift+H"].activated.emit()
        self.assertEqual(clicked, [1])  # off: the key does nothing
        made["Alt+Shift+A"].activated.emit()
        self.assertTrue(self.t.question.calls.get("setFocus"))

    def test_text_size_and_reduce_motion_kept(self):
        # Put back after: with FreeCAD here they are its own parameters,
        # which the later tests read (a step's own view, reduced motion off).
        self.addCleanup(prefs.set_reduce_motion, prefs.reduce_motion())
        self.addCleanup(prefs.set_text_scale, prefs.text_scale())
        self.assertEqual(self.t.font().size, 13.0)
        self.t.scale.setCurrentIndex(self.t.scale.findData(150))
        self.t.scale.currentIndexChanged.emit(2)
        self.assertEqual(prefs.text_scale(), 150)
        self.assertAlmostEqual(self.t.font().size, 19.5)
        self.assertAlmostEqual(self.t.why.font().size, 19.5 * 0.9)
        self.assertTrue(self.t.head.font().bold)
        self.t.motion.toggled.emit(True)
        self.assertTrue(prefs.reduce_motion())

    def test_every_label_has_a_name_for_a_screen_reader(self):
        labels = [w for w in Widget.made if type(w).__name__ == "QLabel"]
        self.assertGreaterEqual(len(labels), 8)
        for lab in labels:
            self.assertTrue(lab.calls.get("setAccessibleName"), lab.args)
        self.assertEqual(self.t.pic.last("setAccessibleName"), ("Picture of this step",))
        self.assertEqual(self.t.credit.last("setAccessibleName"), ("Lesson credit",))

    def test_the_step_is_announced_once_when_it_changes(self):
        st = {"lesson": "x", "step": "2/5", "say": "Push Pad.", "check": "pending"}
        self.t._announce(st)
        self.t._announce(st)
        said = [a for a in self.t.say.calls["setAccessibleName"] if a == ("Step 2/5. Push Pad.",)]
        self.assertEqual(len(said), 1)


class Words(unittest.TestCase):
    def test_tables_agree(self):
        keys = [k for k, _n, _d in tab.CONTROLS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(set(tab.SHORTCUTS) <= set(keys))
        self.assertEqual(len(set(tab.SHORTCUTS.values())), len(tab.SHORTCUTS))
        self.assertEqual(tab.tip("next"), "Check this step, then go on. (Alt+Shift+Right)")
        self.assertEqual(tab.tip("explain"), tab.control("explain")[1])

    def test_announcement(self):
        self.assertEqual(tab.announcement(None), "No lesson running. Select a lesson and push Start, or ask Claude to show you something.")
        self.assertEqual(tab.announcement({"lesson": "x", "step": "1/3", "say": "Push Pad.", "check": "pass"}), "Step 1/3 · done. Push Pad.")


class Contrast(unittest.TestCase):
    THEMES = {
        "dark": {"bubble": "#26292e", "bubble_text": "#f2f2f2", "accent": "#3f93e0"},
        "light": {"bubble": "#fbfbfb", "bubble_text": "#1d1f23", "accent": "#2a6fc9"},
        "bad text": {"bubble": "#777777", "bubble_text": "#888888", "accent": "#7a7a7a"},
        "pale accent": {"bubble": "#ffffff", "bubble_text": "#000000", "accent": "#e8f0ff"},
        "none given": {},
    }

    def test_words_why_line_and_edge_stand_out_in_every_theme(self):
        for name, col in self.THEMES.items():
            with self.subTest(theme=name):
                c = bubble.colours(col)
                self.assertGreaterEqual(bubble.contrast(c["text"], c["fill"]), bubble.TEXT_CONTRAST)
                self.assertGreaterEqual(bubble.contrast(c["dim"], c["fill"]), bubble.TEXT_CONTRAST)
                self.assertGreaterEqual(bubble.contrast(c["edge"], c["fill"]), bubble.EDGE_CONTRAST)
        dark = bubble.colours(self.THEMES["dark"])
        self.assertNotEqual(dark["dim"], dark["text"])  # still dimmer where it can be

    def test_contrast_ratio(self):
        self.assertAlmostEqual(bubble.contrast("#000000", "#ffffff"), 21.0, places=3)
        self.assertAlmostEqual(bubble.contrast("#777777", "#777777"), 1.0)


class Scale(unittest.TestCase):
    def test_kept_within_100_and_200(self):
        p = prefs.Memory()
        self.assertEqual(prefs.text_scale(p), 100)
        self.assertEqual(prefs.set_text_scale(400, p), 200)
        self.assertEqual(prefs.set_text_scale(50, p), 100)
        prefs.set_text_scale(125, p)
        self.assertEqual(prefs.scaled(12, p), 15.0)


class FrameUI:
    def __init__(self):
        self.log = []

    def settle(self, doc=None):
        self.log.append("settle")

    def frame(self, view, doc=None, animate=True):
        self.log.append(("frame", view, animate))


class ReduceMotion(unittest.TestCase):
    def run_lesson(self, lesson, reduce):
        p = prefs.Memory()
        prefs.set_reduce_motion(reduce, p)
        w = World()
        e = Engine(copy.deepcopy(lesson), call=w, doc=lambda: w.doc)
        ui = FrameUI()
        c = run.Controller(e, ui=ui, prefs=p)
        c.start("demo")
        while c.e.state == "step":
            c.act("skip")
        return [x for x in ui.log if x != "settle"]

    def test_camera_still_between_steps_for_every_lesson(self):
        for lesson in starters() + [PART_BOX, TD_PAGE, CONSTRAINT]:
            with self.subTest(lesson=lesson["id"]):
                still = self.run_lesson(lesson, True)
                want = lesson.get("view", "isometric")
                if want == "keep":
                    self.assertEqual(still, [])
                else:
                    self.assertEqual(still, [("frame", want, False)])  # framed once, no animation
                moving = self.run_lesson(lesson, False)
                self.assertTrue(all(x[2] for x in moving))


class Keys(unittest.TestCase):
    """The lesson's keys clash with none of FreeCAD 1.1.3's own: Alt+Return
    (Properties), Alt with a menu's letter (Alt+H opens Help on Windows and
    Linux), and its other Alt keys (data/freecad_keys.json)."""

    def test_no_clash_with_freecad(self):
        import json
        import os

        with open(os.path.join(os.path.dirname(tab.__file__), "data", "freecad_keys.json"), encoding="utf-8") as f:
            fc = json.load(f)
        taken = {k.lower() for k in fc["taken"]} | {f"alt+{c}".lower() for c in fc["menu_letters"]}
        for key, seq in tab.SHORTCUTS.items():
            with self.subTest(control=key):
                self.assertNotIn(seq.lower(), taken)
                self.assertTrue(seq.startswith("Alt+Shift+"), seq)  # never a menu's letter
        self.assertIn("alt+return", taken)
        self.assertIn("alt+h", taken)


class NeverTimesOut(unittest.TestCase):
    """A step waits for the person as long as they need: no timer moves a
    lesson on or ends it while its step is not done. The only timers are the
    re-check after the person acts, the auto-advance after a pass, and the
    rings kept a moment after the lesson is done."""

    def test_a_pending_step_waits_whatever_the_timers_do(self):
        from test_run import Clock, make

        for window in (True, False):
            clock = Clock()
            w, c = make(timer=clock, window=window)
            c.start("guided")
            first = c.e.step["id"]
            for _ in range(50):
                c.poke()
                clock.flush()
            self.assertEqual(c.e.step["id"], first)
            self.assertEqual(c.e.state, "step")
            self.assertTrue(all(ms in (run.DEBOUNCE_MS, run.ADVANCE_MS, run.HOLD_MS) for ms, _ in clock.due))

    def test_no_lesson_has_a_time_limit(self):
        schema = __import__("agentlink_tutor.lessons", fromlist=["schema"]).schema()
        words = json_words(schema)
        for w in ("timeout", "time_limit", "deadline", "expires"):
            self.assertNotIn(w, words)

    def test_do_it_for_me_on_every_step_that_has_a_check(self):
        from agentlink_tutor import lessons

        for lesson in starters():
            main = [s for s in lesson["steps"] if s["id"] not in lessons.detours(lesson)]
            for s in main[:-1]:
                with self.subTest(lesson=lesson["id"], step=s["id"]):
                    self.assertTrue(s.get("do"))


def json_words(x):
    import json

    return json.dumps(x).lower()


class NotColourAlone(unittest.TestCase):
    """A ring is never told by its colour alone: each carries its number,
    and the words name that number."""

    def test_each_ring_has_its_number(self):
        from test_point import run as point_run

        out, ov, _ = point_run({"targets": [{"cmd": "Std_Undo"}, {"cmd": "Std_Redo"}], "say": "Undo it."})
        badges = [sp.get("badge") for show in ov.shows for sp in show["specs"]]
        self.assertTrue(badges)
        self.assertTrue(all(isinstance(b, int) and b >= 1 for b in badges), badges)
        self.assertEqual(len(set(badges)), len(badges))


if __name__ == "__main__":
    unittest.main()
