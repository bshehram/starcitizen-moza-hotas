"""The follower: partial lines, pieces, rotation, overlong lines, and no handle kept between polls."""
import os
import sys
import unittest

import scdash_testlib as lib
from scdash import winutil
from scdash.tail import Follower


class ListSink:
    """Collects what the follower hands on. `got` and `offsets` restart at each reset."""

    def __init__(self):
        self.got, self.offsets, self.resets = [], [], 0

    def reset(self):
        self.resets += 1
        self.got, self.offsets = [], []

    def lines(self, lines, offsets):
        self.got.extend(lines)
        self.offsets.extend(offsets)


def first(n=1):
    return b'<2026-11-26T23:11:20.067Z> BackupNameAttachment=" Build(1) 26 Nov 26 (15 11 1%d)"  -- used by backup system\r\n' % n


class FollowerTest(unittest.TestCase):
    def test_missing_file(self):
        with lib.TempDir() as d:
            self.assertEqual(Follower(d / "Game.log").poll(ListSink()), "missing")

    def test_partial_last_line_is_held(self):
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, first() + b"<2026-11-26T23:11:21.000Z> one\r\n<2026-11-26T23:11:22.000Z> tw")
            f, s = Follower(p), ListSink()
            self.assertEqual(f.poll(s), "read")
            self.assertEqual(len(s.got), 2)               # the first line and "one"; "tw" waits
            lib.write(p, b"o\r\n", "ab")
            f.poll(s)
            self.assertEqual(s.got[-1], b"<2026-11-26T23:11:22.000Z> two\r")
            self.assertEqual(s.offsets[-1], len(first()) + len(b"<2026-11-26T23:11:21.000Z> one\r\n"))

    def test_offsets_point_at_line_starts(self):
        data = lib.sample_bytes("run_a.log")
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, data)
            s = ListSink()
            Follower(p, piece=997).poll(s)
            for line, off in zip(s.got, s.offsets):
                self.assertEqual(data[off:off + len(line)], line)
            self.assertEqual(len(s.got), data.count(b"\n"))

    def test_shorter_file_is_a_new_session(self):
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, first(1) + b"<2026-11-26T23:11:21.000Z> " + b"x" * 500 + b"\r\n")
            f, s = Follower(p), ListSink()
            f.poll(s)
            lib.write(p, first(1))                           # emptied and rewritten, shorter
            f.poll(s)
            self.assertEqual(s.resets, 1)
            self.assertEqual(s.got, [first(1).rstrip(b"\n")])

    def test_changed_first_line_is_a_new_session_even_when_longer(self):
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, first(1) + b"<2026-11-26T23:11:21.000Z> old\r\n")
            f, s = Follower(p), ListSink()
            f.poll(s)
            body = b"".join(b"<2026-11-27T00:00:%02d.000Z> new %d\r\n" % (i, i) for i in range(50))
            lib.write(p, first(2) + body)                    # longer than the old offset
            f.poll(s)
            self.assertEqual(s.resets, 1)
            self.assertEqual(s.got[0], first(2).rstrip(b"\n"))
            self.assertEqual(len(s.got), 51)
            self.assertEqual(f.sessions, 2)

    def test_emptied_file_waits_then_starts_over(self):
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, first(1) + b"<2026-11-26T23:11:21.000Z> old\r\n")
            f, s = Follower(p), ListSink()
            f.poll(s)
            lib.write(p, b"")
            self.assertEqual(f.poll(s), "waiting")
            self.assertEqual(s.resets, 1)
            lib.write(p, first(3))
            f.poll(s)
            self.assertEqual(s.resets, 1)                    # no second reset for the same change
            self.assertEqual(s.got, [first(3).rstrip(b"\n")])

    def test_overlong_line_is_cut_and_memory_stays_bounded(self):
        with lib.TempDir() as d:
            p = d / "Game.log"
            long = b"<2026-11-26T23:11:21.000Z> " + b"y" * 300000
            lib.write(p, first() + long + b"\r\n<2026-11-26T23:11:22.000Z> after\r\n")
            for piece in (1000, 4096, 1 << 20):
                f, s = Follower(p, piece=piece, max_line=1024), ListSink()
                f.poll(s)
                self.assertEqual(len(s.got), 3)
                self.assertEqual(s.got[1], long[:1024])
                self.assertEqual(s.got[2], b"<2026-11-26T23:11:22.000Z> after\r")
                self.assertLessEqual(len(f._partial), 1024)

    def test_budget_limits_one_poll(self):
        data = lib.sample_bytes("courier.log")
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, data)
            f, s = Follower(p, piece=4096), ListSink()
            f.poll(s, budget=10000)
            self.assertEqual(f.offset, 10000)
            while f.poll(s, budget=10000) == "read":
                pass
            self.assertEqual(len(s.got), data.count(b"\n"))

    def test_no_handle_is_kept_between_polls(self):
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, lib.sample_bytes("run_a.log"))
            Follower(p).poll(ListSink())
            os.replace(p, d / "moved.log")                   # fails on Windows if a handle were open
            os.remove(d / "moved.log")

    @unittest.skipUnless(sys.platform == "win32", "Windows sharing modes")
    def test_open_shared_allows_delete_and_rename_while_open(self):
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, b"abc\n")
            f = winutil.open_shared(p)
            try:
                os.replace(p, d / "renamed.log")             # the game could rotate it under us
                self.assertEqual(f.read(), b"abc\n")
            finally:
                f.close()

    def test_open_shared_missing_raises_file_not_found(self):
        with lib.TempDir() as d:
            with self.assertRaises(FileNotFoundError):
                winutil.open_shared(d / "nope.log")


if __name__ == "__main__":
    unittest.main()
