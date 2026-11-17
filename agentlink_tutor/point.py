# SPDX-License-Identifier: LGPL-2.1-or-later
"""tutor_point: ring the window's controls for the person, with numbered
badges and one callout, through Agent Link's overlay ("overlay") and its 3D
annotation layer ("annotations"). Nothing here switches a workbench, opens
a menu, moves the cursor or takes focus: the person's hands stay on the
controls.

Each call replaces the highlights before it (clear: false keeps them);
a call with no targets clears them. A target that cannot be shown comes back
with why, and its words (a menu path, a command's name) join the callout.

Two things more, both so a target is never missing silently: a tree target
gets the Model tab brought to the front and its row scrolled into view
first, when the window allows it (Window.prepare_tree, tutor_point only;
"prepared" in the answer says what was done); and a face or edge lit in
the 3D view is asked first whether the view shows it (Window.light_seen):
off-screen or hidden under something else, it is still lit, but it comes
back in missing with why, and the callout says how to see it.
"""

import sys

from . import callout as callout_mod, lessons, targets

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


plain = callout_mod.plain


def parts(say, found):
    """The callout (callout.Callout): say (words, or a Callout already
    built for a lesson's step), then each missed or native target's words
    as the next numbered lines (callout.py lays them out)."""
    c = say if isinstance(say, callout_mod.Callout) else callout_mod.build(say)
    return callout_mod.merge(c, found)


def callout(say, found):
    """The callout's words as plain text (parts().text()), or None."""
    return parts(say, found).text()


_gen = {"n": 0}


def point(args, win, hooks=None, bindings=None, timer=None, bubble=None, report=None):
    """The tool's answer for args ({targets?, say?, ms?, clear?}). say may
    be a callout.Callout. bubble: bubble.py's show(callout, found) -> True
    when it showed the words itself (over the 3D view) and hide(); without
    it, or when it cannot, the overlay's own callout has them. The answer
    says which ("callout": bubble, overlay or none, with "callout_why" when
    the bubble could not); report, a dict, is filled the same way and kept
    up to date by the bubble's later self-check."""
    report = {} if report is None else report
    tg = args.get("targets") or []
    say = args.get("say")
    ms = args.get("ms")
    if not isinstance(tg, list):
        raise Refusal("invalid_input", "targets: a list of target specs, such as [{cmd: \"PartDesign_Pad\"}]")
    if len(tg) > MAX_TARGETS:
        raise Refusal("invalid_input", f"targets: at most {MAX_TARGETS} at once (this has {len(tg)}); ring the rest in a second call with clear: false")
    if ms is not None and (not isinstance(ms, int) or isinstance(ms, bool) or not 500 <= ms <= MS_MAX):
        raise Refusal("invalid_input", f"ms: 500 to {MS_MAX}, or leave it out to keep them until the next call")
    tg = [lessons.normal_target(spec) for spec in tg]
    for i, spec in enumerate(tg):
        try:
            lessons.target_kind(spec)
        except lessons.LessonError as e:
            raise Refusal("invalid_input", f"targets[{i}]: {e}")
    prepared = _prepare(tg, win, bindings)
    ov, ann = _services(hooks)
    keep = args.get("clear") is False and tg
    if not keep:
        if bubble is not None:
            try:
                bubble.hide()
            except Exception:  # noqa: BLE001
                pass
        if ov is not None:
            ov.clear(OWNER)
        if ann is not None:
            ann.clear(OWNER)
    _gen["n"] += 1
    if not tg:
        return {"cleared": True}
    found = [targets.resolve(spec, i + 1, win, bindings) for i, spec in enumerate(tg)]
    if ov is None:
        report["callout"] = "none"
        for f in found:
            f.marks, f.menu, f.light = [], None, None
            f.why = f.why or "nothing can be drawn: Agent Link's overlay is not here (no window, or an older Agent Link)"
        return {**_answer(found, None, ms, prepared), **report}
    # Faces and edges first: one the view does not show gets its words
    # into the callout (built next) and comes back in missing.
    for f in found:
        if f.light:
            _light(f, win, ov, ann)
    specs, owners = [], []
    for f in found:
        for m in f.marks:
            specs.append({**m, "badge": f.n})
            owners.append(f)
    words = parts(say, found)
    drawn = False
    report.pop("callout_why", None)
    if bubble is not None and not words.empty():
        try:
            doc = win.doc() if hasattr(win, "doc") else None
        except Exception:  # noqa: BLE001
            doc = None
        try:
            drawn = bool(bubble.show(words, found, doc=doc, report=report))
            if not drawn and getattr(bubble, "why", None) and bubble.why():
                report["callout_why"] = str(bubble.why())[:100]
        except Exception as e:  # noqa: BLE001  (the overlay's callout instead)
            drawn = False
            report["callout_why"] = f"bubble failed: {e}"[:100]
    report["callout"] = "none" if words.empty() else "bubble" if drawn else "overlay"
    if drawn and ms and hasattr(bubble, "hide_after"):
        bubble.hide_after(ms)
    got = ov.show(specs, say=None if drawn else words.text(), ms=ms, owner=OWNER) or {}
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
    if ms and ann is not None and timer is not None:
        n = _gen["n"]
        timer(ms, lambda: ann.clear(OWNER) if _gen["n"] == n else None)
    return {**_answer(found, got.get("handle"), ms, prepared), **report}


def _prepare(tg, win, bindings):
    """Each tree target's Model tab brought to the front and its row
    scrolled into view, where win has hands for it (prepare_tree); what was
    done, short lines."""
    prep = getattr(win, "prepare_tree", None)
    if not callable(prep):
        return []
    did = []
    for spec in tg:
        if "tree" not in spec:
            continue
        try:
            ref = targets.bind(spec["tree"], bindings)
            obj = win.obj(ref) if isinstance(ref, str) else None
            got = prep(obj) if obj is not None else None
        except Exception as e:  # noqa: BLE001  (the target still says why)
            got = f"not prepared: {e}"[:80]
        if got and got not in did:
            did.append(got)
    return did


def _light(f, win, ov, ann):
    """f's faces or edges lit through the annotation layer; asked first
    whether the view shows them (win.light_seen). Not shown: still lit (the
    person may turn the view), but f.unseen says why, f goes to missing and
    the callout says how to see it."""
    if ann is None:
        f.why, f.light = "no 3D annotation layer in this Agent Link", None
        return
    obj, subs = f.light
    seen = getattr(win, "light_seen", None)
    unseen = None
    if callable(seen):
        try:
            unseen = seen(obj, subs)
        except Exception as e:  # noqa: BLE001  (cannot be told: drawn as before)
            sys.stderr.write(f"Tutor: whether {', '.join(subs)} shows could not be told ({e})\n")
            unseen = None
    colour = "#3f93e0"
    try:
        colour = ov.colours().get("accent", colour)
    except Exception:
        pass
    try:  # numbered in the view too (an older Agent Link draws no number)
        r = ann.light(obj, subs, owner=OWNER, colour=colour, badge=f.n) or {}
    except TypeError:
        r = ann.light(obj, subs, owner=OWNER, colour=colour) or {}
    if not r.get("lit"):
        f.light = None
        f.why = "; ".join(f"{s}: {w}" for s, w in (r.get("missing") or [])) or "nothing lit"
        return
    if r.get("missing"):
        f.note = "not lit: " + ", ".join(s for s, _w in r["missing"])
    if unseen:
        f.unseen = unseen
        f.why = f"lit, but not seen: {unseen}"
        f.text = see_words(unseen, f.n, win, "edge" if f.kind == "edge" else "face")


def see_words(why, n, win=None, what="face"):
    """The callout's step for a lit face or edge the view does not show."""
    from . import words as words_mod

    b = words_mod.badge(n)
    if why.startswith("off-screen"):
        keys = None
        try:
            keys = (win.command_info("Std_ViewFitAll") or {}).get("shortcut") if win is not None else None
        except Exception:  # noqa: BLE001
            keys = None
        return f"Push Fit all{f' ({keys})' if keys else ''} to see the lit {what} {b}."
    if why.startswith("hidden"):
        return f"Turn the 3D view to see the lit {what} {b}."
    return f"Open the 3D view of the part to see the lit {what} {b}."


def _answer(found, handle, ms, prepared=()):
    shown = [f.answer() for f in found if f.shown()]
    missing = [f.answer() for f in found if not f.shown()]
    for a in shown:
        a.pop("why", None)
    out = {"shown": shown, "missing": missing}
    if prepared:
        out["prepared"] = list(prepared)
    out["until"] = f"{ms} ms" if ms else "the next tutor_point"
    if not shown and missing:
        out["note"] = "nothing ringed; any words for them are in the callout"
    return out
