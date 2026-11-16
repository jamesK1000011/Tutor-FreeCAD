<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Changelog

All notable changes to Tutor for FreeCAD. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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

- A step that passed and was undone counts as not done again.
- From the first live run of T3 on the Mac (FreeCAD 1.1.3): a lesson's setup leaves the window quiet (the sketch it drew closed, no task dialog, nothing selected), so the person can press Pad; in demo mode a step whose controls are in a task panel opens that feature's panel first, so its field and OK are ringed and the person sees them before Next sets the value; the callout shows `**Pad**` as Pad; a workbench is named as its selector names it ("Sketcher is the active workbench, not Part Design"); a Model tree row is found again when FreeCAD rebuilds the tree (a deleted tree or row was kept and failed); a menu target may be the command's name (`{menu: "PartDesign_Pad"}`), its path read from the window, and the starter lessons use that (1.1.3's Part Design menu has "Additive Features", not "Create an additive feature").
