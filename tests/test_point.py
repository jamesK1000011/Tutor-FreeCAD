# SPDX-License-Identifier: LGPL-2.1-or-later
# tutor_point and the target resolver without a window: a stand-in window
# answers what targets.py asks, stand-in overlay and annotation services
# record what would be drawn. Every target kind, found, missing or hidden,
# with the reasons the agent gets; the never-list; the family's surface and
# the Tutor tab's words.
import json
import os
import re
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gen_agentlink_tools  # noqa: E402

from agentlink_tutor import point, tab, targets, window  # noqa: E402

AL = gen_agentlink_tools.source()
if AL and os.path.dirname(AL) not in sys.path:
    sys.path.append(os.path.dirname(AL))


class Obj:
    def __init__(self, name, label=None):
        self.Name, self.Label = name, label or name


class Win:
    """What the FreeCAD window would answer. Every switch or click is a
    failure: the resolver only reads."""

    def __init__(self, **kw):
        self.active = kw.get("active", "PartWorkbench")
        self.benches = kw.get("benches", ["PartWorkbench", "PartDesignWorkbench", "SketcherWorkbench"])
        self.commands = kw.get("commands", {"PartDesign_Pad": [], "Std_Undo": [("undo-btn", None)]})
        self.menus = kw.get("menus", {})
        self.groups = kw.get("groups", {})
        self.native = kw.get("native", False)
        self.task = kw.get("task", None)
        self.objs = {o.Name: o for o in kw.get("objs", [Obj("Sketch"), Obj("Pad")])}
        self.rows = kw.get("rows", {})
        self.docks = kw.get("docks", {})
        self.hidden = kw.get("hidden", {})
        self.selector = kw.get("selector", {"widget": "wb-tabs"})
        self.view = kw.get("view", {"widget": "3d-view"})
        self.face_names = kw.get("faces", ["Face6"])
        self.exts = kw.get("exts", {})

    def __getattr__(self, k):
        if k.startswith(("activate", "run", "click", "select", "set", "expand", "open")):
            raise AssertionError(f"the resolver called {k}: it must only read")
        raise AttributeError(k)

    def visible(self, spec):
        w = spec.get("widget") if isinstance(spec, dict) else spec
        return self.hidden.get(w)

    def active_workbench(self):
        return self.active

    def loaded_benches(self):
        return self.benches

    def bench_title(self, wb):
        return {"PartDesignWorkbench": "Part Design", "PartWorkbench": "Part", "SketcherWorkbench": "Sketcher"}.get(wb, wb)

    def workbench_of(self, cmd):
        return {"PartDesign_": "PartDesignWorkbench", "Part_": "PartWorkbench"}.get(cmd.split("_")[0] + "_")

    def command_exists(self, cmd):
        return cmd in self.commands

    def command_info(self, cmd):
        return {"PartDesign_Pad": {"menuText": "Pad", "shortcut": None}, "Std_Undo": {"menuText": "Undo", "shortcut": "Ctrl+Z"}}.get(cmd, {})

    def command_buttons(self, cmd):
        return list(self.commands.get(cmd, []))

    def command_groups(self, cmd):
        return list(self.groups.get(cmd, []))

    def menu_titles(self):
        return ["File", "Edit", "Part"]

    def menu_path_of(self, cmd):
        return next((list(t) for t, c in self.menus.items() if c == cmd), None)

    def menu_info(self, titles):
        got = self.menus.get(tuple(titles))
        if got is None:
            return {"missing": titles[-1]}
        return {"native": self.native, "cmd": got}

    def workbench_selector(self, wb):
        return self.selector

    def task_open(self):
        return self.task is not None

    def task_widget(self, name=None, label=None, button=None):
        t = self.task or {}
        for key in (name, label, button):
            if key and key in t:
                return t[key]
        return None, f"no {(name or label or button)!r} in the open task dialog"

    def obj(self, ref):
        return self.objs.get(ref) or next((o for o in self.objs.values() if o.Label == ref), None)

    def tree_row(self, obj):
        return self.rows.get(obj.Name, (None, f"{obj.Label} is not in the Model tree"))

    def faces(self, obj, q):
        return (self.face_names, None) if self.face_names else ([], "no face matches the query")

    def edges(self, obj, q):
        return (["Edge3"], None) if q.get("near") else ([], "edge: a query")

    def dock(self, title):
        return self.docks.get(title)

    def view3d(self):
        return self.view

    def ext(self, spec):
        return self.exts.get(spec["ext"])


class Overlay:
    def __init__(self, hidden=None, native=False, missing=None):
        self.shows, self.menus, self.clears, self.watched = [], [], [], []
        self.hide = hidden or {}
        self.native, self.missing = native, missing

    def show(self, specs, say=None, ms=None, owner=""):
        self.shows.append({"specs": specs, "say": say, "ms": ms, "owner": owner})
        hid = [(i, self.hide[s["widget"]]) for i, s in enumerate(specs) if s["widget"] in self.hide]
        return {"handle": 7, "shown": [i for i in range(len(specs)) if i not in dict(hid)], "hidden": hid}

    def watch_menu(self, menu, action, owner="", handle=None, badge=None):
        self.watched.append((menu, action, owner, handle, badge))

    def menu(self, titles, badge=None, owner="", handle=None, say=None, ms=None):
        self.menus.append((tuple(titles), badge, handle))
        if self.native:
            return {"native": True}
        if self.missing:
            return {"missing": self.missing}
        return {"handle": handle}

    def clear(self, owner=None, handle=None):
        self.clears.append(owner)

    def colours(self):
        return {"accent": "#123456"}


class Ann:
    def __init__(self):
        self.lit, self.clears = [], []

    badges = None

    def light(self, obj, subs, owner="", colour=None, badge=None):
        self.badges = (self.badges or []) + [badge]
        self.lit.append((obj.Name, list(subs), colour))
        bad = [s for s in subs if s.startswith("Face9")]
        return {"lit": [s for s in subs if s not in bad], "missing": [(s, "no such face") for s in bad]}

    def clear(self, owner=None):
        self.clears.append(owner)


class Hooks:
    def __init__(self, ov=None, ann=None):
        self.s = {"overlay": ov, "annotations": ann}

    def service(self, name):
        return self.s.get(name)


def run(args, win=None, ov=None, ann=None, bindings=None):
    ov = Overlay() if ov is None else ov
    ann = Ann() if ann is None else ann
    out = point.point(args, win or Win(), hooks=Hooks(ov, ann), bindings=bindings)
    return out, ov, ann


def by_n(out):
    return {a["n"]: a for a in out["shown"] + out["missing"]}


class Commands(unittest.TestCase):
    def test_button_shown_with_its_badge(self):
        out, ov, _ = run({"targets": [{"cmd": "Std_Undo"}], "say": "Undo it."})
        self.assertEqual(out["shown"], [{"n": 1, "kind": "cmd", "on": "Std_Undo button"}])
        self.assertEqual(ov.shows[0]["specs"], [{"widget": "undo-btn", "badge": 1}])
        self.assertEqual(ov.shows[0]["say"], "Undo it.")
        self.assertEqual(ov.shows[0]["owner"], "tutor")

    def test_hidden_toolbar_says_which_workbench(self):
        out, ov, _ = run({"targets": [{"cmd": "PartDesign_Pad"}], "say": "Press Pad."})
        m = out["missing"][0]
        self.assertEqual(m["why"], "toolbar hidden: Part Design is not the active workbench; call workbench activate first")
        self.assertIn("1. Pad", ov.shows[0]["say"])  # the callout says it instead
        self.assertEqual(out["note"], "nothing ringed; any words for them are in the callout")

    def test_unknown_command(self):
        out, _, _ = run({"targets": [{"cmd": "Nope_Cmd"}]})
        self.assertEqual(out["missing"][0]["why"], "no command Nope_Cmd in this FreeCAD")

    def test_button_on_toolbar_of_active_bench_but_hidden(self):
        w = Win(active="PartDesignWorkbench", commands={"PartDesign_Pad": [("pad-btn", "hidden")]})
        out, _, _ = run({"targets": [{"cmd": "PartDesign_Pad"}]}, w)
        self.assertEqual(out["missing"][0]["why"], "its toolbar is hidden or covered")

    def test_overlay_finds_it_covered(self):
        w = Win(commands={"Std_Undo": [("undo-btn", None)]})
        out, _, _ = run({"targets": [{"cmd": "Std_Undo"}]}, w, ov=Overlay(hidden={"undo-btn": "covered"}))
        self.assertEqual(out["missing"][0]["why"], "it is covered")


class Menus(unittest.TestCase):
    PATH = ["Part Design", "Create an additive feature", "Pad"]

    def test_menubar_ringed_through_the_overlay(self):
        w = Win(menus={tuple(self.PATH): "PartDesign_Pad"})
        out, ov, _ = run({"targets": [{"cmd": "Std_Undo"}, {"menu": self.PATH}]}, w)
        self.assertEqual(ov.menus, [(tuple(self.PATH), 2, 7)])
        self.assertEqual(by_n(out)[2]["kind"], "menu")
        self.assertNotIn(2, {a["n"] for a in out["missing"]})

    def test_native_menubar_gives_the_path_and_the_toolbar_button(self):
        w = Win(native=True, menus={("Edit", "Undo"): "Std_Undo"})
        out, ov, _ = run({"targets": [{"menu": ["Edit", "Undo"]}], "say": "Undo."}, w)
        got = out["shown"][0]
        self.assertEqual(got["note"], "menu: native")
        self.assertEqual(got["text"], "Menu: Edit › Undo (Ctrl+Z), or the toolbar button ringed here")
        self.assertEqual(ov.menus, [])  # never drawn over the system menubar
        self.assertEqual(ov.shows[0]["specs"], [{"widget": "undo-btn", "badge": 1}])
        self.assertIn("1. Menu: Edit › Undo", ov.shows[0]["say"])

    def test_native_menubar_without_a_button(self):
        w = Win(native=True, menus={tuple(self.PATH): "PartDesign_Pad"})
        out, _, _ = run({"targets": [{"menu": self.PATH}]}, w)
        m = out["missing"][0]
        self.assertIn("cannot be drawn over", m["why"])
        self.assertEqual(m["text"], "Menu: Part Design › Create an additive feature › Pad")

    def test_menu_by_command_reads_this_windows_path(self):
        path = ("Part Design", "Additive Features", "Pad")  # FreeCAD 1.1.3's own submenu
        w = Win(menus={path: "PartDesign_Pad"})
        out, ov, _ = run({"targets": [{"menu": "PartDesign_Pad"}]}, w)
        self.assertEqual(ov.menus, [(path, 1, 7)])
        out, _, _ = run({"targets": [{"menu": "PartDesign_Pad"}]}, Win(active="SketcherWorkbench"))
        why = out["missing"][0]["why"]
        self.assertIn("Pad is in no menu of this window", why)
        self.assertIn("comes with Part Design", why)

    def test_path_to_walks_submenus(self):
        class A:
            def __init__(self, text, name="", menu=None, sep=False):
                self.t, self.n, self.m, self.sep = text, name, menu, sep

            def text(self):
                return self.t

            def objectName(self):
                return self.n

            def menu(self):
                return self.m

            def isSeparator(self):
                return self.sep

        class M:
            def __init__(self, *acts):
                self.acts = list(acts)

            def actions(self):
                return self.acts

        add = M(A("&Pad", "PartDesign_Pad"), A("Revolution", "PartDesign_Revolution"))
        bar = [A("&File", menu=M(A("Export…", "Std_Export"))),
               A("&Part Design", menu=M(A("", sep=True), A("Additive Features", menu=add)))]
        self.assertEqual(window.path_to(bar, "PartDesign_Pad"), ["Part Design", "Additive Features", "Pad"])
        self.assertEqual(window.path_to(bar, "Std_Export"), ["File", "Export…"])
        self.assertIsNone(window.path_to(bar, "PartDesign_Pocket"))

    def test_missing_title_names_the_workbench_menu(self):
        out, _, _ = run({"targets": [{"menu": self.PATH}]})
        self.assertIn("no menu item 'Pad'", out["missing"][0]["why"])
        self.assertIn("call workbench activate first", out["missing"][0]["why"])


class Dropdowns(unittest.TestCase):
    """A command inside a toolbar dropdown (FreeCAD 1.1.3's group commands):
    the dropdown's button ringed, the item inside it when it is opened."""

    def test_group_buttons_for_any_grouped_command(self):
        for cmd, btn in (("Sketcher_CreateRectangle", "rects-btn"), ("Sketcher_CreateArc", "arcs-btn"),
                         ("Sketcher_CreateCircle", "circles-btn"), ("PartDesign_AdditiveBox", "prims-btn")):
            with self.subTest(cmd=cmd):
                w = Win(commands={cmd: [("hidden-sketcher-btn", "hidden")]}, groups={cmd: [(btn, None, f"{btn}-menu", f"{cmd}-act")]})
                out, ov, _ = run({"targets": [{"cmd": cmd}], "say": "Draw it."}, w)
                got = out["shown"][0]
                self.assertEqual((got["kind"], got["note"]), ("cmd", "in the ▾ menu of this button"))
                self.assertEqual(ov.shows[0]["specs"], [{"widget": btn, "badge": 1}])
                self.assertEqual(ov.watched, [(f"{btn}-menu", f"{cmd}-act", "tutor", 7, 1)])
                self.assertIn("Open the ▾ menu of the ringed button.", ov.shows[0]["say"])

    def test_own_button_first_and_hidden_dropdown_not_used(self):
        w = Win(commands={"Sketcher_CreateLine": [("line-btn", None)]}, groups={"Sketcher_CreateLine": [("x", None, "m", "a")]})
        out, ov, _ = run({"targets": [{"cmd": "Sketcher_CreateLine"}]}, w)
        self.assertEqual(ov.shows[0]["specs"], [{"widget": "line-btn", "badge": 1}])
        self.assertEqual(ov.watched, [])
        w = Win(active="PartDesignWorkbench", commands={"Sketcher_CreateRectangle": []}, groups={"Sketcher_CreateRectangle": [("b", "hidden", "m", "a")]})
        out, _, _ = run({"targets": [{"cmd": "Sketcher_CreateRectangle"}]}, w)
        self.assertEqual(out["missing"][0]["why"], "no toolbar button for it here")


class Benches(unittest.TestCase):
    def test_selector(self):
        out, ov, _ = run({"targets": [{"wb": "PartDesignWorkbench"}]})
        self.assertEqual(out["shown"][0]["on"], "workbench Part Design")
        self.assertEqual(ov.shows[0]["specs"][0]["widget"], "wb-tabs")

    def test_already_active(self):
        out, _, _ = run({"targets": [{"wb": "PartWorkbench"}]})
        self.assertEqual(out["shown"][0]["note"], "already active")

    def test_not_installed_and_selector_hidden(self):
        out, _, _ = run({"targets": [{"wb": "MineWorkbench"}]})
        self.assertEqual(out["missing"][0]["why"], "MineWorkbench is not installed in this FreeCAD")
        out, _, _ = run({"targets": [{"wb": "SketcherWorkbench"}]}, Win(selector=None))
        self.assertEqual(out["missing"][0]["text"], "View › Workbench › Sketcher")


class Tasks(unittest.TestCase):
    def test_no_dialog(self):
        out, _, _ = run({"targets": [{"task": "Length"}]})
        self.assertEqual(out["missing"][0]["why"], "no task dialog is open")

    def test_by_name_then_label_then_button(self):
        w = Win(task={"lengthEdit": ({"widget": "length"}, None), "Length": ({"widget": "length"}, "by its label"),
                      "ok": ({"widget": "ok"}, None)})
        out, ov, _ = run({"targets": [{"task": {"name": "lengthEdit", "label": "Length"}}, {"task": "Length"}, {"task": {"button": "ok"}}]}, w)
        self.assertEqual([a["n"] for a in out["shown"]], [1, 2, 3])
        self.assertEqual(by_n(out)[2]["note"], "by its label")
        self.assertEqual([s["widget"] for s in ov.shows[0]["specs"]], ["length", "length", "ok"])

    def test_tasks_tab_header(self):
        w = Win(task={"Length": ({"widget": "tasks-tab"}, "the Tasks tab is not in front: its tab is ringed")})
        out, _, _ = run({"targets": [{"task": "Length"}]}, w)
        self.assertEqual(out["shown"][0]["note"], "the Tasks tab is not in front: its tab is ringed")

    def test_not_in_dialog(self):
        out, _, _ = run({"targets": [{"task": "Angle"}]}, Win(task={}))
        self.assertEqual(out["missing"][0]["why"], "no 'Angle' in the open task dialog")


class Tree(unittest.TestCase):
    def test_binding_and_folded_parent(self):
        w = Win(objs=[Obj("Sketch001", "Sketch")], rows={"Sketch001": ({"widget": "tree", "rect": None}, "inside Body, which is folded: its row is ringed")})
        out, _, _ = run({"targets": [{"tree": "$sketch"}]}, w, bindings={"sketch": "Sketch001"})
        self.assertEqual(out["shown"][0]["on"], "tree Sketch")
        self.assertIn("folded", out["shown"][0]["note"])

    def test_unbound_and_missing(self):
        out, _, _ = run({"targets": [{"tree": "$sketch"}, {"tree": "Ghost"}, {"tree": "Pad"}]})
        n = by_n(out)
        self.assertEqual(n[1]["why"], "nothing is bound to $sketch: name the object")
        self.assertEqual(n[2]["why"], "no object Ghost in the document")
        self.assertEqual(n[3]["why"], "Pad is not in the Model tree")


class ThreeD(unittest.TestCase):
    def test_face_lit_in_the_accent_never_selected(self):
        out, ov, ann = run({"targets": [{"face": {"normal": [0, 0, 1], "largest": True}, "of": "$pad"}]}, bindings={"pad": "Pad"})
        self.assertEqual(ann.lit, [("Pad", ["Face6"], "#123456")])
        self.assertEqual(out["shown"][0]["on"], "Face6 of Pad")
        self.assertEqual(ov.shows[0]["specs"], [])

    def test_edge_sub_and_misses(self):
        out, _, ann = run({"targets": [{"edge": {"near": [0, 0, 0]}, "of": "Pad"}, {"sub": "Face9", "of": "Pad"},
                                       {"face": {"normal": [1, 0, 0]}, "of": "Ghost"}]}, Win())
        n = by_n(out)
        self.assertEqual(n[1]["on"], "Edge3 of Pad")
        self.assertEqual(n[2]["why"], "Face9: no such face")
        self.assertEqual(n[3]["why"], "no object Ghost in the document")
        self.assertEqual(ann.clears, ["tutor"])

    def test_badge_number_in_the_view(self):
        _out, _ov, ann = run({"targets": [{"cmd": "Std_Undo"}, {"sub": "Face6", "of": "Pad"}]})
        self.assertEqual(ann.badges, [2])

    def test_of_inside_the_query_and_at_for_near(self):
        seen = []
        w = Win()
        w.faces = lambda obj, q: (seen.append(q), (["Face6"], None))[1]
        out, _, _ = run({"targets": [{"face": {"of": "Pad", "at": [0, 5, 10], "normal": [0, 0, 1]}}]}, w)
        self.assertEqual(out["shown"][0]["on"], "Face6 of Pad")
        self.assertEqual(seen, [{"near": [0, 5, 10], "normal": [0, 0, 1]}])

    def test_of_missing_says_where_it_goes(self):
        from agentlink_tutor import lessons

        with self.assertRaises(lessons.LessonError) as e:
            lessons.target_kind({"face": {"of": "Pad", "near": [0, 0, 0]}})
        self.assertIn("put of beside face, not inside it", str(e.exception))
        with self.assertRaises(lessons.LessonError) as e:
            lessons.target_kind({"edge": {"near": [0, 0, 0]}})
        self.assertIn("of, beside edge, names the object", str(e.exception))

    def test_no_face_matches(self):
        out, _, _ = run({"targets": [{"face": {"normal": [1, 0, 0]}, "of": "Pad"}]}, Win(faces=[]))
        self.assertEqual(out["missing"][0]["why"], "no face matches the query")


class DocksViewsExt(unittest.TestCase):
    def test_dock_closed(self):
        w = Win(docks={"Report view": {"widget": "report"}}, hidden={"report": "hidden"})
        out, _, _ = run({"targets": [{"dock": "Report view"}, {"dock": "Nope"}]}, w)
        n = by_n(out)
        self.assertEqual(n[1]["why"], "Report view is closed")
        self.assertEqual(n[1]["text"], "View › Panels › Report view")
        self.assertEqual(n[2]["why"], "no panel Nope")

    def test_view(self):
        out, _, _ = run({"targets": [{"view": "3d"}, {"view": "page"}]})
        self.assertEqual([a["n"] for a in out["shown"]], [1])
        self.assertEqual(by_n(out)[2]["why"], "views: 3d")

    def test_ext(self):
        w = Win(exts={"snap": {"marks": [{"widget": "snap-btn"}], "on": "Snapshot button"}})
        out, _, _ = run({"targets": [{"ext": "snap"}, {"ext": "other"}]}, w)
        self.assertEqual(out["shown"][0]["on"], "Snapshot button")
        self.assertEqual(by_n(out)[2]["why"], "no add-on here shows other")


class Surface(unittest.TestCase):
    def test_clear_and_keep(self):
        out, ov, ann = run({})
        self.assertEqual(out, {"cleared": True})
        self.assertEqual((ov.clears, ann.clears), (["tutor"], ["tutor"]))
        _out, ov, _ = run({"targets": [{"cmd": "Std_Undo"}], "clear": False})
        self.assertEqual(ov.clears, [])

    def test_refusals(self):
        for args, part in (({"targets": [{"cmd": ""}]}, "targets[0]"), ({"targets": [{"bogus": 1}]}, "targets[0]"),
                           ({"targets": [{"cmd": "A"}] * 7}, "at most 6"), ({"targets": [], "ms": 5}, "ms: 500"),
                           ({"targets": "Pad"}, "targets: a list")):
            with self.assertRaises(point.Refusal) as e:
                run(args)
            self.assertEqual(e.exception.code, "invalid_input")
            self.assertIn(part, e.exception.message)

    def test_no_overlay(self):
        out, _, _ = point.point({"targets": [{"cmd": "Std_Undo"}]}, Win(), hooks=Hooks(None, None)), None, None
        self.assertIn("overlay is not here", out["missing"][0]["why"])

    def test_answer_stays_small(self):
        tg = [{"cmd": "PartDesign_Pad"}, {"menu": ["Part Design", "Pad"]}, {"task": "Length"}, {"tree": "$x"},
              {"dock": "Report view"}, {"view": "3d"}]
        out, _, _ = run({"targets": tg, "say": "x" * 300, "ms": 9000})
        self.assertLess(len(json.dumps(out, ensure_ascii=False)), 1400)
        self.assertEqual(out["until"], "9000 ms")

    def test_a_broken_target_is_a_target_missed(self):
        w = Win()
        w.dock = lambda title: 1 / 0
        out, _, _ = run({"targets": [{"dock": "Report view"}]}, w)
        self.assertIn("could not be found", out["missing"][0]["why"])

    def test_callout_words(self):
        f1, f2 = targets.Found(1, "cmd"), targets.Found(2, "menu")
        f2.text = "Menu: Edit › Undo"
        self.assertEqual(point.callout("Undo it.", [f1, f2]), "Undo it.\n2. Menu: Edit › Undo")
        self.assertIsNone(point.callout("  ", [f1]))


class NeverList(unittest.TestCase):
    """The Tutor's window code reads; it never moves the cursor, sends
    input, takes focus, opens a menu, switches workbench or raises the
    window."""

    BAD = [r"QCursor", r"\.setPos\(", r"\.setFocus\(", r"\.popup\(", r"\.exec_?\(", r"activateWindow", r"showFullScreen",
           r"sendEvent", r"postEvent", r"QTest", r"\.click\(", r"\.trigger\(", r"\.raise_\(", r"activateWorkbench",
           r"setExpanded", r"scrollToItem", r"addSelection", r"runCommand"]

    def test_sources(self):
        for f in ("targets.py", "point.py", "window.py", "fam_tutor.py"):
            with open(os.path.join(ROOT, "agentlink_tutor", f), encoding="utf-8") as fh:
                src = fh.read()
            code = re.sub(r'"""[\s\S]*?"""', "", src)
            code = "\n".join(l for l in code.splitlines() if not l.strip().startswith("#"))
            for pat in self.BAD:
                self.assertIsNone(re.search(pat, code), f"{f}: {pat}")


class Edges(unittest.TestCase):
    def test_by_name_and_longest(self):
        e = [types.SimpleNamespace(Length=L) for L in (5, 20, 10)]
        shape = types.SimpleNamespace(Edges=e)
        self.assertEqual(window.edge_pick(shape, {"edges": ["Edge2", "Edge9"]}), ["Edge2"])
        self.assertEqual(window.edge_pick(shape, {"longest": True}), ["Edge2"])
        with self.assertRaises(ValueError):
            window.edge_pick(shape, {"edges": ["Edge9"]})
        with self.assertRaises(ValueError):
            window.edge_pick(types.SimpleNamespace(Edges=[]), {"longest": True})


class Item:
    def __init__(self, text, *kids, expanded=True):
        self.t, self.kids, self.p, self.exp = text, list(kids), None, expanded
        for k in kids:
            k.p = self

    def text(self, _c):
        return self.t

    def child(self, i):
        return self.kids[i]

    def childCount(self):
        return len(self.kids)

    def parent(self):
        return self.p

    def isExpanded(self):
        return self.exp


class Dead:
    """A Qt wrapper whose C++ object FreeCAD deleted: every call raises."""

    def __getattr__(self, k):
        def gone(*a, **kw):
            raise RuntimeError("Internal C++ object (PySide6.QtWidgets.QTreeWidget) already deleted.")

        return gone


class LiveItem(Item):
    dead = False

    def objectName(self):
        if self.dead:
            raise RuntimeError("Internal C++ object already deleted.")
        return ""


class FakeTree:
    def __init__(self, app, visible=True):
        self.app, self.visible = app, visible

    def metaObject(self):
        return types.SimpleNamespace(className=lambda: window.TREE)

    def objectName(self):
        return ""

    def isVisible(self):
        return self.visible

    def topLevelItemCount(self):
        return 1

    def topLevelItem(self, i):
        return self.app

    def viewport(self):
        return self

    def visualItemRect(self, it):
        n = 0 if it.t == "Sketch" else 1
        return types.SimpleNamespace(x=lambda: 0, y=lambda: 20 * n, width=lambda: 100, height=lambda: 18)


class RebuiltTree(unittest.TestCase):
    def setUp(self):
        self.was = window._qt
        window._qt = lambda: (None, None, types.SimpleNamespace(QTreeWidget=object))

    def tearDown(self):
        window._qt = self.was

    def win(self, trees):
        mw = types.SimpleNamespace(findChildren=lambda cls: list(trees))
        return window.Window(gui=types.SimpleNamespace(getMainWindow=lambda: mw), hooks=object())

    def test_a_deleted_tree_is_passed_over_and_the_row_found_again(self):
        sk = LiveItem("Sketch")
        trees = [Dead(), FakeTree(LiveItem("Application", LiveItem("Doc", LiveItem("Body", sk))))]
        w = self.win(trees)
        obj = types.SimpleNamespace(Label="Sketch", Document=types.SimpleNamespace(Label="Doc"))
        got, note = w.tree_row(obj)
        self.assertIsNone(note)
        self.assertEqual(got["rect"](), (0, 0, 100, 18))
        # FreeCAD rebuilds the tree: the old one dies, a new one holds a new row.
        sk.dead = True
        trees[:] = [Dead(), FakeTree(LiveItem("Application", LiveItem("Doc", LiveItem("Body", LiveItem("Sketch")))))]
        self.assertEqual(got["rect"](), (0, 0, 100, 18))
        trees[:] = [Dead()]
        self.assertEqual(w.trees(), [])
        self.assertEqual(w.tree_row(obj), (None, "no Model tree in this window"))

    def test_alive(self):
        self.assertFalse(window.alive(None))
        self.assertFalse(window.alive(Dead()))
        self.assertTrue(window.alive(FakeTree(None)))


class TreeItems(unittest.TestCase):
    def test_finds_the_row_in_its_document(self):
        a = Item("Sketch")
        b = Item("Sketch")
        app = Item("Application", Item("DocA", Item("Body", a)), Item("DocB", Item("Body", b)))
        tree = types.SimpleNamespace(topLevelItemCount=lambda: 1, topLevelItem=lambda i: app)
        self.assertIs(window._find_item(tree, "Sketch", "DocB"), b)
        self.assertIs(window._find_item(tree, "Sketch"), a)
        self.assertIsNone(window._find_item(tree, "Ghost", "DocA"))


class Plain(unittest.TestCase):
    def test_markdown_off_in_the_callout(self):
        self.assertEqual(point.plain("Switch to the **Part Design** workbench."), "Switch to the Part Design workbench.")
        self.assertEqual(point.plain("Press __Pad__, then `OK`; 2 * 3 stays."), "Press Pad, then OK; 2 * 3 stays.")
        self.assertEqual(point.callout("Press **Pad**.", []), "Press Pad.")


class TabWords(unittest.TestCase):
    def test_rows(self):
        self.assertEqual(tab.lesson_rows([{"id": "a.b", "title": "Pad", "minutes": 4, "done": True}, {"id": "a.c", "title": "Hole"}]),
                         [("a.b", "✓ Pad · 4 min"), ("a.c", "Hole")])

    def test_step_words(self):
        self.assertEqual(tab.step_words(None)[0], "No lesson running.")
        self.assertEqual(tab.step_words({"lesson": "x", "step": "done", "skipped": ["pick"]})[1], "Well done. Skipped: pick.")
        h, s, hint = tab.step_words({"lesson": "x", "step": "2/5", "say": "Press Pad.", "check": "fail", "why": "no Pad yet", "hint": 0})
        self.assertEqual((h, s, hint), ("Step 2/5 · not yet", "Press Pad.", "no Pad yet"))
        self.assertEqual(tab.step_words({"lesson": "x", "step": "2/5", "say": "s", "check": "pending", "hint": 1, "hint_text": "Look up."})[2], "Look up.")

    def test_buttons(self):
        self.assertEqual(tab.buttons_on(None)["start"], True)
        self.assertFalse(tab.buttons_on(None)["next"])
        e = types.SimpleNamespace(state="step", history=[])
        on = tab.buttons_on(e)
        self.assertTrue(on["next"] and on["hint"] and on["skip"] and on["stop"])
        self.assertFalse(on["back"] or on["start"] or on["do"])  # no step with a do in front
        self.assertTrue(tab.buttons_on(types.SimpleNamespace(state="step", history=[0]))["back"])
        self.assertTrue(tab.buttons_on(types.SimpleNamespace(state="step", history=[], step={"do": [{"tool": "pd_pad"}]}))["do"])
        self.assertFalse(tab.buttons_on(types.SimpleNamespace(state="step", history=[], step={"say": "Look."}))["do"])

    def test_check_line(self):
        self.assertEqual(tab.check_line(None), "")
        self.assertEqual(tab.check_line({"lesson": "x", "step": "2/5", "check": "pass"}), "Check: passed")
        self.assertEqual(tab.check_line({"lesson": "x", "step": "2/5", "check": "fail", "why": "Length is 20 mm"}), "Check: not yet (Length is 20 mm)")
        self.assertEqual(tab.step_words({"lesson": "x", "step": "1/5", "say": "s", "check": "pending", "why": "needs the FreeCAD window"})[0], "Step 1/5 · waiting")

    def test_question_note(self):
        self.assertEqual(tab.question_note("  why   Pad? ", {"lesson": "agentlink_tutor.pd.pad-sketch", "step": "3/5"}),
                         "Tutor question (lesson agentlink_tutor.pd.pad-sketch, step 3/5): why Pad?")
        self.assertEqual(tab.question_note("what now", None), "Tutor question: what now")
        self.assertIsNone(tab.question_note("   "))

    def test_call_for_turns_ok_into_refused(self):
        panel = types.SimpleNamespace(_call=lambda t, a: (False, {"error": {"message": "no"}}))
        self.assertEqual(tab.call_for(panel)("pd_pad", {}), (True, {"error": {"message": "no"}}))

    def test_tab_paints_no_colours(self):
        with open(os.path.join(ROOT, "agentlink_tutor", "tab.py"), encoding="utf-8") as f:
            src = f.read()
        for bad in ("setStyleSheet", "palette()", "QPalette", "setAutoFillBackground", "#"):
            if bad == "#":
                self.assertIsNone(re.search(r"['\"]#[0-9a-fA-F]{3,6}['\"]", src))
            else:
                self.assertNotIn(bad, src)


@unittest.skipUnless(AL, "needs an Agent Link checkout ($AGENTLINK_SRC or ../agentlink-freecad)")
class WithAgentLink(unittest.TestCase):
    def setUp(self):
        from agentlink import echo, hooks

        self.hooks, self.echo = hooks, echo
        self.saved = hooks.saved()
        self.no_echo = set(getattr(echo, "NO_ECHO", ()))

    def tearDown(self):
        self.hooks.restore(self.saved)
        if hasattr(self.echo, "NO_ECHO"):
            self.echo.NO_ECHO.clear()
            self.echo.NO_ECHO.update(self.no_echo)

    def test_tools_json_is_agent_links_format_and_short(self):
        from agentlink import tooldata

        doc = json.load(open(os.path.join(ROOT, "agentlink_tutor", "data", "tools.json"), encoding="utf-8"))
        self.assertEqual(tooldata.check(doc), [])
        self.assertEqual(set(doc["entries"]), {"tutor_point", "tutor", "tutor_watch"})
        # The design's budget: about 1,800 characters for the three tutor tools.
        self.assertLessEqual(sum(len(e["description"]) for e in doc["entries"].values()), 1800)
        t = doc["entries"]["tutor"]
        self.assertEqual((t["group"], t["changes"]), ("tutor", False))
        self.assertLessEqual(len(t["description"]), 700)
        d = doc["entries"]["tutor_point"]
        self.assertEqual(d["group"], "tutor")
        self.assertLessEqual(len(d["description"]), 600)
        self.assertFalse(d["changes"])

    def test_family_declares_no_echo_and_is_not_lean(self):
        import importlib

        from agentlink_tutor import fam_tutor

        self.assertFalse(getattr(fam_tutor, "LEAN", False))
        self.assertEqual(fam_tutor.GROUP, "tutor")
        self.echo.declare(fam_tutor)
        self.assertTrue(self.echo.skipped("tutor_point"))
        self.assertTrue(self.echo.skipped("tutor"))
        self.assertIsNone(self.echo.command_for("tutor_point", {}))
        fams = importlib.import_module("agentlink_tutor.agentlink_families")
        importlib.reload(fams)
        tabs = [t for t in self.hooks.TABS if t["title"] == "Tutor"]
        self.assertEqual([t["order"] for t in tabs][-1], 15)
        self.assertTrue(self.hooks.api_ok(fams.AGENTLINK_API))

    def test_tool_built_from_data(self):
        from agentlink_tutor import fam_tutor

        tools = fam_tutor.tools(types.SimpleNamespace(doc=None))
        self.assertEqual([t.name for t in tools], ["tutor_point", "tutor", "tutor_watch"])
        self.assertEqual(tools[0].group, "tutor")


if __name__ == "__main__":
    unittest.main()
