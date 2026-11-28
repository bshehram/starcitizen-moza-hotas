"""The plan (PLAN §10): the loader is bounded in every dimension, keeps the last good copy of a
missing or broken file with a short notice, reads times with their offsets, and the example
file holds one run of each kind in the settled shape. Also the user block (quick timers, a
view picked by hand)."""
import json
import os
import unittest

import scdash_testlib as lib
from scdash import plan as P
from scdash.words import parse_time

EXAMPLE = lib.DASHBOARD / "plan.example.json"


def write_json(path, obj):
    lib.write(path, json.dumps(obj).encode("utf-8"))


class ExampleTest(unittest.TestCase):
    def test_example_fits_the_shape_whole(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        plan, skipped = P.normalize(raw)
        self.assertEqual(skipped, {})
        kinds = [r["kind"] for r in plan["runs"]]
        for k in ("mining", "salvage", "cargo", "combat", "mission"):
            self.assertIn(k, kinds)
        self.assertEqual(P.current_run(plan)["id"], "run-b")
        views = {g["view"] for r in plan["runs"] for g in r["legs"]}
        self.assertTrue({"mining", "refinery", "salvage", "selling", "cargo", "combat", "mission"} <= views)
        mining = plan["runs"][0]
        self.assertEqual([t["ore"] for t in mining["targets"]], ["Agricium", "Beryl"])
        self.assertTrue(mining["legs"][0]["done"])
        self.assertEqual(plan["runs"][1]["salvage"]["goal"]["need_scu"], 12.0)
        self.assertEqual(plan["runs"][2]["trade"]["sell_price"], 2140.0)

    def test_times_carry_their_offset(self):
        self.assertEqual(parse_time("2026-11-26T16:21:00-08:00"), parse_time("2026-11-27T00:21:00Z"))
        self.assertIsNone(parse_time("not a time"))
        self.assertIsNone(parse_time("9999-01-01T00:00:00+00:00"))
        self.assertIsNone(parse_time(12345))

    def test_the_first_drawing_with_one_run(self):
        plan, skipped = P.normalize({"run": {"name": "Run B", "targets": ["Agricium"],
                                             "legs": [{"to": "CRU-L5 field", "codes": ["LOC_RR_S2_L5"], "view": "mining"}]}})
        self.assertEqual(skipped, {})
        self.assertEqual((P.current_run(plan)["name"], P.current_run(plan)["kind"]), ("Run B", "mining"))


class BoundsTest(unittest.TestCase):
    def test_every_list_and_text_is_bounded(self):
        raw = {"notes": ["x" * 5000] * 50, "preflight": "one line",
               "runs": [{"name": "r%d" % i, "legs": [{"to": "p%d" % j, "view": "nonsense"} for j in range(40)]}
                        for i in range(20)],
               "timers": [{"label": "t", "ready_at": "2026-11-26T16:21:00-08:00"}] * 50,
               "sell": [{"what": "ore", "scu": float("nan"), "price": -5}] * 50,
               "objectives": [{"title": "o", "materials": [{"name": "m", "need_scu": 1e99}] * 50}] * 50}
        plan, skipped = P.normalize(raw)
        self.assertEqual(len(plan["notes"]), P.MAX_NOTES)
        self.assertTrue(all(len(n) <= P.MAX_TEXT for n in plan["notes"]))
        self.assertEqual(plan["preflight"], ["one line"])
        self.assertEqual(len(plan["runs"]), P.MAX_RUNS)
        self.assertTrue(all(len(r["legs"]) <= P.MAX_LEGS for r in plan["runs"]))
        self.assertTrue(all(g["view"] is None for r in plan["runs"] for g in r["legs"]))
        self.assertEqual(len(plan["timers"]), P.MAX_TIMERS)
        self.assertEqual(len(plan["sell"]), P.MAX_SELL)
        self.assertTrue(all(s["scu"] is None and s["price"] is None for s in plan["sell"]))
        self.assertEqual(len(plan["objectives"]), P.MAX_LIST)
        self.assertTrue(all(m["need_scu"] is None for o in plan["objectives"] for m in o["materials"]))
        self.assertIn("runs", skipped)

    def test_entries_that_do_not_fit_are_left_out_and_counted(self):
        plan, skipped = P.normalize({"runs": [{"name": "ok", "legs": [{"view": "mining"}, {"to": "x"}]}, "junk", {}],
                                     "timers": [{"label": "no time"}, {"label": "ok", "ready_at": "2026-11-26T16:21:00Z"}]})
        self.assertEqual([r["name"] for r in plan["runs"]], ["ok"])
        self.assertEqual(len(plan["runs"][0]["legs"]), 1)
        self.assertEqual(skipped, {"legs": 1, "runs": 2, "timers": 1})

    def test_ids_stay_unique(self):
        plan, _ = P.normalize({"runs": [{"id": "a", "name": "one"}, {"id": "a", "name": "two"}]})
        self.assertEqual(len({r["id"] for r in plan["runs"]}), 2)


class StoreTest(unittest.TestCase):
    def test_missing_invalid_and_last_good_copy(self):
        with lib.TempDir() as d:
            path = d / "plan.json"
            store = P.PlanStore(path)
            self.assertTrue(store.refresh())
            self.assertIsNone(store.plan)
            self.assertIn("no plan.json yet", store.notice)
            self.assertFalse(store.refresh())                   # nothing changed: nothing reread
            write_json(path, {"updated": "2026-11-26T17:30:00-08:00", "notes": ["hello"]})
            self.assertTrue(store.refresh())
            self.assertEqual(store.plan["notes"], ["hello"])
            self.assertIsNone(store.notice)
            lib.write(path, b'{"notes": ["broken"')
            os.utime(path, ns=(1, 2))                           # a new modified time, as a rewrite gives
            self.assertTrue(store.refresh())
            self.assertEqual(store.plan["notes"], ["hello"])    # the last good copy
            self.assertIn("not valid JSON", store.notice)
            self.assertIn("showing the last good copy (updated Nov 26", store.notice)
            os.remove(path)
            self.assertTrue(store.refresh())
            self.assertEqual(store.plan["notes"], ["hello"])
            self.assertIn("is gone", store.notice)

    def test_too_large_deep_or_not_an_object(self):
        with lib.TempDir() as d:
            path = d / "plan.json"
            store = P.PlanStore(path)
            for data, words in ((b" " * (P.MAX_BYTES + 1), "larger than"), (b"[" * 100000, "nested too deeply"),
                                (b"[1, 2]", "not a JSON object"), (b"\xff\xfe{}", "not UTF-8")):
                lib.write(path, data)
                os.utime(path, ns=(len(data), len(data) + len(words)))
                store.refresh()
                self.assertIn(words, store.notice, words)

    def test_partly_wrong_plan_says_so(self):
        with lib.TempDir() as d:
            path = d / "plan.json"
            write_json(path, {"runs": [{"name": "ok"}, {"nope": 1}]})
            store = P.PlanStore(path)
            store.refresh()
            self.assertEqual(len(store.plan["runs"]), 1)
            self.assertIn("1 entry in runs", store.notice)


class UserBlockTest(unittest.TestCase):
    def test_quick_timers_and_pick(self):
        now = parse_time("2026-11-27T20:00:00Z")
        t = P.quick_timer("Medgel", 15, now)
        self.assertEqual(parse_time(t["ready_at"]) - now, 900)
        self.assertIsNone(P.quick_timer("", 15, now))
        self.assertIsNone(P.quick_timer("x", 0, now))
        self.assertIsNone(P.quick_timer("x", 10 ** 9, now))
        many = [P.quick_timer("t%d" % i, 5, now + i) for i in range(20)]
        u = P.clean_user({"timers": [t, {"label": "bad"}, "junk"] + many + [many[-1]],
                          "view": {"view": "mining", "context": "leg:a:0"}, "other": 1})
        self.assertEqual(len(u["timers"]), P.MAX_QUICK)
        self.assertEqual(u["timers"][-1]["label"], "t19")               # the newest kept, once
        self.assertEqual(len({x["id"] for x in u["timers"]}), P.MAX_QUICK)
        self.assertEqual(u["view"]["view"], "mining")
        self.assertEqual(P.clean_user({"view": {"view": "not a view", "context": "x"}})["view"], None)
        self.assertEqual(P.clean_user(None), {"timers": [], "view": None})


if __name__ == "__main__":
    unittest.main()
