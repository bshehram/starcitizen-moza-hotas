"""State rules found in review: travel, the ship flown, queues, downings, respawn places, end
times, feed ids, other players' names, and what is not the user's. Each test names its rule."""
import ast
import json
import unittest

import scdash_testlib as lib
from scdash import events as E
from scdash import pipeline
from scdash.state import State, build_state, clock_facts
from scdash.summary import build_summary

S = "s"
HANDLE = "Pilot_Example"


def run(*evs):
    """Events with the session start and login put in front; offsets and times in order."""
    head = [E.SessionStart(S, 0, 0.0, S, None, None), E.Login(S, 1, 1.0, HANDLE),
            E.JoinServer(S, 2, 2.0, "x"), E.Spawned(S, 3, 3.0)]
    return build_state(head + list(evs))


def at(cls, offset, t, *args):
    return cls(S, offset, float(t), *args)


class TravelTest(unittest.TestCase):
    def test_a_plotted_route_is_not_a_jump(self):
        # "Player Requested Fuel to Quantum Target" logs route lines too [seen: 15 phantom jumps]
        st = run(at(E.RouteStart, 10, 10, "1", "New Babbage", "LOC_B"),
                 at(E.RouteFuel, 11, 10, "1", "LOC_B", 99.0))
        self.assertEqual(st.jumps, [])
        st = run(at(E.QuantumTarget, 10, 10, "DRAK_Golem", "1", "LOC_A"),
                 at(E.RouteFuel, 11, 10, "1", "LOC_A", 50.0),
                 at(E.RouteStart, 12, 20, "1", "ARC L4", "LOC_B"),
                 at(E.RouteFuel, 13, 20, "1", "LOC_B", 99.0))
        self.assertEqual(len(st.jumps), 1)
        self.assertEqual((st.quantum["target"], st.quantum["fuel"]), ("LOC_A", 50.0))

    def test_a_carriers_same_moment_selection_is_one_jump_for_the_boarded_ship(self):
        for order in ((("ORIG_m80", "1"), ("ANVL_Liberator", "2")), (("ANVL_Liberator", "2"), ("ORIG_m80", "1"))):
            st = run(at(E.ChannelJoined, 10, 10, "Origin M80", HANDLE),
                     at(E.QuantumTarget, 11, 20, order[0][0], order[0][1], "OOC_Stanton_1_Hurston"),
                     at(E.QuantumTarget, 12, 20, order[1][0], order[1][1], "OOC_Stanton_1_Hurston"),
                     at(E.QuantumArrived, 13, 60, "ORIG_m80", "1"))
            self.assertEqual(len(st.jumps), 1, order)
            self.assertEqual(st.quantum["vehicle_class"], "ORIG_m80", order)
            self.assertIsNotNone(st.quantum["arrived"], order)
            self.assertEqual((st.ship["name"], st.ship["class"]), ("Origin M80", "ORIG_m80"), order)
            lines = [x for x in st.feed if x["kind"] == "quantum_target"]
            self.assertEqual(len(lines), 1, order)

    def test_another_ships_arrival_is_not_the_users(self):
        st = run(at(E.QuantumTarget, 10, 10, "DRAK_Golem", "1", "LOC_A"),
                 at(E.QuantumArrived, 11, 30, "DRAK_Golem_OX", "9"))
        self.assertIsNone(st.quantum["arrived"])
        self.assertIsNone(st.location)


class ShipTest(unittest.TestCase):
    def test_a_ship_left_is_never_filled_in_with_another(self):
        st = run(at(E.ChannelJoined, 10, 10, "RSI Ursa Medivac", HANDLE),
                 at(E.ChannelLeft, 11, 20, "RSI Ursa Medivac", HANDLE),
                 at(E.SeatLeft, 12, 30, "ANVL_Liberator", "2"))
        self.assertEqual((st.ship["name"], st.ship["class"]), ("Anvil Liberator", "ANVL_Liberator"))

    def test_a_name_that_does_not_fit_is_not_filled_in(self):
        st = run(at(E.ChannelJoined, 10, 10, "RSI Ursa Medivac", HANDLE),
                 at(E.SeatLeft, 12, 30, "ANVL_Liberator", "2"))
        self.assertEqual(st.ship["name"], "Anvil Liberator")


class QueueTest(unittest.TestCase):
    def test_queue_closes_on_respawn_menu_disconnect_and_quit(self):
        q = at(E.HangarQueue, 10, 10, 2, 100.0)
        enders = [[at(E.Incapacitated, 11, 20), at(E.Spawned, 12, 40)],
                  [at(E.FrontEnd, 11, 20, "OnLobbyPostGameUnload")],
                  [at(E.Disconnected, 11, 20, 30016, "Remote Disconnect - Player requested disconnect", False)],
                  [at(E.Quit, 11, 20, 30016, "Quit via console command")]]
        for end in enders:
            st = run(q, *end)
            self.assertIsNone(st.hangar["queue"], end[-1].kind)
            self.assertFalse(clock_facts(st, 10 + 1000)["hangar_stuck"], end[-1].kind)
            self.assertEqual(st.hangar["waits"][-1]["ready"], None)


class HealthTest(unittest.TestCase):
    def test_a_medical_bed_ends_a_downing(self):
        st = run(at(E.Incapacitated, 10, 10), at(E.MedicalBed, 11, 60))
        self.assertEqual(st.health["status"], "ok")
        st2 = build_state([*_head(), at(E.Incapacitated, 10, 10), at(E.MedicalBed, 11, 60),
                           at(E.Quit, 12, 90, 30016, "Quit via console command")])
        self.assertEqual(st2.deaths, [])
        self.assertEqual(len(st2.recoveries), 1)

    def test_a_respawn_soon_after_the_bed_is_still_a_death(self):
        st = run(at(E.Incapacitated, 10, 10), at(E.MedicalBed, 11, 24), at(E.Spawned, 12, 33))
        self.assertEqual(len(st.deaths), 1)

    def test_a_respawn_keeps_the_place_logged_just_before_it(self):
        st = run(at(E.InventoryLocation, 5, 5, "0", "500", "0", "500"),
                 at(E.LocationInventory, 6, 5.1, "Stanton4_NewBabbage"),
                 at(E.Incapacitated, 10, 100),
                 at(E.InventoryLocation, 11, 130, "0", "500", "0", "777"),   # the hospital, ms before
                 at(E.Spawned, 12, 130.004),
                 at(E.LocationInventory, 13, 131, "Stanton4_NewBabbage"))
        self.assertEqual(st.location["code"], "Stanton4_NewBabbage")
        arrivals = [x for x in st.feed if x["text"].startswith("At ")]
        self.assertEqual(len(arrivals), 1)                    # not "At New Babbage" twice

    def test_moving_inside_a_place_is_not_leaving_it(self):
        st = run(at(E.InventoryLocation, 5, 5, "0", "500", "0", "500"),
                 at(E.LocationInventory, 6, 5.1, "Stanton4_NewBabbage"),
                 at(E.InventoryLocation, 7, 50, "500", "500", "500", "777"),
                 at(E.InventoryLocation, 8, 60, "500", "500", "777", "500"))
        self.assertEqual([x["text"] for x in st.feed if "Babbage" in x["text"]], ["At Stanton4_NewBabbage"])
        st = run(at(E.InventoryLocation, 5, 5, "0", "500", "0", "500"),
                 at(E.LocationInventory, 6, 5.1, "Stanton4_NewBabbage"),
                 at(E.InventoryLocation, 7, 50, "500", "0", "500", "900"))
        self.assertTrue(st.location["left"])


class EndTimeTest(unittest.TestCase):
    def test_no_quit_line_ends_at_the_last_line(self):
        data = lib.sample_bytes("run_a.log")
        cut = data.index(b"<2026-11-27T00:22:07")          # after the refinery notice
        tail = b"<2026-11-27T00:30:00.000Z> [Notice] <Nothing of interest> just a line [Team_X]\r\n"
        mem = lib.MemoryLog(data[:cut] + tail)
        r = pipeline.LogReader("x.log", lib.NAMES, opener=mem.opener)
        r.poll()
        r.finish()
        sm = r.summary(complete=True)
        self.assertEqual(sm["ended"]["t"], "2026-11-27T00:30:00.000Z")
        self.assertEqual(sm["end"], "2026-11-27T00:30:00.000Z")


class FeedIdTest(unittest.TestCase):
    def test_ids_are_unique_and_stable(self):
        a = pipeline.read_whole(lib.sample_path("courier.log"), lib.NAMES)
        b = pipeline.read_whole(lib.sample_path("courier.log"), lib.NAMES)
        ids = [x["id"] for x in a.all_lines]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, [x["id"] for x in b.all_lines])

    def test_a_changed_line_comes_out_again_with_its_id(self):
        data = lib.sample_bytes("run_a.log")
        target = data.index(b"<2026-11-26T23:19:04.767Z> [Notice] <Player Selected")
        route = data.index(b"<2026-11-26T23:19:04.767Z> [Notice] <Calculate Route>")
        mem = lib.MemoryLog(data[:route])
        r = pipeline.LogReader("x.log", lib.NAMES, opener=mem.opener)
        r.poll()
        first = [x for x in r.take_lines() if x["kind"] == "quantum_target"]
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["id"], "%d.0" % target)
        mem.data.extend(data[route:data.index(b"\n", data.index(b"fuel estimate", route)) + 1])
        r.poll()
        again = [x for x in r.take_lines() if x["kind"] == "quantum_target"]
        self.assertEqual([x["id"] for x in again], [first[0]["id"]])
        self.assertIn("fuel estimate 153,453", again[0]["text"])
        self.assertGreater(again[0]["rev"], 0)

    def test_recovery_line_has_its_own_id(self):
        st = State()
        lines = []
        for ev in [*_head(), at(E.Incapacitated, 10, 10), at(E.ShopBuy, 11, 100, "shop", "thing", 5.0, 1)]:
            lines += st.apply(ev)
        ids = [x["id"] for x in lines]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual([x["kind"] for x in lines[-2:]], ["recovered", "shop_buy"])


class OtherPlayersTest(unittest.TestCase):
    def test_other_players_names_never_leave_the_state(self):
        st = run(at(E.VehicleDestroyed, 10, 10, "AEGS_Gladius", "5", "77", "Combat", 0, 2, "Zed_Invented", "88"),
                 at(E.ContractAccepted, 11, 20, "Bounty on Zed_Invented", "e0000001-0000-4000-8000-000000000001"),
                 at(E.ObjectiveNew, 12, 20, "Find zed_invented near Lyria", "e0000001-0000-4000-8000-000000000001", None))
        public = json.dumps(st.to_dict())
        self.assertNotIn("Zed_Invented", public)
        self.assertNotIn("zed_invented", public)
        self.assertIn("Bounty on another player", public)
        summary = json.dumps(build_summary(st, complete=True))
        self.assertNotIn("Zed_Invented", summary)
        self.assertIn("Bounty on another player", summary)
        self.assertIn("Zed_Invented", json.dumps(st.to_dict(private=True)))   # memory only

    def test_another_players_channel_and_ejection_are_not_the_users(self):
        st = run(at(E.ChannelJoined, 10, 10, "Drake Cutlass Black", "OtherPilot"),
                 at(E.ThrownOut, 11, 20, "OtherPilot", "DRAK_Cutlass_Black", "5"))
        self.assertFalse(st.ship["own"])
        self.assertEqual(st.health["status"], "ok")
        self.assertIsNone(st._incident)
        self.assertNotIn("Boarded", " ".join(x["text"] for x in st.feed))

    def test_another_players_ship_destroyed_is_not_the_users(self):
        st = run(at(E.VehicleDestroyed, 10, 10, "AEGS_Gladius", "5", "77", "Combat", 0, 2, HANDLE, "1"))
        self.assertEqual(st.ships_lost, [])


class NoClockTest(unittest.TestCase):
    """The state, the events and the records never read the clock (PLAN §7), by any route."""

    FORBIDDEN = {("time", "time"), ("time", "monotonic"), ("time", "perf_counter"),
                 ("datetime", "now"), ("datetime", "utcnow"), ("datetime", "today"), ("date", "today")}

    def test_no_clock_calls_in_the_source(self):
        for name in ("records.py", "events.py", "state.py", "summary.py", "words.py", "names.py"):
            tree = ast.parse((lib.DASHBOARD / "scdash" / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    obj = node.func.value
                    base = obj.attr if isinstance(obj, ast.Attribute) else getattr(obj, "id", None)
                    self.assertNotIn((base, node.func.attr), self.FORBIDDEN, "%s line %d" % (name, node.lineno))
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mod = getattr(node, "module", None) or ""
                    names = {a.name for a in node.names}
                    self.assertFalse(mod == "time" and names & {"time", "monotonic", "perf_counter"},
                                     "%s imports a clock" % name)
                    self.assertFalse(mod == "datetime" and name not in ("summary.py", "words.py") and names & {"datetime", "date"},
                                     "%s imports datetime" % name)


def _head():
    return [E.SessionStart(S, 0, 0.0, S, None, None), E.Login(S, 1, 1.0, HANDLE),
            E.JoinServer(S, 2, 2.0, "x"), E.Spawned(S, 3, 3.0)]


if __name__ == "__main__":
    unittest.main()
