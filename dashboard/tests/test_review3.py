"""The faults the stage 3 review found, one test each (the review's numbers in the names), and
the reference view. Every built line here is invented and its shape unverified, as in
SURVEY.md: the tests say so in their names where they lean on such a shape."""
import json
import os
import unittest
from datetime import timedelta, timezone
from unittest import mock

import scdash_testlib as lib
from scdash import board, pipeline, timeline
from scdash import events as E
from scdash import plan as P
from scdash.state import MAX_OTHERS, State
from scdash.words import parse_time

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
