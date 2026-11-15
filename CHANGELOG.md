<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Changelog

All notable changes to Tutor for FreeCAD. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
