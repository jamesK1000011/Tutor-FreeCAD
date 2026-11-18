<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Tutor for FreeCAD

An agent teaches FreeCAD in your own window. It can explain a control, point
at it, do a job step by step while saying why, or guide you through the job
and check each step as you do it. It never moves your cursor, opens menus
for you or covers the screen: your hands stay on the controls.

Tutor is an add-on for [Agent Link for FreeCAD](https://github.com/jamesK1000011/AgentLink-FreeCAD)
and needs it installed. It is not a workbench: it adds a Tutor tab to Agent
Link's panel and tutor tools for the agent.

<!-- screenshot: the pocket lesson's first step, guided: the callout over the 3D view with its arrow to the ringed New Sketch button, the Tutor tab beside the tree -->

## Install

Tutor is not in the Addon Manager's own catalog yet. Add it, and Agent
Link, as custom repositories:

1. In FreeCAD, open **Edit › Preferences › Addon Manager**.
2. Under **Custom repositories**, add both of these, branch `main`:
   - `https://github.com/jamesK1000011/AgentLink-FreeCAD`
   - `https://github.com/jamesK1000011/Tutor-FreeCAD`
3. Open **Tools › Addon manager**, install **Agent Link**, then **Tutor**.
4. Restart FreeCAD. The Tutor tab is in Agent Link's panel.

<!-- screenshot: Addon Manager preferences with both custom repositories added -->

Add both repositories. Tutor depends on the add-on "Agent Link"; when Agent
Link's repository is not in the list, the Addon Manager takes that name for
a Python package, and the install fails.

Needs FreeCAD 1.1 or newer and
[Agent Link for FreeCAD](https://github.com/jamesK1000011/AgentLink-FreeCAD).

## What it does

Status: early. Eight starter lessons (pad a sketch; cut a pocket and drill
a hole; export an STL; constrain a sketch fully; a fillet and a chamfer; a
parameter driving a dimension; a TechDraw page of a body; an assembly with
one grounded part and a fixed joint) and five lessons adapted from FreeCAD
wiki tutorials (see [Lesson library](#lesson-library)) run in two modes,
switchable at any step:

- **Guided**: you do each step. Its controls are ringed, and the step is
  checked as you work (after a recompute, an undo, a selection, a workbench
  switch, or a call of the agent's); 0.6 s after it passes the lesson goes
  on by itself. The next tutor call goes on first when that pass still
  waits, so a batch of do, do, do walks the steps. Hint climbs a ladder: a nudge, then only the exact field
  ringed, then the exact value, then "Do it for me".
- **Demo**: Claude does each step with the ordinary tools while you watch
  (each call is one undo step), the callout saying what and why, and waits
  for Next before the following one.

A known wrong turn (Pocket for Pad) takes a short detour to put it right.
A course goes chapter by chapter: a chapter starts where the one before
ended, in the document in front when it holds that chapter's result, else
in a new one where the chapters before are done for you first.
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
last part, `pad-sketch`) or an inline lesson of 30 steps or fewer
(`{id: "inline.x", title, steps}`, schema-checked, its calls checked against
the tools there are, its words held to the same writing rules as stored
lessons); a longer job goes in batches, each inline lesson with
`setup: {after: "<the id before>"}` (a stored chapter may come before one
too); `list` names an add-on's lessons with `from`, a course chapter with
`course`, and keeps its answer short (`more`, and a query narrows it); `mode` with another action switches mid-lesson; `do`
is "show me this one". Each answer is the lesson's compact state, under 600
characters: `{lesson, mode, step: "3/5", id, say, check: pass|fail|pending,
why?, hint: 0-3, hint_text?, do_it?, did?, targets: {resolved, missing}}`.
While a lesson runs, a rider line (`tutor: step 3/5 passed; now step 4/5
pending`) joins the agent's other answers when the step's state changes; a
step once passed stays passed when a later re-check cannot be told
(`pending`), so the rider and `status` agree. At the end the answer is
`{step: "done", finished: "lesson complete", final: {step, check, why?}}`
(the last step's check, such as "the part follows size") and the rider says
`tutor: lesson complete, final check passed`.

`start` works in the open document when it is empty; when it holds other
work, the lesson's `doc_new` makes a new document whose name no open
document and no recently saved file has (`PartDesignTutorial_2`), and the first step's
answer says which (`document`). A chapter after another goes on in the open
document when it passes that chapter's result.

In demo mode, as each step comes up, the Tutor makes the window ready for
its targets the way a person following the lesson would have it, and the
answer lists what it did (`prepared`): the command's workbench activated
(through `workbench`, so the echo shows it) when its button shows nowhere,
the Tasks panel or a panel inside the Combo View brought to the front and
scrolled to the field, the object's parents unfolded in the tree. A step
whose check already holds as it comes up (a "Close" step with no sketch
open) is passed with nothing ringed (`targets.note: already done`). A last
check that cannot be told with a panel open gets a quiet window and one more
try. Guided mode changes nothing in the window: the callout tells the
person (`Switch to the Part Design workbench ①.` before the step, the
workbench selector ringed).

`tutor_point`: `{targets: [spec],
say?, ms?, clear?}`. A spec is one of `{cmd}`, `{menu: "PartDesign_Pad"}` (its path read from the window; titles in a list also work), `{wb}`,
`{task: label | {name, label, button}}`, `{tree}`, `{face: query, of}`,
`{edge: query, of}`, `{sub, of}`, `{dock}`, `{view: "3d"}` or `{ext}`. The
answer lists what is shown and, for the rest, why not. It never switches
workbench: when a toolbar is hidden it says so, rings the workbench selector
and puts "Switch to the … workbench." before the instruction, and the agent
may call `workbench activate` first. A command inside a toolbar dropdown
(found by its command name, else by its menu text) rings the dropdown's ▾
arrow, then the item once the menu opens; a button in a short toolbar's
overflow rings its » button. `{dock: "Property view"}` finds the panel
inside another dock (FreeCAD 1.1's Combo View, Model tab) and rings that
tab when it is not in front. A tree row is matched by its label under its
document's row (which may read the document's Label or Name, with a * or a
" : 1" at its end); when the Model tab is not in front (during a lesson the
Agent Link or Tasks tab is) that tab is ringed with "Open the Model tab."
first, and in demo mode it is brought to the front before the row is
unfolded or looked for. When FreeCAD has not filled in a folded branch yet,
the nearest folded parent's row is ringed with "Unfold the ringed row". A
row not found says which trees were searched, whether each showed and
whether it held the document's row.

## Lessons

A lesson is a data file (`agentlink_tutor/lessons/*.lesson.json`, checked
against `agentlink_tutor/data/lesson.schema.json`): steps with what to say,
what to point at, how to check the step is done, and how to do it for you.
Lessons hold no code. A command in a lesson's words is named by a token in
bold, `**{PartDesign_NewSketch|New Sketch}**`: the step shows the command's
menu text as this FreeCAD gives it (so the step and the window agree in
every release and language), and the words after `|` where FreeCAD cannot
be asked. The person never reads an internal name (`Sketcher::SketchObject`,
`PartDesign_Pad`): a lesson that writes one is not loaded. Their words are Simplified Technical English
(short imperative sentences, one instruction each; the rules are in
`agentlink_tutor/data/ste_rules.json`, after ASD-STE100 Issue 9), with an
optional one-line "why" per step that "Show explanations" turns on or off.
Hints climb a fixed ladder for every lesson: the
first says where to look, the second rings only the field, the third gives
the value; a lesson whose first or second hint gives the value away is not
loaded. A lesson may set its 3D view (`view`: isometric by default, or
front, top, …, or keep), and a step its own. A menu is named by its command (`{menu:
"PartDesign_Pad"}`), never by titles, which change between FreeCAD releases
and languages.

A step's check reads what was made, never how: an object of a type with
given values (`{exists: {type: "PartDesign::Hole", where: {ThreadSize:
"M4"}}}`), a property, a volume or size, a sketch's degrees of freedom
(`dof`, or `dof_max` for progress in any order), its dimensions, circles
and outside edges, values bound to a parameter (`{expr: "$sketch", uses:
"size", count: 2}`), and whether the part follows a parameter (`{follows:
"size", object: "$body", by: 5, axis: "x", change: 5}`: the parameter is
raised for a moment inside an undo transaction that is aborted, so the
document is left as it was). The full list is at the top of
`agentlink_tutor/checks.py`.

A lesson may be a chapter of a course (`course: {id, title, chapter}`,
`setup: {after: "<the chapter before>"}`, and its `result`, the check a
later chapter goes on from).

### Lesson library

Adapted from FreeCAD wiki tutorials, in Simplified Technical English, with
the wiki's pictures. Each lesson builds what it needs through the tools
(no example file), checks what you make, and carries its credit (source
page, "FreeCAD wiki contributors", licence, link, adapted):

| Lesson | From the wiki page | Steps | The end, as checked |
|---|---|---|---|
| `wiki.basic-part-design` | [Basic Part Design Tutorial](https://wiki.freecad.org/Basic_Part_Design_Tutorial) | 21 | a body of 18465.69 mm³, 53 × 26 × 26 mm |
| `wiki.basic-techdraw` | [Basic TechDraw Tutorial](https://wiki.freecad.org/Basic_TechDraw_Tutorial) | 10 | two pages: a view with a horizontal and a vertical dimension, a note, a projection group at scale 2 |
| `wiki.film-hinge-sketch` | [Sketcher Examples](https://wiki.freecad.org/Sketcher_Examples) (film hinge) | 8 | a fully constrained sketch; the line's length an expression of the arc's radius |
| `wiki.basic-attachment` | [Basic Attachment Tutorial](https://wiki.freecad.org/Basic_Attachment_Tutorial) | 12 | a block of 98000 mm³: a pad from a named constraint, a triangle hooked on by its attachment offset |
| `wiki.whiffle-ball` | [Whiffle Ball tutorial](https://wiki.freecad.org/Whiffle_Ball_tutorial) | 19 | the ball from Part booleans, filleted |
| `wiki.basic-sketcher` | [Basic Sketcher Tutorial](https://wiki.freecad.org/Basic_Sketcher_Tutorial) | 11 | a fully constrained star sketch, padded to 24247.5 mm³ |
| `wiki.crank-slider-parts` | [Assembly Workbench: Example crank and slider](https://wiki.freecad.org/Assembly_Workbench) | 6 | the four parts, each box and place checked (crank 2607.39 mm³, link rod 2450.27 mm³) |
| `wiki.crank-slider-assembly` | [Assembly Workbench: Example crank and slider](https://wiki.freecad.org/Assembly_Workbench) | 8 | an assembly with Base grounded and a revolute, a slider, a revolute and a cylindrical joint |
| `wiki.configuration-tables` | [Configuration Tables](https://wiki.freecad.org/Configuration_Tables) | 8 | a hex nut bound to a configuration table: 1203.53 mm³ as M10, 1807.6 mm³ as M12 |
| `wiki.fem-cantilever` | [FEM CalculiX Cantilever 3D](https://wiki.freecad.org/FEM_CalculiX_Cantilever_3D) | 5 | a CalculiX analysis (material, fixed, force, mesh) solved twice, the second time with 500 MN along x |
| `wiki.draft-tutorial` | [Draft tutorial](https://wiki.freecad.org/Draft_tutorial) | 13 | a frame, a hexagon, a circle, a polar array of the profile, dimensions of 43.301, 30, 25 and 15 mm |
| `wiki.arch-house` | [Arch tutorial](https://wiki.freecad.org/Arch_tutorial) | 11 | walls of 16.1275 m³ after a door and two windows, an inner wall and door, a slab, a column, a roof, two levels in a building |
| `wiki.surface-examples` | [Surface GeomFillSurface, Sections, BlendCurve](https://wiki.freecad.org/Surface_GeomFillSurface) | 8 | a GeomFillSurface, a Sections surface and a blend curve, each valid |
| `wiki.mesh-to-part` | [Mesh to Part](https://wiki.freecad.org/Mesh_to_Part) | 8 | three meshes, cube.stl written and read back, a solid of 1000 mm³ from the mesh |
| `wiki.cam-walkthrough` | [CAM Walkthrough for the Impatient](https://wiki.freecad.org/CAM_Walkthrough_for_the_Impatient) | 6 | a job with tool 4 at 2000 rpm, an outside profile, a pocket (step over 50 %, Offset) and G-code |
| `wiki.points-workbench` | [Points Workbench (and its command pages)](https://wiki.freecad.org/Points_Workbench) | 7 | a cloud from a cylinder, shaft.ply written and read back, a merged cloud and a structured cloud |

Basic Part Design and Basic TechDraw are the two chapters of one course
(`wiki-part-to-drawing`): the TechDraw lesson goes on from the part, and
builds it through the tools when the document in front does not hold it.
The crank and slider is a course of two chapters (`wiki-crank-slider`): the parts, then the assembly.
`tutor {action: "list", query: "wiki"}` lists them.

### Lessons from other add-ons

An add-on ships lessons in a `lessons/` folder beside its
`agentlink_families` module (or the folders its `LESSONS` names), each
lesson's id starting with the add-on's package name
(`workshop.make.hole-for-hardware`). The Tutor lists and plays them with
its own, checked by the same rules; nothing in Agent Link is needed. An
add-on may also hand a folder over by name:
`hooks.service("lessons").register_folder(folder, "mypackage")`.
`docs/examples/workshop/lessons/hole-for-hardware.lesson.json` is the
lesson Workshop carries (an M4 countersunk hole through a plate, checked by
the hole's type and size).

## Accessibility

- The Tutor tab works from the keyboard alone: Tab goes through every
  control in reading order, and the lesson's buttons have keys that work
  anywhere in the tab (Alt is Option on macOS): Alt+Shift+Right Next,
  Alt+Shift+Left Back, Alt+Shift+H Hint, Alt+Shift+K Skip, Alt+Shift+D Do it
  for me, Alt+Shift+Q Stop, Alt+Shift+Return Start, Alt+Shift+A to the
  question box. Each tooltip says its key. None is one of FreeCAD's own
  keys (Alt+Return opens Properties, Alt with a menu's letter opens that
  menu).
- A ring is never told by its colour alone: each has its number (①, ②),
  and the instruction names it.
- A step never times out: it waits for you. "Do it for me" is on every
  step.
- A step's picture has words for a screen reader, and every label of the
  tab has a name.
- A screen reader has a name and a description for every control, and
  hears the step when it changes.
- The tab sets no colours: its contrast is your theme's. The callout over
  the 3D view keeps at least 4.5:1 for its words (3:1 for its edge) in a
  light or a dark theme.
- **Text size** (100 to 200 %) scales the words in the tab and the
  callout.
- **Reduce motion** frames the part once, at the start, without the
  view's animation, and keeps the camera still between steps.

## Privacy

- Watch mode (the agent following what you do) is off by default. You turn
  it on, and a visible badge shows while it runs.
- What it sees stays in FreeCAD's memory. It is never written to disk or
  sent anywhere, except in answers to the agent's own calls.
- Your lesson progress and your Tutor settings (explanations, text size,
  reduce motion) are kept in FreeCAD's settings on this computer only.

## Callout

The callout sits over the 3D view, on the edge nearest what it points at
(under the toolbars for a toolbar button), with an arrow to the ring, so it
covers no toolbar or panel. It shows the instruction (numbered when it has
more than one line), the why line apart in smaller, dimmer text, and, only
after you act or ask for a hint, why the step is not done yet. When the
lesson's 3D view is not in front, the words go to Agent Link's own callout
instead, and the agent's answers say which (`callout: bubble|overlay|none`).

A lesson works on its own document: setup makes it (or takes the one open
at start), brings its view to the front, and every step and check uses it,
whatever else is open.

## Tests

    python3 -m pytest -q tests

CI runs them on every push and pull request
([tests workflow](https://github.com/jamesK1000011/Tutor-FreeCAD/blob/main/.github/workflows/tests.yml)).

The replay tests need FreeCAD and an Agent Link checkout (`AGENTLINK_SRC`, or
`agentlink-freecad` beside this folder); the tutor tool's tests need the
checkout only; the rest run with plain Python. Guided mode is replayed end
to end by an agent with Agent Link's test flag `AGENTLINK_AS_USER=1`, which
takes the agent's calls as yours: for tests only, never for real use.

## Licence

The code, the starter lessons and the data files: LGPL-2.1-or-later
([LICENSE-Code](https://github.com/jamesK1000011/Tutor-FreeCAD/blob/main/LICENSE-Code)).
The lessons adapted from the FreeCAD wiki and their pictures: CC BY 3.0, by
FreeCAD wiki contributors, adapted
([LICENSE-Assets](https://github.com/jamesK1000011/Tutor-FreeCAD/blob/main/LICENSE-Assets));
REUSE.toml names each file's licence. Not affiliated with or endorsed by the
FreeCAD project or the FPA.
