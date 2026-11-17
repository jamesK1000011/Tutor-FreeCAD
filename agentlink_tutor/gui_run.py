# SPDX-License-Identifier: LGPL-2.1-or-later
"""The window's part of a running lesson: Qt timers, the step's rings and
callout through tutor_point's machinery, and the signals a guided step is
checked on (a recompute, an undo or redo, a selection, a workbench switch).
Loaded only where FreeCAD has a window. Nothing here moves the cursor,
opens a menu or takes focus. In demo mode only, the lesson's own hands
(UI.prepare) put the window the way a step's targets need it: the
command's workbench active (through Agent Link's workbench tool, so the
echo shows it), the Tasks or Model tab in front, a dock shown, a tree
branch unfolded. Guided mode never does: the callout tells the person.
"""
import sys

from . import point



def timer(ms, fn):
    """fn later on the window's thread, as a handle with stop() (later.py:
    a QTimer owned by the Tutor's long-lived QObject, never fired once that
    is gone; the lesson's Controller stops it when the lesson is replaced)."""
    from . import later

    return later.after(int(ms), fn)


def shower(session):
    """show(controller) for run.Controller: rings the targets for the hint
    rung (hint_targets) with the callout's words; show(None) takes the
    tutor's rings away. Answers {resolved, missing}."""

    def show(c):
        try:
            from agentlink import hooks
        except ImportError:
            return None
        if c is None:
            from . import bubble

            point.point({}, None, hooks=hooks, bubble=bubble)
            return None
        from .window import Window

        from . import bubble

        tg, _again = c.shown()
        say = c.parts()
        report = {}
        if not tg:  # words only: the bubble at the 3D view's top, else the overlay's callout
            point.point({}, None, hooks=hooks, bubble=bubble)
            report.update(resolved=0, missing=[], callout="none")
            if say is None or say.empty():
                return report
            if _safe_show(bubble, say, c.e._doc(), report):
                report["callout"] = "bubble"
                return report
            ov = hooks.service("overlay")
            if ov is not None:
                ov.show([], say=say.text(), owner=point.OWNER)
                report["callout"] = "overlay"
            return report
        got = point.point({"targets": tg, "say": say}, Window(session, doc=c.e._doc), hooks=hooks, bindings=c.e.bindings,
                          bubble=bubble, report=report)
        # The same dict the bubble's later self-check updates (callout: overlay).
        report.update(resolved=len(got.get("shown") or []),
                      missing=[str(m.get("why") or "not shown")[:80] for m in got.get("missing") or []])
        return report

    return show


def _safe_show(bubble, words, doc, report):
    try:
        if bubble.show(words, (), doc=doc, report=report):
            return True
        if bubble.why():
            report["callout_why"] = str(bubble.why())[:100]
    except Exception as e:  # noqa: BLE001  (the overlay's callout instead)
        sys.stderr.write(f"Tutor: callout bubble not shown ({e})\n")
        report["callout_why"] = f"bubble failed: {e}"[:100]
    return False


class UI:
    """The lesson's own hands in the window (run.Controller's ui): only
    what the lesson itself left or needs open, never the person's cursor,
    focus or menus."""

    def __init__(self, session=None):
        self.s = session
        self.opened = None  # (document name, object name) this opened for edit

    def _gd(self, doc=None):
        import FreeCADGui

        if doc is not None:
            try:
                return FreeCADGui.getDocument(doc.Name)
            except Exception:  # noqa: BLE001
                pass
        return FreeCADGui.ActiveDocument

    def settle(self, doc=None):
        """After setup: no sketch or feature left in edit in the lesson's
        document, no task dialog, nothing selected (the person starts from a
        quiet window)."""
        import FreeCADGui

        gd = self._gd(doc)
        try:
            if gd is not None and gd.getInEdit() is not None:
                gd.resetEdit()
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"Tutor: edit not closed after setup ({e})\n")
        try:
            if FreeCADGui.Control.activeDialog():
                FreeCADGui.Control.closeDialog()
        except Exception:  # noqa: BLE001
            pass
        try:
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.updateGui()
        except Exception:  # noqa: BLE001
            pass

    def frame(self, view, doc=None, animate=True):
        """The lesson document's 3D view set to view (isometric, front, top,
        right, left, rear, bottom) and fitted to the part. animate False
        (reduced motion): the view's own animation is off while it turns,
        and back as it was after."""
        gd = self._gd(doc)
        v = gd.activeView() if gd is not None else None
        if v is None:
            return
        was = None
        if not animate and hasattr(v, "isAnimationEnabled") and hasattr(v, "setAnimationEnabled"):
            try:
                was = bool(v.isAnimationEnabled())
                v.setAnimationEnabled(False)
            except Exception:  # noqa: BLE001
                was = None
        try:
            turn = getattr(v, "view" + view.capitalize(), None)
            if view == "isometric":
                turn = getattr(v, "viewIsometric", None)
            if callable(turn):
                turn()
            if hasattr(v, "fitAll"):
                v.fitAll()
        finally:
            if was is not None:
                try:
                    v.setAnimationEnabled(was)
                except Exception:  # noqa: BLE001
                    pass

    def open_task(self, engine):
        """Demo: open the feature the step's do works on, so its task panel
        (the field and OK the step rings) shows before Next does it."""
        from . import run

        name = run.edit_target(engine)
        doc = engine._doc()
        obj = doc.getObject(name) if (doc is not None and name) else None
        if obj is None:
            return
        gd = self._gd(doc)
        if gd is None:
            return
        cur = gd.getInEdit()
        if cur is not None:
            return  # something is open already (the person's, or ours)
        gd.setEdit(obj.Name, 0)
        self.opened = (doc.Name, obj.Name)

    def prepare(self, engine):
        """Demo: the window made ready for the step's targets, as a person
        following the lesson would have it. Answers what it did (short
        lines), [] when nothing was needed. Each target kind:

            cmd    no button of it shows and its workbench is not the
                   active one: that workbench activated
            task   the Tasks panel brought to the front (its Combo View
                   tab, its dock), the field scrolled into view
            dock   the panel brought to the front (FreeCAD 1.1's Property
                   view: the Combo View's Model tab)
            tree   the Model tab brought to the front first (Qt let
                   run, so the tree is laid out), then the object's
                   parents unfolded in the tree, its document's row too
        """
        from . import targets as targets_mod
        from .window import Window, ancestors

        win = Window(self.s, doc=engine._doc)
        did = []
        tg = [t for t in (engine.hint_targets() or []) if isinstance(t, dict)]
        for t in tg:
            try:
                if "cmd" in t:
                    got = self._bench_for(engine, win, t["cmd"])
                elif "task" in t:
                    got = self._tasks_front(win, t["task"])
                elif "dock" in t:
                    got = self._panel_front(win, t["dock"])
                elif "tree" in t:
                    ref = targets_mod.bind(t["tree"], engine.bindings)
                    obj = win.obj(ref) if isinstance(ref, str) else None
                    got = self._tree_open(win, obj, ancestors) if obj is not None else None
                else:
                    got = None
            except Exception as e:  # noqa: BLE001  (pointing still says why)
                got = f"not prepared: {e}"[:80]
            if got and got not in did:
                did.append(got)
        return did

    def _bench_for(self, engine, win, cmd):
        if any(h is None for _w, h in win.command_buttons(cmd)):
            return None
        if any(g[1] is None for g in win.command_groups(cmd)):
            return None
        bench = win.workbench_of(cmd)
        if not bench or bench == win.active_workbench() or bench not in (win.loaded_benches() or []):
            return None
        refused = True
        if engine.call is not None:
            try:
                refused, _out = engine.call("workbench", {"activate": bench})
            except Exception:  # noqa: BLE001
                refused = True
        if refused:
            import FreeCADGui

            FreeCADGui.activateWorkbench(bench)
        return f"workbench {win.bench_title(bench)} activated"

    def bring(self, w):
        """w brought to the front: its dock shown, the tabs above it made
        current, its scroll area scrolled to it. True when something moved."""
        from .window import _qt, front_steps

        _QtCore, _QtGui, QtW = _qt()
        moved = False
        for kind, x, arg in front_steps(w, QtW, self._mw()):
            if kind == "dock":
                x.show()
                x.raise_()
            elif kind == "tab":
                x.setCurrentIndex(arg)
            elif kind == "scroll":
                x.ensureWidgetVisible(arg)
            moved = True
        if moved:
            self._update()
        return moved

    def _mw(self):
        import FreeCADGui

        return FreeCADGui.getMainWindow()

    def _update(self):
        try:
            import FreeCADGui

            FreeCADGui.updateGui()
        except Exception:  # noqa: BLE001
            pass

    def _tasks_front(self, win, spec):
        if not win.task_open():
            return None
        tv = win._taskview()
        if tv is None:
            return None
        moved = self.bring(tv)
        q = {"label": spec} if isinstance(spec, str) else dict(spec)
        got, _note = win.task_widget(name=q.get("name"), label=q.get("label"), button=q.get("button"))
        w = got.get("widget") if isinstance(got, dict) else None
        if w is not None and w is not tv:
            moved = self.bring(w) or moved
        return "Tasks panel in front" if moved else None

    def _panel_front(self, win, title):
        for p in win.panels(title):
            if self.bring(p):
                return f"{title} in front"
            return None
        return None

    def _tree_open(self, win, obj, ancestors):
        """Unfold the tree down to obj's row: in every Model tree (the Combo
        View's, a Tree view dock), from its document's row along the rows
        that hold it (body, then the feature that claims it), Qt let run
        between unfoldings (FreeCAD fills a row's children in when it is
        unfolded). Says so only when its row then shows; else why not."""
        import FreeCADGui

        # The Model tab in front first (the Tutor's own Agent Link tab or
        # the Tasks tab is, during a lesson: FreeCAD raises Tasks whenever
        # a task dialog opens), Qt let run, so the tree is laid out before
        # any row is unfolded, scrolled to or looked for. Before anything
        # else: a row that is unfolded already still cannot be ringed while
        # its dock is tabbed behind another (bike-stem-1 steps 13-14).
        front = win.model_tree(obj)
        brought = bool(front is not None and self.bring(front))
        if brought:
            self._update()
            win.pump()
        got, note = win.tree_row(obj)
        if got is not None and note is None:
            # Its row is unfolded already; it may still be scrolled away.
            if scroll_to(win, obj, ancestors):
                self._update()
                win.pump()
                return f"{obj.Label} scrolled into view in the tree"
            return f"{obj.Label} shown in the tree" if brought else None
        doc = getattr(obj, "Document", None)
        try:
            gd = FreeCADGui.getDocument(doc.Name) if doc is not None else None
        except Exception:  # noqa: BLE001
            gd = None
        moved = unfold_to(win, obj, ancestors)
        if gd is not None and hasattr(gd, "toggleTreeItem"):
            for a in reversed(ancestors(obj)):
                try:
                    gd.toggleTreeItem(a, 2)  # 2: unfold (fills in its rows)
                    moved = True
                except Exception:  # noqa: BLE001
                    continue
            if moved:
                win.pump()
                moved = unfold_to(win, obj, ancestors) or moved
        front = win.model_tree(obj)
        if front is not None:
            moved = self.bring(front) or moved
        moved = moved or brought
        if moved:
            self._update()
            win.pump()
        got, note = win.tree_row(obj)
        if got is None:
            return f"{obj.Label} not shown in the tree: {note}"[:600]
        # Unfolded, the row can still lie below the tree's bottom edge (a
        # long history: the ring said "scrolled out of view" on bike-stem-1's
        # Sketch row): the tree is scrolled to it, as a person would.
        if scroll_to(win, obj, ancestors):
            moved = True
            self._update()
            win.pump()
        return f"{obj.Label} shown in the tree" if moved else None

    def close_task(self):
        """Before the do sets the value: the panel this opened is closed."""
        if self.opened is None:
            return
        import FreeCAD

        doc = FreeCAD.getDocument(self.opened[0]) if self.opened[0] in FreeCAD.listDocuments() else None
        self.opened = None
        gd = self._gd(doc) if doc is not None else None
        try:
            if gd is not None and gd.getInEdit() is not None:
                gd.resetEdit()
        except Exception:  # noqa: BLE001
            pass


def attach(c):
    """The window's events re-check the step in front (the controller's
    poke is debounced); observe.py owns the observers."""
    from . import observe

    observe.need(("lesson", id(c)), lambda ev, c=c: c.poke(ev if isinstance(ev, dict) else None))


def detach(c):
    from . import observe

    observe.release(("lesson", id(c)))


def badge(on):
    """The visible sign that Claude is watching: a label in the status bar
    while watch mode is on."""
    import FreeCADGui

    sb = FreeCADGui.getMainWindow().statusBar()
    lab = _BADGE.get("label")
    from . import later

    if lab is not None and not later.valid(lab):  # gone with the status bar
        _BADGE.pop("label", None)
        lab = None
    if on:
        if lab is None:
            from PySide import QtGui

            QtW = getattr(__import__("PySide", fromlist=["QtWidgets"]), "QtWidgets", QtGui)
            lab = QtW.QLabel("● Claude is watching (Tutor tab: turn it off)")
            lab.setObjectName("TutorWatchBadge")
            lab.setAccessibleName("Claude is watching")
            sb.addPermanentWidget(lab)
            _BADGE["label"] = lab
        lab.show()
    elif lab is not None:
        try:
            sb.removeWidget(lab)
            lab.deleteLater()
        except RuntimeError:
            pass
        _BADGE.pop("label", None)


_BADGE = {}


def unfold_to(win, obj, ancestors):
    """Unfold every Model tree from obj's document row down along the rows
    that hold it, letting Qt fill each branch in before the next; a row
    unfolded before its children were filled in is folded and unfolded
    again. True when a row was unfolded."""
    from .window import _child_row, _doc_item, _doc_key

    doc = _doc_key(getattr(obj, "Document", None))
    path = list(reversed(ancestors(obj)))
    moved = False
    for t in win.trees():
        try:
            row = _doc_item(t, doc)
            if row is None:
                continue
            for nxt in path + [obj]:  # obj's own row is left as it is
                if not row.isExpanded():
                    _expand(t, row)
                    moved = True
                    win.pump()
                got = _child_row(row, nxt)
                if got is None:
                    _expand(t, row, False)
                    _expand(t, row)
                    win.pump()
                    moved = True
                    got = _child_row(row, nxt)
                if got is None:
                    break
                row = got
        except RuntimeError:  # deleted while read
            continue
    return moved


def row_shows(view_h, top, bottom):
    """Whether a row from top to bottom (pixels in its tree's viewport, which
    is view_h high) shows whole enough to ring: its middle inside the viewport."""
    mid = (top + bottom) / 2.0
    return 0 <= mid <= view_h


def scroll_to(win, obj, ancestors):
    """Each shown Model tree scrolled so obj's row is in view, where it is
    unfolded but lies outside the viewport. True when a tree was scrolled.
    Demo only (the lesson's own preparation); nothing is selected, folded
    or unfolded."""
    from .window import _child_row, _doc_item, _doc_key

    doc = _doc_key(getattr(obj, "Document", None))
    path = list(reversed(ancestors(obj))) + [obj]
    moved = False
    for t in win.trees():
        try:
            if not t.isVisible():
                continue
            row = _doc_item(t, doc)
            for nxt in path:
                if row is None or not row.isExpanded():
                    row = None
                    break
                row = _child_row(row, nxt)
            if row is None:
                continue
            r = t.visualItemRect(row)
            if row_shows(t.viewport().height(), r.top(), r.bottom()):
                continue
            t.scrollToItem(row)
            moved = True
        except (RuntimeError, AttributeError):  # deleted while read; a stand-in tree
            continue
    return moved


def scroll_row(win, obj, ancestors):
    """The row tree_row rings for obj (its own, else its nearest folded
    parent's) scrolled into view in each Model tree that is in front, where
    it lies outside the tree's viewport. Nothing is unfolded, folded or
    selected. True when a tree was scrolled."""
    from .window import _child_row, _doc_item, _doc_key

    doc = _doc_key(getattr(obj, "Document", None))
    path = list(reversed(ancestors(obj))) + [obj]
    moved = False
    for t in win.trees():
        try:
            if not win.front(t):
                continue
            row = _doc_item(t, doc)
            if row is None:
                continue
            for nxt in path:
                if not row.isExpanded():
                    break  # folded: this row is the one ringed
                got = _child_row(row, nxt)
                if got is None:
                    break
                row = got
            r = t.visualItemRect(row)
            if row_shows(t.viewport().height(), r.top(), r.bottom()):
                continue
            t.scrollToItem(row)
            moved = True
        except (RuntimeError, AttributeError):  # deleted while read; a stand-in tree
            continue
        finally:
            row = None  # no row is held past here (FreeCAD rebuilds them)
    return moved


def model_front(win, obj, ancestors, ui=None):
    """tutor_point's tree target: the Model tree that holds obj's document
    brought to the front, then obj's row scrolled into view, so the row
    itself is ringed and not the Model tab (round 4, picture 0002: the
    Tutor's own Agent Link tab was in front, and the tab was ringed).
    As FreeCAD does it: Control.showModelView() (the Model or Tree view
    dock shown and raised), Qt let run; a dock still tabbed behind another
    is raised by its own steps (gui_run.UI.bring), and last its tab in the
    main window's tab bar made the current one. No focus is taken, no
    cursor moved, nothing unfolded or selected. Answers a short line of
    what it did, None when nothing was needed."""
    from .window import _qt, behind, dock_of, dock_tab

    tree = win.model_tree(obj)
    if tree is None:
        return None
    did = []
    if not win.front(tree):
        try:
            ctl = getattr(win.gui(), "Control", None)
            show = getattr(ctl, "showModelView", None)
            if callable(show):
                show()
                win.pump()
        except Exception as e:  # noqa: BLE001  (the next ways still try)
            sys.stderr.write(f"Tutor: showModelView failed ({e})\n")
        tree = win.model_tree(obj) or tree
        if not win.front(tree):
            if ui is None:
                ui = UI(getattr(win, "s", None))
                ui._mw = win.mw  # the window this Window reads
            try:
                if ui.bring(tree):
                    win.pump()
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"Tutor: the Model dock not raised ({e})\n")
        if not win.front(tree):
            try:
                QtW = _qt()[2]
                mw = win.mw()
                if behind(tree, QtW, mw):
                    got = dock_tab(dock_of(tree, QtW), QtW, mw, shown_only=True)
                    if got is not None:
                        got[0].setCurrentIndex(got[1])
                        win.pump()
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"Tutor: the Model tab not made current ({e})\n")
        if not win.front(tree):
            return None  # tree_row rings the Model tab and says why
        did.append("the Model tab brought to the front")
    if scroll_row(win, obj, ancestors):
        win.pump()
        did.append(f"{getattr(obj, 'Label', 'its')} row scrolled into view")
    return "; ".join(did) or None


def _expand(tree, item, on=True):
    if on and hasattr(tree, "expandItem"):
        tree.expandItem(item)
    elif not on and hasattr(tree, "collapseItem"):
        tree.collapseItem(item)
    else:
        item.setExpanded(on)
