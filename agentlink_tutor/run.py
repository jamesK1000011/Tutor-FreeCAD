# SPDX-License-Identifier: LGPL-2.1-or-later
"""A lesson running: the engine (engine.py) driven in time, for the Tutor tab
and the agent's tutor tool alike.

    Controller(engine, timer=None, show=None, by=None)

timer(ms, fn) runs fn later on the window's thread (a Qt single shot); None
runs it at once (headless, and the tests). show(controller) rings the step's
targets and puts its words in the callout, answering {resolved, missing:
[why]}; None draws nothing (no window).

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

DEBOUNCE_MS = 300
ADVANCE_MS = 600
ACTIONS = ("next", "back", "hint", "skip", "stop", "status", "do")
NO_WINDOW = "no window: nothing ringed"


class Controller:
    def __init__(self, engine, timer=None, show=None, by=None):
        self.e = engine
        self.timer = timer
        self.show = show
        self.busy = False  # the engine's own calls in hand (setup, do)
        self._token = None  # the auto-advance waiting; any move drops it
        self._poked = False
        self.targets = None  # what show answered last
        self.listeners = []  # fn(controller) after each change (the tab)
        self.passed_note = None  # "3/5" passed since the rider last spoke
        self.said = None  # the rider's last line
        self.last_by = None

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
        return engine_mod._fit(st)

    def callout(self):
        """The callout's words for the step in front: what to do, in demo
        why, and the hint or why not yet."""
        if not self.stepping:
            return None
        e, s = self.e, self.e.step
        lines = [e.said or s.get("say")]
        if e.mode == "demo" and s.get("explain"):
            lines.append(s["explain"])
        if e.hint:
            lines.append(e.hint_text())
        elif e.result is not None and e.result.status == "fail" and e.result.why:
            lines.append(f"Not yet: {e.result.why}.")
        if e.passed and e.mode == "demo":
            lines.append("Done. Next goes on.")
        return "\n".join(x for x in lines if x)

    # ---- after each change ---------------------------------------------------------

    def _changed(self):
        if self.show is not None:
            try:
                self.targets = self.show(self) if self.stepping else self.show(None)
            except Exception as err:  # noqa: BLE001  (pointing is a nicety; the lesson goes on)
                self.targets = {"resolved": 0, "missing": [f"not drawn: {err}"[:80]]}
        for fn in list(self.listeners):
            try:
                fn(self)
            except Exception:  # noqa: BLE001
                pass

    def _later(self, ms, fn):
        if self.timer is None:
            fn()
        else:
            self.timer(ms, fn)

    # ---- the person's and the agent's actions --------------------------------------------

    def start(self, mode="guided", fixtures=None):
        self._token = None
        self.busy = True
        try:
            self.e.start(mode, fixtures=fixtures)
        finally:
            self.busy = False
        self._changed()
        return self.state()

    def act(self, action, mode=None, detail=False):
        """One of ACTIONS, after switching to mode when it is given. The
        compact state."""
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
            self.e.do()
        finally:
            self.busy = False
        if self.e.passed:
            self.passed_note = self.e.position()

    def _next(self):
        e = self.e
        e._need_step()
        if e.mode == "demo" and not e.passed and e.step.get("do"):
            # Do the step in front, then go on and wait at the next one.
            self._do()
            if not e.passed:
                return  # refused or not done: stays, with why
            e.next()
            return
        at = e.index
        e.check()
        if e.index != at:
            return  # a known wrong turn: its branch step first
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

    def poke(self):
        """A window signal (recompute, selection, workbench): the check is run
        once the signals have settled for DEBOUNCE_MS."""
        if self._poked or self.busy or not self.stepping:
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
            line = "tutor: lesson done" + (f", skipped {', '.join(sorted(e.skipped))}" if e.skipped else "")
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
