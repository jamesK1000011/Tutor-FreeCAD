# SPDX-License-Identifier: LGPL-2.1-or-later
# What a live demo of a course found in FreeCAD 1.1.3, with stand-ins for
# the window's widgets: a command inside a toolbar dropdown or behind a
# short toolbar's », a panel inside the Combo View's Model tab, the Tasks
# panel behind another tab, tree rows not filled in under a folded parent,
# a step whose workbench is not the active one (demo switches it; guided
# tells the person), the lesson's document, and the finish.
import copy
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from fakes import Doc  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_agentlink_tools  # noqa: E402

AL = gen_agentlink_tools.source()
if AL and os.path.dirname(AL) not in sys.path:
    sys.path.append(os.path.dirname(AL))

from agentlink_tutor import checks, gui_run, run, targets, window  # noqa: E402
from agentlink_tutor.engine import Engine  # noqa: E402


# ---- a little Qt: just what window.py asks ------------------------------------------

class QWidget:
    def __init__(self, parent=None, name="", cls=None, visible=True):
        self._p, self._name, self._vis = parent, name, visible
        self._cls = cls or type(self).__name__
        self.kids = []
        if parent is not None:
            parent.kids.append(self)

    def parentWidget(self):
        return self._p

    def objectName(self):
        return self._name

    def metaObject(self):
        return types.SimpleNamespace(className=lambda: self._cls)

    def isVisible(self):
        p = self
        while p is not None:
            if not p._vis:
                return False
            p = p._p
        return True

    def findChildren(self, cls):
        out = []
        for k in self.kids:
            if isinstance(k, cls):
                out.append(k)
            out += k.findChildren(cls)
        return out

    def width(self):
        return 40

    def height(self):
        return 24


class QStackedWidget(QWidget):
    pass


class QTabBar(QWidget):
    def __init__(self, parent=None, texts=()):
        super().__init__(parent)
        self.texts = list(texts)

    def count(self):
        return len(self.texts)

    def tabText(self, i):
        return self.texts[i]

    def tabRect(self, i):
        return types.SimpleNamespace(x=lambda: 60 * i, y=lambda: 0, width=lambda: 60, height=lambda: 20)


class QTabWidget(QWidget):
    """Pages in a stacked widget; only the current page shows."""

    def __init__(self, parent=None, titles=()):
        super().__init__(parent)
        self.stack = QStackedWidget(self)
        self.bar = QTabBar(self, titles)
        self.pages = []
        self.current = 0

    def page(self, title):
        p = QWidget(self.stack)
        self.pages.append(p)
        p._vis = len(self.pages) - 1 == self.current
        return p

    def indexOf(self, w):
        return self.pages.index(w) if w in self.pages else -1

    def currentIndex(self):
        return self.current

    def setCurrentIndex(self, i):
        self.current = i
        for k, p in enumerate(self.pages):
            p._vis = k == i

    def tabBar(self):
        return self.bar


class QDockWidget(QWidget):
    def __init__(self, parent=None, title=""):
        super().__init__(parent)
        self.title = title

    def windowTitle(self):
        return self.title


class QScrollArea(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.inner = QWidget(self)
        self.scrolled_to = None

    def widget(self):
        return self.inner

    def ensureWidgetVisible(self, w):
        self.scrolled_to = w


class QToolBar(QWidget):
    pass


class QMenu:
    def __init__(self, acts):
        self.acts = acts

    def actions(self):
        return self.acts


class QAction:
    def __init__(self, text):
        self.t = text

    def text(self):
        return self.t

    def isSeparator(self):
        return False

    def objectName(self):
        return ""


class QToolButton(QWidget):
    MenuButtonPopup = 1
    InstantPopup = 2

    def __init__(self, parent=None, name="", menu=None, mode=1, visible=True):
        super().__init__(parent, name=name, visible=visible)
        self._menu, self._mode = menu, mode

    def menu(self):
        return self._menu

    def defaultAction(self):
        return None

    def popupMode(self):
        return self._mode

    def style(self):
        return types.SimpleNamespace(pixelMetric=lambda *a: 13)


class QStyle:
    PM_MenuButtonIndicator = 7


QtW = types.SimpleNamespace(QWidget=QWidget, QStackedWidget=QStackedWidget, QTabWidget=QTabWidget, QTabBar=QTabBar,
                            QDockWidget=QDockWidget, QScrollArea=QScrollArea, QToolBar=QToolBar, QToolButton=QToolButton,
                            QStyle=QStyle, QTreeWidget=object)


class QtCase(unittest.TestCase):
    def setUp(self):
        self.was = window._qt
        window._qt = lambda: (None, None, QtW)
        self.mw = QWidget(name="MainWindow")

    def tearDown(self):
        window._qt = self.was

    def win(self, **kw):
        ov = types.SimpleNamespace(visible=lambda w: None if w.isVisible() else "hidden")
        hooks = types.SimpleNamespace(service=lambda n: ov if n == "overlay" else None)
        w = window.Window(gui=types.SimpleNamespace(getMainWindow=lambda: self.mw), hooks=hooks)
        for k, v in kw.items():
            setattr(w, k, v)
        return w


# ---- T1: dropdowns and short toolbars --------------------------------------------------

class Dropdown(QtCase):
    def test_dropdown_member_found_by_its_menu_text_and_its_arrow_ringed(self):
        bar = QToolBar(self.mw)
        menu = QMenu([QAction("Constrain Block"), QAction("Constrain &Symmetric")])
        btn = QToolButton(bar, menu=menu)
        w = self.win(command_info=lambda cmd: {"menuText": "Constrain Symmetric"}, command_buttons=lambda cmd: [])
        got = w._groups_by_text("Sketcher_ConstrainSymmetric")
        self.assertEqual([(b, a.text()) for b, _m, a in got], [(btn, "Constrain &Symmetric")])
        spec = w.dropdown_spec(btn)
        self.assertIs(spec["widget"], btn)
        self.assertEqual(spec["rect"](), (27, 0, 13, 24))  # the ▾ strip at the right
        self.assertEqual(window.dropdown_spec(QToolButton(bar, mode=2), QtW).keys(), {"widget"})  # the whole button opens it

    def test_resolver_rings_the_arrow_then_the_item(self):
        class Win:
            def command_exists(self, c):
                return True

            def command_info(self, c):
                return {"menuText": "Constrain symmetric"}

            def command_buttons(self, c):
                return []

            def command_groups(self, c):
                return [("grp-btn", None, "grp-menu", "sym-act")]

            def dropdown_spec(self, b):
                return {"widget": b, "rect": (27, 0, 13, 24)}

        f = targets.resolve({"cmd": "Sketcher_ConstrainSymmetric"}, 1, Win())
        self.assertEqual(f.marks, [{"widget": "grp-btn", "rect": (27, 0, 13, 24)}])
        self.assertEqual(f.dropdown, ("grp-menu", "sym-act"))
        self.assertEqual(f.text, "Open the ▾ menu of the ringed button ①. Select Constrain symmetric.")

    def test_short_toolbar_rings_its_overflow_button(self):
        bar = QToolBar(self.mw)
        hidden = QToolButton(bar, visible=False)
        ext = QToolButton(bar, name="qt_toolbar_ext_button")
        self.assertEqual(window.overflow_of(hidden, QtW), {"widget": ext})
        self.assertIsNone(window.overflow_of(ext, QtW))  # it shows: no overflow
        bar._vis = False
        self.assertIsNone(window.overflow_of(hidden, QtW))  # the toolbar itself is hidden

        class Win:
            active = "SketcherWorkbench"

            def command_exists(self, c):
                return True

            def command_info(self, c):
                return {"menuText": "Constrain symmetric"}

            def command_buttons(self, c):
                return [("sym-btn", "hidden")]

            def command_groups(self, c):
                return []

            def overflow(self, w):
                return {"widget": "ext"} if w == "sym-btn" else None

        f = targets.resolve({"cmd": "Sketcher_ConstrainSymmetric"}, 2, Win())
        self.assertEqual((f.marks, f.note), ([{"widget": "ext"}], "behind the toolbar's » button"))
        self.assertEqual(f.text, "Push » at the end of the toolbar ②. Push Constrain symmetric.")


# ---- T2, T5: the Combo View's tabs --------------------------------------------------------

class ComboView(QtCase):
    def combo(self, current=1):
        dock = QDockWidget(self.mw, "Combo View")
        tabs = QTabWidget(dock, ["Model", "Tasks"])
        model, tasks = tabs.page("Model"), tabs.page("Tasks")
        tabs.setCurrentIndex(current)
        prop = QWidget(model, name="PropertyView", cls="Gui::PropertyView")
        scroll = QScrollArea(tasks)
        tv = QWidget(scroll.inner, cls=window.TASKVIEW)
        return tabs, prop, tv, scroll

    def test_property_view_inside_the_model_tab(self):
        tabs, prop, _tv, _s = self.combo(current=1)  # the Tasks tab in front
        got = self.win().dock("Property view")
        spec, note = got
        self.assertIs(spec["widget"], tabs.bar)
        self.assertEqual(spec["rect"](), (0, 0, 60, 20))  # the Model tab
        self.assertEqual(note, "inside the Model tab, which is not in front: its tab is ringed")
        tabs.setCurrentIndex(0)
        self.assertEqual(self.win().dock("Property view"), {"widget": prop})

    def test_resolver_says_open_the_model_tab(self):
        w = types.SimpleNamespace(dock=lambda t: ({"widget": "model-tab"}, "inside the Model tab, which is not in front: its tab is ringed"),
                                  visible=lambda s: None)
        f = targets.resolve({"dock": "Property view"}, 1, w)
        self.assertEqual((f.marks, f.text), ([{"widget": "model-tab"}], "Open the Model tab."))
        w = types.SimpleNamespace(dock=lambda t: None, visible=lambda s: None)
        self.assertEqual(targets.resolve({"dock": "Property view"}, 1, w).why, "no panel Property view")

    def test_front_steps_bring_the_tasks_tab_and_scroll(self):
        tabs, _prop, tv, scroll = self.combo(current=0)  # the Model tab in front
        field = QWidget(tv)
        steps = window.front_steps(field, QtW, self.mw)
        self.assertEqual([(k, a) for k, _x, a in steps], [("tab", 1), ("scroll", field)])
        self.assertEqual(window.tab_of(field, QtW, self.mw), (tabs.bar, 1))
        ui = gui_run.UI()
        ui._mw = lambda: self.mw
        ui._update = lambda: None
        self.assertTrue(ui.bring(field))
        self.assertEqual((tabs.current, scroll.scrolled_to), (1, field))
        self.assertTrue(field.isVisible())

    def test_tabbed_dock_found_by_the_main_windows_tab(self):
        bar = QTabBar(self.mw, ["Report view", "Tasks"])
        dock = QDockWidget(self.mw, "Tasks")
        dock._vis = False
        tv = QWidget(dock, cls=window.TASKVIEW)
        self.assertEqual(window.tab_of(tv, QtW, self.mw), (bar, 1))
        self.assertEqual(window.front_steps(tv, QtW, self.mw), [("dock", dock, None)])


# ---- T3: tree rows not filled in under a folded parent -----------------------------------

class Item:
    def __init__(self, text, *kids, expanded=True):
        self.t, self.kids, self.p, self.exp = text, list(kids), None, expanded
        for k in kids:
            k.p = self

    def text(self, _c):
        return self.t

    def child(self, i):
        return self.kids[i]

    def childCount(self):
        return len(self.kids)

    def parent(self):
        return self.p

    def isExpanded(self):
        return self.exp

    def objectName(self):
        return ""


class Tree:
    def __init__(self, app):
        self.app = app

    def metaObject(self):
        return types.SimpleNamespace(className=lambda: window.TREE)

    def objectName(self):
        return ""

    def isVisible(self):
        return True

    def topLevelItemCount(self):
        return 1

    def topLevelItem(self, i):
        return self.app

    def viewport(self):
        return self

    def visualItemRect(self, it):
        return types.SimpleNamespace(x=lambda: 0, y=lambda: 0, width=lambda: 100, height=lambda: 18)


class TreeRows(unittest.TestCase):
    def setUp(self):
        self.was = window._qt
        window._qt = lambda: (None, None, types.SimpleNamespace(QTreeWidget=object))

    def tearDown(self):
        window._qt = self.was

    def win(self, tree):
        mw = types.SimpleNamespace(findChildren=lambda cls: [tree])
        return window.Window(gui=types.SimpleNamespace(getMainWindow=lambda: mw), hooks=object())

    def objs(self):
        doc = types.SimpleNamespace(Label="BikeStem", Name="BikeStem")
        body = types.SimpleNamespace(Name="Body", Label="Body", Document=doc, InList=[], Group=[])
        sk = types.SimpleNamespace(Name="Sketch", Label="Sketch", Document=doc, InList=[body],
                                   getParentGeoFeatureGroup=lambda: body)
        body.Group.append(sk)
        return doc, body, sk

    def test_folded_body_without_its_rows_rings_the_body(self):
        _doc, body, sk = self.objs()
        body_row = Item("Body", expanded=False)  # folded, its rows not filled in yet
        w = self.win(Tree(Item("Application", Item("BikeStem", body_row))))
        got, note = w.tree_row(sk)
        self.assertIsNotNone(got)
        self.assertEqual(note, "inside Body, which is folded: its row is ringed")
        f = targets.resolve({"tree": "Sketch"}, 1, types.SimpleNamespace(
            obj=lambda r: sk, tree_row=lambda o: (got, note), visible=lambda s: None))
        self.assertEqual(f.text, "Unfold the ringed row in the tree (its arrow).")

    def test_folded_document_row_and_a_changed_documents_star(self):
        _doc, body, _sk = self.objs()
        w = self.win(Tree(Item("Application", Item("BikeStem *", expanded=False))))
        got, note = w.tree_row(body)
        self.assertEqual(note, "inside BikeStem *, which is folded: its row is ringed")
        # Unfolded and still no row: the object has none.
        w = self.win(Tree(Item("Application", Item("BikeStem"))))
        self.assertEqual(w.tree_row(body), (None, "Body is not in the Model tree under BikeStem"))
        w = self.win(Tree(Item("Application", Item("BikeStem*", Item("Body ")))))
        self.assertEqual(w.tree_row(body)[1], None)  # matched by label, ends trimmed

    def test_ancestors(self):
        _doc, body, sk = self.objs()
        self.assertEqual([a.Name for a in window.ancestors(sk)], ["Body"])
        part = types.SimpleNamespace(Name="Part", Group=[body], InList=[])
        body.InList = [part]
        self.assertEqual([a.Name for a in window.ancestors(sk)], ["Body", "Part"])


# ---- T4: the workbench a step needs ---------------------------------------------------------

class Bench(unittest.TestCase):
    def test_demo_activates_the_commands_workbench_through_the_tool(self):
        calls = []
        eng = types.SimpleNamespace(call=lambda t, a: (calls.append((t, a)) or (False, {"active": a["activate"]})))
        win = types.SimpleNamespace(command_buttons=lambda c: [("pad-btn", "hidden")], command_groups=lambda c: [],
                                    workbench_of=lambda c: "PartDesignWorkbench", active_workbench=lambda: "SketcherWorkbench",
                                    loaded_benches=lambda: ["PartDesignWorkbench", "SketcherWorkbench"],
                                    bench_title=lambda b: "Part Design")
        got = gui_run.UI()._bench_for(eng, win, "PartDesign_Pad")
        self.assertEqual(calls, [("workbench", {"activate": "PartDesignWorkbench"})])
        self.assertEqual(got, "workbench Part Design activated")
        # A button that shows, or the bench already active: nothing done.
        win.command_buttons = lambda c: [("pad-btn", None)]
        self.assertIsNone(gui_run.UI()._bench_for(eng, win, "PartDesign_Pad"))
        win.command_buttons = lambda c: []
        win.active_workbench = lambda: "PartDesignWorkbench"
        self.assertIsNone(gui_run.UI()._bench_for(eng, win, "PartDesign_Pad"))
        self.assertEqual(len(calls), 1)


LESSON = {
    "schema": 1, "id": "test.prep.lesson", "version": "1.0.0", "title": "Prep", "summary": "s", "level": "basic", "minutes": 1,
    "requires": {"freecad": ">=1.0", "agentlink_api": ">=1,<2"},
    "setup": {"calls": [{"tool": "doc_new", "args": {"name": "Stem"}}]},
    "steps": [
        {"id": "make", "say": "Push **Pad**.", "targets": [{"cmd": "X_Pad"}], "check": {"exists": "Part::Box"},
         "do": [{"tool": "box", "args": {}}]},
        {"id": "close", "say": "Push **Close**.", "targets": [{"cmd": "X_Close"}], "check": {"exists": "Part::Box"},
         "do": [{"tool": "noop", "args": {}}]},
        {"id": "see", "say": "Done.", "check": {"exists": "Part::Box"}},
    ],
}


class World:
    def __init__(self, label="TutorStem", work=False):
        self.doc = Doc()
        self.doc.Name = self.doc.Label = label
        if work:
            self.doc.add("Other", "Part::Cylinder")
        self.calls = []

    def __call__(self, name, args):
        self.calls.append((name, args))
        if name == "doc_new":
            self.doc = Doc()
            self.doc.Name = self.doc.Label = args["name"]
            return False, {"document": args["name"]}
        if name == "box":
            self.doc.add("Box", "Part::Box")
        return False, {}


class UIStub:
    def __init__(self):
        self.prepared, self.settled = [], 0

    def settle(self, doc=None):
        self.settled += 1

    def frame(self, *a, **k):
        pass

    def open_task(self, e):
        pass

    def close_task(self):
        pass

    def prepare(self, e):
        self.prepared.append(e.step["id"])
        return ["workbench Part Design activated"] if e.step["id"] == "make" else []


class DocumentAndFinish(unittest.TestCase):
    def test_the_open_empty_document_is_used(self):
        w = World()
        e = Engine(copy.deepcopy(LESSON), call=w, doc=lambda: w.doc)
        st = e.start("demo")
        self.assertEqual(w.calls, [])
        self.assertEqual(e.doc_name, "TutorStem")
        self.assertEqual(st["document"], "the lesson works in TutorStem: it was open and empty")

    def test_other_work_gets_a_new_document_with_a_name_not_in_use(self):
        w = World(work=True)
        e = Engine(copy.deepcopy(LESSON), call=w, doc=lambda: w.doc, taken=lambda: {"Stem", "stem_2", "Other"})
        st = e.start("demo")
        self.assertEqual(w.calls, [("doc_new", {"name": "Stem_3"})])
        self.assertEqual(st["document"], "a new document Stem_3: TutorStem holds other work")

    def test_a_pending_recheck_keeps_a_pass(self):
        w = World()
        e = Engine(copy.deepcopy(LESSON), call=w, doc=lambda: w.doc)
        e.start("guided")
        e.do()
        self.assertTrue(e.passed)
        real = checks.evaluate
        checks.evaluate = lambda spec, ctx: checks.pending("close the open panel first")  # cannot be told just now
        try:
            st = e.check()
        finally:
            checks.evaluate = real
        self.assertEqual((e.passed, st["check"]), (True, "pass"))

    def test_demo_prepares_skips_what_is_done_and_ends_with_the_final_check(self):
        w = World()
        ui = UIStub()
        e = Engine(copy.deepcopy(LESSON), call=w, doc=lambda: w.doc)
        c = run.Controller(e, ui=ui, show=lambda ctl: {"resolved": 1, "missing": []} if ctl else None)
        st = c.start("demo")
        self.assertEqual(st["prepared"], ["workbench Part Design activated"])
        st = c.act("next")  # make: done through the tools
        self.assertEqual(st["id"], "close")
        # Its check already holds: passed as it came up, nothing ringed or prepared.
        self.assertEqual((st["check"], st["targets"]["note"]), ("pass", "already done: next goes on"))
        self.assertEqual(c.shown(), ([], None))
        self.assertEqual(ui.prepared, ["make"])
        self.assertNotIn(("noop", {}), w.calls)
        c.act("next")
        st = c.act("next")
        self.assertEqual(st["step"], "done")
        self.assertEqual((st["finished"], st["final"]), ("lesson complete", {"step": "see", "check": "pass"}))
        self.assertEqual(c.rider("x"), "tutor: lesson complete, final check passed")

    def test_demo_final_check_pending_gets_a_quiet_window_and_one_more_try(self):
        w = World()
        ui = UIStub()
        lesson = copy.deepcopy(LESSON)
        e = Engine(lesson, call=w, doc=lambda: w.doc)
        c = run.Controller(e, ui=ui)
        c.start("demo")
        c.act("next")
        tries = []
        real = checks.evaluate

        def ev(spec, ctx):
            # close's Next, "see" coming up and its Next: a panel is open.
            tries.append(1)
            return checks.pending("close the open panel first") if len(tries) <= 3 else real(spec, ctx)

        checks.evaluate = ev
        try:
            c.act("next")  # close: done; "see" comes up, its check not told
            n = ui.settled
            st = c.act("next")
        finally:
            checks.evaluate = real
        self.assertEqual(ui.settled, n + 1)
        self.assertEqual(st["final"], {"step": "see", "check": "pass"})


if __name__ == "__main__":
    unittest.main()
