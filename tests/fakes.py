# SPDX-License-Identifier: LGPL-2.1-or-later
# Plain stand-ins for a FreeCAD document, so checks and the engine are tested
# without FreeCAD.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


class BoundBox:
    def __init__(self, x, y, z, low=(0, 0, 0)):
        self.XLength, self.YLength, self.ZLength = x, y, z
        self.XMin, self.YMin, self.ZMin = low


class Wire:
    def __init__(self, closed=True):
        self.closed = closed

    def isClosed(self):
        return self.closed


class Shape:
    def __init__(self, volume=0.0, size=(0, 0, 0), solids=1, wires=(), null=False, low=(0, 0, 0)):
        self.Volume = volume
        self.BoundBox = BoundBox(*size, low=low)
        self.Solids = [object()] * solids
        self.Wires = list(wires)
        self.null = null

    def isNull(self):
        return self.null


class Quantity:
    def __init__(self, value, unit="mm"):
        self.Value = value
        self.unit = unit


class Obj:
    def __init__(self, name, type_id, label=None, shape=None, state=(), **props):
        self.Name = name
        self.TypeId = type_id
        self.Label = label or name
        self.Shape = shape
        self.State = list(state)
        self.Group = []
        self.valid = True
        for k, v in props.items():
            setattr(self, k, v)

    def isValid(self):
        return self.valid

    def isDerivedFrom(self, t):
        # As FreeCAD's: every Part:: shape type is made from Part::Feature.
        return self.TypeId == t or (t == "Part::Feature" and self.TypeId.startswith("Part::"))

    def hasObject(self, o):
        return o in self.Group


class Doc:
    def __init__(self):
        self.Objects = []

    def add(self, name, type_id, inside=None, **kw):
        n, i = name, 1
        while self.getObject(n) is not None:
            n = f"{name}{i:03d}"
            i += 1
        o = Obj(n, type_id, **kw)
        self.Objects.append(o)
        if inside is not None:
            inside.Group.append(o)
        return o

    def getObject(self, name):
        return next((o for o in self.Objects if o.Name == name), None)

    def remove(self, name):
        self.Objects = [o for o in self.Objects if o.Name != name]
