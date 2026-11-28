"""No line may stall the reader (PLAN §7, §8), however it is shaped: 60 KB lines of many kinds,
for every key the parser reads, each built to hit the patterns' weak spots (long runs of the
words they look for, brackets, quotes, spaces, team tags, notices split in eight pieces). Each
line must be read, applied and turned into a payload in a small fraction of a second.

The stage 3 review found one notice taking 158 s, a marker 8.9 s and a notice of brackets 43 s;
the cap on a record's text (events.MAX_TEXT) and the bounded patterns are what this holds.
Also the memory the state keeps for long texts, and names.find_place on long text."""
import gc
import time
import tracemalloc
import unittest

import scdash_testlib as lib
from scdash import board, events, pipeline, timeline
from scdash.names import MAX_FOUND

K = 60000
FIRST = b'<2026-11-28T07:00:00.000Z> BackupNameAttachment=" Build(1) 27 Nov 26 (23 00 00)"  -- used by backup system\r\n'
T = "<2026-11-28T07:00:01.000Z> "
NAMES = timeline.load_names()
LIMIT_S = 0.15                       # per line: reading, applying, and one payload


def notice(text, tail=True):
    end = '" [7] to queue. New queue size: 1, MissionId: [e0000001-0000-4000-8000-000000000001], ObjectiveId: [dropoff_e0000002-0000-4000-8000-000000000002_0] [Team_CoreGameplayFeatures][Missions][Comms]'
    return "[Notice] <SHUDEvent_OnNotification> Added notification \"%s%s" % (text, end if tail else "")


def tag(key, body):
    return "[Notice] <%s> %s" % (key, body)


def rep(s, n=None):
    return s * ((n or K) // max(1, len(s)))


def hostile_lines():
    """(name, [physical lines]) for every kind the reader has a handler for."""
    out = []
    texts = {
        "accepted dead saints": "Contract Accepted:  DEAD SAINTS - " + rep(" Rank - ") + "x",
        "accepted bounty": "Contract Accepted:  Verified Bounty: " + rep(" at") + " | x |",
        "failed": "Contract Failed: " + rep("A"),
        "crime against": "Crime Committed: " + rep("against "),
        "crime spaces": "Crime Committed: x" + rep(" ") + "y",
        "attacked": "y" + rep("y") + " committed " + rep(" against"),
        "attacked words": "Evil_X committed " + rep("x ") + "against you",
        "deliver of": "New Objective: Deliver 1/2 SCU of" + rep(" of"),
        "collect from": "New Objective: Collect" + rep(" From"),
        "deliver to": "New Objective: Deliver" + rep(" To"),
        "channel": "You have joined channel '" + rep(" : a"),
        "jurisdiction": "Entered" + rep(" Jurisdiction x"),
        "injury": "Severe Injury Detected - " + rep(" - Tier x"),
        "brackets": rep("["),
        "markup": rep("<EM1>[BP]*[50/150 Rep"),
        "quotes": rep('" ['),
        "refinery": "A Refinery Work Order has been Completed at " + rep("at "),
        "awarded": "Awarded " + rep(",") + " aUEC",
    }
    for name, text in texts.items():
        out.append(("notice " + name, [T + notice(text)]))
    # a notice in eight pieces, the most the record layer joins
    piece = rep(" Rank - ", K // 8)
    out.append(("notice in 8 pieces", [T + notice("Contract Accepted:  DEAD SAINTS - " + piece, tail=False)]
                + [T + piece] * 6 + [T + piece + notice("", tail=True)[len("[Notice] <SHUDEvent_OnNotification> Added notification \""):]]))
    out.append(("notice never closed", [T + notice(rep("["), tail=False)] + [T + rep("[")] * 7))
    bodies = {
        "CLocalMissionPhaseMarker::CreateMarker": [
            "Creating objective marker: missionId [x], generator name [" + rep("G") + "], contract [c]",
            "Creating objective marker: missionId [x], generator name [g], contract [" + rep("_RG_") + "]"],
        "Vehicle Destroyed": [rep("Vehicle 'a' [1] class 'b' (owner player [1], driver [1]) destroyed: reason [a] level [0] -> [1] "),
                              "Vehicle '" + rep("'")],
        "CEntityComponentShopUIProvider::SendShopBuyRequest": [rep("shopName[x] client_price[1] "), rep("itemName[")],
        "CEntityComponentShopUIProvider::RmShopFlowResponse": [rep("shopName[x] "), rep("result[")],
        "CEntityComponentCommodityUIProvider::SendCommoditySellRequest": [rep("shopName[x] amount[1] resourceGUID[a] ")],
        "CEntityComponentCommodityUIProvider::SendCommodityBuyRequest": [rep("shopName[x] price[1] resourceGUID[a] ")],
        "CEntityComponentShoppingProvider::SendRentalRequest": [rep("shopName[x] client_price[1] ")],
        "CEntityComponentCommodityUIProvider::LoadShopInventoryData::<lambda_1": [rep("shopName[x] ")],
        "CEntityComponentMiningShopUIProvider::OnRefineryRequest": [rep("SShopRefineryRequest shopName[")],
        "Calculate Route": [rep("Projected Start Location is "), "| " + rep("a_1"), rep("Successfully calculated route to ")],
        "Player Selected Quantum Target - Local": [rep("selected point "), "| " + rep("a_1") + "selected point x"],
        "Quantum Drive Arrived - Arrived at Final Destination": ["| " + rep("a_1")],
        "Vehicle Control Flow": [rep("ClearDriver: releasing control token for 'a_"), "ClearDriver: " + rep("x")],
        "InventoryManagement": [rep("InventoryDataRequest Successful for Inventory[1:Location:1] ")],
        "EndMission": [rep("MissionId[x] "), "MissionId[x] " + rep("CompletionType[")],
        "FatalCollision": ["for vehicle a_1 [" + rep("Zone: x")],
        "LandingArea_UnregisterFromExternalSystems_StowingVehicle": [rep("[STOWING ON UNREGISTER] ")],
        "[ActorState] Dead": ["Actor 'a' [1] ejected from zone '" + rep("a_1")],
        "Adding non kept item [CSCActorCorpseUtils::PopulateItemPortForItemRecoveryEntitlement]": ["Item '" + rep(" - Class(a)")],
        "[ActorState] Place": ["placed 'Mining_Gadget_" + rep("a_1")],
        "AccountLoginCharacterStatus_Character": ["geid 1 " + rep(" state")],
        "Legacy login response": ["User Login Success - Handle[" + rep("a")],
        "Join PU": [rep("shard[")],
        "Update Inventory Location": ["Landing [1] -> [1]. Location [1] -> [" + rep("1")],
        "RequestLocationInventory": ["requested inventory for Location[" + rep("a")],
        "Channel Disconnected": ['cause=1 reason="' + rep("a")],
        "SystemQuit": [rep("cause=1, reason=")],
        "InvalidateAllTerrainCells": [rep("Planet ")],
        "ReuseChannel": [rep("blueprint_library")],
        "CEntityComponentShipListProvider::SetVehicleSpawningInformations": [
            "SetVehicleSpawningInformations - VehicleEntityId: [1], LandingArea: " + rep("[Team_a]") + "x",
            "SetVehicleSpawningInformations - VehicleEntityId: [1], LandingArea: " + rep("a's ")],
    }
    for key, items in bodies.items():
        for i, body in enumerate(items):
            out.append(("%s %d" % (key, i), [T + tag(key, body)]))
    # a spawn line left open, then pieces of team tags with no end
    out.append(("spawn info in pieces", [T + tag("CEntityComponentShipListProvider::SetVehicleSpawningInformations",
                                                 "SetVehicleSpawningInformations - VehicleEntityId: [1], LandingArea: a's")]
                + [T + rep("[Team_a]") + "x"] * 7))
    prefix = {
        "joystick": "- Connected joystick0: a" + rep(" ") + "b",
        "joystick guid": "- Connected joystick0: " + rep("{0"),
        "planet cells": "  planet cells: 1 " + rep(" name:"),
        "screenshot": "ScreenShot: " + rep("/"),
        "profile": "%SAVEDATA%/Controls/Mappings/" + rep(" loaded"),
        "file version": "FileVersion: " + rep("4."),
    }
    for name, line in prefix.items():
        out.append(("prefix " + name, [T + line]))
    for name in ("spawned", "front end", "connect"):
        key = {"spawned": "CSessionManager::OnClientSpawned", "front end": "CSessionManager::RequestFrontEnd",
               "connect": "CSessionManager::ConnectCmd"}[name]
        out.append(("bracket " + name, [T + "[%s] " % key + rep('Started - RequestFrontEndReason="')]))
    return out


def read(lines, first=FIRST):
    data = first + b"".join(x.encode("utf-8") + b"\r\n" for x in lines)
    mem = lib.MemoryLog(data)
    r = pipeline.LogReader("Game.log", NAMES, opener=mem.opener)
    while r.poll() == "read":
        pass
    r.finish()
    return r


class HostileLinesTest(unittest.TestCase):
    def test_no_line_takes_more_than_a_fraction_of_a_second(self):
        slow = []
        for name, lines in hostile_lines():
            t0 = time.perf_counter()
            r = read(lines)
            p = board.build(r.state, None, None, 1.8e9, game_running=True)
            dt = time.perf_counter() - t0
            if dt > LIMIT_S:
                slow.append("%s: %.2f s" % (name, dt))
            self.assertEqual(p["problems"], [], name)
        self.assertEqual(slow, [], "lines that stall the reader")

    def test_a_hostile_first_line(self):
        # The session pattern backtracked over a run of spaces for minutes before it was bounded.
        first = b'<2026-11-28T07:00:00.000Z> BackupNameAttachment=" Build(1) ' + b" " * K + b'x'
        t0 = time.perf_counter()
        sid = events.session_id(first)
        self.assertLess(time.perf_counter() - t0, LIMIT_S)
        self.assertTrue(sid.startswith("log-"))
        t0 = time.perf_counter()
        r = read([T + notice("Contract Accepted:  x")], first=first + b"\r\n")
        self.assertLess(time.perf_counter() - t0, LIMIT_S)
        self.assertEqual(len(r.state.contracts), 1)

    def test_texts_are_cut_where_they_are_parsed(self):
        r = read([T + notice("Contract Accepted:  " + rep("T")),
                  T + notice("New Objective: Deliver %s To %s" % (rep("I", 30000), rep("P", 30000)))])
        c = next(iter(r.state.contracts.values()))
        self.assertLessEqual(len(c["title"]), events.MAX_TEXT)
        self.assertLessEqual(len(c["objectives"][0]["text"]), events.MAX_TEXT)


class LongTextMemoryTest(unittest.TestCase):
    """30 contracts with 20 objectives each, every one 45 KB long: what the state keeps stays
    small (before the cap it was 69 MB in the stage 3 review)."""

    def test_the_state_keeps_little_for_long_texts(self):
        lines = []
        for c in range(30):
            mid = "e%07d-0000-4000-8000-%012d" % (c, c)
            lines.append(T + notice("Contract Accepted:  Job %d" % c).replace("e0000001-0000-4000-8000-000000000001", mid))
            for o in range(20):
                text = "New Objective: Deliver %s To %s" % (("I%d.%d " % (c, o)) * 2500, "P" * 30000)
                lines.append(T + notice(text).replace("e0000001-0000-4000-8000-000000000001", mid)
                             .replace("dropoff_e0000002-0000-4000-8000-000000000002_0", "dropoff_%s_%d" % (mid, o)))
        data = FIRST + b"".join(x.encode("utf-8") + b"\r\n" for x in lines)
        mem = lib.MemoryLog(data)
        del lines, data
        gc.collect()
        tracemalloc.start()
        try:
            r = pipeline.LogReader("Game.log", NAMES, opener=mem.opener)
            while r.poll() == "read":
                pass
            r.finish()
            mem.data = bytearray()
            gc.collect()
            held, _ = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        n = sum(len(c["objectives"]) for c in r.state.contracts.values())
        self.assertEqual(n, 600)
        self.assertLess(held, 8 * 1024 * 1024, "%.1f MB held" % (held / 1e6))

    def test_find_place_neither_scans_nor_keeps_long_text(self):
        n = timeline.load_names()
        n.find_place("warm up the index")
        t0 = time.perf_counter()
        self.assertIsNone(n.find_place("Q" * 480000))
        self.assertLess(time.perf_counter() - t0, 0.01)
        for i in range(MAX_FOUND + 100):
            n.find_place("%d" % i + "Q" * 300)
        self.assertLessEqual(len(n._found), MAX_FOUND)
        self.assertTrue(all(len(k) <= 200 for k in n._found))


if __name__ == "__main__":
    unittest.main()
