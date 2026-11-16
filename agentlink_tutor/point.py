# SPDX-License-Identifier: LGPL-2.1-or-later
"""tutor_point: ring the window's controls for the person, with numbered
badges and one callout, through Agent Link's overlay ("overlay") and its 3D
annotation layer ("annotations"). Nothing here switches a workbench, opens
a menu, moves the cursor or takes focus: the person's hands stay on the
controls.

Each call replaces the highlights before it (clear: false keeps them);
a call with no targets clears them. A target that cannot be shown comes back
with why, and its words (a menu path, a command's name) join the callout.
"""

import re

from . import lessons, targets

OWNER = "tutor"
MS_MAX = 120000
MAX_TARGETS = 6


class Refusal(Exception):
    """Agent Link turns this into a refusal the agent can act on."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _services(hooks):
    if hooks is None:
        return None, None
    return hooks.service("overlay"), hooks.service("annotations")


_MARK = re.compile(r"(\*\*|__)(.+?)\1|`([^`]+)`")


def plain(text):
    """Markdown emphasis taken off (the callout is painted text): **Pad**,
    __Pad__ and `Pad` read as Pad."""
    return _MARK.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(3), str(text))


def callout(say, found):
    """The callout's words: say, then each missed or native target's words
    with its badge number. Markdown emphasis is taken off."""
    say = plain(say) if say else say
    lines = [str(say).strip()] if say and str(say).strip() else []
    for f in found:
        if f.text:
            lines.append(f"{f.n}. {f.text}")
    return "\n".join(lines) or None


_gen = {"n": 0}


def point(args, win, hooks=None, bindings=None, timer=None):
    """The tool's answer for args ({targets?, say?, ms?, clear?})."""
    tg = args.get("targets") or []
    say = args.get("say")
    ms = args.get("ms")
    if not isinstance(tg, list):
        raise Refusal("invalid_input", "targets: a list of target specs, such as [{cmd: \"PartDesign_Pad\"}]")
    if len(tg) > MAX_TARGETS:
        raise Refusal("invalid_input", f"targets: at most {MAX_TARGETS} at once")
    if ms is not None and (not isinstance(ms, int) or isinstance(ms, bool) or not 500 <= ms <= MS_MAX):
        raise Refusal("invalid_input", f"ms: 500 to {MS_MAX}, or leave it out to keep them until the next call")
    tg = [lessons.normal_target(spec) for spec in tg]
    for i, spec in enumerate(tg):
        try:
            lessons.target_kind(spec)
        except lessons.LessonError as e:
            raise Refusal("invalid_input", f"targets[{i}]: {e}")
    ov, ann = _services(hooks)
    keep = args.get("clear") is False and tg
    if not keep:
        if ov is not None:
            ov.clear(OWNER)
        if ann is not None:
            ann.clear(OWNER)
    _gen["n"] += 1
    if not tg:
        return {"cleared": True}
    found = [targets.resolve(spec, i + 1, win, bindings) for i, spec in enumerate(tg)]
    if ov is None:
        for f in found:
            f.marks, f.menu, f.light = [], None, None
            f.why = f.why or "nothing can be drawn: Agent Link's overlay is not here (no window, or an older Agent Link)"
        return _answer(found, None, ms)
    specs, owners = [], []
    for f in found:
        for m in f.marks:
            specs.append({**m, "badge": f.n})
            owners.append(f)
    got = ov.show(specs, say=callout(say, found), ms=ms, owner=OWNER) or {}
    hidden = dict(got.get("hidden") or [])
    for f in found:
        mine = [i for i, g in enumerate(owners) if g is f]
        hid = [hidden[i] for i in mine if i in hidden]
        if mine and len(hid) == len(mine):
            # Kept on the overlay (drawn as soon as it shows), said now.
            f.marks = []
            f.why = f.why or f"it is {hid[0]}"
        if f.dropdown and f.marks and hasattr(ov, "watch_menu"):
            menu, action = f.dropdown
            ov.watch_menu(menu, action, owner=OWNER, handle=got.get("handle"), badge=f.n)
        if f.menu:
            r = ov.menu(f.menu, badge=f.n, owner=OWNER, handle=got.get("handle")) or {}
            if r.get("native"):
                f.menu = None
                f.note = "menu: native"
                f.why = f.why or "the macOS menubar cannot be drawn over; the path is in the callout"
            elif r.get("missing"):
                f.menu = None
                f.why = f.why or f"no menu item {r['missing']!r}"
            elif r.get("why"):
                f.menu = None
                f.why = f.why or r["why"]
        if f.light:
            if ann is None:
                f.why, f.light = "no 3D annotation layer in this Agent Link", None
                continue
            colour = "#3f93e0"
            try:
                colour = ov.colours().get("accent", colour)
            except Exception:
                pass
            obj, subs = f.light
            try:  # numbered in the view too (an older Agent Link draws no number)
                r = ann.light(obj, subs, owner=OWNER, colour=colour, badge=f.n) or {}
            except TypeError:
                r = ann.light(obj, subs, owner=OWNER, colour=colour) or {}
            if not r.get("lit"):
                f.light = None
                f.why = "; ".join(f"{s}: {w}" for s, w in (r.get("missing") or [])) or "nothing lit"
            elif r.get("missing"):
                f.note = "not lit: " + ", ".join(s for s, _w in r["missing"])
    if ms and ann is not None and timer is not None:
        n = _gen["n"]
        timer(ms, lambda: ann.clear(OWNER) if _gen["n"] == n else None)
    return _answer(found, got.get("handle"), ms)


def _answer(found, handle, ms):
    shown = [f.answer() for f in found if f.shown()]
    missing = [f.answer() for f in found if not f.shown()]
    for a in shown:
        a.pop("why", None)
    out = {"shown": shown, "missing": missing}
    out["until"] = f"{ms} ms" if ms else "the next tutor_point"
    if not shown and missing:
        out["note"] = "nothing ringed; any words for them are in the callout"
    return out
