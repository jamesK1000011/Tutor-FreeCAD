# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tutor for FreeCAD: an agent teaches FreeCAD in the person's own window.

Lessons are data (lessons/*.lesson.json, checked against
data/lesson.schema.json); checks.py tells whether a step is done by reading
the document; engine.py walks a lesson step by step. Nothing here imports
Agent Link at load: its agentlink_families module, which only Agent Link
imports, connects the Tutor to it.
"""

VERSION = "0.1.0"
