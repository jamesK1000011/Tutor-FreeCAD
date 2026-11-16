# SPDX-License-Identifier: LGPL-2.1-or-later
"""The lesson running in this FreeCAD (one at a time), shared by the Tutor
tab and the agent's tutor tool, so either can drive it and both show the
same step. In memory only.

new(lesson, call, doc, out_dir, session) builds its engine and Controller
(run.py) with the window's timers, pointing and signals when FreeCAD has a
window, none without. call_done and rider are what Agent Link calls
(fam_tutor registers them); without a lesson they do nothing.
"""

NOW = {"ctl": None}
# The window's state for checks in place of checks.gui_state (tests only).
GUI = None
# The lesson's window hands in place of gui_run.UI (tests only).
UI = None
# fn(controller or None) for each change of the lesson in hand (the tab).
WATCHERS = []


def controller():
    return NOW["ctl"]


def engine():
    c = NOW["ctl"]
    return c.e if c is not None else None


def set_controller(c):
    old = NOW["ctl"]
    if old is not None and old is not c:
        _detach(old)
    NOW["ctl"] = c
    if c is not None:
        for w in WATCHERS:
            if w not in c.listeners:
                c.listeners.append(w)
    for w in list(WATCHERS):
        try:
            w(c)
        except Exception:  # noqa: BLE001
            pass


def watch(fn):
    if fn not in WATCHERS:
        WATCHERS.append(fn)
    c = NOW["ctl"]
    if c is not None and fn not in c.listeners:
        c.listeners.append(fn)


def unwatch(fn):
    if fn in WATCHERS:
        WATCHERS.remove(fn)
    c = NOW["ctl"]
    if c is not None and fn in c.listeners:
        c.listeners.remove(fn)


def bindings():
    e = engine()
    return dict(getattr(e, "bindings", None) or {}) if e is not None else {}


def _window():
    try:
        import FreeCAD

        return bool(FreeCAD.GuiUp)
    except ImportError:
        return False


def find_doc(name):
    """The open document called name (FreeCAD's Name), or None."""
    try:
        import FreeCAD

        return FreeCAD.getDocument(name) if name in FreeCAD.listDocuments() else None
    except Exception:  # noqa: BLE001
        return None


def front_doc():
    """The name of the document whose view is the window's front tab (the
    GUI's active document follows the MDI area, which FreeCAD's own
    setActiveDocument may leave on another), or None."""
    try:
        import FreeCADGui

        gd = FreeCADGui.ActiveDocument
        return gd.Document.Name if gd is not None else None
    except Exception:  # noqa: BLE001
        return None


def taken_names():
    """Document names in use: the open documents' names and labels, and the
    names of recently saved files (FreeCAD's recent-files list)."""
    out = set()
    try:
        import os

        import FreeCAD

        for name, d in FreeCAD.listDocuments().items():
            out.update({name, getattr(d, "Label", name)})
            if getattr(d, "FileName", ""):
                out.add(os.path.splitext(os.path.basename(d.FileName))[0])
        p = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/RecentFiles")
        for i in range(int(p.GetInt("RecentFiles", 4) or 4) + 8):
            f = p.GetString(f"MRU{i}", "")
            if f:
                out.add(os.path.splitext(os.path.basename(f))[0])
    except Exception:  # noqa: BLE001  (no FreeCAD: nothing known in use)
        pass
    return out


def new(lesson, call, doc, out_dir=None, session=None, gui=None, window=None, progress=None):
    """A Controller for lesson, made the one in hand. gui: the window's state
    for checks (checks.gui_state with a window). window: True/False forces
    whether timers, rings and signals are used (default: FreeCAD.GuiUp)."""
    from . import checks, engine as engine_mod, lessons, run

    win = _window() if window is None else window
    if gui is None:
        gui = GUI or (checks.gui_state if win else (lambda: None))
    e = engine_mod.Engine(lesson, call=call, doc=doc, gui=gui, out_dir=out_dir,
                          progress=progress if progress is not None else lessons.Progress(),
                          find_doc=find_doc if win else None, front=front_doc if win else None, taken=taken_names)
    timer = show = ui = None
    if win:
        from . import gui_run

        timer = gui_run.timer
        show = gui_run.shower(session)
        ui = gui_run.UI(session)
    c = run.Controller(e, timer=timer, show=show, ui=UI or ui)
    e._events = c.step_events  # `used` checks: the person's commands since the step began
    set_controller(c)
    if win:
        from . import gui_run

        c.listeners.append(_follow)
        gui_run.attach(c)
    return c


def _follow(c):
    """Signals off once the lesson is over."""
    if c.e.state in ("done", "stopped"):
        _detach(c)


def _detach(c):
    try:
        from . import gui_run

        gui_run.detach(c)
    except Exception:  # noqa: BLE001
        pass
    if c.show is not None and c.e.state == "stopped":  # done: the last rings are held (run.HOLD_MS)
        try:
            c.show(None)
        except Exception:  # noqa: BLE001
            pass


def stop():
    c = NOW["ctl"]
    if c is not None and c.e.state == "step":
        c.act("stop")
    set_controller(None)


# ---- what Agent Link calls ----------------------------------------------------------

def call_done(session, tool, ok, changed=False, *rest):
    c = NOW["ctl"]
    if c is not None:
        c.call_done(session, tool, ok, changed)


def rider(tool=None):
    c = NOW["ctl"]
    return c.rider(tool) if c is not None else None


# ---- watch mode: no lesson; the agent follows the person's events -----------------------

WATCH = {"on": False}


def watching():
    return WATCH["on"]


def watch_mode(on):
    """Watch mode on or off: the window's observers and the visible badge
    with it. Off by default; the buffer is cleared when it goes off."""
    from . import observe

    on = bool(on)
    if on == WATCH["on"]:
        return on
    WATCH["on"] = on
    if on:
        observe.need("watch")
    else:
        observe.release("watch")
        observe.BUF.clear()
    if _window():
        try:
            from . import gui_run

            gui_run.badge(on)
        except Exception:  # noqa: BLE001
            pass
    for w in list(WATCHERS):
        try:
            w(NOW["ctl"])
        except Exception:  # noqa: BLE001
            pass
    return on
