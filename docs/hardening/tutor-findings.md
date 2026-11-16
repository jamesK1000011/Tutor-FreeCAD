# Tutor-FreeCAD: hardening findings (tutor group, 3 tools) — 16 Nov 2026

Nothing here ran on FreeCAD or in a Qt window. Tests: `python3 -m pytest -q` with Agent Link's checkout on the path
(AGENTLINK_SRC, or PYTHONPATH): 296 passed, 9 skipped (293 before; 3 new). Without Agent Link on the path 2 tests fail
before and after this patch (they import agentlink.targets); that is how the repo was.

## The open fault: bike-stem-1 steps 13–14, "scrolled out of view"

**Cause, as far as code proves it.**

1. FreeCAD 1.1 has no Model | Tasks tab widget. FreeCAD 1.1 source: src/Gui/ComboView.cpp builds only a splitter (tree
   over property view); src/Gui/MainWindow.cpp registers Std_TaskView as a dock of its own; src/Gui/DockWindowManager.cpp
   tabs the docks together with `tabifyDockWidget`; src/Gui/Control.cpp (`ControlSingleton::aboutToShowDialog`,
   `showDockWidget`) raises the Tasks dock (`show(); raise()`) whenever a task dialog opens, and `findTabBar` finds a dock's
   tab by its title among the main window's QTabBars. So "the Model tab behind the Tasks tab" is the Model dock tabbed
   behind the Tasks dock by the main window. (Agent Link's own layout.py says the same of 1.1.)
2. The Tutor told "behind a tab" by `isVisible()` everywhere (`window._shown`): `Window.tree_row`, `model_tree`, `dock`,
   `task_widget`, and `front_steps` (a dock got a "bring forward" step only when `not isVisible()`).
3. In `gui_run.UI._tree_open`, a row that `tree_row` reported as found and unfolded took the early branch, which only
   scrolled (`scroll_to`) and never brought the tree's dock forward at all.
4. Qt keeps a dock that is tabbed behind another `isVisible() == True` and parks it outside the window (QDockAreaLayout /
   QWidgetAnimator; the usual way to tell is `visibleRegion().isEmpty()`). **This one link is from Qt's known behaviour,
   not from a source I could read here** (Qt's source is not in the references). It fits what was seen live: the two earlier
   fixes (9718e67 bring the Model tab forward, cadf739 scroll to the row) both pass their stand-in tests, in which a tab
   behind is modelled as not visible, and both did nothing live.

With 2–4 together: the parked tree reads as shown, its Sketch row is found and unfolded, `_tree_open` returns without
raising anything, and the row of a tree that is not on screen is handed to the overlay to ring.
Not explained: by my reading of agentlink/overlay.py a parked widget should come back "covered", not "scrolled out of
view" (`visible()` is asked before the row's rect). The fix does not depend on which of the two words the overlay uses.

**Fix (agentlink_tutor/window.py, gui_run.py).**

- `window.dock_tab(dock)`: the dock's tab in a main-window QTabBar, by title (as FreeCAD's `findTabBar`), a shown bar
  first. `window.behind(w)`: True when w's dock has such a tab in a shown bar and it is not the current one (a floating
  dock: False). `Window.front(w)`: visible and not behind. This holds whether Qt reports the parked dock visible or not.
- `front_steps`: a dock that is hidden **or behind** gets the ("dock") step; `UI.bring` already does `show(); raise_()`
  for it, which is exactly FreeCAD's own `showDockWidget`. No `setFocus`, `activateWindow`, cursor or full-screen call
  exists anywhere in the path.
- `tree_row`, `model_tree`, `dock`, `task_widget` use `front()`: guided mode now rings the Model (or Tasks) tab when the
  dock is behind, instead of a row that is not on screen.
- `_tree_open`: the Model tree's dock is brought forward first, in every case, then the row is looked for, unfolded and
  scrolled to. It answers "Sketch shown in the tree" when only the dock had to come forward.
- The same change fixes the mirror case (a task field while Tasks is behind Model): `_tasks_front` goes through `bring`.

**Tests added (tests/test_window_prep.py, class TabbedDocks, stand-ins):** a dock tabbed behind that still says
isVisible() is not in front, gets a dock step, and guided rings its tab; demo raises the Model dock once (show, raise; the
Tasks dock untouched) for a row already unfolded and then finds the row with no note; a hidden (unused) tab bar does not
count.

**Live check needed:** rerun bike-stem-1 in demo; steps 13 and 14 should answer `prepared: ["Sketch shown in the tree"]`
and `targets.resolved 1`. If the dock's tab text on the Mac is not the dock's windowTitle (a translated or renamed tab),
`dock_tab` finds nothing and behaviour is as before: say so and I would match by Qt's tab data instead. Also not
verified: whether bringing Model forward closes or hides an open task panel's fields the same step also rings (a step with
both a tree and a task target; bike-stem-1 has none).

## Per tool

| Tool | Checked against | Wrong and fixed | Still doubtful | Description |
|---|---|---|---|---|
| tutor_point | point.py, targets.py, lessons.TARGET_KINDS, window.py; FreeCAD 1.1 source src/Gui/ComboView.cpp, Control.cpp, MainWindow.cpp | "behind a tab" told by isVisible() (above); the old description said "dock finds a panel inside another dock's tab", which is 1.0's layout; refusal for more than 6 targets now says how to send the rest | The reply's `missing` words come from Agent Link's overlay (hidden, covered, scrolled out of view): listed from its code, not run | rewritten: every target kind, what is ringed in place of a control that is not on screen, every reply field |
| tutor | tool.py, run.py, engine.py (status, _fit), checks.py (EVAL kinds), lessons.py | demo's tree preparation (above); refusal for a finished lesson names the actions | "0.6 s after a pass" and the hint rungs are from the old text and run.py, not timed; batches (setup.after) not exercised | rewritten: actions, demo vs guided, what demo prepares (and that it takes no focus), inline lesson shape, all check kinds, every reply field |
| tutor_watch | tool.watch, observe.py (MAX 500, ANSWER_MAX 40, WAIT_MAX 25, COALESCE_S 0.3, MILESTONES) | `until` refusal says what each value does | Runs on Agent Link's socket thread (hooks.register_thread_tool): by code | rewritten: every event kind and field, limits, the 25 s wait against a client's time limit |

Index fields: `words` added to all three. No `workbench` (the Tutor has none of its own) and no `commands` (no tool does
the work of a FreeCAD command).

tests/test_point.py: the description length budget (2 550 characters for the three) is removed, per the owner's ruling;
the test still checks the format and now that each description names its reply and carries words.

## Proposed for the hub (not edited: outside this checkout)

- agentlink/layout.py `DockBar.current()` returns the first dock of the tab group whose `isVisible()` is true, with the
  comment "of a tab group only the dock in front is visible". If point 4 above holds, that is always the Model dock.
  The copy of layout.py in each add-on has the same line. Worth one live check (`mw.tabifiedDockWidgets`, then each
  dock's `isVisible()` and `visibleRegion().isEmpty()`), which would also settle point 4.

## No test model

The brief asks for none for this part (tutor.patch and tutor-findings.md only). The live proof is the lesson itself:
`tutor { action: "start", lesson: "bike-stem-1", mode: "demo" }`, then `next` through step 15, reading `prepared` and
`targets` at steps 12–14.
