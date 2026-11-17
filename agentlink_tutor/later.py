# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Tutor's deferred calls on the window's thread, made safe against a
widget that is gone when the call comes due.

FreeCAD crashed once when a timer fired on a deleted object while
Gui.updateGui() ran the event loop. So no deferred call of the Tutor is a
bare QTimer.singleShot(ms, fn) any more. Each one here is a QTimer object:

- owned by a long-lived QObject: the target widget when one is given (a
  timer that is a child of its target dies with it, and never fires), else
  one QObject of the Tutor's own, a child of the application;
- stopped when its target dies, and by stop() or stop_group() (a lesson
  that is replaced takes its calls with it);
- fired only when shiboken6.isValid says the timer, its owner and its
  target are still alive; else the call is dropped, said on stderr.

    h = after(ms, fn, target=None, group=None) -> a handle with stop()
    stop_group(group)
    valid(obj) -> False for a Qt wrapper whose C++ object is gone

Nothing here moves the cursor, takes focus or shows anything.
"""
import sys

_OWNER = {"o": None}
_LIVE = {}  # id(handle) -> handle: the calls waiting, so none is let go early


def _qt():
    from PySide import QtCore

    return QtCore


def _shiboken():
    for mod in ("shiboken6", "shiboken2", "PySide6.shiboken6", "PySide2.shiboken2"):
        try:
            return __import__(mod, fromlist=["isValid"])
        except ImportError:
            continue
    return None


def valid(obj):
    """False for None and for a Qt wrapper whose C++ object is deleted.
    Anything that is not a Qt object (a stand-in) counts as alive."""
    if obj is None:
        return False
    sb = _shiboken()
    if sb is not None:
        try:
            return bool(sb.isValid(obj))
        except Exception:  # noqa: BLE001  (not a Qt object: a stand-in)
            pass
    try:
        if hasattr(obj, "objectName"):
            obj.objectName()
        return True
    except RuntimeError:
        return False


def owner():
    """The Tutor's own long-lived QObject, a child of the application (it
    lives as long as FreeCAD's window); made again if it is gone."""
    o = _OWNER["o"]
    if o is not None and valid(o):
        return o
    QtCore = _qt()
    app = QtCore.QCoreApplication.instance()
    o = QtCore.QObject(app) if app is not None else QtCore.QObject()
    o.setObjectName("TutorTimers")
    _OWNER["o"] = o
    return o


def _is_qobject(x, QtCore):
    try:
        return isinstance(x, QtCore.QObject)
    except TypeError:
        return False


class Later:
    """One deferred call. fire() runs fn once, unless stopped, or the timer,
    its owner or its target is gone."""

    def __init__(self, ms, fn, target=None, group=None):
        QtCore = _qt()
        self.fn, self.target, self.group = fn, target, group
        self.done = False
        self.done_by_stop = False
        par = target if (target is not None and _is_qobject(target, QtCore) and valid(target)) else owner()
        self.parent = par
        t = QtCore.QTimer(par)
        t.setSingleShot(True)
        t.timeout.connect(self.fire)
        self.t = t
        _LIVE[id(self)] = self
        t.start(max(0, int(ms)))

    def alive(self):
        if self.done:
            return False
        if not valid(self.t) or not valid(self.parent):
            return False
        return self.target is None or valid(self.target)

    def fire(self):
        go = self.alive()
        fn = self.fn
        self._end()
        if not go:
            if not self.done_by_stop:
                sys.stderr.write("Tutor: a deferred call was dropped (its window part is gone)\n")
            return
        try:
            fn()
        except Exception as e:  # noqa: BLE001  (a slot must not raise into Qt's event loop)
            sys.stderr.write(f"Tutor: a deferred call failed ({type(e).__name__}: {e})\n")

    def stop(self):
        if self.done:
            return
        self.done_by_stop = True
        self._end()

    def _end(self):
        self.done = True
        _LIVE.pop(id(self), None)
        t, self.t = self.t, None
        if t is not None and valid(t):
            try:
                t.stop()
                t.deleteLater()
            except RuntimeError:
                pass
        self.fn = None  # let go of what the call held (widgets, the controller)


def after(ms, fn, target=None, group=None):
    """fn() in ms on the window's thread, owned as the module says. A
    handle with stop()."""
    return Later(ms, fn, target=target, group=group)


def stop_group(group):
    """Every call still waiting that was made with this group, stopped."""
    for h in [h for h in _LIVE.values() if h.group is group or (group is not None and h.group == group)]:
        h.stop()


def waiting():
    """How many calls are waiting (tests, and a check after a lesson ends)."""
    return len(_LIVE)
