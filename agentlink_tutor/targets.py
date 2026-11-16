# SPDX-License-Identifier: LGPL-2.1-or-later
"""Where a lesson's target is in the window, or why it cannot be shown.

Each target spec (lessons.TARGET_KINDS) is resolved against a window, the
object window.py makes over FreeCAD's main window with Agent Link's own
finders (agentlink.targets, the overlay's visible()); tests give a
stand-in. Resolution never changes anything: no workbench is switched, no
menu opened, no tree branch unfolded, nothing selected or focused.

A target that cannot be found never fails the call: it comes back with
why, and where it helps, words for the callout instead (a menu path, a
command's name and shortcut).

    cmd     the command's toolbar buttons (QAction by objectName); inside a
            toolbar dropdown: the ▾ arrow of its button, the item ringed
            once the menu opens; behind a short toolbar's »: that button;
            hidden with its workbench: "toolbar hidden: Part Design is not
            the active workbench; call workbench activate first", the
            workbench selector ringed and "Switch to the Part Design
            workbench." put before the instruction (demo mode switches it
            itself first, gui_run.UI.prepare)
    menu    the menubar title, then each title inside as the person opens
            it; on the native macOS menubar the path in words, and the
            command's toolbar button ringed when it has one
    wb      the workbench selector (its tab, when it is a tab bar)
    task    in the open task dialog: objectName first, then the field a
            label stands for (its buddy), or a button (ok, cancel, apply,
            close, reset, help); the Tasks tab's header when that tab is
            not in front (a Combo View tab, or a dock tabbed with others)
    tree    the object's row in the Model tab, matched by its label under
            its document's row (which may read the document's Label or Name,
            with a * or a " : 1" at its end); the Model tab's header with
            "Open the Model tab." when that tab is not in front (the Tutor's
            Agent Link tab or the Tasks tab is); a folded parent's row when
            the branch is folded or not filled in yet (it is never unfolded
            here: in demo mode the lesson's own hands bring the Model tab to
            the front and unfold it first, gui_run.UI.prepare). Not found:
            the reason names each tree searched, shown or hidden, and
            whether it holds the document's row
    face, edge, sub   lit in the 3D view through the annotation layer,
            never through FreeCAD's selection
    dock    a dock by its title (Report view, Python console …), or the
            panel of that name inside another dock (FreeCAD 1.1's Property
            view in the Combo View's Model tab): that tab ringed when it is
            not in front
    view    "3d": the 3D view in front
    ext     an add-on's own kind: hooks.read("tutor_target", spec, window)
"""

import re

from . import lessons
from . import words as words_mod

TASK_BUTTONS = ("ok", "cancel", "apply", "close", "reset", "help")


class Found:
    """One target, resolved: what to draw and what to say.

    marks   overlay specs ({widget, rect?, viewport?})
    menu    titles to ring through the overlay's menu()
    dropdown (menu, action): the item inside a toolbar button's dropdown,
            ringed when the person opens it (overlay watch_menu)
    light   (object, [sub-element names]) for the annotation layer
    text    words for the callout in place of (or beside) a ring
    note    a remark on what was found ("already active")
    why     why nothing could be shown
    """

    def __init__(self, n, kind, what=""):
        self.n, self.kind, self.what = n, kind, what
        self.marks, self.menu, self.light = [], None, None
        self.dropdown = None
        self.text = self.note = self.why = None
        # A step the person does first ("Switch to the Part Design
        # workbench."), put before the instruction's step that names the
        # command (names); callout.merge.
        self.before = self.names = None
        # A command reached only through a toolbar dropdown: its name as the
        # window shows it. The callout puts text's steps in place of the
        # instruction's "Push <name>." (callout.merge), not after it.
        self.replaces = None

    def shown(self):
        return bool(self.marks or self.menu or self.light)

    def answer(self):
        out = {"n": self.n, "kind": self.kind}
        if self.what:
            out["on"] = self.what
        for k in ("note", "why", "text"):
            v = getattr(self, k)
            if v:
                out[k] = v
        if self.before:
            out["text"] = self.before + (f" {self.text}" if self.text else "")
        return out


def bind(value, bindings):
    """"$name" swapped for what the lesson bound it to; else as given."""
    if isinstance(value, str):
        m = lessons.VAR.match(value)
        if m:
            return (bindings or {}).get(m.group(1), value)
    return value


def resolve(spec, n, win, bindings=None):
    """A Found for spec, the n-th target (badge n), on win."""
    kind = lessons.target_kind(spec)
    f = Found(n, kind)
    try:
        RESOLVE[kind](f, spec, win, bindings or {})
    except Exception as e:  # noqa: BLE001 — a target that breaks is a target missed
        f.marks, f.menu, f.light = [], None, None
        f.why = f"could not be found ({type(e).__name__}: {e})"
    return f


def _bench(win, wb):
    try:
        return win.bench_title(wb) or wb
    except Exception:
        return wb


def _cmd_name(win, cmd):
    """The command as this window names it (its menu text), never its
    internal name."""
    info = win.command_info(cmd) or {}
    return words_mod.clean_menu_text(info.get("menuText")) or words_mod.command_words(cmd)


def _cmd_words(win, cmd):
    info = win.command_info(cmd) or {}
    words = _cmd_name(win, cmd)
    keys = info.get("shortcut")
    return f"{words} ({keys})" if keys else words


def _spec(win, how, w):
    """win's ring spec for widget w (how: dropdown_spec, the ▾ arrow of a
    dropdown button), or the widget whole."""
    fn = getattr(win, how, None)
    if fn is not None:
        try:
            got = fn(w)
            if got:
                return got
        except Exception:  # noqa: BLE001
            pass
    return {"widget": w}


def _overflow(win, w):
    """The » button of the toolbar w is in, when w is hidden only because
    that toolbar is too short to show it (its overflow); else None."""
    fn = getattr(win, "overflow", None)
    if fn is None:
        return None
    try:
        return fn(w)
    except Exception:  # noqa: BLE001
        return None


def _cmd(f, spec, win, _b):
    cmd = spec["cmd"]
    f.what = f"{cmd} button"
    if not win.command_exists(cmd):
        f.why = f"no command {cmd} in this FreeCAD"
        return
    own = win.command_buttons(cmd)
    seen = [w for w, hidden in own if hidden is None]
    if seen:
        f.marks = [{"widget": w} for w in seen]
        return
    name = _cmd_name(win, cmd)
    words = _cmd_words(win, cmd)
    # Inside a toolbar dropdown (a group command: the button shows the
    # group's action): the button's ▾ arrow ringed, the item inside it once
    # the person opens it.
    every = list(win.command_groups(cmd)) if hasattr(win, "command_groups") else []
    groups = [g for g in every if g[1] is None]
    if groups:
        button, _hidden, menu, action = groups[0]
        f.marks = [_spec(win, "dropdown_spec", button)]
        f.dropdown = (menu, action)
        f.note = "in the ▾ menu of this button"
        f.text = f"Open the ▾ menu of the ringed button {words_mod.badge(f.n)}. Select {words}."
        f.replaces = name
        return
    # The toolbar is there but too short: the button (or its dropdown) is
    # behind the toolbar's » button.
    for w, _hidden in own:
        ext = _overflow(win, w)
        if ext:
            f.marks = [ext]
            f.note = "behind the toolbar's » button"
            f.text = f"Push » at the end of the toolbar {words_mod.badge(f.n)}. Push {words}."
            f.replaces = name
            return
    for button, _hidden, menu, action in every:
        ext = _overflow(win, button)
        if ext:
            f.marks = [ext]
            f.dropdown = (menu, action)
            f.note = "behind the toolbar's » button, in a ▾ menu"
            f.text = f"Push » at the end of the toolbar {words_mod.badge(f.n)}. Open the ▾ menu of the button that holds {name}. Select {words}."
            f.replaces = name
            return
    bench = win.workbench_of(cmd)
    active = win.active_workbench()
    if bench and bench != active:
        title = _bench(win, bench)
        f.why = f"toolbar hidden: {title} is not the active workbench; call workbench activate first"
        # The person switches first (an STE step before the instruction's
        # own); the workbench selector ringed where it shows.
        f.names = name
        sel = None
        try:
            sel = win.workbench_selector(bench) if bench in (win.loaded_benches() or [bench]) else None
        except Exception:  # noqa: BLE001
            sel = None
        if sel and win.visible(sel) is None:
            f.marks = [sel]
            f.note = f.why
            f.before = f"Switch to the {title} workbench {words_mod.badge(f.n)}."
        else:
            f.before = f"Switch to the {title} workbench (View › Workbench › {title})."
        return
    if own or every:
        f.why = "its toolbar is hidden or covered"
    else:
        f.why = "no toolbar button for it here"
    f.text = words


def _menu(f, spec, win, _b):
    titles = spec["menu"]
    if isinstance(titles, str):
        # A command's name: its path is read from this window's menus, so a
        # lesson holds no titles (they change between releases and languages).
        cmd = titles
        found = win.menu_path_of(cmd)
        if not found:
            name = _cmd_name(win, cmd)
            f.what = f"menu {name}"
            f.why = f"{name} is in no menu of this window"
            wb = win.workbench_of(cmd)
            if wb and win.active_workbench() != wb:
                f.why += f" (its menu comes with {win.bench_title(wb)}; call workbench activate first)"
            f.text = f"Menu: {name}"
            return
        titles = found
    path = " › ".join(titles)
    f.what = f"menu {path}"
    info = win.menu_info(titles) or {}
    if info.get("missing"):
        f.why = f"no menu item {info['missing']!r} on the way to {path}"
        if titles and win.active_workbench() and titles[0] not in (win.menu_titles() or []):
            f.why += " (its menu comes with its workbench; call workbench activate first)"
        f.text = f"Menu: {path}"
        return
    if not info.get("native"):
        f.menu = list(titles)
        return
    # The system's menubar (macOS) cannot be drawn over: the path in words,
    # and the same command's toolbar button ringed where there is one.
    f.note = "menu: native"
    cmd = info.get("cmd")
    keys = (win.command_info(cmd) or {}).get("shortcut") if cmd else None
    f.text = f"Menu: {path}" + (f" ({keys})" if keys else "")
    seen = [w for w, hidden in win.command_buttons(cmd) if hidden is None] if cmd else []
    if seen:
        f.marks = [{"widget": w} for w in seen]
        f.text += f", or the ringed toolbar button {words_mod.badge(f.n)}"
    else:
        f.why = "the macOS menubar cannot be drawn over; the path is in the callout"


def _wb(f, spec, win, _b):
    wb = spec["wb"]
    title = _bench(win, wb)
    f.what = f"workbench {title}"
    if wb not in (win.loaded_benches() or []):
        f.why = f"{wb} is not installed in this FreeCAD"
        return
    got = win.workbench_selector(wb)
    if not got:
        f.why = "the workbench selector is hidden"
        f.text = f"View › Workbench › {title}"
        return
    hidden = win.visible(got)
    if hidden:
        f.why = f"the workbench selector is {hidden}"
        f.text = f"View › Workbench › {title}"
        return
    f.marks = [got]
    if win.active_workbench() == wb:
        f.note = "already active"


def _task(f, spec, win, _b):
    v = spec["task"]
    q = {"label": v} if isinstance(v, str) else dict(v)
    f.what = "task " + (q.get("label") or q.get("name") or q.get("button") or "?")
    if not win.task_open():
        f.why = "no task dialog is open"
        return
    got, note = win.task_widget(name=q.get("name"), label=q.get("label"), button=q.get("button"))
    if got is None:
        f.why = note or "not in the open task dialog"
        return
    hidden = win.visible(got)
    if hidden:
        f.why = f"in the task dialog but {hidden}"
        return
    f.marks = [got]
    if note:
        f.note = note


def _tree(f, spec, win, bindings):
    ref = bind(spec["tree"], bindings)
    if lessons.VAR.match(str(ref)):
        f.what = f"tree {ref}"
        f.why = f"nothing is bound to {ref}: name the object"
        return
    obj = win.obj(ref)
    f.what = f"tree {getattr(obj, 'Label', ref)}"
    if obj is None:
        f.why = f"no object {ref} in the document"
        return
    got, note = win.tree_row(obj)
    if got is None:
        f.why = note or "not in the Model tab"
        return
    if note == getattr(win, "MODEL_TAB", None) or (note or "").startswith("the Model tab is not in front"):
        f.text = "Open the Model tab."
    elif "which is folded" in (note or ""):
        f.text = "Unfold the ringed row in the tree (its arrow)."
    hidden = win.visible(got)
    if hidden:
        f.why = f"its row is {hidden}"
        return
    f.marks = [got]
    if note:
        f.note = note


def _of(f, spec, win, bindings):
    ref = bind(spec["of"], bindings)
    if lessons.VAR.match(str(ref)):
        f.why = f"nothing is bound to {ref}: name the object"
        return None
    obj = win.obj(ref)
    if obj is None:
        f.why = f"no object {ref} in the document"
    return obj


def _face(f, spec, win, bindings):
    obj = _of(f, spec, win, bindings)
    f.what = f"face of {getattr(obj, 'Label', spec['of'])}"
    if obj is None:
        return
    names, why = win.faces(obj, spec["face"])
    if not names:
        f.why = why or "no face matches"
        return
    f.light = (obj, names)
    f.what = f"{', '.join(names)} of {obj.Label}"


def _edge(f, spec, win, bindings):
    obj = _of(f, spec, win, bindings)
    f.what = f"edge of {getattr(obj, 'Label', spec['of'])}"
    if obj is None:
        return
    names, why = win.edges(obj, spec["edge"])
    if not names:
        f.why = why or "no edge matches"
        return
    f.light = (obj, names)
    f.what = f"{', '.join(names)} of {obj.Label}"


def _sub(f, spec, win, bindings):
    obj = _of(f, spec, win, bindings)
    f.what = f"{spec['sub']} of {getattr(obj, 'Label', spec['of'])}"
    if obj is None:
        return
    f.light = (obj, [spec["sub"]])


def _dock(f, spec, win, _b):
    title = spec["dock"]
    f.what = f"panel {title}"
    got, note = win.dock(title), None
    if isinstance(got, tuple):  # (the tab that brings it to the front, why)
        got, note = got
    if got is None:
        f.why = note or f"no panel {title}"
        return
    if note:
        # Inside a tab that is not in front (the Combo View's Model tab
        # holds the Property view): that tab ringed, and the words.
        f.note = note
        m = re.match(r"inside the (.+?) tab\b", note)
        if m:
            f.text = f"Open the {m.group(1)} tab."
    hidden = win.visible(got)
    if hidden:
        f.why = f"{title} is {'closed' if hidden == 'hidden' else hidden}"
        f.text = f"View › Panels › {title}"
        return
    f.marks = [got]


def _view(f, spec, win, _b):
    which = spec["view"]
    f.what = f"{which} view"
    if which != "3d":
        f.why = "views: 3d"
        return
    got = win.view3d()
    if got is None:
        f.why = "no 3D view open"
        return
    hidden = win.visible(got)
    if hidden:
        f.why = f"the 3D view is {hidden}"
        return
    f.marks = [got]


def _ext(f, spec, win, _b):
    f.what = f"{spec['ext']}"
    got = win.ext(spec)
    if not got:
        f.why = f"no add-on here shows {spec['ext']}"
        return
    if got.get("why"):
        f.why = got["why"]
        return
    f.marks = list(got.get("marks") or [])
    f.text = got.get("text")
    f.what = got.get("on") or f.what
    if f.marks:
        hidden = [win.visible(m) for m in f.marks]
        f.marks = [m for m, h in zip(f.marks, hidden) if h is None]
        if not f.marks:
            f.why = hidden[0]


RESOLVE = {"cmd": _cmd, "menu": _menu, "wb": _wb, "task": _task, "tree": _tree, "face": _face, "edge": _edge,
           "sub": _sub, "dock": _dock, "view": _view, "ext": _ext}
