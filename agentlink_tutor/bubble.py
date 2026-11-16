# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Tutor's callout bubble over the lesson's 3D view: the step's words
(callout.py) in rich text, the why line smaller and dimmer, with an arrow
toward the ring.

It is built as Agent Link's caption is (a QLabel child of the 3D view's
window, styled by its own stylesheet), which paints over the view on the
Mac where Agent Link's overlay cannot. It takes no mouse, no keys and no
focus, and uses the application's font (no family is named). callout.place()
puts it on the view's edge nearest the ring, so it covers no toolbar, dock
or panel.

show() parents it to the view of the lesson's own document, and only when
that view is the window's front tab. It then checks itself: the label is
visible, has a size, lies inside the view and is what the window shows
there (again a moment later, after the window has settled). When any of
that fails it is hidden, and the words go to Agent Link's overlay callout:
show() answers False, why() says why, and a later failure updates the
report the caller passed ({"callout": "overlay", "callout_why": …}).

    bubble.show(callout, found, doc=None, report=None) -> True when shown
    bubble.hide()
"""
import sys

from . import callout as callout_mod

PAD = 9
RECHECK_MS = (400, 1500)
ARROWS = {"up": "▲", "down": "▼", "left": "◀", "right": "▶",
          "up-left": "◤", "up-right": "◥", "down-left": "◣", "down-right": "◢"}
_STATE = {"w": None, "a": None, "host": None, "gen": 0, "why": None}


def _qt():
    from PySide import QtCore, QtGui

    QtW = getattr(__import__("PySide", fromlist=["QtWidgets"]), "QtWidgets", QtGui)
    return QtCore, QtGui, QtW


def _flag(QtCore, name):
    v = getattr(QtCore.Qt, name, None)
    if v is None:
        for group in ("WidgetAttribute", "FocusPolicy", "TextFormat", "AlignmentFlag"):
            v = getattr(getattr(QtCore.Qt, group, None), name, None)
            if v is not None:
                break
    return v


def why():
    """Why the last show() did not show the bubble (None when it did)."""
    return _STATE["why"]


def _cls(w):
    try:
        return w.metaObject().className()
    except Exception:  # noqa: BLE001
        return type(w).__name__


def subwindow_title_matches(title, label):
    """True when an MDI tab's title is a view of the document labelled
    label ("PocketLesson : 1", "PocketLesson : 1[*]")."""
    t = str(title or "").replace("[*]", "")
    return t == label or t.startswith(label + " : ")


def view_widget(doc=None):
    """(the 3D view widget of doc (else of the front tab), None) when it is
    the window's front tab; else (None, why)."""
    import FreeCADGui

    _QtCore, _QtGui, QtW = _qt()
    mw = FreeCADGui.getMainWindow()
    area = mw.findChild(QtW.QMdiArea) if mw is not None else None
    if area is None:
        return None, "no 3D view area"
    # currentSubWindow, not activeSubWindow: the latter is None while the
    # window is in the background, as the person's window often is.
    cur = area.currentSubWindow() or area.activeSubWindow()
    if doc is not None:
        label = getattr(doc, "Label", None) or getattr(doc, "Name", "")
        mine = [s for s in area.subWindowList() if subwindow_title_matches(s.windowTitle(), label)
                and s.widget() is not None and "View3D" in _cls(s.widget())]
        if not mine:
            return None, f"{label} has no 3D view open"
        if cur not in mine:
            return None, f"{label}'s 3D view is not the front tab"
    w = cur.widget() if cur is not None else None
    if w is None or "View3D" not in _cls(w):
        return None, "no 3D view in front"
    if not w.isVisible():
        return None, "the 3D view is hidden"
    return w, None


def _point(x, y):
    QtCore, _QtGui, _QtW = _qt()
    return QtCore.QPoint(int(x), int(y))


def target_rect(found, mw):
    """The first ringed target's rect in the main window's px; for a face
    or edge lit in the view, None (callout.place keeps to the top edge)."""
    for f in found or ():
        for m in getattr(f, "marks", None) or ():
            w = m.get("widget") if isinstance(m, dict) else None
            if w is None:
                continue
            try:
                if not w.isVisible():
                    continue
                rect = m.get("rect")
                if callable(rect):
                    r = rect()
                    port = m.get("viewport") or w
                    p = port.mapTo(mw, _point(r[0], r[1]))
                    return (p.x(), p.y(), int(r[2]), int(r[3]))
                p = w.mapTo(mw, _point(0, 0))
                return (p.x(), p.y(), w.width(), w.height())
            except Exception:  # noqa: BLE001
                continue
    return None


def _mix(a, b, t):
    """Colour a toward b by t (0..1), as #rrggbb."""
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{int(round(x + (y - x) * t)):02x}" for x, y in zip(ca, cb))


def colours(col=None):
    """{fill, text, dim, edge} from the overlay's colours (the theme's)."""
    if col is None:
        try:
            from agentlink import hooks

            ov = hooks.service("overlay")
            col = ov.colours() if ov is not None else {}
        except Exception:  # noqa: BLE001
            col = {}
    fill = col.get("bubble", "#26292e")
    text = col.get("bubble_text", "#f2f2f2")
    if contrast(text, fill) < TEXT_CONTRAST:
        # A theme whose bubble colours read badly: black or white, whichever
        # stands out more from the fill.
        text = max(("#000000", "#ffffff"), key=lambda c: contrast(c, fill))
    # The why line dimmer than the words, never below the contrast the
    # words need (WCAG AA for small text: 4.5:1).
    t = 0.35
    dim = _mix(text, fill, t)
    while contrast(dim, fill) < TEXT_CONTRAST and t > 0:
        t = round(t - 0.05, 2)
        dim = _mix(text, fill, max(t, 0))
    edge = col.get("accent", "#3f93e0")
    if contrast(edge, fill) < EDGE_CONTRAST:
        edge = text  # the edge must show against the fill (3:1 for graphics)
    return {"fill": fill, "text": text, "dim": dim, "edge": edge}


TEXT_CONTRAST = 4.5  # WCAG 2 AA, normal text
EDGE_CONTRAST = 3.0  # WCAG 2 AA, graphics and a control's edge


def luminance(c):
    """Relative luminance of #rrggbb (WCAG 2)."""
    c = c.lstrip("#")
    out = []
    for i in (0, 2, 4):
        v = int(c[i:i + 2], 16) / 255.0
        out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a, b):
    """The contrast ratio of two colours, 1 to 21 (WCAG 2)."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def stylesheet(col):
    """The label's own stylesheet: colours, edge and padding only. No font
    family is named (the application's font is set on the label)."""
    return (f"QLabel#TutorCallout {{ background: {col['fill']}; color: {col['text']}; border: 2px solid {col['edge']}; "
            f"border-radius: 6px; padding: {PAD}px; }}")


def arrow_sheet(col):
    return f"QLabel#TutorCalloutArrow {{ background: transparent; color: {col['edge']}; border: none; padding: 0px; }}"


def inside(r, area):
    x, y, w, h = r
    ax, ay, aw, ah = area
    return w > 0 and h > 0 and x >= ax and y >= ay and x + w <= ax + aw and y + h <= ay + ah


def verify(w, host, mw):
    """None when w shows over host as meant, else why not."""
    try:
        if w is None or host is None:
            return "gone"
        if not host.isVisible():
            return "its 3D view was hidden"
        if not w.isVisible():
            return "not visible"
        g = w.geometry()
        r = (g.x(), g.y(), g.width(), g.height())
        if not inside(r, (0, 0, host.width(), host.height())):
            return f"placed outside its 3D view ({r[0]}, {r[1]}, {r[2]} × {r[3]})"
        # What the window shows under the bubble's middle is its own 3D view
        # (the bubble takes no mouse, so childAt sees through it).
        at = mw.childAt(w.mapTo(mw, _point(r[2] // 2, r[3] // 2))) if mw is not None else None
        while at is not None and at is not host:
            at = at.parentWidget()
        if at is not host:
            return "covered: its 3D view is not what the window shows there"
    except RuntimeError:
        return "its 3D view was closed"
    return None


SAMPLE = (48, 12)  # the bubble's picture and the window's, compared at this size
MATCH = 40.0  # mean difference per colour channel (0-255) under which they agree


def mean_diff(a, b):
    """Mean absolute difference per channel of two equal lists of (r, g, b)."""
    if not a or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for p, q in zip(a, b) for x, y in zip(p, q)) / (3.0 * len(a))


def _samples(img):
    QtCore, QtGui, _QtW = _qt()
    ignore = _flag(QtCore, "IgnoreAspectRatio")
    smooth = _flag(QtCore, "SmoothTransformation")
    small = img.scaled(SAMPLE[0], SAMPLE[1], ignore, smooth)
    out = []
    for y in range(small.height()):
        for x in range(small.width()):
            c = QtGui.QColor(small.pixel(x, y))
            out.append((c.red(), c.green(), c.blue()))
    return out


def painted(lab, mw):
    """True when the window's picture (Agent Link's grab_window, the one
    window_snapshot and gui_input's shots use: the widgets, with the 3D view
    rendered into its place and what is stacked over it put back) shows the
    bubble where it stands; False when it shows something else there; None
    when it cannot be told (an Agent Link without grab_window)."""
    try:
        from agentlink.grab import grab_window
    except ImportError:
        return None
    QtCore, _QtGui, _QtW = _qt()
    pix = grab_window(mw)
    ratio = pix.devicePixelRatio() if hasattr(pix, "devicePixelRatio") else 1.0
    p = lab.mapTo(mw, _point(0, 0))
    r = QtCore.QRect(int(p.x() * ratio), int(p.y() * ratio), int(lab.width() * ratio), int(lab.height() * ratio))
    there = _samples(pix.copy(r).toImage())
    own = _samples(lab.grab().toImage())
    return mean_diff(there, own) < MATCH


def arrow_at(side, tip, size):
    """Where the arrow label goes (its top-left) for side and tip: on an edge
    its point at tip; at a corner it sits on the corner, pointing out."""
    tx, ty = tip
    aw, ah = size
    return {"up": (tx - aw // 2, ty), "down": (tx - aw // 2, ty - ah),
            "left": (tx, ty - ah // 2), "right": (tx - aw, ty - ah // 2),
            "up-left": (tx - aw // 3, ty - ah + ah // 3), "up-right": (tx - aw + aw // 3, ty - ah + ah // 3),
            "down-left": (tx - aw // 3, ty - ah // 3), "down-right": (tx - aw + aw // 3, ty - ah // 3)}[side]


def show(c, found=(), doc=None, report=None):
    """Show callout c (callout.Callout) over doc's 3D view (else the front
    one), its arrow toward the first ringed target. False, with why(), when
    it cannot be shown there and seen."""
    _STATE["why"] = None
    try:
        import FreeCADGui
    except ImportError:
        _STATE["why"] = "no window"
        return False
    host, why_not = view_widget(doc)
    if host is None:
        hide()
        _STATE["why"] = why_not
        return False
    _QtCore, QtGui, QtW = _qt()
    mw = FreeCADGui.getMainWindow()
    lab, arrow = _widgets(host)
    col = colours()
    lab.setStyleSheet(stylesheet(col))
    arrow.setStyleSheet(arrow_sheet(col))
    from . import prefs

    font = QtGui.QFont(QtW.QApplication.font())
    if font.pointSizeF() > 0:
        font.setPointSizeF(prefs.scaled(font.pointSizeF()))  # the person's text size
    lab.setFont(font)
    arrow.setFont(QtGui.QFont(font))
    lab.setText(c.html(col["text"], col["dim"]))
    lab.setAccessibleDescription(c.text() or "")
    width = min(int(callout_mod.WIDTH * prefs.text_scale() / 100), max(160, host.width() - 2 * callout_mod.MARGIN))
    # The size from these words alone: the last showing's fixed size let go
    # first (a why line turned off left its height, an empty band).
    lab.setMinimumSize(0, 0)
    lab.setMaximumSize(16777215, 16777215)
    lab.setFixedWidth(width)
    hfw = lab.heightForWidth(width)
    bh = max(hfw if hfw > 0 else lab.sizeHint().height(), 1)
    lab.setFixedHeight(bh)
    hp = host.mapTo(mw, _point(0, 0))
    view = (hp.x(), hp.y(), host.width(), host.height())
    x, y, side, tip = callout_mod.place(view, (width, bh), target_rect(found, mw))
    lab.move(int(x - view[0]), int(y - view[1]))
    lab.show()
    lab.raise_()
    if side and tip:
        arrow.setText(ARROWS[side])
        arrow.adjustSize()
        aw, ah = arrow.width(), arrow.height()
        tx, ty = tip[0] - view[0], tip[1] - view[1]
        ax, ay = arrow_at(side, (tx, ty), (aw, ah))
        arrow.move(int(ax), int(ay))
        arrow.show()
        arrow.raise_()
    else:
        arrow.hide()
    _STATE["gen"] += 1
    bad = verify(lab, host, mw)
    if bad:
        hide()
        _STATE["why"] = f"bubble {bad}"
        return False
    _recheck_later(c, report)
    return True


def _recheck_later(c, report):
    """A moment later (the window settled, a tab may have come up in front):
    still seen, else hidden and the words given to the overlay's callout."""
    QtCore, _QtGui, _QtW = _qt()
    gen = _STATE["gen"]

    checked = {"pixels": False}

    def again():
        if _STATE["gen"] != gen:
            return
        try:
            import FreeCADGui

            mw = FreeCADGui.getMainWindow()
            bad = verify(_STATE["w"], _STATE["host"], mw)
            if not bad and not checked["pixels"]:
                checked["pixels"] = True  # once a showing: the grab renders the 3D view
                seen = painted(_STATE["w"], mw)
                if seen is False:
                    bad = "not in the window's picture where it stands"
                elif seen and report is not None:
                    report["callout_seen"] = "pixels"
        except Exception as e:  # noqa: BLE001
            bad = f"not checked ({e})"
        if _STATE["gen"] != gen:
            return  # shown again or hidden meanwhile (the grab ran the event loop)
        if not bad:
            return
        hide()
        _STATE["gen"] += 1
        _STATE["why"] = f"bubble {bad}"
        sys.stderr.write(f"Tutor: callout bubble {bad}; the overlay's callout has the words\n")
        try:
            from agentlink import hooks

            from . import point

            ov = hooks.service("overlay")
            if ov is not None and c.text():
                ov.show([], say=c.text(), owner=point.OWNER)
                if report is not None:
                    report.update(callout="overlay", callout_why=_STATE["why"])
            elif report is not None:
                report.update(callout="none", callout_why=_STATE["why"])
        except Exception:  # noqa: BLE001
            pass

    for ms in RECHECK_MS:
        QtCore.QTimer.singleShot(int(ms), again)


def hide():
    _STATE["gen"] += 1  # a self-check still waiting is called off
    for key in ("w", "a"):
        w = _STATE[key]
        if w is None:
            continue
        try:
            w.hide()
        except RuntimeError:  # its 3D view was closed
            _STATE[key] = None


def hide_after(ms):
    """Hide in ms unless shown again meanwhile (tutor_point's ms)."""
    QtCore, _QtGui, _QtW = _qt()
    gen = _STATE["gen"]
    QtCore.QTimer.singleShot(int(ms), lambda: hide() if _STATE["gen"] == gen else None)


def _widgets(host):
    """The callout label and its arrow, children of host (made again when
    the view changed or was closed)."""
    QtCore, _QtGui, QtW = _qt()
    lab, arrow = _STATE["w"], _STATE["a"]
    try:
        if lab is not None and arrow is not None and lab.parent() is host and arrow.parent() is host:
            return lab, arrow
    except RuntimeError:
        pass
    for w in (lab, arrow):
        try:
            if w is not None:
                w.hide()
                w.deleteLater()
        except RuntimeError:
            pass
    rich = _flag(QtCore, "RichText")
    nofocus = _flag(QtCore, "NoFocus")
    through = _flag(QtCore, "WA_TransparentForMouseEvents")
    lab, arrow = QtW.QLabel(host), QtW.QLabel(host)
    lab.setObjectName("TutorCallout")
    arrow.setObjectName("TutorCalloutArrow")
    lab.setAccessibleName("Tutor step")
    lab.setWordWrap(True)
    top = _flag(QtCore, "AlignTop")
    left = _flag(QtCore, "AlignLeft")
    if top is not None and left is not None:
        lab.setAlignment(top | left)  # any spare height below the words, never above
    if rich is not None:
        lab.setTextFormat(rich)
    for w in (lab, arrow):
        if through is not None:
            w.setAttribute(through, True)
        if nofocus is not None:
            w.setFocusPolicy(nofocus)
    _STATE.update(w=lab, a=arrow, host=host)
    return lab, arrow
