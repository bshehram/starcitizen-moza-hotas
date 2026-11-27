"""Hardening from the second review: the user's handle never reaches public output, hostile
values cannot break the output, ship names fit classes exactly, and an event that fails to
apply cannot stop the reader."""
import json
import math
import unittest
from unittest import mock

import scdash_testlib as lib
from scdash import events as E
from scdash import pipeline
from scdash.state import State, build_state
from scdash.summary import build_summary
from scdash.words import compatible, fit, iso

T = "<2026-11-26T23:%02d:%02d.000Z> "
FIRST = b'<2026-11-26T23:11:20.067Z> BackupNameAttachment=" Build(1) 26 Nov 26 (15 11 12)"  -- used by backup system\r\n'


def line(minute, second, body):
    return (T % (minute, second) + body + "\r\n").encode("utf-8")


def read(data):
    mem = lib.MemoryLog(data)
    r = pipeline.LogReader("Game.log", lib.NAMES, opener=mem.opener, keep_events=True)
    r.poll()
    r.finish()
    return r


LOGIN = "[Notice] <Legacy login response> [CIG-net] User Login Success - Handle[Zed_Handle] - Time[1] [Team_GameServices][Login]"
JOIN = "[Notice] <Join PU> address[192.0.2.1] port[1] shard[pub_example_1] locationId[1] [Team_GameServices][GIM][Matchmaking]"
SPAWN = "[CSessionManager::OnClientSpawned] Spawned!"
CONNECT = "[CSessionManager::ConnectCmd] Connect started!"
RETRIEVE = ("[Notice] <CEntityComponentShipListProvider::SetVehicleSpawningInformations> "
            "SetVehicleSpawningInformations - VehicleEntityId: [900000000001], LandingArea: Zed_Handle's")
CONTRACT = ('[Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted:  Escort Zed_Handle home: " [5] '
            "to queue. New queue size: 1, MissionId: [e0000001-0000-4000-8000-000000000001], ObjectiveId: [] "
            "[Team_CoreGameplayFeatures][Missions][Comms]")


class HandleTest(unittest.TestCase):
    def check(self, r):
        public = json.dumps(r.state.to_dict()) + json.dumps(r.summary(complete=True))
        self.assertNotIn("zed_handle", public.lower())
        self.assertIn("Escort you home", public)
        self.assertEqual(r.state.vehicles["900000000001"]["hangar"], "XL Hangar")
        self.assertIn("Zed_Handle", json.dumps(r.state.to_dict(private=True)))   # memory only

    def test_ship_retrieval_on_one_line(self):
        data = FIRST + line(11, 39, LOGIN) + line(12, 58, JOIN) + line(12, 58, CONNECT) + line(13, 32, SPAWN) \
            + line(14, 48, RETRIEVE + " XL Hangar [Team_GameServices][ASOP]") + line(15, 0, CONTRACT)
        self.check(read(data))

    def test_ship_retrieval_on_two_lines(self):
        data = FIRST + line(11, 39, LOGIN) + line(12, 58, JOIN) + line(12, 58, CONNECT) + line(13, 32, SPAWN) \
            + line(14, 48, RETRIEVE) + line(14, 48, "XL Hangar [Team_GameServices][ASOP]") + line(15, 0, CONTRACT)
        self.check(read(data))


class HostileValuesTest(unittest.TestCase):
    def test_hostile_file_cannot_break_the_output(self):
        big = "9" * 400
        rows = [
            b'<9999-11-26T23:12:00.000Z> [Notice] <Join PU> address[1] port[1] shard[pub_bad_1] locationId[1] [Team_X]\r\n',
            b'<0001-11-26T23:12:00.000Z> [Notice] <Join PU> address[1] port[1] shard[pub_bad_2] locationId[1] [Team_X]\r\n',
            line(12, 58, JOIN), line(12, 58, CONNECT), line(13, 32, SPAWN),
            line(14, 0, "[Notice] <Player Selected Quantum Target - Local> [ItemNavigation][CL][1] | NOT AUTH | "
                        "DRAK_Golem_900000000001[900000000001]|CSCItemNavigation::OnPlayerSelectedQuantumTarget|"
                        "Player has selected point LOC_RR_S3_L4 as their destination, routing locally [Team_CGP4][QuantumTravel]"),
            line(14, 0, "[Notice] <Calculate Route> [ItemNavigation][CL][1] | NOT AUTH | DRAK_Golem_900000000001[900000000001]"
                        "|CSCItemNavigation::CalculateRoute|Successfully calculated route to LOC_RR_S3_L4 fuel estimate %s "
                        "[Team_CGP4][QuantumTravel]" % big),
            line(14, 10, '[Notice] <SHUDEvent_OnNotification> Added notification "Joined hangar queue.'),
            line(14, 10, 'Your place: 2. Max. estimated wait: %s s.: " [3] to queue. New queue size: 1, MissionId: '
                         '[00000000-0000-0000-0000-000000000000], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]' % big),
            line(14, 20, "[Notice] <InventoryManagement> Freight Inventory Grid InventoryDataRequest Successful for "
                         "Player[x] Inventory[1:Location:2] Inventory Result Item Count:[%s]. [Team_X]" % big),
            line(14, 30, "[Notice] <SystemQuit> CSystem::Quit invoked with - cause=30016, reason=Quit via console command, exitCode=0 [Team_Unknown][System]"),
        ]
        r = read(FIRST + b"".join(rows))
        self.assertEqual(r.state.session["unreadable"], 5)
        self.assertEqual(r.state.server["shards"], ["pub_example_1"])
        self.assertIsNone(r.state.quantum["fuel"])
        self.assertIsNone(r.state.hangar["queue"])        # closed at the quit; the wait never came in
        json.dumps(r.state.to_dict(), allow_nan=False)
        json.dumps(r.state.to_dict(private=True), allow_nan=False)
        json.dumps(r.summary(complete=True), allow_nan=False)

    def test_iso_never_raises(self):
        for t in (1e20, -1e15, float("inf"), float("-inf"), float("nan"), 253402300800.0):
            self.assertIsNone(iso(t))
        self.assertEqual(iso(1795734680.067), "2026-11-26T23:11:20.067Z")

    def test_numbers_must_be_finite_and_short(self):
        self.assertFalse(math.isinf(E._num("1" * 25)))
        for bad in ("9" * 400, "1" * 31):
            with self.assertRaises(ValueError):
                E._num(bad)
            with self.assertRaises(ValueError):
                E._int(bad)


class FitTest(unittest.TestCase):
    REAL = [("Anvil C8R Pisces Rescue", "ANVL_C8R_Pisces"), ("Drake Golem", "DRAK_Golem"),
            ("Drake Golem OX", "DRAK_Golem_OX"), ("Anvil Liberator", "ANVL_Liberator"), ("Origin M80", "ORIG_m80"),
            ("RSI Ursa Medivac", "RSI_Ursa_Medivac"), ("Aegis Avenger Titan", "AEGS_Avenger_Titan"),
            ("RSI Salvation", "RSI_Salvation"), ("RSI Perseus", "RSI_Perseus"), ("Greycat ROC", "GRIN_ROC"),
            ("Gatac Hyun", "GAMA_Hyun"), ("Drake Corsair", "DRAK_Corsair")]

    def test_the_twelve_real_pairs(self):
        for name, cls in self.REAL:
            self.assertTrue(compatible(name, cls), (name, cls))
        self.assertFalse(compatible("Drake Golem OX", "DRAK_Golem"))
        self.assertFalse(compatible("Drake Golem", "DRAK_Golem_OX"))
        self.assertFalse(compatible("RSI Ursa Medivac", "ANVL_Liberator"))
        self.assertTrue(compatible("Gatac Hyūn", "GAMA_Hyun"))

    def test_mk_forms(self):
        for name in ("Anvil Hornet Mk II", "Anvil Hornet MkII", "Anvil Hornet Mk 2", "Anvil Hornet Mk2"):
            self.assertEqual(fit(name, "ANVL_Hornet_Mk2"), 2, name)
            self.assertEqual(fit(name, "ANVL_Hornet_MkII"), 2, name)
        self.assertFalse(compatible("Anvil Hornet Mk II", "ANVL_Hornet_Mk1"))

    def test_exact_class_beats_a_shorter_one(self):
        self.assertEqual(fit("Aegis Avenger Titan Renegade", "AEGS_Avenger_Titan_Renegade"), 2)
        self.assertEqual(fit("Aegis Avenger Titan Renegade", "AEGS_Avenger_Titan"), 1)
        s = "s"
        evs = [E.SessionStart(s, 0, 0.0, s, None, None), E.Login(s, 1, 1.0, "Pilot_Example"),
               E.JoinServer(s, 2, 2.0, "x"), E.Spawned(s, 3, 3.0),
               E.ChannelJoined(s, 10, 10.0, "Aegis Avenger Titan Renegade", "Pilot_Example"),
               E.QuantumTarget(s, 11, 20.0, "AEGS_Avenger_Titan", "1", "LOC_A"),
               E.QuantumTarget(s, 12, 20.0, "AEGS_Avenger_Titan_Renegade", "2", "LOC_A")]
        st = build_state(evs)
        self.assertEqual(len(st.jumps), 1)
        self.assertEqual(st.quantum["vehicle_id"], "2")
        self.assertEqual((st.ship["vehicle_id"], st.ship["class"]), ("2", "AEGS_Avenger_Titan_Renegade"))


class ApplyFailureTest(unittest.TestCase):
    def test_an_event_that_fails_to_apply_does_not_stop_the_reader(self):
        with mock.patch.object(State, "_on_join_server", side_effect=RuntimeError("broken handler")):
            r = pipeline.read_whole(lib.sample_path("run_a.log"), lib.NAMES)
        self.assertEqual(r.apply_errors, 1)
        self.assertEqual(r.state.session["unreadable"], 1)
        self.assertEqual(r.state.session["game"], "ended")   # everything after it was still applied
        self.assertEqual(len(r.state.jumps), 3)


if __name__ == "__main__":
    unittest.main()
