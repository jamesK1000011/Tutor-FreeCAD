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

## T3: guided and demo modes

- **A core rider line on answers** that an add-on can feed (`tutor: step 3/7
  passed`), separate from the single `notice` service an add-on may take:
  `protocol._add_notice` with more than one provider, or a second channel.
- **`call_done` with the tool's name and whether it changed the document**,
  so the engine re-checks a step after the agent's own calls in demo mode.

## T4: watch mode

- **An `agent_acting` flag** set by echo's before/after and gui_link's
  `in_call`, readable by an add-on, so the person's events are kept apart
  from the agent's.
- **A socket-thread tool flag** (a `THREAD_TOOLS` set next to `PINNED_FREE`
  that an add-on's family can declare into), so `tutor_watch wait` is
  answered on gui_link's socket thread and never blocks the GUI thread or
  holds `in_call`.
- **The main window's `workbenchActivated`** and command `QAction.triggered`
  signals reachable without the add-on importing GUI internals, or a core
  `command_used` event through `hooks.emit`.

## T5: add-on lessons

- **`_register_lessons(mod)`** in `agentlink/families/__init__.py`, a twin of
  `_register_guides`: a `lessons/` folder beside an add-on's
  `agentlink_families` module offered to whoever provides the `lessons`
  service (the Tutor), with the add-on's package name as the owner. Without
  the Tutor installed nothing reads them.
- **`tutor_target` and `tutor_check` readers** need nothing new:
  `hooks.register_reader`/`hooks.read` already serve them.
