<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Tutor for FreeCAD

An agent teaches FreeCAD in your own window. It can explain a control, point
at it, do a job step by step while saying why, or guide you through the job
and check each step as you do it. It never moves your cursor, opens menus
for you or covers the screen: your hands stay on the controls.

Tutor is an add-on for [Agent Link for FreeCAD](https://github.com/jamesK1000011/AgentLink-FreeCAD)
and needs it installed. It is not a workbench: it adds a Tutor tab to Agent
Link's panel and tutor tools for the agent.

Status: early. Three starter lessons (pad a sketch, cut a pocket and drill
a hole, export an STL) run in two modes, switchable at any step:

- **Guided**: you do each step. Its controls are ringed, and the step is
  checked as you work (after a recompute, an undo, a selection, a workbench
  switch, or a call of the agent's); 0.6 s after it passes the lesson goes
  on by itself. Hint climbs a ladder: a nudge, then only the exact field
  ringed, then the exact value, then "Do it for me".
- **Demo**: Claude does each step with the ordinary tools while you watch
  (each call is one undo step), the callout saying what and why, and waits
  for Next before the following one.

A known wrong turn (Pocket for Pad) takes a short detour to put it right.
Watch mode follows what you do without a lesson: turn on "Let Claude
watch" in the Tutor tab (or ask Claude to), and a sign shows in the status
bar while it is on. Claude then sees short events (a command used, an
object made, a panel closed, your questions from Ask Claude) and can help
as you work. In a lesson, a step can be checked on the command you used.

## For the agent

`tool_groups enable: ["tutor"]` lists `tutor`, `tutor_point` and
`tutor_watch`.

`tutor_watch`: `{since?, wait?: 0-25 s, until?: any|milestone}` while watch
mode is on: the person's events after `since` (`{n, k: cmd|wb|sel|clr|new|
del|rc|edit|done|undo|redo|save|ask, …}`, milestones `m: 1`), waiting up to
`wait` seconds for one (or for a milestone), and `next` for the following
call. It is answered on Agent Link's socket thread, so a long wait never
holds the window. `tutor {action: "watch", on}` turns watch mode on or off
when the person asks.

`tutor`: `{action: list|start|next|back|hint|skip|do|stop|status|explain,
lesson?, mode?: demo|guided, query?, detail?, on?}`. `start` takes a lesson's id (or its
last part, `pad-sketch`) or an inline lesson of 8 steps or fewer
(`{id: "inline.x", title, steps}`, schema-checked, its calls checked against
the tools there are); `mode` with another action switches mid-lesson; `do`
is "show me this one". Each answer is the lesson's compact state, under 600
characters: `{lesson, mode, step: "3/5", id, say, check: pass|fail|pending,
why?, hint: 0-3, hint_text?, do_it?, did?, targets: {resolved, missing}}`.
While a lesson runs, a rider line (`tutor: step 3/5 passed; now step 4/5
pending`) joins the agent's other answers when the step's state changes.

`tutor_point`: `{targets: [spec],
say?, ms?, clear?}`. A spec is one of `{cmd}`, `{menu: "PartDesign_Pad"}` (its path read from the window; titles in a list also work), `{wb}`,
`{task: label | {name, label, button}}`, `{tree}`, `{face: query, of}`,
`{edge: query, of}`, `{sub, of}`, `{dock}`, `{view: "3d"}` or `{ext}`. The
answer lists what is shown and, for the rest, why not. It never switches
workbench: when a toolbar is hidden it says so, and the agent may call
`workbench activate` first.

## Lessons

A lesson is a data file (`agentlink_tutor/lessons/*.lesson.json`, checked
against `agentlink_tutor/data/lesson.schema.json`): steps with what to say,
what to point at, how to check the step is done, and how to do it for you.
Lessons hold no code. Their words are Simplified Technical English
(short imperative sentences, one instruction each; the rules are in
`agentlink_tutor/data/ste_rules.json`, after ASD-STE100 Issue 9), with an
optional one-line "why" per step that "Show explanations" turns on or off.
Hints climb a fixed ladder for every lesson: the
first says where to look, the second rings only the field, the third gives
the value; a lesson whose first or second hint gives the value away is not
loaded. A lesson may set its 3D view (`view`: isometric by default, or
front, top, …, or keep), and a step its own. A menu is named by its command (`{menu:
"PartDesign_Pad"}`), never by titles, which change between FreeCAD releases
and languages. Other add-ons can ship their own lessons.

## Privacy

- Watch mode (the agent following what you do) is off by default. You turn
  it on, and a visible badge shows while it runs.
- What it sees stays in FreeCAD's memory. It is never written to disk or
  sent anywhere, except in answers to the agent's own calls.
- Your lesson progress is kept in FreeCAD's settings on this computer only.

## Tests

    python3 -m pytest -q tests

The replay tests need FreeCAD and an Agent Link checkout (`AGENTLINK_SRC`, or
`agentlink-freecad` beside this folder); the tutor tool's tests need the
checkout only; the rest run with plain Python. Guided mode is replayed end
to end by an agent with Agent Link's test flag `AGENTLINK_AS_USER=1`, which
takes the agent's calls as yours: for tests only, never for real use.

## Licence

LGPL-2.1-or-later. Not affiliated with or endorsed by the FreeCAD project or
the FPA.
