<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# What the Tutor needs from Agent Link core

The Tutor is an add-on. It reaches Agent Link only through what Agent Link
offers every add-on (`agentlink/hooks.py`, the `agentlink_families` module,
the guides folder). Phase T1 (the lesson engine, checks and starter lessons)
needs nothing new. Later phases need these generic hooks in core; none of
them names the Tutor.

## T2: pointing at things and the Tutor tab (done)

In Agent Link core since 15 Nov 2026 (API 1, additions only; core names
no add-on):

- **The overlay painter**, `hooks.service("overlay")`
  (`agentlink/overlay.py`): `show(specs, say, ms, owner)`, `menu(titles,
  badge, owner, handle)`, `flash(widget, ms)`, `clear(owner)`,
  `visible(widget)`, `colours()`. One transparent, mouse-transparent child
  of the main window; rings in the theme's accent with a black or white
  halo by the theme's lightness, numbered badges, one callout inside the
  window; hidden targets reported. Echo's lit buttons are drawn on it.
- **Target resolution helpers**, `agentlink.targets`: `command_for`,
  `actions` (QActions by `objectName`), `buttons`, `menus_of`,
  `associated`, `menu_path`, `native_menubar`, `workbench_of`.
- **`hooks.register_tab`** at order 15: the slot is kept free in core
  (`panel_tabs.CORE_TABS`); the Tutor tab takes it.
- **The coin annotation layer**, `hooks.service("annotations")`
  (`agentlink/annotate.py`): `light(obj, subs, owner, colour)`,
  `clear(owner)`; the panel's pins and Steps stage share its scene helpers.
- **Echo's skip list open to add-ons**: a family's `NO_ECHO` (names or
  prefixes), next to `batch`, `session_state`, `tool_groups` and
  `guide_read`; `echo.skipped(name)`. The tutor family declares `tutor`.

## T3: guided and demo modes (done)

In Agent Link core since 15 Nov 2026 (API 1, additions only; core names
no add-on):

- **The rider line**, `hooks.register_rider(owner, fn)` /
  `unregister_rider(owner)`: after every call `fn(tool)` gives a short line
  or `None`; every active provider's line joins the answer as `"rider"`
  (each cut to 80 characters, the whole to 200), apart from the single
  `notice` service. The Tutor's: `tutor: step 3/5 passed; now step 4/5
  pending`, given when it changes, never on the tutor's own answers.
- **`call_done(session, tool, ok, changed)`** after every call through the
  server (the agent's, a panel click's, a batch's inner calls), refusals
  too, before the rider is asked; `changed` when the call went through and
  changed the document; `session.by` says whose. The Tutor re-checks the
  step in front on it (not during its own setup or do).
- **The test flag `AGENTLINK_AS_USER=1`** (the design's
  `AGENTLINK_TUTOR_AS_USER`, made generic): the agent's calls run as the
  person's (`session.by`), so guided mode is tested end to end by an agent
  (`tests/test_tool.py`, `tests/test_replay_t3_fc.py`). Off by default,
  documented as test-only in Agent Link's `docs/hooks.md`.
- From the live check: the 3D badge (`annotations.light(…, badge=n)`) is a
  disc and a bold number sized for the screen's pixel ratio, drawn at the
  point of the face nearest its centre that the view shows with room
  around it, not under another part.

The window's own signals a guided step is checked on in T3 need nothing
new: FreeCAD's document observer (recompute, undo, redo, deletion), its
selection observer and the main window's `workbenchActivated`, all public.

## T4: watch mode (done)

In Agent Link core since 15 Nov 2026 (API 1, additions only; core names
no add-on):

- **`hooks.agent_acting()`**, True while one of the agent's own calls runs
  (every call goes through `Server.call`, the window link's and the
  echo's alike; a panel click is the person's), so the person's events are
  kept apart from the agent's.
- **Socket-thread tools**, `hooks.register_thread_tool(name)` beside
  `PINNED_FREE`: the window link answers such a tool on a thread of its own
  (`Server.handle_light`: no undo step, echo, call_done, notice or rider),
  never through the GUI thread's queue and never holding `in_call`; replies
  on one connection are written one at a time. `tutor_watch` is one.
- **Window events**, `hooks.watch_window(owner)`: while watched,
  `workbench_activated(name, by)` and `command_used(name, by)` through
  `hooks.emit` (`agentlink/gui_events.py`), so the Tutor imports no GUI
  internals; `hooks.off(event, fn)` takes a listener off.

## T5: add-on lessons

- **`_register_lessons(mod)`** in `agentlink/families/__init__.py`, a twin of
  `_register_guides`: a `lessons/` folder beside an add-on's
  `agentlink_families` module offered to whoever provides the `lessons`
  service (the Tutor), with the add-on's package name as the owner. Without
  the Tutor installed nothing reads them.
- **`tutor_target` and `tutor_check` readers** need nothing new:
  `hooks.register_reader`/`hooks.read` already serve them.
