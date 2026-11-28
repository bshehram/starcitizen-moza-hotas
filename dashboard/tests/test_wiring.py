"""Stage 3 in the service (PLAN §12 stage 3, "Left to do" item 2; dashboard/STATE.md, "The
message and the endpoints"): the board built from the state, the plan and the user block, sent
beside the stage 2 parts; the four changing routes; the user block across restarts and a
state.json read late; plan.json picked up; the board rebuilt at next_change_ms and not before;
unmapped contracts recorded; nothing half-read sent while catching up; and the two faults in the
service's own log.

Every test has its own data folder, log and port; none touches dashboard/data/ or the real log."""
import json
import logging
import os
import random
import secrets
import socket
import sys
import threading
import time
import unittest
from unittest import mock

import scdash_testlib as lib
import test_service_helpers as h
from scdash import config, server, service
from scdash.service import Service
from test_service import Case, Clock, Mono, Probe, answers, run_in_thread, settings
from test_server import Stream

RUN_A = h.RUN_A.read_bytes()
MINING_CUT = RUN_A[:10756]          # in the Golem's pilot seat: the "ship" rule, context ship:<id>
TRAVEL_CUT = RUN_A[:12989]          # a quantum target chosen at offset 10756: the "travel" rule
PLAN_EXAMPLE = lib.DASHBOARD / "plan.example.json"


class Req:
    """What a route handler gets, for calling one directly."""

    def __init__(self, body):
        self.json = body


def board(svc):
    return json.loads(svc.hub.latest)["board"]


class WiringCase(Case):
    def make(self, running=True, names=lib.NAMES, clock=None, **kw):
        svc = Service(self.inst.data, self.inst.log, settings(**kw), probe=Probe(running), names=names,
                      clock=clock or Clock(time.time()))
        self.services.append(svc)
        return svc

    def started(self, data, running=True, **kw):
        self.inst.write_log(data)
        svc = self.make(running=running, **kw)
        svc.start_reading()
        self.drain(svc)
        return svc

    def saved_user(self):
        return (service.read_json(self.inst.data / "state.json") or {}).get("user")


# ---------------------------------------------------------------------------- the message

class Message(WiringCase):
    def test_the_board_goes_out_beside_the_stage_2_parts(self):
        svc = self.started(RUN_A, running=False)
        msg = json.loads(svc.hub.latest)
        self.assertEqual(sorted(msg), ["board", "clock", "flags", "service", "state"])
        b = msg["board"]
        self.assertEqual(b["schema"], 1)
        self.assertEqual(b["view"]["name"], "idle")
        self.assertEqual(b["view"]["rule"], "no_game")
        self.assertEqual(b["problems"], [])
        self.assertFalse(b["plan"]["loaded"])
        self.assertEqual(b["plan"]["notice"], "there is no plan.json yet")
        self.assertIsInstance(b["next_change_ms"], int)
        self.assertEqual(svc.board_builds, 1)
        self.assertEqual(json.loads(svc.hub.latest)["state"]["alerts"], [], "the state's own slots stay empty")

    def test_the_board_is_not_built_every_turn(self):
        svc = self.started(RUN_A, running=True)
        builds = svc.board_builds
        for _ in range(5):
            svc.tick()
        self.assertEqual(svc.board_builds, builds, "no input changed and no moment reached")
        self.inst.write_log(b"<2026-11-26T23:59:00.000Z> [Notice] nothing an event is made of\n", "ab")
        svc.tick()
        self.assertEqual(svc.board_builds, builds, "bytes read that make no event change nothing")

    def test_a_board_that_raises_does_not_end_the_service(self):
        self.inst.write_log(RUN_A)
        svc = self.make(running=False)
        with mock.patch.object(service.boardlib, "build", side_effect=RuntimeError("broken board")):
            svc.start_reading()
            b = board(svc)
            self.assertEqual(b["problems"], ["service: RuntimeError"])
            self.assertEqual(b["view"]["rule"], "error")
            for _ in range(3):
                svc.tick()
        self.assertGreaterEqual(svc.errors, 1)
        svc._board_next_ms = 0                          # the minute's retry, now
        svc.tick()
        self.assertEqual(board(svc)["problems"], [], "built again once it works")
        log = svc.paths.log.read_text(encoding="utf-8")
        self.assertEqual(log.count("error in building the board"), 1)

    def test_problems_are_logged_once_per_distinct_set(self):
        svc = self.started(RUN_A, running=False)
        calls = {"n": 0}
        real = service.boardlib.build

        def flaky(*a, **kw):
            calls["n"] += 1
            p = real(*a, **kw)
            p["problems"] = ["model: KeyError"] if calls["n"] % 2 else ["strip: ValueError", "model: KeyError"]
            return p
        with mock.patch.object(service.boardlib, "build", side_effect=flaky):
            for _ in range(6):
                svc._board_next_ms = 0
                svc.tick()
        log = svc.paths.log.read_text(encoding="utf-8")
        self.assertEqual(log.count("the board left parts out"), 2, "two distinct sets, each once")


# ---------------------------------------------------------------------------- the changing routes

class Endpoints(WiringCase):
    """Each changing route is behind the CHANGE guard: refused without the token, with a foreign
    Host, with a foreign Origin, with a bad body; accepted otherwise."""

    ROUTES = (("/api/view", {"view": "mining"}), ("/api/view/live", {}),
              ("/api/timers/add", {"label": "Tea", "minutes": 5}),
              ("/api/timers/remove", {"id": "quick:q1"}))
    BAD = {"/api/view": [{"view": "nope"}, {"view": 3}, {}, {"view": "mining", "extra": 1}, {"view": "MINING"},
                         {"view": "live"}],
           "/api/view/live": [{"view": "now"}, {"x": None}],
           "/api/timers/add": [{"label": "Tea"}, {"minutes": 5}, {"label": "", "minutes": 5},
                               {"label": " ", "minutes": 5}, {"label": "x" * 61, "minutes": 5},
                               {"label": "Tea", "minutes": 0.1}, {"label": "Tea", "minutes": 1441},
                               {"label": "Tea", "minutes": "5"}, {"label": "Tea", "minutes": True},
                               {"label": 5, "minutes": 5}, {"label": "Tea", "minutes": 5, "id": "x"}],
           "/api/timers/remove": [{"id": "q1"}, {"id": "plan:t1"}, {"id": "quick:"}, {"id": "quick:" + "a" * 60},
                                  {"id": "quick:a b"}, {"id": 1}, {}]}

    def post(self, port, path, body, token, host=None, origin=None, ctype="application/json"):
        hdr = {"Content-Type": ctype, server.TOKEN_HEADER: token,
               "Origin": origin or "http://127.0.0.1:%d" % port}
        hdr = {k: v for k, v in hdr.items() if v is not None}
        return h.request(port, "POST", path, hdr, body, host=host)

    def test_the_guard_on_every_changing_route(self):
        self.inst.write_log(RUN_A)
        svc = self.make(running=False)
        t, out = run_in_thread(svc)
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            port, token = run["port"], run["token"]
            self.assertTrue(h.wait_until(lambda: answers(port), 5))
            before = json.dumps(svc.user_data)
            for path, body in self.ROUTES:
                for tok in ("", "wrong", token + "x"):
                    self.assertEqual(self.post(port, path, body, tok)[0], 403, (path, tok))
                self.assertEqual(h.request(port, "POST", path, {"Content-Type": "application/json",
                                                               "Origin": "http://127.0.0.1:%d" % port}, body)[0], 403)
                self.assertEqual(self.post(port, path, body, token, host="evil.example:%d" % port)[0], 403, path)
                for origin in ("http://evil.example", "null", "http://127.0.0.1:%d" % (port + 1)):
                    self.assertEqual(self.post(port, path, body, token, origin=origin)[0], 403, (path, origin))
                self.assertEqual(self.post(port, path, body, token, ctype="text/plain")[0], 415, path)
                self.assertEqual(self.post(port, path, b"not json", token)[0], 400, path)
                self.assertEqual(self.post(port, path, b"[1]", token)[0], 400, path)
                for bad in self.BAD[path]:
                    status, _, raw = self.post(port, path, bad, token)
                    self.assertEqual(status, 400, (path, bad))
                    self.assertIn("error", json.loads(raw))
                self.assertEqual(h.request(port, "GET", path)[0], 405, path)
                self.assertEqual(self.post(port, path + "?token=" + token, body, "")[0], 403, "no token in a URL")
            self.assertEqual(json.dumps(svc.user_data), before, "nothing refused changed anything")
            # and each is accepted when everything is right
            status, _, raw = self.post(port, "/api/view", {"view": "reference"}, token)
            self.assertEqual(status, 200, raw)
            self.assertEqual(json.loads(raw)["view"], {"name": "reference", "auto": "idle", "picked": True})
            self.assertEqual(board(svc)["view"]["name"], "reference", "the next message has it")
            status, _, raw = self.post(port, "/api/timers/add", {"label": "Tea", "minutes": 5}, token)
            self.assertEqual(status, 200, raw)
            tid = json.loads(raw)["timer"]["id"]
            self.assertTrue(tid.startswith("quick:q"))
            self.assertIn(tid, [x["id"] for x in board(svc)["timers"]])
            status, _, raw = self.post(port, "/api/timers/remove", {"id": tid}, token)
            self.assertEqual((status, json.loads(raw)["removed"]), (200, True))
            self.assertNotIn(tid, [x["id"] for x in board(svc)["timers"]])
            status, _, raw = self.post(port, "/api/timers/remove", {"id": tid}, token)
            self.assertEqual((status, json.loads(raw)["removed"]), (200, False), "removing twice is no error")
            status, _, raw = self.post(port, "/api/view/live", {}, token)
            self.assertEqual(status, 200, raw)
            self.assertEqual(json.loads(raw)["view"]["picked"], False)
            self.assertEqual(board(svc)["view"]["name"], "idle")
            self.assertNotIn("view", self.saved_user(), "saved at once, not 10 s later")
        finally:
            svc.request_stop()
            t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_OK)

    def test_a_change_wakes_the_loop_and_the_page_gets_it(self):
        """The loop sleeps ~10 s with no game; a change is sent at once, not on its next turn."""
        self.inst.write_log(RUN_A)
        svc = self.make(running=False, process_check_seconds=10.0)
        t, out = run_in_thread(svc)
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            self.assertTrue(h.wait_until(lambda: answers(run["port"]), 5))
            t0 = time.monotonic()
            status, _, _ = self.post(run["port"], "/api/view", {"view": "selling"}, run["token"])
            self.assertEqual(status, 200)
            st = answers(run["port"])
            self.assertEqual(st["board"]["view"]["name"], "selling")
            self.assertLess(time.monotonic() - t0, 2.0)
        finally:
            svc.request_stop()
            t.join(15)


# ---------------------------------------------------------------------------- picks

class Picks(WiringCase):
    def test_a_pick_survives_a_restart(self):
        svc = self.started(MINING_CUT)
        self.assertEqual(board(svc)["view"]["name"], "mining")
        status, answer = svc._api_view(Req({"view": "refinery"}))
        self.assertEqual(status, 200, answer)
        self.assertEqual(answer["view"], {"name": "refinery", "auto": "mining", "picked": True})
        self.assertEqual(self.saved_user()["view"]["view"], "refinery", "saved at once")
        self.assertEqual(self.saved_user()["view"]["context"], "ship:900000000014")
        svc.close()
        again = self.make(running=True)                  # restarted mid-session: reads from the top
        again.start_reading()
        self.drain(again)
        b = board(again)
        self.assertEqual((b["view"]["name"], b["view"]["picked"]), ("refinery", True))
        self.assertEqual(again.user_data["view"]["view"], "refinery")

    def test_a_pick_is_dropped_when_the_context_changes(self):
        svc = self.started(MINING_CUT)
        self.assertEqual(svc._api_view(Req({"view": "cargo"}))[0], 200)
        self.assertEqual(board(svc)["view"]["name"], "cargo")
        self.inst.write_log(TRAVEL_CUT[len(MINING_CUT):], "ab")    # a quantum target is chosen
        self.drain(svc)
        b = board(svc)
        self.assertEqual(b["view"]["name"], "travel")
        self.assertFalse(b["view"]["picked"])
        self.assertFalse(b["view"]["pick_dropped"], "the payload is built again without the pick")
        self.assertNotIn("view", svc.user_data)
        self.assertNotIn("view", self.saved_user(), "and the saved block forgets it at once")
        self.assertIn("dropped: its context changed", svc.paths.log.read_text(encoding="utf-8"))

    def test_the_reference_pick_survives_context_restart_and_session_end(self):
        svc = self.started(MINING_CUT)
        self.assertEqual(svc._api_view(Req({"view": "reference"}))[0], 200)
        b = board(svc)
        self.assertEqual((b["view"]["name"], b["view"]["auto"], b["model"]["mode"]), ("reference", "mining", "mining"))
        self.inst.write_log(TRAVEL_CUT[len(MINING_CUT):], "ab")    # context change
        self.drain(svc)
        b = board(svc)
        self.assertEqual((b["view"]["name"], b["view"]["auto"]), ("reference", "travel"))
        svc.close()
        again = self.make(running=True)                              # restart
        again.start_reading()
        self.drain(again)
        self.assertEqual(board(again)["view"]["name"], "reference")
        self.inst.write_log(RUN_A[len(TRAVEL_CUT):], "ab")           # the rest, to the quit line
        self.drain(again)
        again.probe.on = False                                       # and the game process goes
        again._next_probe = 0.0
        again.tick()
        b = board(again)
        self.assertEqual((b["view"]["name"], b["view"]["auto"]), ("reference", "idle"))
        self.assertEqual(self.saved_user()["view"]["view"], "reference")
        self.assertEqual(again._api_live(Req({}))[0], 200)
        self.assertEqual(board(again)["view"]["name"], "idle", "only Live ends it")

    def test_no_pick_while_a_large_log_is_half_read(self):
        """A pick is kept under the context it was made in; on a half-read state it would be
        dropped as soon as the rest came in: refused with 503 until caught up."""
        self.inst.write_log(RUN_A)
        with mock.patch.object(config, "READ_BUDGET", 2048):
            svc = self.make(running=True)
            svc.mono = Mono(1000.0)
            svc.start_reading()
            self.assertTrue(svc.tick(), "still catching up")
            self.assertEqual(svc._api_view(Req({"view": "mining"}))[0], 503)
            self.assertEqual(svc._api_timer_add(Req({"label": "x", "minutes": 1}))[0], 503,
                             "nothing changes before the log has been read once (finding G)")
            self.drain(svc, 200)
        self.assertEqual(svc._api_view(Req({"view": "mining"}))[0], 200)
        self.assertEqual(svc._api_timer_add(Req({"label": "x", "minutes": 1}))[0], 200)


# ---------------------------------------------------------------------------- quick timers

class QuickTimers(WiringCase):
    def test_added_removed_and_capped(self):
        svc = self.started(RUN_A, running=False)
        ids = []
        for i in range(12):
            status, answer = svc._api_timer_add(Req({"label": "Timer %d" % i, "minutes": 10 + i}))
            self.assertEqual(status, 200, answer)
            ids.append(answer["timer"]["id"])
            svc.clock.t += 0.001                              # a new millisecond each
        self.assertEqual(len(set(ids)), 12)
        quick = [x for x in board(svc)["timers"] if x["source"] == "quick"]
        self.assertEqual([x["label"] for x in quick], ["Timer %d" % i for i in range(2, 12)], "the newest ten")
        self.assertEqual(len(self.saved_user()["timers"]), 10)
        self.assertEqual(svc._api_timer_remove(Req({"id": ids[5]}))[1]["removed"], True)
        self.assertNotIn(ids[5], [x["id"] for x in board(svc)["timers"]])
        self.assertEqual(svc._api_timer_remove(Req({"id": ids[0]}))[1]["removed"], False, "already dropped by the cap")
        self.assertEqual(len(self.saved_user()["timers"]), 9)
        b = board(svc)
        t = next(x for x in b["timers"] if x["id"] == ids[11])
        self.assertEqual(t["state"], "running")
        self.assertAlmostEqual(t["ready_ms"], (svc.clock.t - 0.001 + 21 * 60) * 1000, delta=1.5)   # float ms

    def test_a_label_is_cleaned_and_bounded(self):
        svc = self.started(RUN_A, running=False)
        status, answer = svc._api_timer_add(Req({"label": "Tea\x1b[31m‮", "minutes": 0.5}))
        self.assertEqual(status, 200)
        self.assertEqual(answer["timer"]["label"], "Tea[31m")
        self.assertEqual(svc._api_timer_add(Req({"label": "\x1b\x07", "minutes": 1}))[0], 400)
        self.assertEqual(svc._api_timer_add(Req({"label": "x", "minutes": 10 ** 400}))[0], 400)
        self.assertEqual(svc._api_timer_add(Req({"label": "x", "minutes": float("nan")}))[0], 400)


# ---------------------------------------------------------------------------- the plan

class Plan(WiringCase):
    def write_plan(self, obj):
        text = obj if isinstance(obj, str) else json.dumps(obj)
        (self.inst.data / "plan.json").write_text(text, encoding="utf-8")

    def test_an_edit_is_picked_up_and_sent(self):
        svc = self.started(RUN_A, running=False)
        self.assertFalse(board(svc)["plan"]["loaded"])
        plan = json.loads(PLAN_EXAMPLE.read_text(encoding="utf-8"))
        self.write_plan(plan)
        svc._next_plan_check = 0.0
        svc.tick()
        b = board(svc)
        self.assertTrue(b["plan"]["loaded"])
        self.assertIsNone(b["plan"]["notice"])
        first_run = b["plan"]["run"]
        self.assertTrue(first_run)
        cur = next(r for r in plan["runs"] if r["id"] == plan["current_run"])
        cur["name"] = "Renamed run for the test"
        self.write_plan(plan)
        svc._next_plan_check = 0.0
        svc.tick()
        self.assertEqual(board(svc)["plan"]["run"], "Renamed run for the test")
        self.assertIn("plan.json read", svc.paths.log.read_text(encoding="utf-8"))
        self.assertTrue(svc.status()["plan"]["loaded"])

    def test_a_broken_plan_keeps_the_last_good_copy_with_a_notice(self):
        svc = self.started(RUN_A, running=False)
        self.write_plan(json.loads(PLAN_EXAMPLE.read_text(encoding="utf-8")))
        svc._next_plan_check = 0.0
        svc.tick()
        good = board(svc)["plan"]
        self.write_plan('{"schema": 1,\n "runs": [')
        svc._next_plan_check = 0.0
        svc.tick()
        b = board(svc)["plan"]
        self.assertTrue(b["loaded"])
        self.assertEqual(b["run"], good["run"])
        self.assertIn("not valid JSON", b["notice"])
        self.assertIn("last good copy", b["notice"])
        self.assertIn("not valid JSON", svc.status()["plan"]["notice"])

    def test_the_plan_is_looked_at_once_a_second_at_most(self):
        svc = self.started(RUN_A, running=True)
        svc.mono = Mono(5000.0)
        svc._next_plan_check = 0.0
        with mock.patch.object(svc.plans, "refresh", wraps=svc.plans.refresh) as spy:
            for _ in range(5):
                svc.tick()
            self.assertEqual(spy.call_count, 1)
            svc.mono.t += config.PLAN_CHECK_SECONDS
            svc.tick()
            self.assertEqual(spy.call_count, 2)

    def test_a_refresh_that_raises_does_not_end_the_loop(self):
        svc = self.started(RUN_A, running=True)
        with mock.patch.object(svc.plans, "refresh", side_effect=OSError("odd")):
            svc._next_plan_check = 0.0
            svc.tick()
        self.assertGreaterEqual(svc.errors, 1)
        self.assertIn("error in looking at plan.json", svc.paths.log.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------- next_change_ms

class NextChange(WiringCase):
    def test_rebuilt_at_next_change_and_not_before(self):
        data = lib.sample_bytes("built_failed.log")
        self.inst.write_log(data)
        first = service.log_span(self.inst.log)[1]
        clock = Clock(first + 1)
        svc = self.make(running=False, clock=clock, process_check_seconds=10.0)
        svc.start_reading()
        b = board(svc)
        nxt = b["next_change_ms"]
        alerts = len(b["alerts"])
        self.assertGreater(alerts, 0)
        builds = svc.board_builds
        clock.t = nxt / 1000.0 - 0.5
        for _ in range(3):
            svc.tick()
        self.assertEqual(svc.board_builds, builds, "not before the moment")
        wait = svc._next_wait()
        self.assertTrue(0.4 < wait <= 0.55, "the loop wakes for it, not 10 s later: %r" % wait)
        clock.t = nxt / 1000.0 + 0.001
        svc.tick()
        self.assertEqual(svc.board_builds, builds + 1, "rebuilt at the moment, with no new event")
        self.assertEqual(len(board(svc)["alerts"]), alerts - 1, "the alert that expired is gone")
        self.assertGreater(board(svc)["next_change_ms"], nxt)

    def test_the_wait_follows_the_replay_clock(self):
        svc = self.started(RUN_A, running=False, process_check_seconds=10.0)
        clock = service.ReplayClock(svc.clock.now(), 100.0)
        svc.clock = clock
        svc._board_next_ms = int((clock.now() + 50.0) * 1000)       # 50 s of replay time = 0.5 s
        self.assertLess(svc._next_wait(), 0.6)
        clock.freeze()
        self.assertGreater(svc._next_wait(), 1.0, "a frozen clock never reaches it")


# ---------------------------------------------------------------------------- state.json read late

class LateUserBlock(WiringCase):
    def test_unreadable_at_start_then_readable_is_merged_not_overwritten(self):
        self.inst.write_log(RUN_A)
        folder = self.inst.data / "state.json"
        folder.mkdir(parents=True)                       # cannot be opened as a file
        svc = self.make(running=False, state_save_seconds=2.0)
        svc.start_reading()
        self.assertFalse(svc._user_loaded)
        s1, a1 = svc._api_timer_add(Req({"label": "made while unreadable", "minutes": 30}))
        self.assertEqual(s1, 200)
        self.assertEqual(svc._api_view(Req({"view": "reference"}))[0], 200)
        self.assertEqual(svc._api_timer_remove(Req({"id": "quick:q-file-2"}))[0], 200, "maybe in the file")
        self.assertTrue(folder.is_dir(), "never saved over what was not read")
        self.assertEqual(board(svc)["view"]["name"], "reference", "shown already")
        # The file becomes readable, holding what an earlier run saved.
        folder.rmdir()
        file_block = {"timers": [{"id": "q-file-1", "label": "from the file", "added_at": "2026-11-26T23:00:00.000Z",
                                  "ready_at": "2026-11-27T01:00:00.000Z"},
                                 {"id": "q-file-2", "label": "removed while unreadable",
                                  "added_at": "2026-11-26T23:00:00.000Z", "ready_at": "2026-11-27T01:00:00.000Z"}],
                      "view": {"view": "mining", "context": "ship:1", "at": None}, "kept": {"other": 1}}
        service.write_json(folder, {"schema": 1, "user": file_block, "state": {}})
        svc._next_user_try = 0.0
        svc.tick()
        self.assertTrue(svc._user_loaded)
        labels = [x["label"] for x in svc.user_data["timers"]]
        self.assertEqual(labels, ["from the file", "made while unreadable"])
        self.assertEqual(svc.user_data["view"]["view"], "reference", "the newer pick wins")
        self.assertEqual(svc.user_data["kept"], {"other": 1}, "what the file holds is kept")
        saved = self.saved_user()
        self.assertEqual([x["label"] for x in saved["timers"]], labels, "and saved, merged")
        quick = [x["label"] for x in board(svc)["timers"] if x["source"] == "quick"]
        self.assertIn("made while unreadable", quick)
        self.assertIn("merged into it", svc.paths.log.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------- unmapped contracts

class UnmappedContracts(WiringCase):
    def test_written_beside_the_location_codes_and_kept(self):
        svc = self.started(lib.sample_bytes("built_unknown.log"), running=False)
        um = service.read_json(self.inst.data / "unmapped.json")
        self.assertIn("locations", um)
        entries = list(um["contracts"].values())
        self.assertEqual([(e["contract"], e["generator"], e["title"]) for e in entries],
                         [("Example_Unlisted_Contract", "Example_Generator", "A Very Unusual Job")])
        self.assertEqual(entries[0]["session"], "Build(13220821) 27 Nov 26 (21 00 00)")
        # another session's: merged, the first one kept
        svc.close()
        self.inst.write_log(lib.sample_bytes("built_failed.log"))
        svc2 = self.make(running=False)
        svc2.start_reading()
        um = service.read_json(self.inst.data / "unmapped.json")
        titles = sorted(e["title"] for e in um["contracts"].values())
        self.assertEqual(titles, ["A Very Unusual Job", "Claim #4521: Drake Cutlass Black Salvage Rights"])

    def test_bounded(self):
        svc = self.started(lib.sample_bytes("built_unknown.log"), running=False)
        with mock.patch.object(config, "MAX_UNMAPPED_CONTRACTS", 3):
            state = json.loads(svc.hub.latest)["state"]
            for i in range(6):
                state["session"]["last_event"] = "2030-01-01T00:00:0%d.000Z" % i
                svc._note_unmapped(state, {"unmapped_contracts": [{"contract": "C%d" % i, "generator": None,
                                                                   "title": "t" * 400}]})
            um = service.read_json(self.inst.data / "unmapped.json")
        self.assertEqual(sorted(e["contract"] for e in um["contracts"].values()), ["C3", "C4", "C5"])
        self.assertTrue(all(len(e["title"]) <= 300 for e in um["contracts"].values()))


# ---------------------------------------------------------------------------- catching up

class CatchUp(WiringCase):
    def test_nothing_half_read_goes_out_and_no_old_alert_flashes_up(self):
        """courier.log has a death at 7:05 AM and a respawn after it: read in 2 KB pieces, a
        half-read state would carry the Dead alert. Nothing is sent until the whole log is in."""
        self.inst.write_log(lib.sample_bytes("courier.log"))
        with mock.patch.object(config, "READ_BUDGET", 2048):
            svc = self.make(running=True)
            svc.mono = Mono(1000.0)
            svc.start_reading()
            self.assertIsNone(svc.hub.latest, "nothing before the first read")
            turns = 0
            while svc.tick():
                turns += 1
                self.assertIsNone(svc.hub.latest, "nothing while catching up")
        self.assertGreater(turns, 10)
        self.assertEqual(svc.publishes, 1)
        b = board(svc)
        self.assertNotIn("Dead", [a["kind"] for a in b["alerts"]])
        self.assertEqual(svc.board_builds, 1)

    def test_a_read_that_fails_while_catching_up_ends_the_catch_up(self):
        """Left set after a failed read, the flag refused every pick and held back every change
        from the page for as long as reads kept failing."""
        self.inst.write_log(RUN_A)
        with mock.patch.object(config, "READ_BUDGET", 2048):
            svc = self.make(running=True)
            svc.mono = Mono(1000.0)
            svc.start_reading()
            self.assertTrue(svc.tick(), "catching up")
            self.assertEqual(svc._api_view(Req({"view": "mining"}))[0], 503)
            with mock.patch.object(svc.reader, "poll", side_effect=OSError("a read that fails")):
                for _ in range(3):
                    with self.assertRaises(OSError):
                        svc.tick()                       # the loop logs it and waits a second
                self.assertIsNone(svc._busy_since)
                published = svc.publishes
                self.assertEqual(svc._api_timer_add(Req({"label": "x", "minutes": 1}))[0], 200)
                self.assertEqual(svc.publishes, published + 1, "a change from the page goes out")
                self.assertEqual(svc._api_view(Req({"view": "mining"}))[0], 200, "a pick is taken")
            self.drain(svc, 200)                         # reads work again: caught up as before
        self.assertFalse(svc.tick())
        self.assertIsNone(svc._busy_since)

    def test_a_very_long_catch_up_still_sends_now_and_then(self):
        self.inst.write_log(lib.sample_bytes("courier.log"))
        with mock.patch.object(config, "READ_BUDGET", 2048):
            svc = self.make(running=True)
            svc.mono = Mono(1000.0)
            svc.start_reading()
            svc.tick()
            svc.mono.t += config.CATCH_UP_PUBLISH_SECONDS
            svc.tick()
            self.assertIsNotNone(svc.hub.latest)


# ---------------------------------------------------------------------------- the lock

class TheLock(WiringCase):
    """A change from the page runs under the main loop's lock. Nothing in it may wait on a page's
    connection, and a disk that fails saves must not make the page's changes wait on it."""

    def test_while_saves_fail_a_change_does_not_wait_for_the_disk(self):
        svc = self.started(RUN_A, running=False)
        svc.mono = Mono(1000.0)
        real = service.write_json
        tries = []

        def held(path, obj, indent=1):
            if path.name != "state.json":
                return real(path, obj, indent)
            tries.append(time.monotonic())
            time.sleep(0.3)                              # a held file: atomic_write retries ~2 s
            raise PermissionError("[WinError 32] held by another program")
        with mock.patch.object(service, "write_json", side_effect=held):
            self.assertEqual(svc._api_timer_add(Req({"label": "first", "minutes": 5}))[0], 200)
            self.assertEqual(len(tries), 1, "saved at once, as always; it fails")
            t0 = time.monotonic()
            for i in range(4):
                self.assertEqual(svc._api_timer_add(Req({"label": "more %d" % i, "minutes": 5}))[0], 200)
            self.assertEqual(len(tries), 1, "no save tried from the page while saves fail")
            self.assertLess(time.monotonic() - t0, 0.25)
            svc.tick()
            self.assertEqual(len(tries), 1, "nor by the loop before its pause")
            svc.mono.t += svc.settings["state_save_seconds"]
            svc.tick()
            self.assertEqual(len(tries), 2, "the loop tries again at its own pace")
        svc.mono.t += svc.settings["state_save_seconds"]
        svc.tick()                                       # the file is free again
        self.assertEqual([x["label"] for x in self.saved_user()["timers"]],
                         ["first"] + ["more %d" % i for i in range(4)])
        self.assertEqual(svc._api_timer_add(Req({"label": "after", "minutes": 5}))[0], 200)
        self.assertEqual(self.saved_user()["timers"][-1]["label"], "after", "saved at once again")

    def test_a_page_that_never_reads_holds_up_no_change(self):
        """A page connection that reads nothing fills its socket's buffers; its own thread then
        waits in a write. The change requests and every other page carry on."""
        self.inst.write_log(RUN_A)
        svc = self.make(running=False, push_min_seconds=0.05)
        t, out = run_in_thread(svc)
        hung = None
        good = None
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            port, token = run["port"], run["token"]
            self.assertTrue(h.wait_until(lambda: answers(port), 5))
            hung = socket.socket()
            hung.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
            hung.connect(("127.0.0.1", port))
            hung.sendall(b"GET /api/stream HTTP/1.0\r\nHost: 127.0.0.1:%d\r\n\r\n" % port)
            self.assertTrue(h.wait_until(lambda: svc.hub.clients == 1, 5))
            sent_before, published_before = svc.hub.sent, svc.publishes
            slowest = 0.0
            hdr = {"Content-Type": "application/json", server.TOKEN_HEADER: token,
                   "Origin": "http://127.0.0.1:%d" % port}
            for i in range(40):                          # each change a new message of ~size bytes
                t0 = time.monotonic()
                status, _, raw = h.request(port, "POST", "/api/timers/add", hdr, {"label": "t%d" % i, "minutes": 5})
                slowest = max(slowest, time.monotonic() - t0)
                self.assertEqual(status, 200, raw)
                if i % 10 == 9:
                    for x in svc.user_data["timers"]:
                        h.request(port, "POST", "/api/timers/remove", hdr, {"id": "quick:" + x["id"]})
                time.sleep(0.06)
            published, sent = svc.publishes - published_before, svc.hub.sent - sent_before
            self.assertGreaterEqual(published, 40)
            self.assertLess(sent, published / 4, "the page's thread is stuck in a write (%d of %d sent)"
                            % (sent, published))
            self.assertEqual(svc.hub.clients, 1, "and still connected")
            self.assertLess(slowest, 1.0, "no change waited on the page")
            good = Stream(port)
            self.assertTrue(h.wait_until(lambda: good.data() and good.data()[-1] == svc.hub.latest, 5),
                            "another page gets the newest state")
            self.assertEqual(h.request(port, "POST", "/api/timers/add", hdr, {"label": "final one", "minutes": 5})[0], 200)
            self.assertTrue(h.wait_until(lambda: "final one" in good.data()[-1], 5), "and the next change")
        finally:
            for c in (hung, good):
                if c is not None:
                    c.close()
            svc.request_stop()
            t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_OK)


# ---------------------------------------------------------------------------- the board's inputs

class BoardInputs(WiringCase):
    """`_board_inputs()` is complete: whenever the service does not rebuild the board, a board
    built afresh from the same state, plan, user block, clock and game flag is the same payload.
    Every sample log, fed in random pieces with the clock moving, a plan and changes from the
    page on the way, and the game ending at the close."""

    def test_a_board_not_rebuilt_equals_one_built_now(self):
        rnd = random.Random(20261128)
        samples = sorted(p.name for p in (lib.DASHBOARD / "tests" / "samples").glob("*.log"))
        self.assertGreater(len(samples), 10)
        compared = 0
        for name in samples:
            data = lib.sample_bytes(name)
            folder = self.inst.data / ("case-" + name)
            log = self.inst.dir / ("log-" + name)
            log.write_bytes(b"")
            first = service.line_time(data.split(b"\n", 1)[0]) or 1.8e9
            clock = Clock(first)
            svc = Service(folder, log, settings(), probe=Probe(True), names=lib.NAMES, clock=clock)
            self.services.append(svc)
            svc.start_reading()
            pos, step = 0, 0
            while pos < len(data) or step < 3:
                n = rnd.choice((1, 7, 64, 500, 2048, 9000))
                with open(log, "ab") as f:
                    f.write(data[pos:pos + n])
                pos += n
                step += 1
                clock.t += rnd.choice((0.0, 0.5, 3.0, 40.0, 400.0))
                if step == 4:
                    (folder / "plan.json").write_text(PLAN_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
                    svc._next_plan_check = 0.0
                if step == 6:
                    svc._api_timer_add(Req({"label": "a quick one", "minutes": 2}))
                if step == 8:
                    svc._api_view(Req({"view": "refinery"}))
                svc._next_probe = 0.0
                svc.tick()
                compared += self.same(svc, name, step)
                clock.t += rnd.choice((0.2, 30.0, 700.0))  # a turn with only the clock moving
                svc.tick()
                compared += self.same(svc, name, "%s+clock" % step)
            svc.probe.on = False                         # the game goes: the session is read to its end
            svc._next_probe = 0.0
            clock.t += 5.0
            svc.tick()
            compared += self.same(svc, name, "end")
            svc.close()
        self.assertGreater(compared, 200, "enough turns compared")

    def same(self, svc, name, step):
        now = svc.clock.now()
        if svc._board_due(now):
            return 0
        fresh = service.boardlib.build(svc.reader.state, svc.plans, svc.user_data, now, bool(svc.game_running))
        self.assertEqual(fresh, svc.board, "%s, step %s: the board changed with no input changed" % (name, step))
        return 1


# ---------------------------------------------------------------------------- lone surrogates

# A plan with lone surrogates, written as the JSON escapes a file can hold ("\ud800" is valid
# JSON; json.loads gives a code point UTF-8 cannot encode). Bytes, so nothing here encodes them.
SURROGATE_PLAN = (b'{"schema": 1, "notes": ["\\ud800 a lone surrogate"], "current_run": "r", '
                  b'"runs": [{"id": "r", "name": "Run \\udfff", "kind": "mining", "status": "in_progress"}]}')


def strict_json(raw):
    """Parsed as a browser's JSON.parse would: UTF-8, and no NaN or Infinity."""
    def no_constant(name):
        raise ValueError("not JSON: %s" % name)
    return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw, parse_constant=no_constant)


def has_surrogate(obj):
    return any(0xD800 <= ord(ch) <= 0xDFFF for s in strings(obj) for ch in s)


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from strings(v)


class LoneSurrogates(WiringCase):
    """No text from the plan, the log, state.json or a request body can make the page's message,
    state.json, unmapped.json, a summary, status or an endpoint's answer fail to encode (stage 3
    review: "\\ud800" in plan.json or a quick timer's label raised UnicodeEncodeError). The source
    modules may clean such text too; these tests also put it past them, so they hold either way."""

    def post(self, port, token, path, body):
        return h.request(port, "POST", path, {"Content-Type": "application/json", server.TOKEN_HEADER: token,
                                              "Origin": "http://127.0.0.1:%d" % port}, body)

    def test_a_plan_and_a_label_with_lone_surrogates_over_http(self):
        (self.inst.data).mkdir(parents=True, exist_ok=True)
        (self.inst.data / "plan.json").write_bytes(SURROGATE_PLAN)
        self.inst.write_log(MINING_CUT)
        svc = self.make(running=False)
        t, out = run_in_thread(svc)
        stream = None
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            port, token = run["port"], run["token"]
            self.assertTrue(h.wait_until(lambda: answers(port), 5))
            status, _, raw = h.request(port, "GET", "/api/state")
            self.assertEqual(status, 200, raw[:200])
            msg = strict_json(raw)
            self.assertTrue(msg["board"]["plan"]["loaded"])
            self.assertFalse(has_surrogate(msg))
            stream = Stream(port)
            self.assertTrue(h.wait_until(lambda: stream.data(), 5), "the stream carries the message")
            self.assertFalse(has_surrogate(strict_json(stream.data()[0])))
            # a label with one: taken out like a control character; with nothing else: 400
            status, _, raw = self.post(port, token, "/api/timers/add", {"label": "Tea\ud800", "minutes": 5})
            self.assertEqual(status, 200, raw)
            self.assertEqual(strict_json(raw)["timer"]["label"], "Tea")
            for label in ("\ud800", "\udfff\ud800", " \ud800 "):
                status, _, raw = self.post(port, token, "/api/timers/add", {"label": label, "minutes": 5})
                self.assertEqual(status, 400, (ascii(label), raw))
            status, _, raw = self.post(port, token, "/api/view", {"view": "mining", "x\ud800": 1})
            self.assertEqual(status, 400)
            strict_json(raw)                                   # the error names the field: still JSON
            status, _, raw = h.request(port, "GET", "/api/status")
            self.assertEqual(status, 200)
            self.assertFalse(has_surrogate(strict_json(raw)))
            self.assertTrue(h.wait_until(lambda: any(
                "Tea" in d for d in stream.data()), 5), "the change reached the page")
            saved = strict_json((self.inst.data / "state.json").read_bytes())
            self.assertEqual([x["label"] for x in saved["user"]["timers"]], ["Tea"], "saved at once")
            self.assertEqual(svc.errors, 0, svc.paths.log.read_text(encoding="utf-8")[-3000:])
        finally:
            if stream is not None:
                stream.close()
            svc.request_stop()
            t.join(15)
        self.assertEqual(out.get("code"), service.EXIT_OK)

    def test_a_board_that_leaks_one_or_a_nan_still_goes_out_and_is_saved(self):
        """Past any cleaning at the source: a payload part with a lone surrogate and a NaN."""
        self.inst.write_log(RUN_A)
        real = service.boardlib.build

        def leaky(*a, **kw):
            p = real(*a, **kw)
            p["alerts"] = [{"id": "x\ud800", "level": "warn", "kind": "Attention", "title": "odd \udfff title",
                            "text": None, "do": None, "t": None, "t_ms": float("nan"), "until_ms": float("inf"),
                            "since_ms": None}]
            return p
        with mock.patch.object(service.boardlib, "build", side_effect=leaky):
            svc = self.make(running=False)
            svc.start_reading()
        msg = strict_json(svc.hub.latest.encode("utf-8"))
        a = msg["board"]["alerts"][0]
        self.assertEqual((a["title"], a["id"], a["t_ms"], a["until_ms"]), ("odd \ufffd title", "x\ufffd", None, None))
        status, (body, ctype) = svc._api_state(None)
        self.assertEqual(status, 200)
        strict_json(body)
        svc._unsaved = True
        svc._save_state()
        self.assertFalse(has_surrogate(strict_json((self.inst.data / "state.json").read_bytes())))
        self.assertEqual(svc.errors, 0)

    def test_a_state_json_and_an_unmapped_json_holding_them(self):
        self.inst.data.mkdir(parents=True, exist_ok=True)
        (self.inst.data / "state.json").write_bytes(
            b'{"schema": 1, "user": {"timers": [{"id": "q1", "label": "Tea \\ud800", '
            b'"added_at": "2030-01-01T00:00:00.000Z", "ready_at": "2030-01-01T01:00:00.000Z"}], '
            b'"kept\\udfff": ["x\\ud800"]}, "state": {}}')
        (self.inst.data / "unmapped.json").write_bytes(
            b'{"schema": 1, "locations": {"Code\\ud800": {"first_seen": "t\\udfff", "session": null, '
            b'"junk": "' + b"j" * 5000 + b'"}}, "contracts": {"k\\ud800": {"title": "T\\udfff"}}}')
        svc = self.started(lib.sample_bytes("built_unknown.log"), running=False)
        msg = strict_json(svc.hub.latest.encode("utf-8"))
        labels = [x["label"] for x in msg["board"]["timers"] if x["source"] == "quick"]
        self.assertEqual(len(labels), 1)                 # "Tea", or "Tea" and U+FFFD: either encodes
        self.assertTrue(labels[0].startswith("Tea") and not has_surrogate(labels), ascii(labels))
        self.assertFalse(has_surrogate(svc.user_data))
        svc._unsaved = svc._save_now = True
        svc._after_read(svc.clock.now())
        saved = strict_json((self.inst.data / "state.json").read_bytes())
        self.assertEqual(saved["user"]["kept\ufffd"], ["x\ufffd"], "kept, and encodable")
        um = strict_json((self.inst.data / "unmapped.json").read_bytes())
        code = [k for k in um["locations"] if k.startswith("Code")]       # cleaned: "Code" or "Code" + U+FFFD
        self.assertEqual(len(code), 1, list(um["locations"]))
        self.assertNotIn("junk", um["locations"][code[0]], "only the file's own two fields come back")
        self.assertFalse(has_surrogate(um))
        self.assertEqual(svc.errors, 0, svc.paths.log.read_text(encoding="utf-8")[-3000:])

    def test_status_and_the_service_log(self):
        svc = self.started(RUN_A, running=False)
        svc.plans.notice = "plan.json: odd \ud800"
        svc.user_data = {"view": {"view": "mining\udfff"}}
        st = svc.status()
        self.assertFalse(has_surrogate(st))
        json.dumps(st, ensure_ascii=False).encode("utf-8")
        svc.log.info("a line with a lone surrogate: %s", "x\ud800y")
        for hd in svc.log.handlers:
            hd.flush()
        text = svc.paths.log.read_text(encoding="utf-8")
        self.assertIn("a line with a lone surrogate: x\\ud800y", text, "escaped, not lost")

    def test_write_json_turns_them_and_nan_into_valid_json(self):
        p = self.inst.data / "x.json"
        service.write_json(p, {"a\ud800": ["b\udfff", float("nan"), float("-inf"), 1.5], "c": "\u00e9"})
        self.assertEqual(strict_json(p.read_bytes()), {"a\ufffd": ["b\ufffd", None, None, 1.5], "c": "\u00e9"})


# ---------------------------------------------------------------------------- status

class Status(WiringCase):
    def test_status_names_the_view_the_plan_and_the_problems(self):
        svc = self.started(MINING_CUT)
        st = svc.status()
        self.assertEqual(st["board"]["view"], "mining")
        self.assertEqual(st["board"]["rule"], "ship")
        self.assertEqual(st["board"]["problems"], 0)
        self.assertFalse(st["plan"]["loaded"])
        self.assertEqual(st["plan"]["notice"], "there is no plan.json yet")
        self.assertTrue(st["user"]["read"])
        self.assertIn("ships", st["reference_tables"])

    def test_the_status_command_prints_them(self):
        self.inst.write_log(MINING_CUT)
        svc = self.make(running=False)
        t, out = run_in_thread(svc)
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            self.assertTrue(h.wait_until(lambda: answers(run["port"]), 5))
            r = h.cli("status", "--data", self.inst.data)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"View +idle \(rule no_game\)")
            self.assertRegex(r.stdout, r"Plan +none")
            self.assertRegex(r.stdout, r"Notice +there is no plan.json yet")
            self.assertRegex(r.stdout, r"Problems +0")
            j = json.loads(h.cli("status", "--data", self.inst.data, "--json").stdout)
            self.assertEqual(j["status"]["board"]["view"], "idle")
        finally:
            svc.request_stop()
            t.join(15)


# ---------------------------------------------------------------------------- the service's own log

class OwnLog(WiringCase):
    def test_a_save_that_always_fails_logs_one_traceback(self):
        """Each failure names a new temporary file; it is the same fault all the same."""
        svc = self.started(RUN_A, running=False)

        def fails(path, obj, indent=1):
            raise PermissionError("[WinError 5] Access is denied: '.scdash-tmp-%s-state.json.tmp'" % secrets.token_hex(4))
        svc.mono = Mono(1000.0)
        with mock.patch.object(service, "write_json", side_effect=fails):
            for _ in range(25):
                svc._unsaved = svc._save_now = True
                svc.mono.t += svc.settings["state_save_seconds"]      # the loop's retry, each time
                svc._after_read(svc.clock.now())
        log = svc.paths.log.read_text(encoding="utf-8")
        self.assertEqual(log.count("Traceback"), 1, log[-2000:])
        self.assertEqual(log.count("error in saving state.json (carrying on)"), 1)
        self.assertIn("the same error in saving state.json, 11 times now", log)

    def test_two_errors_that_take_turns_are_each_logged_once(self):
        svc = self.started(RUN_A, running=False)
        for i in range(20):
            try:
                if i % 2:
                    raise OSError("a %d" % i)
                raise ValueError("b %d" % i)
            except Exception:                              # noqa: BLE001
                svc._error("somewhere")
        self.assertEqual(svc.paths.log.read_text(encoding="utf-8").count("Traceback"), 2)

    def test_the_same_error_in_full_again_after_an_hour(self):
        svc = self.started(RUN_A, running=False)
        with mock.patch.object(config, "ERROR_FULL_AGAIN_SECONDS", 0.2):
            for _ in range(2):
                try:
                    raise OSError("again")
                except OSError:
                    svc._error("somewhere")
                time.sleep(0.25)
        self.assertEqual(svc.paths.log.read_text(encoding="utf-8").count("Traceback"), 2)


class FrontEndFaultsDiffer(unittest.TestCase):
    """The front end's one line a minute for repeats no longer holds back a different fault, and
    the count of repeats goes out on a timer, without waiting for the next fault or shutdown."""

    def test_a_different_fault_is_logged_at_once_and_counts_flush_on_a_timer(self):
        records = []

        class Grab(logging.Handler):
            def emit(self, record):
                records.append((time.monotonic(), record.getMessage()))
        lg = logging.getLogger("scdash-test-frontend-differ-%x" % id(self))
        lg.setLevel(logging.DEBUG)
        lg.propagate = False
        lg.addHandler(Grab())

        def fault_a():
            raise RuntimeError("fault A")

        def fault_b():
            raise KeyError("fault B")
        with mock.patch.object(server, "FAULT_REPORT_SECONDS", 0.6, create=True):
            srv = server.Server(h.free_port(), "token-for-the-test-only", logger=lg, poll_interval=0.05)
            srv.start()
            try:
                fe = srv._httpd
                real = fe._turn
                # Phase 1: A repeats (counted), then B comes once while A's count is pending.
                fe._turn = fault_a
                time.sleep(0.3)
                t_b = time.monotonic()
                once = {"n": 0}

                def b_once():
                    if once["n"] == 0:
                        once["n"] += 1
                        fault_b()
                    return real()
                fe._turn = b_once
                self.assertTrue(h.wait_until(lambda: any("fault B" in m for _, m in records), 2),
                                "the different fault is in the log at once")
                t_logged = next(t for t, m in records if "fault B" in m)
                self.assertLess(t_logged - t_b, 0.4, "not held back behind A's minute")
                # Phase 2: A again (known: counted), then no fault at all.
                fe._turn = fault_a
                time.sleep(0.3)
                fe._turn = real
                n_before = len(records)
                self.assertTrue(h.wait_until(lambda: any("more time" in m for _, m in records[n_before:]), 2),
                                "the count goes out on the timer, with no new fault and no shutdown")
                self.assertEqual(h.request(srv.port, "GET", "/api/nothing")[0], 404, "it still serves")
            finally:
                srv.stop()
        full = [m for _, m in records if "Traceback" in m]
        self.assertEqual(len(full), 2, "A once in full, B once in full")
        self.assertTrue(any("fault A" in m for m in full) and any("fault B" in m for m in full))


# ============================================================================ the review's fix round
# The wiring review of 2026-11-28 (data/handoff/session4/review-wiring/REPORT.md): each finding
# (A to K), and a test for each guard its mutation run found untested.

TIMER = {"id": "q1", "label": "Real timer", "added_at": "2030-01-01T00:00:00.000Z",
         "ready_at": "2030-01-01T05:00:00.000Z"}


def timer(tid, label):
    return dict(TIMER, id=tid, label=label)


def text_of(*codes):
    """A text from code points: invisible characters are written by number, never literally."""
    return "".join(map(chr, codes))


def post(port, token, path, body):
    return h.request(port, "POST", path, {"Content-Type": "application/json", server.TOKEN_HEADER: token,
                                          "Origin": "http://127.0.0.1:%d" % port}, body)


class FixCase(WiringCase):
    def write_state(self, text):
        self.inst.data.mkdir(parents=True, exist_ok=True)
        (self.inst.data / "state.json").write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))

    def log_text(self, svc):
        return svc.paths.log.read_text(encoding="utf-8")


class UserBlockFromFile(FixCase):
    """A: a user block nested 2,500 deep wiped the block and stopped the last log from being read.
    B: timers the board renamed could not be removed. D: unknown keys were kept without bound."""

    DEEP = "[" * 2500 + "1" + "]" * 2500           # json.loads takes it; a recursive walk does not

    def deep_block(self):
        return ('{"timers": [%s], "view": {"view": "reference", "context": "reference", "at": null}, '
                '"deep": %s, "small": {"a": 1}}' % (json.dumps(TIMER), self.DEEP))

    def check_kept(self, svc):
        self.assertEqual([x["label"] for x in svc.user_data["timers"]], ["Real timer"])
        self.assertEqual(svc.user_data["view"]["view"], "reference")
        self.assertNotIn("deep", svc.user_data)
        self.assertEqual(svc.user_data["small"], {"a": 1})
        self.assertIn("left out 'deep' (nested deeper than", self.log_text(svc))
        saved = self.saved_user()
        self.assertEqual(saved["timers"][0]["label"], "Real timer")
        self.assertNotIn("deep", saved)
        self.assertEqual(board(svc)["view"]["name"], "reference")

    def test_a_deeply_nested_key_is_left_out_and_the_rest_kept_no_game(self):
        self.write_state('{"schema": 1, "user": %s, "state": {}}' % self.deep_block())
        svc = self.started(RUN_A, running=False)
        self.assertGreater(svc.reader.state.session["events"], 0, "the last log is read at the start")
        self.check_kept(svc)

    def test_a_deeply_nested_key_is_left_out_and_the_rest_kept_game_running(self):
        self.write_state('{"schema": 1, "user": %s, "state": {}}' % self.deep_block())
        svc = self.started(RUN_A, running=True)
        self.check_kept(svc)

    def test_scrub_and_the_depth_check_never_recurse_too_far(self):
        x = 1
        for _ in range(5000):
            x = [x]
        self.assertTrue(server.json_depth_over(x, 100))
        self.assertFalse(server.json_depth_over([[1]], 2))
        self.assertTrue(server.json_depth_over([[[1]]], 2))
        out = server.scrub(x)                       # no RecursionError
        depth = 0
        while isinstance(out, list):
            out, depth = out[0], depth + 1
        self.assertEqual((depth, out), (server.MAX_DEPTH, None), "what is deeper becomes None")
        server._finite({"a": x, "n": float("nan")})            # no RecursionError either

    def test_a_state_json_that_does_not_parse_is_moved_aside_not_saved_over(self):
        """Each damaged file kept aside, the first copy never replaced (the review's second
        round: a second damage replaced the copy that held the user's real data)."""
        bads = (b'{"schema": 1, "user": {"timers": [ broken', b"\xff\xfe not UTF-8", b"[1, 2]")
        names = ("state.damaged.json", "state.damaged-2.json", "state.damaged-3.json")
        for bad, name in zip(bads, names):
            self.write_state(bad)
            svc = self.started(RUN_A, running=False)
            self.assertTrue(svc._user_loaded)
            self.assertIsNotNone(strict_json((self.inst.data / "state.json").read_bytes())["state"])
            self.assertIn("moved aside to %s;" % name, self.log_text(svc))
            svc.close()
        for bad, name in zip(bads, names):
            self.assertEqual((self.inst.data / name).read_bytes(), bad, name)
        self.assertEqual(sorted(p.name for p in self.inst.data.glob("state*")), sorted(names + ("state.json",)))

    def test_once_every_copy_name_is_taken_only_the_last_is_replaced(self):
        first = b'{"schema": 1, "user": {"timers": [ the first damage'
        self.write_state(first)
        self.started(RUN_A, running=False).close()
        for n in range(2, config.MAX_DAMAGED_COPIES + 2):
            self.write_state(b"{ damage %d" % n)
            self.started(RUN_A, running=False).close()
        self.assertEqual((self.inst.data / "state.damaged.json").read_bytes(), first, "the first copy is kept")
        last = config.MAX_DAMAGED_COPIES
        self.assertEqual((self.inst.data / ("state.damaged-%d.json" % last)).read_bytes(), b"{ damage %d" % (last + 1))
        self.assertEqual(len(list(self.inst.data.glob("state.damaged*"))), config.MAX_DAMAGED_COPIES)
        self.assertIn("replacing the copy that was there", self.log_text(self.services[-1]))

    def test_a_byte_order_mark_is_not_damage(self):
        """The review's second round: Windows PowerShell 5.1 saves UTF-8 with a byte-order mark;
        such a state.json was moved aside and the user's timers vanished."""
        self.write_state(b"\xef\xbb\xbf" + json.dumps({"schema": 1, "user": {"timers": [TIMER]}, "state": {}}).encode())
        svc = self.started(RUN_A, running=False)
        self.assertEqual([x["label"] for x in svc.user_data["timers"]], ["Real timer"])
        self.assertFalse((self.inst.data / "state.damaged.json").exists())
        self.assertEqual([x["label"] for x in board(svc)["timers"] if x["id"].startswith("quick:")], ["Real timer"])

    def test_a_damaged_state_json_that_cannot_be_moved_aside_is_never_saved_over(self):
        """Round 2 of the mutation run: a failed move aside had no test. A folder in the copy's
        place makes the rename fail: the damaged file must stay as it is, unread, until the
        move works, and then the copy holds it."""
        bad = b'{"schema": 1, "user": {"timers": [ broken'
        self.write_state(bad)
        aside = self.inst.data / "state.damaged.json"
        taken = [aside] + [self.inst.data / ("state.damaged-%d.json" % n)
                           for n in range(2, config.MAX_DAMAGED_COPIES + 1)]
        for p in taken:                                 # every copy's name a folder with something in it
            p.mkdir()
            (p / "keep").write_bytes(b"x")
        svc = self.started(RUN_A, running=False)
        self.assertEqual((self.inst.data / "state.json").read_bytes(), bad, "never saved over")
        self.assertFalse(svc._user_loaded)
        self.assertIn("could not be moved aside", self.log_text(svc))
        for p in taken:
            (p / "keep").unlink()
            p.rmdir()
        svc._next_user_try = 0.0
        svc.tick()
        self.assertTrue(svc._user_loaded)
        self.assertEqual(aside.read_bytes(), bad)
        self.assertTrue(svc._save_state(), "saved now, as at the next 10 s save")
        self.assertIsNotNone(strict_json((self.inst.data / "state.json").read_bytes())["state"])

    def test_a_fault_while_taking_the_block_aborts_nothing_and_saves_over_nothing(self):
        self.write_state('{"schema": 1, "user": {"timers": [%s]}, "state": {}}' % json.dumps(TIMER))
        before = (self.inst.data / "state.json").read_bytes()
        self.inst.write_log(RUN_A)
        with mock.patch.object(service, "user_block_from_file", side_effect=RuntimeError("odd")):
            svc = self.make(running=False)
            svc.start_reading()
            self.drain(svc)
            self.assertGreater(svc.reader.state.session["events"], 0, "the last log is read all the same")
            self.assertFalse(svc._user_loaded)
            self.assertIsNotNone(svc.hub.latest)
            self.assertEqual((self.inst.data / "state.json").read_bytes(), before, "never saved over")
        self.assertGreaterEqual(svc.errors, 1)

    def test_timers_the_file_holds_are_removed_by_the_id_the_page_shows(self):
        self.write_state(json.dumps({"schema": 1, "user": {"timers": [timer("q1", "First"), timer("q1", "Second"),
                                                                     timer("bad id!", "Odd"), {"label": "no time"}]},
                                     "state": {}}))
        svc = self.started(RUN_A, running=False)
        shown = [x["id"] for x in board(svc)["timers"] if x["source"] == "quick"]
        self.assertEqual(len(set(shown)), 3)
        self.assertEqual(sorted("quick:" + x["id"] for x in svc.user_data["timers"]), sorted(shown), "stored as shown")
        for tid in shown:
            status, answer = svc._api_timer_remove(Req({"id": tid}))
            self.assertEqual((status, answer["removed"]), (200, True), tid)
        self.assertEqual([x for x in board(svc)["timers"] if x["source"] == "quick"], [])
        self.assertEqual(self.saved_user().get("timers"), [])
        self.assertIn("1 quick timer(s) the page could not show", self.log_text(svc))

    def test_the_block_is_bounded_and_what_is_left_out_logged_once(self):
        extra = {"k%02d" % i: i for i in range(40)}
        extra["big"] = "x" * 20000
        self.write_state(json.dumps({"schema": 1, "user": dict({"timers": [TIMER]}, **extra), "state": {}}))
        svc = self.started(RUN_A, running=False)
        self.assertEqual(sorted(k for k in svc.user_data if k not in ("timers", "view")),
                         ["k%02d" % i for i in range(config.MAX_USER_EXTRA_KEYS)])
        self.assertLess((self.inst.data / "state.json").stat().st_size, 64 * 1024, "the 20 KB key is not rewritten")
        self.assertEqual(self.log_text(svc).count("user block: left out"), 1)
        svc.close()
        self.write_state(json.dumps({"schema": 1, "user": {"one": "y" * (config.MAX_USER_EXTRA_BYTES + 1)},
                                     "state": {}}))
        again = self.started(RUN_A, running=False)
        self.assertNotIn("one", again.user_data, "a key over the size bound")

    def test_a_key_name_over_64_characters_is_left_out(self):
        """Round 2 of the mutation run: the name bound had no test."""
        block, left_out = service.user_block_from_file({"n" * 64: 1, "m" * 65: 2})
        self.assertEqual(block, {"n" * 64: 1})
        self.assertEqual(len(left_out), 1)
        self.assertIn("a key name over 64 characters", left_out[0])

    def test_adding_the_same_timer_twice_keeps_one(self):
        u = service.apply_user_op({}, ("add", TIMER))
        self.assertEqual(len(service.apply_user_op(u, ("add", TIMER))["timers"]), 1)


class Labels(FixCase):
    def test_a_label_needs_a_visible_character(self):
        """C: labels of only invisible characters were taken."""
        svc = self.started(RUN_A, running=False)
        for codes in ((0x200B, 0x200B), (0xFEFF,), (0x2060, 0x180E), (0xE0041, 0xE0042), (0x034F,), (0x00AD,),
                      (0x3000,), (0x20, 0x200D)):
            label = text_of(*codes)
            status, answer = svc._api_timer_add(Req({"label": label, "minutes": 5}))
            self.assertEqual(status, 400, ascii(label))
        for codes in ((0x200B, 0x54, 0x65, 0x61), (0xE9,), (0x37,), (0x21,), (0x2603,), (0x4E00,)):
            label = text_of(*codes)
            self.assertEqual(svc._api_timer_add(Req({"label": label, "minutes": 5}))[0], 200, ascii(label))


class UnmappedFile(FixCase):
    """J: unmapped.json was saved over after its one read had failed."""

    def test_never_saved_over_unread_and_merged_once_readable(self):
        um = self.inst.data / "unmapped.json"
        um.mkdir(parents=True)                     # cannot be opened as a file
        svc = self.started(lib.sample_bytes("built_unknown.log"), running=False)
        self.assertTrue(um.is_dir(), "never saved over")
        self.assertTrue(svc._unmapped_dirty, "the new entries wait in memory")
        um.rmdir()
        service.write_json(um, {"schema": 1, "contracts": {},
                                "locations": {"Earlier_Code": {"first_seen": "2026-01-01T00:00:00.000Z",
                                                               "session": "earlier"}}})
        svc._next_unmapped_try = 0.0
        svc.tick()
        data = strict_json(um.read_bytes())
        self.assertEqual(data["locations"]["Earlier_Code"]["first_seen"], "2026-01-01T00:00:00.000Z")
        self.assertIn("A Very Unusual Job", [e["title"] for e in data["contracts"].values()])
        self.assertFalse(svc._unmapped_dirty)

    def test_a_read_that_fails_once_is_not_followed_by_a_write(self):
        """Round 2 of the mutation run: in the test above the write fails too (a folder), so a
        write after a failed read went unseen. As in the review (finding J), the file is held at
        the read and free again at the write: nothing may be written before it has been read."""
        um = self.inst.data / "unmapped.json"
        self.inst.data.mkdir(parents=True, exist_ok=True)
        earlier = {"schema": 1, "contracts": {},
                   "locations": {"Earlier_Code": {"first_seen": "2026-01-01T00:00:00.000Z", "session": "earlier"}}}
        service.write_json(um, earlier)
        real = Service._read_data_file
        held = {"n": 0}

        def read(svc_self, path):
            if path.name == "unmapped.json" and held["n"] == 0:
                held["n"] += 1
                return service._UNREADABLE                # held without sharing at this one look
            return real(svc_self, path)
        with mock.patch.object(Service, "_read_data_file", read):
            svc = self.started(lib.sample_bytes("built_unknown.log"), running=False)
            svc._next_unmapped_try = 0.0
            svc.tick()                                    # the retry reads it and merges (if not done already)
        self.assertEqual(held["n"], 1, "the first look found it held")
        self.assertFalse(svc._unmapped_dirty)
        data = strict_json(um.read_bytes())
        self.assertIn("Earlier_Code", data["locations"], "the earlier session's entry is kept")
        self.assertIn("A Very Unusual Job", [e["title"] for e in data["contracts"].values()])

    def test_a_byte_order_mark_is_not_damage(self):
        um = self.inst.data / "unmapped.json"
        self.inst.data.mkdir(parents=True, exist_ok=True)
        um.write_bytes(b"\xef\xbb\xbf" + json.dumps({"schema": 1, "contracts": {}, "locations": {
            "Earlier_Code": {"first_seen": "2026-01-01T00:00:00.000Z", "session": "earlier"}}}).encode())
        self.started(lib.sample_bytes("built_unknown.log"), running=False)
        self.assertFalse((self.inst.data / "unmapped.damaged.json").exists())
        self.assertIn("Earlier_Code", strict_json(um.read_bytes())["locations"], "merged, not moved aside")

    def test_a_damaged_file_is_moved_aside(self):
        self.inst.data.mkdir(parents=True, exist_ok=True)
        (self.inst.data / "unmapped.json").write_bytes(b"not json")
        self.started(lib.sample_bytes("built_unknown.log"), running=False)
        self.assertEqual((self.inst.data / "unmapped.damaged.json").read_bytes(), b"not json")
        self.assertTrue(strict_json((self.inst.data / "unmapped.json").read_bytes())["contracts"])

    def test_locations_are_bounded(self):
        svc = self.started(lib.sample_bytes("built_unknown.log"), running=False)
        with mock.patch.object(config, "MAX_UNMAPPED", 3):
            state = json.loads(svc.hub.latest)["state"]
            for i in range(6):
                state["session"]["last_event"] = "2030-01-01T00:00:0%d.000Z" % i
                state["unmapped"] = ["Code_%d" % i]
                svc._note_unmapped(state, {"unmapped_contracts": []})
        um = strict_json((self.inst.data / "unmapped.json").read_bytes())
        self.assertEqual(sorted(um["locations"]), ["Code_3", "Code_4", "Code_5"])

    def test_texts_are_cleaned_and_go_through_the_name_scrubber_when_written(self):
        svc = self.started(lib.sample_bytes("built_unknown.log"), running=False)
        state = json.loads(svc.hub.latest)["state"]
        esc, rlo = chr(0x1B), chr(0x202E)

        def scrubber(obj):                          # stands in for the state's: hides one name, cleans nothing
            return json.loads(json.dumps(obj).replace("SecretHandle", "another player"))
        with mock.patch.object(svc.reader.state, "scrub", side_effect=scrubber):
            svc._note_unmapped(state, {"unmapped_contracts": [
                {"contract": "C1", "generator": None, "title": "Hunt SecretHandle " + esc + "[31m" + rlo}]})
        um = strict_json((self.inst.data / "unmapped.json").read_bytes())
        title = next(e["title"] for e in um["contracts"].values() if e["contract"] == "C1")
        self.assertEqual(title, "Hunt another player [31m")


class StopAndChanges(FixCase):
    """F: the last save ran without the lock and could overwrite a change already answered 200."""

    def test_a_change_after_the_stop_is_asked_for_gets_503(self):
        svc = self.started(RUN_A, running=False)
        svc.request_stop()
        for fn, body in ((svc._api_timer_add, {"label": "x", "minutes": 5}), (svc._api_view, {"view": "mining"}),
                         (svc._api_live, {}), (svc._api_timer_remove, {"id": "quick:q1"})):
            self.assertEqual(fn(Req(body)), (503, {"error": "shutting down"}))
        self.assertEqual(svc.user_data, {})

    def test_a_change_holding_the_lock_at_the_stop_is_answered_and_saved(self):
        self.inst.write_log(RUN_A)
        svc = self.make(running=False, process_check_seconds=10.0)
        inside, go = threading.Event(), threading.Event()
        real = service.boardlib.add_quick_timer

        def held(*a, **kw):
            inside.set()
            go.wait(10)
            return real(*a, **kw)
        t, out = run_in_thread(svc)
        res = {}
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            port, token = run["port"], run["token"]
            self.assertTrue(h.wait_until(lambda: answers(port), 5))
            with mock.patch.object(service.boardlib, "add_quick_timer", side_effect=held):
                w = threading.Thread(target=lambda: res.setdefault(
                    "change", post(port, token, "/api/timers/add", {"label": "at the stop", "minutes": 5})))
                w.start()
                self.assertTrue(inside.wait(5), "the change holds the lock")
                s = threading.Thread(target=lambda: res.setdefault(
                    "stop", post(port, token, "/api/shutdown", {"reason": "test"})))
                s.start()
                self.assertTrue(h.wait_until(lambda: svc._closing, 5))
                time.sleep(0.3)                         # the last save is waiting for the lock now
                go.set()
                w.join(15)
                s.join(15)
        finally:
            go.set()
            svc.request_stop()
            t.join(15)
        self.assertEqual(res["change"][0], 200, res["change"][2][:200])
        self.assertEqual(res["stop"][0], 200)
        self.assertEqual(out.get("code"), service.EXIT_OK)
        self.assertIn("at the stop", [x["label"] for x in self.saved_user()["timers"]], "answered 200: on disk")

    def test_the_last_save_waits_for_a_change_made_while_saves_were_failing(self):
        """Round 2 of the mutation run: the test above passes without the last save's lock,
        because that change saves itself. A change made while saves are failing does not (only
        the loop retries), so the last save is the one that writes it: it must wait for the
        change and take its snapshot after it, or the change is answered 200 and lost."""
        svc = self.started(RUN_A, running=False)
        self.assertFalse(svc._unsaved)
        svc._save_failing = True                      # the last save failed; the disk works again
        inside, go = threading.Event(), threading.Event()
        real = service.boardlib.add_quick_timer

        def held(*a, **kw):
            inside.set()
            go.wait(10)
            return real(*a, **kw)
        res = {}
        with mock.patch.object(service.boardlib, "add_quick_timer", side_effect=held):
            w = threading.Thread(target=lambda: res.setdefault(
                "change", svc._api_timer_add(Req({"label": "while failing", "minutes": 5}))))
            w.start()
            self.assertTrue(inside.wait(5), "the change holds the lock")
            s = threading.Thread(target=svc._last_save_at_stop)
            s.start()
            time.sleep(0.3)
            self.assertTrue(s.is_alive(), "the last save waits for the change")
            go.set()
            w.join(10)
            s.join(10)
        self.assertEqual(res["change"][0], 200)
        self.assertEqual([x["label"] for x in self.saved_user()["timers"]], ["while failing"])

    def test_the_last_save_gives_up_on_a_lock_held_too_long(self):
        svc = self.started(RUN_A, running=False)
        held, release = threading.Event(), threading.Event()

        def holder():
            with svc._lock:
                held.set()
                release.wait(10)
        th = threading.Thread(target=holder)
        th.start()
        try:
            self.assertTrue(held.wait(5))
            with mock.patch.object(config, "SHUTDOWN_LOCK_SECONDS", 0.3):
                t0 = time.monotonic()
                svc._last_save_at_stop()
                took = time.monotonic() - t0
        finally:
            release.set()
            th.join(5)
        self.assertGreaterEqual(took, 0.25)
        self.assertLess(took, 5)
        self.assertIn("the last save is skipped", self.log_text(svc))

    def test_a_write_that_never_returns_does_not_hang_the_stop(self):
        """The review's second round: the last save waited on the write in flight without a
        bound. A write of state.json that never returns: the stop goes on after its bound."""
        svc = self.started(RUN_A, running=False)
        svc._change_user(("add", timer("q5", "unsaved")))
        svc._unsaved = True
        never = threading.Event()
        real = service.write_json

        def stuck(path, obj, indent=1):
            if path.name == "state.json":
                never.wait(20)
            return real(path, obj, indent)
        try:
            with mock.patch.object(service, "write_json", side_effect=stuck), \
                    mock.patch.object(config, "SHUTDOWN_SAVE_SECONDS", 0.3):
                s = threading.Thread(target=svc._last_save_at_stop)
                t0 = time.monotonic()
                s.start()
                s.join(5)
                alive, took = s.is_alive(), time.monotonic() - t0
        finally:
            never.set()
            h.wait_until(lambda: svc._written_seq >= svc._snap_seq, 5)   # the left-over write ends before cleanup
        self.assertFalse(alive, "the stop did not hang")
        self.assertGreaterEqual(took, 0.25)
        self.assertIn("the last save did not end in", self.log_text(svc))

    def test_the_last_save_writes_what_the_loop_had_not_saved_yet(self):
        """The save at shutdown happens: what the loop read since its last 10 s save is on disk."""
        svc = self.started(MINING_CUT, running=True)
        before = service.read_json(svc.paths.state)["state"]["session"]["events"]
        self.inst.write_log(RUN_A[len(MINING_CUT):], "ab")
        svc._last_save = svc.mono()                      # the 10 s save is not due on this turn
        svc.tick()
        now = svc.reader.state.session["events"]
        self.assertGreater(now, before)
        self.assertEqual(service.read_json(svc.paths.state)["state"]["session"]["events"], before, "not saved yet")
        svc._last_save_at_stop()
        self.assertEqual(service.read_json(svc.paths.state)["state"]["session"]["events"], now)


class SlowDisk(FixCase):
    """E: every change saved state.json under the lock, so a slow disk stalled the loop and other
    changes waited past 5 s for a 503."""

    def test_a_slow_save_holds_no_lock_and_changes_share_a_write(self):
        svc = self.started(RUN_A, running=False)
        real = service.write_json
        writes = []

        def slow(path, obj, indent=1):
            if path.name == "state.json":
                writes.append(time.monotonic())
                time.sleep(0.6)
            return real(path, obj, indent)
        res = []
        with mock.patch.object(service, "write_json", side_effect=slow):
            ths = [threading.Thread(target=lambda i=i: res.append(
                (svc._api_timer_add(Req({"label": "t%d" % i, "minutes": 5}))[0], time.monotonic()))) for i in range(5)]
            t0 = time.monotonic()
            for x in ths:
                x.start()
            time.sleep(0.2)
            self.assertTrue(svc._lock.acquire(timeout=0.2), "no write holds the lock: the loop can turn")
            svc._lock.release()
            for x in ths:
                x.join(10)
        self.assertEqual(sorted(s for s, _ in res), [200] * 5)
        self.assertLessEqual(len(writes), 3, "changes made together share writes (%d)" % len(writes))
        self.assertLess(max(t for _, t in res) - t0, 2.5, "no change waited for every other change's write")
        self.assertEqual(sorted(x["label"] for x in self.saved_user()["timers"]), ["t%d" % i for i in range(5)])

    def test_the_loops_own_slow_save_holds_no_lock(self):
        """Round 2 of the mutation run: only the changes' saves were tested. The loop's turn
        takes its snapshot under the lock and writes it after: a change meanwhile is not held up."""
        svc = self.started(MINING_CUT, running=True)
        self.inst.write_log(RUN_A[len(MINING_CUT):], "ab")
        svc._last_save = svc.mono() - 1e6                # the 10 s save is due on this turn
        real = service.write_json
        writing = threading.Event()

        def slow(path, obj, indent=1):
            if path.name == "state.json":
                writing.set()
                time.sleep(0.8)
            return real(path, obj, indent)
        with mock.patch.object(service, "write_json", side_effect=slow):
            t = threading.Thread(target=svc.tick)
            t.start()
            self.assertTrue(writing.wait(5), "the turn saves")
            got = svc._lock.acquire(timeout=0.3)
            if got:
                svc._lock.release()
            t.join(10)
        self.assertTrue(got, "the loop's write is made outside the lock")
        self.assertEqual(service.read_json(svc.paths.state)["state"]["session"]["events"],
                         svc.reader.state.session["events"], "and it is on disk")

    def test_an_older_snapshot_is_never_written_after_a_newer_one(self):
        svc = self.started(RUN_A, running=False)
        with svc._lock:
            svc._change_user(("add", timer("q7", "older")))
            svc._publish(svc._flags(svc.clock.now()), svc.clock.now())
            older = svc._take_snapshot()
            svc._change_user(("add", timer("q8", "newer")))
            svc._unsaved = True
            newer = svc._take_snapshot()
        self.assertTrue(svc._write_snapshot(newer))
        self.assertTrue(svc._write_snapshot(older), "already on disk: nothing written")
        self.assertEqual([x["label"] for x in self.saved_user()["timers"]], ["older", "newer"])


class FirstRead(FixCase):
    """G: a change made before the first read published a board built on an empty state."""

    CHANGES = (("_api_timer_add", {"label": "x", "minutes": 5}), ("_api_view", {"view": "cargo"}),
               ("_api_live", {}), ("_api_timer_remove", {"id": "quick:q1"}))

    def test_no_change_before_the_first_read(self):
        self.inst.write_log(MINING_CUT)
        svc = self.make(running=True)
        for name, body in self.CHANGES:             # the server answers before start_reading even ran
            self.assertEqual(getattr(svc, name)(Req(body))[0], 503, name)
        svc.start_reading()
        for name, body in self.CHANGES:
            self.assertEqual(getattr(svc, name)(Req(body))[0], 503, name)
        self.assertIsNone(svc.hub.latest, "nothing was published")
        self.assertEqual(svc.user_data, {})
        self.drain(svc)
        for name, body in self.CHANGES:
            self.assertEqual(getattr(svc, name)(Req(body))[0], 200, name)

    def test_a_last_log_that_cannot_be_read_does_not_lock_the_page_out(self):
        """Round 2 of the mutation run: no game, and the last log's read fails at the start and
        again on the next turn. The first read then counts as done: changes are taken, or the
        page could change nothing for as long as the log stays unreadable."""
        self.inst.write_log(MINING_CUT)
        svc = self.make(running=False)
        with mock.patch.object(svc, "_read_to_end", side_effect=OSError("held")):
            with self.assertRaises(OSError):
                svc.start_reading()
            self.assertEqual(svc._api_timer_add(Req({"label": "x", "minutes": 5}))[0], 503,
                             "the retry on the next turn comes first")
            with self.assertRaises(OSError):
                svc.tick()
        status, answer = svc._api_timer_add(Req({"label": "after", "minutes": 5}))
        self.assertEqual(status, 200, answer)
        self.assertEqual([x["label"] for x in self.saved_user()["timers"]], ["after"])

    def test_a_turn_that_raises_after_the_read_does_not_lock_the_page_out(self):
        """The review's second round: the read reaches the end, then a later step of the turn
        raises on every turn (`_flags` here). The first read is done all the same."""
        self.inst.write_log(MINING_CUT)
        svc = self.make(running=True)
        svc.start_reading()
        with mock.patch.object(svc, "_flags", side_effect=RuntimeError("a later step")):
            for _ in range(3):
                with self.assertRaises(RuntimeError):
                    svc.tick()
            self.assertTrue(svc._first_read_done)
            status, answer = svc._api_timer_add(Req({"label": "taken", "minutes": 5}))
        self.assertEqual(status, 200, answer)
        self.assertEqual(svc.user_data["timers"][-1]["label"], "taken")


class FailedBoards(FixCase):
    """H: a payload json could not write sent nothing at all. And the guards the mutation run found
    untested: the minute's retry of a failed board, and the fallback board's shape."""

    def test_a_payload_json_cannot_write_becomes_the_fallback_board(self):
        self.inst.write_log(RUN_A)
        real = service.boardlib.build

        def odd(*a, **kw):
            p = real(*a, **kw)
            p["alerts"] = [{"id": {1, 2}}]          # a set: json cannot write it
            return p
        with mock.patch.object(service.boardlib, "build", side_effect=odd):
            svc = self.make(running=False)
            svc.start_reading()
        b = board(svc)
        self.assertEqual((b["problems"], b["view"]["rule"]), (["service: TypeError"], "error"))
        self.assertAlmostEqual(svc._board_next_ms / 1000.0, svc.clock.now() + 60, delta=1)
        self.assertEqual(svc._api_timer_add(Req({"label": "x", "minutes": 5}))[0], 200)
        self.assertEqual(board(svc)["problems"], [], "built again with the next input change")

    def test_a_failed_board_is_built_again_a_minute_later_and_not_before(self):
        self.inst.write_log(RUN_A)
        clock = Clock(time.time())
        with mock.patch.object(service.boardlib, "build", side_effect=RuntimeError("broken")):
            svc = self.make(running=False, clock=clock, process_check_seconds=10.0)
            svc.start_reading()
            self.assertEqual(svc._board_next_ms, int(round((clock.t + 60) * 1000)))
            builds = svc.board_builds
            clock.t += 30
            svc.tick()
            self.assertEqual(svc.board_builds, builds, "not before the minute")
        clock.t += 31
        svc.tick()
        self.assertEqual(svc.board_builds, builds + 1)
        self.assertEqual(board(svc)["problems"], [])

    def test_the_fallback_board_has_the_keys_of_any_other(self):
        svc = self.started(RUN_A, running=False)
        normal = board(svc)
        fb = service.fallback_board(svc.plans, RuntimeError("x"))
        self.assertEqual(sorted(fb), sorted(normal))
        for k in ("view", "plan"):
            self.assertEqual(sorted(fb[k]), sorted(normal[k]), k)
        for k in ("alerts", "timers", "unmapped_contracts", "problems"):
            self.assertIsInstance(fb[k], list, k)

    def test_problem_sets_logged_are_bounded(self):
        svc = self.started(RUN_A, running=False)
        with mock.patch.object(config, "MAX_PROBLEM_SETS", 2):
            for i in range(5):
                svc._log_problems(["p%d" % i])
        log = self.log_text(svc)
        self.assertEqual(log.count("the board left parts out"), 2)
        self.assertEqual(log.count("different sets of problems"), 1)


class LockAndCatchUp(FixCase):
    """The mutation run: the lock could be removed from the changes, or its timeout, and a change
    during a catch-up could publish, and no test failed."""

    def test_a_change_waits_for_the_lock_and_gives_up_after_its_timeout(self):
        svc = self.started(RUN_A, running=False)
        held, release = threading.Event(), threading.Event()

        def holder():
            with svc._lock:
                held.set()
                release.wait(10)
        th = threading.Thread(target=holder)
        th.start()
        self.assertTrue(held.wait(5))
        res = {}
        with mock.patch.object(config, "CHANGE_LOCK_SECONDS", 0.3):
            t0 = time.monotonic()
            w = threading.Thread(target=lambda: res.setdefault(
                "r", (svc._api_timer_add(Req({"label": "x", "minutes": 5})), time.monotonic())))
            w.start()
            w.join(3)
            alive = w.is_alive()
        release.set()
        th.join(5)
        w.join(5)
        self.assertFalse(alive, "it gave up after its timeout")
        (status, answer), t1 = res["r"]
        self.assertEqual(status, 503, "it waited for the lock")
        self.assertGreaterEqual(t1 - t0, 0.25)
        self.assertNotIn("timers", svc.user_data)

    def test_a_change_during_a_catch_up_publishes_nothing_half_read(self):
        self.inst.write_log(MINING_CUT)
        svc = self.make(running=True)
        svc.mono = Mono(1000.0)
        svc.start_reading()
        self.drain(svc)
        with mock.patch.object(config, "READ_BUDGET", 2048):
            self.inst.write_log(RUN_A[len(MINING_CUT):], "ab")
            self.assertTrue(svc.tick(), "catching up")
            published, latest = svc.publishes, svc.hub.latest
            self.assertEqual(svc._api_timer_add(Req({"label": "during", "minutes": 5}))[0], 200)
            self.assertEqual((svc.publishes, svc.hub.latest), (published, latest), "nothing half-read went out")
            self.drain(svc, 400)
        self.assertIn("during", svc.hub.latest)
        self.assertEqual([x["label"] for x in self.saved_user()["timers"]], ["during"])

    def test_no_pick_during_a_catch_up_after_the_first_read(self):
        """Round 2 of the mutation run: with the first-read gate in front, the old catch-up test
        no longer reached the pick's own check. After the first read a large piece of log (a flood
        mid-session) makes a catch-up again: a pick then is refused with its own reason, other
        changes are taken, and the pick is taken once caught up."""
        self.inst.write_log(MINING_CUT)
        svc = self.make(running=True)
        svc.mono = Mono(1000.0)
        svc.start_reading()
        self.drain(svc)
        self.assertTrue(svc._first_read_done)
        with mock.patch.object(config, "READ_BUDGET", 2048):
            self.inst.write_log(RUN_A[len(MINING_CUT):], "ab")
            self.assertTrue(svc.tick(), "catching up")
            self.assertEqual(svc._api_view(Req({"view": "travel"})),
                             (503, {"error": "still reading the log: pick again in a moment"}))
            self.assertIsNone(svc.user_data.get("view"))
            self.assertEqual(svc._api_timer_add(Req({"label": "taken", "minutes": 5}))[0], 200)
            self.drain(svc, 400)
        status, answer = svc._api_view(Req({"view": "travel"}))
        self.assertEqual(status, 200)
        self.assertTrue(answer["view"]["picked"])

    def test_a_saved_pick_is_not_dropped_on_a_half_read_state_after_a_restart(self):
        svc = self.started(MINING_CUT)
        self.assertEqual(svc._api_view(Req({"view": "refinery"}))[0], 200)
        svc.close()
        with mock.patch.object(config, "READ_BUDGET", 1024):
            again = self.make(running=True)
            again.mono = Mono(5000.0)
            again.start_reading()
            half_read = 0
            while True:
                again.mono.t += config.CATCH_UP_PUBLISH_SECONDS     # a half-read message each turn
                busy = again.tick()
                half_read += busy
                if not busy:
                    break
        self.assertGreater(half_read, 3)
        b = board(again)
        self.assertEqual((b["view"]["name"], b["view"]["picked"]), ("refinery", True))
        self.assertNotIn("dropped", self.log_text(again))

    def test_live_while_state_json_is_unread_drops_the_file_pick_later(self):
        self.inst.write_log(RUN_A)
        folder = self.inst.data / "state.json"
        folder.mkdir(parents=True)
        svc = self.make(running=False, state_save_seconds=2.0)
        svc.start_reading()
        self.assertFalse(svc._user_loaded)
        self.assertEqual(svc._api_live(Req({})), (200, {"ok": True, "had_pick": False,
                                                       "view": {"name": "idle", "auto": "idle", "picked": False}}))
        folder.rmdir()
        # The reference pick, which no change of context drops (round 2 of the mutation run: a
        # mining pick was dropped by its context anyway, so the test passed with the op unrecorded).
        service.write_json(folder, {"schema": 1, "state": {},
                                    "user": {"view": {"view": "reference", "context": "reference", "at": None}}})
        svc._next_user_try = 0.0
        svc.tick()
        self.assertTrue(svc._user_loaded)
        self.assertNotIn("view", svc.user_data, "Live was asked for: the file's pick goes")
        self.assertNotIn("view", self.saved_user())
        self.assertNotEqual(board(svc)["view"]["name"], "reference")

    def test_changes_kept_for_an_unread_file_are_bounded(self):
        self.inst.write_log(RUN_A)
        (self.inst.data / "state.json").mkdir(parents=True)
        svc = self.make(running=False)
        svc.start_reading()
        with mock.patch.object(config, "MAX_USER_OPS", 3):
            for i in range(5):
                self.assertEqual(svc._api_timer_add(Req({"label": "t%d" % i, "minutes": 5}))[0], 200)
        self.assertEqual([op[1]["label"] for op in svc._user_ops], ["t2", "t3", "t4"])


class LoopTurns(FixCase):
    """I: every change ran a whole loop turn, with a poll of the log while the game runs."""

    def test_a_change_runs_no_turn_of_the_loop(self):
        self.inst.write_log(RUN_A)
        svc = self.make(running=True, process_check_seconds=10.0, poll_seconds=1.0)
        turns = []
        real = svc.tick

        def counted():
            turns.append(time.monotonic())
            return real()
        svc.tick = counted
        t, out = run_in_thread(svc)
        try:
            run = h.wait_until(lambda: service.read_json(svc.paths.run), 10)
            port, token = run["port"], run["token"]
            self.assertTrue(h.wait_until(lambda: answers(port), 5))
            n0, t0 = len(turns), time.monotonic()
            for i in range(40):
                self.assertEqual(post(port, token, "/api/timers/add", {"label": "t%d" % i, "minutes": 5})[0], 200)
            dt = time.monotonic() - t0
            n = len(turns) - n0
        finally:
            svc.request_stop()
            t.join(15)
        self.assertLessEqual(n, dt + 2, "%d turns in %.1f s for 40 changes: about one a second" % (n, dt))


class StatusPrivacy(FixCase):
    def test_status_shows_no_profile_folder_and_counts_withheld_notices(self):
        svc = self.started(RUN_A, running=False)
        home = os.path.normcase(os.path.normpath(os.environ.get("USERPROFILE") or os.path.expanduser("~")))
        st = svc.status()
        self.assertNotIn(home, os.path.normcase(json.dumps(st).replace("\\\\", "\\")))
        if os.path.normcase(sys.executable).startswith(home):
            self.assertTrue(st["python"].startswith("%USERPROFILE%"), st["python"])
        self.assertEqual(service.shown_path(os.path.join(home, "x", "y.exe")), os.path.join("%USERPROFILE%", "x", "y.exe"))
        self.assertEqual(service.shown_path(os.path.join(home + "x", "y")), os.path.join(home + "x", "y"),
                         "only the folder itself, not a name that starts like it")
        self.assertIn("withheld", st["session"])
        self.assertEqual(st["session"]["withheld_tips"], 0)       # the tip-shaped ones (round 5)


if __name__ == "__main__":
    unittest.main()
