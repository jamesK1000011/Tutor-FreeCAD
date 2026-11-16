# SPDX-License-Identifier: LGPL-2.1-or-later
"""The lesson in hand in this FreeCAD (the Tutor tab's engine), so the
agent's tutor_point can use its bindings ($sketch: the sketch the person
made). In memory only."""

NOW = {"engine": None}


def engine():
    return NOW["engine"]


def set_engine(e):
    NOW["engine"] = e


def bindings():
    e = NOW["engine"]
    return dict(getattr(e, "bindings", None) or {}) if e is not None else {}
