"""Record to event: one test per marker, on sanitized real lines (samples/markers.log and friends)."""
import unittest

import scdash_testlib as lib
from scdash import events, pipeline


def parse(name):
    return pipeline.read_whole(lib.sample_path(name), lib.NAMES).events


def by_kind(evs):
    out = {}
    for ev in evs:
        out.setdefault(ev.kind, []).append(ev)
    return out


class MarkerEventsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = by_kind(parse("markers.log"))

    def one(self, kind):
        self.assertIn(kind, self.ev, kind)
        return self.ev[kind][0]

    def test_session_start(self):
        e = self.one("session_start")
        self.assertEqual(e.name, "Build(13220821) 26 Nov 26 (15 11 12)")
        self.assertEqual(e.build, "13220821")
        self.assertEqual(e.local, "26 Nov 26 (15 11 12)")
        self.assertEqual(e.session, e.name)

    def test_version_joystick_login_character(self):
        self.assertEqual(self.one("game_version").version, "4.10.201.48085")
        j = self.one("joystick")
        self.assertEqual((j.index, j.name, j.guid),
                         (0, "MOZA AB6 FFB Base", "1002346E-0000-0000-0000-504944564944"))
        self.assertEqual(self.one("login").handle, "Pilot_Example")
        c = self.one("character")
        self.assertEqual((c.player_id, c.current), ("900000000003", True))
        self.assertFalse(any("1000001" in str(v) for v in c.to_dict().values()))   # no account id

    def test_menu_server_spawn(self):
        self.assertEqual(self.one("front_end").reason, "ProcessBootRequest")
        self.assertEqual(self.one("join_server").shard, "pub_example_00000000_001")
        self.assertIn("connecting", self.ev)
        self.assertIn("spawned", self.ev)

    def test_disconnects_and_quit(self):
        d = {(e.cause, e.process) for e in self.ev["disconnected"]}
        self.assertIn((30016, False), d)
        self.assertIn((30013, True), d)                      # only on the Process twin [seen]
        self.assertIn((30028, False), d)
        reasons = [e.reason for e in self.ev["disconnected"]]
        self.assertIn("DisconnectCmd: disconnect light ExitToMenu", reasons)
        q = self.one("quit")
        self.assertEqual((q.cause, q.reason), (30016, "Quit via console command"))

    def test_quantum(self):
        t = self.one("quantum_target")
        self.assertEqual((t.vehicle_class, t.vehicle_id, t.code), ("DRAK_Golem", "900000000010", "LOC_RR_S3_L4"))
        r = self.one("route_start")
        self.assertEqual((r.start, r.code), ("New Babbage", "LOC_RR_S3_L4"))
        f = self.one("route_fuel")
        self.assertAlmostEqual(f.fuel, 153453.046875)
        a = self.one("quantum_arrived")
        self.assertEqual((a.vehicle_class, a.vehicle_id), ("DRAK_Golem", "900000000010"))
        self.assertIn("quantum_obstructed", self.ev)

    def test_places(self):
        i = self.one("inventory_location")
        self.assertEqual((i.landing_from, i.location_to), ("0", "900000000006"))
        self.assertEqual(self.one("location_inventory").code, "Stanton4_NewBabbage")
        p = self.one("planet_cells")
        self.assertEqual((p.body, p.cells), ("OOC_Stanton_4_Microtech", 233))
        self.assertEqual(self.one("jurisdiction").name, "microTech")
        self.assertEqual({e.inside for e in self.ev["armistice"]}, {True, False})
        self.assertEqual({e.inside for e in self.ev["monitored"]}, {True})

    def test_ships(self):
        r = self.one("ship_retrieved")
        self.assertEqual((r.vehicle_id, r.hangar), ("900000000010", "XL Hangar"))   # no handle kept
        s = self.one("seat_left")
        self.assertEqual((s.vehicle_class, s.vehicle_id), ("DRAK_Golem", "900000000010"))
        st = self.one("stowed")
        self.assertEqual(st.vehicle_id, "900000000008")
        d = self.one("vehicle_destroyed")
        self.assertEqual((d.vehicle_class, d.owner_id, d.reason, d.level_to),
                         ("AEGS_Sabre_Unmanned_Salvage", "0", "GameRules", 2))
        fc = self.one("fatal_collision")
        self.assertEqual((fc.vehicle_class, fc.zone, fc.player_pilot), ("ORIG_m80", "OOC_Stanton1_L2", True))
        j = self.one("channel_joined")
        self.assertEqual((j.name, j.owner), ("Drake Golem", "Pilot_Example"))
        self.assertEqual(self.one("channel_left").name, "Origin M80")

    def test_body(self):
        t = self.one("thrown_out")
        self.assertEqual((t.actor, t.vehicle_class), ("Pilot_Example", "ORIG_m80"))
        i = self.one("item_lost")
        self.assertEqual((i.item_class, i.port), ("body_01_noMagicPocket", "Body_ItemPort"))
        self.assertIn("incapacitated", self.ev)
        self.assertIn("emergency", self.ev)
        inj = self.one("injury")
        self.assertEqual((inj.severity, inj.part, inj.tier), ("Severe", "Torso", 1))
        self.assertIn("regen_set", self.ev)
        self.assertIn("medical_bed", self.ev)

    def test_contracts(self):
        a = self.one("contract_accepted")
        self.assertEqual((a.title, a.mission_id),
                         ("ENTRY LVL. COURIER NEEDED IN STANTON", "e0000001-0000-4000-8000-000000000001"))
        o = self.one("objective_new")
        self.assertEqual(o.text, "Deliver Food Supplies To Storehouse")
        oc = self.one("objective_complete")
        self.assertEqual(oc.text, "Collect Food Supplies From Security Compound")   # a split notice
        self.assertEqual(oc.objective_id, "pickup_e0000003-0000-4000-8000-000000000003_0")
        self.assertEqual(self.one("contract_complete").mission_id, a.mission_id)
        ends = {e.completion for e in self.ev["mission_ended"]}
        self.assertEqual(ends, {"Complete", "Abandon"})
        m = self.one("mission_marker")
        self.assertEqual((m.giver, m.contract), ("FTL_Courier", "FTL_Courier_Stanton_Food_Rank0"))

    def test_hangar_refinery_blueprint(self):
        h = self.one("hangar_queue")
        self.assertEqual((h.place, h.wait_s), (2, 200.0))
        self.assertIn("hangar_ready", self.ev)
        rd = self.ev["refinery_done"]
        self.assertEqual((rd[0].count, rd[0].station), (1, "MIC-L2 Long Forest Station"))
        self.assertEqual((rd[1].count, rd[1].station), (2, "MIC-L1 Shallow Frontier Station"))
        self.assertEqual(self.one("blueprint").name, "Defiant")

    def test_trade(self):
        b = self.one("shop_buy")
        self.assertEqual((b.shop, b.item, b.price, b.quantity),
                         ("SCShop_Platinumbay_small", "QDRV_JUST_S03_Agni_SCItem", 430920.0, 1))
        s = self.one("shop_sell")
        self.assertEqual((s.item, s.price), ("kegr_fire_extinguisher_01", 362.0))
        res = self.ev["shop_result"]
        self.assertEqual({(r.result, r.trade) for r in res}, {("Success", None), ("Success", "Buying")})
        cs = self.ev["commodity_sell"]
        self.assertEqual((cs[0].shop, cs[0].amount, cs[0].quantity, cs[0].box),
                         ("SCShop_CommEx_TDD_NewBabbage", 240279.0, "9", "1 x 2"))
        cb = self.one("commodity_buy")
        self.assertEqual((cb.price, cb.quantity), (25025.0, "3200.000000 cSCU"))
        self.assertEqual(self.one("refinery_sell").shop, "SCShop_RefineryAdmin_ORE")
        r = self.one("rental")
        self.assertEqual((r.item, r.price), ("GRIN_ROC", 2598.75))
        o = self.one("shop_offer")
        self.assertEqual(o.commodity, "ResourceType.Scrap")

    def test_misc(self):
        self.assertEqual(self.one("storage_count").count, 0)
        self.assertIn("fabricator_opened", self.ev)
        g = self.ev["gadget_placed"]
        self.assertEqual((g[0].gadget, g[0].rock), ("Mining_Gadget_SHIN_Sabir", "MineableRock_AsteroidEpic_Lindinium"))
        self.assertIsNone(g[1].rock)
        self.assertEqual(self.one("screenshot").name, "ScreenShot-2026-11-25_13-38-37-41E.jpg")
        self.assertEqual(self.one("profile_loaded").name, "MOZA.xml")

    def test_identity_is_session_and_offset(self):
        evs = parse("markers.log")
        idents = [e.ident for e in evs]
        self.assertEqual(len(idents), len(set(idents)))
        data = lib.sample_bytes("markers.log")
        for e in evs:
            self.assertEqual(data[e.offset:e.offset + 1], b"<")

    def test_round_trip(self):
        for e in parse("markers.log"):
            self.assertEqual(events.event_from_dict(e.to_dict()), e)


class NoticeTextTest(unittest.TestCase):
    def test_markup_is_stripped(self):
        self.assertEqual(events.notice_text("<EM4>Contract Accepted</EM4>:  Haul [BP] [50/150 Rep]: "),
                         "Contract Accepted: Haul")

    def test_session_id_of_other_first_lines(self):
        self.assertTrue(events.session_id(b"<2026> something else").startswith("log-"))


if __name__ == "__main__":
    unittest.main()
