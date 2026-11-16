<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Changelog

All notable changes to Tutor for FreeCAD. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Nothing yet.

## [0.1.0] - 2026-11-16

The first release (not tagged yet): Tutor, an add-on for Agent Link for
FreeCAD (API 1) on FreeCAD 1.1 that teaches FreeCAD in the person's own
window. Lessons are data files in Simplified Technical English; guided and
demo modes check each step and climb a hint ladder; `tutor_point` rings
controls and lights faces; watch mode follows the person's work when they
turn it on; the Tutor tab sits in Agent Link's panel; three starter lessons
(pad a sketch, cut a pocket and drill a hole, export an STL).

### Fixed

From the guided live run of the pocket lesson (FreeCAD 1.1.3), as rules for every lesson:

- A step starts quiet: the callout and the Tutor tab show only the instruction and its why line. Why the step is not done ("Not yet: …") shows only once the person has acted since the step began (an event of theirs, a call of theirs, a call that changed the document, Do) or asked for a hint. The agent's answers still carry the check's result.
- No internal names in anything the person reads: type ids and command names become plain words in one place (`words.py`: Sketcher::SketchObject is "sketch", PartDesign::Pad "pad", a task panel "the pad task panel", a command its menu text, a property "Use custom vector"). A test runs every lesson, step and hint rung, and every check's failure, and scans what the person would read; a lesson that writes an internal name is not loaded.
- The callout's layout (`callout.py`, for lessons and `tutor_point` alike): each sentence of the instruction its own line, numbered only when there is more than one line; a target's own words (the ▾ menu of a toolbar dropdown) as the next numbered line, naming its badge (②); the why line its own paragraph, smaller and dimmer; then the hint or why not yet. No "2." without a "1.".
- Step words name a command as this FreeCAD does: a lesson writes `**{PartDesign_NewSketch|New Sketch}**`, and the step shows the command's live menu text (`Gui.Command.get(name).getInfo()['menuText']`, & and … taken off), the words after `|` where FreeCAD cannot be asked. The starter lessons use it (the pocket lesson said "Create sketch" where 1.1.3's menu says "New Sketch"). Every command name the targets give is its cleaned menu text.
- The callout no longer covers the toolbars: it is drawn over the 3D view (a child of the view's window, as Agent Link's caption is; the overlay cannot draw there on the Mac), on the view's edge nearest its target, under the toolbars for a toolbar button and at the left edge for the Tasks panel, kept off the navigation cube, with an arrow to the ring (`bubble.py`, placement in `callout.place`). Where there is no 3D view, the overlay's callout as before.
- Check and tab words follow the writing rules: "push OK", "task panel".

### Added

- An icon (`agentlink_tutor/icons/Tutor.svg`, a mortarboard over a cube, drawn for Tutor), named in `package.xml`.
- README: an Install section (the Addon Manager's custom repositories: add both Agent Link and Tutor, or the dependency on "Agent Link" is taken for a Python package and the install fails), screenshot slots, links that work off GitHub.
- A tests workflow (`.github/workflows/tests.yml`): the headless suite on push and pull request, one job, one Python version, pip cached.
- Watch mode (T4): with "Let Claude watch" on in the Tutor tab (or `tutor {action: "watch", on}` when the person asks; off by default, a sign in the status bar while on), the person's events go into a ring buffer in memory (`observe.py`: commands used, workbench switches, selections, objects made and deleted, recomputes, a task panel opened and closed, undo, redo, save, and Ask Claude questions), the agent's own left out, selection and recompute bursts coalesced. `tutor_watch {since, wait 0–25 s, until: any|milestone}` answers them as a long poll on Agent Link's socket thread, never holding the window; a milestone (something finished) ends a wait early. The window's observers attach only while watch mode or a lesson needs them. A guided step's `used` check passes on the command the person used since the step began.
- Every lesson's words are checked as Simplified Technical English (`ste.py`, rules as data in `data/ste_rules.json`, a short subset of ASD-STE100 Issue 9 in our own words, not its dictionary): each sentence of a step's instruction one instruction, starting with an action verb (push for buttons, select, set, type …), at most 20 words; no passive, no -ing words, no filler words, no "then" joining two instructions, each number with its unit; UI names in bold taken as written. Stored lessons and the agent's inline lessons alike are refused with the reasons until they comply. The starter lessons are rewritten to pass.
- A step's optional `why`: one short explainer sentence (at most 15 words) under the instruction, in the callout and the tab. "Show explanations" in the Tutor tab (on by default, kept as `ShowExplainers` under BaseApp/Preferences/Mod/Tutor) and the tool's `{action: "explain", on}` switch it; the answers carry `explain: on|off` and send the why line (`because`) only while it is on, or with `detail`.
- Guided and demo modes (T3). The `tutor` tool (group `tutor`, not in the lean list): `{action: list|start|next|back|hint|skip|do|stop|status, lesson?, mode?, query?, detail?}`, a lesson by id (or the end of it) or inline (8 steps or fewer, schema-checked), answered as the lesson's compact state under 600 characters with what was ringed (`targets: {resolved, missing}`). Demo: next does the step through the ordinary tools (each call one undo step, the echo showing it), the callout saying what and why, and waits at the following step. Guided: the person does it; the step is checked after the agent's and the person's calls (Agent Link's `call_done`) and on the window's recompute, undo, redo, selection and workbench signals (debounced 300 ms) and on Next, and goes on by itself 600 ms after a pass; a pass right after the agent's own call is counted as done for the person. Modes switch mid-lesson; `do` is "show me this one". The hint ladder: a nudge, then only the exact field ringed, then the exact value (the step's third hint, or what its check wants: "Length = 15 mm; then press OK"), with "Do it for me". Branches take a known wrong turn's detour. While a lesson runs, a rider line (`tutor: step 3/5 passed; now step 4/5 pending`) joins the agent's other answers when the state changes.
- The Tutor tab: Guided or Demo (switchable at any step), the check's result in words, "Do it for me" on whenever the step can be done for the person, Next saying what it does in each mode; it follows the lesson as the agent's calls and the checks move it.

- From the first live pass on the Mac (FreeCAD 1.1.3): `tutor_point` takes `of` written inside a face or edge query and `at` (or `point`) for `near`, and a missing `of` says to put it beside the query; a lit face, edge or vertex carries its badge number in the 3D view; the Tutor tab's lesson list takes its own row (Start below it), a long title cut by the style with the whole title in its tooltip.
- `tutor_point` (group `tutor`, not in the lean list): rings the window's controls for the person with numbered badges and one callout, and lights faces, edges and vertices in the 3D view, through Agent Link's overlay and annotation services. Every target kind: a command's toolbar buttons, a menu path (the menubar title, then inside each menu as the person opens it; on the macOS menubar the path in words and the toolbar button), the workbench selector, a task dialog's field (its name, then the label it stands for) or button with the Tasks tab's header when that tab is behind, a Model tree row (a folded parent's row; never unfolded), a face, edge or sub-element, a dock, the 3D view, and an add-on's own kind (`tutor_target` readers). A target that cannot be shown says why ("toolbar hidden: Part Design is not the active workbench; call workbench activate first") and its words join the callout; nothing is switched, opened, unfolded, selected or focused. Each call replaces the highlights before it unless `clear: false`; no targets clears them.
- The Tutor tab in Agent Link's panel (between Notes and Steps): the lessons this FreeCAD can run, the step in front with its words and hint, the step's targets ringed, Back, Next, Hint, Skip and Stop, and Ask Claude, which leaves the question as a note for the agent. It follows the theme (no colours of its own). "Do it for me" is shown, off, until demo mode.
- The lesson format (`data/lesson.schema.json`) and its loader: lessons found
  per add-on folder, ids namespaced by package, a listing that hides lessons
  this FreeCAD cannot run, inline lessons of 8 steps or fewer, and progress
  kept as id@version in FreeCAD's settings.
- Step checks: a closed, read-only vocabulary (exists, absent, new, prop,
  valid, volume, bbox, sketch, file, selected, workbench, editing,
  task_open, used, all, any, not), each failure with a short why.
- The lesson engine: demo and guided modes, bindings to what the person
  made, a three-rung hint ladder, branches for known wrong turns, and a
  compact state under 600 characters.
- Three starter lessons: pad a sketch, cut a pocket and drill a hole, and
  export an STL, each replayed against FreeCAD in the tests.

### Changed

- A `cmd` target whose command sits inside a toolbar dropdown (FreeCAD 1.1.3's group commands: Sketcher's rectangles, arcs and circles, Part Design's primitives) rings the dropdown's button, says "open the ▾ menu of the ringed button", and rings the item inside once the person opens it (Agent Link's `targets.group_buttons` and the overlay's `watch_menu`); it had said "no toolbar button for it here". A plainly visible button is no longer called covered (Agent Link's overlay now asks the window what is under it).
- From the guided live run (FreeCAD 1.1.3), as rules for every lesson rather than fixes to one: the hint ladder is held by the lesson validator (`lessons.hint_problems`): hints 1 and 2 never say a value the step's check wants (a number or a file name), so a lesson that does is left out with the reason; the second rung rings the step's task field only (the first task target that is not a button, else the first target); a guided step whose controls are in a task panel that was closed while its feature exists (OK pressed with another value) rings the feature's row in the Model tree and says "Double-click <label> in the tree to change it."; after setup the lesson's 3D view is set (isometric unless the lesson's new `view` says otherwise, `keep` leaves the camera) and fitted, and a step lighting faces or edges comes up in that view (or its own `view`); a finished lesson keeps its last rings and lit faces for 10 s or until Stop; a Model-tree target is the row in the lesson's own document, never a same-named row of another open document, and when the Model tab is behind (FreeCAD shows Tasks after a workbench switch) its tab is ringed with "Open the Model tab". The second hints of the Pad and Pocket lessons no longer say the value.
- A step that passed and was undone counts as not done again.
- From the first live run of T3 on the Mac (FreeCAD 1.1.3): a lesson's setup leaves the window quiet (the sketch it drew closed, no task dialog, nothing selected), so the person can press Pad; in demo mode a step whose controls are in a task panel opens that feature's panel first, so its field and OK are ringed and the person sees them before Next sets the value; the callout shows `**Pad**` as Pad; a workbench is named as its selector names it ("Sketcher is the active workbench, not Part Design"); a Model tree row is found again when FreeCAD rebuilds the tree (a deleted tree or row was kept and failed); a menu target may be the command's name (`{menu: "PartDesign_Pad"}`), its path read from the window, and the starter lessons use that (1.1.3's Part Design menu has "Additive Features", not "Create an additive feature").
