# SPDX-License-Identifier: LGPL-2.1-or-later
"""A lesson running: the engine (engine.py) driven in time, for the Tutor tab
and the agent's tutor tool alike.

    Controller(engine, timer=None, show=None, ui=None)

timer(ms, fn) runs fn later on the window's thread (later.after: a QTimer
owned by a long-lived QObject, checked alive before it fires); None runs it
at once (headless, and the tests). When it answers a handle with stop(),
the handle is kept, and cancel_later() stops every one still waiting. show(controller) rings the step's
targets and puts its words in the callout, answering {resolved, missing:
[why]}; None draws nothing (no window). ui: the window's hands for the
lesson itself (gui_run.UI): settle() after setup (no sketch left open, no
task dialog, nothing selected), open_task(engine) to open the feature a demo
step's task-panel targets live in, close_task() before its do.

Demo mode: next does the step in front through the tools (its do: the echo
shows each call, one undo step each), then goes on to the following step
and waits there; the callout says what and why. Nothing moves on by itself.

Guided mode: the person does the step. Its check is run again after the
agent's or the person's calls (call_done), on the window's own signals (a
recompute, a selection, a workbench switch: poke, debounced DEBOUNCE_MS) and
on Next; ADVANCE_MS after it passes the lesson goes on by itself. A step
that passes right after the agent's own call is counted as done for the
person (done_for), unless Agent Link's test flag AGENTLINK_AS_USER makes the
agent's calls the person's.

Either mode: hint climbs the ladder (engine.raise_hint), do is "Do it for
me" / "show me this one", and mode switches mid-lesson. rider(tool) is the
line Agent Link adds to the agent's answers while a lesson runs.
"""
from . import engine as engine_mod
from . import prefs as prefs_mod

DEBOUNCE_MS = 300
ADVANCE_MS = 600
HOLD_MS = 10000  # the last step's rings stay this long after the lesson is done
VIEWS = ("isometric", "front", "top", "right", "left", "rear", "bottom")
SPATIAL = ("face", "edge", "sub")
ACTIONS = ("next", "back", "hint", "skip", "stop", "status", "do", "explain")
NO_WINDOW = "no window: nothing ringed"


EDIT_KEYS = ("feature", "object", "sketch")


def edit_target(engine):
    """The object whose task panel holds a step's task targets: what its do
    works on (a feature, object or sketch argument), else the object its
    check reads a property of; bindings resolved. None when neither names one."""
    s = engine.step or {}
    for c in s.get("do") or ():
        args = engine_mod.resolve(c.get("args") or {}, engine.bindings)
        for k in EDIT_KEYS:
            if isinstance(args.get(k), str) and args[k]:
                return args[k]
    found = _prop_object(engine_mod.resolve(s.get("check") or {}, engine.bindings))
    return found


def _prop_object(check):
    if isinstance(check, dict):
        if isinstance(check.get("prop"), str):
            return check["prop"]
        if isinstance(check.get("expr"), str):
            return check["expr"]  # the object whose value is bound
        for k in ("all", "any"):
            for c in check.get(k) or ():
                got = _prop_object(c)
                if got:
                    return got
    return None


def step_view(lesson, step):
    """The view a step comes up in: its own view, else the lesson's (default
    isometric) when it lights faces or edges; None: the camera stays."""
    v = (step or {}).get("view")
    if v is None and any(isinstance(t, dict) and any(k in t for k in SPATIAL) for t in (step or {}).get("targets") or ()):
        v = (lesson or {}).get("view", "isometric")
    return v if v in VIEWS else None


def task_targets(step):
    """True when some of the step's targets are in a task panel."""
    return any(isinstance(t, dict) and "task" in t for t in (step or {}).get("targets") or ())


class Controller:
    def __init__(self, engine, timer=None, show=None, ui=None, prefs=None):
        from . import prefs as prefs_mod

        self.e = engine
        self.prefs = prefs  # FreeCAD's parameters, or a stand-in (tests)
        self.e.explain = prefs_mod.explainers(prefs)
        self.timer = timer
        self._waiting = []  # the timer's handles still waiting (cancel_later)
        self.show = show
        self.ui = ui
        self.busy = False  # the engine's own calls in hand (setup, do)
        self._token = None  # the auto-advance waiting; any move drops it
        self._poked = False
        self.targets = None  # what show answered last
        self.listeners = []  # fn(controller) after each change (the tab)
        self.passed_note = None  # "3/5" passed since the rider last spoke
        self.said = None  # the rider's last line
        self.last_by = None
        self._framed = None  # the step the view was last set for
        self.step_seq = 0  # the event number when the step in front began (observe.BUF)
        self._seq_at = None
        self._holding = False
        self.acted = False  # the person acted since the step in front began (verdict_due)
        self.done_before = False  # demo: the step's check already held when it came up
        self.prepared = None  # demo: what the lesson's hands did to show the step (workbench, tab, tree)

    # ---- reading ----------------------------------------------------------------

    @property
    def mode(self):
        return self.e.mode

    @property
    def stepping(self):
        return self.e.state == "step"

    def state(self, detail=False):
        """The compact state (engine.status) with what was ringed."""
        st = dict(self.e.status(detail=detail))
        if self.stepping and self.e.step.get("targets"):
            t = self.targets or {"resolved": 0, "missing": [NO_WINDOW]}
            st["targets"] = {"resolved": t.get("resolved", 0), "missing": list(t.get("missing") or [])[:3]}
            if self.done_before and self.e.passed and self.e.mode == "demo":
                st["targets"]["note"] = "already done: next goes on"
        if self.stepping and self.prepared:
            st["prepared"] = list(self.prepared)[:3]
        if self.stepping and self.targets and self.targets.get("callout"):
            # Where the person reads the step: bubble (over the 3D view),
            # overlay (Agent Link's callout) or none; why when not the bubble.
            st["callout"] = self.targets["callout"]
            if self.targets.get("callout_why"):
                st["callout_why"] = self.targets["callout_why"]
        return engine_mod._fit(st)

    def panel_closed(self):
        """True when the window shows no task dialog (known only with one)."""
        try:
            g = self.e._gui()
        except Exception:  # noqa: BLE001
            g = None
        return g is not None and g.task is None

    def shown(self):
        """(targets, words) to ring for the step in front at its hint rung.
        Guided, a step whose controls are in a task panel that is closed
        while its feature exists (OK pressed with another value): the
        feature's tree row instead, and how to open it again."""
        e = self.e
        if e.mode == "demo" and self.done_before and e.passed:
            return [], None  # already done: nothing to ring, Next goes on
        tg = e.hint_targets()
        if e.mode == "guided" and task_targets(e.step) and not e.passed and self.panel_closed():
            name = edit_target(e)
            doc = e._doc()
            obj = doc.getObject(name) if (doc is not None and name and hasattr(doc, "getObject")) else None
            if obj is not None:
                rest = [t for t in tg if not (isinstance(t, dict) and "task" in t)]
                return [{"tree": obj.Name}] + rest, f"Double-click {obj.Label} in the tree to change it."
        return tg, None

    def verdict_due(self):
        """True when the step's check may be told to the person: they acted
        since the step began (an event of theirs, a call that changed the
        document, Next or Do) or asked for a hint. At the step's start the
        callout and the tab show only what to do and why."""
        return bool(self.acted or self.e.hint)

    def parts(self):
        """The callout for the step in front (callout.Callout): the
        instruction a line a sentence, its why line when explanations are
        on, then the hint, or why it is not done yet once the person has
        acted. None when no step is in front."""
        from . import callout as callout_mod

        if not self.stepping:
            return None
        e, s = self.e, self.e.step
        steps = [e.say()]
        again = self.shown()[1]
        notes = []
        if e.hint:
            notes.append(e.hint_text())
        elif self.verdict_due() and e.result is not None and e.result.status == "fail" and e.result.why:
            notes.append(f"Not yet: {e.result.why}.")
        if e.passed and e.mode == "demo":
            notes.append("Done. Push Next.")
        why = e.why() if e.explain and s.get("why") and not e.said else None
        c = callout_mod.build(" ".join(x for x in steps if x), why=why, notes=notes)
        if again:
            c = callout_mod.Callout([again] + c.steps, c.why, c.notes, True if len(c.steps) else None)
        return c

    def callout(self):
        """The callout's words as plain text (parts().text())."""
        c = self.parts()
        return c.text() if c is not None else None

    def person_state(self):
        """state() as the person is shown it (the Tutor tab): the check's
        verdict held back until verdict_due."""
        st = dict(self.state())
        if self.stepping and not self.verdict_due() and st.get("check") == "fail":
            st["check"] = "pending"
            st.pop("why", None)
        return st

    # ---- after each change ---------------------------------------------------------

    def step_events(self):
        """The person's events since the step in front began, for a
        `used` check; None when nothing is watched (the check waits)."""
        from . import observe

        if not observe.active():
            return None
        return observe.BUF.since(self.step_seq)

    def _changed(self):
        entered = False
        if self.stepping and self.e.index != self._seq_at:
            from . import observe

            self._seq_at = self.e.index
            self.step_seq = observe.BUF.seq
            self.acted = False
            self.done_before = False
            self.prepared = None
            entered = True
        if entered and self.e.mode == "demo" and not self.e.passed:
            self._already_done()
        if self.ui is not None and self.stepping and self.e.mode == "demo" and not self.e.passed and task_targets(self.e.step):
            # Demo: the feature's task panel opened, so its field and OK are
            # ringed and the person sees them change.
            try:
                self.ui.open_task(self.e)
            except Exception:  # noqa: BLE001
                pass
        if entered and self.ui is not None and self.e.mode == "demo" and not self.done_before and hasattr(self.ui, "prepare"):
            # Demo: the window put the way the step's targets need it (the
            # command's workbench active, the Tasks or Model tab in front,
            # the object's tree row unfolded), so each target can be ringed.
            was, self.busy = self.busy, True  # its workbench call is the lesson's own, not re-checked
            try:
                self.prepared = self.ui.prepare(self.e) or None
            except Exception as err:  # noqa: BLE001
                self.prepared = [f"not prepared: {err}"[:80]]
            finally:
                self.busy = was
        if self.ui is not None and self.stepping and self.e.index != self._framed:
            self._framed = self.e.index
            # Reduced motion: the camera is not turned between steps.
            v = None if prefs_mod.reduce_motion(self.prefs) else step_view(self.e.lesson, self.e.step)
            if v:
                try:
                    self.ui.frame(v, self.e._doc())
                except Exception:  # noqa: BLE001
                    pass
        if self.show is not None:
            try:
                if self.stepping:
                    self.targets = self.show(self)
                elif self.e.state == "done":
                    self._hold()
                else:
                    self.show(None)
            except Exception as err:  # noqa: BLE001  (pointing is a nicety; the lesson goes on)
                self.targets = {"resolved": 0, "missing": [f"not drawn: {err}"[:80]]}
        for fn in list(self.listeners):
            try:
                fn(self)
            except Exception:  # noqa: BLE001
                pass

    def _already_done(self):
        """Demo: a step whose check holds as it comes up (an earlier step's
        calls did it, or the window is already so: no sketch open for a
        "Close" step) is passed now, with nothing to ring; Next goes on.
        The check is read without following a branch."""
        from . import checks

        e = self.e
        s = e.step or {}
        if "check" not in s:
            return
        try:
            r = checks.evaluate(engine_mod.resolve(s["check"], e.bindings), e.context())
        except Exception:  # noqa: BLE001
            return
        if r.status == "pass":
            e.check()
            self.done_before = e.passed

    def _hold(self):
        """Lesson done: the last step's rings and lit faces stay up for
        HOLD_MS, or until Stop or another lesson takes them."""
        if self._holding:
            return
        self._holding = True

        def clear():
            if self.e.state == "done" and self.show is not None:
                self.show(None)

        self._later(HOLD_MS, clear)

    def _later(self, ms, fn):
        if self.timer is None:
            fn()
            return
        h = self.timer(ms, fn)
        if hasattr(h, "stop"):
            # Kept, so a lesson that is replaced takes its waiting calls with
            # it (the last lesson's hold must not clear the next one's rings).
            self._waiting = [x for x in self._waiting if not getattr(x, "done", False)] + [h]

    def cancel_later(self):
        """Every call this lesson left waiting (auto-advance, debounce,
        hold), stopped: live.set_controller does this when another lesson,
        or none, takes its place."""
        waiting, self._waiting = self._waiting, []
        self._token = None
        for h in waiting:
            try:
                h.stop()
            except Exception:  # noqa: BLE001
                pass

    # ---- the person's and the agent's actions --------------------------------------------

    def start(self, mode="guided", fixtures=None):
        self._token = None
        self.busy = True
        try:
            self.e.start(mode, fixtures=fixtures)
            if self.ui is not None:
                # The person starts from a quiet window: setup's sketch closed,
                # no task dialog, nothing selected, the part in view.
                try:
                    self.ui.settle(self.e._doc())
                except TypeError:  # a stand-in without the document
                    self.ui.settle()
                v = (self.e.lesson or {}).get("view", "isometric")
                if v in VIEWS:
                    if prefs_mod.reduce_motion(self.prefs):
                        try:
                            self.ui.frame(v, self.e._doc(), animate=False)
                        except TypeError:  # a stand-in without animate
                            self.ui.frame(v, self.e._doc())
                    else:
                        self.ui.frame(v, self.e._doc())
        finally:
            self.busy = False
        self._changed()
        return self.state()

    def set_explain(self, on):
        """Explanations on or off, kept as the person's preference."""
        from . import prefs as prefs_mod

        self.e.explain = prefs_mod.set_explainers(on, self.prefs)
        self._changed()
        return self.state()

    def act(self, action, mode=None, detail=False, on=None):
        """One of ACTIONS, after switching to mode when it is given. The
        compact state. explain: on (True or False) sets the explanations."""
        if action == "explain":
            if on is None:
                raise engine_mod.TutorError("explain: on, true or false")
            return self.set_explain(on)
        if action not in ACTIONS:
            raise engine_mod.TutorError(f"action: one of {', '.join(ACTIONS)}")
        if action != "status":
            self._token = None
        if mode is not None and mode != self.e.mode:
            self.e.set_mode(mode)
            if action == "status":
                self._changed()
        if action == "status":
            return self.state(detail=detail)
        if action == "stop":
            self.e.stop()
        elif action == "back":
            self.e.back()
        elif action == "skip":
            self.e.skip()
        elif action == "hint":
            self.e.raise_hint()
        elif action == "do":
            self.acted = True
            self._do()
            if self.e.passed and self.e.mode == "guided":
                self._advance_later()
        elif action == "next":
            self._next()
        self._changed()
        return self.state(detail=detail)

    def _do(self):
        self.busy = True
        try:
            if self.ui is not None and task_targets(self.e.step):
                self.ui.close_task()  # the panel opened to show it; the do sets the value
            self.e.do()
        finally:
            self.busy = False
        if self.e.passed:
            self.passed_note = self.e.position()

    def _next(self):
        e = self.e
        e._need_step()
        if e.mode == "demo" and not e.passed and e.step.get("do"):
            # Do the step in front, then go on and wait at the next one. A
            # step whose check already holds (done by an earlier step, or by
            # the person before the mode switch) is not done again.
            at = e.index
            if "check" in e.step and e.check()["check"] == "pass":
                if e.index == at:
                    self.passed_note = e.position()
                    e.next()
                return
            if e.index != at:
                return  # a known wrong turn: its branch step first
            self._do()
            if not e.passed:
                return  # refused or not done: stays, with why
            e.next()
            return
        at = e.index
        e.check()
        if e.index != at:
            return  # a known wrong turn: its branch step first
        if e.mode == "demo" and e.result is not None and e.result.status == "pending" and self.ui is not None:
            # Demo: a check that cannot be told with a panel open (a check
            # that changes a parameter for a moment) gets a quiet window and
            # one more try, so the lesson ends with its verdict.
            try:
                self.ui.settle(e._doc())
            except Exception:  # noqa: BLE001
                pass
            e.check()
            if e.index != at:
                return
        if e.passed:
            self.passed_note = e.position()
        e.next()

    # ---- re-checking ----------------------------------------------------------------

    def recheck(self, by=None):
        """The step's check again; in guided mode a pass goes on by itself
        ADVANCE_MS later. by: whose action led here ("agent": the step is
        counted as done for the person)."""
        e = self.e
        if self.busy or not self.stepping:
            return
        was = e.passed
        at = e.index
        e.check()
        if e.index != at:
            self._changed()  # a branch was taken
            return
        if e.passed and not was:
            self.passed_note = e.position()
            if by == "agent":
                e.done_for.add(e.step["id"])
            if e.mode == "guided":
                self._advance_later()
        self._changed()

    def _advance_later(self):
        tok, at = object(), self.e.index
        self._token = tok
        now = self.timer is None

        def go():
            if self._token is not tok or self.e.index != at or not self.stepping:
                return  # the person moved on or went back meanwhile
            self._token = None
            if not now and self.e.check().get("check") != "pass":
                return self._changed()  # undone meanwhile: stays
            self.e.next()
            if not now:
                self._changed()

        self._later(ADVANCE_MS, go)

    def poke(self, ev=None):
        """A window signal (recompute, selection, workbench): the check is run
        once the signals have settled for DEBOUNCE_MS. ev: the person's event
        (observe.py), which counts as acting when it came after the step
        began; a signal without one counts too. Signals raised while a
        check tries a parameter for a moment (checks.TRIAL) are not the
        person's and are dropped."""
        from . import checks

        if self.busy or not self.stepping or checks.in_trial():
            return
        if ev is None or not isinstance(ev.get("n"), int) or ev["n"] > self.step_seq:
            self.acted = True
        if self._poked:
            return
        self._poked = True

        def fire():
            self._poked = False
            self.recheck(by="person")

        self._later(DEBOUNCE_MS, fire)

    def call_done(self, session, tool, ok, changed=False):
        """Agent Link's call_done: a call went through, the agent's or a panel
        click's; the tutor's own calls and the engine's are not re-checked."""
        if self.busy or not ok or not self.stepping or str(tool).startswith("tutor"):
            return
        by = getattr(session, "by", "agent")
        self.last_by = by
        if by != "agent" or changed:
            self.acted = True  # a read-only call of the agent's is no act of the person's
        self.recheck(by=by)

    # ---- the rider line ----------------------------------------------------------------

    def rider(self, tool=None):
        """"tutor: step 3/5 passed" and the like, for the agent's next answer:
        a pass once, and the step's state when it differs from the last
        line given. None for the tutor's own answers and once it is over."""
        if str(tool or "").startswith("tutor"):
            return None
        e = self.e
        if e.state not in ("step", "done"):
            return None
        if e.state == "done":
            # The same verdict as tutor status: complete, the last check as
            # it stood when the lesson ended, and what was skipped.
            line = "tutor: lesson complete"
            if e.final is not None:
                fin = {"pass": "passed", "fail": "not passed", "pending": "not told", "not run": "not run"}.get(e.final["check"], e.final["check"])
                line += f", final check {fin}" + (f" ({e.final['why']})" if e.final.get("why") else "")
            line += f", skipped {', '.join(sorted(e.skipped))}" if e.skipped else ""
        else:
            word = {"pass": "passed", "fail": "not yet", "pending": "pending"}[e.result.status if e.result else "pending"]
            now = f"step {e.position()} {word}"
            if word == "not yet" and e.result.why:
                now += f" ({e.result.why})"
            if self.passed_note and self.passed_note != e.position():
                line = f"tutor: step {self.passed_note} passed; now {now}"
            else:
                line = f"tutor: {now}"
        self.passed_note = None
        if line == self.said:
            return None
        self.said = line
        return line
