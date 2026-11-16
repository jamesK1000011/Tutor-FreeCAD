# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Tutor tab in Agent Link's panel (order 15, between Notes and Steps):
the lessons installed, the step in front and what it says, Back, Next,
Hint, Skip and Stop, and Ask Claude, which leaves the person's question as
a note the agent reads through Agent Link's notes.

The tab follows the theme the person chose: it sets no colours and paints
no background (FreeCAD's light themes are stylesheets over a palette that
may stay dark, so a colour read from the palette would be wrong); it uses
fonts only. The words and which buttons are on are plain functions,
tested without a window; the Qt part is TutorTab.

Not here yet (T3, guided and demo modes): checking a step on the person's
own actions as they happen, and "Do it for me"; that button is shown, off,
with a tooltip saying so.
"""

from . import live

DO_LATER = "Do it for me comes with demo mode in a later version of the Tutor."
NO_DOC = "Open a document first: the question is left as a note on it."


# ---- words and states (no Qt) -------------------------------------------------

def lesson_rows(listing):
    """[(id, text)] for the lesson list: title, minutes, a tick when done."""
    out = []
    for l in listing or []:
        mins = f" · {l['minutes']} min" if l.get("minutes") else ""
        out.append((l["id"], f"{'✓ ' if l.get('done') else ''}{l['title']}{mins}"))
    return out


def step_words(status):
    """(heading, say, hint) for the tab from the engine's compact state."""
    st = status or {}
    if "lesson" not in st:
        return ("No lesson running.", "Pick a lesson and press Start, or ask Claude to show you something.", "")
    if st.get("step") == "done":
        skipped = st.get("skipped") or []
        return ("Lesson done.", "Well done." + (f" Skipped: {', '.join(skipped)}." if skipped else ""), "")
    head = f"Step {st.get('step')}"
    if st.get("check") == "pass":
        head += " · done"
    elif st.get("check") == "fail" and st.get("why"):
        head += " · not yet"
    hint = st.get("hint_text") or (st.get("why") if st.get("check") == "fail" else "") or ""
    return (head, st.get("say") or "", hint)


def buttons_on(engine):
    """Which of the tab's buttons are on for the engine's state."""
    state = getattr(engine, "state", "idle") if engine is not None else "idle"
    stepping = state == "step"
    back = stepping and bool(getattr(engine, "history", None))
    return {"start": not stepping, "back": back, "next": stepping, "hint": stepping, "skip": stepping,
            "stop": stepping, "do": False, "ask": True}


def question_note(text, status=None):
    """The note left for the agent when the person presses Ask Claude."""
    t = " ".join(str(text or "").split())
    st = status or {}
    where = f" (lesson {st['lesson']}, step {st.get('step')})" if st.get("lesson") and st.get("step") not in (None, "done") else ""
    return f"Tutor question{where}: {t}" if t else None


def _doc(session):
    d = getattr(session, "doc", None)
    if d is None:
        try:
            import FreeCAD

            d = FreeCAD.ActiveDocument
        except ImportError:
            d = None
    return d


def call_for(panel):
    """The engine's call(tool, args) -> (refused, answer) over the panel's
    own runner, as the person's click (shown and logged)."""

    def call(tool, args):
        ok, out = panel._call(tool, args)
        return (not ok), out

    return call


# ---- the tab (Qt) --------------------------------------------------------------

def _qt():
    from PySide import QtCore, QtGui

    QtW = getattr(__import__("PySide", fromlist=["QtWidgets"]), "QtWidgets", QtGui)
    return QtCore, QtGui, QtW


def TutorTab(panel):
    """The tab's widget, its class made on first use (Qt loads then)."""
    return _make()(panel)


_CLS = {}


def _make():
    if "tab" in _CLS:
        return _CLS["tab"]
    QtCore, QtGui, QtW = _qt()

    class Tab(QtW.QWidget):
        def __init__(self, panel):
            super().__init__()
            self.panel = panel
            self.setObjectName("AgentLinkTutorTab")
            self._library = None
            lay = QtW.QVBoxLayout(self)
            lay.setContentsMargins(6, 6, 6, 6)
            row = QtW.QHBoxLayout()
            self.pick = QtW.QComboBox()
            self.pick.setAccessibleName("Lessons")
            self.start = QtW.QPushButton("Start")
            self.start.setToolTip("Start the lesson: it sets up a document, then shows each step.")
            row.addWidget(self.pick, 1)
            row.addWidget(self.start)
            lay.addLayout(row)
            self.head = QtW.QLabel()
            f = QtGui.QFont(self.head.font())
            f.setBold(True)
            self.head.setFont(f)
            self.say = QtW.QLabel()
            self.say.setWordWrap(True)
            self.say.setTextFormat(getattr(QtCore.Qt, "MarkdownText", getattr(QtCore.Qt, "RichText", 1)))
            self.say.setAccessibleName("Tutor step")
            self.hint = QtW.QLabel()
            self.hint.setWordWrap(True)
            fi = QtGui.QFont(self.hint.font())
            fi.setItalic(True)
            self.hint.setFont(fi)
            self.hint.setAccessibleName("Tutor hint")
            for w in (self.head, self.say, self.hint):
                lay.addWidget(w)
            grid = QtW.QGridLayout()
            self.b = {}
            for i, (key, text, tip) in enumerate((
                    ("back", "Back", "The step before."), ("next", "Next", "Check this step, then go on."),
                    ("hint", "Hint", "A hint, then a closer one."), ("skip", "Skip", "Leave this step and go on."),
                    ("do", "Do it for me", DO_LATER), ("stop", "Stop", "Stop the lesson; the document stays."))):
                b = QtW.QPushButton(text)
                b.setToolTip(tip)
                grid.addWidget(b, i // 3, i % 3)
                self.b[key] = b
            lay.addLayout(grid)
            ask = QtW.QHBoxLayout()
            self.question = QtW.QLineEdit()
            self.question.setPlaceholderText("Ask Claude about this step…")
            self.question.setAccessibleName("Question for Claude")
            self.ask = QtW.QPushButton("Ask Claude")
            self.ask.setToolTip("Leave the question as a note: Claude reads it with the notes.")
            ask.addWidget(self.question, 1)
            ask.addWidget(self.ask)
            lay.addLayout(ask)
            self.line = QtW.QLabel()
            self.line.setWordWrap(True)
            lay.addWidget(self.line)
            lay.addStretch(1)
            self.start.clicked.connect(self._start)
            self.b["back"].clicked.connect(lambda: self._step("back"))
            self.b["next"].clicked.connect(lambda: self._step("next"))
            self.b["hint"].clicked.connect(lambda: self._step("raise_hint"))
            self.b["skip"].clicked.connect(lambda: self._step("skip"))
            self.b["stop"].clicked.connect(lambda: self._step("stop"))
            self.ask.clicked.connect(self._ask)
            self.question.returnPressed.connect(self._ask)
            self.pick.currentIndexChanged.connect(lambda _i: self._buttons())
            self._pointed = False
            self.fill()

        # -- reading
        def library(self):
            if self._library is None:
                from . import lessons

                self._library = lessons.core_library()
            return self._library

        def fill(self):
            """The lesson list and the step, each time the tab comes up."""
            try:
                from . import lessons

                lib = self.library()
                try:
                    import FreeCAD
                    import FreeCADGui
                    from agentlink import hooks

                    ver = ".".join(FreeCAD.Version()[:3])
                    benches = list(FreeCADGui.listWorkbenches())
                    api = hooks.API
                except Exception:
                    ver, benches, api = None, None, None
                rows = lesson_rows(lib.listing(lessons.Progress(), ver, api, benches))
                keep = self.pick.currentData()
                self.pick.clear()
                for lid, text in rows:
                    self.pick.addItem(text, lid)
                if keep:
                    i = self.pick.findData(keep)
                    if i >= 0:
                        self.pick.setCurrentIndex(i)
                if not rows:
                    self.pick.addItem("No lessons for this FreeCAD", None)
            except Exception as e:  # noqa: BLE001
                self.line.setText(f"Lessons could not be read: {e}")
            self._show()

        def _show(self, status=None):
            e = live.engine()
            if status is None:
                status = e.status() if e is not None else None
            head, say, hint = step_words(status)
            self.head.setText(head)
            self.say.setText(say)
            self.say.setAccessibleDescription(say)
            self.hint.setText(hint)
            self.hint.setVisible(bool(hint))
            self._buttons()
            self._point(e)

        def _buttons(self):
            on = buttons_on(live.engine())
            self.start.setEnabled(on["start"] and self.pick.currentData() is not None)
            for k, b in self.b.items():
                b.setEnabled(on[k])

        def _point(self, e):
            """Ring the step's targets, its words in the callout (the
            agent's tutor_point does the same)."""
            from . import point
            from .window import Window

            try:
                from agentlink import hooks
            except Exception:
                return
            if e is None or getattr(e, "state", None) != "step":
                # Only the tab's own rings go; the agent's stay.
                if self._pointed:
                    point.point({}, None, hooks=hooks)
                    self._pointed = False
                return
            s = e.step
            try:
                session, _server = self.panel._server()
            except Exception:
                session = None
            say = e.said or s.get("say")
            hint = e.hint_text() if e.hint else None
            point.point({"targets": list(s.get("targets") or []), "say": "\n".join(x for x in (say, hint) if x)},
                        Window(session), hooks=hooks, bindings=e.bindings)
            self._pointed = True

        # -- acting
        def _start(self):
            from . import engine, lessons

            lid = self.pick.currentData()
            if not lid:
                return
            try:
                lesson = self.library().get(lid)
                session = None
                try:
                    session, _server = self.panel._server()
                except Exception:
                    pass
                e = engine.Engine(lesson, call=call_for(self.panel), doc=lambda s=session: _doc(s),
                                  out_dir=getattr(session, "out_dir", None), progress=lessons.Progress())
                live.set_engine(e)
                self.line.setText("")
                self._show(e.start("guided"))
            except Exception as err:  # noqa: BLE001  (a setup call refused, a lesson gone)
                self.line.setText(f"The lesson could not start: {err}")
                self._show()

        def _step(self, what):
            e = live.engine()
            if e is None:
                return
            try:
                if what == "next":
                    at = e.index
                    st = e.check()
                    if e.index != at:  # a known wrong turn: its branch step first
                        return self._show(st)
                st = getattr(e, what)()
                if what == "stop":
                    live.set_engine(None)
                self.line.setText("")
                self._show(st if what != "stop" else None)
            except Exception as err:  # noqa: BLE001
                self.line.setText(str(err))

        def _ask(self):
            text = question_note(self.question.text(), (live.engine().status() if live.engine() else None))
            if not text:
                return
            try:
                import FreeCAD
                from agentlink.families import notes as nf

                doc = FreeCAD.ActiveDocument
                if doc is None:
                    self.line.setText(NO_DOC)
                    return
                nf.add_note(doc, [0.0, 0.0, 0.0], text, "person")
                self.question.clear()
                self.line.setText("Left for Claude as a note (Notes tab).")
                refresh = getattr(self.panel, "refresh", None)
                if callable(refresh):
                    refresh()
            except Exception as err:  # noqa: BLE001
                self.line.setText(f"The note could not be left: {err}")

    _CLS["tab"] = Tab
    return Tab
