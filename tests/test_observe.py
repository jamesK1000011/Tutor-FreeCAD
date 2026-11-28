# SPDX-License-Identifier: LGPL-2.1-or-later
# T4: the person's events (observe.py), watch mode and tutor_watch, the long
# poll answered off the GUI thread, and guided `used` checks on command
# events. Ends with a soak: many events and waiters, no slowdown, bounded.
import json
import os
import sys
import threading
import time
import unittest

from test_engine import World, pad_lesson
from test_run import Clock

from agentlink_tutor import live, observe, run, tool
from agentlink_tutor.checks import GuiState
from agentlink_tutor.engine import Engine
from agentlink_tutor.point import Refusal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_agentlink_tools  # noqa: E402

AL = gen_agentlink_tools.source()
if AL and os.path.dirname(AL) not in sys.path:
    sys.path.append(os.path.dirname(AL))
try:
    from agentlink import hooks

    HAVE = hasattr(hooks, "register_thread_tool")
except ImportError:
    HAVE = False


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def fresh():
    observe.BUF = observe.Buffer()
    observe._NEED.clear()
    observe._ATTACHED.update(on=False, doc=None, gui=None, sel=None)
    live.WATCH["on"] = False


class Buffer(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.b = observe.Buffer(size=5, clock=self.clock)

    def test_numbered_milestones_and_ring(self):
        self.b.push("cmd", c="PartDesign_Pad")
        self.clock.t += 1
        self.b.push("new", o="Pad", ty="PartDesign::Pad")
        evs = self.b.since(0)
        self.assertEqual(evs, [{"n": 1, "k": "cmd", "c": "PartDesign_Pad"}, {"n": 2, "k": "new", "o": "Pad", "ty": "PartDesign::Pad", "m": 1}])
        for i in range(10):
            self.clock.t += 1
            self.b.push("cmd", c=f"C{i}")
        self.assertEqual(len(self.b.events), 5)
        self.assertEqual(self.b.first(), 8)
        self.assertEqual([e["n"] for e in self.b.since(10)], [11, 12])

    def test_bursts_coalesce(self):
        for o in ("Sketch", "Pad", "Body"):
            self.b.push("sel", o=o)
            self.clock.t += 0.1
        self.assertEqual([(e["k"], e["o"]) for e in self.b.since(0)], [("sel", "Body")])
        self.clock.t += 1
        self.b.push("sel", o="Pad")
        self.assertEqual(len(self.b.events), 2)
        self.b.push("rc", d="A")
        self.b.push("rc", d="A")
        self.b.push("rc", d="B")  # another document: kept apart
        self.assertEqual([(e["k"], e.get("d")) for e in self.b.since(0)][-2:], [("rc", "A"), ("rc", "B")])

    def test_wait(self):
        t0 = time.monotonic()
        self.assertEqual(self.b.wait(0, 0.2), [])
        self.assertGreaterEqual(time.monotonic() - t0, 0.15)
        self.b.push("cmd", c="X")
        t0 = time.monotonic()
        self.assertEqual(len(self.b.wait(0, 5)), 1)  # there already: at once
        self.assertLess(time.monotonic() - t0, 0.1)

    def test_wait_wakes_on_a_push_from_another_thread(self):
        b = observe.Buffer()
        threading.Timer(0.1, lambda: b.push("sel", o="Pad")).start()
        threading.Timer(0.2, lambda: b.push("new", o="Pad")).start()
        t0 = time.monotonic()
        got = b.wait(0, 5, "milestone")  # a selection is no milestone: it waits on
        dt = time.monotonic() - t0
        self.assertTrue(0.15 < dt < 2, dt)
        self.assertEqual([e["k"] for e in got], ["sel", "new"])
        t0 = time.monotonic()
        threading.Timer(0.1, lambda: b.push("cmd", c="Y")).start()
        self.assertEqual(b.wait(2, 5, "any")[-1]["c"], "Y")
        self.assertLess(time.monotonic() - t0, 2)

    def test_wait_is_capped(self):
        was = observe.WAIT_MAX
        observe.WAIT_MAX = 0.2
        try:
            t0 = time.monotonic()
            observe.Buffer().wait(0, 999)
            self.assertLess(time.monotonic() - t0, 1.0)
        finally:
            observe.WAIT_MAX = was


class Owners(unittest.TestCase):
    def setUp(self):
        fresh()

    def tearDown(self):
        fresh()

    def test_no_window_nothing_attached_listeners_still_told(self):
        got = []
        self.assertFalse(observe.need("a", got.append))
        observe.record("cmd", c="X")
        self.assertEqual(got[-1]["c"], "X")
        observe.release("a")
        self.assertEqual(observe.owners(), set())

    @unittest.skipUnless(HAVE, "needs Agent Link's T4 hooks")
    def test_the_agents_own_events_left_out(self):
        with hooks.acting():
            self.assertIsNone(observe.record("cmd", c="PartDesign_Pad"))
        observe.record("cmd", c="PartDesign_Pocket")
        self.assertEqual([e["c"] for e in observe.BUF.since(0)], ["PartDesign_Pocket"])
        observe._cmd("A", "agent")
        observe._cmd("B", "person")
        observe._wb("PartDesignWorkbench", "person")
        self.assertEqual([e.get("c") or e.get("w") for e in observe.BUF.since(0)][-2:], ["B", "PartDesignWorkbench"])


class UsedChecks(unittest.TestCase):
    """A guided step checked on the command the person used (any lesson)."""

    LESSON = {"schema": 1, "id": "inline.used", "version": "0.0.0", "title": "Use a command",
              "steps": [{"id": "a", "say": "Push **Pad**.", "check": {"used": "PartDesign_Pad"}},
                        {"id": "b", "say": "Push **Pocket**.", "check": {"used": "PartDesign_Pocket"}}]}

    def setUp(self):
        fresh()

    def tearDown(self):
        fresh()

    def test_used_from_command_events(self):
        w = World()
        e = Engine(json.loads(json.dumps(self.LESSON)), call=w, doc=lambda: w.doc, gui=lambda: GuiState())
        c = run.Controller(e)
        e._events = c.step_events
        c.start("guided")
        self.assertEqual(c.act("status")["check"], "pending")
        self.assertEqual(c.e.check()["why"], "the person's actions are not being watched")
        observe._ATTACHED["on"] = True  # the window's observers (GUI only)
        observe.need(("lesson", id(c)), lambda ev: c.recheck(by="person"))
        observe.record("cmd", c="PartDesign_Pocket")  # not this step's
        self.assertEqual(c.e.step["id"], "a")
        observe.record("cmd", c="PartDesign_Pad")
        self.assertEqual(c.e.step["id"], "b")  # passed, on (no timer: at once)
        self.assertEqual(c.state()["check"], "pending")  # Pocket used before b began does not count
        c.recheck()
        self.assertEqual(c.e.check()["check"], "fail")
        observe.record("cmd", c="PartDesign_Pocket")
        self.assertEqual(c.e.state, "done")


class Watch(unittest.TestCase):
    def setUp(self):
        fresh()

    def tearDown(self):
        fresh()

    def test_off_says_so(self):
        out = tool.watch({"wait": 0})
        self.assertFalse(out["watching"])
        self.assertNotIn("say", out)

    def test_on_events_next_and_more(self):
        live.watch_mode(True)
        self.assertIn("watch", observe.owners())
        for i in range(45):
            observe.BUF.push("cmd", c=f"C{i}")
        out = tool.watch({})
        self.assertEqual(len(out["events"]), observe.ANSWER_MAX)
        self.assertEqual((out["next"], out["more"]), (45, 5))
        self.assertEqual(tool.watch({"since": 45})["events"], [])
        self.assertLess(len(json.dumps(tool.watch({}))), 1800)
        live.watch_mode(False)
        self.assertEqual(observe.BUF.since(0), [])  # cleared when off
        self.assertNotIn("watch", observe.owners())

    def test_missed_when_older_left_the_ring(self):
        live.watch_mode(True)
        observe.BUF = observe.Buffer(size=3)
        for i in range(10):
            observe.BUF.push("cmd", c=str(i))
        self.assertTrue(tool.watch({"since": 2})["missed"])

    def test_refusals(self):
        live.watch_mode(True)
        for a in ({"wait": 26}, {"since": -1}, {"until": "soon"}, {"wait": True}):
            with self.subTest(a=a), self.assertRaises(Refusal):
                tool.watch(a)

    def test_long_poll_until_milestone(self):
        live.watch_mode(True)
        threading.Timer(0.1, lambda: observe.BUF.push("sel", o="Sketch")).start()
        threading.Timer(0.3, lambda: observe.record("ask", q="Why Pad?")).start()
        t0 = time.monotonic()
        out = tool.watch({"wait": 10, "until": "milestone"})
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual(out["events"][-1], {"n": 2, "k": "ask", "q": "Why Pad?", "m": 1})


@unittest.skipUnless(HAVE, "needs Agent Link's T4 hooks")
class OffTheGuiThread(unittest.TestCase):
    def setUp(self):
        fresh()
        self.saved = hooks.saved()
        hooks.reset()

    def tearDown(self):
        hooks.restore(self.saved)
        hooks.THREAD_TOOLS.discard("tutor_watch")
        fresh()

    def test_answered_on_a_thread_while_the_main_thread_works(self):
        import types

        from agentlink.protocol import Server

        from agentlink_tutor import fam_tutor

        tools = fam_tutor.tools(types.SimpleNamespace(doc=None))
        self.assertIn("tutor_watch", hooks.THREAD_TOOLS)
        srv = Server("t", "0", tools, "")
        live.watch_mode(True)
        out = {}

        def poll():
            r = srv.handle_light({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "tutor_watch", "arguments": {"wait": 5, "until": "milestone"}}})
            out["r"] = json.loads(r["result"]["content"][0]["text"])

        th = threading.Thread(target=poll)
        th.start()
        busy_until = time.monotonic() + 0.3
        n = 0
        while time.monotonic() < busy_until:  # the GUI thread keeps working meanwhile
            n += 1
        observe.record("new", o="Pad", ty="PartDesign::Pad")
        th.join(3)
        self.assertFalse(th.is_alive())
        self.assertEqual(out["r"]["events"][-1]["k"], "new")
        self.assertGreater(n, 1000)


class Soak(unittest.TestCase):
    """Many events with waiters polling: memory stays bounded and a push
    takes no longer at the end than at the start (the Mac soak: 30 min)."""

    def test_no_slowdown(self):
        b = observe.Buffer()
        stop = threading.Event()
        polled = [0]

        def poller():
            since = 0
            while not stop.is_set():
                evs = b.wait(since, 0.05, "any")
                if evs:
                    since = evs[-1]["n"]
                polled[0] += 1

        ths = [threading.Thread(target=poller, daemon=True) for _ in range(4)]
        for t in ths:
            t.start()
        kinds = ("cmd", "sel", "rc", "new", "clr")

        def burst(n):
            t0 = time.perf_counter()
            for i in range(n):
                b.push(kinds[i % 5], c="X", o="Pad", d="Doc")
            return (time.perf_counter() - t0) / n

        first = burst(20000)
        for _ in range(8):
            burst(20000)
        last = burst(20000)
        stop.set()
        for t in ths:
            t.join(2)
        self.assertEqual(len(b.events), observe.MAX)
        self.assertEqual(b.seq, 200000)
        self.assertLess(last, first * 3 + 1e-5, (first, last))
        self.assertGreater(polled[0], 4)


if __name__ == "__main__":
    unittest.main()
