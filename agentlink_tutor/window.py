# SPDX-License-Identifier: LGPL-2.1-or-later
"""The FreeCAD window as targets.py reads it: Agent Link's finders
(agentlink.targets, the overlay's visible()) and FreeCAD's own widgets.
Loaded only through agentlink_families, inside the FreeCAD window.

Read only: nothing here switches a workbench, opens a menu, unfolds a tree
branch, scrolls, selects, clicks or takes focus.
"""

import re

TASKVIEW = "Gui::TaskView::TaskView"
TREE = "Gui::TreeWidget"
VIEW3D = "View3DInventor"


def _qt():
    from PySide import QtCore, QtGui

    QtW = getattr(__import__("PySide", fromlist=["QtWidgets"]), "QtWidgets", QtGui)
    return QtCore, QtGui, QtW


def _cls(w):
    try:
        return w.metaObject().className()
    except Exception:
        return type(w).__name__


def _label_text(t):
    from agentlink.targets import norm

    return norm(str(t or "").rstrip(":："))


MODEL_TAB = "the Model tab is not in front: open it (its tab is ringed)"
# Panels FreeCAD may put inside another dock (1.1's Combo View holds the
# Property view in its Model tab), by the class of the panel's widget.
PANELS = {
    "property view": ("Gui::PropertyView", "Gui::PropertyEditor::PropertyEditor"),
    "tree view": (TREE,),
    "model": (TREE,),
    "tasks": (TASKVIEW,),
    "selection view": ("Gui::DockWnd::SelectionView",),
    "report view": ("Gui::DockWnd::ReportOutput",),
    "python console": ("Gui::PythonConsole",),
}


class Window:
    def __init__(self, session=None, gui=None, hooks=None, doc=None):
        self.s = session
        self._gui = gui
        self._hooks = hooks
        self._doc = doc  # the lesson's document, when a lesson asks

    # ---- FreeCAD -------------------------------------------------------------
    def gui(self):
        if self._gui is None:
            import FreeCADGui

            self._gui = FreeCADGui
        return self._gui

    def mw(self):
        return self.gui().getMainWindow()

    def hooks(self):
        if self._hooks is None:
            from agentlink import hooks

            self._hooks = hooks
        return self._hooks

    def overlay(self):
        return self.hooks().service("overlay")

    def visible(self, spec):
        ov = self.overlay()
        w = spec.get("widget") if isinstance(spec, dict) else spec
        if ov is None:
            return "not drawable (no overlay)"
        return ov.visible(w)

    def doc(self):
        """The lesson's document when given, else the session's, else the
        one in front: objects are found there by name, never by label
        across documents."""
        d = self._doc() if callable(self._doc) else None
        if d is None:
            d = getattr(self.s, "doc", None) if self.s is not None else None
        if d is None:
            import FreeCAD

            d = FreeCAD.ActiveDocument
        return d

    def obj(self, ref):
        d = self.doc()
        if d is None or not isinstance(ref, str):
            return None
        return d.getObject(ref) or next((o for o in d.Objects if o.Label == ref), None)

    # ---- workbenches and commands ---------------------------------------------
    def active_workbench(self):
        try:
            wb = self.gui().activeWorkbench()
            return wb.name() if wb else None
        except Exception:
            return None

    def loaded_benches(self):
        try:
            return list(self.gui().listWorkbenches())
        except Exception:
            return []

    def bench_title(self, wb):
        try:
            return self.gui().listWorkbenches()[wb].MenuText
        except Exception:
            return wb

    def workbench_of(self, cmd):
        from agentlink import targets

        return targets.workbench_of(cmd)

    def command_exists(self, cmd):
        try:
            return cmd in self.gui().listCommands()
        except Exception:
            return True

    def command_info(self, cmd):
        try:
            info = self.gui().Command.get(cmd).getInfo()
        except Exception:
            return {}
        keys = info.get("shortcutText") or info.get("shortcut") or ""
        from . import words

        return {"menuText": words.clean_menu_text(info.get("menuText")) or words.command_words(cmd), "shortcut": str(keys) or None}

    def command_buttons(self, cmd):
        from agentlink import targets

        ov = self.overlay()
        out = []
        for w in targets.buttons(cmd, self.mw()):
            out.append((w, ov.visible(w) if ov is not None else "not drawable"))
        return out

    def command_groups(self, cmd):
        """[(button, why hidden or None, menu, action)]: toolbar buttons
        whose dropdown holds cmd (Agent Link's targets.group_buttons)."""
        from agentlink import targets

        ov = self.overlay()
        got = list(targets.group_buttons(cmd, self.mw())) if hasattr(targets, "group_buttons") else []
        if not got:
            got = self._groups_by_text(cmd)
        return [(b, ov.visible(b) if ov is not None else "not drawable", m, a) for b, m, a in got]

    def _groups_by_text(self, cmd):
        """[(button, menu, action)]: toolbar buttons whose dropdown holds an
        item with cmd's menu text, for a dropdown whose items carry neither
        the command's objectName nor its CommandName (so Agent Link's
        group_buttons misses them). The command's own buttons are left out."""
        from agentlink.targets import norm

        _QtCore, _QtGui, QtW = _qt()
        want = norm((self.command_info(cmd) or {}).get("menuText"))
        if not want:
            return []
        own = {id(w) for w, _h in self.command_buttons(cmd)}
        out = []
        for b in self.mw().findChildren(QtW.QToolButton):
            try:
                if id(b) in own:
                    continue
                d = b.defaultAction()
                menus = [m for m in (b.menu(), d.menu() if d is not None else None) if m is not None]
                for m in dict.fromkeys(menus):
                    a = next((x for x in m.actions() if not x.isSeparator() and norm(x.text()) == want), None)
                    if a is not None:
                        out.append((b, m, a))
                        break
            except RuntimeError:
                continue
        return out

    def dropdown_spec(self, button):
        """The ring for a dropdown button: its ▾ arrow when the button has
        one beside it (a menu-button popup), else the whole button."""
        _QtCore, _QtGui, QtW = _qt()
        return dropdown_spec(button, QtW)

    def overflow(self, w):
        """The » button of the toolbar w sits in, as a ring spec, when that
        toolbar shows but w does not (the toolbar is too short and w is in
        its overflow); else None."""
        _QtCore, _QtGui, QtW = _qt()
        return overflow_of(w, QtW)

    # ---- menus -------------------------------------------------------------------
    def menu_titles(self):
        try:
            return [a.text().replace("&", "") for a in self.mw().menuBar().actions()]
        except Exception:
            return []

    def menu_path_of(self, cmd):
        """The titles from the menubar down to cmd's item, as this window
        shows them (translated, this release's own submenus), or None."""
        try:
            return path_to(self.mw().menuBar().actions(), cmd)
        except Exception:  # noqa: BLE001
            return None

    def menu_info(self, titles):
        from agentlink import targets

        mw = self.mw()
        found = targets.menu_path(titles, mw)
        if found.get("missing") is not None:
            return {"missing": found["missing"]}
        last = found["chain"][-1][1] if found["chain"] else None
        cmd = last.objectName() if last is not None else None
        return {"native": targets.native_menubar(mw), "cmd": cmd or None}

    # ---- the workbench selector --------------------------------------------------
    def workbench_selector(self, wb):
        _QtCore, _QtGui, QtW = _qt()
        mw = self.mw()
        title = self.bench_title(wb)
        for bar in mw.findChildren(QtW.QTabBar):
            par = bar.parentWidget()
            if "Workbench" not in _cls(par) and "Workbench" not in _cls(bar):
                continue
            if not bar.isVisible():
                continue
            for i in range(bar.count()):
                if title in (bar.tabText(i), bar.tabToolTip(i)) or wb == str(bar.tabData(i) or ""):
                    return {"widget": bar, "rect": (lambda b=bar, k=i: _r(b.tabRect(k)))}
            return {"widget": par or bar}
        for box in mw.findChildren(QtW.QComboBox):
            if "Workbench" in _cls(box) and box.isVisible():
                return {"widget": box}
        return None

    # ---- task dialogs ------------------------------------------------------------
    def task_open(self):
        try:
            return self.gui().Control.activeDialog()
        except Exception:
            return False

    def _taskview(self):
        _QtCore, _QtGui, QtW = _qt()
        views = [w for w in self.mw().findChildren(QtW.QWidget) if _cls(w) == TASKVIEW]
        seen = [v for v in views if v.isVisible()]
        return (seen or views or [None])[0]

    def task_widget(self, name=None, label=None, button=None):
        _QtCore, _QtGui, QtW = _qt()
        tv = self._taskview()
        if tv is None:
            return None, "the Tasks panel is not in this window"
        w, via = None, None
        if name:
            w = tv.findChild(QtW.QWidget, name)
            via = "by its name" if w is not None else None
        if w is None and label:
            w = self._field_for(tv, label)
            via = "by its label" if w is not None else None
        if w is None and button:
            w = self._button(tv, button)
        if w is None:
            what = name or label or button
            return None, f"no {what!r} in the open task dialog"
        if not self.front(tv) or not w.isVisible():
            head = self._tab_header(tv)
            if head is not None:
                return head, "the Tasks tab is not in front: its tab is ringed"
        return {"widget": w}, (None if via in (None, "by its name") else via)

    def _field_for(self, tv, label):
        _QtCore, _QtGui, QtW = _qt()
        want = _label_text(label)
        for lab in tv.findChildren(QtW.QLabel):
            if _label_text(lab.text()) != want:
                continue
            buddy = lab.buddy()
            if buddy is not None:
                return buddy
            lay = lab.parentWidget().layout() if lab.parentWidget() is not None else None
            got = _beside(lay, lab, QtW)
            return got or lab
        # A check box or button carries its own text.
        for b in tv.findChildren(QtW.QAbstractButton):
            if _label_text(b.text()) == want:
                return b
        return None

    def _button(self, tv, which):
        _QtCore, _QtGui, QtW = _qt()
        B = QtW.QDialogButtonBox
        std = getattr(B, {"ok": "Ok"}.get(which, which.capitalize()), None)
        if std is None:
            std = getattr(getattr(B, "StandardButton", B), {"ok": "Ok"}.get(which, which.capitalize()), None)
        for box in tv.findChildren(B):
            b = box.button(std) if std is not None else None
            if b is not None:
                return b
        return None

    def _tab_header(self, w, title=False):
        """The tab that brings w to the front, as a ring spec, or None: the
        tab of the QTabWidget w sits in that is not in front, else the tab
        of the dock w is in when that dock is tabbed behind another.
        title: (spec, the tab's text)."""
        _QtCore, _QtGui, QtW = _qt()
        got = tab_of(w, QtW, self.mw())
        if got is None:
            return None
        bar, i = got
        spec = {"widget": bar, "rect": (lambda b=bar, k=i: _r(b.tabRect(k)))}
        if title:
            try:
                return spec, str(bar.tabText(i)).replace("&", "")
            except RuntimeError:
                return spec, "other"
        return spec

    def front(self, w):
        """Whether w shows and is in front: visible, and its dock not
        tabbed behind another dock of the main window (behind)."""
        if not _shown(w):
            return False
        try:
            QtW = _qt()[2]
        except Exception:  # noqa: BLE001  (no Qt: a stand-in window)
            return True
        return not behind(w, QtW, self.mw())

    # ---- the model tree ------------------------------------------------------------
    def trees(self):
        """The window's Model trees, found afresh each time (FreeCAD deletes
        and rebuilds them: a wrapper kept from before is dead): the Combo
        View's and any Tree view dock, floating ones too, the shown one
        first; dead ones left out."""
        _QtCore, _QtGui, QtW = _qt()
        found = list(self.mw().findChildren(QtW.QTreeWidget))
        try:  # a dock torn off as its own window
            for top in QtW.QApplication.topLevelWidgets():
                if top is not self.mw():
                    found += list(top.findChildren(QtW.QTreeWidget))
        except Exception:  # noqa: BLE001  (no application: a stand-in)
            pass
        out, seen = [], set()
        for t in found:
            try:
                if alive(t) and _is_tree(t) and id(t) not in seen:
                    seen.add(id(t))
                    out.append((0 if t.isVisible() else 1, len(out), t))
            except RuntimeError:
                continue
        return [t for _v, _i, t in sorted(out, key=lambda x: x[:2])]

    def pump(self):
        """Let Qt run what waits (FreeCAD fills an unfolded row's children
        in, and lays the rows out, from the event loop)."""
        try:
            QtCore = _qt()[0]
            QtCore.QCoreApplication.processEvents()
        except Exception:  # noqa: BLE001
            pass

    def model_tree(self, obj=None):
        """The Model tree a step's row is looked for in first, and the one
        demo brings to the front: a tree holding the object's document row
        (the Combo View's, inside its Model tab, before a Tree view dock),
        else the first tree inside a tab, else the first tree; None when
        the window has none."""
        trees = self.trees()
        if not trees:
            return None
        key = _doc_key(getattr(obj, "Document", None)) if obj is not None else None
        mine = [t for t in trees if key and _safe(lambda t=t: _doc_item(t, key))] or trees
        tabbed = [t for t in mine if _safe(lambda t=t: tab_of_any(t, self.mw()))]
        shown = [t for t in mine if self.front(t)]
        return (shown or tabbed or mine)[0]

    def tree_row(self, obj):
        label = obj.Label
        d = getattr(obj, "Document", None)
        doc = getattr(d, "Label", None)
        key = _doc_key(d)
        trees = self.trees()
        if not trees:
            return None, "no Model tree in this window"
        rows = {id(t): _safe(lambda t=t: _doc_item(t, key)) for t in trees}
        # The trees that hold the document's row come first; any other
        # tree is still searched (a row found by label under no document).
        mine = [t for t in trees if rows[id(t)] is not None]
        order = mine + [t for t in trees if t not in mine]
        if not any(self.front(t) for t in (mine or trees)):
            # The Combo View shows its Tasks or Agent Link tab (the Tutor
            # lives in Agent Link's; FreeCAD flips to Tasks on a workbench
            # switch): the Model tab's header is ringed first, before any
            # row is looked for in a tree that is not laid out.
            for t in mine or trees:
                head = _safe(lambda t=t: self._tab_header(t))
                if head is not None:
                    return head, MODEL_TAB
        tree = item = None
        for t in order:
            try:
                item = _find_obj(t, obj, key)
            except RuntimeError:  # deleted while read
                item = None
            if item is not None:
                tree = t
                break
        if item is None:
            # Not filled in yet (FreeCAD adds a folded branch's rows when it
            # is first unfolded): down from the document's row along the
            # rows that hold the object, the deepest one found; a folded
            # one is ringed. Unfolded without it: the object has no row.
            seen = []
            for t in order:
                try:
                    row = rows[id(t)]
                    for nxt in list(reversed(ancestors(obj))) + [obj]:
                        if row is None or not row.isExpanded():
                            break
                        got = _child_row(row, nxt)
                        if got is None:
                            seen.append(row)
                            row = None
                            break
                        row = got
                except RuntimeError:
                    row = None
                if row is not None and not row.isExpanded():
                    tree, item = t, row
                    break
            if item is None:
                why = f"{label} is not in the Model tree" + (f" under {doc}" if doc else "")
                if seen:
                    try:
                        kids = [str(seen[0].child(j).text(0)) for j in range(min(seen[0].childCount(), 8))]
                        why += f" ({seen[0].text(0)} holds: {', '.join(kids) or 'nothing'})"
                    except (RuntimeError, AttributeError):
                        pass
                why += "; searched: " + "; ".join(self._tree_said(t, rows[id(t)], doc) for t in trees)
                return None, why
        note = None
        # A folded branch is never unfolded: its nearest shown parent's row is ringed.
        top, p = item, item.parent()
        while p is not None:
            if not p.isExpanded():
                top = p
            p = p.parent()
        if top is not item or not any(_same(item.text(0), n) for n in _names(obj)):
            note = f"inside {top.text(0)}, which is folded: its row is ringed"
        row_label = top.text(0)
        if not self.front(tree):
            head = self._tab_header(tree)
            if head is not None:
                return head, MODEL_TAB
        box = {"tree": tree}
        top = item = p = None  # no row is held past here

        def rect():
            # The row again whenever its tree or item has been rebuilt.
            # FreeCAD rebuilds a document's rows after a recompute or when an
            # edit ends. A row kept from before is then a dead wrapper, and
            # while it is held Qt's binding can hand the same dead wrapper
            # back for the new row at its address: using it raised
            # RuntimeError, which the ring read as "scrolled out of view"
            # (bike-stem-1 steps 13-14). So no row is kept: it is looked up
            # by its label each time, in the tree it was in first.
            first = box["tree"]
            order = ([first] if alive(first) else []) + [x for x in self.trees() if x is not first]
            for _again in (0, 1):
                for t in order:
                    try:
                        it = _find_item(t, row_label, key)
                        if it is None:
                            continue
                        r = _r(t.visualItemRect(it))
                    except RuntimeError:
                        continue
                    finally:
                        it = None
                    box["tree"] = t
                    return r
                import gc

                gc.collect()  # dead wrappers let go, then once more
            return None

        return {"widget": tree, "viewport": tree.viewport(), "rect": rect}, note

    def _tree_said(self, t, doc_row, doc):
        """One searched tree in a not-found message: where it is (its dock,
        its tab), whether it shows, whether it holds the document's row
        (and else the rows it does hold)."""
        where = _safe(lambda: _tree_place(t)) or "a Model tree"
        bits = [where, "shown" if self.front(t) else "behind another tab" if _shown(t) else "hidden"]
        if doc:
            if doc_row is not None:
                bits.append(f"{doc} row {doc_row.text(0)!r}")
            else:
                tops = _safe(lambda: _top_texts(t)) or []
                bits.append(f"no {doc} row (rows: {', '.join(tops) or 'none'})")
        return ", ".join(bits)

    # ---- docks and views ---------------------------------------------------------
    def dock(self, title):
        """A dock by its title; else the panel of that name inside another
        dock (FreeCAD 1.1's Property view sits in the Combo View's Model
        tab): the panel when it shows, else (the ring of the tab that
        brings it to the front, "inside the Model tab, …")."""
        from agentlink.targets import norm

        _QtCore, _QtGui, QtW = _qt()
        want = norm(title)
        docks = [d for d in self.mw().findChildren(QtW.QDockWidget) if norm(d.windowTitle()) == want or norm(d.objectName()) == want]
        shown = [d for d in docks if self.front(d)]
        if shown:
            return {"widget": shown[0]}
        for d in docks:   # tabbed behind another dock: its tab is ringed
            if _shown(d):
                head = self._tab_header(d, title=True)
                if head is not None:
                    spec, tab = head
                    return spec, f"the {tab} tab is not in front: its tab is ringed"
        panels = self.panels(title)
        for p in panels:
            if self.front(p):
                return {"widget": p}
        for p in panels:
            head = self._tab_header(p, title=True)
            if head is not None:
                spec, tab = head
                return spec, f"inside the {tab} tab, which is not in front: its tab is ringed"
        if docks:
            return {"widget": docks[0]}
        return None

    def panels(self, title):
        """The widgets that are the panel called title wherever it is put:
        by its class (PANELS) or its objectName (spaces ignored)."""
        from agentlink.targets import norm

        _QtCore, _QtGui, QtW = _qt()
        want = norm(title)
        classes = PANELS.get(want, ())
        bare = want.replace(" ", "")
        out = []
        for w in self.mw().findChildren(QtW.QWidget):
            try:
                if isinstance(w, QtW.QDockWidget):
                    continue
                if _cls(w) in classes or (bare and norm(w.objectName()).replace(" ", "") == bare):
                    out.append(w)
            except RuntimeError:
                continue
        return out

    def view3d(self):
        _QtCore, _QtGui, QtW = _qt()
        area = self.mw().findChild(QtW.QMdiArea)
        if area is None:
            return None
        cur = area.activeSubWindow()
        if cur is not None and VIEW3D in _cls(cur.widget()):
            return {"widget": cur}
        for sub in area.subWindowList():
            if VIEW3D in _cls(sub.widget()):
                return {"widget": sub}
        return None

    # ---- faces and edges -----------------------------------------------------------
    def faces(self, obj, query):
        from agentlink import facepick

        try:
            return [n for n, _f in facepick.pick(obj.Shape, query, "face")], None
        except Exception as e:  # noqa: BLE001  (facepick's ToolError says what is wrong)
            return [], getattr(e, "message", None) or str(e)

    def edges(self, obj, query):
        try:
            return edge_pick(obj.Shape, query), None
        except ValueError as e:
            return [], str(e)

    # ---- add-ons' own kinds -------------------------------------------------------
    def ext(self, spec):
        return self.hooks().read("tutor_target", spec, self)


def path_to(acts, cmd, depth=5):
    """[titles] from these actions down to the one whose objectName is cmd
    (FreeCAD names a command's QAction after it), depth first; None when no
    menu holds it. Plain: anything with text(), objectName(), menu()."""
    for a in acts or []:
        try:
            if a.isSeparator():
                continue
            if a.objectName() == cmd:
                return [a.text().replace("&", "")]
            m = a.menu() if depth > 0 else None
            if m is not None:
                below = path_to(m.actions(), cmd, depth - 1)
                if below:
                    return [a.text().replace("&", "")] + below
        except RuntimeError:  # a menu deleted while read
            continue
    return None


def alive(obj):
    """False for a Qt wrapper whose C++ object is gone."""
    if obj is None:
        return False
    for mod in ("shiboken6", "shiboken2", "PySide6.shiboken6", "PySide2.shiboken2"):
        try:
            sb = __import__(mod, fromlist=["isValid"])
            return bool(sb.isValid(obj))
        except ImportError:
            continue
        except Exception:  # noqa: BLE001  (not a Qt object: a stand-in)
            break
    try:
        if hasattr(obj, "objectName"):
            obj.objectName()
        elif hasattr(obj, "childCount"):
            obj.childCount()  # a tree row: no QObject, so asked something
        return True
    except RuntimeError:
        return False


def _r(q):
    return (q.x(), q.y(), q.width(), q.height())


def _beside(lay, lab, QtW):
    """The field a label stands for in its layout: the field of its form
    row, or the next cell of its grid row."""
    if lay is None:
        return None
    try:
        if isinstance(lay, QtW.QFormLayout):
            row, _role = lay.getWidgetPosition(lab)
            if row >= 0:
                role = getattr(QtW.QFormLayout, "FieldRole", None) or QtW.QFormLayout.ItemRole.FieldRole
                it = lay.itemAt(row, role)
                return it.widget() if it is not None else None
        if isinstance(lay, QtW.QGridLayout):
            i = lay.indexOf(lab)
            if i >= 0:
                r, c, _rs, _cs = lay.getItemPosition(i)
                it = lay.itemAtPosition(r, c + 1)
                return it.widget() if it is not None else None
        if isinstance(lay, QtW.QBoxLayout):
            i = lay.indexOf(lab)
            it = lay.itemAt(i + 1) if i >= 0 else None
            return it.widget() if it is not None else None
    except Exception:
        return None
    return None


def _shown(w):
    try:
        return bool(w.isVisible())
    except RuntimeError:
        return False


def _plain(text):
    return str(text).replace("&", "")


def dock_of(w, QtW):
    """The dock w is in (w itself when it is one), or None."""
    p = w
    while p is not None:
        if isinstance(p, QtW.QDockWidget):
            return p
        p = p.parentWidget()
    return None


def dock_tab(dock, QtW, mw, shown_only=False):
    """(tab bar, index) of the main window's own tab for a dock it tabs
    with others (FreeCAD 1.1: Model, Tasks and an add-on's panel are docks
    of their own, tabbed together by the main window), found by the dock's
    title among the main window's tab bars as FreeCAD's own
    ControlSingleton::findTabBar does; a shown bar before a hidden one
    (Qt keeps tab bars it no longer uses). None when it has no such tab."""
    if dock is None or mw is None:
        return None
    try:
        want = _plain(dock.windowTitle())
    except (RuntimeError, AttributeError):
        return None
    hidden = None
    for bar in mw.findChildren(QtW.QTabBar):
        try:
            if bar.parentWidget() is not mw:
                continue
            for i in range(bar.count()):
                if _plain(bar.tabText(i)) == want:
                    if _shown(bar):
                        return bar, i
                    if hidden is None:
                        hidden = (bar, i)
                    break
        except RuntimeError:
            continue
    return None if shown_only else hidden


def behind(w, QtW, mw):
    """True when the dock holding w is tabbed behind another dock of the
    main window: its tab is in a shown main-window tab bar and is not the
    current one. isVisible() cannot tell: Qt keeps a dock that is tabbed
    behind another visible and parks it outside the window, so its tree
    reads as shown, with rows, while nothing of it is on screen (live,
    FreeCAD 1.1.3: bike-stem-1 steps 13-14, the Model dock behind Tasks)."""
    try:
        dock = dock_of(w, QtW)
        if dock is None or mw is None:
            return False
        if hasattr(dock, "isFloating") and dock.isFloating():
            return False
        got = dock_tab(dock, QtW, mw, shown_only=True)
        if got is None:
            return False
        bar, i = got
        return int(bar.currentIndex()) != i
    except (RuntimeError, AttributeError, TypeError, ValueError):
        return False


def _find_item(tree, label, doc_label=None, strict=False):
    """The tree item labelled label; under the document's own item when
    several documents hold one of that label. strict: only under that
    document's item when the tree has one (another document's row of the
    same label is never taken for it)."""
    hits = []
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop(0)
        if it is None:
            continue
        if _same(it.text(0), label) and it.parent() is not None:
            hits.append(it)
        stack += [it.child(j) for j in range(it.childCount())]

    def in_doc(it):
        p = it.parent()
        while p is not None:
            if _doc_is(p.text(0), doc_label):
                return True
            p = p.parent()
        return False

    mine = [h for h in hits if doc_label is None or in_doc(h)]
    if strict and doc_label is not None and not mine and _has_doc(tree, doc_label):
        return None
    return (mine or hits or [None])[0]


def _same(text, label):
    """A tree row's text is label: spaces at the ends and a changed
    document's trailing * left out."""
    a = str(text or "").strip()
    b = str(label or "").strip()
    return a == b or a.rstrip("*").strip() == b


def _is_tree(w):
    """A FreeCAD Model tree (Gui::TreeWidget, or a class built on it)."""
    c = _cls(w)
    c = str(c)
    return c == TREE or (c.startswith("Gui::") and c.endswith("TreeWidget"))


def _names(obj):
    """What a row of obj may read: its Label, else its Name (unless another
    object of the document carries that Name as its Label)."""
    out = [getattr(obj, "Label", None)]
    name = getattr(obj, "Name", None)
    if name not in out and not _label_taken(obj, name):
        out.append(name)
    return [n for n in out if n]


def _child_row(row, obj):
    """obj's row among row's children (Label first, then Name), or None."""
    kids = [row.child(j) for j in range(row.childCount())]
    for n in _names(obj):
        for k in kids:
            if k is not None and _same(k.text(0), n):
                return k
    return None


def _find_obj(tree, obj, doc_label):
    """obj's row in the tree, under its document's row: by Label, else by
    Name when no object of the document carries that Name as a Label."""
    item = None
    for n in _names(obj):
        item = _find_item(tree, n, doc_label, strict=True)
        if item is not None:
            break
    return item


def _label_taken(obj, text):
    try:
        return any(getattr(o, "Label", None) == text for o in obj.Document.Objects)
    except Exception:  # noqa: BLE001
        return False


def _doc_item(tree, doc_label):
    """The document's own row (the application's child, or a top row), or
    None. doc_label: the document's Label, or (Label, Name); the row may
    read either, with a changed document's * or a " : 1" view number."""
    if not doc_label:
        return None
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if top is None:
            continue
        if _doc_is(top.text(0), doc_label):
            return top
        for j in range(top.childCount()):
            c = top.child(j)
            if c is not None and _doc_is(c.text(0), doc_label):
                return c
    return None


def _doc_key(d):
    """(Label, Name) of a document, what its tree row may read; None."""
    if d is None:
        return None
    key = tuple(dict.fromkeys(str(x) for x in (getattr(d, "Label", None), getattr(d, "Name", None)) if x))
    return key or None


_VIEWNO = re.compile(r"\s*:\s*\d+\s*$")


def _doc_text(text):
    """A document row's text without a changed document's * and a view
    number (" : 1") at its end."""
    a = str(text or "").strip()
    for _ in range(2):
        a = _VIEWNO.sub("", a).rstrip("*").strip()
    return a


def _doc_is(text, doc):
    """The row text is the document's row: doc a Label or (Label, Name)."""
    if not doc:
        return False
    names = [doc] if isinstance(doc, str) else [n for n in doc if n]
    a = _doc_text(text)
    return any(_same(text, n) or a == str(n).strip() for n in names)


def _safe(fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001  (a widget deleted while read; a stand-in)
        return None


def _top_texts(tree, most=6):
    """The texts of a tree's top rows and their children (the documents
    under Application), for a not-found message."""
    out = []
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        if top is None:
            continue
        out.append(str(top.text(0)))
        out += [str(top.child(j).text(0)) for j in range(min(top.childCount(), most))]
    return out[:most]


def _tree_place(t):
    """Where a tree sits, for a message: its dock's title and the tab it is
    in ("Combo View, Model tab"), else its class."""
    dock = tab = None
    chain, p = [t], t.parentWidget()
    while p is not None:
        if tab is None and hasattr(p, "indexOf") and hasattr(p, "tabBar"):
            # The tab's page is a child of the tab widget's own stack.
            i = next((k for k in (p.indexOf(c) for c in chain[-2:]) if k >= 0), -1)
            if i >= 0:
                tab = str(p.tabBar().tabText(i)).replace("&", "")
        if dock is None and str(_cls(p)).endswith("DockWidget") and hasattr(p, "windowTitle"):
            dock = str(p.windowTitle())
        chain.append(p)
        p = p.parentWidget()
    bits = [x for x in (dock, f"{tab} tab" if tab else None) if x]
    return ", ".join(bits) or str(_cls(t))


def tab_of_any(w, mw=None):
    """tab_of with this window's Qt: whether w sits in a tab at all (in
    front or not): (tab widget, index) or None."""
    _QtCore, _QtGui, QtW = _qt()
    page, p = w, w.parentWidget()
    while p is not None:
        if isinstance(p, QtW.QStackedWidget) and isinstance(p.parentWidget(), QtW.QTabWidget):
            i = p.parentWidget().indexOf(page)
            if i >= 0:
                return p.parentWidget(), i
        page, p = p, p.parentWidget()
    return None


def _claimer(o):
    """The object whose tree row holds o's row (a Pad holds its sketch,
    a Body its features): one of o's InList whose view claims o."""
    got = []
    for q in getattr(o, "InList", None) or ():
        kids = _claimed(q)
        if kids and o in kids:
            got.append(q)
    # Claimed by a body and by a feature the body claims: the feature's
    # row is the one that holds it.
    for q in got:
        if not any(q is not r and q in _claimed(r) for r in got):
            continue
        return q
    return got[0] if got else None


def _claimed(q):
    try:
        vo = getattr(q, "ViewObject", None)
        return list(vo.claimChildren() or ()) if vo is not None else []
    except Exception:  # noqa: BLE001
        return []


def ancestors(obj, depth=12):
    """The objects whose tree rows hold obj's row, nearest first: the one
    whose view claims it (a Pad its sketch), else its body or part (the
    parent geo feature group), else the group whose Group holds it."""
    out, seen, o = [], set(), obj
    for _ in range(depth):
        p = None
        try:
            p = o.getParentGeoFeatureGroup() if hasattr(o, "getParentGeoFeatureGroup") else None
        except Exception:  # noqa: BLE001
            p = None
        claim = _claimer(o)
        if claim is not None:
            p = claim
        if p is None:
            for q in getattr(o, "InList", None) or ():
                try:
                    if o in (getattr(q, "Group", None) or ()):
                        p = q
                        break
                except Exception:  # noqa: BLE001
                    continue
        name = getattr(p, "Name", None)
        if p is None or name in seen:
            break
        seen.add(name)
        out.append(p)
        o = p
    return out


def tab_of(w, QtW, mw=None):
    """(tab bar, index) of the tab that brings w to the front, or None:
    the nearest QTabWidget page holding w that is not its current page,
    else the main window's tab of the dock holding w when it is tabbed
    behind another. Plain: works on anything with Qt's methods."""
    page, p = w, w.parentWidget()
    dock = None
    while p is not None:
        if isinstance(p, QtW.QStackedWidget) and isinstance(p.parentWidget(), QtW.QTabWidget):
            tabs = p.parentWidget()
            i = tabs.indexOf(page)
            if i >= 0 and (tabs.currentIndex() != i or not _shown(w)):
                return tabs.tabBar(), i
        if dock is None and isinstance(p, QtW.QDockWidget):
            dock = p
        page, p = p, p.parentWidget()
    if dock is not None and mw is not None:
        return dock_tab(dock, QtW, mw)
    return None


def front_steps(w, QtW, mw=None):
    """What brings w to the front, outermost first, as (kind, widget, arg):
    ("dock", dock, None) a closed or tabbed dock shown, ("tab", tabwidget,
    index) a tab made current, ("scroll", area, w) scrolled to. Read only:
    gui_run.UI.bring does them (demo mode, the lesson's own hands)."""
    out, page, p = [], w, w.parentWidget()
    while p is not None:
        if isinstance(p, QtW.QStackedWidget) and isinstance(p.parentWidget(), QtW.QTabWidget):
            tabs = p.parentWidget()
            i = tabs.indexOf(page)
            if i >= 0 and tabs.currentIndex() != i:
                out.append(("tab", tabs, i))
        elif isinstance(p, QtW.QScrollArea) and p.widget() is not None and p.widget() is page:
            out.append(("scroll", p, w))
        elif isinstance(p, QtW.QDockWidget) and (not _shown(p) or behind(p, QtW, mw)):
            # Hidden, or tabbed behind another dock (which Qt still calls
            # visible): shown and raised, as FreeCAD's own
            # ControlSingleton::showDockWidget does. No focus is taken.
            out.append(("dock", p, None))
        page, p = p, p.parentWidget()
    return list(reversed(out))


def dropdown_spec(button, QtW):
    """{widget, rect?}: a menu-button popup's ▾ arrow (the strip at its
    right, as wide as the style's menu indicator), else the button."""
    try:
        TB = QtW.QToolButton
        popup = getattr(TB, "MenuButtonPopup", None)
        if popup is None:
            popup = TB.ToolButtonPopupMode.MenuButtonPopup
        if button.popupMode() != popup:
            return {"widget": button}
        St = QtW.QStyle
        pm = getattr(St, "PM_MenuButtonIndicator", None)
        if pm is None:
            pm = St.PixelMetric.PM_MenuButtonIndicator
        aw = int(button.style().pixelMetric(pm, None, button) or 12)
    except Exception:  # noqa: BLE001
        return {"widget": button}
    return {"widget": button, "rect": (lambda b=button, a=aw: (max(0, b.width() - a), 0, min(a, b.width()), b.height()))}


def overflow_of(w, QtW):
    """The » (extension) button of w's toolbar as a ring spec, when the
    toolbar shows, w does not and the » does; else None."""
    if _shown(w):
        return None
    p = w.parentWidget() if w is not None else None
    while p is not None and not isinstance(p, QtW.QToolBar):
        p = p.parentWidget()
    if p is None or not _shown(p):
        return None
    for b in p.findChildren(QtW.QToolButton):
        try:
            if b.objectName() == "qt_toolbar_ext_button" and _shown(b):
                return {"widget": b}
        except RuntimeError:
            continue
    return None


def _has_doc(tree, doc_label):
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    depth = 0
    while stack and depth < 3:
        nxt = []
        for it in stack:
            if it is None:
                continue
            if _doc_is(it.text(0), doc_label):
                return True
            nxt += [it.child(j) for j in range(it.childCount())]
        stack, depth = nxt, depth + 1
    return False


def edge_pick(shape, q):
    """Edge names for a query: {edges: ["Edge3"]}, {near: [x, y, z]} (the
    nearest), {longest: true}, {direction: [dx, dy, dz]} (straight edges
    that way). ValueError says what is wrong."""
    edges = list(getattr(shape, "Edges", []) or [])
    if not edges:
        raise ValueError("the object has no edges")
    names = [f"Edge{i + 1}" for i in range(len(edges))]
    if not isinstance(q, dict) or not q:
        raise ValueError("edge: a query such as {near: [x, y, z]}, {longest: true}, {direction: [0, 0, 1]} or {edges: [\"Edge3\"]}")
    if "edges" in q:
        got = [n for n in q["edges"] if n in names]
        if not got:
            raise ValueError(f"no {', '.join(map(str, q['edges']))}: the object has Edge1 to Edge{len(edges)}")
        return got
    pick = list(range(len(edges)))
    if "direction" in q:
        import FreeCAD

        d = FreeCAD.Vector(*q["direction"])
        if d.Length == 0:
            raise ValueError("direction: not [0, 0, 0]")
        d.normalize()
        keep = []
        for i in pick:
            e = edges[i]
            v = e.Vertexes[-1].Point - e.Vertexes[0].Point if len(e.Vertexes) == 2 else None
            if v is not None and v.Length > 0 and abs(abs(v.normalize().dot(d)) - 1) < 1e-3 and "Line" in type(e.Curve).__name__:
                keep.append(i)
        pick = keep
        if not pick:
            raise ValueError("no straight edge runs that way")
    if "near" in q:
        import FreeCAD
        import Part

        p = Part.Vertex(FreeCAD.Vector(*q["near"]))
        pick = [min(pick, key=lambda i: edges[i].distToShape(p)[0])]
    if q.get("longest"):
        pick = [max(pick, key=lambda i: edges[i].Length)]
    return [names[i] for i in pick]
