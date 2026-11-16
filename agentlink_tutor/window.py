# SPDX-License-Identifier: LGPL-2.1-or-later
"""The FreeCAD window as targets.py reads it: Agent Link's finders
(agentlink.targets, the overlay's visible()) and FreeCAD's own widgets.
Loaded only through agentlink_families, inside the FreeCAD window.

Read only: nothing here switches a workbench, opens a menu, unfolds a tree
branch, scrolls, selects, clicks or takes focus.
"""

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


class Window:
    def __init__(self, session=None, gui=None, hooks=None):
        self.s = session
        self._gui = gui
        self._hooks = hooks

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
        return {"menuText": str(info.get("menuText") or cmd).replace("&", ""), "shortcut": str(keys) or None}

    def command_buttons(self, cmd):
        from agentlink import targets

        ov = self.overlay()
        out = []
        for w in targets.buttons(cmd, self.mw()):
            out.append((w, ov.visible(w) if ov is not None else "not drawable"))
        return out

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
        if not tv.isVisible() or not w.isVisible():
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

    def _tab_header(self, w):
        """The tab of the QTabWidget w sits in, as a ring spec, or None."""
        _QtCore, _QtGui, QtW = _qt()
        page, p = w, w.parentWidget()
        while p is not None:
            if isinstance(p, QtW.QStackedWidget) and isinstance(p.parentWidget(), QtW.QTabWidget):
                tabs = p.parentWidget()
                i = tabs.indexOf(page)
                if i >= 0:
                    bar = tabs.tabBar()
                    return {"widget": bar, "rect": (lambda b=bar, k=i: _r(b.tabRect(k)))}
            page, p = p, p.parentWidget()
        return None

    # ---- the model tree ------------------------------------------------------------
    def trees(self):
        """The window's Model trees, found afresh each time (FreeCAD deletes
        and rebuilds them: a wrapper kept from before is dead), the shown
        one first; dead ones left out."""
        _QtCore, _QtGui, QtW = _qt()
        out = []
        for t in self.mw().findChildren(QtW.QTreeWidget):
            try:
                if alive(t) and _cls(t) == TREE:
                    out.append((0 if t.isVisible() else 1, len(out), t))
            except RuntimeError:
                continue
        return [t for _v, _i, t in sorted(out, key=lambda x: x[:2])]

    def tree_row(self, obj):
        label = obj.Label
        doc = getattr(getattr(obj, "Document", None), "Label", None)
        trees = self.trees()
        if not trees:
            return None, "no Model tree in this window"
        tree = item = None
        for t in trees:
            try:
                item = _find_item(t, label, doc)
            except RuntimeError:  # deleted while read
                item = None
            if item is not None:
                tree = t
                break
        if item is None:
            return None, f"{label} is not in the Model tree"
        note = None
        # A folded branch is never unfolded: its nearest shown parent's row is ringed.
        top, p = item, item.parent()
        while p is not None:
            if not p.isExpanded():
                top = p
            p = p.parent()
        if top is not item:
            note = f"inside {top.text(0)}, which is folded: its row is ringed"
        row_label = top.text(0)
        if not tree.isVisible():
            head = self._tab_header(tree)
            if head is not None:
                return head, "the Model tab is not in front: its tab is ringed"
        box = {"tree": tree, "item": top}

        def rect():
            # The row again whenever its tree or item has been rebuilt.
            t, it = box["tree"], box["item"]
            if not (alive(t) and alive(it)):
                fresh = self.trees()
                t = fresh[0] if fresh else None
                it = _find_item(t, row_label, doc) if t is not None else None
                if it is None:
                    return None
                box["tree"], box["item"] = t, it
            return _r(t.visualItemRect(it))

        return {"widget": tree, "viewport": tree.viewport(), "rect": rect}, note

    # ---- docks and views ---------------------------------------------------------
    def dock(self, title):
        from agentlink.targets import norm

        _QtCore, _QtGui, QtW = _qt()
        want = norm(title)
        for d in self.mw().findChildren(QtW.QDockWidget):
            if norm(d.windowTitle()) == want or norm(d.objectName()) == want:
                return {"widget": d}
        return None

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
        obj.objectName() if hasattr(obj, "objectName") else None
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


def _find_item(tree, label, doc_label=None):
    """The tree item labelled label; under the document's own item when
    several documents hold one of that label."""
    hits = []
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop(0)
        if it is None:
            continue
        if it.text(0) == label and it.parent() is not None:
            hits.append(it)
        stack += [it.child(j) for j in range(it.childCount())]

    def in_doc(it):
        p = it.parent()
        while p is not None:
            if p.text(0) == doc_label:
                return True
            p = p.parent()
        return False

    mine = [h for h in hits if doc_label is None or in_doc(h)]
    return (mine or hits or [None])[0]


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
