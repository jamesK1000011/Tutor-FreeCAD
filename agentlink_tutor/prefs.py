# SPDX-License-Identifier: LGPL-2.1-or-later
"""The person's Tutor preferences, in FreeCAD's parameters on this computer
(User parameter:BaseApp/Preferences/Mod/Tutor). Without FreeCAD (tests) an
in-memory stand-in keeps them.

    ShowExplainers   bool, default on: each step's short "why" line under
                     its instruction, in the callout, the tab and the
                     agent's answers
"""
PARAMS = "User parameter:BaseApp/Preferences/Mod/Tutor"
EXPLAIN = "ShowExplainers"


class Memory:
    def __init__(self):
        self.values = {}

    def GetBool(self, name, default=False):
        return self.values.get(name, default)

    def SetBool(self, name, value):
        self.values[name] = bool(value)


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
