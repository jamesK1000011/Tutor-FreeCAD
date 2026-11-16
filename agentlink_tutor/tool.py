# SPDX-License-Identifier: LGPL-2.1-or-later
"""The agent's tutor tool: lessons listed, started (by id, or written on the
fly), and walked in demo or guided mode, answering the lesson's compact
state (under 600 characters).

    {action: list|start|next|back|hint|skip|do|stop|status|explain,
     lesson?, mode?: demo|guided, query?, detail?, on?}

The lesson in hand is the Tutor tab's too (live.py): the person's buttons
and the agent's calls move the same lesson.
"""
import json

from . import engine as engine_mod
from . import lessons, live
from .point import Refusal

LIST_MAX = 12


def _tools_of(session):
    srv = getattr(session, "server", None)
    return set(getattr(srv, "tools", None) or ()) or None


def call_for(session):
    """call(tool, args) -> (refused, answer) through the session's server, as
    the agent's own calls go (the echo shows each, one undo step each)."""

    def call(tool, args):
        srv = getattr(session, "server", None)
        if srv is None:
            raise engine_mod.TutorError("no Agent Link server to call tools through")
        r = srv.call({"name": tool, "arguments": args})
        return bool(r.get("isError")), json.loads(r["content"][0]["text"])

    return call


def _here():
    """(FreeCAD version, Agent Link API, workbenches) where known."""
    ver = api = benches = None
    try:
        import FreeCAD

        ver = ".".join(FreeCAD.Version()[:3])
        if FreeCAD.GuiUp:
            import FreeCADGui

            benches = list(FreeCADGui.listWorkbenches())
    except Exception:  # noqa: BLE001
        pass
    try:
        from agentlink import hooks

        api = hooks.API
    except Exception:  # noqa: BLE001
        pass
    return ver, api, benches


def find(lib, ref):
    """A lesson by its id, or by the last part of it when only one
    lesson's id ends so."""
    have = lib.lessons()
    if ref in have:
        return have[ref]
    ends = [k for k in have if k.endswith("." + ref) or k.rpartition(".")[2] == ref]
    if len(ends) == 1:
        return have[ends[0]]
    raise Refusal("not_found", f"no lesson {ref}; tutor {{action: \"list\"}} lists them" + (f" (several end so: {', '.join(ends)})" if ends else ""))


def tutor(a, session, lib, progress=None):
    action = a.get("action") or "status"
    mode = a.get("mode")
    c = live.controller()
    try:
        if action == "list":
            ver, api, benches = _here()
            rows = lib.listing(progress or lessons.Progress(), ver, api, benches)
            q = str(a.get("query") or "").lower().strip()
            if q:
                ls = lib.lessons()
                rows = [r for r in rows if q in r["id"].lower() or q in r["title"].lower()
                        or any(q in t for t in ls[r["id"]].get("tags") or ())]
            out = {"lessons": rows[:LIST_MAX]}
            if len(rows) > LIST_MAX:
                out["more"] = len(rows) - LIST_MAX
            if c is not None and c.stepping:
                out["running"] = f"{c.e.lesson['id']} step {c.e.position()}"
            return out
        if action == "explain":
            if not isinstance(a.get("on"), bool):
                raise Refusal("invalid_input", "explain: on, true or false")
            if c is not None and c.e.state in ("step", "done"):
                return c.act("explain", on=a["on"])
            from . import prefs

            return {"explain": "on" if prefs.set_explainers(a["on"]) else "off"}
        if action == "start":
            ref = a.get("lesson")
            if isinstance(ref, str) and ref.strip().startswith("{"):
                ref = json.loads(ref)
            if isinstance(ref, dict):
                lesson = lessons.inline(ref, tools=_tools_of(session))
            elif isinstance(ref, str) and ref:
                lesson = find(lib, ref)
            else:
                raise Refusal("invalid_input", "start: lesson, an id from tutor {action: \"list\"} or an inline lesson {id: \"inline.x\", title, steps: [≤8]}")
            if c is not None and c.stepping:
                c.act("stop")
            c = live.new(lesson, call=call_for(session), doc=lambda: getattr(session, "doc", None),
                         out_dir=getattr(session, "out_dir", None), session=session, progress=progress)
            return c.start(mode or "guided")
        if c is None or c.e.state not in ("step", "done"):
            raise Refusal("invalid_state", "no lesson running: tutor {action: \"list\"}, then {action: \"start\", lesson}")
        if c.e.state == "done" and action not in ("status", "stop"):
            raise Refusal("invalid_state", "the lesson is done: start another, or status")
        out = c.act(action, mode=mode, detail=bool(a.get("detail")), on=a.get("on"))
        if action == "stop":
            live.set_controller(None)
        return out
    except (engine_mod.TutorError, lessons.LessonError) as e:
        raise Refusal("invalid_state" if isinstance(e, engine_mod.TutorError) else "invalid_input", str(e)[:300])
    except ValueError as e:  # an inline lesson's JSON
        raise Refusal("invalid_input", f"lesson: {e}"[:300])
