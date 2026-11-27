"""No line, whatever it holds, can stop or stall the reader (PLAN §7, §8). A line that cannot be
read is skipped and counted in `state.session["unreadable"]`, and the offset always moves on."""
import unittest

import scdash_testlib as lib
from scdash import pipeline
from scdash.tail import Follower

FIRST = b'<2026-11-26T23:11:20.067Z> BackupNameAttachment=" Build(1) 26 Nov 26 (15 11 12)"  -- used by backup system\r\n'
GOOD_JOIN = b"<2026-11-26T23:12:58.692Z> [Notice] <Join PU> address[192.0.2.1] port[1] shard[pub_example_1] locationId[1] [Team_GameServices][GIM][Matchmaking]\r\n"
BAD_DIGITS = b"<2026-1X-26T23:12:59.000Z> [Notice] <Join PU> address[192.0.2.1] port[1] shard[pub_example_2] locationId[1] [Team_GameServices][GIM][Matchmaking]\r\n"
NON_ASCII = b"<2026-11-26T23:1\xe9:00.000Z> [Notice] <Join PU> address[192.0.2.1] port[1] shard[pub_example_3] locationId[1] [Team_GameServices][GIM][Matchmaking]\r\n"
BAD_FLOAT = (b"<2026-11-26T23:13:01.000Z> [Notice] <Calculate Route> [ItemNavigation][CL][1] | NOT AUTH | DRAK_Golem_900000000001[900000000001]"
             b"|CSCItemNavigation::CalculateRoute|Successfully calculated route to LOC_RR_S3_L4 fuel estimate 1.2.3 [Team_CGP4][QuantumTravel]\r\n")
BAD_PRICE = (b"<2026-11-26T23:13:02.000Z> [Notice] <CEntityComponentShopUIProvider::SendShopBuyRequest> Sending SShopBuyRequest - playerId[1] "
             b"shopId[1] shopName[SCShop_Example] kioskId[1] client_price[1.2.3] itemClassGUID[x] itemName[thing] quantity[1]  [Team_CoreGameplayFeatures][Shops][UI]\r\n")
GOOD_QUIT = b"<2026-11-26T23:14:00.000Z> [Notice] <SystemQuit> CSystem::Quit invoked with - cause=30016, reason=Quit via console command, exitCode=0 [Team_Unknown][System]\r\n"


class MalformedLinesTest(unittest.TestCase):
    def read(self, data, **kw):
        mem = lib.MemoryLog(data)
        r = pipeline.LogReader("Game.log", lib.NAMES, opener=mem.opener, keep_events=True, **kw)
        for _ in range(3):                                   # polls after the end must be calm
            r.poll()
        r.finish()
        return r

    def test_bad_lines_are_skipped_counted_and_reading_goes_on(self):
        data = FIRST + BAD_DIGITS + NON_ASCII + GOOD_JOIN + BAD_FLOAT + BAD_PRICE + GOOD_QUIT
        r = self.read(data)
        self.assertEqual(r.follower.offset, len(data))
        self.assertEqual(r.state.session["unreadable"], 4)
        self.assertEqual(r.state.server["shards"], ["pub_example_1"])
        self.assertEqual(r.state.session["game"], "ended")   # the line after the bad ones was read
        self.assertEqual(r.summary(complete=True)["unreadable"], 4)
        kinds = [e.kind for e in r.events]
        self.assertEqual(kinds.count("unreadable"), 4)

    def test_same_result_in_any_pieces(self):
        data = FIRST + BAD_DIGITS + NON_ASCII + GOOD_JOIN + BAD_FLOAT + BAD_PRICE + GOOD_QUIT
        whole = self.read(data).state.to_dict()
        for piece in (7, 50, 333):
            self.assertEqual(self.read(data, piece=piece).state.to_dict(), whole)

    def test_a_failing_receiver_cannot_stall_the_follower(self):
        data = FIRST + b"".join(b"<2026-11-26T23:13:%02d.000Z> [Notice] <X> line %d\r\n" % (i, i) for i in range(40))

        class Sink:
            def __init__(self):
                self.got, self.calls = [], 0

            def reset(self):
                pass

            def lines(self, lines, offsets):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("the receiver failed")
                self.got.extend(zip(lines, offsets))

        mem = lib.MemoryLog(data)
        f, sink = Follower("Game.log", mem.opener, piece=100), Sink()
        while f.poll(sink) == "read":
            pass
        self.assertEqual(f.offset, len(data))
        self.assertEqual(f.sink_errors, 1)
        for line, off in sink.got:                           # nothing split or joined wrongly
            self.assertEqual(data[off:off + len(line)], line)
            self.assertTrue(line.startswith(b"<2026-"))


if __name__ == "__main__":
    unittest.main()
