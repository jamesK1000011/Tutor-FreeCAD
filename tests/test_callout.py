# SPDX-License-Identifier: LGPL-2.1-or-later
# The callout as the person sees it, without FreeCAD (findings of the guided
# live run on FreeCAD 1.1.3, fixed for every lesson):
#  1. no "Not yet" until the person acts or asks for a hint;
#  2. no internal names (type ids, command names) in anything the person reads;
#  3. the instruction, the why line and a target's words laid out apart, numbered
#     only when there is more than one line;
#  4. a command named by its live menu text (FreeCAD's getInfo), so step and
#     window agree in every release;
#  5. the bubble over the 3D view, clear of the toolbars and docks, its arrow
#     to the ring.
import json
import os
import unittest

from fakes import Doc
from test_engine import World
from test_run import AGENT, PERSON, Clock

from agentlink_tutor import callout, checks, engine, lessons, point, run, tab, targets, words
from agentlink_tutor.checks import GuiState
from agentlink_tutor.engine import Engine


def load(name):
    with open(os.path.join(lessons.CORE_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def pocket(timer=None, show=None):
    w = World()
    w.gui = GuiState("PartDesignWorkbench")
    e = Engine(load("pocket-hole.lesson.json"), call=w, doc=lambda: w.doc, gui=lambda: w.gui)
    c = run.Controller(e, timer=timer, show=show)
    c.start("guided")
    return w, c


class FakeGuiCommands:
    """FreeCADGui.Command as words.py asks it: getInfo()['menuText']."""

    def __init__(self, texts):
        self.texts = texts
        self.Command = self

    def get(self, name):
        if name not in self.texts:
            raise KeyError(name)
        text = self.texts[name]
        return type("C", (), {"getInfo": lambda _self: {"menuText": text}})()


class LiveNames:
    """words.GUI points at a stand-in FreeCADGui for the test's length."""

    def __init__(self, texts):
        self.g = FakeGuiCommands(texts) if texts is not None else None

    def __enter__(self):
        self.old = words.GUI["get"]
        words.GUI["get"] = lambda: self.g
        return self

    def __exit__(self, *a):
        words.GUI["get"] = self.old


class VerdictWaits(unittest.TestCase):
    """1: at a step's start only the instruction and its why line."""

    def test_nothing_done_no_not_yet(self):
        w, c = pocket()
        self.assertEqual(c.e.step["id"], "top")
        # The agent looks around (a read-only call): the step is re-checked
        # and fails, but the person has done nothing yet.
        c.call_done(AGENT, "view_snapshot", True, False)
        self.assertEqual(c.e.result.status, "fail")
        self.assertNotIn("Not yet", c.callout())
        st = c.person_state()
        self.assertEqual(st["check"], "pending")
        self.assertNotIn("why", st)
        self.assertEqual(tab.check_line(st), "Check: waiting")
        self.assertEqual(tab.step_words(st)[2], "")
        self.assertEqual(c.state()["check"], "fail")  # the agent still hears the truth

    def test_a_window_signal_before_the_step_is_not_an_act(self):
        clock = Clock()
        w, c = pocket(timer=clock)
        c.poke({"n": c.step_seq, "k": "clr"})  # setup's own selection clear
        clock.flush()
        self.assertNotIn("Not yet", c.callout())

    def test_after_the_person_acts_it_says_why(self):
        clock = Clock()
        w, c = pocket(timer=clock)
        c.poke({"n": c.step_seq + 1, "k": "sel", "o": "Body"})
        clock.flush()
        self.assertIn("Not yet: no new sketch yet.", c.callout())
        self.assertEqual(c.person_state()["check"], "fail")

    def test_a_person_call_or_a_changing_agent_call_counts(self):
        for who, changed in ((PERSON, False), (AGENT, True)):
            with self.subTest(by=who.by, changed=changed):
                w, c = pocket()
                c.call_done(who, "selection", True, changed)
                self.assertIn("Not yet", c.callout())

    def test_a_hint_shows_at_once(self):
        w, c = pocket()
        c.act("hint")
        self.assertIn("Click the flat face on top.", c.callout())

    def test_the_next_step_starts_quiet_again(self):
        w, c = pocket()
        c.call_done(PERSON, "selection", True, False)
        self.assertTrue(c.acted)
        c.act("skip")
        self.assertFalse(c.acted)
        c.call_done(AGENT, "view_snapshot", True, False)
        self.assertNotIn("Not yet", c.callout())


class NoInternalNames(unittest.TestCase):
    """2: everything the engine can say to the person, scanned for type ids
    and command names."""

    def assertPlain(self, text, where):
        self.assertEqual(words.internal_names(text), [], f"{where}: {text!r}")

    def test_type_and_command_words(self):
        self.assertEqual(words.type_words("Sketcher::SketchObject"), "sketch")
        self.assertEqual(words.type_words("PartDesign::Pad"), "pad")
        self.assertEqual(words.type_words("PartDesign::AdditiveBox"), "additive box")
        self.assertEqual(words.type_words("Part::FeaturePython"), "feature")
        self.assertEqual(words.prop_words("UseCustomVector"), "Use custom vector")
        self.assertEqual(words.prop_words("Length"), "Length")
        with LiveNames(None):
            self.assertEqual(words.command_words("PartDesign_NewSketch"), "New Sketch")
            self.assertEqual(words.command_words("Sketcher_CreateRectangle"), "Create Rectangle")
        self.assertEqual(words.internal_names("no new SketchObject yet"), ["SketchObject"])
        self.assertEqual(words.internal_names("the PartDesign::Pad and Sketcher_NewSketch"), ["PartDesign::Pad", "Sketcher_NewSketch"])
        self.assertEqual(words.internal_names("FreeCAD makes a Pad from the Sketch."), [])

    def test_every_check_failure_in_plain_words(self):
        w = World()
        w.gui = GuiState("StartWorkbench", editing="Sketch", task="PartDesign_Pad")
        w.doc.add("Body", "PartDesign::Body")
        w.doc.add("Sketch", "Sketcher::SketchObject")
        ctx = checks.Context(doc=w.doc, gui=w.gui, events=[], before={"Body", "Sketch"})
        cases = [
            {"exists": {"type": "Sketcher::SketchObject", "label": "Top"}}, {"exists": "PartDesign::Pocket"},
            {"exists": {"type": "PartDesign::Hole", "in": "Body"}}, {"new": "Sketcher::SketchObject"},
            {"new": "PartDesign::AdditiveBox"}, {"absent": "Sketcher::SketchObject"},
            {"prop": "Body", "name": "UseCustomVector", "eq": 1}, {"workbench": "PartDesignWorkbench"},
            {"editing": None}, {"editing": "Body"}, {"task_open": None}, {"task_open": "PartDesign_Pocket"},
            {"used": "PartDesign_NewSketch"}, {"selected": "Sketch"},
            {"any": [{"new": "PartDesign::Pad"}, {"used": "PartDesign_Pad"}]},
        ]
        with LiveNames(None):
            for chk in cases:
                r = checks.evaluate(chk, ctx)
                self.assertEqual(r.status, "fail", chk)
                self.assertPlain(r.why, json.dumps(chk))
                ex = checks.exact(chk, w.doc)
                if ex:
                    self.assertPlain(ex, f"exact {json.dumps(chk)}")

    def test_every_lesson_step_rung_and_callout(self):
        lib = lessons.core_library()
        with LiveNames(None):
            for lid in sorted(lib.lessons()):
                lesson = lib.get(lid)
                w = World()
                w.gui = GuiState("StartWorkbench")
                ok = lambda _t, _a: (False, {})  # noqa: E731  setup's calls answered, nothing made
                e = Engine(lesson, call=ok, doc=lambda w=w: w.doc, gui=lambda w=w: w.gui, events=lambda: [])
                c = run.Controller(e)
                c.start("guided")
                seen = 0
                while c.stepping and seen < 30:
                    seen += 1
                    c.call_done(PERSON, "selection", True, True)  # acted: the verdict shows
                    for rung in range(engine.HINT_MAX + 1):
                        where = f"{lid} {c.e.step['id']} rung {rung}"
                        self.assertPlain(c.callout(), where)
                        st = c.person_state()
                        for text in tab.step_words(st) + (tab.check_line(st), tab.why_line(st)):
                            self.assertPlain(text, where)
                        for key in ("say", "because", "why", "hint_text"):
                            self.assertPlain(st.get(key), f"{where} {key}")
                        c.act("hint")
                    c.act("skip")
                self.assertGreater(seen, 2, lid)

    def test_lessons_naming_internal_names_are_refused(self):
        bad = {"schema": 1, "id": "inline.bad", "version": "1.0.0", "title": "Bad",
               "steps": [{"id": "a", "say": "Push PartDesign_Pad.", "check": {"new": "PartDesign::Pad"}}]}
        with self.assertRaises(lessons.LessonError) as x:
            lessons.inline(bad)
        self.assertIn("PartDesign_Pad is FreeCAD's internal name", str(x.exception))
        bad["steps"][0]["say"] = "Push {PartDesign_Pad}."
        with self.assertRaises(lessons.LessonError) as x:
            lessons.inline(bad)
        self.assertIn("a command goes in bold", str(x.exception))
        bad["steps"][0]["say"] = "Push **{PartDesign_Pad|Pad}**."
        self.assertEqual(lessons.inline(bad)["id"], "inline.bad")


class Layout(unittest.TestCase):
    """3: the pocket lesson's first step as the live run showed it."""

    def dropdown(self, n=2):
        f = targets.Found(n, "cmd")
        f.marks = [{"widget": "group-button"}]
        f.text = f"Open the ▾ menu of the ringed button {words.badge(n)}. Select New Sketch."
        return f

    def test_instruction_why_and_dropdown_apart(self):
        with LiveNames({"PartDesign_NewSketch": "&New Sketch…"}):
            w, c = pocket()
            c.call_done(AGENT, "view_snapshot", True, False)  # re-checked, nothing done
            got = point.callout(c.parts(), [targets.Found(1, "face"), self.dropdown()])
        self.assertEqual(got, "1. Select the top face of the block.\n"
                              "2. Push New Sketch.\n"
                              "3. Open the ▾ menu of the ringed button ②. Select New Sketch.\n"
                              "\n"
                              "A sketch on this face sets where the pocket starts.")

    def test_one_line_has_no_number(self):
        c = callout.build("Push **Pad**.", why="Pad makes a solid.")
        self.assertEqual(c.text(), "Push Pad.\n\nPad makes a solid.")
        self.assertEqual(callout.build(None).add_steps(["Menu: Edit › Undo"]).text(), "Menu: Edit › Undo")

    def test_a_description_stays_one_paragraph(self):
        c = callout.build("Done: a 4 mm pocket. The top face shows in colour.")
        self.assertEqual(c.text(), "Done: a 4 mm pocket. The top face shows in colour.")

    def test_rich_text_why_smaller_and_dimmer(self):
        c = callout.build("Select the face. Push **Pad**.", why="Pad <makes> a solid.", notes=["Not yet: no pad yet."])
        h = c.html("#111111", "#777777")
        self.assertIn("<td>Select the face.</td>", h)
        self.assertIn('font-size:small; color:#777777">Pad &lt;makes&gt; a solid.</p>', h)
        self.assertLess(h.index("Push Pad."), h.index("Pad &lt;makes&gt;"))
        self.assertLess(h.index("Pad &lt;makes&gt;"), h.index("Not yet"))


class LiveMenuText(unittest.TestCase):
    """4: the step names the command as this FreeCAD's menu does."""

    def test_step_uses_the_live_menu_text(self):
        for live, want in (({"PartDesign_NewSketch": "&New Sketch…"}, "New Sketch"),
                           ({"PartDesign_NewSketch": "Create sketch..."}, "Create sketch"),
                           (None, "New Sketch")):  # headless: the lesson's fallback
            with self.subTest(live=live), LiveNames(live):
                w, c = pocket()
                self.assertEqual(c.state()["say"], f"Select the top face of the block. Push **{want}**.")
                self.assertIn(f"Push {want}.", c.callout())

    def test_hints_and_why_too(self):
        with LiveNames({"PartDesign_Pad": "Pad", "Std_Undo": "&Undo"}):
            self.assertEqual(words.ui_text("Push **{Std_Undo|Undo}** (⌘Z)."), "Push **Undo** (⌘Z).")
            self.assertEqual(words.ui_text("**{PartDesign_Pad}** makes a solid."), "**Pad** makes a solid.")
        with LiveNames(None):
            self.assertEqual(words.ui_text("**{PartDesign_Pocket}**"), "**Pocket**")

    def test_menu_text_cleaned(self):
        self.assertEqual(words.clean_menu_text("&Export..."), "Export")
        self.assertEqual(words.clean_menu_text("Save &As…"), "Save As")
        self.assertEqual(words.clean_menu_text("Fit && Finish"), "Fit & Finish")


class Placement(unittest.TestCase):
    """5: over the 3D view, under the toolbars, arrow to the ring."""

    VIEW = (300, 120, 1000, 700)  # the 3D view in the main window's px
    TOOLBAR_BUTTON = (520, 60, 32, 32)  # a ringed button in the toolbars above
    TOOLBARS = (0, 30, 1300, 90)
    DOCK = (0, 120, 300, 700)

    def inside_view(self, x, y, w, h):
        vx, vy, vw, vh = self.VIEW
        return vx <= x and vy <= y and x + w <= vx + vw and y + h <= vy + vh

    def test_toolbar_target_bubble_below_the_toolbars(self):
        x, y, side, tip = callout.place(self.VIEW, (300, 90), self.TOOLBAR_BUTTON)
        self.assertTrue(self.inside_view(x, y, 300, 90))
        self.assertEqual(side, "up")
        self.assertEqual(callout._overlap((x, y, 300, 90), self.TOOLBARS), 0)
        self.assertEqual(callout._overlap((x, y, 300, 90), self.DOCK), 0)
        self.assertEqual(tip, (536, y - callout.ARROW))  # under the ring's middle
        self.assertLessEqual(y - self.VIEW[1], callout.MARGIN + callout.ARROW)

    def test_dock_target_arrow_left(self):
        field = (40, 400, 200, 24)  # a Tasks panel field in the left dock
        x, y, side, tip = callout.place(self.VIEW, (300, 90), field)
        self.assertTrue(self.inside_view(x, y, 300, 90))
        self.assertEqual(side, "left")
        self.assertEqual(callout._overlap((x, y, 300, 90), self.DOCK), 0)
        self.assertEqual(tip[1], 412)

    def test_kept_off_the_navigation_cube(self):
        right_button = (1250, 60, 32, 32)
        x, y, side, _tip = callout.place(self.VIEW, (300, 90), right_button)
        vx, vy, vw, _vh = self.VIEW
        cube = (vx + vw - callout.CUBE[0], vy, callout.CUBE[0], callout.CUBE[1])
        self.assertEqual(callout._overlap((x, y, 300, 90), cube), 0)
        self.assertEqual(side, "up")

    def test_no_target_top_centre_and_face_in_view(self):
        x, y, side, tip = callout.place(self.VIEW, (300, 90), None)
        self.assertEqual((side, tip), (None, None))
        self.assertEqual(x, 300 + (1000 - 300) // 2)
        face = (900, 500, 80, 80)
        x, y, side, tip = callout.place(self.VIEW, (300, 90), face)
        self.assertEqual(side, None)
        self.assertEqual(callout._overlap((x, y, 300, 90), face), 0)

    def test_point_lets_the_bubble_take_the_words(self):
        class Bubble:
            def __init__(self):
                self.shown, self.hidden = [], 0

            def show(self, c, found, doc=None, report=None):
                self.shown.append(c.text())
                return True

            def hide(self):
                self.hidden += 1

            def why(self):
                return None

        from test_point import Ann, Hooks, Overlay, Win

        ov, b = Overlay(), Bubble()
        win = Win()
        hooks = Hooks(ov, Ann())
        out = point.point({"targets": [{"view": "3d"}], "say": "Look here."}, win, hooks=hooks, bubble=b)
        self.assertEqual(b.shown, ["Look here."])
        self.assertIsNone(ov.shows[-1]["say"])  # the overlay draws only the rings
        self.assertEqual(out["callout"], "bubble")
        point.point({}, win, hooks=hooks, bubble=b)
        self.assertEqual(b.hidden, 2)

    def test_a_bubble_that_cannot_show_says_why_and_the_overlay_has_the_words(self):
        class NoView:
            def show(self, c, found, doc=None, report=None):
                return False

            def hide(self):
                pass

            def why(self):
                return "PocketLesson's 3D view is not the front tab"

        from test_point import Ann, Hooks, Overlay, Win

        ov = Overlay()
        report = {}
        out = point.point({"targets": [{"view": "3d"}], "say": "Look here."}, Win(), hooks=Hooks(ov, Ann()), bubble=NoView(), report=report)
        self.assertEqual(ov.shows[-1]["say"], "Look here.")
        self.assertEqual((out["callout"], out["callout_why"]), ("overlay", "PocketLesson's 3D view is not the front tab"))
        self.assertEqual(report["callout"], "overlay")  # the dict the later self-check updates
        out = point.point({"targets": [{"view": "3d"}]}, Win(), hooks=Hooks(None, Ann()), bubble=NoView())
        self.assertEqual(out["callout"], "none")

    def test_the_controller_tells_the_agent_where_the_words_are(self):
        report = {"resolved": 2, "missing": [], "callout": "overlay", "callout_why": "bubble not visible"}
        w, c = pocket(show=lambda ctl: report)
        st = c.state()
        self.assertEqual((st["callout"], st["callout_why"]), ("overlay", "bubble not visible"))
        report.update(callout="bubble")
        report.pop("callout_why")
        self.assertNotIn("callout_why", c.state())

    def test_bubble_pieces_without_qt(self):
        from agentlink_tutor import bubble

        self.assertTrue(bubble.subwindow_title_matches("PocketLesson : 1[*]", "PocketLesson"))
        self.assertFalse(bubble.subwindow_title_matches("PocketLesson2 : 1", "PocketLesson"))
        self.assertFalse(bubble.subwindow_title_matches("WindowTest (recovered 00:17) : 1", "PocketLesson"))
        self.assertTrue(bubble.inside((10, 19, 340, 90), (0, 0, 1000, 700)))
        self.assertFalse(bubble.inside((10, 19, 0, 90), (0, 0, 1000, 700)))  # no size
        self.assertFalse(bubble.inside((900, 19, 340, 90), (0, 0, 1000, 700)))  # off the view's edge
        col = bubble.colours({"bubble": "#ffffff", "bubble_text": "#000000", "accent": "#0072b2"})
        # No font family named anywhere (Qt warned of a missing "Sans" on the Mac).
        for text in (bubble.stylesheet(col), bubble.arrow_sheet(col), callout.build("Push **Pad**. Set it.", why="Why.").html()):
            self.assertNotIn("font-family", text)
            self.assertNotIn("Sans", text)


class Docs(World):
    """Several open documents, as the window had them: the session's
    document (where the tools act) and the window's front tab, each by name.
    follow_front: the panel's own server, whose session follows the front."""

    def __init__(self, front="WindowTest", follow_front=False):
        self.docs = {}
        self.session = self.front = None
        self.follow_front = follow_front
        super().__init__()
        self.docs.clear()
        for name in ("WindowTest", "Other"):
            d = Doc()
            d.Name = d.Label = name
            self.docs[name] = d
        self.session = self.front = front

    @property
    def doc(self):
        return self.docs.get(self.front if self.follow_front else self.session)

    @doc.setter
    def doc(self, d):
        pass  # World's own doc_new: handled below

    def __call__(self, name, args):
        if name == "doc_new":
            self.calls.append((name, args))
            d = Doc()
            d.Name = d.Label = args.get("name") or "Unnamed"
            self.docs[d.Name] = d
            self.session = d.Name  # the session switches; the front tab stays (a recovered document)
            return False, {"document": d.Name}
        if name == "doc_switch":
            self.calls.append((name, args))
            self.session = args["document"]
            if args.get("front"):
                self.front = args["document"]
            return False, {"document": args["document"]}
        return super().__call__(name, args)


class LessonDocument(unittest.TestCase):
    """The lesson's setup, checks, targets and view on its own document,
    with another document in front at start."""

    def run_pocket(self, w):
        w.gui = GuiState("PartDesignWorkbench")
        e = Engine(load("pocket-hole.lesson.json"), call=w, doc=lambda: w.doc, gui=lambda: w.gui,
                   find_doc=lambda n: w.docs.get(n), front=lambda: w.front)
        c = run.Controller(e)
        c.start("guided")
        return e, c

    def test_setup_on_the_lessons_document_with_its_view_in_front(self):
        for follow in (False, True):
            with self.subTest(follow_front=follow):
                w = Docs(follow_front=follow)
                e, c = self.run_pocket(w)
                self.assertEqual(e.doc_name, "PocketLesson")
                self.assertEqual(w.front, "PocketLesson")
                names = [n for n, _a in w.calls]
                self.assertEqual(names[:2], ["doc_new", "doc_switch"])
                self.assertEqual(w.calls[1][1], {"document": "PocketLesson", "front": True})
                self.assertEqual(w.docs["WindowTest"].Objects, [])  # nothing made in the document that was in front
                self.assertEqual({o.TypeId for o in w.docs["PocketLesson"].Objects},
                                 {"PartDesign::Body", "Sketcher::SketchObject", "PartDesign::Pad"})
                self.assertIs(e._doc(), w.docs["PocketLesson"])
                self.assertEqual(e.bindings["body"], "Body")

    def test_checks_read_the_lessons_document_when_another_comes_to_the_front(self):
        w = Docs()
        e, c = self.run_pocket(w)
        w.front = w.session = "WindowTest"  # the person brings their own document to the front
        w.docs["WindowTest"].add("Sketch", "Sketcher::SketchObject")
        e.check()
        self.assertEqual(e.result.status, "fail")  # a sketch in WindowTest is not the lesson's
        self.assertIs(e._doc(), w.docs["PocketLesson"])

    def test_do_brings_the_lesson_back_first(self):
        w = Docs()
        e, c = self.run_pocket(w)
        while e.step["id"] != "pocket":
            c.act("skip")
        w.front = w.session = "WindowTest"
        n = len(w.calls)
        e.step["do"] = [{"tool": "selection", "args": {"objects": ["Body"]}}]
        try:
            e.do()
        except engine.TutorError:
            pass
        self.assertEqual(w.calls[n], ("doc_switch", {"document": "PocketLesson", "front": True}))
        self.assertEqual(w.front, "PocketLesson")

    def test_one_document_no_switch(self):
        w = Docs(front="PocketLesson")
        w.docs["PocketLesson"] = w.docs.pop("Other")
        w.docs["PocketLesson"].Name = w.docs["PocketLesson"].Label = "PocketLesson"
        lesson = load("pocket-hole.lesson.json")
        lesson["setup"] = {"calls": [c for c in lesson["setup"]["calls"] if c["tool"] != "doc_new"], "bind": lesson["setup"]["bind"]}
        w.gui = GuiState("PartDesignWorkbench")
        e = Engine(lesson, call=w, doc=lambda: w.doc, gui=lambda: w.gui, find_doc=lambda n: w.docs.get(n), front=lambda: w.front)
        e.start("guided")
        self.assertEqual(e.doc_name, "PocketLesson")
        self.assertNotIn("doc_switch", [n for n, _a in w.calls])


if __name__ == "__main__":
    unittest.main()
