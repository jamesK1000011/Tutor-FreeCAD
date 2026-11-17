<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# Tutor-FreeCAD: round-4 picture review of `tutor_point` — findings and fixes

Source: the hub's `docs/hardening/window-r4-ws-tex-tutor-findings.md` (Tutor section: 4 pictures, 0 good, 1 minor,
3 bad) and `docs/hardening/round6-findings.md` section 9 ("what Tutor must change"). Line numbers are those of
`main` 11d7128. Nothing here ran on FreeCAD or in a Qt window: the checks are stand-in tests
(`tests/test_r4_review.py`, 27 tests) and FreeCAD 1.1.3's source.

Tests: `timeout 295 python3 -m pytest -q tests` with Agent Link's checkout on the path (`AGENTLINK_SRC`): 327 passed,
5 skipped (300 / 5 before). Without it: 303 passed, 27 skipped, and the same 2 failures as before this change
(`test_window_prep` Dropdown and ComboView import `agentlink.targets`).

## 1. A tree target ringed the "Model" tab, not the PointBox row (picture 0002)

**Cause.** `agentlink_tutor/window.py:409-417` (`Window.tree_row`): when no tree that holds the document is in
front, the Model tab's header is ringed and `MODEL_TAB` said; `window.py:473` does the same after the row is found.
The Tutor lives in Agent Link's dock, which is in front while it runs, so this was the answer every time.
`tutor_point` never changed the window (by design until now).

**Second cause, found by the new tests.** `agentlink_tutor/targets.py:341`: `note == getattr(win, "MODEL_TAB",
None)` is True for a row found with no note on a `Window` (which has no `MODEL_TAB` attribute): "Open the Model tab."
joined the callout of every tree row that was ringed.

**Change.**
- `gui_run.model_front(win, obj, ancestors)`: when obj's Model tree is not in front, `Gui.Control.showModelView()`
  (FreeCAD 1.1.3 `src/Gui/Control.cpp` 130-146: the Tree view or Model dock's `show(); raise()`), Qt let run;
  still behind: `UI.bring` (the dock's own steps); still behind: the dock's tab in the main window's QTabBar
  (`window.dock_tab`, as `ControlSingleton::findTabBar`) made current. Then `gui_run.scroll_row` scrolls the row
  `tree_row` will ring (its own, or its nearest folded parent's) into view with `scrollToItem`. No focus, cursor,
  unfold or selection.
- `Window(hands=True).prepare_tree(obj)` calls it; only `tutor_point` makes its Window with hands
  (`fam_tutor.py`). A lesson's Window has none: demo already prepares through `gui_run.UI`, guided still tells the
  person (the `tutor` tool's description says so).
- `point._prepare` runs it for each tree target before resolving; the answer has `prepared` (left out when nothing
  was done). If nothing could bring the tab forward, the tab is ringed and "Open the Model tab." said, as before.
- `targets._tree`: the `MODEL_TAB` text only for a real note.
- `tutor_point`'s description says it now does this one thing to the window (lengthened, nothing taken out).

**How sure.** High that this was the cause (the hub's round-6 reading and the code agree). Medium that
`showModelView` alone brings the dock forward on the Mac: it calls `raise()` on the QDockWidget, which Qt turns into
the tab switch for a tabified dock; the tab-bar fallback covers it if not.

**Live check.** `tutor_point {targets: [{tree: "PointBox"}]}` with the Tutor tab in front: the Model tab comes
forward, the PointBox row is ringed, the answer has `prepared: ["the Model tab brought to the front"]` and no
"Open the Model tab." in the callout. A long tree: also "PointBox row scrolled into view".

## 2. The text bubble was cut off (pictures 0002, 0009)

**Cause.** `agentlink_tutor/bubble.py:319`: the label's height was `heightForWidth(width)`; its padding (9 px) and
border (2 px) are set in its stylesheet (`bubble.py:190`), and Qt does not count stylesheet padding in a
word-wrapped rich-text QLabel's `heightForWidth`, so the label was too short by about 22 px plus the wrap that the
narrower content width adds.

**Change.** `bubble.text_height`: a `QTextDocument` with the label's font and the same rich text,
`setTextWidth(width - 2 * (PAD + BORDER))`; `bubble.fit_height`: that height plus `2 * (PAD + BORDER)`, never less
than Qt's own `heightForWidth`, Qt's size hint only when neither can be told. The document keeps its default margin,
so the measure can only be a few px too tall, never too short (the label is top-aligned).

**How sure.** High (it is the hub's own diagnosis, and the measure is independent of the stylesheet).

**Live check.** A long `say` (three wrapped lines and a why line): every line shows, a band of at most about 8 px
under the last.

## 3. The face pointer was missing with nothing said (pictures 0001, 0002)

**Cause.** The view did not frame the box: Texturizer's preview of another document sat in it (Texturizer's own
fix). But the Tutor said nothing: `agentlink_tutor/point.py:146-159` lit the face through the annotation layer
and counted it as shown whenever `ann.light` answered `lit`, whether or not any of it was on screen.

**Change.**
- `Window.light_seen(obj, subs)`: before the light is drawn (a pick could otherwise hit the tint itself), it checks
  that the 3D view in front is the object's document's (`FreeCADGui.ActiveDocument`, which the annotation layer
  draws in, and `bubble.view_widget`), then takes Agent Link's own badge candidates (`annotate.candidates`) and asks
  the view where each falls (`getPointOnScreen`, `getSize`) and what shows there (`getObjectInfo`, 60 picks at most).
  Answers None (seen) or why: "off-screen: no point of Face6 is inside the 3D view (the view does not frame
  PointBox)", "hidden: something else is drawn over Face6 at all 12 of its points inside the 3D view", or "the 3D
  view in front shows X, not Y". It answers None (as before) when it cannot tell (an older Agent Link).
- `point._light`: an unseen face or edge is still lit (turned into view, it shows), but `Found.unseen` makes it
  count as missing: `why: "lit, but not seen: …"`, and the callout gets "Push Fit all (V, F) to see the lit face ①."
  or "Turn the 3D view to see the lit face ①.". The light step now runs before the callout is built.

**How sure.** High for "never silent". Medium for the pixel test: `getPointOnScreen` and `getObjectInfo` both use the
viewport's pixel coordinates (FreeCAD 1.1.3 `View3DInventorViewer::getPointOnViewport`,
`View3DInventorPy::getObjectInfo`), as Agent Link's `annotate.visible_point` already assumes; a node that is no
document object (a preview) picks as None and so counts as covering, which is wanted here.

**Live check.** With the Texturizer preview leak (or a view panned away): `tutor_point {targets: [{face: {normal:
[0,0,1]}, of: "PointBox"}]}` answers the face in `missing` with "off-screen" or "hidden", and the callout says Fit
all. After Fit All: in `shown`.

Not done: the bubble's arrow for a face still keeps to the view's top edge (`bubble.target_rect` has no rect for a
lit face); "bubble anchored top left" from round 3 stays open.

## 4. Timers and deferred calls (FreeCAD crashed once when a timer fired on a deleted object during `Gui.updateGui()`)

**Inventory on `main`.** Every deferred call was a bare `QTimer.singleShot(ms, functor)`, with no context object, so
none was ever stopped and none checked what it touched:
- `bubble.py:398` the bubble's self-checks (400 and 1500 ms), touching the label and its 3D view;
- `bubble.py:417` `hide_after` (`tutor_point`'s ms), touching the label;
- `gui_run.py:21` the lesson's timer (`run.Controller._later`, `run.py:317`): auto-advance, debounce, the 30 s hold
  after the end, each calling `show` (rings and the bubble) — and an old lesson's hold could clear the next one's;
- `fam_tutor.py:27` `tutor_point`'s ms: the lit faces cleared.
`Gui.updateGui()` at `gui_run.py:119` (`UI.settle`) and `gui_run.py:263` (`UI._update`), and `window.py:377`
(`processEvents`) run the event loop, where any of these can come due. The Tutor tab's `_changed` and the badge also
touched widgets without a validity check.

**Change.** New `agentlink_tutor/later.py`: `after(ms, fn, target=None, group=None)` makes a `QTimer` whose parent
is the target widget when there is one (Qt deletes it with the widget: it never fires) or else one long-lived
QObject of the Tutor's, a child of the application. Before it runs, `shiboken6.isValid` must hold for the timer,
its parent and the target; a call that raises is caught (said on stderr), so nothing raises into Qt's event loop
during `updateGui`. Handles have `stop()`. Every deferred call above goes through it; `run.Controller` keeps its
handles and `cancel_later()` stops them when `live.set_controller` replaces the lesson. The bubble's self-check
returns at once when the label or its view is gone; `hide()` and `_widgets()` skip a deleted label; the tab and the
badge check validity first.

**How sure.** That these timers could touch a deleted widget: certain from the code. That one of them was the crash:
not proved (the crash log was not available here; Agent Link's own timers and other add-ons' fire in the same
`updateGui`). The change removes every way the Tutor's own could.

**Live check.** Start a lesson, close the lesson document's 3D view within 1.5 s of a step showing its bubble, and
start a second lesson within 30 s of finishing one: no crash, no "deferred call failed" on stderr, the second
lesson's rings stay.
