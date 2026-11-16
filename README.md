<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Tutor for FreeCAD

An agent teaches FreeCAD in your own window. It can explain a control, point
at it, do a job step by step while saying why, or guide you through the job
and check each step as you do it. It never moves your cursor, opens menus
for you or covers the screen: your hands stay on the controls.

Tutor is an add-on for [Agent Link for FreeCAD](https://github.com/jamesK1000011/AgentLink-FreeCAD)
and needs it installed. It is not a workbench: it adds a Tutor tab to Agent
Link's panel and tutor tools for the agent.

Status: early. The lesson engine, its checks and three starter lessons are
here (pad a sketch, cut a pocket and drill a hole, export an STL), with the
Tutor tab and `tutor_point`, which rings the controls a step needs. Guided
and demo modes (each step checked as you go, "Do it for me") and watch mode
come next.

## For the agent

`tool_groups enable: ["tutor"]` lists `tutor_point`: `{targets: [spec],
say?, ms?, clear?}`. A spec is one of `{cmd}`, `{menu: [titles]}`, `{wb}`,
`{task: label | {name, label, button}}`, `{tree}`, `{face: query, of}`,
`{edge: query, of}`, `{sub, of}`, `{dock}`, `{view: "3d"}` or `{ext}`. The
answer lists what is shown and, for the rest, why not. It never switches
workbench: when a toolbar is hidden it says so, and the agent may call
`workbench activate` first.

## Lessons

A lesson is a data file (`agentlink_tutor/lessons/*.lesson.json`, checked
against `agentlink_tutor/data/lesson.schema.json`): steps with what to say,
what to point at, how to check the step is done, and how to do it for you.
Lessons hold no code. Other add-ons can ship their own lessons.

## Privacy

- Watch mode (the agent following what you do) is off by default. You turn
  it on, and a visible badge shows while it runs.
- What it sees stays in FreeCAD's memory. It is never written to disk or
  sent anywhere, except in answers to the agent's own calls.
- Your lesson progress is kept in FreeCAD's settings on this computer only.

## Tests

    python3 -m pytest -q tests

The replay tests need FreeCAD and an Agent Link checkout (`AGENTLINK_SRC`, or
`agentlink-freecad` beside this folder); the rest run with plain Python.

## Licence

LGPL-2.1-or-later. Not affiliated with or endorsed by the FreeCAD project or
the FPA.
