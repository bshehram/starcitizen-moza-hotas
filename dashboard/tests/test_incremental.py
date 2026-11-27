"""Idempotence (PLAN §7): random-sized pieces, small read pieces, a restart, and a rotation all
give the same events and state as one pass over the same bytes."""
import json
import random
import unittest

import scdash_testlib as lib
from scdash import pipeline

SAMPLES = ["run_a.log", "courier.log", "menu_return.log", "markers.log", "records.log", "preflight_fail.log"]


def snapshot(reader):
    return (json.dumps([e.to_dict() for e in reader.events], sort_keys=True),
            json.dumps(reader.state.to_dict(private=True), sort_keys=True),
            json.dumps(reader.all_lines, sort_keys=True))


def one_pass(path):
    return pipeline.read_whole(path, lib.NAMES)


def grown(data, seed, max_piece, read_piece, path=None):
    """Let the log grow by `data` a random piece at a time, polling after each piece. In memory
    by default (fast); through a real file when `path` is given."""
    rnd = random.Random(seed)
    if path is None:
        mem = lib.MemoryLog()
        reader = pipeline.LogReader("Game.log", lib.NAMES, opener=mem.opener, keep_events=True,
                                    piece=read_piece)
        append = mem.data.extend
    else:
        lib.write(path, b"")
        reader = pipeline.LogReader(path, lib.NAMES, keep_events=True, piece=read_piece)
        append = lambda b: lib.write(path, b, "ab")       # noqa: E731
    pos = 0
    while pos < len(data):
        n = rnd.randint(1, max_piece)
        append(data[pos:pos + n])
        pos += n
        while reader.poll() == "read":
            pass
    reader.finish()
    return reader


class IncrementalTest(unittest.TestCase):
    def test_random_pieces_equal_one_pass(self):
        for name in SAMPLES:
            data = lib.sample_bytes(name)
            whole = snapshot(one_pass(lib.sample_path(name)))
            # every size cuts lines, CR LF pairs and multi-line records somewhere
            for seed, max_piece, read_piece in ((1, 9, 64), (2, 300, 1000), (3, 5000, 1 << 20), (4, 997, 333)):
                with self.subTest(sample=name, seed=seed):
                    self.assertEqual(snapshot(grown(data, seed, max_piece, read_piece)), whole)

    def test_random_pieces_through_a_real_file(self):
        with lib.TempDir() as d:
            for name in ("run_a.log", "records.log"):
                data = lib.sample_bytes(name)
                whole = snapshot(one_pass(lib.sample_path(name)))
                with self.subTest(sample=name):
                    self.assertEqual(snapshot(grown(data, 5, 4000, 777, d / "Game.log")), whole)

    def test_partial_line_waits_for_its_newline(self):
        data = lib.sample_bytes("run_a.log")
        cut = data.index(b"Quantum Drive Arrived") + 10          # in the middle of the line
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, data[:cut])
            r = pipeline.LogReader(p, lib.NAMES, keep_events=True)
            r.poll()
            self.assertNotIn("quantum_arrived", [e.kind for e in r.events])
            lib.write(p, data[cut:], "ab")
            r.poll()
            self.assertIn("quantum_arrived", [e.kind for e in r.events])

    def test_restart_mid_session_rereads_to_the_same_state(self):
        data = lib.sample_bytes("courier.log")
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, data[:len(data) // 2])
            first = pipeline.LogReader(p, lib.NAMES, keep_events=True)
            first.poll()
            lib.write(p, data[len(data) // 2:], "ab")
            first.poll()
            first.finish()
            again = one_pass(p)                                   # a fresh reader from the top
            self.assertEqual(snapshot(again), snapshot(first))

    def test_rotation_finishes_the_old_session(self):
        a, b = lib.sample_bytes("run_a.log"), lib.sample_bytes("courier.log")
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, a)
            r = pipeline.LogReader(p, lib.NAMES)
            r.poll()
            lib.write(p, b)                                       # emptied in place, new launch
            r.poll()
            r.finish()
            done = r.take_finished()
            self.assertEqual([s["session"] for s in done], ["Build(13220821) 26 Nov 26 (15 11 12)"])
            self.assertEqual(r.state.session["id"], "Build(13220821) 21 Nov 26 (05 19 29)")
            self.assertEqual(r.state.to_dict(), one_pass(lib.sample_path("courier.log")).state.to_dict())


if __name__ == "__main__":
    unittest.main()
