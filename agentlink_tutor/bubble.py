# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Tutor's callout bubble over the 3D view: the step's words (callout.py)
in rich text, the why line smaller and dimmer, with an arrow to the ring.

It is a child of the 3D view's window (as Agent Link's caption is), so it
draws over the view on every platform (Agent Link's overlay cannot: the
view's GL surface paints over it). There it covers no toolbar, dock or
panel; callout.place() puts it on the view's edge nearest the ring (under
the toolbars for a toolbar button, at the left edge for the Tasks panel).
It takes no mouse, no keys and no focus. When there is no 3D view (Start
page, a TechDraw page) show() answers False and the overlay's own callout
has the words.

    bubble.show(callout, found) -> True when shown
    bubble.hide()
"""
import sys

from . import callout as callout_mod

PAD = 9
RADIUS = 6
_STATE = {"w": None, "gen": 0}


def _qt():
    from PySide import QtCore, QtGui

    QtW = getattr(__import__("PySide", fromlist=["QtWidgets"]), "QtWidgets", QtGui)
    return QtCore, QtGui, QtW


def _flag(QtCore, name):
    v = getattr(QtCore.Qt, name, None)
    if v is None:
        for group in ("WidgetAttribute", "FocusPolicy", "GlobalColor"):
            v = getattr(getattr(QtCore.Qt, group, None), name, None)
            if v is not None:
                break
    return v


def view_widget():
    """The 3D view in front (the MDI area's active window's widget), or None."""
    import FreeCADGui

    _QtCore, _QtGui, QtW = _qt()
    mw = FreeCADGui.getMainWindow()
    area = mw.findChild(QtW.QMdiArea) if mw is not None else None
    sub = area.activeSubWindow() if area is not None else None
    w = sub.widget() if sub is not None else None
    if w is None or not w.isVisible():
        return None
    try:
        cls = w.metaObject().className()
    except Exception:  # noqa: BLE001
        cls = type(w).__name__
    return w if "View3D" in cls else None


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


def _colours():
    try:
        from agentlink import hooks

        ov = hooks.service("overlay")
        col = ov.colours() if ov is not None else {}
    except Exception:  # noqa: BLE001
        col = {}
    fill = col.get("bubble", "#26292e")
    text = col.get("bubble_text", "#f2f2f2")
    return {"fill": fill, "text": text, "dim": _mix(text, fill, 0.35), "edge": col.get("accent", "#3f93e0")}


def show(c, found=()):
    """Show callout c (callout.Callout) over the 3D view, its arrow to the
    first ringed target. False when there is no 3D view to show it on."""
    try:
        import FreeCADGui
    except ImportError:
        return False
    host = view_widget()
    if host is None:
        hide()
        return False
    mw = FreeCADGui.getMainWindow()
    w = _widget(host)
    col = _colours()
    w.set_text(c.html(col["text"], col["dim"]), col)
    bw, bh = w.natural_size()
    hp = host.mapTo(mw, _point(0, 0))
    view = (hp.x(), hp.y(), host.width(), host.height())
    x, y, side, tip = callout_mod.place(view, (bw, bh), target_rect(found, mw))
    w.put(x - view[0], y - view[1], bw, bh, side, None if tip is None else (tip[0] - view[0], tip[1] - view[1]))
    _STATE["gen"] += 1
    return True


def hide():
    w = _STATE["w"]
    if w is None:
        return
    try:
        w.hide()
    except RuntimeError:  # its 3D view was closed
        _STATE["w"] = None


def hide_after(ms):
    """Hide in ms unless shown again meanwhile (tutor_point's ms)."""
    QtCore, _QtGui, _QtW = _qt()
    gen = _STATE["gen"]
    QtCore.QTimer.singleShot(int(ms), lambda: hide() if _STATE["gen"] == gen else None)


def _widget(host):
    w = _STATE["w"]
    try:
        if w is not None and w.parent() is host:
            return w
        if w is not None:
            w.hide()
            w.deleteLater()
    except RuntimeError:
        pass
    w = _bubble_class()(host)
    _STATE["w"] = w
    return w


_CLS = {}


def _bubble_class():
    if "b" in _CLS:
        return _CLS["b"]
    QtCore, QtGui, QtW = _qt()

    class Bubble(QtW.QWidget):
        def __init__(self, host):
            super().__init__(host)
            self.setObjectName("TutorCallout")
            self.setAccessibleName("Tutor step")
            for name in ("WA_TransparentForMouseEvents", "WA_TranslucentBackground", "WA_NoSystemBackground"):
                flag = _flag(QtCore, name)
                if flag is not None:
                    self.setAttribute(flag, True)
            nofocus = _flag(QtCore, "NoFocus")
            if nofocus is not None:
                self.setFocusPolicy(nofocus)
            self.doc = QtGui.QTextDocument(self)
            self.doc.setDocumentMargin(0)
            self.col = {}
            self.side = None
            self.tip = None
            self.box = (0, 0, 0, 0)

        def set_text(self, html, col):
            f = QtGui.QFont(QtW.QApplication.font())
            if f.pixelSize() <= 0 and f.pointSizeF() > 0:
                f.setPixelSize(max(13, int(round(f.pointSizeF() * 96 / 72.0))))
            elif f.pixelSize() > 0:
                f.setPixelSize(max(13, f.pixelSize()))
            self.doc.setDefaultFont(f)
            self.doc.setHtml(html)
            self.col = col
            self.setAccessibleDescription(self.doc.toPlainText())

        def natural_size(self):
            self.doc.setTextWidth(-1)
            ideal = self.doc.idealWidth()
            self.doc.setTextWidth(min(callout_mod.WIDTH - 2 * PAD, ideal + 1))
            s = self.doc.size()
            return (int(s.width()) + 2 * PAD, int(s.height()) + 2 * PAD)

        def put(self, x, y, w, h, side, tip):
            """The bubble at (x, y, w, h) in the host's px; the widget grows
            to hold the arrow on side, its point at tip."""
            a = callout_mod.ARROW
            gx, gy, gw, gh = x, y, w, h
            if side == "up":
                gy, gh = y - a, h + a
            elif side == "down":
                gh = h + a
            elif side == "left":
                gx, gw = x - a, w + a
            elif side == "right":
                gw = w + a
            self.box = (x - gx, y - gy, w, h)
            self.side = side
            self.tip = None if tip is None else (tip[0] - gx, tip[1] - gy)
            self.doc.setTextWidth(w - 2 * PAD)
            self.setGeometry(int(gx), int(gy), int(gw), int(gh))
            self.show()
            self.raise_()
            self.update()

        def paintEvent(self, _ev):
            try:
                self._paint()
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"Tutor: callout not painted ({e})\n")

        def _paint(self):
            p = QtGui.QPainter(self)
            aa = getattr(QtGui.QPainter, "Antialiasing", None) or QtGui.QPainter.RenderHint.Antialiasing
            p.setRenderHint(aa, True)
            x, y, w, h = self.box
            path = QtGui.QPainterPath()
            path.addRoundedRect(QtCore.QRectF(x, y, w, h), RADIUS, RADIUS)
            if self.side and self.tip:
                tx, ty = self.tip
                a = callout_mod.ARROW
                tri = QtGui.QPainterPath()
                if self.side == "up":
                    pts = [(tx - a, y + 1), (tx, y - a), (tx + a, y + 1)]
                elif self.side == "down":
                    pts = [(tx - a, y + h - 1), (tx, y + h + a), (tx + a, y + h - 1)]
                elif self.side == "left":
                    pts = [(x + 1, ty - a), (x - a, ty), (x + 1, ty + a)]
                else:
                    pts = [(x + w - 1, ty - a), (x + w + a, ty), (x + w - 1, ty + a)]
                tri.moveTo(*pts[0])
                for pt in pts[1:]:
                    tri.lineTo(*pt)
                tri.closeSubpath()
                path = path.united(tri)
            p.setPen(QtGui.QPen(QtGui.QColor(self.col.get("edge", "#3f93e0")), 2))
            p.setBrush(QtGui.QBrush(QtGui.QColor(self.col.get("fill", "#26292e"))))
            p.drawPath(path)
            p.translate(x + PAD, y + PAD)
            self.doc.drawContents(p)
            p.end()

    _CLS["b"] = Bubble
    return Bubble
