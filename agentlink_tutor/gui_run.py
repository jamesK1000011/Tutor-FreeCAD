# SPDX-License-Identifier: LGPL-2.1-or-later
"""The window's part of a running lesson: Qt timers, the step's rings and
callout through tutor_point's machinery, and the signals a guided step is
checked on (a recompute, an undo or redo, a selection, a workbench switch).
Loaded only where FreeCAD has a window. Nothing here moves the cursor,
opens a menu, switches a workbench or takes focus.
"""
import sys

from . import point

_OBS = {}  # controller id -> (doc observer, selection observer, workbench slot)


def timer(ms, fn):
    from PySide import QtCore

    QtCore.QTimer.singleShot(int(ms), fn)


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
            point.point({}, None, hooks=hooks)
            return None
        from .window import Window

        tg, _again = c.shown()
        say = c.callout()
        if not tg:  # words only: the callout at the window's top centre
            point.point({}, None, hooks=hooks)
            ov = hooks.service("overlay")
            if ov is not None and say:
                ov.show([], say=point.plain(say), owner=point.OWNER)
            return {"resolved": 0, "missing": []}
        got = point.point({"targets": tg, "say": say}, Window(session, doc=c.e._doc), hooks=hooks, bindings=c.e.bindings)
        return {"resolved": len(got.get("shown") or []),
                "missing": [str(m.get("why") or "not shown")[:80] for m in got.get("missing") or []]}

    return show


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

    def settle(self):
        """After setup: no sketch or feature left in edit, no task dialog,
        nothing selected (the person starts from a quiet window)."""
        import FreeCADGui

        gd = self._gd()
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

    def frame(self, view, doc=None):
        """The lesson document's 3D view set to view (isometric, front, top,
        right, left, rear, bottom) and fitted to the part."""
        gd = self._gd(doc)
        v = gd.activeView() if gd is not None else None
        if v is None:
            return
        turn = getattr(v, "view" + view.capitalize(), None)
        if view == "isometric":
            turn = getattr(v, "viewIsometric", None)
        if callable(turn):
            turn()
        if hasattr(v, "fitAll"):
            v.fitAll()

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


class _DocObserver:
    def __init__(self, poke):
        self.poke = poke

    def slotRecomputedDocument(self, doc):
        self.poke()

    def slotUndoDocument(self, doc):
        self.poke()

    def slotRedoDocument(self, doc):
        self.poke()

    def slotDeletedObject(self, obj):
        self.poke()


class _SelObserver:
    def __init__(self, poke):
        self.poke = poke

    def addSelection(self, doc, obj, sub, pnt):
        self.poke()

    def removeSelection(self, doc, obj, sub):
        self.poke()

    def setSelection(self, doc):
        self.poke()

    def clearSelection(self, doc):
        self.poke()


def attach(c):
    """The signals that re-check the step in front (debounced by the
    controller's poke)."""
    if id(c) in _OBS:
        return
    import FreeCAD
    import FreeCADGui

    doc_obs, sel_obs, slot = _DocObserver(c.poke), _SelObserver(c.poke), None
    try:
        FreeCAD.addDocumentObserver(doc_obs)
    except Exception as e:  # noqa: BLE001
        doc_obs = None
        sys.stderr.write(f"Tutor: no document signals ({e})\n")
    try:
        FreeCADGui.Selection.addObserver(sel_obs)
    except Exception as e:  # noqa: BLE001
        sel_obs = None
        sys.stderr.write(f"Tutor: no selection signals ({e})\n")
    try:
        mw = FreeCADGui.getMainWindow()

        def slot(_name=None):
            c.poke()

        mw.workbenchActivated.connect(slot)
    except Exception:  # noqa: BLE001  (a step on the workbench is checked on Next)
        slot = None
    _OBS[id(c)] = (doc_obs, sel_obs, slot)


def detach(c):
    got = _OBS.pop(id(c), None)
    if got is None:
        return
    doc_obs, sel_obs, slot = got
    try:
        import FreeCAD
        import FreeCADGui

        if doc_obs is not None:
            FreeCAD.removeDocumentObserver(doc_obs)
        if sel_obs is not None:
            FreeCADGui.Selection.removeObserver(sel_obs)
        if slot is not None:
            FreeCADGui.getMainWindow().workbenchActivated.disconnect(slot)
    except Exception:  # noqa: BLE001
        pass

