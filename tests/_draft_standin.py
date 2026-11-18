# SPDX-License-Identifier: LGPL-2.1-or-later
# A stand-in for the Draft objects that Agent Link's Draft tools make in
# FreeCAD 1.1, as FreeCAD's own source makes them (src/Mod/Draft/draftmake,
# draftfunctions/upgrade.py of tag 1.1.3):
#   draft_shape arc, circle   Part::Part2DObjectPython, Proxy Circle
#                             (Radius, FirstAngle, LastAngle)
#   draft_shape rectangle     Part::Part2DObjectPython, Proxy Rectangle
#   draft_shape polygon       Part::Part2DObjectPython, Proxy Polygon
#   draft_shape wire, bspline Part::FeaturePython, Proxy Wire or BSpline
#   draft_modify upgrade      Draft's makeWires: one plain Part::Feature
#                             "Wire" for each cluster of edges that meet
#                             (1e-7 mm), the inputs removed
#   draft_link_array polar    Part::FeaturePython, Proxy Array
#   draft_dimension linear    App::FeaturePython, Proxy LinearDimension
# Each shape has its edges, wires and a box from points along it, so a
# lesson's bbox, draft and shape checks are tested without FreeCAD. The
# real check is the live replay.
import math

from fakes import BoundBox, Quantity

TOL = 1e-7


class Proxy:
    def __init__(self, kind):
        self.Type = kind


class Edge:
    def __init__(self, pts):
        self.pts = [tuple(float(c) for c in p) for p in pts]

    @property
    def ends(self):
        return self.pts[0], self.pts[-1]


class Wire:
    def __init__(self, edges, closed):
        self.Edges = edges
        self.closed = closed

    def isClosed(self):
        return self.closed


class DShape:
    """Edges as point lists; Wires as the clusters whose ends meet."""

    def __init__(self, edges, closed=None):
        self.Edges = list(edges)
        self.Wires = clusters(self.Edges) if closed is None else [Wire(self.Edges, closed)]
        self.Solids = []
        self.Faces = []
        self.Volume = 0.0
        pts = [p for e in self.Edges for p in e.pts] or [(0.0, 0.0, 0.0)]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        self.BoundBox = BoundBox(*(h - l for h, l in zip(hi, lo)), low=tuple(lo))

    def isNull(self):
        return False


def _same(p, q):
    return math.dist(p, q) <= TOL


def clusters(edges):
    """The wires edges make: the ones whose ends meet within 1e-7 mm, as
    Part.sortEdges joins them."""
    left, out = list(edges), []
    while left:
        group = [left.pop(0)]
        grew = True
        while grew:
            grew = False
            ends = [p for e in group for p in e.ends]
            for e in list(left):
                if any(_same(a, b) for a in e.ends for b in ends):
                    group.append(e)
                    left.remove(e)
                    grew = True
        free = [p for e in group for p in e.ends]
        closed = all(sum(_same(p, q) for q in free) >= 2 for p in free)
        out.append(Wire(group, closed))
    return out


def arc_points(r, a0, a1, centre=(0.0, 0.0, 0.0), n=360):
    span = (a1 - a0) % 360 or 360
    cx, cy, cz = centre
    return [(cx + r * math.cos(math.radians(a0 + span * i / n)), cy + r * math.sin(math.radians(a0 + span * i / n)), cz) for i in range(n + 1)]


def _rot(p, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


def make(world, name, args):
    """What the Draft tool name makes from args in world.doc; None when name
    is not one this stand-in knows (the caller answers it)."""
    doc = world.doc
    if name == "draft_shape":
        kind = args.get("kind")
        at = tuple(args.get("at") or (0, 0, 0))
        if kind in ("arc", "circle"):
            r = float(args["radius"])
            a0, a1 = (float(args.get("start", 0)), float(args.get("end", 90))) if kind == "arc" else (0.0, 360.0)
            sh = DShape([Edge(arc_points(r, a0, a1, at))], closed=kind == "circle")
            props = dict(Radius=Quantity(r), FirstAngle=Quantity(a0 if kind == "arc" else 0.0, "deg"),
                         LastAngle=Quantity(a1 if kind == "arc" else 0.0, "deg"))
            return doc.add("Arc" if kind == "arc" else "Circle", "Part::Part2DObjectPython", shape=sh, Proxy=Proxy("Circle"),
                           label=args.get("name"), **props)
        if kind == "rectangle":
            L, H = float(args["length"]), float(args["height"])
            x, y, z = at
            c = [(x, y, z), (x + L, y, z), (x + L, y + H, z), (x, y + H, z)]
            sh = DShape([Edge([c[i], c[(i + 1) % 4]]) for i in range(4)])
            return doc.add("Rectangle", "Part::Part2DObjectPython", shape=sh, Proxy=Proxy("Rectangle"), label=args.get("name"),
                           Length=Quantity(L), Height=Quantity(H))
        if kind == "polygon":
            n, r = int(args.get("sides", 6)), float(args["radius"])
            c = [(at[0] + r * math.cos(2 * math.pi * i / n), at[1] + r * math.sin(2 * math.pi * i / n), at[2]) for i in range(n)]
            sh = DShape([Edge([c[i], c[(i + 1) % n]]) for i in range(n)])
            return doc.add("Polygon", "Part::Part2DObjectPython", shape=sh, Proxy=Proxy("Polygon"), label=args.get("name"),
                           FacesNumber=n, Radius=Quantity(r))
        if kind in ("wire", "bspline"):
            pts = [tuple(p) for p in args["points"]]
            edges = [Edge([pts[i], pts[i + 1]]) for i in range(len(pts) - 1)] if kind == "wire" else [Edge(pts)]
            base = ("Line" if len(pts) == 2 else "Wire") if kind == "wire" else "BSpline"
            return doc.add(base, "Part::FeaturePython", shape=DShape(edges), Proxy=Proxy("Wire" if kind == "wire" else "BSpline"),
                           label=args.get("name"), Points=pts, Closed=bool(args.get("closed")))
        return None
    if name == "draft_modify" and args.get("op") == "upgrade":
        objs = [o for o in (doc.getObject(n) for n in args["objects"]) if o is not None]
        edges = [e for o in objs for e in o.Shape.Edges]
        made = [doc.add("Wire", "Part::Feature", shape=DShape(w.Edges, closed=w.closed)) for w in clusters(edges)]
        if args.get("delete", True):
            for o in objs:
                doc.Objects.remove(o)
        return made[0] if made else None
    if name == "draft_link_array" and args.get("kind") == "polar":
        base = doc.getObject(args["object"])
        if base is None:
            return None
        n, ang = int(args.get("count", 4)), float(args.get("angle", 360))
        step = ang / n if abs(ang) >= 360 else ang / max(n - 1, 1)
        edges = [Edge([_rot(p, step * k) for p in e.pts]) for k in range(n) for e in base.Shape.Edges]
        return doc.add("Array", "Part::FeaturePython", shape=DShape(edges, closed=True), Proxy=Proxy("Array"), label=args.get("name"),
                       Base=base, ArrayType="polar", NumberPolar=n, Angle=Quantity(ang, "deg"))
    if name == "draft_dimension" and args.get("kind") == "linear":
        d = math.dist(args["from"], args["to"])
        return doc.add("Dimension", "App::FeaturePython", Proxy=Proxy("LinearDimension"), label=args.get("name"), Distance=Quantity(d))
    return None
