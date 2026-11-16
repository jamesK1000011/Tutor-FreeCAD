# SPDX-License-Identifier: LGPL-2.1-or-later
# What Agent Link for FreeCAD loads from the Tutor when both are installed:
# the tutor tools (group tutor, not in the lean list) and the Tutor tab in
# Agent Link's panel, between Notes and Steps. Agent Link finds this module
# by convention and never names it; without Agent Link it is never loaded.
from agentlink import hooks

from . import fam_tutor

AGENTLINK_API = ">=1,<2"
FAMILIES = [fam_tutor]
CREDIT = None
LICENSE = "LGPL-2.1-or-later"
TAB = "Tutor"
TAB_ORDER = 15


def _tab(panel):
    from . import tab

    return tab.TutorTab(panel)


hooks.register_tab(TAB, _tab, order=TAB_ORDER)
