# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Tutor's step checks: a small closed vocabulary, read-only, evaluated against
the session's document and (when there is a window) what the window shows.

A check is a one-key object, the key its kind:

    exists / absent  an object ("$pad", a name) or a query {type, in, label,
                     where}; a string with "::" is a type ("PartDesign::Pocket");
                     where: {property: value or {eq|lt|gt|le|ge, tol}} (a hole
                     whose ThreadSize is "M4" and Diameter at least 4.3)
    new              an object of a type made since the step began
    prop             {"prop": "$pad", "name": "Length", "eq"|"lt"|"gt"|"le"|"ge": n,
                     "tol": mm or deg, "unit": "mm"}
    valid            "$pad" or {"object": "$pad", "solid": true}: recomputed, no
                     error, a shape (one solid or more for PartDesign features)
    volume           {"volume": "$body", "eq"|…: mm³, "tol"}; the object may be a
                     query ({type, label, where}): one object it finds passes
    bbox             {"bbox": "$body", "size": [x, y, z], "min"?: [x, y, z],
                     "tol"}: the box's size and, with min, its lowest corner
                     (where it is); the object may be a query too
    sketch           {"sketch": "$s", "closed": true, "dof": 0, "full": true,
                     "dof_max": n (n degrees of freedom or fewer: progress,
                     whatever the order), "count": n (lines and curves),
                     "dims": [47] (each a driving dimension's value, mm),
                     "external": n (at least n outside edges brought in),
                     "radii": [14.5] (each a circle's or arc's radius in it)}
    expr             {"expr": "$sketch", "uses": "size", "count": 2, "path"?}: at
                     least count of the object's values bound to an expression
                     naming the parameter (VarSet.size, <<Params>>.size)
    follows          {"follows": "size", "object": "$body", "by": 5, "axis"?:
                     "x"|"y"|"z", "change"?: mm, "tol"?}: the part follows the
                     parameter: size raised by `by` for a moment (inside an undo
                     transaction that is aborted), the object recomputes with
                     no error and its size changes (along axis by change);
                     then everything is put back
    file             {"file": "Part.stl", "min_bytes": 84}: in the session's folder
    selected         "$sketch" or {"object", "sub": "Face"}           (window)
    workbench        "PartDesignWorkbench"                              (window)
    editing          an object, or null                                 (window)
    task_open        a dialog ("PartDesign_Pad"), true for any, or null (window)
    used             a command seen in the person's events
    all / any / not  combinators

Each answers Result(status, why): status "pass", "fail" or "pending" (cannot be
told here: the window is not up, or nothing is being watched). why is a short
sentence for the person and the agent when it is not a pass. Bindings ($pad)
are resolved before a check runs (engine.resolve), so a check sees names.

Add-ons add kinds with hooks.register_reader("tutor_check", fn(kind, spec, ctx))
answering a Result (or a (status, why) pair), or None when the kind is not
theirs. Nothing here changes the document, except follows, which changes
one parameter for a moment inside a transaction it aborts (TRIAL is set
while it runs, so the window's signals it raises are not taken for the
person's).
"""
import collections
import os
import re

from . import words

Result = collections.namedtuple("Result", "status why")

PASS = Result("pass", None)
DOC_KINDS = ("exists", "absent", "new", "prop", "valid", "volume", "bbox", "sketch", "file", "expr", "follows")
GUI_KINDS = ("selected", "workbench", "editing", "task_open")
EVENT_KINDS = ("used",)
LOGIC_KINDS = ("all", "any", "not")
KINDS = DOC_KINDS + GUI_KINDS + EVENT_KINDS + LOGIC_KINDS
CMP = ("eq", "lt", "gt", "le", "ge")
NO_WINDOW = "needs the FreeCAD window"


def fail(why):
    return Result("fail", why)


def pending(why):
    return Result("pending", why)


class Context:
    """What a check reads. doc: the document (or None); gui: a GuiState, or
    None when there is no window; events: the person's events (dicts with
    k "cmd" and c the command), or None when nothing is watched; before: the
    object names there were when the step began; out_dir: the session's folder."""

    def __init__(self, doc=None, gui=None, events=None, before=None, out_dir=None):
        self.doc = doc
        self.gui = gui
        self.events = events
        self.before = set(before or ())
        self.out_dir = out_dir


class GuiState:
    """The window's state as checks read it: the active workbench's name,
    the selection [(object name, [sub-element names])], the object in edit
    (its name or None) and the open task dialog's id (or None)."""

    def __init__(self, workbench=None, selection=(), editing=None, task=None):
        self.workbench = workbench
        self.selection = [(n, list(subs or ())) for n, subs in selection]
        self.editing = editing
        self.task = task


def gui_state():
    """The window's state, read from FreeCADGui; None without a window. The
    task dialog is named from the object in edit (PartDesign::Pad ->
    PartDesign_Pad), which is the dialog FreeCAD opens for it."""
    try:
        import FreeCAD
        import FreeCADGui

        if not FreeCAD.GuiUp:
            return None
    except ImportError:
        return None
    try:
        wb = FreeCADGui.activeWorkbench().name()
    except Exception:
        wb = None
    try:
        sel = [(x.ObjectName, list(x.SubElementNames)) for x in FreeCADGui.Selection.getSelectionEx()]
    except Exception:
        sel = []
    editing = task = None
    try:
        gd = FreeCADGui.ActiveDocument
        vp = gd.getInEdit() if gd is not None else None
        if vp is not None:
            editing = vp.Object.Name
            task = vp.Object.TypeId.replace("::", "_")
    except Exception:
        pass
    try:
        if task is None and FreeCADGui.Control.activeDialog():
            task = True
    except Exception:
        pass
    return GuiState(wb, sel, editing, task)


# ---- finding objects -------------------------------------------------------


def _objects(doc):
    return list(getattr(doc, "Objects", None) or [])


def lookup(doc, ref):
    """The object named or labelled ref, or None."""
    if doc is None or not isinstance(ref, str):
        return None
    get = getattr(doc, "getObject", None)
    o = get(ref) if get else None
    if o is not None:
        return o
    return next((x for x in _objects(doc) if getattr(x, "Label", None) == ref), None)


def _is_type(o, t):
    if getattr(o, "TypeId", None) == t:
        return True
    try:
        return bool(o.isDerivedFrom(t))
    except Exception:
        return False


def _inside(o, container):
    try:
        if container.hasObject(o):
            return True
    except Exception:
        pass
    try:
        return o.getParentGeoFeatureGroup() is container
    except Exception:
        return False


def query(spec):
    """A query object from a check's operand: {type, in, label} or None for
    an object reference (then the operand is the reference)."""
    if isinstance(spec, str):
        return {"type": spec} if "::" in spec else None
    if isinstance(spec, dict):
        return spec
    return None


def find(ctx, spec, only_new=False):
    """The objects a reference or a query names, oldest first."""
    q = query(spec)
    if q is None:
        o = lookup(ctx.doc, spec)
        found = [o] if o is not None else []
    else:
        inside = lookup(ctx.doc, q["in"]) if q.get("in") else None
        if q.get("in") and inside is None:
            return []
        found = [o for o in _objects(ctx.doc)
                 if (not q.get("type") or _is_type(o, q["type"]))
                 and (not q.get("label") or getattr(o, "Label", None) == q["label"])
                 and (inside is None or _inside(o, inside))
                 and matches(o, q.get("where"))]
    if only_new:
        found = [o for o in found if o.Name not in ctx.before]
    return found


def matches(o, where):
    """True when o's properties are as where says: {name: value} (a number
    within 1e-6, else the same text: an enumeration's choice), {name:
    {eq|lt|gt|le|ge: n, tol}}, or {name: {set: true}} (it has the property,
    and it holds something: a link, a value)."""
    for name, want in (where or {}).items():
        if not hasattr(o, name):
            return False
        have = getattr(o, name)
        if isinstance(want, dict) and "set" in want:
            if bool(want["set"]) != (have is not None and have != "" and have != [] and have != ()):
                return False
        elif isinstance(want, dict):
            if compare(name, have, want).status != "pass":
                return False
        elif number(want) is not None and number(have) is not None:
            if abs(number(have) - number(want)) > 1e-6:
                return False
        elif str(have) != str(want):
            return False
    return True


def _where_words(where):
    out = []
    for name, want in (where or {}).items():
        if isinstance(want, dict) and "set" in want:
            out.append(f"{words.prop_words(name)}" if want["set"] else f"no {words.prop_words(name)}")
        elif isinstance(want, dict):
            op = next((k for k in CMP if k in want), "eq")
            word = {"eq": "", "lt": "under ", "gt": "over ", "le": "at most ", "ge": "at least "}[op]
            out.append(f"{words.prop_words(name)} {word}{_fmt(number(want[op]) if number(want[op]) is not None else want[op])}")
        else:
            shown = _fmt(number(want)) if number(want) is not None else words.split_camel(want) if isinstance(want, str) else want
            out.append(f"{words.prop_words(name)} {shown}")
    return (" with " + " and ".join(out)) if out else ""


def describe(spec, doc=None):
    """A reference or query in the person's words: "sketch", "pad
    labelled Pad001 in Body" (never a type id: words.type_words)."""
    q = query(spec)
    if q is None:
        return _label(doc, spec) if doc is not None else str(spec)
    t = words.type_words(q["type"]) if q.get("type") else "object"
    where = f" in {_label(doc, q['in'])}" if q.get("in") else ""
    return t + (f" labelled {q['label']}" if q.get("label") else "") + _where_words(q.get("where")) + where


# ---- numbers ---------------------------------------------------------------


def number(v):
    """A property's value as a float (a Quantity's Value: mm, deg), or None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    val = getattr(v, "Value", None)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    return None


def _fmt(x, unit=""):
    s = f"{x:.3f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)
    return f"{s} {unit}".strip()


def compare(what, have, spec, unit=""):
    """have against spec's eq/lt/gt/le/ge (tol for eq); a Result."""
    tol = float(spec.get("tol", 1e-6))
    for op in CMP:
        if op not in spec:
            continue
        want = spec[op]
        h, w = number(have), number(want)
        if h is None or w is None:
            ok = op == "eq" and have == want
        else:
            ok = {"eq": abs(h - w) <= tol, "lt": h < w, "gt": h > w, "le": h <= w + tol, "ge": h >= w - tol}[op]
        if not ok:
            word = {"eq": "", "lt": "under ", "gt": "over ", "le": "at most ", "ge": "at least "}[op]
            shown = _fmt(h, unit) if h is not None else repr(have)
            wanted = _fmt(w, unit) if w is not None else repr(want)
            return fail(f"{what} is {shown}; the step wants {word}{wanted}")
    return PASS


# ---- the kinds -------------------------------------------------------------


def _exists(spec, ctx):
    if find(ctx, spec):
        return PASS
    return fail(f"there is no {describe(spec, ctx.doc)} yet")


def _absent(spec, ctx):
    got = find(ctx, spec)
    if not got:
        return PASS
    return fail(f"{got[0].Label} is still there")


def _new(spec, ctx):
    if find(ctx, spec, only_new=True):
        return PASS
    return fail(f"no new {describe(spec, ctx.doc)} yet")


def _one(ctx, ref):
    o = lookup(ctx.doc, ref)
    return o, (None if o is not None else fail(f"{ref} is not in the document"))


def _prop(spec, ctx):
    o, bad = _one(ctx, spec.get("prop"))
    if bad:
        return bad
    name = spec.get("name")
    if not hasattr(o, name):
        return fail(f"{o.Label} has no {words.prop_words(name)}")
    return compare(words.prop_words(name), getattr(o, name), spec, spec.get("unit", ""))


def _shape(o):
    sh = getattr(o, "Shape", None)
    try:
        return None if sh is None or sh.isNull() else sh
    except Exception:
        return None


def _valid(spec, ctx):
    ref = spec.get("object") if isinstance(spec, dict) else spec
    o, bad = _one(ctx, ref)
    if bad:
        return bad
    state = [str(x) for x in (getattr(o, "State", None) or [])]
    if "Invalid" in state or "Error" in state:
        return fail(f"{o.Label} has an error: recompute fails")
    try:
        if not o.isValid():
            return fail(f"{o.Label} has an error: recompute fails")
    except AttributeError:
        pass
    if "Touched" in state:
        return pending(f"{o.Label} is waiting for a recompute")
    want_solid = spec.get("solid") if isinstance(spec, dict) and "solid" in spec else str(getattr(o, "TypeId", "")).startswith("PartDesign::")
    sh = _shape(o)
    if want_solid and (sh is None or not getattr(sh, "Solids", None)):
        return fail(f"{o.Label} is not a solid")
    return PASS


def _each(spec, ctx, kind, one):
    """one(o) for the object a check names, or for each object its query
    finds (a pass when one of them passes; else the first one's why)."""
    ref = spec.get(kind)
    q = query(ref) if isinstance(ref, dict) else None
    if q is None:
        o, bad = _one(ctx, ref)
        return bad or one(o)
    found = find(ctx, q)
    if not found:
        return fail(f"there is no {describe(ref, ctx.doc)} yet")
    first = None
    for o in found:
        r = one(o)
        if r.status == "pass":
            return r
        first = first or r
    return first


def _volume(spec, ctx):
    def one(o):
        sh = _shape(o)
        if sh is None:
            return fail(f"{o.Label} has no shape yet")
        return compare(f"{o.Label}'s volume", float(sh.Volume), spec, "mm³")

    return _each(spec, ctx, "volume", one)


def _bbox(spec, ctx):
    tol = float(spec.get("tol", 0.01))

    def one(o):
        sh = _shape(o)
        if sh is None:
            return fail(f"{o.Label} has no shape yet")
        bb = sh.BoundBox
        have = [bb.XLength, bb.YLength, bb.ZLength]
        want = spec.get("size") or []
        if any(abs(h - w) > tol for h, w in zip(have, want)):
            return fail(f"{o.Label} is {' × '.join(_fmt(float(h)) for h in have)} mm; the step wants {' × '.join(_fmt(float(w)) for w in want)}")
        if spec.get("min") is not None:
            low = [bb.XMin, bb.YMin, bb.ZMin]
            at = [float(w) for w in spec["min"]]
            if any(abs(h - w) > tol for h, w in zip(low, at)):
                return fail(f"{o.Label}'s lowest corner is at {', '.join(_fmt(float(h)) for h in low)} mm; "
                            f"the step wants {', '.join(_fmt(w) for w in at)} (Placement)")
        return PASS

    return _each(spec, ctx, "bbox", one)


def _sketch(spec, ctx):
    o, bad = _one(ctx, spec.get("sketch"))
    if bad:
        return bad
    if spec.get("closed"):
        sh = _shape(o)
        wires = list(getattr(sh, "Wires", None) or []) if sh is not None else []
        if not wires:
            return fail(f"{o.Label} has no profile yet")
        if not all(w.isClosed() for w in wires):
            return fail(f"{o.Label} has an open outline: its ends do not meet")
    if "dof" in spec or spec.get("full"):
        try:
            o.solve()
        except Exception:
            pass
        dof = getattr(o, "DoF", None)
        if dof is None:
            return pending(f"{o.Label}'s degrees of freedom cannot be read in this FreeCAD")
        want = 0 if spec.get("full") else spec["dof"]
        if dof != want:
            return fail(f"{o.Label} has {dof} degrees of freedom; the step wants {want}" + (" (fully constrained)" if want == 0 else ""))
    if "dof_max" in spec:
        try:
            o.solve()
        except Exception:
            pass
        dof = getattr(o, "DoF", None)
        if dof is None:
            return pending(f"{o.Label}'s degrees of freedom cannot be read in this FreeCAD")
        if dof > int(spec["dof_max"]):
            return fail(f"{o.Label} has {dof} degrees of freedom; the step wants {int(spec['dof_max'])} or fewer")
    if "count" in spec:
        n = len(own_geometry(o))
        if n < int(spec["count"]):
            return fail(f"{o.Label} has {n} lines or curves; the step wants {int(spec['count'])}")
    for d in spec.get("dims") or ():
        if not any(abs(h - float(d)) <= float(spec.get("tol", 0.01)) for h in dims(o)):
            return fail(f"{o.Label} has no dimension of {_fmt(float(d), 'mm')} yet")
    if "external" in spec:
        n = external_count(o)
        if n < int(spec["external"]):
            return fail(f"{o.Label} has {n} outside edges brought in; the step wants {int(spec['external'])}"
                        " (External Geometry)")
    for r in spec.get("radii") or ():
        have = radii(o)
        if not any(abs(h - float(r)) <= float(spec.get("tol", 0.01)) for h in have):
            return fail(f"{o.Label} has no circle or arc of radius {_fmt(float(r), 'mm')}")
    return PASS


def external_count(o):
    """How many edges of other objects the sketch brings in (its External
    Geometry): the sub-elements of ExternalGeometry's links."""
    n = 0
    for link in getattr(o, "ExternalGeometry", None) or ():
        subs = link[1] if isinstance(link, (tuple, list)) and len(link) > 1 else ()
        subs = [subs] if isinstance(subs, str) else list(subs or ())
        n += max(1, len(subs))
    return n


DIM_TYPES = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter")


def dims(o):
    """The values (mm, without sign) of the sketch's driving dimensions."""
    out = []
    for c in getattr(o, "Constraints", None) or ():
        if getattr(c, "Type", None) in DIM_TYPES and getattr(c, "Driving", True):
            v = number(getattr(c, "Value", None))
            if v is not None:
                out.append(abs(v))
    return out


def own_geometry(o):
    """The sketch's own lines and curves (not construction, not points)."""
    out = []
    for i, g in enumerate(getattr(o, "Geometry", None) or ()):
        if type(g).__name__ == "Point":
            continue
        try:
            if o.getConstruction(i):
                continue
        except Exception:  # noqa: BLE001
            pass
        out.append(g)
    return out


def radii(o):
    """The radii of the sketch's own circles and arcs (not construction)."""
    out = []
    for i, g in enumerate(getattr(o, "Geometry", None) or ()):
        r = getattr(g, "Radius", None)
        if not isinstance(r, (int, float)) or isinstance(r, bool):
            continue
        try:
            if o.getConstruction(i):
                continue
        except Exception:  # noqa: BLE001
            pass
        out.append(float(r))
    return out


# ---- parameters: bound values, and the part following them --------------------


def _param_re(name):
    """An expression naming the parameter name as a member: VarSet.size,
    <<My params>>.size, Params.size (not sizeX, not a bare size)."""
    return re.compile(r"(?:<<[^<>]+>>|\b[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*" + re.escape(name) + r"\b")


def bound(o, name, path=None):
    """[(path, expression)] of o's values bound to an expression that names
    the parameter."""
    rx = _param_re(name)
    out = []
    for item in getattr(o, "ExpressionEngine", None) or ():
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        p, e = str(item[0]), str(item[1])
        if rx.search(e) and (not path or path in p):
            out.append((p, e))
    return out


def _expr(spec, ctx):
    o, bad = _one(ctx, spec.get("expr"))
    if bad:
        return bad
    name = spec.get("uses")
    want = int(spec.get("count", 1))
    got = bound(o, name, spec.get("path"))
    if len(got) >= want:
        return PASS
    if not got:
        return fail(f"no value of {o.Label} uses {name} yet: give a dimension the expression of {name}")
    return fail(f"{len(got)} value{'s' if len(got) != 1 else ''} of {o.Label} use{'s' if len(got) == 1 else ''} {name}; the step wants {want}")


TRIAL = [0]  # > 0 while follows changes a parameter for a moment


def in_trial():
    return TRIAL[0] > 0


def holder(doc, name):
    """(object, kind) that holds the parameter name: a variable set with
    that property ("varset"), else a spreadsheet with that alias ("sheet");
    (None, None) when there is none."""
    for o in _objects(doc):
        t = str(getattr(o, "TypeId", ""))
        if t.endswith("VarSet") and hasattr(o, name):
            return o, "varset"
    for o in _objects(doc):
        if str(getattr(o, "TypeId", "")).startswith("Spreadsheet::"):
            try:
                if o.getCellFromAlias(name):
                    return o, "sheet"
            except Exception:  # noqa: BLE001
                pass
    return None, None


def _get_param(h, kind, name):
    return number(getattr(h, name, None))


def _set_param(h, kind, name, value):
    if kind == "varset":
        setattr(h, name, value)
        return
    cell = h.getCellFromAlias(name)
    try:
        had = str(h.getContents(cell))
    except Exception:  # noqa: BLE001
        had = ""
    unit = "mm" if "mm" in had else ""
    h.set(cell, f"{value:g} {unit}".strip())


def _sizes(o):
    sh = _shape(o)
    if sh is None:
        return None
    bb = sh.BoundBox
    return {"x": float(bb.XLength), "y": float(bb.YLength), "z": float(bb.ZLength)}


def _broken(doc):
    out = []
    for o in _objects(doc):
        state = [str(x) for x in (getattr(o, "State", None) or [])]
        bad = "Invalid" in state or "Error" in state
        try:
            bad = bad or not o.isValid()
        except AttributeError:
            pass
        if bad:
            out.append(o.Label)
    return out


def _follows(spec, ctx):
    name = spec.get("follows")
    doc = ctx.doc
    o, bad = _one(ctx, spec.get("object"))
    if bad:
        return bad
    if ctx.gui is not None and (ctx.gui.editing or ctx.gui.task):
        return pending(f"close the open panel first: the check changes {name} for a moment")
    h, kind = holder(doc, name)
    if h is None:
        return fail(f"there is no parameter {name} yet (a variable set, or a spreadsheet alias)")
    old = _get_param(h, kind, name)
    if old is None:
        return fail(f"{name} in {h.Label} is not a number")
    if not all(hasattr(doc, a) for a in ("openTransaction", "abortTransaction", "recompute")):
        return pending("this check needs FreeCAD (it changes the parameter for a moment)")
    if getattr(doc, "HasPendingTransaction", False):
        return pending(f"an edit is still open: finish it first, the check changes {name} for a moment")
    by = float(spec.get("by", 5))
    tol = float(spec.get("tol", 0.05))
    base = _sizes(o)
    if base is None:
        return fail(f"{o.Label} has no shape yet")
    TRIAL[0] += 1
    try:
        doc.openTransaction("Tutor check")
        try:
            _set_param(h, kind, name, old + by)
            doc.recompute()
            after = _sizes(o)
            broken = _broken(doc)
        finally:
            doc.abortTransaction()
            if _get_param(h, kind, name) != old:
                _set_param(h, kind, name, old)
            doc.recompute()
    finally:
        TRIAL[0] -= 1
    shown = _fmt(old + by, "mm")
    if broken:
        return fail(f"with {name} at {shown}, {', '.join(broken[:3])} {'has' if len(broken) == 1 else 'have'} an error")
    if after is None:
        return fail(f"with {name} at {shown}, {o.Label} has no shape")
    axis = spec.get("axis")
    moved = {k: after[k] - base[k] for k in base}
    if axis:
        d = moved[axis]
        if "change" in spec:
            want = float(spec["change"])
            if abs(d - want) > tol:
                return fail(f"when {name} grows {_fmt(by, 'mm')}, {o.Label} grows {_fmt(d, 'mm')} along {axis.upper()}; the step wants {_fmt(want, 'mm')}")
        elif abs(d) <= tol:
            return fail(f"{o.Label} does not follow {name}: it keeps its size along {axis.upper()}")
        return PASS
    if all(abs(d) <= tol for d in moved.values()):
        return fail(f"{o.Label} does not follow {name}: it keeps its size when {name} changes")
    return PASS


def _file(spec, ctx):
    name = spec.get("file")
    if not ctx.out_dir:
        return pending("the session's folder is not known")
    p = os.path.join(ctx.out_dir, name)
    if not os.path.isfile(p):
        return fail(f"{name} is not in the session's folder yet")
    size = os.path.getsize(p)
    if size < int(spec.get("min_bytes", 1)):
        return fail(f"{name} is only {size} bytes: the export looks empty")
    return PASS


def _selected(spec, ctx):
    if ctx.gui is None:
        return pending(NO_WINDOW)
    ref = spec.get("object") if isinstance(spec, dict) else spec
    sub = spec.get("sub") if isinstance(spec, dict) else None
    o = lookup(ctx.doc, ref) if ref else None
    name = o.Name if o is not None else ref
    for n, subs in ctx.gui.selection:
        if name is not None and n != name:
            continue
        if sub is None or any(s.startswith(sub) for s in subs):
            return PASS
    what = (o.Label if o is not None else (ref or "something")) + (f" ({sub.lower()})" if sub else "")
    return fail(f"{what} is not selected")


def bench_text(name):
    """A workbench as its selector names it ("Part Design" for
    PartDesignWorkbench): FreeCAD's MenuText where there is a window, else
    from the class name."""
    if not name:
        return name
    try:
        import FreeCADGui

        text = FreeCADGui.listWorkbenches()[name].MenuText
        if text:
            return str(text)
    except Exception:  # noqa: BLE001
        pass
    short = name[:-len("Workbench")] if name.endswith("Workbench") else name
    return BENCH_WORDS.get(short, short)


def _workbench(spec, ctx):
    if ctx.gui is None:
        return pending(NO_WINDOW)
    if ctx.gui.workbench == spec:
        return PASS
    have = bench_text(ctx.gui.workbench) if ctx.gui.workbench else "another"
    return fail(f"{have} is the active workbench, not {bench_text(spec)}")


def _editing(spec, ctx):
    if spec is None:
        # No window has nothing open for editing.
        if ctx.gui is None or ctx.gui.editing is None:
            return PASS
        return fail(f"{_label(ctx.doc, ctx.gui.editing)} is still open for editing: push OK or Close")
    if ctx.gui is None:
        return pending(NO_WINDOW)
    o = lookup(ctx.doc, spec)
    name = o.Name if o is not None else spec
    if ctx.gui.editing == name:
        return PASS
    return fail(f"{_label(ctx.doc, spec)} is not open for editing")


def _task_open(spec, ctx):
    if spec is None:
        if ctx.gui is None or ctx.gui.task is None:
            return PASS
        return fail("a task panel is still open: push OK or Cancel")
    if ctx.gui is None:
        return pending(NO_WINDOW)
    task = ctx.gui.task
    if task is not None and (spec is True or task == spec):
        return PASS
    return fail(f"the {task_words(spec) + ' ' if spec is not True else ''}task panel is not open")


def task_words(task):
    """A task panel's name (FreeCAD's PartDesign_Pad, from the type of the
    object in edit) as the person knows it: "pad"."""
    t = str(task or "")
    return words.type_words(t.replace("_", "::", 1) if "::" not in t else t)


def _used(spec, ctx):
    if ctx.events is None:
        return pending("the person's actions are not being watched")
    if any(e.get("k") == "cmd" and e.get("c") == spec for e in ctx.events):
        return PASS
    return fail(f"{words.command_words(spec)} has not been used yet")


def _all(spec, ctx):
    wait = None
    for s in spec:
        r = evaluate(s, ctx)
        if r.status == "fail":
            return r
        if r.status == "pending" and wait is None:
            wait = r
    return wait or PASS


def _any(spec, ctx):
    whys, wait = [], None
    for s in spec:
        r = evaluate(s, ctx)
        if r.status == "pass":
            return PASS
        if r.status == "pending" and wait is None:
            wait = r
        whys.append(r.why)
    return wait or fail("; or ".join(w for w in whys if w))


def _not(spec, ctx):
    r = evaluate(spec, ctx)
    if r.status == "pending":
        return r
    return PASS if r.status == "fail" else fail("that is what the step should not be")


EVAL = {"exists": _exists, "absent": _absent, "new": _new, "prop": _prop, "valid": _valid, "volume": _volume, "bbox": _bbox,
        "sketch": _sketch, "file": _file, "expr": _expr, "follows": _follows, "selected": _selected, "workbench": _workbench, "editing": _editing,
        "task_open": _task_open, "used": _used, "all": _all, "any": _any, "not": _not}


def kind_of(check):
    """The kind of a check: the one key of KINDS it holds (the operand's
    options, such as name or tol, ride beside it); None when it is not one."""
    if not isinstance(check, dict):
        return None
    ks = [k for k in check if k in KINDS]
    if len(ks) == 1:
        return ks[0]
    if not ks and len(check) >= 1:
        return next(iter(check))  # an add-on's kind, or a mistake: validate() says which
    return None


def operand(check, kind):
    """What a kind reads: its own value, or the whole object for the kinds
    whose options ride beside the key (prop, volume, bbox, sketch, file,
    expr, follows)."""
    if kind in ("prop", "volume", "bbox", "sketch", "file", "expr", "follows"):
        return check
    if kind in ("selected", "valid") and len(check) > 1:
        return {"object": check[kind], **{k: v for k, v in check.items() if k != kind}}
    return check[kind]


def evaluate(check, ctx):
    """A Result for one check (bindings already resolved)."""
    kind = kind_of(check)
    if kind is None:
        return fail(f"not a check: {check!r}"[:120])
    fn = EVAL.get(kind)
    if fn is None:
        try:
            from agentlink import hooks  # Agent Link, when installed

            got = hooks.read("tutor_check", kind, check, ctx)
        except ImportError:
            got = None
        if got is None:
            return fail(f"no installed add-on checks {kind!r}")
        return got if isinstance(got, Result) else Result(*got)
    try:
        return fn(operand(check, kind), ctx)
    except Exception as e:  # noqa: BLE001 - a check never stops the lesson
        return pending(f"{kind} could not be read: {e}"[:160])


# Workbench names as their selector shows them, where the two differ.
BENCH_WORDS = {"PartDesign": "Part Design", "TechDraw": "TechDraw", "Fem": "FEM", "Cam": "CAM", "Path": "CAM",
               "MeshPart": "Mesh", "OpenSCAD": "OpenSCAD", "Start": "Start"}


def _label(doc, ref):
    o = lookup(doc, ref) if ref else None
    return getattr(o, "Label", None) or str(ref)


def exact(check, doc=None):
    """The exact thing a check wants, in a few words for the top of the hint
    ladder ("Length = 15 mm; then push OK"), or None when it says nothing a
    person can type or pick. Bindings already resolved."""
    kind = kind_of(check)
    if kind is None:
        return None
    if kind in ("all", "any"):
        parts = [p for p in (exact(c, doc) for c in check[kind]) if p]
        parts = list(dict.fromkeys(parts))
        return ("; " if kind == "all" else " or ").join(parts) or None
    if kind == "prop":
        op = next((k for k in CMP if k in check), None)
        if op is None:
            return None
        word = {"eq": "=", "lt": "<", "gt": ">", "le": "≤", "ge": "≥"}[op]
        return f"{words.prop_words(check['name'])} {word} {_fmt(number(check[op]) if number(check[op]) is not None else check[op], check.get('unit', ''))}"
    if kind == "bbox":
        size = check.get("size") or []
        return "size " + " × ".join(_fmt(float(v)) for v in size) + " mm" if len(size) == 3 else None
    if kind == "volume":
        op = next((k for k in CMP if k in check), None)
        return f"volume {_fmt(float(check[op]))} mm³" if op == "eq" else None
    if kind in ("task_open", "editing") and check.get(kind) is None:
        return "then push OK"
    if kind == "workbench":
        return f"the {bench_text(str(check[kind]))} workbench"
    if kind == "selected":
        ref = check[kind]
        return f"select {_label(doc, ref)}" + (f" ({check['sub'].lower()})" if check.get("sub") else "")
    if kind == "new":
        return f"a new {describe(check[kind], doc)}"
    if kind == "file":
        return f"saved as {check[kind]}"
    if kind == "used":
        return f"use {words.command_words(check[kind])}"
    return None


def needs_window(check):
    """True when every way the check can pass needs the window or watching."""
    kind = kind_of(check)
    if kind in ("task_open", "editing") and check.get(kind) is None:
        # "No task open" / "nothing in edit" pass without a window too.
        return False
    if kind in GUI_KINDS + EVENT_KINDS:
        return True
    if kind == "all":
        return any(needs_window(c) for c in check["all"])
    if kind == "any":
        return all(needs_window(c) for c in check["any"])
    return False


def _is_var(x):
    return isinstance(x, str) and x.startswith("$") and x[1:].isidentifier()


# What each kind's operand must look like (lessons.validate uses this).
def problems(check, where, extra_kinds=()):
    out = []
    if not isinstance(check, dict) or not check:
        return [f"{where}: a check is an object with one kind ({', '.join(KINDS)})"]
    kind = kind_of(check)
    if kind is None:
        return [f"{where}: one kind per check, not {sorted(k for k in check if k in KINDS)}"]
    if kind not in KINDS:
        if kind in extra_kinds:
            return []
        return [f"{where}: unknown check kind {kind!r}"]
    v = check[kind]
    opts = {k for k in check if k != kind}
    allowed = {"prop": {"name", "unit", "tol", *CMP}, "volume": {"tol", *CMP}, "bbox": {"size", "min", "tol"},
               "sketch": {"closed", "dof", "full", "external", "radii", "tol", "dof_max", "count", "dims"}, "file": {"min_bytes"}, "selected": {"sub"}, "valid": {"solid"},
               "expr": {"uses", "count", "path"}, "follows": {"object", "by", "axis", "change", "tol"}}.get(kind, set())
    if opts - allowed:
        out.append(f"{where}: {kind} takes no {', '.join(sorted(opts - allowed))}")
    if kind in LOGIC_KINDS:
        items = [v] if kind == "not" else v
        if kind != "not" and (not isinstance(v, list) or not v):
            return out + [f"{where}.{kind}: a list of checks"]
        for i, c in enumerate(items):
            out += problems(c, f"{where}.{kind}" + (f"[{i}]" if kind != "not" else ""), extra_kinds)
        return out
    if kind in ("exists", "absent", "new"):
        if not (isinstance(v, str) and v) and not (isinstance(v, dict) and v and set(v) <= {"type", "in", "label", "where"}):
            out.append(f"{where}.{kind}: an object, a type (\"PartDesign::Pad\") or {{type, in, label, where}}")
        elif isinstance(v, dict) and "where" in v:
            w = v["where"]
            if not (isinstance(w, dict) and w):
                out.append(f"{where}.{kind}.where: {{property: value}}, such as {{\"ThreadSize\": \"M4\"}}")
            else:
                for pn, pv in w.items():
                    if isinstance(pv, dict) and set(pv) == {"set"}:
                        if not isinstance(pv["set"], bool):
                            out.append(f"{where}.{kind}.where.{pn}.set: true or false")
                    elif isinstance(pv, dict):
                        if not any(k in pv for k in CMP) or set(pv) - set(CMP) - {"tol"}:
                            out.append(f"{where}.{kind}.where.{pn}: a value, or {{eq|lt|gt|le|ge: n, tol}}")
                    elif not isinstance(pv, (str, int, float, bool)):
                        out.append(f"{where}.{kind}.where.{pn}: a value, or {{eq|lt|gt|le|ge: n, tol}}")
    elif kind == "prop":
        if not isinstance(check.get("name"), str):
            out.append(f"{where}: prop needs name (the property)")
        if not any(k in check for k in CMP):
            out.append(f"{where}: prop needs one of {', '.join(CMP)}")
    elif kind == "volume":
        if not any(k in check for k in CMP):
            out.append(f"{where}: volume needs one of {', '.join(CMP)}")
    elif kind == "bbox":
        size = check.get("size")
        if not (isinstance(size, list) and len(size) == 3):
            out.append(f"{where}: bbox needs size [x, y, z] (mm)")
        low = check.get("min")
        if low is not None and not (isinstance(low, list) and len(low) == 3 and all(number(x) is not None for x in low)):
            out.append(f"{where}: min is the box's lowest corner [x, y, z] (mm)")
    elif kind == "expr":
        if not isinstance(v, str):
            out.append(f"{where}.expr: an object")
        if not (isinstance(check.get("uses"), str) and check["uses"].isidentifier()):
            out.append(f"{where}: expr needs uses (the parameter's name, such as size)")
        if "count" in check and not (isinstance(check["count"], int) and not isinstance(check["count"], bool) and check["count"] >= 1):
            out.append(f"{where}: count is a whole number, 1 or more")
    elif kind == "follows":
        if not (isinstance(v, str) and v.isidentifier()):
            out.append(f"{where}.follows: the parameter's name (size)")
        if not isinstance(check.get("object"), str):
            out.append(f"{where}: follows needs object (the body or feature that should change)")
        if check.get("axis") not in (None, "x", "y", "z"):
            out.append(f"{where}: axis is x, y or z")
        if "change" in check and "axis" not in check:
            out.append(f"{where}: change needs axis")
        for k in ("by", "change", "tol"):
            if k in check and number(check[k]) is None:
                out.append(f"{where}: {k} is a number (mm)")
        if number(check.get("by", 5)) == 0:
            out.append(f"{where}: by is not 0")
    elif kind == "file":
        if not (isinstance(v, str) and v and os.path.basename(v) == v and not v.startswith(".")):
            out.append(f"{where}.file: a plain file name in the session's folder, no path")
    elif kind == "workbench":
        if not isinstance(v, str):
            out.append(f"{where}.workbench: a workbench's name (PartDesignWorkbench)")
    elif kind == "used":
        if not isinstance(v, str):
            out.append(f"{where}.used: a command's name (PartDesign_Pad)")
    elif kind == "task_open":
        if not (v is None or v is True or isinstance(v, str)):
            out.append(f"{where}.task_open: a dialog's name, true or null")
    elif kind in ("editing",):
        if not (v is None or isinstance(v, str)):
            out.append(f"{where}.editing: an object, or null")
    elif kind in ("selected", "valid", "sketch"):
        if not isinstance(v, str):
            out.append(f"{where}.{kind}: an object")
    if kind in ("volume", "bbox"):
        v = check[kind]
        if not ((isinstance(v, str) and v) or (isinstance(v, dict) and v and set(v) <= {"type", "in", "label", "where"})):
            out.append(f"{where}.{kind}: an object, or a query {{type, in, label, where}}")
    if kind == "sketch" and "radii" in check:
        r = check["radii"]
        if not (isinstance(r, list) and r and all(_is_var(x) or (number(x) is not None and number(x) > 0) for x in r)):
            out.append(f"{where}: radii is a list of radii (mm)")
    if kind == "sketch" and "dims" in check:
        r = check["dims"]
        if not (isinstance(r, list) and r and all(_is_var(x) or (number(x) is not None and number(x) > 0) for x in r)):
            out.append(f"{where}: dims is a list of dimensions (mm)")
    for k in ("dof_max", "count"):
        if kind == "sketch" and k in check and not (isinstance(check[k], int) and not isinstance(check[k], bool) and check[k] >= 0):
            out.append(f"{where}: {k} is a whole number")
    if kind == "sketch" and "external" in check and not (isinstance(check["external"], int) and check["external"] >= 1):
        out.append(f"{where}: external is a whole number, 1 or more")
    return out
