"""The readings table: proto3 defaults, the quirk rules, countermeasure counts, and the generic
tree that keeps every field the table does not use. Synthetic snapshots only.

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES). The rest of this file is this
project's own.
"""
import json
import unittest

import scdash_testlib  # noqa: F401
import test_telemetry_fake as fake

from scdash import telemetry_readings as rd


class ReadingsTest(unittest.TestCase):
    def setUp(self):
        self.schema = fake.make_schema()
        self.r = rd.Readings(self.schema, fake.RESPONSE)

    def build(self, obj):
        return self.r.build(self.schema.decode(fake.RESPONSE, fake.encode(self.schema, fake.RESPONSE, obj)))

    def test_table_names_are_unique_and_documented(self):
        names = []
        for e in rd.TABLE:
            names += list(e.params[2].values()) if e.kind == "count" else [e.name]
            self.assertTrue(e.unit, e.name)
            self.assertNotIn("verified", e.note.lower().replace("unverified", ""), e.name)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(v["verified"] is False for v in self.r.info.values()))

    def test_defaults_and_absence(self):
        out = self.build({"vehicle": {"state": {"flight": {"instruments": {}, "state": {}},
                                                "power": {}}}})["readings"]
        self.assertEqual(out["speed_mps"], 0.0)               # message there, field not sent
        self.assertIsInstance(out["speed_mps"], float)
        self.assertFalse(out["power_engines"])
        self.assertFalse(out["landed"])
        self.assertNotIn("gear", out)                         # proto3 optional: absent stays absent
        self.assertNotIn("g_force", out)                      # optional message not sent
        self.assertNotIn("warn_pwr", out)                     # annunciators not sent at all
        self.assertNotIn("balance_auec", out)                 # actor not sent at all
        self.assertTrue(out["in_vehicle"])
        self.assertIsNone(out["vehicle_class"])               # "" means none
        self.assertIsNone(out["vehicle_type"])                # UNSPECIFIED means none
        empty = self.r.build({})
        self.assertEqual(empty["readings"], {"in_vehicle": False})

    def test_quirk_rules(self):
        inst = {"altitude": 3.4028234663852886e38, "hydrogen_fuel": 0.0, "quantum_fuel": 0.0,
                "speed": 12.5, "heading": 1.0}
        out = self.build({"vehicle": {"state": {"flight": {"instruments": inst,
                                                           "state": {"vtol": "DEPLOYED"}}}}})
        r = out["readings"]
        self.assertIsNone(r["altitude_m"])
        self.assertIsNone(r["fuel_hydrogen_frac"])
        self.assertIsNone(r["fuel_quantum_frac"])
        self.assertEqual(r["speed_mps"], 12.5)
        self.assertNotIn("vtol", r)
        self.assertEqual(out["withheld"], {"vtol": "DEPLOYED"})
        out = self.build({"vehicle": {"state": {"flight": {"instruments": {"hydrogen_fuel": 3.0}}}}})
        self.assertIsNone(out["readings"]["fuel_hydrogen_frac"])   # not a fraction
        out = self.build({"vehicle": {"state": {"flight": {"instruments": {"hydrogen_fuel": 0.25}}}}})
        self.assertEqual(out["readings"]["fuel_hydrogen_frac"], 0.25)

    def test_countermeasures(self):
        out = self.build({"weapons": {"countermeasures": [
            {"type": "DECOY", "amount": 10}, {"type": "DECOY", "amount": 2},
            {"type": "NOISE"}, {"type": "UNSPECIFIED", "amount": 99}]}})["readings"]
        self.assertEqual((out["decoys"], out["noise"]), (12, 0))
        out = self.build({"weapons": {"preset_name": "x"}})["readings"]
        self.assertNotIn("decoys", out)                       # none listed: unknown, not zero

    # From CSR tests/test_tlm_recording.py lines 24-43 (flatten and frame_events tests): the idea.
    def test_other_keeps_what_the_table_does_not_use(self):
        out = self.build({"vehicle": {"state": {"flight": {"settings": {
            "ifcs_coupled": {"enabled": True, "active": False}}}}},
            "events": {"events": [{"type": "ACTOR_DEAD"}]}})
        self.assertFalse(out["readings"]["coupled"])
        self.assertEqual(out["other"], {"vehicle": {"state": {"flight": {"settings": {
            "ifcs_coupled": {"enabled": True}}}}}})
        self.assertEqual(out["events"], ["ACTOR_DEAD"])
        self.assertEqual(out["source"], "telemetry")
        flat = rd.flatten(out["other"])
        self.assertEqual(flat, {"vehicle.state.flight.settings.ifcs_coupled.enabled": True})
        json.dumps(out)

    def test_a_field_the_table_does_not_know_lands_in_other(self):
        schema = fake.make_schema(with_shields=True)
        r = rd.Readings(schema, fake.RESPONSE, table=[e for e in rd.TABLE if not e.field.startswith("vehicle.state.shields")])
        msg = fake.snapshot(schema, extra_vehicle={"shields": {"level": 0.5}})
        out = r.build(schema.decode(fake.RESPONSE, msg))
        self.assertEqual(rd.flatten(out["other"])["vehicle.state.shields.level"], 0.5)

    def test_fields_missing_from_the_build_are_listed(self):
        self.assertIn("shield_level", self.r.missing)
        self.assertIn("master_mode", self.r.missing)
        self.assertNotIn("speed_mps", self.r.missing)

    def test_events_of_odd_shapes(self):
        self.assertEqual(rd.events_of({}), [])
        many = {"events": {"events": [{"type": "ACTOR_DEAD"}] * 100}}
        self.assertEqual(len(rd.events_of(many)), rd.MAX_EVENTS_PER_SNAPSHOT)
        self.assertEqual(rd.events_of({"events": {"events": [{"type": 9}, "x", {}]}}), [9, "UNSPECIFIED"])
        self.assertEqual(rd.events_of({"events": "x"}), [])
        self.assertEqual(rd.events_of(None), [])


if __name__ == "__main__":
    unittest.main()
