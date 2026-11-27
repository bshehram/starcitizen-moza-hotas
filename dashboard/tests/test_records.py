"""Line to record: split notices, triple logging, untimed lines, interleaving, level parts."""
import unittest

import scdash_testlib as lib
from scdash import events
from scdash.records import RecordReader, parse_ts


def records(data, reader=None):
    reader = reader or events.new_record_reader()
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    offs, o = [], 0
    for line in lines:
        offs.append(o)
        o += len(line) + 1
    reader.lines(lines, offs)
    reader.flush()
    return reader.take()


class RecordsTest(unittest.TestCase):
    def setUp(self):
        self.data = lib.sample_bytes("records.log")
        self.recs = records(self.data)

    def test_untimed_lines_are_skipped(self):
        # records.log opens with two debug dumps whose inner lines have no time
        self.assertTrue(all(not r.text.startswith(" Size:[") for r in self.recs))
        self.assertTrue(all(r.ts.startswith("2026-") for r in self.recs))

    def test_split_notice_is_one_record_with_its_whole_text(self):
        hq = [r for r in self.recs if "Joined hangar queue" in r.text]
        self.assertEqual(len(hq), 1)                        # logged three times, read once
        self.assertIn("Your place: 2. Max. estimated wait: 200.000000 s.", hq[0].text)
        self.assertTrue(hq[0].complete)
        self.assertEqual(hq[0].offset, self.data.index(b"<2026-11-26T23:17:10.584Z> [Notice] <SHUDEvent"))

    def test_two_line_ship_retrieval(self):
        sv = [r for r in self.recs if r.key.endswith("SetVehicleSpawningInformations")]
        self.assertEqual(len(sv), 1)
        self.assertTrue(sv[0].text.endswith("XL Hangar [Team_GameServices][ASOP]"))

    def test_a_line_of_its_own_between_pieces_is_read_and_order_kept(self):
        left = [i for i, r in enumerate(self.recs) if "You have left the channel" in r.text]
        destroyed = [i for i, r in enumerate(self.recs) if r.key == "Vehicle Destroyed"]
        self.assertEqual(len(left), 1)
        self.assertEqual(len(destroyed), 1)                 # not swallowed by the waiting notice
        self.assertLess(left[0], destroyed[0])              # file order, though it came out later
        self.assertTrue(self.recs[left[0]].complete)
        self.assertIn('" [39] to queue', self.recs[left[0]].text)
        self.assertEqual(self.recs, sorted(self.recs, key=lambda r: r.offset))

    def test_double_level_part(self):
        reader = RecordReader({b"Invalid path": None}, {}, {}, set())
        recs = records(self.data, reader)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].level, "SPAM 119][Error")
        self.assertTrue(recs[0].text.startswith("[TRANSPORT] Path"))

    def test_notice_that_never_closes_is_still_emitted(self):
        data = (b'<2026-11-26T23:17:10.584Z> [Notice] <SHUDEvent_OnNotification> Added notification "Joined hangar queue.\r\n'
                + b"".join(b"<2026-11-26T23:17:11.000Z> [Notice] <Other> line %d [Team_X]\r\n" % i for i in range(6)))
        recs = records(data)
        self.assertEqual(len(recs), 1)
        self.assertFalse(recs[0].complete)
        ev = events.EventParser().event(recs[0])
        self.assertEqual(ev.kind, "hangar_queue")
        self.assertIsNone(ev.wait_s)

    def test_parse_ts(self):
        self.assertEqual(parse_ts("2026-11-26T23:11:20.067"), 1795734680.067)


class EchoTest(unittest.TestCase):
    def test_echo_and_update_copies_never_count(self):
        recs = records(lib.sample_bytes("run_a.log"))
        notices = [r for r in recs if r.key == "SHUDEvent_OnNotification"]
        raw = lib.sample_bytes("run_a.log").count(b"<SHUDEvent_OnNotification> Added notification")
        self.assertEqual(len(notices), raw)
        self.assertFalse(any(r.key == "UpdateNotificationItem" for r in recs))


if __name__ == "__main__":
    unittest.main()
