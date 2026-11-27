"""Events to state: session life cycle, travel, arrivals, other people's ships, deaths, contracts."""
import json
import unittest
from dataclasses import replace
from unittest import mock

import scdash_testlib as lib
from scdash import events as E
from scdash import pipeline
from scdash.state import State, build_state, clock_facts
from scdash.summary import build_summary


def read(name):
    return pipeline.read_whole(lib.sample_path(name), lib.NAMES)


class RunATest(unittest.TestCase):
    """The afternoon of 2026-11-26: New Babbage -> ARC-L4 -> MIC-L2 in the Golem, OX home."""

    @classmethod
    def setUpClass(cls):
        cls.r = read("run_a.log")
        cls.st = cls.r.state

    def test_session_life_cycle(self):
        s = self.st.session
        self.assertEqual(s["id"], "Build(13220821) 26 Nov 26 (15 11 12)")
        self.assertEqual(s["game"], "ended")
        self.assertEqual(s["ended"]["how"], "quit")
        self.assertEqual(s["spawns"], 1)                     # the menu's own spawn is not counted
        self.assertEqual(s["version"], "4.10.201.48085")
        self.assertEqual(self.st.server["shard"], "pub_example_00000000_001")
        self.assertEqual([x["what"] for x in self.st.left_server], ["left"])   # the twin line counts once
        # in the world from 3:13:32 PM to the disconnect at 4:37:29 PM
        self.assertAlmostEqual(s["in_game_s"], 1 * 3600 + 23 * 60 + 57.4, delta=1)

    def test_game_state_steps(self):
        st = State(lib.NAMES)
        seen = []
        for ev in self.r.events:
            st.apply(ev)
            if not seen or seen[-1] != st.session["game"]:
                seen.append(st.session["game"])
        self.assertEqual(seen, ["menu", "in_game", "menu", "ended"])

    def test_quantum_travel(self):
        jumps = self.st.jumps
        self.assertEqual([j["target"] for j in jumps], ["LOC_RR_S3_L4", "LOC_RR_S4_L2", "NewBabbage_LOC"])
        self.assertEqual([j["start"] for j in jumps], ["New Babbage", "ARC L4", "MIC-L2 Long Forest Station"])
        self.assertAlmostEqual(jumps[0]["fuel"], 153453.046875)
        self.assertIsNotNone(jumps[0]["arrived"])
        self.assertIsNotNone(jumps[1]["arrived"])
        self.assertIsNone(jumps[2]["arrived"])                # the OX's jump logged no arrival [seen]
        self.assertEqual(jumps[2]["closed_by"], "docked")
        self.assertEqual(self.st.quantum["closed_by"], "docked")
        lines = [x["text"] for x in self.r.all_lines]
        self.assertIn("Quantum target: ARC-L4 Faint Glen Station, from New Babbage, fuel estimate 153,453", lines)

    def test_arrivals_and_departures(self):
        places = [p["code"] for p in self.st.places]
        self.assertEqual(places, ["Stanton4_NewBabbage", "LOC_RR_S3_L4", "LOC_RR_S4_L2", "RR_MIC_L2",
                                  "Stanton4_NewBabbage"])
        lines = [x["text"] for x in self.r.all_lines]
        self.assertIn("Left New Babbage", lines)
        self.assertIn("Left MIC-L2 Long Forest Station", lines)
        loc = self.st.location
        self.assertEqual((loc["code"], loc["docked"]), ("Stanton4_NewBabbage", True))

    def test_other_ships_are_not_the_users(self):
        own = set(self.st.vehicles)
        self.assertEqual(own, {"900000000014", "900000000037"})   # Golem and Golem OX
        self.assertEqual(self.st.ships_lost, [])               # the drone destroyed nearby is not ours
        stowed = [v for v in self.st.vehicles.values() if v["status"] == "stowed"]
        self.assertEqual(stowed, [])                           # the hangars' stows are other ships
        self.assertEqual(self.st.vehicles["900000000037"]["name"], "Drake Golem OX")

    def test_hangar_and_refinery(self):
        self.assertIsNone(self.st.hangar["queue"])
        w = self.st.hangar["waits"][0]
        self.assertEqual(w["wait_s"], 100.0)                   # the last estimate before it opened
        self.assertEqual(self.st.refinery[0]["station"], "MIC-L2 Long Forest Station")
        self.assertEqual([t["kind"] for t in self.st.trade], ["refinery_sell"])

    def test_preflight_pass(self):
        self.assertTrue(self.st.preflight["ok"])

    def test_handle_stays_private(self):
        d = json.dumps(self.st.to_dict())
        self.assertNotIn("Pilot_Example", d)
        self.assertIn("Pilot_Example", json.dumps(self.st.to_dict(private=True)))
        sm = json.dumps(build_summary(self.st, complete=True))
        self.assertNotIn("Pilot_Example", sm)
        self.assertNotIn("900000000003", sm)                  # the player id

    def test_no_wall_clock(self):
        with mock.patch("time.time", side_effect=AssertionError("wall clock read")):
            st = build_state(self.r.events, lib.NAMES)
            st.to_dict()
            build_summary(st, complete=True)
        self.assertEqual(st.to_dict(), self.st.to_dict())

    def test_clock_facts_take_now(self):
        st = State(lib.NAMES)
        for ev in self.r.events:
            st.apply(ev)
            if ev.kind == "hangar_queue":
                break
        q = st.hangar["queue"]
        self.assertFalse(clock_facts(st, q["joined"] + 100)["hangar_stuck"])
        self.assertTrue(clock_facts(st, q["joined"] + 401)["hangar_stuck"])


class CourierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = read("courier.log")
        cls.st = cls.r.state

    def test_contracts_one_per_mission_id(self):
        cs = list(self.st.contracts.values())
        self.assertEqual(len(cs), 5)
        self.assertEqual([c["status"] for c in cs], ["complete", "complete", "abandoned", "complete", "complete"])
        self.assertEqual(cs[0]["internal"], "FTL_Courier_Stanton_Food_Rank0")
        self.assertEqual(cs[0]["objective"], "Deliver Food Supplies To Storehouse")
        # the game announces a contract again after a relog: still one contract
        again = [e for e in self.r.events if e.kind == "contract_accepted"][0]
        st = build_state(self.r.events + [replace(again, offset=10**9, t=again.t + 9999)], lib.NAMES)
        self.assertEqual(len(st.contracts), 5)

    def test_blueprints(self):
        self.assertEqual([b["name"] for b in self.st.blueprints], ["Defiant", "Sedulity", "Endurance", "Colossus"])

    def test_death_and_respawn(self):
        self.assertEqual(len(self.st.deaths), 1)
        d = self.st.deaths[0]
        self.assertEqual(d["cause"], "ship destroyed")
        self.assertEqual(d["items_lost"], 6)
        self.assertEqual(self.st.health["status"], "ok")
        self.assertEqual(self.st.ships_lost[0]["reason"], "SelfDestruct")
        self.assertEqual(self.st.location["code"], "Stanton4_NewBabbage")     # where the respawn was


class MenuReturnTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = read("menu_return.log")
        cls.st = cls.r.state

    def test_return_to_menu_is_not_an_end(self):
        st = State(lib.NAMES)
        after_exit = None
        for ev in self.r.events:
            st.apply(ev)
            if ev.kind == "front_end" and ev.reason == "OnLobbyPostGameUnload" and after_exit is None:
                after_exit = (st.session["game"], st.session["ended"])
        self.assertEqual(after_exit, ("menu", None))
        self.assertEqual(self.st.session["spawns"], 2)       # back into the world after the menu
        self.assertEqual([x["what"] for x in self.st.left_server], ["menu", "left"])
        self.assertEqual(self.st.server["shards"], ["pub_example_00000000_001", "pub_example_00000000_002"])
        self.assertEqual(self.st.session["ended"]["how"], "quit")

    def test_downed_then_respawn_is_a_death(self):
        causes = [d["cause"] for d in self.st.deaths]
        self.assertEqual(causes, ["downed", "ship destroyed"])


class PreflightTest(unittest.TestCase):
    """Both the AB6 and the MTQ must be connected; their order does not matter (the user's
    report, 2026-11-27). A missing one is the red failure (12 AB6-missing launches)."""

    def test_stick_base_missing(self):
        st = read("preflight_fail.log").state
        self.assertIs(st.preflight["ok"], False)
        self.assertEqual(st.preflight["missing"], ["MOZA AB6 FFB Base"])
        self.assertEqual(st.preflight["text"], "AB6 not connected; joystick 1 is Joystick (Razer Huntsman V3 Pro)")

    def test_throttle_missing(self):
        st = read("preflight_no_mtq.log").state
        self.assertIs(st.preflight["ok"], False)
        self.assertEqual(st.preflight["missing"], ["MOZA MTQ Throttle Panel"])
        self.assertIn("MTQ not connected; joystick 1 is MOZA AB6 FFB Base", st.preflight["text"])

    def test_all_three_present_keyboard_first_passes(self):
        r = read("preflight_reordered.log")
        pf = r.state.preflight
        self.assertIs(pf["ok"], True)
        self.assertEqual((pf["order"], pf["missing"]), ("differs", []))
        self.assertIn("AB6 is joystick 3, MTQ is joystick 2", pf["text"])
        self.assertIn("which has worked", pf["text"])
        # never a failure on the way, not even between the second and the third joystick line
        st = State(lib.NAMES)
        for ev in r.events:
            st.apply(ev)
            self.assertIsNot(st.preflight["ok"], False, ev.kind)
        sm = build_summary(r.state, complete=True)["preflight"]
        self.assertEqual((sm["ok"], sm["order"], sm["missing"]), (True, "differs", []))

    def test_usual_order(self):
        st = read("run_a.log").state
        self.assertEqual((st.preflight["ok"], st.preflight["order"], st.preflight["missing"]), (True, "usual", []))

    def test_swapped_pair_passes(self):
        st = build_state([E.SessionStart("s", 0, 0.0, "s", None, None),
                          E.Joystick("s", 1, 1.0, 0, "MOZA MTQ Throttle Panel", "1101346E-0000-0000-0000-504944564944"),
                          E.Joystick("s", 2, 1.1, 1, "MOZA AB6 FFB Base", "1002346E-0000-0000-0000-504944564944")])
        self.assertIs(st.preflight["ok"], True)
        self.assertEqual(st.preflight["order"], "differs")

    def test_waits_before_failing(self):
        evs = [E.SessionStart("s", 0, 0.0, "s", None, None),
               E.Joystick("s", 1, 1.0, 0, "Joystick (Razer Huntsman V3 Pro)", "02A61532-0000-0000-0000-504944564944"),
               E.Joystick("s", 2, 1.1, 1, "MOZA MTQ Throttle Panel", "1101346E-0000-0000-0000-504944564944")]
        st = build_state(evs)
        self.assertIsNone(st.preflight["ok"])                 # the AB6 line may still come
        st.apply(E.Login("s", 3, 9.0, "Pilot_Example"))
        self.assertIs(st.preflight["ok"], False)


class RecoveryTest(unittest.TestCase):
    def test_up_again_without_respawn_is_not_a_death(self):
        s = "s"
        evs = [E.SessionStart(s, 0, 0.0, s, None, None), E.JoinServer(s, 1, 1.0, "x"),
               E.Spawned(s, 2, 2.0), E.Incapacitated(s, 3, 10.0),
               E.QuantumTarget(s, 4, 100.0, "DRAK_Golem", "1", "LOC_RR_S3_L4")]
        st = build_state(evs)
        self.assertEqual(st.deaths, [])
        self.assertEqual(len(st.recoveries), 1)
        self.assertEqual(st.health["status"], "ok")

    def test_items_without_respawn_are_not_a_death(self):
        s = "s"
        evs = [E.SessionStart(s, 0, 0.0, s, None, None), E.JoinServer(s, 1, 1.0, "x"), E.Spawned(s, 2, 2.0),
               E.ItemLost(s, 3, 10.0, "body_01", "Body_ItemPort"),
               E.ShopBuy(s, 4, 200.0, "shop", "thing", 10.0, 1)]
        st = build_state(evs)
        self.assertEqual(st.deaths, [])
        self.assertEqual(st.health["status"], "ok")


if __name__ == "__main__":
    unittest.main()
