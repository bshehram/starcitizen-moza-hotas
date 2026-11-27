"""Flood and speed (PLAN §9, §13): lines that match nothing are read in pieces without memory
growing, and a 5 MB log parses inside the 1-second budget.

The flood is generated here, never committed. Its size defaults to 100 MB, as PLAN §13 asks;
set SCDASH_FLOOD_MB to change it (for example 10 on a slow machine).
"""
import os
import time
import tracemalloc
import unittest

import scdash_testlib as lib
from scdash import pipeline

JUNK = [
    b"<2026-11-26T23:13:40.877Z> [Error] <CSCLoadingPlatformManager::TransitionLightGroupState> [Loading Platform] "
    b"Loading Platform Manager [LoadingPlatformManager_FreightElevator] does not have reference to the light group "
    b"[Team_CoreGameplayFeatures][Cargo]\r\n",
    b"<2026-11-26T23:13:40.877Z> [Notice] <No Manufacturer> [TRANSPORT] This network doesn't have a manufacturer set\r\n",
    b"<2026-11-26T23:13:40.877Z> [SPAM 119][Error] <Invalid path> [TRANSPORT] Path [0 -> 0] not found, carriage "
    b"will not move this update\r\n",
    b" Size:[6] State:[state: eBS_BatchCompletion] FromObjectContainer:[true] \n",
    b"<2026-11-26T23:13:40.877Z>    Class: [SCTransportManager]\r\n",
]
FIRST = b'<2026-11-26T23:11:20.067Z> BackupNameAttachment=" Build(1) 26 Nov 26 (15 11 12)"  -- used by backup system\r\n'


def junk_block(size):
    out, n = [], 0
    while n < size:
        for line in JUNK:
            out.append(line)
            n += len(line)
    return b"".join(out)


class FloodTest(unittest.TestCase):
    def test_flood_of_unmatched_lines_keeps_memory_flat(self):
        mb = int(os.environ.get("SCDASH_FLOOD_MB", "100"))
        block = junk_block(1 << 20)
        with lib.TempDir() as d:
            p = d / "Game.log"
            with open(p, "wb") as f:
                f.write(FIRST)
                for _ in range(mb):
                    f.write(block)
            tracemalloc.start()
            try:
                r = pipeline.LogReader(p, lib.NAMES)
                while r.poll() == "read":
                    pass
                r.finish()
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertEqual(r.state.session["events"], 1)         # only the first line means anything
            self.assertGreaterEqual(r.parser.reader.lines_seen, mb * 5000)
            self.assertLess(peak, 12 * 1024 * 1024, "peak %.1f MB" % (peak / 1e6))

    def test_flood_without_newlines_is_bounded(self):
        mem = lib.MemoryLog(FIRST + b"<2026-11-26T23:13:40.877Z> " + b"z" * (8 << 20))
        r = pipeline.LogReader("Game.log", lib.NAMES, opener=mem.opener)
        while r.poll() == "read":
            pass
        self.assertLessEqual(len(r.follower._partial), 64 * 1024)


class SpeedTest(unittest.TestCase):
    def test_5mb_log_inside_budget(self):
        # the samples without their first lines, so the whole file stays one session
        body = b"".join(lib.sample_bytes(n).split(b"\n", 1)[1] for n in ("courier.log", "menu_return.log"))
        filler = junk_block(len(body) * 3)
        unit = body + filler
        data = FIRST + unit * max(1, (5 << 20) // len(unit))
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, data)
            t0 = time.perf_counter()
            r = pipeline.read_whole(p, lib.NAMES, keep_events=False)
            dt = time.perf_counter() - t0
        self.assertGreater(r.state.session["events"], 1000)
        self.assertLess(dt, 1.0, "%.2f s for %.1f MB" % (dt, len(data) / 1e6))


if __name__ == "__main__":
    unittest.main()
