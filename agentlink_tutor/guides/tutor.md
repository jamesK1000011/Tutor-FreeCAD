<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Tutor: lessons in the person's own window

The Tutor teaches FreeCAD with lessons: data files, each a list of steps. A
step says what to do, rings the controls, checks the document and can be
done for the person. `tool_groups enable: ["tutor"]` gives `tutor`,
`tutor_point` and `tutor_watch`.

## workflow
1. `tutor { action: "list" }` lists the lessons this FreeCAD can run; `query` narrows it (a word of the title, the id, a course or a tag: `wiki` gives the lessons adapted from FreeCAD wiki tutorials). Only installed add-ons add rows (`from`).
2. `tutor { action: "start", lesson, mode }`: `guided` (the person does each step) or `demo` (you do each step with the lesson's own calls). The first answer can carry `document` (where the lesson works) and `credit` (where an adapted lesson comes from). Say the credit to the person once.
3. In guided mode, wait: the rider line (`tutor: step 3/8 passed`) tells you when a step passes. Never hurry the person; a step never times out.
4. `hint` climbs the ladder (where to look, the field, the value). `do` is "Do it for me" for the step in front, on every step. `mode` switches at any step.
5. At the end the answer is `step: "done"` with `final`, the last step's check.

## words to the person
- Name a ringed control by its number as the callout does (①, ②), never by its colour alone.
- Keep to the lesson's words (Simplified Technical English): one instruction a sentence, the names of controls in bold.
- A step's `picture` (shown in the Tutor tab) has its words in `picture`: read them to a person who cannot see it.

## the lesson library
- First steps: pad a sketch, a pocket and a hole, export an STL, a fully constrained sketch, a fillet and a chamfer, a parameter, a TechDraw page, a fixed joint.
- Adapted from the FreeCAD wiki (CC BY 3.0, "FreeCAD wiki contributors", each with its credit): Basic Part Design, Basic TechDraw (chapter 2 of the same course: it builds the part through the tools when the document does not hold it), the film hinge of the Sketcher examples, Basic Attachment, Whiffle Ball, Basic Sketcher (the star), the crank and slider of the Assembly workbench (two chapters: the parts in Part, then the assembly), Configuration Tables (a hex nut, M10 and M12).
- Add-ons ship their own (Workshop: hole for hardware).

## inline lessons
`start` takes a lesson you write: `{id: "inline.x", title, steps}`, 30 steps at most; a longer job goes in batches (`setup: {after: <the batch before>}`). Each step: `{id, say, why?, targets, do: [{tool, args}], check}`. The check reads what was made, never how: `new`, `exists {type, where}`, `prop`, `volume`, `bbox {size, min}`, `sketch {closed, full, dims}`, `expr {uses}`. `volume` and `bbox` take a query (`{type: "Part::Feature"}`) when the object's name is not known. An inline lesson has no pictures and no files.

## traps
- A step only the window can tell (a workbench switch) stays `pending` without a window; its `do` needs the window.
- A chapter after another goes on in the document in front when it passes that chapter's `result`; else it makes a new document and does the chapters before through their steps' calls.
