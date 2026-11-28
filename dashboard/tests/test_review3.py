"""The faults the stage 3 review found, one test each (the review's numbers in the names), and
the reference view. Every built line here is invented and its shape unverified, as in
SURVEY.md: the tests say so in their names where they lean on such a shape."""
import json
import os
import re
import time
import unittest
from datetime import timedelta, timezone
from unittest import mock

import scdash_testlib as lib
from scdash import board, law, pipeline, timeline
from scdash import events as E
from scdash import plan as P
from scdash import state as S
from scdash.state import MAX_OTHERS, OTHER_PLAYER as OTHER, State
from scdash.words import clean_text, parse_time

NAMES = timeline.load_names()
PST = timezone(timedelta(hours=-8), "PST")
FIRST = '<2026-11-28T07:00:00.000Z> BackupNameAttachment=" Build(1) 27 Nov 26 (23 00 00)"  -- used by backup system'
HEAD = ["[Notice] <AccountLoginCharacterStatus_Character> Character: createdAt 1 - updatedAt 2 - geid 900000000003 - accountId 1000001 - name Pilot_Example - state STATE_CURRENT [Team_GameServices][Login]",
        "[Notice] <Legacy login response> [CIG-net] User Login Success - Handle[Pilot_Example] - Time[4] [Team_GameServices][Login]",
        '[CSessionManager::RequestFrontEnd] Started - RequestFrontEndReason="ProcessBootRequest"!',
        "[CSessionManager::OnClientSpawned] Spawned!",
        "[Notice] <Join PU> address[192.0.2.1] port[1] shard[pub_example_00000000_001] locationId[5] [Team_GameServices][GIM][Matchmaking]",
        "[CSessionManager::ConnectCmd] Connect started!",
        "[CSessionManager::OnClientSpawned] Spawned!"]
ZERO = "00000000-0000-0000-0000-000000000000"
RLO, RLM = chr(0x202E), chr(0x200F)            # bidi controls, built here (not typed into the file)


def notice(text, mid=ZERO, oid=""):
    return ('[Notice] <SHUDEvent_OnNotification> Added notification "%s: " [1] to queue. New queue size: 1, '
            'MissionId: [%s], ObjectiveId: [%s] [Team_CoreGameplayFeatures][Missions][Comms]' % (text, mid, oid))


class Lines:
    """A log built line by line, one second apart, read with the real reader."""

    def __init__(self, head=True):
        self.t = parse_time("2026-11-28T07:00:00Z")
        self.lines = [FIRST]
        for x in (HEAD if head else []):
            self.add(x)

    def add(self, body, step=1.0):
        """One record; a line break in it makes continuation pieces with the same time, as the
        game writes a notice whose text holds one."""
        self.t += step
        ms = int(round((self.t % 1) * 1000)) % 1000
        from datetime import datetime
        stamp = "<%s.%03dZ>" % (datetime.fromtimestamp(int(self.t), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), ms)
        for piece in body.split("\n"):
            self.lines.append("%s %s" % (stamp, piece))
        return self

    def read(self):
        mem = lib.MemoryLog(("\r\n".join(self.lines) + "\r\n").encode("utf-8"))
        r = pipeline.LogReader("Game.log", NAMES, opener=mem.opener, keep_events=True)
        while r.poll() == "read":
            pass
        r.finish()
        return r


def everything(r, plan=None, user=None):
    """Every public output there is for this reader: payloads of every view, the state, the
    summary, the timeline's text and JSON."""
    st = r.state
    now = (st.session["last_t"] or 1.8e9) + 5
    out = [json.dumps(board.build(st, plan, user, now), ensure_ascii=False)]
    for v in P.VIEWS:
        out.append(json.dumps(board.build(st, plan, {"view": board.pick(st, plan, v, True, now)}, now), ensure_ascii=False))
    sm = r.summary(complete=True)
    out += [json.dumps(st.to_dict(), ensure_ascii=False), json.dumps(sm, ensure_ascii=False),
            timeline.render_text(r, sm), timeline.dumps(timeline.render_json(r, sm, show_all=True))]
    return "\n".join(out)


class PlanLoaderTest(unittest.TestCase):
    """Review 3: the plan loader never raises, and a file held open a moment is read later."""

    def test_huge_numbers_and_wrong_types(self):
        plan, skipped = P.normalize({"objectives": [{"title": "x", "materials": [{"name": "n", "need_scu": 10 ** 400}]}],
                                     "runs": [{"name": "r", "legs": [{"to": "x", "gm": 10 ** 330}]}],
                                     "current_run": [1, 2]})
        self.assertIsNone(plan["objectives"][0]["materials"][0]["need_scu"])
        self.assertIsNone(plan["runs"][0]["legs"][0]["gm"])
        self.assertIsNone(plan["current_run"])
        self.assertIsNone(P.normalize({"current_run": {"a": 1}})[0]["current_run"])

    def test_a_file_held_open_is_read_once_it_is_free(self):
        with lib.TempDir() as d:
            path = d / "plan.json"
            lib.write(path, json.dumps({"notes": ["old"]}).encode())
            store = P.PlanStore(path)
            store.refresh()
            lib.write(path, json.dumps({"notes": ["new"]}).encode())
            os.utime(path, ns=(1, 2))
            real_open = open

            def held(p, *a, **k):
                if str(p) == str(path):
                    raise PermissionError("held by its writer")
                return real_open(p, *a, **k)
            with mock.patch("builtins.open", held):
                self.assertTrue(store.refresh())
            self.assertIn("cannot be read now", store.notice)
            self.assertEqual(store.plan["notes"], ["old"])
            self.assertTrue(store.refresh())                  # the file has not changed since
            self.assertEqual(store.plan["notes"], ["new"])
            self.assertIsNone(store.notice)

    def test_a_shape_nobody_thought_of_is_a_notice_not_a_raise(self):
        with lib.TempDir() as d:
            path = d / "plan.json"
            lib.write(path, b'{"notes": ["x"]}')
            store = P.PlanStore(path)
            with mock.patch("scdash.plan.normalize", side_effect=OverflowError("boom")):
                store.refresh()
            self.assertIn("could not be read into a plan (OverflowError)", store.notice)
            self.assertFalse(store.refresh())                 # judged: not reread until it changes


class StaleTargetTest(unittest.TestCase):
    """Review 4: an open quantum target ends when the user leaves the world."""

    def target(self):
        return Lines().add(notice("You have joined channel 'Drake Golem : Pilot_Example'.")).add(
            "[Notice] <Player Selected Quantum Target - Local> [ItemNavigation][CL][1] | NOT AUTH | DRAK_Golem_900000000010[900000000010]|"
            "CSCItemNavigation::OnPlayerSelectedQuantumTarget|Player has selected point LOC_RR_S2_L5 as their destination, routing locally [Team_CGP4][QuantumTravel]")

    def test_menu_and_rejoin_close_the_target(self):
        g = self.target()
        g.add('[Notice] <Channel Disconnected> cause=30016 reason="Player requested disconnect" [Team_Network]')
        g.add("[CSessionManager::OnClientSpawned] Spawned!").add(HEAD[4]).add(HEAD[5]).add(HEAD[6])
        r = g.read()
        p = board.build(r.state, None, None, r.state.session["last_t"] + 1)
        self.assertNotEqual(p["view"]["name"], "travel")
        self.assertEqual(r.state.quantum["closed_by"], "left the server")

    def test_a_respawn_and_a_new_server_close_it_too(self):
        r = self.target().add(notice("Incapacitated: x")).add("[CSessionManager::OnClientSpawned] Spawned!").read()
        self.assertEqual(r.state.quantum["closed_by"], "respawned")
        r = self.target().add(HEAD[4]).read()
        self.assertEqual(r.state.quantum["closed_by"], "joined a server")


class NamesPrivacyTest(unittest.TestCase):
    """Review 5: names around the law notices do not leak, whatever is inside or around them."""

    def test_names_with_bidi_or_control_characters_unverified_shape(self):
        for name, plain in (("Evil%sAttA" % RLO, "EvilAttA"), ("Evil%sAttB" % RLM, "EvilAttB"), ("Evil\x85AttC", "EvilAttC")):
            r = Lines().add(notice("%s committed Assault against you" % name)).read()
            self.assertNotIn(plain, everything(r), plain)
        r = Lines().add(notice("Crime Committed: Assault\nagainst Vic%stimE" % RLO)).read()
        self.assertNotIn("VictimE", everything(r))
        killer = "Kil%sler_Z" % RLO
        r = Lines().add("[Notice] <Vehicle Destroyed> Vehicle 'AEGS_Gladius_9001' [9001] class 'AEGS_Gladius' (owner player [77], "
                        "driver [0]) destroyed: reason [Combat] level [0] -> [2] flags [1] killer '%s' [88] authority [0] [Team_X]" % killer).read()
        self.assertNotIn("Killer_Z", everything(r))

    def test_loose_shapes_unverified_shape(self):
        r = Lines().add(notice("Evil_AttF committed Assault against you.")).add(
            notice("Crime Committed: Assault\nagainst Evil_VicG (Civilian)")).read()
        out = everything(r)
        self.assertNotIn("Evil_AttF", out)
        self.assertNotIn("Evil_VicG", out)
        self.assertIn("crime_against_you", [e.kind for e in r.events])

    def test_a_law_notice_we_cannot_read_is_not_shown_unverified_shape(self):
        r = Lines().add(notice("Evil_AttH committed Assault")).add(notice("Evil_AttH is near")).read()
        out = everything(r)
        self.assertNotIn("Evil_AttH", out)
        self.assertIn(E.REDACTED, out)


class HandPickTest(unittest.TestCase):
    """Review 6: a hand pick survives walking inside one place and a long context."""

    def test_walking_inside_a_place_keeps_the_pick(self):
        g = Lines().add("[Notice] <Update Inventory Location> Player [Pilot_Example] is changing location. Landing [0] -> [6]. "
                        "Location [0] -> [6]. Pending [0] [Team_X]").add(
            "[Notice] <RequestLocationInventory> Player[Pilot_Example] requested inventory for Location[RR_ARC_L1] [Team_X]")
        r = g.read()
        pk = board.pick(r.state, None, "refinery", True, r.state.session["last_t"])
        g.add("[Notice] <Update Inventory Location> Player [Pilot_Example] is changing location. Landing [6] -> [6]. "
              "Location [6] -> [99]. Pending [0] [Team_X]")
        g.add("[Notice] <RequestLocationInventory> Player[Pilot_Example] requested inventory for Location[RR_ARC_L1] [Team_X]")
        r = g.read()
        p = board.build(r.state, None, {"view": pk}, r.state.session["last_t"] + 1)
        self.assertEqual((p["view"]["name"], p["view"]["picked"], p["view"]["pick_dropped"]), ("refinery", True, False))

    def test_a_long_context_still_sticks(self):
        r = Lines().add(notice("Contract Accepted:  " + "Long title " * 30)).read()
        now = r.state.session["last_t"] + 1
        pk = board.pick(r.state, None, "combat", True, now)
        self.assertLessEqual(len(pk["context"]), 200)
        p = board.build(r.state, None, {"view": pk}, now)
        self.assertEqual((p["view"]["name"], p["view"]["picked"]), ("combat", True))


class NextChangeTest(unittest.TestCase):
    """Review 7: the payload changes with `now` only where next_change_ms says."""

    def test_local_midnight_is_a_change(self):
        r = Lines().read()
        plan = P.normalize({"timers": [{"id": "r", "kind": "refinery", "label": "R", "location": "ARC-L1",
                                        "ready_at": "2026-11-28T07:30:00Z"}]})[0]
        before = parse_time("2026-11-28T07:59:00Z")            # 11:59 PM in PST
        a = board.build(r.state, plan, None, before, tz=PST)
        self.assertEqual(a["next_change_ms"], int(parse_time("2026-11-28T08:00:00Z") * 1000))
        b = board.build(r.state, plan, None, before + 50, tz=PST)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_a_running_duration_is_not_worded(self):
        r = Lines().add(notice("Joined hangar queue.\nYour place: 2. Max. estimated wait: 60.000000 s.")).read()
        j = r.state.hangar["queue"]["joined"]
        x = [a for a in board.build(r.state, None, None, j + 200)["alerts"] if a["title"] == "Hangar queue stuck"]
        y = [a for a in board.build(r.state, None, None, j + 900)["alerts"] if a["title"] == "Hangar queue stuck"]
        self.assertEqual(x, y)
        self.assertEqual(x[0]["since_ms"], int(round(j * 1000)))
        self.assertEqual(x[0]["text"], "The estimate was 1 min 00 s.")


class DeathBurstTest(unittest.TestCase):
    def test_a_body_right_after_a_gear_burst_is_a_death(self):
        """Review 8: a gear burst from another body, then the user's body 1 s later."""
        s = "s"
        evs = [E.SessionStart(s, 0, 0.0, s, None, None), E.JoinServer(s, 1, 1.0, "x"), E.Spawned(s, 2, 2.0),
               E.ItemLost(s, 3, 10.0, "rifle_gear", "Weapon_ItemPort"),
               E.ItemLost(s, 4, 10.5, "helmet_gear", "Helmet_ItemPort"),
               E.ItemLost(s, 5, 11.5, "body_01_noMagicPocket", "Body_ItemPort"),
               E.ItemLost(s, 6, 11.6, "undersuit", "Undersuit_ItemPort"),
               E.Spawned(s, 7, 40.0)]
        st = State(NAMES)
        for ev in evs:
            st.apply(ev)
        self.assertEqual([d["items_lost"] for d in st.deaths], [2])


class ContractBlockTest(unittest.TestCase):
    def test_the_window_holds_the_current_row(self):
        """Review 9: ten objectives, nine done: the cut blocks count what they leave out."""
        g = Lines()
        mid = "e0000031-0000-4000-8000-000000000031"
        g.add(notice("Contract Accepted:  Example Job", mid))
        for i in range(10):
            g.add(notice("New Objective: Step number %d" % i, mid, "obj_%d" % i), step=0.2)
        for i in range(9):
            g.add(notice("Objective Complete: Step number %d" % i, mid, "obj_%d" % i), step=0.2)
        st = g.read().state
        now = st.session["last_t"] + 1
        for view, size in (("now", 3), ("mission", 8)):
            c = board.build(st, None, {"view": board.pick(st, None, view, True, now)}, now)["model"]["contract"]
            self.assertEqual(len(c["objectives"]), size, view)
            self.assertEqual(c["objectives"][-1]["state"], "now", view)
            self.assertEqual((c["more"], c["before"], c["after"]), (10 - size, 10 - size, 0), view)


class MonitoredTest(unittest.TestCase):
    def test_a_new_server_or_the_menu_clears_monitored_space_down_unverified_shape(self):
        """Review 10."""
        g = Lines().add(notice("Monitored Space Down"))
        r = g.read()
        self.assertTrue(r.state.zone["monitored_down"])
        r = g.add(HEAD[4]).read()
        self.assertFalse(r.state.zone["monitored_down"])
        r = Lines().add(notice("Monitored Space Down")).add('[CSessionManager::RequestFrontEnd] Started - RequestFrontEndReason="OnLobbyPostGameUnload"!').read()
        self.assertFalse(r.state.zone["monitored_down"])
        p = board.build(r.state, None, None, r.state.session["last_t"] + 3 * 3600)
        self.assertNotIn("Monitored space down", [a["title"] for a in p["alerts"]])


class StationMatchTest(unittest.TestCase):
    def test_no_prefix_matching(self):
        """Review 11: a timer at "M" is not cleared by a notice at MIC-L2."""
        r = Lines().add(notice("A Refinery Work Order has been Completed at MIC-L2 Long Forest Station")).read()
        nt = r.state.refinery[-1]["t"]
        plan = P.normalize({"timers": [
            {"id": "m", "kind": "refinery", "label": "M", "location": "M", "ready_at": "2026-11-28T07:00:00Z"},
            {"id": "x", "kind": "refinery", "label": "X", "location": "Some Unknown Place", "ready_at": "2026-11-28T07:00:00Z"},
            {"id": "a", "kind": "refinery", "label": "A", "location": "MIC-L2", "ready_at": "2026-11-28T07:00:00Z"}]})[0]
        states = {t["label"]: t["state"] for t in board.build(r.state, plan, None, nt + 60)["timers"]}
        self.assertEqual(states, {"M": "ready", "X": "ready", "A": "done"})


class ContractCapTest(unittest.TestCase):
    def test_the_newest_contract_is_never_dropped(self):
        """Review 12: 35 contracts accepted; then ended ones go first."""
        g = Lines()
        for c in range(35):
            mid = "e%07d-0000-4000-8000-%012d" % (c, c)
            g.add(notice("Contract Accepted:  Job %d" % c, mid), step=0.1)
        st = g.read().state
        titles = [c["title"] for c in st.contracts.values()]
        self.assertEqual(len(titles), 30)
        self.assertIn("Job 34", titles)
        self.assertEqual(st.current_contracts()[0]["title"], "Job 34")
        g.add("[Notice] <EndMission> Ending mission for player. MissionId[e0000010-0000-4000-8000-000000000010] Player[x] "
              "PlayerId[1] CompletionType[Complete] Reason[Mission Ended] [Team_X]")
        g.add(notice("Contract Accepted:  Job new", "e0000099-0000-4000-8000-000000000099"))
        titles = [c["title"] for c in g.read().state.contracts.values()]
        self.assertNotIn("Job 10", titles)                    # the ended one went, not an active one
        self.assertIn("Job 5", titles)
        self.assertIn("Job new", titles)


class QuickTimerTest(unittest.TestCase):
    def test_same_millisecond_ids_differ_and_quick_timers_keep_room(self):
        """Review 13, and 16's quick timers under twenty plan timers."""
        now = 1795800000.0
        u = board.add_quick_timer({}, "Tea", 5, now)
        u = board.add_quick_timer(u, "Coffee", 10, now)
        self.assertNotEqual(u["timers"][0]["id"], u["timers"][1]["id"])
        # twenty plan timers due before the quick ones, so they sort first and used to fill the list
        plan = P.normalize({"timers": [{"id": "t%d" % i, "label": "p%d" % i, "ready_at": "2026-11-27T17:21:00Z"}
                                       for i in range(20)]})[0]
        p = board.build(Lines().read().state, plan, u, now + 1)
        labels = [t["label"] for t in p["timers"]]
        self.assertIn("Tea", labels)
        self.assertIn("Coffee", labels)
        self.assertEqual(len(labels), 20)


class FallbackTest(unittest.TestCase):
    def test_the_whole_build_fallback_names_what_failed(self):
        """Review 16: the fallback payload named "rules:" whatever had failed."""
        st = Lines().read().state
        with mock.patch.object(board.views, "Ctx", side_effect=KeyError("x")):
            p = board.build(st, None, None, st.session["last_t"] + 1)
        self.assertEqual(p["view"]["rule"], "error")
        self.assertEqual(p["view"]["mode"], "flight")
        self.assertIn("build: KeyError", p["problems"])
        self.assertFalse(any(x.startswith("rules:") for x in p["problems"]))


class BoundedNamesTest(unittest.TestCase):
    def test_the_set_is_bounded_and_a_forgotten_name_stays_hidden_unverified_shape(self):
        """Review 14: past MAX_OTHERS names the oldest are forgotten, and a text that held one
        from before (a contract title, the feed, the timeline's lines) still does not show it."""
        g = Lines()
        g.add(notice("Contract Accepted:  Escort Evil_00000 home", "e0000001-0000-4000-8000-000000000001"))
        for i in range(MAX_OTHERS + 300):
            g.add(notice("Evil_%05d committed Assault against you" % i), step=0.01)
        r = g.read()
        st = r.state
        self.assertLessEqual(len(st._others), MAX_OTHERS)
        self.assertNotIn("Evil_00000", st._others)            # forgotten
        self.assertGreaterEqual(st.forgotten, 1)
        out = everything(r)
        self.assertNotIn("Evil_00000", out)
        self.assertNotIn("Evil_01299", out)                   # remembered, and scrubbed as ever
        self.assertIn("Escort another player home", out)


class Round2Test(unittest.TestCase):
    """Review round 2 (A, B, C, E). Built lines: the shapes are the game's text, unverified in a log."""

    def test_a_crime_against_security_and_a_ship_changes_no_other_text_unverified_shape(self):
        def session(extra):
            g = Lines()
            g.add("[Notice] <SHUDEvent_OnNotification> Added notification \"Entered Hurston Dynamics Jurisdiction: \" [1] to queue. "
                  "New queue size: 1, MissionId: [%s], ObjectiveId: [] [Team_X]" % ZERO)
            g.add(notice("You have joined channel 'Drake Golem : Pilot_Example'."))
            for x in extra:
                g.add(notice(x))
            st = g.read().state
            p = board.build(st, None, None, st.session["last_t"] + 5)
            return st, p
        before_st, before = session([])
        st, p = session(["Crime Committed: Trespassing\nagainst Hurston Security",
                         "Crime Committed: Trespassing\nagainst Drake Golem",
                         "Evil_X committed Assault against your ship", "A player committed Assault against you"])
        self.assertEqual(st.zone["jurisdiction"], before_st.zone["jurisdiction"])
        self.assertEqual(p["strip"], before["strip"])
        self.assertEqual(sorted(st._others), ["Evil_X"])          # only the handle-shaped non-game word
        out = everything(Lines().add(notice("Crime Committed: Trespassing\nagainst Evil_V")).read())
        self.assertNotIn("Evil_V", out)
        for a in p["alerts"]:
            self.assertNotIn("another player Golem", (a["title"] or "") + (a["text"] or ""))

    def test_a_long_ship_channel_is_not_shown_unverified_shape(self):
        r = Lines().add(notice("You have joined channel '%s : Evil_Owner1'." % ("S" * 250))).read()
        self.assertNotIn("Evil_Owner1", everything(r))
        self.assertIn(E.REDACTED_COMMS, everything(r))

    def test_forgetting_keeps_handles_whole_and_hidden(self):
        g = Lines()
        g.add(notice("Bob_Q committed Assault against you"))
        for i in range(499):
            g.add(notice("Flood_%04d committed Assault against you" % i), step=0.01)
        g.add(notice("Bob_Q-Smith committed Assault against you"))
        g.add(notice("Contract Accepted:  Escort Bob_Q-Smith home", "e0000042-0000-4000-8000-000000000042"))
        for i in range(499, 1002):
            g.add(notice("Flood_%04d committed Assault against you" % i), step=0.01)
        g.add(notice("Contract Accepted:  Escort Bob_Q to safety", "e0000043-0000-4000-8000-000000000043"))
        out = everything(g.read())
        self.assertNotIn("-Smith", out)
        self.assertNotIn("Bob_Q", out)

    def test_out_of_range_values_are_counted(self):
        plan, skipped = P.normalize({"current_run": ["x"], "runs": [{"name": "A", "legs": [{"to": "X", "gm": 1e12}]}]})
        self.assertEqual(skipped, {"current_run": 1, "numbers": 1})
        self.assertIn("1 number", P.left_out(skipped))


MID = "e0000301-0000-4000-8000-000000000301"


def destroyed(killer):
    """A <Vehicle Destroyed> line naming a killer, for a ship that is not the user's."""
    return ("[Notice] <Vehicle Destroyed> Vehicle 'AEGS_Gladius_9001' [9001] class 'AEGS_Gladius' (owner player [77], "
            "driver [0]) destroyed: reason [Combat] level [0] -> [2] flags [1] killer '%s' [88] authority [0] [Team_X]" % killer)


def flood(g, n, tag="Fl"):
    """n names learned, each with a feed line of its own (a charge against the user)."""
    for i in range(n):
        g.add(notice("%s_%05d committed Homicide against you" % (tag, i)), step=0.01)
    return g


def quiet_flood(g, n, tag="Ch"):
    """n names learned with no feed line: owners of ship channels the user leaves without being
    aboard (state._on_channel_left)."""
    for i in range(n):
        g.add(notice("You have left the channel 'Drake Golem : %s_%05d'." % (tag, i)), step=0.01)
    return g


def take_all(lines):
    """Read built lines the way the service does (keep_events=False), then take_lines() once."""
    mem = lib.MemoryLog(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    r = pipeline.LogReader("Game.log", NAMES, opener=mem.opener)
    while r.poll() == "read":
        pass
    r.finish()
    return r, r.take_lines()


def best_of(n, fn):
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return min(out)


class Round3Test(unittest.TestCase):
    """Review round 3: its findings 1 to 8, and the five fixes of round 2 that no test checked
    (the mutations of its claim 4). Every name is invented; the notice shapes are the game's own
    text (scdash/law.py), unverified in a log."""

    # finding 1: the forgotten-name lookup was cubic in a text's "-" parts

    def test_a_hyphen_run_costs_linear_time_before_and_after_forgetting(self):
        st = State(NAMES)
        crafted = ["-".join(["a"] * k) for k in range(2, 51)] + ["-" * k + "a" for k in range(2, 100)]
        for n in crafted:                                      # names with every number of parts
            st._other(n)
        for i in range(MAX_OTHERS // 2 - len(crafted) - 1):
            st._other("Kept_%05d" % i)
        texts = ["-".join(["a"] * 1024)[:E.MAX_TEXT], "-" * (E.MAX_TEXT - 1) + "a", "-".join(["b0"] * 700)[:E.MAX_TEXT]] * 10

        def scrub_all():
            for t in texts:
                st.scrub(t)
        before = best_of(2, scrub_all)
        for i in range(MAX_OTHERS):
            st._other("Flood_%05d" % i)
        self.assertGreaterEqual(st.forgotten, 1)
        after = best_of(2, scrub_all)
        # about 0.05 s here; the cubic lookup took 1.6 s for one of these texts, and without its
        # budget the bounded one took 0.13 s for the second
        self.assertLess(before, 1.0)
        self.assertLess(after, 1.0)
        self.assertNotIn("a-a", st.scrub(texts[0]).replace(OTHER, ""))   # hidden whole, never cut

    def test_many_hyphen_notices_after_forgetting_unverified_shape(self):
        g = flood(Lines(), MAX_OTHERS + 1)
        for i in range(50):
            g.add(notice("-".join(["b%d" % (i % 10)] * 680)), step=0.5)
        g.add(notice("Contract Accepted:  " + "-".join(["c"] * 880), MID))
        r = g.read()
        st = r.state
        self.assertGreaterEqual(st.forgotten, 1)
        now = st.session["last_t"] + 5
        t = best_of(1, lambda: (st.to_dict(), board.build(st, None, None, now),
                                board.build(st, None, {"view": board.pick(st, None, "mission", True, now)}, now)))
        self.assertLess(t, 3.0)                       # 0.03 s here; 33 s and 2.5 s before

    # finding 2: unlisted shapes of the families that name a player were shown raw

    SHAPES = {   # the game's text with the name planted -> the neutral wording [game, not seen]
        "Victim: Zq_Planted7": "Victim: someone",
        "%s has joined the channel 'Drake Golem : Pilot_Example'.": "Another player has joined the channel",
        "%s invited to party.": "Invitation sent to another player",
        "%s is now group '" + "G" * 60 + "' leader.": "Another player is now the leader",
        "The channel 'Drake Cutlass Black : %s' has been disbanded.": "A group or channel has been disbanded",
        "Comms Channel Joined: channel 'Drake Golem : %s'": "Joined a comms channel",
        "Hail Target: %s": "Hailing a contact",
        "Party Launching: Initiated by %s": "Party launch started by the party leader",
        "Party Launch: %s is already in your instance.": "A party member is already in your instance",
        "%s connected.": "A party member connected",
        "%s disconnected.": "A party member disconnected",
        "%s canceled their join queue.": "A party member canceled their join queue",
        "Join queue canceled by party leader %s.": "The party leader canceled the join queue",
        "%s has started to QT to your current location.": "A party member has started quantum travel to your location",
        "Currency Transfer Request: %s wants to send you 5000 aUEC": "Another player wants to send you money",
        "Quantum Travel Calibration Started By %s": "Quantum travel calibration started by a party member",
        "New Member Joined: %s has joined the party.": "Another player has joined the party or group",
        "Member Left: %s has left the party.": "Another player has left the party or group",
        "Transfer Failed: Your transfer to %s has failed to send.": "Your transfer to another player has failed",
        "Beacon Accepted: %s accepted your Medical contract.": "Another player accepted your beacon contract",
        "Contract Complete: Your Medical contract's complete. Please rate %s.": "Contract complete: a service beacon contract",
    }

    def test_every_listed_shape_is_worded_without_the_name_unverified_shape(self):
        name = "Zq_Planted7"
        for shape, words in self.SHAPES.items():
            text = shape.replace("%s", name)
            r = Lines().add(notice("You have joined channel 'Drake Golem : Pilot_Example'.")).add(notice(text)).read()
            out = everything(r)
            self.assertNotIn(name, out, text)
            self.assertEqual(r.state.feed[-1]["text"], words, text)   # the neutral words, not the text
            self.assertIn(name, r.state._others, text)                 # and learned
            self.assertNotIn("Hail", r.state._others, text)
            self.assertEqual(r.state.session["withheld"], 0, text)      # a known shape is not counted

    def test_a_named_shape_whose_name_cannot_be_learned_is_still_worded_unverified_shape(self):
        # "Drake" is a word of the game, so the scrubber never learns it: only the wording hides it
        r = Lines().add(notice("You have joined Drake's party.")).add(notice("Victim: Drake")).read()
        out = everything(r)
        self.assertNotIn("Drake's", out)
        self.assertIn("You have joined another player's party or group", out)
        self.assertIn("Victim: someone", out)

    UNKNOWN = [   # (text, family, its neutral wording): shapes nobody has written down
        ("Zq_Unk1 committed Homicide on the moon", "law", E.REDACTED),
        ("Comms Channel Renamed: channel 'Drake Golem : Zq_Unk2'", "comms", E.REDACTED_COMMS),
        ("Party Recall: Zq_Unk3 is waiting", "party", E.REDACTED_PARTY),
        ("Transfer Pending: Zq_Unk4 has sent you nothing yet", "transfer", E.REDACTED_TRANSFER),
        ("Beacon Pinged: Zq_Unk5 pinged your beacon", "beacon", E.REDACTED_BEACON),
    ]

    def test_an_unknown_shape_of_a_naming_family_is_withheld_and_counted_unverified_shape(self):
        for text, family, words in self.UNKNOWN:
            name = text.split("Zq_")[1].split()[0].strip("'")
            r = Lines().add(notice(text)).read()
            out = everything(r)
            self.assertNotIn("Zq_" + name, out, text)
            self.assertEqual(r.state.feed[-1]["text"], words, text)
            ev = [e for e in r.events if e.kind == "notice"][-1]
            self.assertEqual(ev.withheld, family, text)
            self.assertEqual(r.state.session["withheld"], 1, text)
            self.assertEqual(r.state.to_dict()["session"]["withheld"], 1, text)
            self.assertEqual(r.summary(complete=True)["withheld"], 1, text)
        # a tutorial tip with a family's cue is not counted; a notice with no cue is shown as it is
        r = Lines().add(notice("Quantum Linking: Once linked, you will be able to initiate QT for the group nearby")).add(
            notice("Entering Private Property")).read()
        self.assertEqual(r.state.session["withheld"], 0)
        self.assertEqual(r.state.feed[-1]["text"], "Entering Private Property")

    def test_a_text_of_these_families_that_names_nobody_is_shown_as_it_is_unverified_shape(self):
        for text in ("You have left the party.", "You have been kicked from the group.", "Member Left: You have left the party.",
                     "Party Disbanded: Leader Disbanded Party", "Your party has disbanded.", "Party Launching",
                     "Session Full: Not enough room for Party", "Join queue canceled."):
            r = Lines().add(notice(text)).read()
            self.assertEqual(r.state.feed[-1]["text"], text, text)
            self.assertEqual(r.state.session["withheld"], 0, text)

    def test_hail_learns_the_contact_not_the_word_hail_unverified_shape(self):
        st = Lines().add(notice("Hail Target: Zq_Hailed")).read().state
        self.assertEqual(sorted(st._others), ["Zq_Hailed"])
        self.assertEqual(E.comms_names("Hail Target: Zq_Hailed2"), ("Zq_Hailed2",))

    # finding 3: names that differ only in case

    def test_names_that_differ_in_case_are_replaced_whole(self):
        self.assertEqual(S.name_regex(["Bob_Q", "bob_q-Smith"]).sub("X", "Escort bob_q-Smith home"), "Escort X home")
        r = Lines().add(notice("Bob_Q committed Homicide against you")).add(
            notice("bob_q-Smith committed Homicide against you")).add(notice("Contract Accepted:  Escort bob_q-Smith home", MID)).read()
        out = everything(r)
        self.assertNotIn("-Smith", out)
        self.assertIn("Escort another player home", out)

    # finding 4: what may be learned and what is hidden once forgotten are the same set

    def test_every_handle_learned_is_found_again_once_forgotten(self):
        for s in ("-Lead_Hy", "Trail_Hy-", "Dbl--Hy", "Mid-Hy-Ph", "A1234", "a_b", "---x", "x" * 60):
            self.assertTrue(law.HANDLE_RE.match(s), s)
            self.assertTrue(S._RUN_RE.fullmatch(s), s)
        for name in ("-Lead_Hy", "Trail_Hy-", "Dbl--Hy", "Mid-Hy-Ph"):
            g = Lines().add(notice("%s committed Homicide against you" % name))
            g.add(notice("Contract Accepted:  Escort %s home" % name, MID))
            flood(g, MAX_OTHERS + 1)
            g.add(notice("Contract Accepted:  Bring %s to safety" % name, "e0000302-0000-4000-8000-000000000302"))
            r = g.read()
            self.assertNotIn(name, r.state._others, name)               # forgotten
            out = everything(r)
            self.assertNotIn(name.strip("-"), out, name)
            self.assertIn("Bring another player to safety", out, name)

    # finding 5: lone surrogates

    def test_lone_surrogates_are_taken_out_of_every_text(self):
        bad = chr(0xD800) + "x" + chr(0xDFFF)
        self.assertEqual(clean_text("a" + bad), "ax")
        with lib.TempDir() as d:
            path = d / "plan.json"
            lib.write(path, b'{"notes": ["\\ud800 a lone surrogate"], "runs": [{"id": "r", "name": "Run \\udfff", "status": "in_progress"}]}')
            store = P.PlanStore(path)
            store.refresh()
        user = board.add_quick_timer({}, "Tea" + bad, 5, 1.8e9)
        self.assertEqual(user["timers"][0]["label"], "Teax")
        user["timers"].append({"id": "q2", "label": "Odd" + bad, "ready_at": "2026-11-28T08:00:00Z"})
        st = Lines().read().state
        p = board.build(st, store.plan, user, st.session["last_t"] + 1)
        text = json.dumps(p, ensure_ascii=False)
        text.encode("utf-8")                                      # raised UnicodeEncodeError
        self.assertEqual(p["plan"]["run"], "Run")
        json.dumps(st.to_dict(), ensure_ascii=False).encode("utf-8")

    # finding 6: `timeline` was quadratic in the number of names

    def test_timeline_reads_many_names_as_fast_as_the_service(self):
        g = Lines()
        for i in range(20000):
            g.add(notice("Tl_%07d committed Homicide against you" % i), step=0.001)
        data = ("\r\n".join(g.lines) + "\r\n").encode("utf-8")

        def read(keep):
            r = pipeline.LogReader("Game.log", NAMES, opener=lib.MemoryLog(data).opener, keep_events=keep)
            while r.poll() == "read":
                pass
            r.finish()
            return len(r.all_lines)
        plain = best_of(1, lambda: read(False))
        keep = best_of(1, lambda: read(True))
        # about the same here; 3.3 times the service's way before
        self.assertLess(keep, 1.6 * plain + 0.3, "%.2f s against %.2f s" % (keep, plain))

    # the fixes of round 2 no test checked, and finding 7 (take_lines)

    def test_a_forgotten_name_no_scrubber_can_find_leaves_every_text_held(self):
        # A killer's name that is not handle-shaped: once forgotten, neither the scrubber's names
        # nor the hashes of forgotten names can find it, so only the walks that replace it in every
        # text held (the state's own, and the reader's lines) keep it out.
        def log(lines_after):
            g = Lines().add(destroyed("Zq Two"))
            g.add(notice("Contract Accepted:  Escort Zq Two home", MID))
            flood(g, lines_after)                     # the contract's line leaves the state's feed
            return quiet_flood(g, MAX_OTHERS + 1 - lines_after)   # "Zq Two" is the oldest: forgotten
        g = log(60)
        r = g.read()
        self.assertGreaterEqual(r.state.forgotten, 1)
        self.assertNotIn("Zq Two", r.state._others)
        self.assertNotIn("Zq Two", json.dumps(r.state.to_dict()))          # the state's walk
        self.assertIn("Escort another player home", json.dumps(r.state.to_dict()))
        _, lines = take_all(g.lines)
        self.assertNotIn("Zq Two", json.dumps(lines))                       # the lines waiting
        self.assertIn("Contract accepted: Escort another player home", [x["text"] for x in lines])
        # 600 lines after it: it has left the lines waiting too, and only the list of every line
        # (`timeline`) still holds it
        r = log(600).read()
        self.assertGreaterEqual(r.state.forgotten, 1)
        sm = r.summary(complete=True)
        text = timeline.render_text(r, sm, show_all=True)
        self.assertNotIn("Zq Two", text)
        self.assertIn("Contract accepted: Escort another player home", text)
        self.assertNotIn("Zq Two", json.dumps(timeline.render_json(r, sm, show_all=True)))

    def test_the_stoplist_holds_whatever_game_words_are_given(self):
        for w in ("your", "player", "security", "Officer", "Captain", "Turret"):
            self.assertIsNone(law.learnable(w, frozenset()), w)
        gw = State(NAMES).ref.game_words(NAMES)
        for w in ("Drakes", "Golems", "Securities", "Officers"):       # plurals (finding 9)
            self.assertIsNone(law.learnable(w, gw), w)
        self.assertEqual(law.learnable("Zq_Planted7.", gw), "Zq_Planted7")

    def test_a_ship_channel_of_150_characters_is_read_unverified_shape(self):
        ship = ("Long " * 30).strip()
        st = Lines().add(notice("You have joined channel '%s : Pilot_Example'." % ship)).read().state
        self.assertEqual((st.ship["name"], st.ship["own"]), (ship, True))

    def test_every_pattern_for_a_named_notice_is_bounded(self):
        # No unbounded repeat: with a text of MAX_TEXT, each costs a bounded time (PLAN §8)
        pats = ([p for p, _ in E.NAMED_NOTICES] + [p for p, _ in E.BEFORE_KINDS] + [f[1] for f in E.FAMILIES]
                + [E.TOAST_TITLE_RE, E.MARKUP_RE, law.NAMELESS_NUMBER_RE, law.BEACON_MARKER_RE, law.BOUNTY_MARKER_RE]
                + E._SOCIAL_NAME_RES + [p for _, p, _ in law.PLAYER_TITLES]
                + [p for _, p, _, _ in law.PLAYER_OBJECTIVES])
        unbounded = re.compile(r"(?<!\\)[*+]")
        self.assertEqual([p.pattern for p in pats if unbounded.search(p.pattern)], [])

    def test_a_long_hyphenated_text_that_names_nobody_is_left_alone(self):
        st = State(NAMES)
        for i in range(MAX_OTHERS + 1):
            st._other("Flood_%05d" % i)
        self.assertGreaterEqual(st.forgotten, 1)
        text = "-".join("Part%d" % i for i in range(60))      # 60 parts: no name has that many
        self.assertEqual(st.scrub(text), text)

    def test_take_lines_are_scrubbed(self):
        g = Lines().add(notice("Zq_Known committed Homicide against you"))
        g.add(notice("Contract Accepted:  Escort Zq_Known and Pilot_Example home", MID))
        _, lines = take_all(g.lines)
        text = json.dumps(lines)
        self.assertNotIn("Zq_Known", text)
        self.assertNotIn("Pilot_Example", text)
        self.assertIn("Contract accepted: Escort another player and you home", [x["text"] for x in lines])

    def test_a_one_word_victim_that_is_a_game_word_is_not_learned_unverified_shape(self):
        g = Lines().add("[Notice] <SHUDEvent_OnNotification> Added notification \"Entered Hurston Dynamics Jurisdiction: \" [1] to queue. "
                        "New queue size: 1, MissionId: [%s], ObjectiveId: [] [Team_X]" % ZERO)
        for victim in ("Hurston", "Lorville", "Drake"):
            g.add(notice("Crime Committed: Trespassing (Second Degree)\nagainst %s" % victim))
        st = g.read().state
        self.assertEqual(st._others, {})
        self.assertIn("Hurston Dynamics", json.dumps(st.to_dict()))

    def test_a_word_that_is_not_handle_shaped_is_not_learned_unverified_shape(self):
        g = Lines()
        for victim in ("Zq.Dot", "12345", "Zq@Mail", "Zq+Plus"):
            g.add(notice("Crime Committed: Homicide\nagainst %s" % victim))
            g.add(notice("%s committed Homicide against you" % victim))
        self.assertEqual(g.read().state._others, {})

    # finding 8: the plan loader counts every value it drops or changes

    def test_every_dropped_or_changed_plan_value_is_counted(self):
        leg = {"to": "CRU-L1"}
        cases = {
            "status": {"runs": [{"id": "a", "name": "A", "status": "running"}]},
            "kind": {"runs": [{"id": "a", "name": "A", "kind": "bounty"}]},
            "leg view": {"runs": [{"name": "r", "legs": [dict(leg, view="travel")]}]},
            "id": {"runs": [{"id": "a b", "name": "A"}]},
            "13 legs": {"runs": [{"name": "r", "legs": [leg] * 13}]},
            "legs not a list": {"runs": [{"name": "r", "legs": {"to": "x"}}]},
            "13 materials": {"objectives": [{"title": "x", "materials": [{"name": "n%d" % i} for i in range(13)]}]},
            "7 targets": {"runs": [{"name": "r", "targets": ["Agricium"] * 7}]},
            "11 notes": {"notes": ["n"] * 11},
            "a note not a text": {"notes": ["a", 5]},
            "started_at": {"timers": [{"id": "t", "label": "L", "ready_at": "2026-11-27T12:00:00Z", "started_at": "soon"}]},
            "updated": {"updated": "yesterday"},
            "salvage not an object": {"runs": [{"name": "r", "salvage": ["x"]}]},
            "codes with spaces": {"runs": [{"name": "r", "legs": [dict(leg, codes=["LOC RR"])]}]},
            "text over 300": {"notes": ["n" * 400]},
            "timer kind": {"timers": [{"id": "t", "kind": "egg", "label": "L", "ready_at": "2026-11-27T12:00:00Z"}]},
        }
        for label, raw in cases.items():
            plan, skipped = P.normalize(raw)
            self.assertTrue(skipped, label)
            self.assertTrue(P.left_out(skipped), label)
        self.assertEqual(P.normalize(cases["11 notes"])[1], {"notes": 1})
        self.assertEqual(P.normalize(cases["text over 300"])[1], {"cut": 1})
        self.assertIn("1 value (", P.left_out(P.normalize(cases["status"])[1]))
        example = json.loads((lib.DASHBOARD / "plan.example.json").read_text(encoding="utf-8"))
        self.assertEqual(P.normalize(example)[1], {})              # nothing counted in a good plan

    def test_the_law_sample_uses_the_games_own_crime_names(self):
        r = pipeline.read_whole(lib.sample_path("built_law.log"), NAMES)
        crimes = [e.crime for e in r.events if e.kind in ("crime", "crime_against_you")]
        self.assertEqual(len(crimes), 2)
        for c in crimes:
            self.assertIn(c, law.CRIMES)


BEACON = "e0000401-0000-4000-8000-000000000401"


def forgotten_state(forget, keep=()):
    """A state whose names `forget` were forgotten (a forgetting pass) and `keep` are known."""
    st = State(NAMES)
    st.me["handle"] = "Pilot_Example"
    for n in forget:
        st._other(n)
    st._forget([n for n in forget if n in st._others])
    for n in keep:
        st._other(n)
    return st


class Round4Test(unittest.TestCase):
    """Review round 4: its findings 1 to 10, the shard name, and the mutations of its claim 10
    that no test caught. Every name is invented; the shapes are the game's own text (law.py),
    unverified in a log, unless a test's name says inferred."""

    def public(self, r):
        return everything(r) + json.dumps(r.take_lines())

    # finding 1: the service beacon's objectives -------------------------------------------
    def test_every_beacon_objective_is_worded_without_the_initiator_unverified_shape(self):
        for key, rx, words, who in law.PLAYER_OBJECTIVES:
            if not who:
                continue
            title = {"ServiceBeacon_CombatAssist_Avenge_Obj_Title": "Avenge Zq_Init4."}.get(key)
            text = title or rx.pattern.strip("^$").replace(r"(\S{1,100})", "Zq_Init4").replace(r"(\S{1,100}?)", "Zq_Init4")
            text = text.replace(r"\.?", ".").replace(".{1,200}", "Lorville")
            g = Lines().add(notice("Contract Accepted: Medical Rescue", BEACON))
            g.add(notice("New Objective: %s" % text, BEACON, "obj_1"))
            g.add(notice("Objective Complete: %s" % text, BEACON, "obj_1"))
            g.add(notice("Contract Accepted: Escort Zq_Init4 to Lorville", ZERO))   # another text names them
            r = g.read()
            self.assertNotIn("Zq_Init4", self.public(r), key)
            self.assertIn("Zq_Init4", r.state._others, key)
            c = r.state.contracts[BEACON]
            self.assertEqual((c["objective"], c["objectives"][0]["state"]), (words, "complete"), key)
            self.assertEqual(r.state.session["withheld"], 0, key)

    def test_the_rescue_sequence_shows_no_initiator_unverified_shape(self):
        g = Lines().add(notice("Medical Rescue Requested: Rescue Beacon Activated By: Zq_Down5. Payment: 15000. Distance: 1.2 km."))
        g.add(notice("Contract Accepted: Medical Rescue", BEACON))
        g.add(notice("New Objective: Rescue Zq_Down5", BEACON, "o1"))
        g.add(notice("Contract Complete: The Medical Rescue contract’s complete. Please rate Zq_Down5."))
        r = g.read()
        self.assertNotIn("Zq_Down5", self.public(r))
        feed = [x["text"] for x in r.state.feed]
        self.assertIn("A rescue beacon from another player", feed)
        self.assertIn("New objective: Rescue the player who set the beacon", feed)
        self.assertIn("Contract complete: a service beacon contract", feed)     # the "The" form
        self.assertEqual(list(r.state.contracts), [BEACON])                    # not taken for a title
        self.assertEqual((r.state.session["withheld"], r.state.session["withheld_tips"]), (0, 0))

    def test_the_downed_users_beacon_accepted_by_a_rescuer_unverified_shape(self):
        g = Lines().add(notice("Zq_Medic2 accepted the Rescue Beacon and is 1.2 km away."))
        g.add(notice("Contract Accepted: Escort Zq_Medic2 to Lorville", MID))
        r = g.read()
        self.assertEqual(r.state.feed[-2]["text"], "Another player accepted your rescue beacon")
        self.assertNotIn("Zq_Medic2", self.public(r))
        self.assertEqual(r.state.session["withheld"], 0)

    def test_an_objective_of_a_beacon_in_an_unknown_shape_is_withheld_unverified_shape(self):
        g = Lines().add(notice("Contract Accepted: Medical Rescue", BEACON))
        g.add(notice("New Objective: Carry Zq_Down6 to a clinic", BEACON, "o1"))
        g.add(notice("New Objective: Stay at Current Location.", BEACON, "o2"))      # the game's, nameless
        r = g.read()
        self.assertNotIn("Zq_Down6", self.public(r))
        texts = [o["text"] for o in r.state.contracts[BEACON]["objectives"]]
        self.assertEqual(texts, [law.WITHHELD_OBJECTIVE, "Stay at Current Location."])
        self.assertEqual(r.state.session["withheld"], 1)

    def test_a_beacon_known_by_its_marker_alone_unverified_shape(self):
        g = Lines().add("[Notice] <CLocalMissionPhaseMarker::CreateMarker> Creating objective marker: missionId [%s], "
                        "generator name [BeaconContractGenerator], contract [ReviveBeacon] [Team_X]" % BEACON)
        g.add(notice("New Objective: Rescue Zq_Down7", BEACON, "o1"))
        r = g.read()
        self.assertNotIn("Zq_Down7", self.public(r))
        self.assertEqual(r.state.contracts[BEACON]["objective"], "Rescue the player who set the beacon")

    def test_a_player_bounty_known_by_its_marker_alone_unverified_shape(self):
        # NorthRock_PVP's kind in the contracts table is "bounty", as for an NPC bounty: the
        # marker's names say the target is a player
        bounty = "e0000404-0000-4000-8000-000000000404"
        g = Lines().add("[Notice] <CLocalMissionPhaseMarker::CreateMarker> Creating objective marker: missionId [%s], "
                        "generator name [NorthRock_PVP], contract [NorthRock_Bounty_General_PVP] [Team_X]" % bounty)
        g.add(notice("New Objective: Locate Zq_Wanted2", bounty, "o1"))
        r = g.read()
        self.assertNotIn("Zq_Wanted2", self.public(r))
        self.assertEqual(r.state.contracts[bounty]["objective"], "Locate the target")

    def test_the_same_words_in_other_contracts_are_left_alone(self):
        g = Lines().add(notice("Contract Accepted: Deliver Cargo to Lorville", MID))
        g.add(notice("New Objective: Go to Lorville", MID, "o1"))
        g.add(notice("New Objective: Protect Zq_Npc8", MID, "o2"))           # a known kind: as written
        g.add(notice("New Objective: Go to Lorville", ZERO.replace("0", "1"), "o3"))   # unknown: no handle in it
        r = g.read()
        feed = [x["text"] for x in r.state.feed]
        self.assertEqual(feed.count("New objective: Go to Lorville"), 2)
        self.assertIn("New objective: Protect Zq_Npc8", feed)
        self.assertEqual(r.state.session["withheld"], 0)

    def test_an_objective_of_an_unknown_contract_with_a_handle_is_worded_unverified_shape(self):
        unknown = "e0000402-0000-4000-8000-000000000402"
        g = Lines().add(notice("New Objective: Rescue Zq_Down9", unknown, "o1"))
        g.add(notice("New Objective: Reach Drake Cutlass Black's Beacon", unknown, "o2"))
        r = g.read()
        self.assertNotIn("Zq_Down9", self.public(r))
        objs = [o["text"] for o in r.state.contracts[unknown]["objectives"]]
        self.assertEqual(objs, ["Rescue the target", "Reach the ship's beacon"])     # no beacon words
        self.assertNotIn("Zq_Down9", r.state._others)                                 # and nothing learned

    # round 5's review: contracts the log never placed, then placed ----------------------------
    def test_one_word_npc_names_in_an_unplaced_contract_are_not_learned(self):
        unknown = "e0000405-0000-4000-8000-000000000405"
        g = Lines().add(notice("New Objective: Neutralize Bomber", unknown, "o1"))
        g.add(notice("New Objective: Eliminate Vasquez.", unknown, "o2"))
        g.add(notice("New Objective: Locate Navigator", unknown, "o3"))
        r = g.read()
        self.assertEqual([o["text"] for o in r.state.contracts[unknown]["objectives"]],
                         ["Neutralize the target", "Eliminate the target", "Locate the target"])
        self.assertEqual(set(r.state._others), set())
        self.assertNotIn("_raw", json.dumps(r.state.to_dict(private=True)))       # kept, never output
        # the marker places it: an NPC bounty of the Bounty Hunters Guild, its objectives as written
        g.add("[Notice] <CLocalMissionPhaseMarker::CreateMarker> Creating objective marker: missionId [%s], "
              "generator name [BountyHuntersGuild_FPS], contract [BHG_FPS_Intro] [Team_X]" % unknown)
        c = g.read().state.contracts[unknown]
        self.assertEqual([o["text"] for o in c["objectives"]],
                         ["Neutralize Bomber", "Eliminate Vasquez.", "Locate Navigator"])
        self.assertEqual(c["objective"], "Locate Navigator")

    def test_a_beacon_placed_after_its_objectives_unverified_shape(self):
        g = Lines().add(notice("New Objective: Rescue Tank", BEACON, "o1"))          # a notice word as handle
        g.add(notice("New Objective: Carry Zq_Down8 to a clinic", BEACON, "o2"))
        g.add(notice("Contract Accepted: Medical Rescue", BEACON))
        g.add(notice("Contract Accepted: Escort Tank and Zq_Down8 to Lorville", MID))
        r = g.read()
        c = r.state.contracts[BEACON]
        self.assertEqual([o["text"] for o in c["objectives"]],
                         ["Rescue the player who set the beacon", law.WITHHELD_OBJECTIVE])
        self.assertIn("Tank", r.state._others)
        self.assertEqual(r.state.session["withheld"], 1)
        self.assertNotIn("Escort Tank", self.public(r))

    def test_a_neutralize_slot_of_a_player_bounty_is_learned_unverified_shape(self):
        bounty = "e0000406-0000-4000-8000-000000000406"
        g = Lines().add(notice("Contract Accepted: Pro Tem Suspect Apprehension", bounty))
        g.add(notice("New Objective: Neutralize Zq_Wanted3", bounty, "o1"))
        g.add(notice("New Objective: Eliminate Hostiles", bounty, "o2"))
        g.add(notice("Contract Accepted: Escort Zq_Wanted3 to Lorville", MID))
        r = g.read()
        self.assertNotIn("Zq_Wanted3", self.public(r))
        self.assertEqual([o["text"] for o in r.state.contracts[bounty]["objectives"]],
                         ["Neutralize the target", "Eliminate the target"])     # no beacon words in a bounty

    def test_a_beacon_known_by_a_marker_the_table_does_not_hold_unverified_shape(self):
        beacon = "e0000407-0000-4000-8000-000000000407"
        g = Lines().add("[Notice] <CLocalMissionPhaseMarker::CreateMarker> Creating objective marker: missionId [%s], "
                        "generator name [ServiceBeacon_Heal], contract [ServiceBeacon_Heal_01] [Team_X]" % beacon)
        g.add(notice("New Objective: Treat Zq_Hurt1", beacon, "o1"))
        r = g.read()
        self.assertEqual(r.state.contracts[beacon]["objective"], "Treat the player who set the beacon")
        self.assertIn("Zq_Hurt1", r.state._others)

    def test_the_guilds_npc_certifications_are_not_player_contracts(self):
        for internal, giver in (("BountyHuntersGuild_Certification_Easy", "BountyHuntersGuild_KIllShip"),
                                ("BHG_FPS_Intro", "BountyHuntersGuild_FPS")):
            self.assertIs(law.player_contract({"internal": internal, "giver": giver, "kind": "bounty"}), False)
        self.assertEqual(law.player_contract({"internal": "NorthRock_Bounty_General_PVP", "giver": "NorthRock_PVP",
                                              "kind": "bounty"}), "bounty")

    def test_an_exact_slot_learns_a_notice_word_unverified_shape(self):
        g = Lines().add(notice("Tank has joined the party."))
        g.add(notice("Contract Accepted: Escort Tank to Lorville", MID))
        r = g.read()
        self.assertIn("Tank", r.state._others)
        self.assertNotIn("Escort Tank", self.public(r))

    def test_a_plural_of_a_notice_word_is_no_guess(self):
        gw = State(NAMES).ref.game_words(NAMES)
        self.assertNotIn("abilities", law.NOTICE_WORDS)
        self.assertEqual(law.learnable("Abilities", gw), "Abilities")
        self.assertIsNone(law.guessable("Abilities", gw))

    def test_a_nameless_title_and_description_that_is_no_toast(self):
        r = Lines().add(notice("Squad Invite: Accept Invitation?")).read()
        self.assertEqual(r.state.feed[-1]["text"], "Squad Invite: Accept Invitation?")
        self.assertEqual(r.state.session["withheld"], 0)

    def test_a_known_toasts_long_nameless_description_is_shown(self):
        t = "Party Launch Failed: Party launch failed because you are currently not in an instance."
        r = Lines().add(notice(t)).read()
        self.assertEqual(r.state.feed[-1]["text"], t)

    def test_a_tip_with_a_nameless_topic_is_no_familys(self):
        r = Lines().add(notice("Investigate Distress Beacon: Locate and investigate the source of a faint distress beacon")).read()
        self.assertEqual((r.state.session["withheld"], r.state.session["withheld_tips"]), (0, 0))

    def test_the_seal_takes_out_a_forgotten_name_that_starts_with_a_known_one(self):
        # the review's probe_seal.py: a killer "Zq_Bob Smith" forgotten, "Zq_Bob" still known
        g = Lines().add(destroyed("Zq_Bob Smith"))
        g.add(notice("Contract Accepted: Escort Zq_Bob Smith home", MID))
        flood(g, MAX_OTHERS + 100, tag="Xs")
        g.add(notice("Zq_Bob has joined the party."))
        old = g.lines
        mem = lib.MemoryLog(("\r\n".join(old) + "\r\n").encode("utf-8"))
        r = pipeline.LogReader("Game.log", NAMES, opener=mem.opener, keep_events=True)
        while r.poll() == "read":
            pass
        new = Lines(head=False)
        new.lines[0] = new.lines[0].replace("27 Nov 26 (23 00 00)", "28 Nov 26 (04 00 00)")
        mem.data = bytearray(("\r\n".join(new.lines) + "\r\n").encode("utf-8"))
        for _ in range(3):
            r.poll()
        text = timeline.render_text(r, r.summary(True), show_all=True)
        self.assertIn("Escort another player home", text)
        self.assertNotIn("Smith", text)

    def test_a_player_bounty_title_is_worded_and_teaches_the_name_unverified_shape(self):
        bounty = "e0000403-0000-4000-8000-000000000403"
        g = Lines().add(notice("Contract Accepted: Apprehend Suspect: Zq_Wanted1", bounty))
        g.add(notice("New Objective: Locate Zq_Wanted1", bounty, "o1"))
        g.add(notice("New Objective: Follow Zq_Wanted1 home", bounty, "o2"))     # not a known shape
        g.add(notice("Contract Complete: Apprehend Suspect: Zq_Wanted1", bounty))
        r = g.read()
        self.assertNotIn("Zq_Wanted1", self.public(r))
        c = r.state.contracts[bounty]
        self.assertEqual(c["title"], "Apprehend Suspect: another player")
        self.assertEqual([o["text"] for o in c["objectives"]], ["Locate the target", law.WITHHELD_OBJECTIVE])
        self.assertIn("Zq_Wanted1", r.state._others)

    # finding 2: a known toast title, a bare name ----------------------------------------------
    def test_a_known_toast_title_with_a_bare_name_inferred_shape(self):
        for title in ("Friend Request", "Friend Added", "Friend Request Declined", "Member Left", "Member Kicked",
                      "New Member Joined", "New Party Leader", "Invite Sent To", "Provider Arrived"):
            r = Lines().add(notice("%s: Zq_Pal2" % title)).read()
            self.assertNotIn("Zq_Pal2", self.public(r), title)
            self.assertEqual(r.state.feed[-1]["text"], "%s: another player" % title)
            self.assertIn("Zq_Pal2", r.state._others, title)

    def test_every_text_under_a_known_toast_title_belongs_to_a_family_inferred_shape(self):
        r = Lines().add(notice("Friend Request: hello there Zq_Pal3 wants to be friends")).read()
        self.assertNotIn("Zq_Pal3", self.public(r))
        self.assertEqual(r.state.feed[-1]["text"], E.REDACTED_PARTY)
        self.assertEqual(r.state.session["withheld"], 1)
        long = "Friend Request: " + "a very long description naming Zq_Pal4 that runs on and on"
        r = Lines().add(notice(long)).read()
        self.assertEqual(r.state.feed[-1]["text"], E.REDACTED_PARTY)       # a known toast is no tip
        self.assertNotIn("Zq_Pal4", self.public(r))

    # finding 4: the game's own nameless texts ---------------------------------------------------
    def test_every_nameless_game_text_is_shown_as_written(self):
        texts = sorted(set(law.NAMELESS_TEXTS.values()))
        g = Lines()
        for t in texts:
            g.add(notice(t), step=0.01)
        r = g.read()
        self.assertEqual((r.state.session["withheld"], r.state.session["withheld_tips"]), (0, 0))
        self.assertEqual(set(r.state._others), set())             # and teach no name
        shown = {x["text"] for x in r.all_lines}
        for t in texts:
            head, sep, rest = t.partition(": ")
            if not (sep and len(rest) > 40):                    # a tip is never a feed line
                self.assertIn(t, shown)
        self.assertIn("Your Rescue Beacon has been accepted. Assistance is on the way.", shown)

    def test_a_title_and_its_description_both_nameless(self):
        for t in ("Party Disbanded: Leader Disbanded Party", "Session Full: Not enough room for Party",
                  "Party Launch Failed: Session not found", "Party Launch Failed: ",   # an empty description
                  "Rescue Beacon: Current Balance: 1,250 aUEC - Insufficient funds for activation."):
            r = Lines().add(notice(t)).read()
            self.assertEqual(r.state.session["withheld"], 0, t)

    def test_a_tip_shaped_family_notice_is_counted_apart_unverified_shape(self):
        r = Lines().add(notice("Rescue Beacon: Zq_Tip1 needs help, payment 15000 aUEC, distance 1.2 km, respond now")).read()
        self.assertEqual((r.state.session["withheld"], r.state.session["withheld_tips"]), (0, 1))
        self.assertEqual(r.summary(True)["withheld_tips"], 1)
        self.assertNotIn("Zq_Tip1", self.public(r))
        # a journal's long text with a family's word in it is no family's (its topic decides)
        r = Lines().add(notice("Missing Persons: a long journal text about a group of people who went missing near Yela")).read()
        self.assertEqual((r.state.session["withheld"], r.state.session["withheld_tips"]), (0, 0))

    # finding 5: a guess never learns a word of the game's notices ------------------------------
    def test_a_game_text_teaches_no_false_name(self):
        r = Lines().add(notice("Share is unavailable if there are no eligible party members.")).read()
        self.assertEqual(set(r.state._others), set())
        self.assertEqual(r.state.session["withheld"], 0)
        gw = r.state.ref.game_words(NAMES)
        for w in ("Contract", "Contracts", "Beacon", "Request", "Escort", "Refuel", "Payment", "Distance",
                  "Provider", "Squad", "Friend", "Calibration", "Objective", "Clinic", "Rescuer", "Bunker", "Share"):
            self.assertIsNone(law.guessable(w, gw), w)
        self.assertEqual(law.guessable("Zq_Guess1", gw), "Zq_Guess1")

    def test_the_providers_complete_toast_without_its_title_unverified_shape(self):
        r = Lines().add(notice("The Medical Rescue contract’s complete.  Please rate Zq_Rated1.")).read()
        self.assertEqual(r.state.feed[-1]["text"], "Contract complete: a service beacon contract")
        self.assertEqual(r.state.session["withheld"], 0)
        self.assertIn("Zq_Rated1", r.state._others)

    def test_a_guess_after_by_colon_unverified_shape(self):
        g = Lines().add(notice("Escort Beacon Activated By: Zq_Esc1. Payment: 900 aUEC."))
        g.add(notice("Contract Accepted: Escort Zq_Esc1 to Lorville", MID))
        r = g.read()
        self.assertEqual(r.state.session["withheld"], 1)
        self.assertNotIn("Zq_Esc1", self.public(r))

    def test_a_guess_never_learns_a_notice_word_unverified_shape(self):
        # an unknown shape of the party family whose word after "by" is a word of the game's notices
        r = Lines().add(notice("Party invite forwarded by Squad.")).add(notice("Group launch held by Request")).read()
        self.assertEqual(r.state.session["withheld"], 2)
        self.assertEqual(set(r.state._others), set())
        gw = r.state.ref.game_words(NAMES)
        self.assertEqual((law.learnable("Squad", gw), law.learnable("Request", gw)), ("Squad", "Request"))

    def test_a_guess_still_learns_a_handle_unverified_shape(self):
        # social_names: an unknown shape of the party family names someone after "by"
        g = Lines().add(notice("Quantum travel calibration started by Zq_Cal9"))
        g.add(notice("Contract Accepted: Escort Zq_Cal9 to Lorville", MID))
        r = g.read()
        self.assertEqual(r.state.session["withheld"], 1)
        self.assertNotIn("Zq_Cal9", self.public(r))

    def test_a_channel_owner_is_learned_from_a_member_notice_unverified_shape(self):
        g = Lines().add(notice("Zq_Mem1 has joined the channel 'Drake Cutlass Black : Zq_Own1'."))
        g.add(notice("Contract Accepted: Escort Zq_Own1 to Lorville", MID))
        r = g.read()
        self.assertEqual(r.state.feed[-2]["text"], "Another player has joined the channel")
        self.assertNotIn("Zq_Own1", self.public(r))
        self.assertNotIn("Zq_Mem1", self.public(r))

    def test_a_one_word_notice_that_can_be_a_handle_is_withheld(self):
        r = Lines().add(notice("Zq_Lone7")).add(notice("Lorville")).read()
        self.assertEqual([x["text"] for x in r.state.feed][-2:], [law.ONE_WORD_WITHHELD, "Lorville"])
        self.assertEqual(r.state.session["withheld"], 1)
        self.assertNotIn("Zq_Lone7", self.public(r))

    def test_an_organizations_area_unverified_shape(self):
        r = Lines().add(notice("Trespassing in Zq_Org1-Controlled Area Leave or Risk Prosecution")).read()
        self.assertNotIn("Zq_Org1", self.public(r))
        self.assertEqual(r.state.session["withheld"], 0)

    def test_crime_names_are_only_the_games_words(self):
        r = Lines().add(notice("Crime Committed: Zq_Odd5 did a thing")).read()
        self.assertEqual(r.state.feed[-1]["text"], "Crime committed: a crime")
        self.assertIsNone(law.crime_name("Zq_Odd5"))
        self.assertEqual(law.crime_name("Battery (First Degree)"), "Battery (First Degree)")

    def test_money_sent_with_its_colon_unverified_shape(self):
        r = Lines().add(notice("Transfer Sent: You sent Zq_Pay3:\n5000 aUEC")).read()
        self.assertEqual(r.state.feed[-1]["text"], "You sent money to another player")
        self.assertEqual(r.state.session["withheld"], 0)

    # finding 6: a session change in the same file -------------------------------------------
    def test_lines_of_an_ended_session_are_scrubbed_with_its_own_names(self):
        old = Lines().add(notice("Zq_Old1 committed Homicide against you"))
        old.add(notice("Contract Accepted: Escort Zq_Old1 home", MID))
        new = Lines()
        new.lines[0] = new.lines[0].replace("27 Nov 26 (23 00 00)", "28 Nov 26 (01 00 00)")
        for keep in (False, True):
            mem = lib.MemoryLog(("\r\n".join(old.lines) + "\r\n").encode("utf-8"))
            r = pipeline.LogReader("Game.log", NAMES, opener=mem.opener, keep_events=keep)
            while r.poll() == "read":
                pass
            mem.data = bytearray(("\r\n".join(new.lines) + "\r\n").encode("utf-8"))   # the game started again
            for _ in range(3):
                r.poll()
            self.assertEqual(len(r.take_finished()), 1)
            out = json.dumps(r.take_lines())
            if keep:
                out += timeline.render_text(r, r.summary(True), show_all=True) + json.dumps(r.all_lines)
            self.assertIn("Escort another player home", out, keep)
            self.assertNotIn("Zq_Old1", out, keep)

    def test_a_session_line_inside_the_file_seals_the_old_lines(self):
        g = Lines().add(notice("Zq_Old2 committed Homicide against you"))
        g.add(notice("Contract Accepted: Escort Zq_Old2 home", MID))
        g.add('BackupNameAttachment=" Build(1) 28 Nov 26 (02 00 00)"  -- used by backup system')
        g.add(notice("Entered Hurston Dynamics Jurisdiction"))
        r = g.read()
        self.assertNotIn("Zq_Old2", timeline.render_text(r, r.summary(True), show_all=True) + json.dumps(r.all_lines))
        _, lines = take_all(g.lines)
        self.assertNotIn("Zq_Old2", json.dumps(lines))

    def test_a_name_forgotten_before_the_session_ended_stays_out_of_its_lines(self):
        # a killer's name with spaces: not found again by the hashes, only by the forgetting pass
        g = Lines().add(destroyed("Zq Spaced Killer"))
        g.add(notice("Contract Accepted: Escort Zq Spaced Killer home", MID))
        quiet_flood(g, MAX_OTHERS + 1)
        g.add('BackupNameAttachment=" Build(1) 28 Nov 26 (03 00 00)"  -- used by backup system')
        r = g.read()
        self.assertNotIn("Zq Spaced Killer", timeline.render_text(r, r.summary(True), show_all=True))

    # findings 7 to 9 and the scrubber's mutations ---------------------------------------------
    def test_past_the_budget_the_rest_of_a_run_is_hidden(self):
        crafted = ["-".join(["q"] * k) + "x%d" % k for k in range(1, 51)]       # 50 part counts
        st = forgotten_state(crafted + ["Zq_End9"])
        out = st.scrub("-".join(["ab"] * 600) + "-Zq_End9")
        self.assertNotIn("Zq_End9", out)
        self.assertIn(OTHER, out)

    def test_names_of_up_to_eight_part_counts_never_cut_a_nameless_run(self):
        names = ["Pa%d-" % i + "-".join("w%d" % j for j in range(p - 1)) if p > 1 else "Pa%d" % i
                 for i, p in enumerate([1 + (i % 8) for i in range(16)])]
        st = forgotten_state(names)
        for parts in (20, 40, 300):
            text = "-".join(["abc"] * parts)
            self.assertEqual(st.scrub(text), text, parts)
        st = forgotten_state(["-".join(["q"] * k) + "x%d" % k for k in range(1, 13)])     # 12 part counts
        text = "-".join(["abc"] * 20)                     # 174 lookups: within 8 * 20 + 64, not 8 * 20
        self.assertEqual(st.scrub(text), text)

    def test_hashes_first_then_the_known_names(self):
        st = forgotten_state(["Bob_Q-Smith"], keep=["Bob_Q"])
        self.assertEqual(st.scrub("Escort Bob_Q-Smith home"), "Escort another player home")
        self.assertEqual(st.scrub("Escort Bob_Q home"), "Escort another player home")

    def test_letters_re_i_takes_as_equal_share_a_branch(self):
        for names, text in ((["boſ-x", "bos"], "Escort boſ-x"), (["bıll-x", "bill"], "Escort bıll-x"),
                            (["σσσ-x", "σσς"], "Escort σσς-x")):
            st = State(NAMES)
            for n in names:
                st._other(n)
            self.assertEqual(st.scrub(text), "Escort another player", ascii(text))

    def test_a_killer_of_100_characters_is_kept(self):
        st = State(NAMES)
        name = "K" * 61 + "_" + "z" * 38
        st._other(name)
        self.assertEqual(st.scrub("Killed by %s" % name), "Killed by another player")

    def test_more_than_a_thousand_forgotten_names_stay_hidden(self):
        st = State(NAMES)
        first = "Zq_First1"
        st._other(first)
        for i in range(2600):                               # five forgetting passes: 2,500 hashes
            st._other("Fl_%05d" % i)
        self.assertNotIn(first, st._others)
        self.assertGreater(len(st._forgot_order), 1000)
        self.assertEqual(st.scrub("Escort %s home" % first), "Escort another player home")

    # the shard name ------------------------------------------------------------------------------
    def test_the_shard_name_is_in_the_private_form_only(self):
        r = Lines().read()
        pub, priv = r.state.to_dict(), r.state.to_dict(private=True)
        self.assertNotIn("pub_example_00000000_001", json.dumps(pub) + json.dumps(r.summary(True)))
        self.assertEqual(pub["server"]["count"], 1)
        self.assertEqual(priv["server"]["shard"], "pub_example_00000000_001")
        self.assertIn("Joining a server", [x["text"] for x in r.state.feed])


class ReferenceViewTest(unittest.TestCase):
    """The reference cards (PLAN §4 item 18): only a hand pick shows them, and no change of
    context, restart or session end drops that pick."""

    def test_it_stays_until_live_is_picked(self):
        g = Lines().add(notice("You have joined channel 'Drake Golem : Pilot_Example'."))
        st = g.read().state
        now = st.session["last_t"] + 1
        user = {"view": board.pick(st, None, "reference", True, now)}
        p = board.build(st, None, user, now)
        self.assertEqual((p["view"]["name"], p["view"]["auto"], p["view"]["mode"]), ("reference", "mining", "mining"))
        self.assertEqual(p["model"], {"view": "reference", "mode": "mining", "auto": "mining"})
        self.assertTrue(p["view"]["picked"])
        # a change of context: a jump
        g.add("[Notice] <Player Selected Quantum Target - Local> [ItemNavigation][CL][1] | NOT AUTH | DRAK_Golem_900000000010[900000000010]|"
              "CSCItemNavigation::OnPlayerSelectedQuantumTarget|Player has selected point LOC_RR_S2_L5 as their destination, routing locally [Team_X]")
        st = g.read().state                                   # a fresh reader: the restart
        p = board.build(st, None, user, st.session["last_t"] + 1)
        self.assertEqual((p["view"]["name"], p["view"]["auto"], p["view"]["pick_dropped"]), ("reference", "travel", False))
        # the session ends
        g.add("[Notice] <SystemQuit> CSystem::Quit invoked with - cause=30016, reason=Quit via console command, exitCode=0 [Team_X]")
        st = g.read().state
        p = board.build(st, None, user, st.session["last_t"] + 60, game_running=False)
        self.assertEqual((p["view"]["name"], p["view"]["auto"], p["view"]["mode"]), ("reference", "idle", "flight"))
        self.assertIsInstance(p["alerts"], list)
        self.assertIsInstance(p["timers"], list)
        self.assertIsNone(board.pick(st, None, "live"))       # Live: save no pick
        self.assertEqual(board.build(st, None, {"view": None}, st.session["last_t"] + 60, False)["view"]["name"], "idle")


if __name__ == "__main__":
    unittest.main()
