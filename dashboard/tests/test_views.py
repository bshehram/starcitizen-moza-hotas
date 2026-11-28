"""Stage 3's payload (board.build): the view rules in order on real sessions and built ones, the
alerts and timers by event time (a restart raises nothing old), the hand pick, and the models.

Tests on a `built_*.log` say "unverified" in their names: those line shapes come from the
game's text and other tools' parsers, not from a log of the user's (dashboard/SURVEY.md)."""
import json
import unittest
from datetime import timedelta, timezone
from unittest import mock

import scdash_testlib as lib
from scdash import board, pipeline, timeline
from scdash import plan as P
from scdash.refdata import RefData
from scdash.state import State
from scdash.words import clock, parse_time

NAMES = timeline.load_names()
PACIFIC = timezone(timedelta(hours=-8), "PST")
T = parse_time


def read(name):
    return pipeline.read_whole(lib.sample_path(name), NAMES)


def plan_of(raw):
    plan, skipped = P.normalize(raw)
    assert not skipped, skipped
    return plan


# A plan written for the afternoon of 2026-11-26 (samples/run_a.log): Tungsten at ARC-L4, refined
# at MIC-L2, the OX hauls the lots home to New Babbage.
RUN_A = plan_of({
    "updated": "2026-11-26T15:00:00-08:00",
    "objectives": [{"id": "ore", "title": "Ore for the drives", "status": "in_progress",
                    "next_step": "Run A: Tungsten at ARC-L4",
                    "materials": [{"name": "Tungsten", "need_scu": 2.22, "held_scu": 0.4, "min_quality": 600}]}],
    "runs": [{"id": "run-a", "name": "Run A", "kind": "mining", "status": "in_progress", "targets": ["Tungsten"],
              "legs": [{"to": "ARC-L4 field", "codes": ["LOC_RR_S3_L4"], "view": "mining", "do": "Mine Tungsten"},
                       {"to": "MIC-L2", "codes": ["LOC_RR_S4_L2", "RR_MIC_L2"], "view": "refinery", "refine": ["Tungsten"]},
                       {"to": "New Babbage", "codes": ["NewBabbage_LOC", "Stanton4_NewBabbage"], "view": "cargo",
                        "do": "Haul the lots home"}]}],
    "timers": [{"id": "old", "kind": "refinery", "label": "Tungsten", "location": "MIC-L2",
                "ready_at": "2026-11-26T16:20:00-08:00"},
               {"id": "new", "kind": "refinery", "label": "Beryl", "location": "MIC-L2 Long Forest Station",
                "ready_at": "2026-11-26T18:00:00-08:00"}]})


def views_over(events, plan=None, user=None, names=NAMES, ref=None):
    """[(view, rule, event kind, time)] each time the chosen view changes, replaying the events."""
    st = State(names, ref)
    out = []
    for ev in events:
        st.apply(ev)
        p = board.build(st, plan, user, ev.t, game_running=True)
        if not out or out[-1][0] != p["view"]["name"]:
            out.append((p["view"]["name"], p["view"]["rule"], ev.kind, clock(ev.t, PACIFIC)))
    return out, st


class RunAViewsTest(unittest.TestCase):
    """A real mining session with a plan written for it: Preflight, Travel, Mining, Refinery."""

    @classmethod
    def setUpClass(cls):
        cls.r = read("run_a.log")
        cls.seq, cls.st = views_over(cls.r.events, RUN_A)

    def test_views_in_order_at_the_right_events(self):
        self.assertEqual(self.seq, [
            ("preflight", "menu", "session_start", "3:11:20 PM"),
            ("now", "else", "spawned", "3:13:32 PM"),                  # in the world, nothing yet
            ("mining", "ship", "channel_joined", "3:16:55 PM"),        # boarded the Golem, a mining ship
            ("travel", "travel", "quantum_target", "3:19:04 PM"),
            ("mining", "leg", "quantum_arrived", "3:22:51 PM"),        # the run's first leg
            ("travel", "travel", "quantum_target", "3:58:41 PM"),
            ("refinery", "leg", "quantum_arrived", "4:03:04 PM"),      # its second
            ("travel", "travel", "quantum_target", "4:26:16 PM"),
            ("cargo", "leg", "inventory_location", "4:29:05 PM"),      # home with the lots
            ("preflight", "menu", "disconnected", "4:37:29 PM"),       # back at the menu
            ("idle", "no_game", "quit", "4:37:29 PM"),
        ])

    def at(self, kind, when):
        st = State(NAMES)
        for ev in self.r.events:
            st.apply(ev)
            if ev.kind == kind and clock(ev.t, PACIFIC) == when:
                return st, board.build(st, RUN_A, {}, ev.t, game_running=True, tz=PACIFIC)
        raise AssertionError("no %s at %s" % (kind, when))

    def test_the_models_on_the_way(self):
        _, p = self.at("quantum_target", "3:19:04 PM")
        m = p["model"]
        self.assertEqual((m["dest"]["short"], m["run"]), ("ARC-L4", "Run A"))
        self.assertEqual([x["state"] for x in m["legs"]], ["now", "later", "later"])
        self.assertIn("Take rocks at 600 and up.", m["arrive"])
        self.assertEqual(p["strip"]["where"]["text"], "To ARC-L4")
        _, p = self.at("quantum_arrived", "3:22:51 PM")
        m = p["model"]
        ore = m["ores"][0]
        self.assertEqual((ore["name"], ore["take"], ore["reads"][0]["scan"]), ("Tungsten", "600+", "11,610"))
        self.assertEqual(m["spot"], "arc-l4-field")
        self.assertEqual(m["goal"]["items"][0]["note"], "1.82 to go")
        self.assertEqual(m["controls"]["mode"], "mining")
        _, p = self.at("quantum_arrived", "4:03:04 PM")
        m = p["model"]
        self.assertEqual(m["station"]["short"], "MIC-L2")
        self.assertEqual(m["method"]["name"], "Pyrometric Chromalysis")
        self.assertEqual([t["label"] for t in m["timers"]], ["Tungsten", "Beryl"])

    def test_the_refinery_notice_clears_only_the_timer_it_can(self):
        notice = T("2026-11-26T16:21:31-08:00")
        p = board.build(self.st, RUN_A, {}, notice + 60, game_running=True, tz=PACIFIC)
        timers = {t["label"]: t for t in p["timers"]}
        self.assertEqual(timers["Tungsten"]["state"], "done")
        self.assertEqual(timers["Beryl"]["state"], "running")          # due at 6 PM: not this notice's
        self.assertIn("Work order complete", [a["title"] for a in p["alerts"]])


class RestartTest(unittest.TestCase):
    """PLAN §7 and §13: rereading a session raises no old alert, and an old completion notice
    does not clear a newer timer."""

    def test_reread_two_hours_later(self):
        r = read("run_a.log")
        later = T("2026-11-26T18:30:00-08:00")
        p = board.build(r.state, RUN_A, {}, later, game_running=True)
        self.assertEqual(p["alerts"], [])
        timers = {t["label"]: t["state"] for t in p["timers"]}
        self.assertEqual(timers, {"Tungsten": "done", "Beryl": "ready"})   # ready by its time, not cleared

    def test_a_reread_from_the_top_gives_the_same_payload(self):
        a = read("run_a.log")
        b = read("run_a.log")
        now = T("2026-11-26T16:22:00-08:00")
        self.assertEqual(board.build(a.state, RUN_A, {}, now), board.build(b.state, RUN_A, {}, now))

    def test_two_orders_at_one_station(self):
        r = read("run_a.log")
        plan = plan_of({"timers": [
            {"id": "a", "kind": "refinery", "label": "A", "location": "MIC-L2", "ready_at": "2026-11-26T16:15:00-08:00"},
            {"id": "b", "kind": "refinery", "label": "B", "location": "MIC-L2", "ready_at": "2026-11-26T16:10:00-08:00"},
            {"id": "c", "kind": "refinery", "label": "C", "location": "MIC-L1", "ready_at": "2026-11-26T16:00:00-08:00"}]})
        p = board.build(r.state, plan, {}, T("2026-11-26T16:30:00-08:00"))
        states = {t["label"]: t["state"] for t in p["timers"]}
        self.assertEqual(states, {"B": "done", "A": "ready", "C": "ready"})   # the earliest that fits


class CourierViewTest(unittest.TestCase):
    """A real courier contract (samples/courier.log) on the Cargo view, pickup then drop-off."""

    def test_cargo_with_pickup_then_drop_off(self):
        r = read("courier.log")
        st = State(NAMES)
        seen = {}
        for ev in r.events:
            st.apply(ev)
            # the accept notice, then both objectives in the same millisecond; then the pickup done
            if ev.kind in ("objective_new", "objective_complete") and ev.text.startswith("Collect Data Probe"):
                seen[ev.kind] = board.build(st, None, {}, ev.t)
        p = seen["objective_new"]
        self.assertEqual(p["view"]["rule"], "contract")
        stop = p["model"]["this_stop"]
        self.assertEqual((stop["big"], stop["unit"], stop["sub"]), ("Data Probe", "to pick up", "at HUR-L1 Green Glade Station"))
        stops = p["model"]["stops"]
        self.assertEqual([(s["kind"], s["place"]) for s in stops],
                         [("pickup", "HUR-L1 Green Glade Station"), ("dropoff", "HUR-L3 Thundering Express Station")])
        objs = p["model"]["contract"]["objectives"]
        self.assertEqual([o["state"] for o in objs], ["now", "next"])
        self.assertEqual(p["model"]["contract"]["giver"], "FTL Courier")
        p = seen["objective_complete"]
        stop = p["model"]["this_stop"]
        self.assertEqual((stop["big"], stop["unit"], stop["sub"]),
                         ("Data Probe", "to drop off", "at HUR-L3 Thundering Express Station"))
        self.assertEqual([o["state"] for o in p["model"]["contract"]["objectives"]], ["done", "now"])
        self.assertEqual(p["model"]["contract"]["count"], "Objective 2 of 2")
        self.assertEqual(p["model"]["contract_total"]["big"], "2")    # two stops, no SCU in a courier run


class BuiltViewsTest(unittest.TestCase):
    def last(self, name, plan=None):
        r = read(name)
        return r, board.build(r.state, plan, {}, r.state.session["last_t"] + 1, game_running=True)

    def test_hauling_on_cargo_with_its_stops_unverified_shape(self):
        _, p = self.last("built_hauling.log")
        m = p["model"]
        self.assertEqual(p["view"]["name"], "cargo")
        self.assertEqual([(s["index"], s["scu"], s["place"], s["state"]) for s in m["stops"]],
                         [(0, 16, "CRU-L1 Ambitious Dream Station", "done"), (1, 8, "Orison", "active")])
        self.assertEqual((m["this_stop"]["big"], m["this_stop"]["unit"]), ("8", "SCU off"))
        self.assertEqual(m["contract_total"], {"big": "24", "unit": "SCU", "sub": "in 2 stops"})
        self.assertEqual((m["grid"]["big"], m["grid"]["sub"]), ("64", "room to spare"))
        self.assertTrue(m["unverified"])
        self.assertIn("Medical Supplies", m["trade"]["bought"])

    def test_bounty_on_combat_in_a_ship_unverified_shape(self):
        _, p = self.last("built_bounty.log")
        m = p["model"]
        self.assertEqual((p["view"]["name"], m["on_foot"]), ("combat", False))
        self.assertEqual(m["where"], "Pilot seat · Origin M80")
        self.assertEqual((m["tally"]["destroyed"], m["tally"]["kills_verified"]), (2, False))
        self.assertEqual(m["controls"]["mode"], "combat")
        self.assertEqual(m["contract"]["setting"], "ship")
        self.assertEqual(m["law"]["jurisdiction"], "UEE jurisdiction")
        attacked = [a for a in p["alerts"] if a["kind"] == "Attacked"]
        self.assertEqual(attacked[0]["level"], "bad")
        self.assertNotIn("OtherPilot_7", json.dumps(p))

    def test_on_foot_combat_unverified_shape(self):
        _, p = self.last("built_onfoot.log")
        m = p["model"]
        self.assertEqual((p["view"]["name"], m["on_foot"], m["controls"], m["tally"]), ("combat", True, None, None))
        self.assertEqual(m["ship_left"]["name"], "Origin M80")
        self.assertEqual(m["health"], "Moderate injury: left arm, tier 2")
        self.assertEqual(m["contract"]["current"], "Neutralize Kade Ross")
        self.assertEqual(p["strip"]["ship"], {"icon": "walk", "text": "On foot"})

    def test_unknown_contract_on_mission_and_unmapped_unverified_shape(self):
        _, p = self.last("built_unknown.log")
        self.assertEqual(p["view"]["name"], "mission")
        self.assertEqual(p["model"]["contract"]["title"], "A Very Unusual Job")
        self.assertTrue(p["model"]["contract"]["unmapped"])
        self.assertEqual(p["unmapped_contracts"][0]["contract"], "Example_Unlisted_Contract")

    def test_failed_contract_shown_as_failed_unverified_shape(self):
        r, p = self.last("built_failed.log")
        titles = [a["title"] for a in p["alerts"]]
        self.assertIn("Contract failed: Opportunity for Independent Cargo Hauler", titles)
        self.assertEqual(r.state.to_dict()["contracts"][0]["status"], "failed")
        self.assertEqual(p["view"]["name"], "now")                    # nothing active any more
        later = board.build(r.state, None, {}, r.state.session["last_t"] + 3600)
        self.assertEqual(later["alerts"], [])                         # expired by event time


class PreflightTest(unittest.TestCase):
    def before_quit(self, name):
        r = read(name)
        st = State(NAMES)
        for ev in r.events:
            if ev.kind == "quit":
                break
            st.apply(ev)
        return board.build(st, plan_of({"preflight": ["Switch on the AB6 base"]}), {}, st.session["last_t"] + 1)

    def test_stick_base_missing_is_the_red_alert(self):
        p = self.before_quit("preflight_fail.log")
        self.assertEqual(p["view"]["name"], "preflight")
        a = p["alerts"][0]
        self.assertEqual((a["level"], a["kind"], a["title"]), ("bad", "Preflight failed", "Stick base not detected"))
        m = p["model"]
        self.assertEqual((m["verdict"], m["title"]), ("fail", "Stick base not detected"))
        self.assertEqual([(d["slot"], d["mark"]) for d in m["devices"]],
                         [("Joystick 1", "info"), ("Joystick 2", "ok"), ("Not found", "bad")])
        self.assertEqual(m["devices"][0]["role"], "keyboard")
        self.assertEqual(m["why"], "The keyboard took joystick 1. Every stick binding points at it.")
        self.assertEqual(m["plan_notes"], ["Switch on the AB6 base"])
        self.assertEqual(p["strip"]["state"], "Preflight failed")

    def test_a_different_order_passes_with_a_note(self):
        p = self.before_quit("preflight_reordered.log")
        self.assertFalse([a for a in p["alerts"] if a["level"] == "bad"])
        m = p["model"]
        self.assertEqual(m["verdict"], "pass")
        self.assertIn("different order than usual", m["note"])


class PickTest(unittest.TestCase):
    def test_a_hand_pick_stays_until_the_context_changes(self):
        r = read("run_a.log")
        st = State(NAMES)
        it = iter(r.events)
        for ev in it:
            st.apply(ev)
            if ev.kind == "quantum_arrived":
                break
        p = board.build(st, RUN_A, {}, ev.t)
        self.assertEqual(p["view"]["name"], "mining")
        user = {"view": board.pick(st, RUN_A, "now", now=ev.t)}
        p = board.build(st, RUN_A, user, ev.t + 30)
        self.assertEqual((p["view"]["name"], p["view"]["picked"], p["view"]["auto"]), ("now", True, "mining"))
        for ev in it:                                             # on to the next jump
            st.apply(ev)
            if ev.kind == "quantum_target":
                break
        p = board.build(st, RUN_A, user, ev.t)
        self.assertEqual((p["view"]["name"], p["view"]["pick_dropped"]), ("travel", True))
        self.assertIsNone(board.pick(st, RUN_A, "nonsense"))

    def test_quick_timers_through_the_user_block(self):
        r = read("run_a.log")
        now = r.state.session["last_t"]
        user = board.add_quick_timer({}, "Medgel", 10, now)
        p = board.build(r.state, None, user, now + 60)
        q = [t for t in p["timers"] if t["source"] == "quick"]
        self.assertEqual((q[0]["label"], q[0]["state"]), ("Medgel", "running"))
        self.assertEqual(p["next_change_ms"], q[0]["ready_ms"])
        self.assertEqual(board.remove_quick_timer(user, q[0]["id"])["timers"], [])
        self.assertIsNone(board.add_quick_timer({}, "", 10, now))


class PayloadTest(unittest.TestCase):
    def test_keys_privacy_and_no_clock_unverified_shape(self):
        r = read("built_law.log")
        with mock.patch("time.time", side_effect=AssertionError("wall clock read")):
            p = board.build(r.state, RUN_A, {}, r.state.session["last_t"] + 5)
        self.assertEqual(set(p), {"schema", "view", "model", "strip", "alerts", "timers", "plan",
                                  "unmapped_contracts", "next_change_ms", "problems"})
        self.assertEqual(p["problems"], [])
        text = json.dumps(p, allow_nan=False)
        for name in ("Pilot_Example", "OtherPilot_2", "OtherPilot_3", "900000000003"):
            self.assertNotIn(name, text)
        with self.assertRaises(ValueError):
            board.build(r.state, None, {}, None)

    def check_every_view(self, samples):
        # A hand pick can name any view; each model must cope with a state that has nothing for it.
        for name in samples:
            r = read(name)
            st = r.state
            for view in P.VIEWS:
                pk = board.pick(st, RUN_A, view, game_running=True)
                p = board.build(st, RUN_A, {"view": pk}, st.session["last_t"] + 1, game_running=True)
                self.assertEqual(p["model"]["view"], view, (name, view))
                self.assertEqual(p["problems"], [], (name, view))
                json.dumps(p, allow_nan=False)

    def test_every_view_has_a_model_for_any_state(self):
        self.check_every_view(("run_a.log", "courier.log", "preflight_fail.log"))
        empty = State(NAMES)
        for view in P.VIEWS:
            p = board.build(empty, None, {"view": board.pick(empty, None, view)}, 0.0 + 1.8e9)
            self.assertEqual(p["model"]["view"], view)

    def test_every_view_has_a_model_on_built_samples_unverified_shape(self):
        self.check_every_view(("built_law.log", "built_hauling.log", "built_bounty.log", "built_onfoot.log"))

    def test_hostile_texts_and_a_failing_part(self):
        from scdash import events as E
        s = "s"
        evil = "\x1b[31m\u202e Zed_Bad " + "x" * 5000
        evs = [E.SessionStart(s, 0, 1.8e9, s, None, None), E.Login(s, 1, 1.8e9, "Pilot_Example"),
               E.JoinServer(s, 2, 1.8e9 + 1, "x"), E.Spawned(s, 3, 1.8e9 + 2),
               E.ContractAccepted(s, 4, 1.8e9 + 3, evil, "m1"),
               E.ObjectiveNew(s, 5, 1.8e9 + 4, "Deliver 0/9999999 SCU of %s to %s" % (evil, evil), "m1",
                              "dropoff_e0000001-0000-4000-8000-000000000001_7"),
               E.CrimeAgainstYou(s, 6, 1.8e9 + 5, "Zed_Bad", evil), E.Fined(s, 7, 1.8e9 + 6, 1e12)]
        st = State(NAMES)
        for ev in evs:
            st.apply(ev)
        p = board.build(st, None, {}, 1.8e9 + 10)
        self.assertEqual(p["problems"], [])

        def walk(x):
            if isinstance(x, str):
                self.assertLessEqual(len(x), board.MAX_TEXT)
                self.assertNotIn("\x1b", x)
                self.assertNotIn("\u202e", x)
                self.assertNotIn("Zed_Bad", x)
            elif isinstance(x, dict):
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(p)
        from scdash import views
        name = p["view"]["name"]
        with mock.patch.dict(views.MODELS, {name: mock.Mock(side_effect=RuntimeError("broken"))}):
            p = board.build(st, None, {}, 1.8e9 + 10)
        self.assertEqual(p["model"], {"view": name, "unavailable": True})
        self.assertEqual(p["problems"], ["model: RuntimeError"])
        self.assertTrue(p["alerts"])                              # the rest is still there

    def test_plan_notice_reaches_the_payload(self):
        with lib.TempDir() as d:
            store = P.PlanStore(d / "plan.json")
            store.refresh()
            p = board.build(State(NAMES), store, {}, 1.8e9, game_running=False)
            self.assertEqual(p["plan"]["loaded"], False)
            self.assertIn("no plan.json yet", p["plan"]["notice"])
            self.assertEqual(p["view"]["name"], "idle")


class ReferenceViewsTest(unittest.TestCase):
    """The example plan's runs against the reference tables (no log needed beyond a place)."""

    def state_at(self, code, ref=None, how="quantum"):
        from scdash import events as E
        st = State(NAMES, ref)
        s = "s"
        for ev in [E.SessionStart(s, 0, 1.8e9, s, None, None), E.JoinServer(s, 1, 1.8e9 + 1, "x"),
                   E.Spawned(s, 2, 1.8e9 + 2)]:
            st.apply(ev)
        if how == "quantum":
            st.apply(E.QuantumTarget(s, 3, 1.8e9 + 10, "DRAK_Golem", "1", code))
            st.apply(E.QuantumArrived(s, 4, 1.8e9 + 60, "DRAK_Golem", "1"))
        else:
            st.apply(E.LocationInventory(s, 3, 1.8e9 + 60, code))
        return st

    def example(self, run=None):
        raw = json.loads((lib.DASHBOARD / "plan.example.json").read_text(encoding="utf-8"))
        if run:
            raw["current_run"] = run
        return plan_of(raw)

    def test_mining_at_cru_l5(self):
        st = self.state_at("LOC_RR_S2_L5")
        p = board.build(st, self.example(), {}, 1.8e9 + 61)
        m = p["model"]
        self.assertEqual((p["view"]["name"], p["view"]["rule"]), ("mining", "leg"))
        self.assertEqual([o["name"] for o in m["ores"]], ["Agricium", "Beryl"])
        self.assertEqual(m["ores"][0]["reads"][0]["scan"], "11,655")
        self.assertTrue(m["ores"][0]["tier_text"].startswith("Uncommon · 2"))
        self.assertEqual((m["ores"][1]["take"], m["ores"][1]["skip"]), ("700+", "700"))
        self.assertIn("None within 1%", m["alike"])
        self.assertEqual(m["goal"]["first"], "Agricium first: it is 3.62 SCU short.")
        self.assertTrue(m["refine"]["rows"])

    def test_mining_without_a_plan_shows_what_spawns_there(self):
        from scdash import events as E
        st = self.state_at("LOC_RR_S3_L4")
        st.apply(E.ChannelJoined("s", 5, 1.8e9 + 70, "Drake Golem", "Pilot_Example"))
        p = board.build(st, None, {}, 1.8e9 + 71)
        m = p["model"]
        self.assertEqual((p["view"]["name"], p["view"]["rule"], m["ores_from"]), ("mining", "ship", "spot"))
        self.assertEqual(m["spot"], "arc-l4-field")
        self.assertTrue(m["ores"])
        self.assertTrue(all(o["take"] is None for o in m["ores"]))
        self.assertIsNone(m["goal"])

    def test_salvage_prices_only_with_the_file(self):
        with lib.TempDir() as d:
            prices = d / "prices.json"
            lib.write(prices, json.dumps({"commodities": {
                "Recycled Material Composite": {"rows": [{"terminal": 1, "place": "cru-l1", "buy": None, "sell": 9750, "date": "2026-11-26"}]},
                "Construction Materials": {"rows": [{"terminal": 1, "place": "cru-l1", "buy": None, "sell": 2480, "date": "2026-11-25"}]}}}).encode())
            ref = RefData(prices=prices)
            st = self.state_at("RR_CRU_L4", ref, how="inventory")
            p = board.build(st, self.example("rmc"), {"view": None}, 1.8e9 + 61)
            m = p["model"]
            self.assertEqual(p["view"]["name"], "salvage")
            self.assertEqual([(x["what"], x["note"], x["price"]) for x in m["sell"]["rows"]],
                             [("RMC", "keep for repairs", "9,750"), ("Construction Materials", "sell", "2,480")])
            self.assertEqual(m["sell"]["foot"], "aUEC per SCU · UEX, Nov 26")
            self.assertEqual((m["goal"]["held"], m["goal"]["need"]), ("4.5", "12"))
            missing = RefData(prices=d / "none.json")
            st = self.state_at("RR_CRU_L4", missing, how="inventory")
            m = board.build(st, self.example("rmc"), {}, 1.8e9 + 61)["model"]
            self.assertEqual([x["price"] for x in m["sell"]["rows"]], [None, None])
            self.assertIsNone(m["sell"]["foot"])

    def test_selling_with_the_plans_list(self):
        st = self.state_at("Stanton4_NewBabbage", how="inventory")
        p = board.build(st, self.example(), {}, 1.8e9 + 61)
        self.assertEqual(p["view"]["name"], "selling")
        rows = p["model"]["rows"]
        self.assertEqual([r["what"] for r in rows], ["Taranite", "Quartz"])
        self.assertEqual(rows[0]["value"], "218,400")


if __name__ == "__main__":
    unittest.main()
