# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Tutor's state machine: one lesson, its mode, the step in front, the
hint level and the bindings ($name: the object the person actually made).

Nothing here draws or watches. The engine is given what it reads:

    call(tool, args) -> (refused, answer)   Agent Link's tools by name
    doc()                                   the session's document
    gui()                                   a checks.GuiState, or None
    events()                                the person's events, or None
    out_dir                                 the session's folder

Modes: demo (the steps are done through the tools, one by one, and the engine
waits for next), guided (the person does each step; check() is called on their
events and the engine moves on when it passes) and watch (no lesson). Explain
and point-out keep no state and do not come here. demo and guided switch
mid-lesson (set_mode); "show me this one" is do() on the step in front.

The hint ladder, one rung per raise_hint: 1 a nudge (the step's first hint,
else why it is not done; the same rings), 2 the field (only the step's task
field ringed, else its first target: hint_targets; never the value), 3 the
exact value (the step's third hint, else the value its check wants:
checks.exact) and "Do it for me" offered. lessons.hint_problems holds every
lesson's hints 1 and 2 to that: neither says the value.

run.py drives this engine in the window and for the tutor tool: timers,
re-checks on events, pointing and the rider line.

Steps run in their order, except that a step a branch goes to (a detour) is
entered only through that branch; when it passes it goes to its next, or
back to the step that branched.
"""
import os
import shutil

from . import checks, lessons, words

MODES = ("demo", "guided", "watch")
HINT_MAX = 3
STATE_MAX = 600


def resolve(value, bindings):
    """value with every "$name" swapped for its binding (a number stays a
    number); unknown names are left as they are."""
    if isinstance(value, str):
        m = lessons.VAR.match(value)
        if m and m.group(1) in bindings:
            return bindings[m.group(1)]
        return value
    if isinstance(value, dict):
        return {k: resolve(v, bindings) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, bindings) for v in value]
    return value


def field_target(targets):
    """The one target the second hint rings: the first field of a task panel
    (a task target that is not a button), else the first target."""
    for t in targets:
        task = t.get("task") if isinstance(t, dict) else None
        if isinstance(task, str) or (isinstance(task, dict) and not task.get("button")):
            return t
    return targets[0]


class TutorError(ValueError):
    pass


class Engine:
    def __init__(self, lesson=None, call=None, doc=None, gui=None, events=None, out_dir=None, progress=None):
        self.lesson = lesson
        self.call = call
        self._doc = doc or (lambda: None)
        self._gui = gui or (lambda: None)
        self._events = events or (lambda: None)
        self.out_dir = out_dir
        self.progress = progress
        self.mode = None
        self.state = "idle"  # idle, step, done, stopped
        self.index = None
        self.hint = 0
        self.passed = False
        self.result = None
        self.bindings = {}
        self.before = set()
        self.history = []  # step indexes visited, for back
        self.return_to = None  # where a detour goes back to
        self.said = None  # a branch's words, shown once
        self.skipped = set()
        self.explain = True  # the step's why line in answers (prefs.ShowExplainers)
        self.done_for = set()  # steps done for the person (do, or the agent's own calls)
        self.did = None  # the step do() last ran
        if lesson is not None:
            self._ids = [s["id"] for s in lesson["steps"]]
            self._detours = lessons.detours(lesson)
            self._main = [i for i, sid in enumerate(self._ids) if sid not in self._detours]

    # ---- reading ------------------------------------------------------------

    @property
    def step(self):
        return self.lesson["steps"][self.index] if self.index is not None else None

    def context(self):
        return checks.Context(doc=self._doc(), gui=self._gui(), events=self._events(), before=self.before, out_dir=self.out_dir)

    def _names(self):
        doc = self._doc()
        return {o.Name for o in (getattr(doc, "Objects", None) or [])}

    def position(self):
        """"n/m" over the main path; a detour shows the step it came from."""
        i = self.index
        if i is not None and i not in self._main and self.return_to is not None:
            i = self.return_to
        n = self._main.index(i) + 1 if i in self._main else 0
        return f"{n}/{len(self._main)}"

    # ---- starting -----------------------------------------------------------

    def set_mode(self, mode):
        """demo or guided, mid-lesson; the step in front stays."""
        if mode not in ("demo", "guided"):
            raise TutorError("mode: demo or guided (watch has no lesson)")
        if self.state not in ("step", "done"):
            raise TutorError(f"no lesson running: the lesson is {self.state}")
        self.mode = mode
        return self.status()

    def start(self, mode="guided", fixtures=None):
        """Set the lesson up (its setup calls through the tools) and enter its
        first step. fixtures: the folder a fixture file is copied from."""
        if mode not in MODES:
            raise TutorError(f"mode: one of {', '.join(MODES)}")
        self.mode = mode
        if mode == "watch":
            self.state = "watch"
            return self.status()
        if self.lesson is None:
            raise TutorError("start: a lesson (its id, or an inline lesson)")
        self.bindings = dict(self.lesson.get("vars") or {})
        setup = self.lesson.get("setup") or {}
        if setup.get("doc") == "new":
            self._run([{"tool": "doc_new", "args": {"name": self.lesson["id"].rpartition(".")[2].replace("-", "_")}}], "setup")
        elif setup.get("fixture"):
            folder = fixtures or self.lesson.get("_folder") or ""
            src = os.path.join(folder, setup["fixture"])
            dst = os.path.join(self.out_dir or ".", setup["fixture"])
            shutil.copyfile(src, dst)  # opened as a copy: the lesson's file stays as shipped
            self._run([{"tool": "doc_open", "args": {"path": dst}}], "setup")
        elif setup.get("calls"):
            self._run(setup["calls"], "setup")
        self._bind(setup.get("bind"), only_new=False)
        self.state = "step"
        self.history = []
        self._enter(self._main[0])
        return self.status()

    def _run(self, calls, where):
        if self.call is None:
            raise TutorError("no tools to call: the engine was given no call")
        answers = []
        for c in calls:
            refused, out = self.call(c["tool"], resolve(c.get("args") or {}, self.bindings))
            answers.append({"tool": c["tool"], "refused": bool(refused), "answer": out})
            if refused:
                raise TutorError(f"{where}: {c['tool']} was refused — {_reason(out)}")
        return answers

    def _bind(self, bind, only_new):
        ctx = self.context()
        for name, spec in (bind or {}).items():
            if isinstance(spec, str):
                o = checks.lookup(ctx.doc, resolve(spec, self.bindings))
            else:
                kind = next(iter(spec))
                found = checks.find(ctx, resolve(spec[kind], self.bindings), only_new=(kind == "new" and only_new))
                o = found[-1] if found else None
            if o is not None:
                self.bindings[name] = o.Name

    def _enter(self, index):
        if self.index is not None and (not self.history or self.history[-1] != self.index):
            self.history.append(self.index)
        self.index = index
        self.hint = 0
        self.passed = False
        self.result = None
        self.did = None
        self.before = self._names()

    # ---- moving -------------------------------------------------------------

    def _following(self):
        s = self.step
        if s.get("next"):
            return self._ids.index(s["next"])
        if self.index not in self._main:  # a detour goes back where it came from
            return self.return_to
        later = [i for i in self._main if i > self.index]
        return later[0] if later else None

    def check(self):
        """Evaluate the step's check; on a pass bind what it made, on a fail
        follow a branch whose when holds. The compact state."""
        self._need_step()
        s = self.step
        ctx = self.context()
        r = checks.evaluate(resolve(s["check"], self.bindings), ctx) if "check" in s else checks.PASS
        self.result = r
        if r.status == "pass":
            if not self.passed:
                self._bind(s.get("bind"), only_new=True)
            self.passed = True
            return self.status()
        for b in s.get("branches") or []:
            if checks.evaluate(resolve(b["when"], self.bindings), ctx).status == "pass":
                self.return_to = self.index if self.index in self._main else self.return_to
                self._enter(self._ids.index(b["goto"]))
                self.said = b.get("say")
                return self.status()
        self.passed = False  # done once, undone since
        return self.status()

    def next(self):
        """The following step (a step left unpassed counts as skipped); done
        after the last."""
        self._need_step()
        if not self.passed:
            self.skipped.add(self.step["id"])
        nxt = self._following()
        if self.index not in self._main and nxt == self.return_to:
            self.return_to = None
        self.said = None
        if nxt is None:
            self.state = "done"
            if self.progress is not None:
                self.progress.mark(self.lesson["id"], self.lesson["version"])
            return self.status()
        self._enter(nxt)
        return self.status()

    skip = next

    def back(self):
        self._need_step()
        if not self.history:
            return self.status()
        self.index = self.history.pop()
        self.did = None
        self.hint = 0
        self.passed = False
        self.result = None
        self.said = None
        self.before = self._names()
        return self.status()

    def stop(self):
        self.state = "stopped"
        return self.status()

    def do(self):
        """Run the step's do through the tools (demo, or "Do it for me"),
        then check it."""
        self._need_step()
        if not self.step.get("do"):
            raise TutorError(f"step {self.step['id']} has nothing to do for the person")
        self._run(self.step["do"], f"step {self.step['id']}")
        self.did = self.step["id"]
        self.done_for.add(self.step["id"])
        return self.check()

    # ---- hints --------------------------------------------------------------

    def raise_hint(self):
        """One rung up the ladder: 1 a nudge, 2 the exact field ringed, 3 the
        exact value and "Do it for me"."""
        self._need_step()
        self.hint = min(self.hint + 1, HINT_MAX)
        return self.status()

    def say(self):
        """The step's words as the person reads them: a branch's words once,
        else the step's; each command named by its live menu text."""
        s = self.step
        return words.ui_text(self.said or s["say"]) if s is not None else None

    def why(self):
        s = self.step
        return words.ui_text(s.get("why")) if s is not None else None

    def hint_text(self):
        """The hint at this rung, commands named as the window names them."""
        return words.ui_text(self._hint_text())

    def _hint_text(self):
        if self.hint == 0:
            return None
        hints = self.step.get("hints") or []
        if self.hint <= len(hints):
            return hints[self.hint - 1]
        if self.hint == 1:
            return (self.result.why + ".") if self.result is not None and self.result.why else self.step["say"]
        if self.hint == 2:
            return "Look for what is ringed." if self.step.get("targets") else self.step["say"]
        exact = checks.exact(resolve(self.step["check"], self.bindings), self.context().doc) if "check" in self.step else None
        if exact:
            return exact + "."
        return hints[-1] if hints else self.step["say"]

    def hint_targets(self):
        """The step's targets to ring at this rung: all of them at rungs 0
        and 1; from rung 2 the field only (field_target)."""
        tg = list(self.step.get("targets") or []) if self.step else []
        if self.hint >= 2 and tg:
            return [field_target(tg)]
        return tg

    def offer_do(self):
        return self.hint >= HINT_MAX and bool(self.step.get("do"))

    # ---- answering ----------------------------------------------------------

    def _need_step(self):
        if self.state != "step":
            raise TutorError(f"no step in front: the lesson is {self.state}")

    def status(self, detail=False):
        """The compact state (under 600 characters): lesson, step n/m, say,
        check, why, hint and the number of targets."""
        if self.state in ("idle", "watch", "stopped") or self.lesson is None:
            return {"state": self.state, **({"mode": self.mode} if self.mode else {})}
        out = {"lesson": self.lesson["id"], "mode": self.mode, "explain": "on" if self.explain else "off"}
        if self.state == "done":
            out.update(step="done", skipped=sorted(self.skipped))
            if self.done_for:
                out["done_for"] = sorted(self.done_for)
            return _fit(out)
        s = self.step
        r = self.result
        out.update(step=self.position(), id=s["id"], say=self.say())
        if s.get("why") and (self.explain or detail):
            out["because"] = words.ui_text(s["why"])
        out["check"] = r.status if r is not None else "pending"
        if r is not None and r.why:
            out["why"] = r.why
        out["hint"] = self.hint
        if self.hint:
            out["hint_text"] = self.hint_text()
        if self.offer_do():
            out["do_it"] = True
        if s.get("targets"):
            out["targets"] = len(s["targets"])
        if self.did is not None:
            out["did"] = self.did
        if detail:
            later = [self.lesson["steps"][i]["say"] for i in self._main if i > self.index]
            out["remaining"] = [t[:60] for t in later]
        return _fit(out)


def _fit(out):
    """Text fields cut so the answer stays under STATE_MAX characters."""
    import json

    for key in ("remaining", "missing", "because", "hint_text", "why", "say"):
        if len(json.dumps(out, ensure_ascii=False)) <= STATE_MAX:
            break
        v = out.get(key) if key != "missing" else (out.get("targets") or {}).get("missing") if isinstance(out.get("targets"), dict) else None
        if isinstance(v, list):
            while v and len(json.dumps(out, ensure_ascii=False)) > STATE_MAX:
                v.pop()
        elif isinstance(v, str):
            over = len(json.dumps(out, ensure_ascii=False)) - STATE_MAX
            out[key] = v[: max(20, len(v) - over - 1)] + "…"
    return out


def _reason(out):
    if isinstance(out, dict):
        e = out.get("error")
        if isinstance(e, dict):
            return e.get("message") or str(e)
        return str(e or out)[:200]
    return str(out)[:200]
