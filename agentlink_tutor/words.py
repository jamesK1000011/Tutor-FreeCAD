# SPDX-License-Identifier: LGPL-2.1-or-later
"""Plain words for the person: the one place where FreeCAD's internal names
(type ids such as Sketcher::SketchObject, command names such as
PartDesign_NewSketch, property names such as UseCustomVector) become what
the window shows ("sketch", "New Sketch", "Use custom vector").

Nothing the person reads (the callout, the Tutor tab, a check's "not yet",
a hint) carries an internal name; tests/test_words.py scans every string the
engine can produce for one.

A lesson names a command in its words as a token inside bold:
**{PartDesign_NewSketch}** or, with the words to use where FreeCAD cannot
be asked (headless, an older FreeCAD), **{PartDesign_NewSketch|New Sketch}**.
ui_text() swaps the token for the command's live menu text (FreeCAD's
Command.getInfo()['menuText'], & and … taken off), so the step's words and
the window agree in every FreeCAD release and language.
"""
import re

# Type ids as the person knows them. Anything else: the last part of the
# id, split at its capitals and lower-cased (PartDesign::AdditiveBox ->
# "additive box").
TYPES = {
    "Sketcher::SketchObject": "sketch",
    "Sketcher::SketchObjectPython": "sketch",
    "PartDesign::Body": "body",
    "PartDesign::Pad": "pad",
    "PartDesign::Pocket": "pocket",
    "PartDesign::Hole": "hole",
    "PartDesign::Revolution": "revolution",
    "PartDesign::Groove": "groove",
    "PartDesign::Fillet": "fillet",
    "PartDesign::Chamfer": "chamfer",
    "PartDesign::Plane": "datum plane",
    "PartDesign::Line": "datum line",
    "PartDesign::Point": "datum point",
    "PartDesign::ShapeBinder": "shape binder",
    "PartDesign::SubShapeBinder": "sub-shape binder",
    "Part::Feature": "shape",
    "Part::Box": "cube",
    "Part::Cylinder": "cylinder",
    "Part::Sphere": "sphere",
    "Part::Cone": "cone",
    "Part::Torus": "torus",
    "Part::Cut": "cut",
    "Part::Fuse": "union",
    "Part::Common": "intersection",
    "Part::Extrusion": "extrusion",
    "App::Part": "part",
    "App::DocumentObjectGroup": "group",
    "App::Origin": "origin",
    "Mesh::Feature": "mesh",
    "Spreadsheet::Sheet": "spreadsheet",
}

_DROP = ("Object", "Feature", "Python")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Internal names as they look: a type id, a command name, a CamelCase word
# with a capital inside (SketchObject, NewSketch). FreeCAD and a few
# product names are the program's own words.
INTERNAL = re.compile(r"\b[A-Z][A-Za-z0-9]*::[A-Za-z0-9]+\b|\b[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*\b|\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b")
OWN_WORDS = ("FreeCAD", "TechDraw", "OpenSCAD", "OrcaSlicer", "KiCad", "macOS")


def split_camel(name):
    return _CAMEL.sub(" ", str(name))


def type_words(type_id):
    """A type id in plain words: Sketcher::SketchObject -> "sketch"."""
    t = str(type_id or "")
    if t in TYPES:
        return TYPES[t]
    last = t.split("::")[-1]
    for d in _DROP:
        if last.endswith(d) and len(last) > len(d):
            last = last[: -len(d)]
    return split_camel(last).lower() or "object"


def prop_words(name):
    """A property's name as its field shows it: Length stays Length,
    UseCustomVector reads "Use custom vector"."""
    n = str(name or "")
    words = split_camel(n).split()
    if len(words) < 2:
        return n
    return " ".join([words[0]] + [w if w.isupper() else w.lower() for w in words[1:]])


def _gui():
    try:
        import FreeCAD
        import FreeCADGui

        return FreeCADGui if getattr(FreeCAD, "GuiUp", False) else None
    except ImportError:
        return None


GUI = {"get": _gui}  # tests put a stand-in here


def clean_menu_text(text):
    """FreeCAD's menuText as the person reads it: no & (the mnemonic), no
    … or ... (the dialog sign), no stray spaces."""
    t = str(text or "").replace("&&", "\0").replace("&", "").replace("\0", "&")
    t = t.replace("…", "").replace("...", "")
    return " ".join(t.split())


def live_menu_text(cmd):
    """The command's menu text from FreeCAD, cleaned; None when FreeCAD
    cannot be asked (no window, no such command)."""
    g = GUI["get"]()
    if g is None:
        return None
    try:
        info = g.Command.get(cmd).getInfo()
    except Exception:  # noqa: BLE001
        return None
    got = clean_menu_text(info.get("menuText") if isinstance(info, dict) else None)
    return got or None


def command_words(cmd, fallback=None):
    """What the window calls the command: its live menu text, else the
    lesson's fallback, else its name made readable (PartDesign_NewSketch
    -> "New Sketch")."""
    got = live_menu_text(cmd)
    if got:
        return got
    if fallback:
        return fallback
    return split_camel(str(cmd).split("_", 1)[-1])


TOKEN = re.compile(r"\{([A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)(?:\|([^{}]*))?\}")


def ui_text(text):
    """text with each {Command} or {Command|fallback} token swapped for the
    command's words (command_words). None stays None."""
    if text is None:
        return None
    return TOKEN.sub(lambda m: command_words(m.group(1), (m.group(2) or "").strip() or None), str(text))


def tokens(text):
    """[(command, fallback)] named in text."""
    return [(m.group(1), m.group(2)) for m in TOKEN.finditer(str(text or ""))]


def internal_names(text):
    """The internal names text still carries ([] for plain words)."""
    return [m for m in INTERNAL.findall(str(text or "")) if m not in OWN_WORDS]


BADGES = "①②③④⑤⑥⑦⑧⑨"


def badge(n):
    """A badge number as the disc it is drawn in on the screen: 2 -> ②."""
    return BADGES[n - 1] if isinstance(n, int) and 1 <= n <= len(BADGES) else f"({n})"
