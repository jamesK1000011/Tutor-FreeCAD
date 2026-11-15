# SPDX-License-Identifier: LGPL-2.1-or-later
# What Agent Link for FreeCAD loads from the Tutor when both are installed.
# Agent Link finds this module by convention and never names it; without
# Agent Link it is never loaded. The lesson engine comes first; the tutor
# tools, the Tutor tab in Agent Link's panel and the guide come in later
# phases (docs/core-hooks-needed.md), so for now it offers no tools and
# costs the agent nothing.
AGENTLINK_API = ">=1,<2"
FAMILIES = []
CREDIT = None
LICENSE = "LGPL-2.1-or-later"
