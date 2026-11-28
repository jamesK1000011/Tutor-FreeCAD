# SPDX-License-Identifier: LGPL-2.1-or-later
# The round-4 picture review of tutor_point, with stand-ins (no FreeCAD, no
# Qt): a tree target whose Model tab is behind the Tutor's own tab (the
# Model tab is brought forward and the row ringed, not the tab); the
# bubble's height from its words plus the stylesheet's padding; a lit face
# the view does not show (missing, with why, never silent); and the
# deferred calls (owned by a long-lived QObject, stopped with their target,
# alive-checked before they touch anything).
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import test_window_prep as wp  # noqa: E402  (its little Qt)

from agentlink_tutor import bubble, gui_run, later, live, point, run, targets, window  # noqa: E402


# ---- a little QtCore: objects that can die, timers fired by hand ----------------------------

class QObject:
    def __init__(self, parent=None):
        self._parent, self.dead, self.name = parent, False, ""

    def setObjectName(self, n):
        self.name = n

    def objectName(self):
        return self.name


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)


class QTimer(QObject):
    made = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeout = Signal()
        self.ms = self.running = None
        QTimer.made.append(self)

    def setSingleShot(self, on):
        self.single = on

    def start(self, ms):
        self.ms, self.running = ms, True

    def stop(self):
        self.running = False

    def deleteLater(self):
        self.dead = True

    def fire(self):
        """What Qt's event loop does when it comes due; a timer that is
        deleted (or whose parent is: Qt deletes children) never fires."""
        p = self
        while p is not None:
            if p.dead:
                return False
            p = p._parent
        if not self.running:
            return False
        self.running = False
        for s in self.timeout.slots:
            s()
        return True


QtCore = types.SimpleNamespace(QObject=QObject, QTimer=QTimer,
                               QCoreApplication=types.SimpleNamespace(instance=lambda: None))
SHIBOKEN = types.SimpleNamespace(isValid=lambda o: not getattr(o, "dead", False))


class FakeQt(unittest.TestCase):
    def setUp(self):
        self.was = (later._qt, later._shiboken, dict(later._OWNER))
        later._qt = lambda: QtCore
        later._shiboken = lambda: SHIBOKEN
        later._OWNER["o"] = None
        later._LIVE.clear()
        QTimer.made = []

    def tearDown(self):
        later._qt, later._shiboken = self.was[0], self.was[1]
        later._OWNER.clear()
        later._OWNER.update(self.was[2])
        later._LIVE.clear()


# ---- deferred calls ---------------------------------------------------------------------------

class Later(FakeQt):
    def test_owned_by_one_long_lived_object_and_fired_once(self):
        got = []
        h = later.after(250, lambda: got.append(1))
        t = QTimer.made[-1]
        self.assertIs(t._parent, later.owner())  # never a bare singleShot
        self.assertEqual(later.owner().objectName(), "TutorTimers")
        self.assertEqual((t.ms, t.single), (250, True))
        self.assertEqual(later.waiting(), 1)
        self.assertTrue(t.fire())
        self.assertEqual(got, [1])
        self.assertTrue(h.done and t.dead)  # deleted after it fired
        self.assertEqual(later.waiting(), 0)

    def test_a_timer_on_a_widget_dies_with_it(self):
        lab = QObject()
        got = []
        later.after(400, lambda: got.append("touched"), target=lab)
        t = QTimer.made[-1]
        self.assertIs(t._parent, lab)  # a child: Qt deletes it with the label
        lab.dead = True  # the 3D view (and the label) closed
        self.assertFalse(t.fire())
        self.assertEqual(got, [])

    def test_a_dead_target_is_checked_before_the_call(self):
        # The target is no QObject parent here (a stand-in), so the timer
        # fires; the call still sees the target is gone and is dropped.
        target = types.SimpleNamespace(dead=False)
        got = []
        h = later.after(10, lambda: got.append("touched"), target=target)
        target.dead = True
        h.fire()
        self.assertEqual(got, [])
        self.assertTrue(h.done)

    def test_a_dead_owner_drops_the_call_and_a_new_owner_is_made(self):
        got = []
        h = later.after(10, lambda: got.append(1))
        first = later.owner()
        first.dead = True
        h.fire()
        self.assertEqual(got, [])
        self.assertIsNot(later.owner(), first)

    def test_stop_and_stop_group(self):
        got = []
        a = later.after(10, lambda: got.append("a"), group="lesson-1")
        b = later.after(10, lambda: got.append("b"), group="lesson-2")
        ta, tb = QTimer.made[-2:]
        later.stop_group("lesson-1")
        self.assertFalse(ta.fire())
        self.assertTrue(a.done and ta.dead and not b.done)
        b.stop()
        self.assertFalse(tb.fire())
        self.assertEqual(got, [])

    def test_a_failing_call_does_not_raise_into_the_event_loop(self):
        def boom():
            raise RuntimeError("Internal C++ object already deleted.")

        later.after(10, boom)
        self.assertTrue(QTimer.made[-1].fire())  # said on stderr, not raised


class LessonTimers(FakeQt):
    def test_a_replaced_lesson_takes_its_waiting_calls_with_it(self):
        from test_run import make

        _w, c = make(timer=gui_run.timer)
        fired = []
        c._later(30000, lambda: fired.append("hold: show(None)"))  # the done lesson's hold
        c._later(600, lambda: fired.append("advance"))
        self.assertEqual(len(c._waiting), 2)
        was = live.NOW["ctl"]
        try:
            live.set_controller(c)
            live.set_controller(None)  # another lesson (or none) takes its place
        finally:
            live.NOW["ctl"] = was
        self.assertEqual(c._waiting, [])
        self.assertTrue(all(not t.fire() for t in QTimer.made))
        self.assertEqual(fired, [])

    def test_fam_tutor_ms_timer_is_owned(self):
        try:
            from agentlink_tutor import fam_tutor
        except ImportError:
            self.skipTest("needs an Agent Link checkout ($AGENTLINK_SRC)")

        h = fam_tutor._timer(500, lambda: None)
        self.assertIsNotNone(h)
        self.assertIs(QTimer.made[-1]._parent, later.owner())


class BubbleTimers(FakeQt):
    def setUp(self):
        super().setUp()
        self.state = dict(bubble._STATE)

    def tearDown(self):
        bubble._STATE.clear()
        bubble._STATE.update(self.state)
        super().tearDown()

    def test_recheck_and_hide_after_are_children_of_the_label(self):
        lab, host = QObject(), QObject()
        bubble._STATE.update(w=lab, a=None, host=host)
        bubble._recheck_later(types.SimpleNamespace(text=lambda: "Push Pad."), {})
        bubble.hide_after(5000)
        self.assertEqual(len(QTimer.made), len(bubble.RECHECK_MS) + 1)
        self.assertTrue(all(t._parent is lab for t in QTimer.made))
        lab.dead = True  # its 3D view closed during Gui.updateGui()
        self.assertFalse(any(t.fire() for t in QTimer.made))

    def test_a_recheck_on_a_closed_view_touches_nothing(self):
        touched = []

        class Lab(QObject):
            def hide(self):
                touched.append("hide")

            def geometry(self):
                touched.append("geometry")

        lab, host = Lab(), QObject()
        host.dead = True  # the view went; the label is alive a moment longer
        bubble._STATE.update(w=lab, a=None, host=host, gen=5)
        bubble._recheck_later(types.SimpleNamespace(text=lambda: "Push Pad."), {})
        QTimer.made[0].fire()
        self.assertEqual(touched, [])
        self.assertIsNone(bubble._STATE["w"])

    def test_hide_skips_a_dead_label(self):
        touched = []

        class Lab(QObject):
            def hide(self):
                touched.append(self)

        dead, alive = Lab(), Lab()
        dead.dead = True
        bubble._STATE.update(w=dead, a=alive)
        bubble.hide()
        self.assertEqual(touched, [alive])
        self.assertIsNone(bubble._STATE["w"])


# ---- the bubble's height ------------------------------------------------------------------------

class TextDoc:
    """QTextDocument: lines of 20 px, wrapped every 30 characters per 100 px."""

    seen = {}

    def setDefaultFont(self, f):
        TextDoc.seen["font"] = f

    def setHtml(self, h):
        self.h = h

    def setTextWidth(self, w):
        TextDoc.seen["width"] = w
        self.w = w

    def size(self):
        per_line = max(1, int(30 * self.w / 100))
        lines = -(-len(self.h) // per_line)
        return types.SimpleNamespace(height=lambda: 20.0 * lines + 0.4)


class BubbleHeight(unittest.TestCase):
    def test_measured_inside_the_padding_and_the_padding_added(self):
        QtGui = types.SimpleNamespace(QTextDocument=TextDoc)
        width = 340
        h = bubble.text_height("x" * 400, "font", width - 2 * bubble.frame(), QtGui)
        self.assertEqual(TextDoc.seen, {"font": "font", "width": width - 2 * (bubble.PAD + bubble.BORDER)})
        self.assertEqual(h, 101)  # 5 lines, rounded up
        # Qt's heightForWidth left the stylesheet's padding out (round 4: the
        # text cut in half): the bubble is the words plus padding and border.
        self.assertEqual(bubble.fit_height(h, hfw=80, hint_h=40), 101 + 2 * (bubble.PAD + bubble.BORDER))
        self.assertEqual(bubble.fit_height(0, hfw=80, hint_h=40), 80)  # cannot be told: Qt's own
        self.assertEqual(bubble.fit_height(0, hfw=0, hint_h=40), 40)
        self.assertIn(f"border: {bubble.BORDER}px", bubble.stylesheet(bubble.colours({})))
        self.assertIn(f"padding: {bubble.PAD}px", bubble.stylesheet(bubble.colours({})))

    def test_no_qt_text_document_is_zero(self):
        self.assertEqual(bubble.text_height("x", None, 100, types.SimpleNamespace()), 0)


# ---- a tree target: the Model tab brought forward, the row ringed --------------------------------

class SettableBar(wp.MainTabBar):
    def setCurrentIndex(self, i):
        self.cur = i


class StuckDock(wp.TabbedDock):
    """A dock whose raise_ does not switch the tab (the tab bar must)."""

    def raise_(self):
        self.calls.append("raise")


class FarTree(wp.DockTree):
    """A tree whose Sketch row lies below its viewport until scrolled to."""

    def visualItemRect(self, it):
        top = 0 if (it.text(0) in self.scrolled) else 400
        return types.SimpleNamespace(x=lambda: 0, y=lambda: top, width=lambda: 100, height=lambda: 18,
                                     top=lambda: top, bottom=lambda: top + 18)


class TreeTarget(unittest.TestCase):
    def setUp(self):
        self.was = window._qt
        self.qtw = types.SimpleNamespace(**{**vars(wp.QtW), "QTreeWidget": object})
        window._qt = lambda: (None, None, self.qtw)

    def tearDown(self):
        window._qt = self.was

    def build(self, show_model=True, dock=wp.TabbedDock, tree=wp.DockTree):
        mw = wp.QWidget(name="MainWindow")
        # The Tutor lives in Agent Link's tab: in front while it runs.
        bar = SettableBar(mw, ["Model", "Tasks", "Agent Link"], current=2)
        model = dock(mw, "Model", bar)
        doc = types.SimpleNamespace(Label="PointDoc", Name="PointDoc", Objects=[])
        box = types.SimpleNamespace(Name="PointBox", Label="PointBox", Document=doc, InList=[])
        doc.Objects.append(box)
        doc.getObject = lambda n: box if n == "PointBox" else None
        app = wp.Item("Application", wp.Item("PointDoc", wp.Item("Origin"), wp.Item("PointBox")))
        t = tree(app, model)
        find = mw.findChildren
        mw.findChildren = lambda cls: [t] if cls is object else find(cls)
        calls = []

        def show_model_view():
            calls.append("showModelView")
            model.show()
            model.raise_()

        ctl = types.SimpleNamespace(showModelView=show_model_view) if show_model else types.SimpleNamespace()
        gui = types.SimpleNamespace(getMainWindow=lambda: mw, Control=ctl)
        win = window.Window(gui=gui, hooks=object(), doc=lambda: doc, hands=True)
        win.pump = lambda: None
        return types.SimpleNamespace(mw=mw, bar=bar, model=model, tree=t, box=box, win=win, calls=calls)

    def test_without_hands_the_model_tab_is_ringed_as_before(self):
        w = self.build()
        w.win.hands = False
        self.assertIsNone(w.win.prepare_tree(w.box))
        spec, note = w.win.tree_row(w.box)
        self.assertEqual(note, window.MODEL_TAB)
        self.assertIs(spec["widget"], w.bar)

    def test_show_model_view_then_the_row_is_ringed_not_the_tab(self):
        w = self.build()
        did = w.win.prepare_tree(w.box)
        self.assertEqual(w.calls, ["showModelView"])
        self.assertEqual(did, "the Model tab brought to the front")
        self.assertEqual(w.bar.cur, 0)
        spec, note = w.win.tree_row(w.box)
        self.assertIsNone(note)
        self.assertIs(spec["widget"], w.tree)
        self.assertEqual(spec["rect"](), (0, 0, 100, 18))
        self.assertIsNone(w.win.prepare_tree(w.box))  # in front already: nothing to do

    def test_without_show_model_view_the_dock_is_raised(self):
        w = self.build(show_model=False)
        self.assertEqual(w.win.prepare_tree(w.box), "the Model tab brought to the front")
        self.assertEqual(w.model.calls, ["show", "raise"])
        self.assertEqual(w.bar.cur, 0)

    def test_a_dock_that_raise_does_not_switch_gets_its_tab_made_current(self):
        w = self.build(show_model=False, dock=StuckDock)
        self.assertEqual(w.win.prepare_tree(w.box), "the Model tab brought to the front")
        self.assertEqual(w.bar.cur, 0)

    def test_nothing_works_the_tab_is_ringed_and_said(self):
        w = self.build(show_model=False, dock=StuckDock)
        w.bar.setCurrentIndex = lambda i: None
        self.assertIsNone(w.win.prepare_tree(w.box))
        self.assertEqual(w.win.tree_row(w.box)[1], window.MODEL_TAB)

    def test_the_row_is_scrolled_into_view_first(self):
        w = self.build(tree=FarTree)
        did = w.win.prepare_tree(w.box)
        self.assertEqual(did, "the Model tab brought to the front; PointBox row scrolled into view")
        self.assertEqual(w.tree.scrolled, ["PointBox"])

    def test_point_says_what_it_prepared(self):
        w = self.build()
        ov = types.SimpleNamespace(clear=lambda o: None, colours=lambda: {},
                                   show=lambda specs, **k: {"handle": 1, "hidden": []},
                                   visible=lambda wd: None)
        hooks = types.SimpleNamespace(service=lambda n: ov if n == "overlay" else None)
        w.win._hooks = hooks
        out = point.point({"targets": [{"tree": "PointBox"}]}, w.win, hooks=hooks)
        self.assertEqual(out["prepared"], [{"did": "tabFront", "tab": "Model"}])
        self.assertEqual([a["kind"] for a in out["shown"]], ["tree"])
        self.assertNotIn("text", out["shown"][0])  # no "Open the Model tab."


# ---- a lit face the view does not show ------------------------------------------------------------

class View:
    """FreeCAD's 3D view: points to pixels, and what each pixel shows."""

    def __init__(self, at, shows=None, size=(800, 600)):
        self.at, self.show, self.size = at, shows or {}, size
        self.picks = 0

    def getSize(self):
        return self.size

    def getPointOnScreen(self, p):
        return self.at[tuple(p)]

    def getObjectInfo(self, xy):
        self.picks += 1
        return self.show.get(xy)


class FaceSeen(unittest.TestCase):
    PTS = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]

    def test_seen_off_screen_and_hidden(self):
        names = {"PointBox"}
        on = View({p: (100 + i, 100) for i, p in enumerate(self.PTS)},
                  {(101, 100): {"Object": "PointBox", "Component": "Face6"}})
        self.assertEqual(window.seen_on(on, names, "Face6", self.PTS), (2, True))
        off = View({p: (-50, 900) for p in self.PTS})
        self.assertEqual(window.seen_on(off, names, "Face6", self.PTS), (0, False))
        self.assertEqual(off.picks, 0)  # nothing asked of pixels outside the view
        covered = View({p: (100, 100) for p in self.PTS}, {(100, 100): {"Object": "Preview", "Component": "Face1"}})
        self.assertEqual(window.seen_on(covered, names, "Face6", self.PTS), (3, False))
        self.assertTrue(window.unseen_why([("Face6", 0, 3)], "PointBox").startswith("off-screen: no point of Face6"))
        self.assertEqual(window.unseen_why([("Face6", 3, 3)], "PointBox"),
                         "hidden: something else is drawn over Face6 at all 3 of its points inside the 3D view")

    def test_picks_are_bounded(self):
        pts = [(i, 0, 0) for i in range(200)]
        v = View({p: (10, 10) for p in pts})
        window.seen_on(v, {"X"}, "Face1", pts)
        self.assertEqual(v.picks, window.SEEN_PICKS)

    def run_point(self, unseen):
        lit = []
        ov = types.SimpleNamespace(clear=lambda o: None, colours=lambda: {"accent": "#123456"},
                                   show=lambda specs, say=None, **k: lit.append(("say", say)) or {"handle": 1, "hidden": []})
        ann = types.SimpleNamespace(clear=lambda o: None,
                                    light=lambda obj, subs, **k: lit.append(("light", list(subs))) or {"lit": list(subs), "missing": []})
        hooks = types.SimpleNamespace(service=lambda n: {"overlay": ov, "annotations": ann}.get(n))
        box = types.SimpleNamespace(Name="PointBox", Label="PointBox")
        asked = []
        win = types.SimpleNamespace(obj=lambda r: box, faces=lambda o, q: (["Face6"], None),
                                    light_seen=lambda o, subs: asked.append((o.Name, list(subs))) or unseen,
                                    command_info=lambda c: {"shortcut": "V, F"} if c == "Std_ViewFitAll" else {})
        out = point.point({"targets": [{"face": {"normal": [0, 0, 1]}, "of": "PointBox"}], "say": "Look at the top."},
                          win, hooks=hooks)
        return out, lit, asked

    def test_a_face_the_view_shows_is_shown(self):
        out, lit, asked = self.run_point(None)
        self.assertEqual(asked, [("PointBox", ["Face6"])])
        self.assertEqual([a["kind"] for a in out["shown"]], ["face"])
        self.assertEqual(out["missing"], [])

    def test_an_off_screen_face_is_missing_with_why_and_the_callout_says_how(self):
        why = "off-screen: no point of Face6 is inside the 3D view (the view does not frame PointBox)"
        out, lit, _asked = self.run_point(why)
        self.assertEqual(out["shown"], [])
        self.assertEqual(out["missing"][0]["why"], {"reason": "litNotSeen", "unseen": why})
        self.assertIn(("light", ["Face6"]), lit)  # still lit: turned into view, it shows
        say = [x[1] for x in lit if x[0] == "say"][0]
        self.assertIn("Push Fit all (V, F) to see the lit face ①.", say)
        self.assertNotIn("note", out)

    def test_a_hidden_face_says_turn_the_view(self):
        out, lit, _ = self.run_point("hidden: something else is drawn over Face6 at all 3 of its points inside the 3D view")
        say = [x[1] for x in lit if x[0] == "say"][0]
        self.assertIn("Turn the 3D view to see the lit face ①.", say)
        self.assertTrue(out["missing"][0]["why"]["unseen"].startswith("hidden"))

    def test_found_shown_counts_an_unseen_light_as_missing(self):
        f = targets.Found(1, "face")
        f.light = ("obj", ["Face6"])
        self.assertTrue(f.shown())
        f.unseen = "off-screen"
        self.assertFalse(f.shown())


class LightSeenInFreeCAD(unittest.TestCase):
    """Window.light_seen on stand-ins of FreeCADGui and a shape, through
    Agent Link's own annotate.candidates."""

    def setUp(self):
        try:
            from agentlink import annotate  # noqa: F401
        except ImportError:
            self.skipTest("needs an Agent Link checkout ($AGENTLINK_SRC)")
        self.mods = {k: sys.modules.get(k) for k in ("FreeCADGui",)}

    def tearDown(self):
        for k, v in self.mods.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def world(self, view, active="PointDoc"):
        vec = types.SimpleNamespace
        face = types.SimpleNamespace(
            CenterOfMass=vec(x=0.5, y=0.5, z=1.0),
            tessellate=lambda tol: ([vec(x=0, y=0, z=1), vec(x=1, y=0, z=1), vec(x=0, y=1, z=1)], [(0, 1, 2)]))
        doc = types.SimpleNamespace(Name="PointDoc", Label="PointDoc")
        box = types.SimpleNamespace(Name="PointBox", Label="PointBox", Document=doc, InList=[],
                                    Shape=types.SimpleNamespace(getElement=lambda s: face))
        gd = types.SimpleNamespace(activeView=lambda: view)
        act = types.SimpleNamespace(Document=types.SimpleNamespace(Name=active, Label=active))
        sys.modules["FreeCADGui"] = types.SimpleNamespace(ActiveDocument=act, getDocument=lambda n: gd)
        return window.Window(hooks=object()), box

    def test_off_screen_hidden_seen_and_another_document(self):
        class V(View):
            def getPointOnScreen(self, p):
                return self.at(p)

        off = V(lambda p: (-10, -10))
        win, box = self.world(off)
        self.assertTrue(win.light_seen(box, ["Face6"]).startswith("off-screen"))
        seen = V(lambda p: (50, 50), {(50, 50): {"Object": "PointBox", "Component": "Face6"}})
        win, box = self.world(seen)
        self.assertIsNone(win.light_seen(box, ["Face6"]))
        covered = V(lambda p: (50, 50), {(50, 50): {"Object": "TexturePreview", "Component": "Face1"}})
        win, box = self.world(covered)
        self.assertTrue(win.light_seen(box, ["Face6"]).startswith("hidden"))
        win, box = self.world(seen, active="OtherDoc")
        self.assertEqual(win.light_seen(box, ["Face6"]),
                         "the 3D view in front shows OtherDoc, not PointDoc: the light is drawn there, not on PointBox")


if __name__ == "__main__":
    unittest.main()
