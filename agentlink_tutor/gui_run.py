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

        tg = c.e.hint_targets()
        say = c.callout()
        if not tg:  # words only: the callout at the window's top centre
            point.point({}, None, hooks=hooks)
            ov = hooks.service("overlay")
            if ov is not None and say:
                ov.show([], say=say, owner=point.OWNER)
            return {"resolved": 0, "missing": []}
        got = point.point({"targets": tg, "say": say}, Window(session), hooks=hooks, bindings=c.e.bindings)
        return {"resolved": len(got.get("shown") or []),
                "missing": [str(m.get("why") or "not shown")[:80] for m in got.get("missing") or []]}

    return show


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

