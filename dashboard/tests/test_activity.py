"""Stage 3's events and state: the new notice kinds, contract kinds from the reference table,
courier and hauling stops, the session's tally, a death from the body item, commodity
quantities, shop places, and the privacy of the names the law notices carry.

Real lines and built lines are kept apart (dashboard/SURVEY.md): `courier.log`, `markers.log`
and `run_a.log` are sanitized real lines; every `built_*.log` was written from the game's text
and other tools' parsers, so every test on one says "unverified" in its name: the line shape it
reads has not been seen in a log of the user's yet.
"""
import json
import unittest

import scdash_testlib as lib
from scdash import events as E
from scdash import pipeline, timeline
from scdash.refdata import RefData
from scdash.state import State, build_state
from scdash.summary import build_summary

NAMES = timeline.load_names()          # the real table: the built samples use real station codes
S = "s"
HANDLE = "Pilot_Example"
PID = "900000000003"


def read(name, names=NAMES):
    return pipeline.read_whole(lib.sample_path(name), names)


def run(*evs):
    head = [E.SessionStart(S, 0, 0.0, S, None, None), E.Character(S, 1, 0.5, PID, True),
            E.Login(S, 2, 1.0, HANDLE), E.JoinServer(S, 3, 2.0, "x"), E.Spawned(S, 4, 3.0)]
    return build_state(head + list(evs), NAMES)


def at(cls, offset, t, *args):
    return cls(S, offset, float(t), *args)


def public(st):
    return json.dumps(st.to_dict()) + json.dumps(build_summary(st, complete=True))


class NoticeKindsTest(unittest.TestCase):
    def test_new_kinds_unverified_shapes_are_read_before_the_catch_all(self):
        r = read("built_law.log")
        kinds = [e.kind for e in r.events]
        for k in ("monitored_down", "crime", "crimestat", "crime_against_you", "fined", "impounded", "reward"):
            self.assertIn(k, kinds)
        self.assertNotIn("notice", kinds)                      # nothing fell through to the catch-all
        crime = next(e for e in r.events if e.kind == "crime")
        self.assertEqual((crime.crime, crime.victim), ("Assault", "OtherPilot_2"))   # a split notice
        self.assertEqual(next(e for e in r.events if e.kind == "fined").amount, 1500.0)
        self.assertEqual(next(e for e in r.events if e.kind == "reward").amount, 50250.0)
        self.assertEqual(next(e for e in r.events if e.kind == "impounded").vehicle, "Drake Golem")
        for e in r.events:
            self.assertEqual(E.event_from_dict(e.to_dict()), e)

    def test_a_long_failed_notice_is_not_a_tip_unverified(self):
        # SURVEY.md §0.6: the hint rule would have hidden these two.
        text = 'Added notification "Contract Failed: Claim #4521: Drake Cutlass Black Salvage Rights: " [5] to queue'
        rec = type("R", (), {"text": text})
        ev = E._h_notice(rec, ("s", 0, 1.0))
        self.assertEqual((ev.kind, ev.title), ("contract_failed", "Claim #4521: Drake Cutlass Black Salvage Rights"))
        rec.text = 'Added notification "Objective Failed: Deliver 0/24 SCU of Agricium to MIC-L1 Shallow Frontier Station: " [6]'
        self.assertEqual(E._h_notice(rec, ("s", 0, 1.0)).kind, "objective_failed")

    def test_the_driver_id_is_kept(self):
        d = next(e for e in pipeline.read_whole(lib.sample_path("courier.log"), lib.NAMES).events
                 if e.kind == "vehicle_destroyed")
        self.assertEqual(d.driver_id, "0")
        old = d.to_dict()
        del old["driver_id"]                                  # a dict written before stage 3
        self.assertIsNone(E.event_from_dict(old).driver_id)


class ContractKindTest(unittest.TestCase):
    def test_courier_contracts_from_the_table(self):
        st = read("courier.log").state
        for c in st.contracts.values():
            self.assertEqual((c["kind"], c["view"], c["giver_name"]), ("delivery", "cargo", "FTL Courier"), c["internal"])
            self.assertEqual(c["lookup"], "contract")
        self.assertEqual(st.unmapped_contracts(), [])

    def test_lookup_order(self):
        ref = RefData()
        # a sub-contract index is stripped when the entry has that many subs [seen: menu_return.log]
        self.assertEqual(ref.contract("FTL_Courier_Stanton_Iron_Rank0_2", "FTL_Courier")["how"], "sub-contract")
        self.assertEqual(ref.contract("FTL_Courier_Stanton_Iron_Rank0_9", "FTL_Courier")["how"], "generator")
        # `also`: the contract another generator offers takes that generator's view
        info = ref.contract("HaulCargo_AToB_Interstellar_Bulk_Plas_Scr_Cob", "Covalex_Hauling")
        self.assertEqual((info["view"], info["how"]), ("cargo", "contract, also"))
        self.assertEqual(ref.contract(None, None, "ENTRY LVL. COURIER NEEDED IN STANTON")["how"], "title")
        self.assertEqual(ref.contract(None, None, "Defend Ruin Station from Outlaws")["how"], "title pattern")
        self.assertEqual(ref.contract("Example_Bounty_KillShip", "Example_Generator")["how"], "rule")
        unk = ref.contract("Example_Unlisted_Contract", "Example_Generator", "A Very Unusual Job")
        self.assertEqual((unk["kind"], unk["view"], unk["unmapped"]), ("unknown", "mission", True))

    def test_unknown_contract_is_listed_unverified_shape(self):
        st = read("built_unknown.log").state
        self.assertEqual(st.unmapped_contracts(), [{"contract": "Example_Unlisted_Contract",
                                                    "generator": "Example_Generator", "title": "A Very Unusual Job"}])
        self.assertEqual(st.to_dict()["unmapped_contracts"][0]["contract"], "Example_Unlisted_Contract")

    def test_failed_and_withdrawn_unverified_shapes(self):
        r = read("built_failed.log")
        cs = list(r.state.contracts.values())
        self.assertEqual([c["status"] for c in cs], ["failed", "withdrawn"])
        self.assertEqual(cs[0]["end_reason"], "Mission timer expired")
        self.assertEqual(cs[0]["objectives"][0]["state"], "failed")
        texts = [x["text"] for x in r.all_lines]
        self.assertEqual(texts.count("Contract failed: Opportunity for Independent Cargo Hauler"), 1)   # once
        self.assertNotIn("Contract fail:", " ".join(texts))
        sm = build_summary(r.state, complete=True)
        self.assertEqual([c["status"] for c in sm["contracts"]], ["failed", "withdrawn"])
        out = timeline.render_text(r, sm)
        self.assertIn("Opportunity for Independent Cargo Hauler (hauling, failed)", out)

    def test_end_status_words(self):
        st = run(at(E.ContractAccepted, 10, 10, "Job", "m1"), at(E.MissionEnded, 11, 20, "m1", "Fail", "x"),
                 at(E.ContractAccepted, 12, 30, "Job 2", "m2"), at(E.MissionEnded, 13, 40, "m2", "Deactivate", None))
        self.assertEqual([c["status"] for c in st.contracts.values()], ["failed", "withdrawn"])


class StopsTest(unittest.TestCase):
    def test_courier_pickup_and_drop_off(self):
        st = read("courier.log").state
        c = list(st.contracts.values())[1]                      # the Data Probe run
        stops = {o["stop"]["kind"]: o["stop"] for o in c["objectives"]}
        self.assertEqual((stops["pickup"]["item"], stops["pickup"]["place"]), ("Data Probe", "HUR-L1 Green Glade Station"))
        self.assertEqual((stops["dropoff"]["item"], stops["dropoff"]["place"]),
                         ("Data Probe", "HUR-L3 Thundering Express Station"))
        self.assertTrue(stops["pickup"]["verified"])
        self.assertEqual(stops["dropoff"]["index"], 0)
        # the drop-off got no notice of its own; the contract completing delivered it
        self.assertTrue(all(o["state"] == "complete" for o in c["objectives"]))

    def test_hauling_drop_offs_unverified_shape(self):
        st = read("built_hauling.log").state
        c = next(iter(st.contracts.values()))
        stops = [o["stop"] for o in c["objectives"]]
        self.assertEqual([(s["index"], s["amount"], s["total"], s["unit"], s["commodity"], s["place"]) for s in stops],
                         [(0, 16, 16, "SCU", "Quartz", "CRU-L1 Ambitious Dream Station"), (1, 0, 8, "SCU", "Quartz", "Orison")])
        self.assertFalse(any(s["verified"] for s in stops))
        self.assertEqual(c["kind"], "hauling")

    def test_boxes_unverified_shape(self):
        st = run(at(E.ContractAccepted, 10, 10, "Haul", "m1"),
                 at(E.ObjectiveNew, 11, 10, "Deliver 0/12 Cargo Boxes to Port Tressler", "m1", "dropoff_e0000001-0000-4000-8000-000000000001_2"))
        s = next(iter(st.contracts.values()))["objectives"][0]["stop"]
        self.assertEqual((s["unit"], s["total"], s["commodity"], s["index"]), ("boxes", 12, None, 2))


class TallyTest(unittest.TestCase):
    def test_kills_and_exclusions_unverified_shape(self):
        st = read("built_bounty.log").state
        # the Buccaneer once (crippled, then destroyed), the Gladius; not the wreck the game
        # removed (GameRules) and not the sentry (no maker code in front of its class)
        self.assertEqual(st.tally, {"destroyed": 2, "crippled": 0, "lost": 0, "downed": 0})
        texts = [x["text"] for x in st.feed]
        self.assertIn("You destroyed a Drake Buccaneer", texts)
        self.assertIn("You destroyed an Aegis Gladius", texts)
        self.assertIn("Removed nearby: Aegis Sabre", texts)
        c = next(iter(st.contracts.values()))
        self.assertEqual((c["view"], c["setting"]), ("combat", "ship"))

    def test_a_self_destruct_is_a_loss_whoever_the_killer_is(self):
        # records.log: the user's own Pisces, self-destructed, with another player as "killer" [seen]
        evs = [at(E.VehicleDestroyed, 10, 10, "ANVL_C8R_Pisces", "7", PID, "SelfDestruct", 0, 2, "OtherPilot_1", "88")]
        st = run(*evs)
        self.assertEqual((st.tally["lost"], st.tally["destroyed"]), (1, 0))
        st = run(at(E.VehicleDestroyed, 10, 10, "AEGS_Gladius", "5", "0", "SelfDestruct", 0, 2, HANDLE, PID))
        self.assertEqual(st.tally["destroyed"], 0)                # never trust the killer on a self-destruct

    def test_courier_session_lost_one_ship(self):
        st = read("courier.log").state
        self.assertEqual(st.tally["lost"], 1)
        self.assertEqual(st.tally["destroyed"], 0)

    def test_downings_are_counted(self):
        st = read("menu_return.log", lib.NAMES).state
        self.assertGreaterEqual(st.tally["downed"], 1)


class DeathTest(unittest.TestCase):
    def test_a_burst_that_starts_with_gear_is_not_the_users(self):
        st = run(at(E.ItemLost, 10, 100, "rsi_odyssey_undersuit_01_01_01", "Armor_Undersuit"),
                 at(E.ItemLost, 11, 100, "grin_tractor_01", "wep_stocked_2"))
        self.assertEqual(st.health["status"], "ok")
        self.assertIsNone(st._incident)
        st = run(at(E.ItemLost, 10, 100, "body_01_noMagicPocket", "Body_ItemPort"),
                 at(E.ItemLost, 11, 100, "grin_tractor_01", "wep_stocked_2"),
                 at(E.Spawned, 12, 130))
        self.assertEqual([d["items_lost"] for d in st.deaths], [2])

    def test_the_real_death_still_counts_its_items(self):
        st = read("courier.log").state
        self.assertEqual([(d["cause"], d["items_lost"]) for d in st.deaths], [("ship destroyed", 6)])


class TradeTest(unittest.TestCase):
    def test_commodity_quantities(self):
        st = read("markers.log", lib.NAMES).state
        buy = next(r for r in st.trade if r["kind"] == "commodity_buy")
        self.assertEqual((buy["scu"], round(buy["per_scu"], 2), buy["scu_verified"]), (32.0, 782.03, True))
        sell = next(r for r in st.trade if r["kind"] == "commodity_sell")
        self.assertEqual((sell["scu"], sell["scu_verified"]), (9.0, False))   # read as SCU [ref], unverified

    def test_commodity_name_and_shop_place_unverified_shape(self):
        st = read("built_hauling.log").state
        buy = next(r for r in st.trade if r["kind"] == "commodity_buy")
        self.assertEqual(buy["commodity"], "Medical Supplies")
        info = st.shop_info(buy)
        self.assertEqual((info["kind"], info["place"], info["place_from"]), ("commodity terminal", "new-babbage", "table"))
        # a chain's shared name takes its place from the last inventory location before the line
        st = run(at(E.LocationInventory, 10, 10, "RR_CRU_L1"),
                 at(E.CommoditySell, 11, 20, "SCShop_Admin_lt_base_g", "x", 100.0, "2", None))
        info = st.shop_info(st.trade[0])
        self.assertEqual((info["place"], info["place_from"]), ("cru-l1", "last inventory location"))

    def test_ship_info_unverified_shape(self):
        st = read("built_hauling.log").state
        info = st.to_dict()["ship"]["info"]
        self.assertEqual((info["name"], info["job"], info["cargo_scu"]), ("Drake Golem OX", "cargo", 64))


class LawPrivacyTest(unittest.TestCase):
    def test_names_in_law_notices_are_scrubbed_unverified_shape(self):
        r = read("built_law.log")
        out = public(r.state) + timeline.render_text(r, r.summary(complete=True)) + \
            json.dumps(timeline.render_json(r, r.summary(complete=True)))
        for name in ("OtherPilot_2", "OtherPilot_3", "Pilot_Example"):
            self.assertNotIn(name, out)
        self.assertIn("committed Assault against you", out)
        self.assertIn("another player", out)
        # The state keeps no law text with the name, private or not; the name is learned only.
        self.assertNotIn("OtherPilot_3", json.dumps(r.state.to_dict(private=True)))
        self.assertIn("OtherPilot_3", r.state._others)
        self.assertEqual(r.state.zone["monitored_down"], False)                    # restored again
        self.assertEqual([x["kind"] for x in r.state.law],
                         ["crime", "crimestat", "attacked", "fined", "impounded", "crimestat"])

    def test_sanitizer_knows_the_new_contexts(self):
        import sanitize
        lines = [
            '<2026-11-28T07:04:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Crime Committed: Assault',
            '<2026-11-28T07:04:00.000Z> against Vex_Invented: " [2] to queue.',
            '<2026-11-28T07:05:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Quill_Invented committed Assault against you: " [4]',
        ]
        san = sanitize.Sanitizer()
        san.learn("\n".join(lines))
        out = "\n".join(san.line(x) for x in lines)
        self.assertNotIn("Vex_Invented", out)
        self.assertNotIn("Quill_Invented", out)
        self.assertIn("against you", out)                       # "you" is not a name
        self.assertEqual(san.leftovers(out), [])


if __name__ == "__main__":
    unittest.main()
