<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# What the Tutor offers other add-ons

Agent Link's own hooks are in its `docs/hooks.md`. This page is the
Tutor's side: how another add-on ships lessons and teaches its own tools.
Nothing here needs code in Agent Link, and Agent Link names no add-on.

## Lessons from an add-on

A lesson is data: one `<name>.lesson.json` (the schema is
`agentlink_tutor/data/lesson.schema.json`), and pictures beside it in
`pictures/`. An add-on ships its lessons in one of three ways:

1. A `lessons/` folder beside its `agentlink_families` module. The Tutor
   finds it when Agent Link has loaded that module (not when Agent Link
   left it out for its API).
2. The folders its `agentlink_families` module names in `LESSONS`
   (a folder name or a list), beside the module.
3. `hooks.service("lessons").register_folder(folder, owner)` at load time.

Each lesson's id starts with the add-on's package name
(`workshop.make.hole-for-hardware`); the Tutor refuses one that does not, and
a second lesson with an id already taken. Each is held to the same rules as
the Tutor's own: the schema, the writing rules (Simplified Technical
English), the hint ladder, the check vocabulary and the tools Agent Link has.
Workshop ships `workshop/lessons/hole-for-hardware.lesson.json`;
`docs/examples/workshop/` keeps a copy for the Tutor's tests.

### No cost until installed

An add-on's lessons cost the agent nothing until that add-on is installed
and the agent asks for the list (`tutor {action: "list"}`, which names the
add-on in `from`). No tool description names a lesson
(`tests/test_chapters.py::NoCostUntilInstalled`).

## Credit and licence

A lesson adapted from another work carries a `credit` block: `source`
(the page), `authors`, `licence` (`CC-BY-3.0` for the FreeCAD wiki,
`CC-BY-4.0` for the FreeCAD Manual), `link`, `adapted: true` and, in short,
`changes`. The Tutor shows the credit with the lesson's first step and in
its tab. An add-on that ships such lessons lists each lesson and picture in
its REUSE.toml with that licence, and ships the licence text beside its code
licence (the Tutor: `LICENSE-Code`, `LICENSE-Assets`).

A step's `picture` is `{file: "pictures/x.png", alt}`; `alt` is the words a
screen reader says. A lesson whose picture is not in its folder is refused.
A raster picture is looked at for personal data before it is committed
(`.github/privacy/images.txt`).

## Checks and targets of an add-on's own

- `hooks.register_reader("tutor_check", fn(kind, spec, ctx))`: a check kind
  of the add-on's own; answer a `(status, why)` or `None` when the kind is
  not yours.
- `hooks.register_reader("tutor_target", fn(spec, window))`: a target of the
  add-on's own (a control in its panel), named in a lesson as `{ext: …}`.

## Guides

The Tutor's guide for the agent is `agentlink_tutor/guides/tutor.md`
(`guide_read tutor`), registered by Agent Link as every add-on's `guides/`
folder is.
