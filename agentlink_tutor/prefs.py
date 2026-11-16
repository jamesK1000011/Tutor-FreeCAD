# SPDX-License-Identifier: LGPL-2.1-or-later
"""The person's Tutor preferences, in FreeCAD's parameters on this computer
(User parameter:BaseApp/Preferences/Mod/Tutor). Without FreeCAD (tests) an
in-memory stand-in keeps them.

    ShowExplainers   bool, default on: each step's short "why" line under
                     its instruction, in the callout, the tab and the
                     agent's answers
    ReduceMotion     bool, default off: no camera turns between steps (the
                     part is framed once, at the start, without the view's
                     animation); highlights stay still
    TextScale        int, percent, default 100 (100 to 200): the Tutor
                     tab's and the callout's text size over the
                     application's font
"""
PARAMS = "User parameter:BaseApp/Preferences/Mod/Tutor"
EXPLAIN = "ShowExplainers"
MOTION = "ReduceMotion"
SCALE = "TextScale"
SCALES = (100, 125, 150, 175, 200)


class Memory:
    def __init__(self):
        self.values = {}

    def GetBool(self, name, default=False):
        return self.values.get(name, default)

    def SetBool(self, name, value):
        self.values[name] = bool(value)

    def GetInt(self, name, default=0):
        return self.values.get(name, default)

    def SetInt(self, name, value):
        self.values[name] = int(value)


_MEM = Memory()


def params():
    try:
        import FreeCAD

        return FreeCAD.ParamGet(PARAMS)
    except ImportError:
        return _MEM


def explainers(p=None):
    return bool((p or params()).GetBool(EXPLAIN, True))


def set_explainers(on, p=None):
    (p or params()).SetBool(EXPLAIN, bool(on))
    return bool(on)


def reduce_motion(p=None):
    return bool((p or params()).GetBool(MOTION, False))


def set_reduce_motion(on, p=None):
    (p or params()).SetBool(MOTION, bool(on))
    return bool(on)


def text_scale(p=None):
    """The text size in percent, kept within 100 to 200."""
    try:
        v = int((p or params()).GetInt(SCALE, 100))
    except Exception:  # noqa: BLE001
        v = 100
    return min(max(v, SCALES[0]), SCALES[-1])


def set_text_scale(percent, p=None):
    v = min(max(int(percent), SCALES[0]), SCALES[-1])
    (p or params()).SetInt(SCALE, v)
    return v


def scaled(points, p=None):
    """A font's point size at the person's text size."""
    return float(points) * text_scale(p) / 100.0
