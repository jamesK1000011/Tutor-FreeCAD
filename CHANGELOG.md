<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Changelog

All notable changes to Tutor for FreeCAD. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
