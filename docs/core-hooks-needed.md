<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# What the Tutor needs from Agent Link core

The Tutor is an add-on. It reaches Agent Link only through what Agent Link
offers every add-on (`agentlink/hooks.py`, the `agentlink_families` module,
the guides folder). Phase T1 (the lesson engine, checks and starter lessons)
needs nothing new. Later phases need these generic hooks in core; none of
them names the Tutor.

## T2: pointing at things and the Tutor tab

- **An overlay painter service.** One transparent, mouse-transparent overlay
  widget over the main window that any add-on can ask to ring a widget rect
  or a menubar title, with a badge and a callout (`hooks.service("overlay")`
  or similar), and echo painted through it too, so a theme's stylesheet is
  never overwritten per widget. Echo's button lighting moves onto it.
- **Target resolution helpers exposed for reuse.** Echo's `command_for()` and
  the QAction lookup by `objectName` that `flash_command()` uses, callable by
  an add-on (today they are private to `echo.py`).
- **`hooks.register_tab`** at order 15 (between Notes and Steps) for the
  Tutor tab. Already there; listed so its order slot is kept free.
- **The coin annotation layer** that `Pins`/`Stage` use for the 3D
  sub-element highlight, offered as a service, so the Tutor need not copy it.
- **Echo's skip list open to add-ons**, so `tutor*` calls are not echoed
  (next to `session_state` and `tool_groups`).

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
