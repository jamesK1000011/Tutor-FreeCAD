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
        self.assertEqual(w.tree_row(body), (None, "Body is not in the Model tree under BikeStem (BikeStem holds: nothing);"
                                                  " searched: a Model tree, shown, BikeStem row 'BikeStem'"))
        w = self.win(Tree(Item("Application", Item("BikeStem*", Item("Body ")))))
        self.assertEqual(w.tree_row(body)[1], None)  # matched by label, ends trimmed

    def test_ancestors(self):
        _doc, body, sk = self.objs()
        self.assertEqual([a.Name for a in window.ancestors(sk)], ["Body"])
        part = types.SimpleNamespace(Name="Part", Group=[body], InList=[])
        body.InList = [part]
        self.assertEqual([a.Name for a in window.ancestors(sk)], ["Body", "Part"])


# ---- the live check of bike-stem-1 steps 13 and 14: a row filled in lazily -----------------

class LazyItem(Item):
    """A row whose children FreeCAD fills in only once it is unfolded, and
    only when Qt next runs its events (pump)."""

    def __init__(self, text, *later, expanded=False, filled=False):
        super().__init__(text, *(later if filled else ()), expanded=expanded)
        self.later = list(later)
        for k in later:
            k.p = self

    def setExpanded(self, on):
        self.exp = on


class LazyTree(Tree):
    def __init__(self, app, pending):
        super().__init__(app)
        self.pending = pending

    def expandItem(self, it):
        if not it.exp:
            it.exp = True
            if isinstance(it, LazyItem) and not it.kids:
                self.pending.append(it)

    def collapseItem(self, it):
        it.exp = False


class LazyRows(unittest.TestCase):
    def setUp(self):
        self.was = window._qt
        window._qt = lambda: (None, None, types.SimpleNamespace(QTreeWidget=object))

    def tearDown(self):
        window._qt = self.was

    def objs(self, pad=False):
        doc = types.SimpleNamespace(Label="TutorStem2", Name="TutorStem2", Objects=[])
        body = types.SimpleNamespace(Name="Body", Label="Body", Document=doc, InList=[], Group=[])
        sk = types.SimpleNamespace(Name="Sketch", Label="Sketch", Document=doc, InList=[body],
                                   getParentGeoFeatureGroup=lambda: body)
        body.Group.append(sk)
        body.ViewObject = types.SimpleNamespace(claimChildren=lambda: list(body.Group))
        doc.Objects += [body, sk]
        if pad:
            p = types.SimpleNamespace(Name="Pad", Label="Pad", Document=doc, InList=[body],
                                      getParentGeoFeatureGroup=lambda: body)
            p.ViewObject = types.SimpleNamespace(claimChildren=lambda: [sk])
            body.Group.append(p)
            sk.InList = [body, p]
            doc.Objects.append(p)
            return doc, body, sk, p
        return doc, body, sk

    def setup_tree(self, body_row, extra_trees=()):
        pending = []
        app = Item("Application", LazyItem("TutorStem2", body_row, LazyItem("Params", filled=True), filled=True, expanded=True))
        tree = LazyTree(app, pending)
        trees = [tree, *extra_trees]
        mw = types.SimpleNamespace(findChildren=lambda cls: list(trees))
        w = window.Window(gui=types.SimpleNamespace(getMainWindow=lambda: mw), hooks=object())

        def pump():
            while pending:
                it = pending.pop(0)
                it.kids = list(it.later)
        w.pump = pump
        return w, tree, pending

    def ui(self, win):
        ui = gui_run.UI()
        ui.bring = lambda w: False
        ui._update = lambda: None
        return ui

    def test_unfolded_and_filled_in_after_qt_runs(self):
        _doc, body, sk = self.objs()
        body_row = LazyItem("Body", LazyItem("Origin", filled=True), LazyItem("Sketch", filled=True))
        w, _t, _p = self.setup_tree(body_row)
        self.assertEqual(w.tree_row(sk)[1], "inside Body, which is folded: its row is ringed")
        fake = types.SimpleNamespace(getDocument=lambda n: None)
        sys.modules["FreeCADGui"] = fake
        try:
            got = self.ui(w)._tree_open(w, sk, window.ancestors)
        finally:
            sys.modules.pop("FreeCADGui", None)
        self.assertEqual(got, "Sketch shown in the tree")
        row, note = w.tree_row(sk)
        self.assertIsNone(note)
        self.assertIsNotNone(row)

    def test_a_row_below_the_trees_edge_is_scrolled_to(self):
        # bike-stem-1 steps 13-14: the Sketch row was unfolded but lay below
        # the tree's bottom edge, and the ring said "scrolled out of view".
        _doc, body, sk = self.objs()
        body_row = LazyItem("Body", LazyItem("Origin", filled=True), LazyItem("Sketch", filled=True), expanded=True)
        body_row.kids = list(body_row.later) if not body_row.kids else body_row.kids
        w, tree, _p = self.setup_tree(body_row)
        w.pump()
        scrolled, where = [], {"y": 400}
        tree.height = lambda: 200
        tree.visualItemRect = lambda it: types.SimpleNamespace(
            x=lambda: 0, y=lambda: where["y"], width=lambda: 100, height=lambda: 18,
            top=lambda: where["y"], bottom=lambda: where["y"] + 18)

        def scroll(it):
            scrolled.append(it.text(0))
            where["y"] = 90
        tree.scrollToItem = scroll
        self.assertFalse(gui_run.row_shows(200, 400, 418))
        self.assertTrue(gui_run.row_shows(200, 90, 108))
        sys.modules["FreeCADGui"] = types.SimpleNamespace(getDocument=lambda n: None)
        try:
            got = self.ui(w)._tree_open(w, sk, window.ancestors)
            again = self.ui(w)._tree_open(w, sk, window.ancestors)
        finally:
            sys.modules.pop("FreeCADGui", None)
        self.assertEqual(scrolled, ["Sketch"])
        self.assertIn("Sketch", got)
        self.assertIsNone(again)  # in view now: nothing more to do

    def test_a_row_unfolded_before_it_was_filled_in_is_unfolded_again(self):
        # The Body row reads unfolded but holds no rows yet: the old lookup
        # said "not in the Model tree" even after preparing.
        _doc, body, sk = self.objs()
        body_row = LazyItem("Body", LazyItem("Origin", filled=True), LazyItem("Sketch", filled=True), expanded=True)
        w, _t, _p = self.setup_tree(body_row)
        got, why = w.tree_row(sk)
        self.assertIsNone(got)
        self.assertEqual(why, "Sketch is not in the Model tree under TutorStem2 (Body holds: nothing);"
                              " searched: a Model tree, shown, TutorStem2 row 'TutorStem2'")
        sys.modules["FreeCADGui"] = types.SimpleNamespace(getDocument=lambda n: None)
        try:
            self.assertEqual(self.ui(w)._tree_open(w, sk, window.ancestors), "Sketch shown in the tree")
        finally:
            sys.modules.pop("FreeCADGui", None)
        self.assertIsNone(w.tree_row(sk)[1])

    def test_a_sketch_under_its_pad(self):
        _doc, body, sk, pad = self.objs(pad=True)
        self.assertEqual([a.Name for a in window.ancestors(sk)], ["Pad", "Body"])
        pad_row = LazyItem("Pad", LazyItem("Sketch", filled=True))
        body_row = LazyItem("Body", LazyItem("Origin", filled=True), pad_row)
        w, _t, _p = self.setup_tree(body_row)
        sys.modules["FreeCADGui"] = types.SimpleNamespace(getDocument=lambda n: None)
        try:
            self.assertEqual(self.ui(w)._tree_open(w, sk, window.ancestors), "Sketch shown in the tree")
        finally:
            sys.modules.pop("FreeCADGui", None)
        self.assertTrue(pad_row.exp)
        self.assertIsNone(w.tree_row(sk)[1])

    def test_folded_pad_rings_the_pad(self):
        _doc, body, sk, pad = self.objs(pad=True)
        body_row = LazyItem("Body", LazyItem("Origin", filled=True), LazyItem("Pad", LazyItem("Sketch", filled=True)),
                            filled=True, expanded=True)
        w, _t, _p = self.setup_tree(body_row)
        self.assertEqual(w.tree_row(sk)[1], "inside Pad, which is folded: its row is ringed")

    def test_the_second_tree_a_tree_view_dock(self):
        _doc, body, sk = self.objs()
        empty = Tree(Item("Application", Item("Other")))
        body_row = LazyItem("Body", LazyItem("Sketch", filled=True), filled=True, expanded=True)
        w, tree, _p = self.setup_tree(body_row)
        trees = [empty, tree]
        w._gui = types.SimpleNamespace(getMainWindow=lambda: types.SimpleNamespace(findChildren=lambda cls: list(trees)))
        got, note = w.tree_row(sk)
        self.assertIsNone(note)
        self.assertIs(got["widget"], tree)

    def test_matched_by_label_then_by_name(self):
        doc, body, sk = self.objs()
        sk.Label = "Base profile"
        body_row = LazyItem("Body", LazyItem("Sketch", filled=True), filled=True, expanded=True)
        w, _t, _p = self.setup_tree(body_row)
        self.assertIsNone(w.tree_row(sk)[1])  # its row reads its Name
        body_row.kids[0].t = "Base profile"
        self.assertIsNone(w.tree_row(sk)[1])
        # Another object carries the Name as its Label: that row is not taken.
        body_row.kids[0].t = "Sketch"
        doc.Objects.append(types.SimpleNamespace(Name="Sketch001", Label="Sketch"))
        self.assertIsNone(w.tree_row(sk)[0])

    def test_trees_seen_once_and_a_subclass_counts(self):
        t = Tree(Item("Application"))
        sub = Tree(Item("Application"))
        sub.metaObject = lambda: types.SimpleNamespace(className=lambda: "Gui::MyTreeWidget")
        mw = types.SimpleNamespace(findChildren=lambda cls: [t, t, sub])
        w = window.Window(gui=types.SimpleNamespace(getMainWindow=lambda: mw), hooks=object())
        self.assertEqual(w.trees(), [t, sub])


# ---- the live check of bike-stem-1 step 13: the Model tree inside a tab not in front ------

class TreeW(QWidget):
    """A Model tree widget in a tab page: rows read as ever, laid out (a
    row's rect) only while it shows; expandItem notes whether it showed."""

    def __init__(self, parent, app, pending):
        super().__init__(parent, cls=window.TREE)
        self.app, self.pending, self.expanded_hidden = app, pending, []

    def topLevelItemCount(self):
        return 1

    def topLevelItem(self, i):
        return self.app

    def viewport(self):
        return self

    def visualItemRect(self, it):
        h = 18 if self.isVisible() else 0
        return types.SimpleNamespace(x=lambda: 0, y=lambda: 0, width=lambda: 100 if h else 0, height=lambda: h)

    def expandItem(self, it):
        if not self.isVisible():
            self.expanded_hidden.append(it.t)
        LazyTree.expandItem(self, it)

    def collapseItem(self, it):
        it.exp = False


class HiddenTab(QtCase):
    def objs(self, doc_label="TutorStem3"):
        doc = types.SimpleNamespace(Label=doc_label, Name="TutorStem3", Objects=[])
        body = types.SimpleNamespace(Name="Body", Label="Body", Document=doc, InList=[], Group=[])
        sk = types.SimpleNamespace(Name="Sketch", Label="Sketch", Document=doc, InList=[body],
                                   getParentGeoFeatureGroup=lambda: body)
        body.Group.append(sk)
        body.ViewObject = types.SimpleNamespace(claimChildren=lambda: list(body.Group))
        doc.Objects += [body, sk]
        return doc, body, sk

    def combo(self, doc_row="TutorStem3", dock_tree=False):
        """Model | Tasks | Agent Link, the Agent Link tab in front (the
        Tutor lives there); a hidden Tree view dock beside, not filled in."""
        dock = QDockWidget(self.mw, "Combo View")
        tabs = QTabWidget(dock, ["Model", "Tasks", "Agent Link"])
        model, _tasks, _al = tabs.page("Model"), tabs.page("Tasks"), tabs.page("Agent Link")
        tabs.setCurrentIndex(2)
        pending = []
        body_row = LazyItem("Body", LazyItem("Origin", filled=True), LazyItem("Sketch", filled=True))
        app = Item("Application", LazyItem(doc_row, body_row, filled=True, expanded=True))
        tree = TreeW(model, app, pending)
        other = None
        if dock_tree:
            tv = QDockWidget(self.mw, "Tree view")
            tv._vis = False
            other = TreeW(tv, Item("Application"), [])
        w = self.win()

        def pump():
            while pending:
                it = pending.pop(0)
                it.kids = list(it.later)
        w.pump = pump
        return w, tabs, tree, other

    def ui(self):
        ui = gui_run.UI()
        ui._mw = lambda: self.mw
        ui._update = lambda: None
        return ui

    def test_guided_rings_the_model_tab_first(self):
        _d, _b, sk = self.objs()
        w, tabs, _tree, _o = self.combo()
        got, note = w.tree_row(sk)
        self.assertEqual(note, window.MODEL_TAB)
        self.assertIs(got["widget"], tabs.bar)
        self.assertEqual(got["rect"](), (0, 0, 60, 20))  # the Model tab, not Tasks or Agent Link
        f = targets.resolve({"tree": "Sketch"}, 1, types.SimpleNamespace(
            obj=lambda r: sk, tree_row=lambda o: (got, note), visible=lambda s: None))
        self.assertEqual(f.text, "Open the Model tab.")

    def test_demo_brings_the_model_tab_before_unfolding(self):
        _d, _b, sk = self.objs()
        w, tabs, tree, other = self.combo(dock_tree=True)
        sys.modules["FreeCADGui"] = types.SimpleNamespace(getDocument=lambda n: None)
        try:
            got = self.ui()._tree_open(w, sk, window.ancestors)
        finally:
            sys.modules.pop("FreeCADGui", None)
        self.assertEqual(got, "Sketch shown in the tree")
        self.assertEqual(tabs.current, 0)
        self.assertEqual(tree.expanded_hidden, [])  # nothing unfolded while hidden
        self.assertFalse(other.isVisible())  # the empty Tree view dock left closed
        row, note = w.tree_row(sk)
        self.assertIsNone(note)
        self.assertEqual(row["rect"](), (0, 0, 100, 18))

    def test_document_row_with_a_star_or_a_view_number_or_its_name(self):
        for text in ("TutorStem3 : 1", "TutorStem3*", "TutorStem3 : 1*", "TutorStem3* : 1"):
            with self.subTest(text=text):
                self.mw = QWidget(name="MainWindow")
                _d, _b, sk = self.objs()
                w, tabs, _t, _o = self.combo(doc_row=text)
                tabs.setCurrentIndex(0)
                self.assertEqual(w.tree_row(sk)[1], "inside Body, which is folded: its row is ringed")
        # The row reads the document's Name, its Label changed.
        self.mw = QWidget(name="MainWindow")
        _d, _b, sk = self.objs(doc_label="Bike stem")
        w, tabs, _t, _o = self.combo(doc_row="TutorStem3")
        tabs.setCurrentIndex(0)
        self.assertEqual(w.tree_row(sk)[1], "inside Body, which is folded: its row is ringed")
        self.assertTrue(window._doc_is("Bike stem : 2", ("Bike stem", "TutorStem3")))
        self.assertFalse(window._doc_is("Bike stem 2", ("Bike stem", "TutorStem3")))

    def test_not_found_says_which_trees_were_searched(self):
        _d, _b, sk = self.objs()
        w, tabs, _tree, _other = self.combo(doc_row="Unnamed", dock_tree=True)
        tabs.setCurrentIndex(0)
        got, why = w.tree_row(sk)
        self.assertIsNone(got)
        self.assertEqual(why, "Sketch is not in the Model tree under TutorStem3; searched: "
                              "Combo View, Model tab, shown, no TutorStem3 row (rows: Application, Unnamed); "
                              "Tree view, hidden, no TutorStem3 row (rows: Application)")


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


# ---- bike-stem-1 steps 13 and 14, live on FreeCAD 1.1.3: the Model dock tabbed behind Tasks ----

class MainTabBar(QTabBar):
    """The main window's own tab bar over docks it tabs together (FreeCAD
    1.1: Model, Tasks and a panel are docks of their own)."""

    def __init__(self, parent, texts, current=0):
        super().__init__(parent, texts)
        self.cur = current

    def currentIndex(self):
        return self.cur


class TabbedDock(QDockWidget):
    """A dock in such a tab group. As Qt does, a dock tabbed behind another
    stays isVisible(): it is parked outside the window. show and raise_
    make its tab the current one."""

    def __init__(self, parent, title, bar):
        super().__init__(parent, title)
        self.bar = bar
        self.calls = []

    def isFloating(self):
        return False

    def show(self):
        self.calls.append("show")

    def raise_(self):
        self.calls.append("raise")
        self.bar.cur = self.bar.texts.index(self.title)


class DockTree(Tree):
    """A Model tree inside a dock: rows as Tree, a parent as a widget."""

    def __init__(self, app, parent):
        super().__init__(app)
        self._p = parent
        self.scrolled = []

    def parentWidget(self):
        return self._p

    def height(self):
        return 200

    def scrollToItem(self, it):
        self.scrolled.append(it.text(0))


class TabbedDocks(unittest.TestCase):
    def setUp(self):
        self.was = window._qt
        self.qtw = types.SimpleNamespace(**{**vars(QtW), "QTreeWidget": object})
        window._qt = lambda: (None, None, self.qtw)
        self.mw = QWidget(name="MainWindow")
        self.bar = MainTabBar(self.mw, ["Model", "Tasks", "Agent Link"], current=1)  # Tasks in front
        self.model = TabbedDock(self.mw, "Model", self.bar)
        self.tasks = TabbedDock(self.mw, "Tasks", self.bar)
        doc = types.SimpleNamespace(Label="TutorStem", Name="TutorStem", Objects=[])
        self.body = types.SimpleNamespace(Name="Body", Label="Body", Document=doc, InList=[], Group=[])
        self.sk = types.SimpleNamespace(Name="Sketch", Label="Sketch", Document=doc, InList=[self.body],
                                        getParentGeoFeatureGroup=lambda: self.body)
        self.body.Group.append(self.sk)
        doc.Objects += [self.body, self.sk]
        app = Item("Application", Item("TutorStem", Item("Body", Item("Origin"), Item("Sketch"))))
        self.tree = DockTree(app, self.model)
        mw = self.mw
        tree = self.tree
        find = mw.findChildren
        mw.findChildren = lambda cls: [tree] if cls is object else find(cls)
        self.win = window.Window(gui=types.SimpleNamespace(getMainWindow=lambda: mw), hooks=object())
        self.win.pump = lambda: None

    def tearDown(self):
        window._qt = self.was

    def test_a_dock_tabbed_behind_is_not_in_front_though_qt_calls_it_visible(self):
        self.assertTrue(self.tree.isVisible() and self.model.isVisible())
        self.assertTrue(window.behind(self.tree, self.qtw, self.mw))
        self.assertFalse(window.behind(self.tasks, self.qtw, self.mw))
        self.assertFalse(self.win.front(self.tree))
        self.assertEqual(window.front_steps(self.tree, self.qtw, self.mw), [("dock", self.model, None)])
        self.assertEqual(window.front_steps(self.tasks, self.qtw, self.mw), [])
        # Guided: the Model tab is ringed, never the row of a tree that is not on screen.
        spec, note = self.win.tree_row(self.sk)
        self.assertIs(spec["widget"], self.bar)
        self.assertEqual(spec["rect"](), (0, 0, 60, 20))
        self.assertEqual(note, window.MODEL_TAB)

    def test_demo_brings_the_model_dock_forward_for_a_row_already_unfolded(self):
        ui = gui_run.UI()
        ui._mw = lambda: self.mw
        ui._update = lambda: None
        sys.modules["FreeCADGui"] = types.SimpleNamespace(getDocument=lambda n: None)
        try:
            got = ui._tree_open(self.win, self.sk, window.ancestors)
            again = ui._tree_open(self.win, self.sk, window.ancestors)
        finally:
            sys.modules.pop("FreeCADGui", None)
        self.assertEqual(got, "Sketch shown in the tree")
        self.assertEqual(self.model.calls, ["show", "raise"])  # once; no focus call exists on the stand-in to make
        self.assertEqual(self.bar.cur, 0)
        self.assertEqual(self.tasks.calls, [])
        self.assertIsNone(again)
        row, note = self.win.tree_row(self.sk)
        self.assertIsNone(note)
        self.assertIs(row["widget"], self.tree)

    def test_a_tab_bar_qt_no_longer_uses_does_not_count(self):
        self.bar._vis = False  # hidden: a bar left from an earlier tab group
        self.assertFalse(window.behind(self.tree, self.qtw, self.mw))
        self.assertTrue(self.win.front(self.tree))


if __name__ == "__main__":
    unittest.main()
