# SPDX-License-Identifier: LGPL-2.1-or-later
"""What the person does in the window, as short events in a ring buffer,
for watch mode (the agent follows along through tutor_watch) and for a
lesson's checks (a command used).

Events are plain dicts with short keys, numbered n in order:

    {n, k: "cmd", c}      a command used (toolbar, menu, shortcut)
    {n, k: "wb", w}       a workbench switched to
    {n, k: "sel", o, s?}  something selected (o object, s sub-element)
    {n, k: "clr"}         the selection cleared
    {n, k: "new", o, ty}  an object made
    {n, k: "del", o}      an object deleted
    {n, k: "rc", d}       a document recomputed
    {n, k: "edit", o}     an object opened for editing (its task panel)
    {n, k: "done", o}     the editing closed (OK, Close or Cancel)
    {n, k: "undo"|"redo"} undo, redo
    {n, k: "save", d}     a document saved
    {n, k: "ask", q}      the person's question (Ask Claude)

A milestone (m: 1) is a point where the person has finished something:
new, done, rc, undo, redo, save, ask. Only the person's events are kept:
those that happen while one of the agent's calls runs are left out
(Agent Link's agent_acting). Bursts coalesce: a run of selections, or of
recomputes, within COALESCE_S keeps the last one in place.

The buffer is thread-safe: the GUI thread pushes, and tutor_watch waits on
Agent Link's socket thread (a long poll) without holding the GUI thread.
Nothing is written to disk or sent anywhere but in answers to the agent's
own calls. The window's observers are attached only while something needs
them (watch mode, a running lesson) and taken off after.
"""
import collections
import threading
import time

MAX = 500
COALESCE_S = 0.3
MILESTONES = ("new", "done", "rc", "undo", "redo", "save", "ask")
COALESCE = ("sel", "rc")
ANSWER_MAX = 40
WAIT_MAX = 25.0


class Buffer:
    def __init__(self, size=MAX, clock=time.monotonic):
        self.cond = threading.Condition()
        self.events = collections.deque(maxlen=size)
        self.seq = 0
        self.clock = clock
        self._last_t = 0.0

    def push(self, k, **fields):
        """Add an event (or replace the last one of a burst); its number."""
        fields = {key: v for key, v in fields.items() if v is not None}
        with self.cond:
            now = self.clock()
            last = self.events[-1] if self.events else None
            self.seq += 1
            ev = {"n": self.seq, "k": k, **fields}
            if k in MILESTONES:
                ev["m"] = 1
            if (k in COALESCE and last is not None and last["k"] == k and now - self._last_t < COALESCE_S
                    and (k != "rc" or last.get("d") == fields.get("d"))):
                self.events[-1] = ev  # the burst's last state, numbered anew
            else:
                self.events.append(ev)
            self._last_t = now
            self.cond.notify_all()
            return self.seq

    def since(self, n=0, kinds=None, limit=None):
        with self.cond:
            out = [e for e in self.events if e["n"] > n and (kinds is None or e["k"] in kinds)]
        return out[-limit:] if limit else out

    def first(self):
        with self.cond:
            return self.events[0]["n"] if self.events else self.seq + 1

    def wait(self, since=0, timeout=0.0, until="any"):
        """Events after since, waiting up to timeout seconds for one (any) or
        for a milestone (milestone); returns what there is at the end."""
        timeout = max(0.0, min(float(timeout or 0), WAIT_MAX))
        end = time.monotonic() + timeout

        def ready():
            evs = [e for e in self.events if e["n"] > since]
            return bool(evs) if until == "any" else any(e.get("m") for e in evs)

        with self.cond:
            while not ready():
                left = end - time.monotonic()
                if left <= 0:
                    break
                self.cond.wait(left)
        return self.since(since)

    def clear(self):
        with self.cond:
            self.events.clear()
            self.cond.notify_all()


BUF = Buffer()

# ---- who needs the observers -----------------------------------------------------------

_NEED = {}  # owner -> fn(event) or None
_ATTACHED = {"on": False, "doc": None, "gui": None, "sel": None}


def active():
    return _ATTACHED["on"]


def need(owner, listener=None, attach=True):
    """owner needs the window's events; listener(event) is told of each.
    The observers attach with the first owner (where there is a window)."""
    _NEED[owner] = listener
    if attach and not _ATTACHED["on"]:
        _attach()
    return _ATTACHED["on"]


def release(owner):
    _NEED.pop(owner, None)
    if not _NEED and _ATTACHED["on"]:
        _detach()


def owners():
    return set(_NEED)


def record(k, **fields):
    """An event from the window: kept (unless the agent is acting) and told
    to each owner's listener. Not while a check changes a parameter for
    a moment (checks.TRIAL): those signals are the Tutor's, not the person's."""
    from . import checks

    if checks.in_trial():
        return None
    try:
        from agentlink import hooks

        if hooks.agent_acting() if hasattr(hooks, "agent_acting") else False:
            return None
    except ImportError:
        pass
    BUF.push(k, **fields)
    ev = BUF.events[-1] if BUF.events else {"k": k}
    for fn in list(_NEED.values()):
        if fn is not None:
            try:
                fn(ev)
            except Exception:  # noqa: BLE001
                pass
    return ev


# ---- the window's observers (GUI thread) ---------------------------------------------------

def _name(o):
    return getattr(o, "Name", None)


class _Doc:
    def slotCreatedObject(self, obj):
        record("new", o=_name(obj), ty=getattr(obj, "TypeId", None))

    def slotDeletedObject(self, obj):
        record("del", o=_name(obj))

    def slotRecomputedDocument(self, doc):
        record("rc", d=getattr(doc, "Name", None))

    def slotUndoDocument(self, doc):
        record("undo")

    def slotRedoDocument(self, doc):
        record("redo")

    def slotFinishSaveDocument(self, doc, path):
        record("save", d=getattr(doc, "Name", None))


class _GuiDoc:
    def slotInEdit(self, vp):
        record("edit", o=_name(getattr(vp, "Object", None)))

    def slotResetEdit(self, vp):
        record("done", o=_name(getattr(vp, "Object", None)))


class _Sel:
    def addSelection(self, doc, obj, sub, pnt):
        record("sel", o=obj, s=sub or None)

    def setSelection(self, doc):
        pass

    def removeSelection(self, doc, obj, sub):
        pass

    def clearSelection(self, doc):
        record("clr")


def _cmd(name, by):
    if by != "agent":
        record("cmd", c=name)


def _wb(name, by):
    if by != "agent":
        record("wb", w=name)


def _attach():
    try:
        import FreeCAD
        import FreeCADGui

        if not FreeCAD.GuiUp:
            return
    except ImportError:
        return
    d, g, s = _Doc(), _GuiDoc(), _Sel()
    for add, obs, key in ((FreeCAD.addDocumentObserver, d, "doc"), (getattr(FreeCADGui, "addDocumentObserver", None), g, "gui"),
                          (FreeCADGui.Selection.addObserver, s, "sel")):
        try:
            if add is not None:
                add(obs)
                _ATTACHED[key] = obs
        except Exception:  # noqa: BLE001
            _ATTACHED[key] = None
    try:
        from agentlink import hooks

        hooks.on("command_used", _cmd)
        hooks.on("workbench_activated", _wb)
        if hasattr(hooks, "watch_window"):
            hooks.watch_window("tutor")
    except ImportError:
        pass
    _ATTACHED["on"] = True


def _detach():
    try:
        import FreeCAD
        import FreeCADGui

        if _ATTACHED["doc"] is not None:
            FreeCAD.removeDocumentObserver(_ATTACHED["doc"])
        if _ATTACHED["gui"] is not None and hasattr(FreeCADGui, "removeDocumentObserver"):
            FreeCADGui.removeDocumentObserver(_ATTACHED["gui"])
        if _ATTACHED["sel"] is not None:
            FreeCADGui.Selection.removeObserver(_ATTACHED["sel"])
    except Exception:  # noqa: BLE001
        pass
    try:
        from agentlink import hooks

        for ev, fn in (("command_used", _cmd), ("workbench_activated", _wb)):
            if hasattr(hooks, "off"):
                hooks.off(ev, fn)
        if hasattr(hooks, "unwatch_window"):
            hooks.unwatch_window("tutor")
    except Exception:  # noqa: BLE001
        pass
    _ATTACHED.update(on=False, doc=None, gui=None, sel=None)
