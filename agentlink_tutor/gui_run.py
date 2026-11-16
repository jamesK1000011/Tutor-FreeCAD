# SPDX-License-Identifier: LGPL-2.1-or-later
"""The window's part of a running lesson: Qt timers, the step's rings and
callout through tutor_point's machinery, and the signals a guided step is
checked on (a recompute, an undo or redo, a selection, a workbench switch).
Loaded only where FreeCAD has a window. Nothing here moves the cursor,
opens a menu, switches a workbench or takes focus.
"""
import sys

from . import point



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
