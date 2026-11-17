# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Tutor tab in Agent Link's panel (order 15, between Notes and Steps):
the lessons installed, Guided or Demo, the step in front with what it says
and whether its check passed, Back, Next, Hint, Skip, Do it for me and
Stop, and Ask Claude, which leaves the person's question as a note the
agent reads through Agent Link's notes. The lesson is the one in hand
(live.py): the agent's tutor tool moves the same one, and the tab follows.

The tab follows the theme the person chose: it sets no colours and paints
no background (FreeCAD's light themes are stylesheets over a palette that
may stay dark, so a colour read from the palette would be wrong); it uses
fonts only. The words and which buttons are on are plain functions,
tested without a window; the Qt part is TutorTab.

In guided mode the step is checked as the person works (run.py) and the
lesson goes on by itself once it passes; in demo mode Next does the step
for them and waits at the next one.

Accessibility: every control is reached with Tab in reading order and has
a screen-reader name and description (CONTROLS); the lesson's buttons have
keys that work anywhere in the tab (SHORTCUTS, said in their tooltips); the
step's words are announced when they change; Text size scales the tab's
and the callout's words (100 to 200 %); Reduce motion keeps the camera
still between steps. Contrast comes from the person's theme (no colours
here); the callout over the 3D view keeps 4.5:1 (bubble.colours).
"""

from . import live

DO_TIP = "Do this step for me: the tools do it while you watch (one undo step per call)."
NEXT_TIP = {"guided": "Check this step, then go on.", "demo": "Do this step, then wait at the next one."}
MODES = (("guided", "Guided: I do it"), ("demo", "Demo: show me"))

# Keys for the lesson's buttons, anywhere in the tab (not in the question
# box, where typing wins). Alt is Option on macOS.
SHORTCUTS = {
    "start": "Alt+Return", "back": "Alt+Left", "next": "Alt+Right", "hint": "Alt+H",
    "skip": "Alt+K", "do": "Alt+D", "stop": "Alt+Q", "question": "Alt+A",
}

# Every control's screen-reader name and description, in Tab order.
CONTROLS = (
    ("pick", "Lessons", "The lessons this FreeCAD can run. Select one, then push Start."),
    ("start", "Start", "Start the lesson: it sets up a document, then shows each step."),
    ("mode", "Lesson mode", "Guided: you do each step and it is checked as you go. Demo: each step is done for you while you watch. Switch any time."),
    ("back", "Back", "The step before."),
    ("next", "Next", "Check this step, then go on."),
    ("hint", "Hint", "A hint, then a closer one."),
    ("skip", "Skip", "Leave this step and go on."),
    ("do", "Do it for me", DO_TIP),
    ("stop", "Stop", "Stop the lesson; the document stays."),
    ("explain", "Show explanations", "A short line under each step that says why. Off: only the steps."),
    ("watch", "Let Claude watch", "Claude follows what you do here (no lesson). A sign shows in the status bar. Off by default."),
    ("motion", "Reduce motion", "Keep the 3D view still between steps: the part is framed once, at the start, with no animation."),
    ("scale", "Text size", "The size of the words in this tab and in the callout."),
    ("question", "Question for Claude", "Type a question about this step. Push Ask Claude to leave it as a note."),
    ("ask", "Ask Claude", "Leave the question as a note: Claude reads it with the notes."),
)


def control(key):
    """(name, description) of a control."""
    for k, name, desc in CONTROLS:
        if k == key:
            return name, desc
    raise KeyError(key)


def tip(key, native=None):
    """A control's tooltip: its description, and its key when it has one
    (native: the key as this system writes it, ⌥→ on macOS)."""
    _name, desc = control(key)
    keys = native or SHORTCUTS.get(key)
    return f"{desc} ({keys})" if keys else desc


def announcement(status):
    """What a screen reader says when the step changes: the step's heading,
    then its words."""
    head, say, hint = step_words(status)
    return " ".join(x for x in (head.rstrip(".") + ".", say, hint) if x and x != ".")
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
        return ("No lesson running.", "Select a lesson and push Start, or ask Claude to show you something.", "")
    if st.get("step") == "done":
        skipped = st.get("skipped") or []
        return ("Lesson done.", "Well done." + (f" Skipped: {', '.join(skipped)}." if skipped else ""), "")
    head = f"Step {st.get('step')}"
    if st.get("check") == "pass":
        head += " · done"
    elif st.get("check") == "fail" and st.get("why"):
        head += " · not yet"
    elif st.get("check") == "pending" and st.get("why"):
        head += " · waiting"
    hint = st.get("hint_text") or (st.get("why") if st.get("check") == "fail" else "") or ""
    return (head, st.get("say") or "", hint)


def why_line(status):
    """The step's short explainer for the tab (empty when explanations are
    off: the state carries none then)."""
    st = status or {}
    return st.get("because") or "" if "lesson" in st and st.get("step") != "done" else ""


def check_line(status):
    """The step's check result in words for the tab."""
    st = status or {}
    c = st.get("check")
    if "lesson" not in st or st.get("step") == "done" or c is None:
        return ""
    word = {"pass": "Check: passed", "fail": "Check: not yet", "pending": "Check: waiting"}[c]
    return word + (f" ({st['why']})" if st.get("why") and c != "pass" else "")


def buttons_on(engine):
    """Which of the tab's buttons are on for the engine's state."""
    state = getattr(engine, "state", "idle") if engine is not None else "idle"
    stepping = state == "step"
    back = stepping and bool(getattr(engine, "history", None))
    step = getattr(engine, "step", None) if stepping else None
    do = bool(stepping and isinstance(step, dict) and step.get("do"))
    return {"start": not stepping, "back": back, "next": stepping, "hint": stepping, "skip": stepping,
            "stop": stepping or state == "done", "do": do, "ask": True, "mode": True}


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
            # The list takes the whole row in a narrow dock, Start below it;
            # sized to a minimum, not to its longest title, so the style cuts
            # a long title with … and the tooltip holds it whole.
            self.pick = QtW.QComboBox()
            pol = getattr(QtW.QComboBox, "AdjustToMinimumContentsLengthWithIcon", None)
            if pol is None:
                pol = QtW.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            self.pick.setSizeAdjustPolicy(pol)
            self.pick.setMinimumContentsLength(12)
            self.start = QtW.QPushButton("Start")
            self.mode = QtW.QComboBox()
            for key, text in MODES:
                self.mode.addItem(text, key)
            lay.addWidget(self.pick)
            row = QtW.QHBoxLayout()
            row.addWidget(self.start)
            row.addWidget(self.mode, 1)
            lay.addLayout(row)
            self.head = QtW.QLabel()
            f = QtGui.QFont(self.head.font())
            f.setBold(True)
            self.head.setFont(f)
            self.say = QtW.QLabel()
            self.say.setWordWrap(True)
            self.say.setTextFormat(getattr(QtCore.Qt, "MarkdownText", getattr(QtCore.Qt, "RichText", 1)))
            self.hint = QtW.QLabel()
            self.hint.setWordWrap(True)
            fi = QtGui.QFont(self.hint.font())
            fi.setItalic(True)
            self.hint.setFont(fi)
            self.hint.setAccessibleName("Tutor hint")
            self.check = QtW.QLabel()
            self.check.setWordWrap(True)
            self.check.setAccessibleName("Tutor check")
            self.why = QtW.QLabel()
            self.why.setWordWrap(True)
            fw = QtGui.QFont(self.why.font())
            fw.setItalic(True)
            if fw.pointSizeF() > 0:
                fw.setPointSizeF(fw.pointSizeF() * 0.9)
            self.why.setFont(fw)
            self.why.setAccessibleName("Why this step")
            for w in (self.head, self.say, self.why, self.check, self.hint):
                lay.addWidget(w)
            from . import prefs

            self.explain = QtW.QCheckBox("Show explanations")
            self.explain.setChecked(prefs.explainers())
            self.explain.toggled.connect(self._explain)
            lay.addWidget(self.explain)
            self.watch = QtW.QCheckBox("Let Claude watch")
            self.watch.setChecked(live.watching())
            self.watch.toggled.connect(lambda on: live.watch_mode(bool(on)))
            lay.addWidget(self.watch)
            self.motion = QtW.QCheckBox("Reduce motion")
            self.motion.setChecked(prefs.reduce_motion())
            self.motion.toggled.connect(lambda on: prefs.set_reduce_motion(bool(on)))
            lay.addWidget(self.motion)
            size_row = QtW.QHBoxLayout()
            size_label = QtW.QLabel("Text size")
            self.scale = QtW.QComboBox()
            for pc in prefs.SCALES:
                self.scale.addItem(f"{pc} %", pc)
            self.scale.setCurrentIndex(max(0, self.scale.findData(prefs.text_scale())))
            self.scale.currentIndexChanged.connect(self._scale)
            size_label.setBuddy(self.scale)
            size_row.addWidget(size_label)
            size_row.addWidget(self.scale, 1)
            lay.addLayout(size_row)
            grid = QtW.QGridLayout()
            self.b = {}
            for i, key in enumerate(("back", "next", "hint", "skip", "do", "stop")):
                b = QtW.QPushButton(control(key)[0])
                grid.addWidget(b, i // 3, i % 3)
                self.b[key] = b
            lay.addLayout(grid)
            ask = QtW.QHBoxLayout()
            self.question = QtW.QLineEdit()
            self.question.setPlaceholderText("Ask Claude about this step…")
            self.ask = QtW.QPushButton("Ask Claude")
            ask.addWidget(self.question, 1)
            ask.addWidget(self.ask)
            lay.addLayout(ask)
            self.line = QtW.QLabel()
            self.line.setWordWrap(True)
            self.line.setAccessibleName("Tutor message")
            lay.addWidget(self.line)
            lay.addStretch(1)
            self.head.setAccessibleName("Tutor step heading")
            self._access(QtCore, QtGui, QtW)
            self._apply_scale()
            self.start.clicked.connect(self._start)
            for key in ("back", "next", "hint", "skip", "do", "stop"):
                self.b[key].clicked.connect(lambda _c=False, k=key: self._step(k))
            self.mode.currentIndexChanged.connect(self._mode)
            self.ask.clicked.connect(self._ask)
            self.question.returnPressed.connect(self._ask)
            self.pick.currentIndexChanged.connect(lambda _i: (self._buttons(), self._pick_tip()))
            live.watch(self._changed)
            self.destroyed.connect(lambda *_a, f=self._changed: live.unwatch(f))
            self.fill()

        # -- accessibility
        def _widget(self, key):
            return self.b.get(key) or getattr(self, key)

        def _access(self, QtCore, QtGui, QtW):
            """Names, descriptions, Tab order and keys for every control."""
            strong = getattr(QtCore.Qt, "StrongFocus", None) or QtCore.Qt.FocusPolicy.StrongFocus
            ctx = getattr(QtCore.Qt, "WidgetWithChildrenShortcut", None) or QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut
            native = getattr(QtGui.QKeySequence, "NativeText", None) or QtGui.QKeySequence.SequenceFormat.NativeText
            Shortcut = getattr(QtGui, "QShortcut", None) or getattr(QtW, "QShortcut")
            order = []
            self._keys = []
            self._native = {}
            for key, name, desc in CONTROLS:
                w = self._widget(key)
                w.setAccessibleName(name)
                w.setAccessibleDescription(desc)
                w.setFocusPolicy(strong)  # Tab reaches it (macOS leaves buttons out by default)
                seq = QtGui.QKeySequence(SHORTCUTS[key]) if key in SHORTCUTS else None
                if seq is not None:
                    self._native[key] = seq.toString(native)
                w.setToolTip(tip(key, self._native.get(key)))
                if seq is not None:
                    sc = Shortcut(seq, self)
                    sc.setContext(ctx)
                    sc.activated.connect(lambda k=key: self._key(k))
                    self._keys.append(sc)
                order.append(w)
            for a, b in zip(order, order[1:]):
                QtW.QWidget.setTabOrder(a, b)

        def _key(self, key):
            """A control's key: a button acts as clicked (when on); Alt+A
            puts the cursor in the question box."""
            if key == "question":
                self.question.setFocus()
                return
            w = self._widget(key)
            if w.isEnabled():
                w.click()

        def _apply_scale(self):
            """The person's text size over the application's font."""
            from . import prefs

            try:
                base = QtGui.QFont(QtW.QApplication.font())
            except Exception:  # noqa: BLE001
                return
            if base.pointSizeF() > 0:
                base.setPointSizeF(prefs.scaled(base.pointSizeF()))
            self.setFont(base)
            for w, bold, italic, k in ((self.head, True, False, 1.0), (self.hint, False, True, 1.0), (self.why, False, True, 0.9)):
                f = QtGui.QFont(base)
                f.setBold(bold)
                f.setItalic(italic)
                if f.pointSizeF() > 0:
                    f.setPointSizeF(f.pointSizeF() * k)
                w.setFont(f)

        def _scale(self, _i=None):
            from . import prefs

            prefs.set_text_scale(self.scale.currentData() or 100)
            self._apply_scale()
            c = live.controller()
            if c is not None and c.stepping:
                c._changed()  # the callout again, at the new size

        def _announce(self, status):
            """The step's words told to a screen reader when they change."""
            text = announcement(status)
            if text == getattr(self, "_said", None):
                return
            self._said = text
            self.say.setAccessibleName(text[:200])
            try:
                acc = QtGui.QAccessible
                ev = QtGui.QAccessibleEvent(self.say, acc.NameChanged if hasattr(acc, "NameChanged") else acc.Event.NameChanged)
                acc.updateAccessibility(ev)
            except Exception:  # noqa: BLE001  (an older Qt: the name is still set)
                pass

        # -- reading
        def library(self):
            if self._library is None:
                from . import lessons

                self._library = lessons.installed_library()
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
                tip = getattr(QtCore.Qt, "ToolTipRole", None) or QtCore.Qt.ItemDataRole.ToolTipRole
                for lid, text in rows:
                    self.pick.addItem(text, lid)
                    self.pick.setItemData(self.pick.count() - 1, text, tip)
                if keep:
                    i = self.pick.findData(keep)
                    if i >= 0:
                        self.pick.setCurrentIndex(i)
                if not rows:
                    self.pick.addItem("No lessons for this FreeCAD", None)
                self._pick_tip()
            except Exception as e:  # noqa: BLE001
                self.line.setText(f"Lessons could not be read: {e}")
            self._show()

        def _show(self, status=None):
            c = live.controller()
            if c is not None and (status is None or "lesson" in status):
                # As the person is shown it: no "not yet" before they act.
                status = c.person_state()
            head, say, hint = step_words(status)
            if status and status.get("mode") and "lesson" in status:
                head += " · " + ("demo" if status["mode"] == "demo" else "guided")
            self.head.setText(head)
            self.say.setText(say)
            self.say.setAccessibleDescription(say)
            self._announce(status)
            why = why_line(status)
            self.why.setText(why)
            self.why.setVisible(bool(why))
            if self.watch.isChecked() != live.watching():
                self.watch.blockSignals(True)
                self.watch.setChecked(live.watching())
                self.watch.blockSignals(False)
            c2 = live.controller()
            if c2 is not None and self.explain.isChecked() != bool(c2.e.explain):
                self.explain.blockSignals(True)
                self.explain.setChecked(bool(c2.e.explain))
                self.explain.blockSignals(False)
            line = check_line(status)
            self.check.setText(line)
            self.check.setVisible(bool(line))
            self.hint.setText(hint)
            self.hint.setVisible(bool(hint))
            if c is not None and c.mode in ("demo", "guided"):
                i = self.mode.findData(c.mode)
                if i >= 0 and i != self.mode.currentIndex():
                    self.mode.blockSignals(True)
                    self.mode.setCurrentIndex(i)
                    self.mode.blockSignals(False)
            self._buttons()

        def _changed(self, _c=None):
            """The lesson moved (the agent's call, a check that passed, a
            timer): the tab follows. A tab that is gone (its panel closed)
            is never touched: it stops following."""
            from . import later

            if not later.valid(self):
                live.unwatch(self._changed)
                return
            try:
                self._show()
            except RuntimeError:  # the widget is gone
                live.unwatch(self._changed)

        def _pick_tip(self):
            role = getattr(QtCore.Qt, "ToolTipRole", None) or QtCore.Qt.ItemDataRole.ToolTipRole
            self.pick.setToolTip(str(self.pick.itemData(self.pick.currentIndex(), role) or control("pick")[1]))

        def _buttons(self):
            e = live.engine()
            on = buttons_on(e)
            self.start.setEnabled(on["start"] and self.pick.currentData() is not None)
            for k, b in self.b.items():
                b.setEnabled(on[k])
            words = NEXT_TIP.get(getattr(e, "mode", None) or self.mode.currentData() or "guided", NEXT_TIP["guided"])
            self.b["next"].setToolTip(f"{words} ({getattr(self, '_native', {}).get('next', SHORTCUTS['next'])})")
            self.b["next"].setAccessibleDescription(words)

        # -- acting
        def _start(self):
            from . import lessons

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
                c = live.new(lesson, call=call_for(self.panel), doc=lambda: _doc(self._session()),
                             out_dir=getattr(session, "out_dir", None), session=session, progress=lessons.Progress())
                self.line.setText("")
                self._show(c.start(self.mode.currentData() or "guided"))
            except Exception as err:  # noqa: BLE001  (a setup call refused, a lesson gone)
                self.line.setText(f"The lesson could not start: {err}")
                self._show()

        def _session(self):
            """The session the panel's calls go to now (Agent Link may make a
            new one when the front document changes)."""
            try:
                return self.panel._server()[0]
            except Exception:  # noqa: BLE001
                return None

        def _step(self, what):
            c = live.controller()
            if c is None:
                return
            try:
                st = c.act(what)
                if what == "stop":
                    live.set_controller(None)
                    st = None
                self.line.setText("")
                self._show(st)
            except Exception as err:  # noqa: BLE001  (a refused call: its words)
                self.line.setText(str(err))
                self._show()

        def _explain(self, on):
            c = live.controller()
            if c is not None:
                self._show(c.set_explain(bool(on)))
            else:
                from . import prefs

                prefs.set_explainers(bool(on))

        def _mode(self, _i=None):
            c = live.controller()
            if c is None or not c.stepping:
                self._buttons()
                return
            try:
                self._show(c.act("status", mode=self.mode.currentData()))
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
                if live.watching():
                    from . import observe

                    observe.record("ask", q=text[:300])  # a waiting tutor_watch answers at once
                self.question.clear()
                self.line.setText("Left for Claude as a note (Notes tab).")
                refresh = getattr(self.panel, "refresh", None)
                if callable(refresh):
                    refresh()
            except Exception as err:  # noqa: BLE001
                self.line.setText(f"The note could not be left: {err}")

    _CLS["tab"] = Tab
    return Tab
