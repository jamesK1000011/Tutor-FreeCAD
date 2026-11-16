# SPDX-License-Identifier: LGPL-2.1-or-later
"""The callout's words, laid out the same way for every lesson and for the
agent's tutor_point:

    1. Select the top face of the block.        the instruction, one line
    2. Push New Sketch.                         per sentence, numbered when
    3. Open the ▾ menu of the ringed button ②.  there is more than one line;
       Select New Sketch.                       a target's own words go on
                                                as the next numbers
    A sketch on this face sets where …          the why line: its own
                                                paragraph, smaller and dimmer
    Not yet: no new sketch yet.                 a hint, or why it is not done
                                                (only once the person acted)

A single line has no number, so there is never a "2." without a "1.".
Markdown emphasis is taken off (the callout is painted text). text() is
the plain form (paragraphs apart by an empty line) for Agent Link's overlay;
html() the rich form for the Tutor's own bubble (bubble.py), where the why
line is smaller and dimmer.

place() puts the bubble over the 3D view, under the toolbars, where it
covers no toolbar or dock but the one it points at, with its arrow to the
ring. Plain Python: tested without Qt.
"""
import html as _html
import re

_MARK = re.compile(r"(\*\*|__)(.+?)\1|`([^`]+)`")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9▾①-⑨\"'(*_`])")


def plain(text):
    """Markdown emphasis taken off: **Pad**, __Pad__ and `Pad` read as Pad."""
    return _MARK.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(3), str(text))


def sentences(text):
    t = " ".join(str(text or "").split())
    return [s for s in _SENT.split(t) if s.strip()] if t else []


def _verbs():
    try:
        from . import ste

        r = ste.rules()
        return {v.lower() for v in r.get("action_verbs", [])} | {v.lower() for v in r.get("not_for_buttons", {})}
    except Exception:  # noqa: BLE001
        return {"select", "push", "click", "set", "type", "open", "draw", "make", "use", "press"}


def _instruction(sentence):
    first = re.match(r"[A-Za-z-]+", plain(sentence).strip())
    return bool(first) and first.group(0).lower() in _verbs()


class Callout:
    """steps: the instruction's lines (and the targets' words) in order;
    why: the explainer; notes: a hint, why not yet, "Done. Push Next."."""

    def __init__(self, steps=(), why=None, notes=(), numbered=None):
        self.steps = [plain(s).strip() for s in steps if s and str(s).strip()]
        self.why = plain(why).strip() if why and str(why).strip() else None
        self.notes = [plain(n).strip() for n in notes if n and str(n).strip()]
        self._numbered = numbered

    @property
    def numbered(self):
        if self._numbered is not None:
            return self._numbered and len(self.steps) > 1
        return len(self.steps) > 1

    def lines(self):
        if not self.numbered:
            return list(self.steps)
        return [f"{i}. {s}" for i, s in enumerate(self.steps, 1)]

    def add_steps(self, more):
        """A copy with more lines after the instruction (the targets' words)."""
        more = [m for m in more if m]
        c = Callout(self.steps + more, self.why, self.notes, self._numbered or (True if more else None))
        return c

    def empty(self):
        return not (self.steps or self.why or self.notes)

    def text(self):
        """Plain text: the lines, then the why line and the notes, each its
        own paragraph."""
        paras = ["\n".join(self.lines())] if self.steps else []
        if self.why:
            paras.append(self.why)
        paras += self.notes
        return "\n\n".join(p for p in paras if p) or None

    def html(self, text_colour="#1d1f23", dim_colour="#6a6f78"):
        """Rich text for the Tutor's bubble: a numbered list when numbered,
        the why line smaller and dimmer in its own paragraph."""
        esc = _html.escape
        out = []
        if self.steps:
            if self.numbered:
                rows = "".join(
                    f'<tr><td style="padding-right:6px" align="right">{i}.</td><td>{esc(s)}</td></tr>'
                    for i, s in enumerate(self.steps, 1))
                out.append(f'<table cellspacing="0" cellpadding="1">{rows}</table>')
            else:
                out.append(f"<p style=\"margin:0\">{esc(self.steps[0])}</p>")
        if self.why:
            out.append(f'<p style="margin-top:6px; margin-bottom:0; font-size:small; color:{dim_colour}">{esc(self.why)}</p>')
        for n in self.notes:
            out.append(f'<p style="margin-top:6px; margin-bottom:0">{esc(n)}</p>')
        return f'<div style="color:{text_colour}">' + "".join(out) + "</div>"

    def __str__(self):
        return self.text() or ""


def build(say=None, why=None, notes=(), extra=()):
    """A Callout from a step's (or the agent's) words: each sentence of say
    one line; numbered when there is more than one line and they are steps
    (each starts with an action verb) or a target adds its own."""
    sents = sentences(say)
    extra = [e for e in extra or () if e]
    numbered = None
    if not extra and len(sents) > 1 and not all(_instruction(s) for s in sents):
        sents = [" ".join(sents)]  # a description: one paragraph, no numbers
    if extra:
        numbered = True
    return Callout(sents + extra, why, notes, numbered)


# ---- where the bubble goes (no Qt) ---------------------------------------------------

MARGIN = 10  # px from the 3D view's edges
ARROW = 9  # px: the arrow's length
CUBE = (150, 150)  # the navigation cube's corner (top right) kept clear where there is room
WIDTH = 340


def _clamp(v, lo, hi):
    return max(lo, min(v, hi)) if hi >= lo else lo


def place(view, size, target=None, keep_clear=()):
    """(x, y, side, tip) of a bubble of size (w, h) inside view (x, y, w, h),
    all in one coordinate space (the main window's px).

    The bubble sits over the 3D view, so it covers no toolbar, dock or
    panel. It goes on the view's edge nearest the target (a ring in the
    toolbars above: the top edge, under it; a dock at the left: the left
    edge), slid along that edge to line up with the target, kept off the
    navigation cube's corner and the rects in keep_clear where it can.
    side: where the arrow points ("up", "left", "right", "down", or None for
    no target or one inside the view); tip: the arrow's point (x, y), on
    the bubble's edge, as near the target as the bubble allows."""
    vx, vy, vw, vh = view
    bw, bh = size
    bw, bh = min(bw, vw - 2 * MARGIN), min(bh, vh - 2 * MARGIN)
    lo_x, hi_x = vx + MARGIN, vx + vw - MARGIN - bw
    lo_y, hi_y = vy + MARGIN + ARROW, vy + vh - MARGIN - bh
    cube = (vx + vw - CUBE[0], vy, CUBE[0], CUBE[1])
    clear = [cube] + [tuple(r) for r in keep_clear or ()]

    def overlaps(x, y):
        return sum(_overlap((x, y, bw, bh), r) for r in clear)

    if target is None:
        x, y = _clamp(vx + (vw - bw) // 2, lo_x, hi_x), lo_y
        return (x, y, None, None)
    tx, ty, tw, th = target
    cx, cy = tx + tw / 2.0, ty + th / 2.0
    inside = vx <= cx <= vx + vw and vy <= cy <= vy + vh
    if inside:
        # A face or edge in the view: the top edge, on the side away from it.
        x = _clamp(int(vx + MARGIN if cx > vx + vw / 2.0 else vx + vw - MARGIN - bw), lo_x, hi_x)
        if overlaps(x, lo_y):
            x = lo_x if x != lo_x else hi_x
        return (x, lo_y, None, None)
    if cy < vy:
        side = "up"
    elif cy > vy + vh:
        side = "down"
    elif cx < vx:
        side = "left"
    else:
        side = "right"
    if side in ("up", "down"):
        y = lo_y if side == "up" else vy + vh - MARGIN - ARROW - bh
        x = _clamp(int(cx - bw / 2.0), lo_x, hi_x)
        if overlaps(x, y):
            # Slide away from the cube (or what else must stay clear).
            left = _clamp(min(int(cx - bw / 2.0), cube[0] - bw - MARGIN), lo_x, hi_x)
            x = left if overlaps(left, y) < overlaps(x, y) else x
        tip = (_clamp(int(cx), x + 12, x + bw - 12), y - ARROW if side == "up" else y + bh + ARROW)
        return (x, y, side, tip)
    x = vx + MARGIN + ARROW if side == "left" else vx + vw - MARGIN - ARROW - bw
    y = _clamp(int(cy - bh / 2.0), lo_y, hi_y)
    if overlaps(x, y):
        y = _clamp(cube[1] + cube[3] + MARGIN, lo_y, hi_y)
    tip = (x - ARROW if side == "left" else x + bw + ARROW, _clamp(int(cy), y + 10, y + bh - 10))
    return (x, y, side, tip)


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    w = min(ax + aw, bx + bw) - max(ax, bx)
    h = min(ay + ah, by + bh) - max(ay, by)
    return max(0, w) * max(0, h)
