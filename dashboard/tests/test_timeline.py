"""The timeline command: its text and JSON, the session list, the PSOCacheGen skip, and the
`scdash.py` beside `scdash/` import trap (run from the project root and from inside dashboard/)."""
import json
import shutil
import subprocess
import sys
import unittest
from datetime import timedelta, timezone

import scdash_testlib as lib
import scdash
from scdash import timeline
from scdash.summary import build_summary

PACIFIC = timezone(timedelta(hours=-8), "PST")


class TimelineTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader, cls.summary = timeline.run(lib.sample_path("run_a.log"), lib.NAMES)
        cls.text = timeline.render_text(cls.reader, cls.summary, tz=PACIFIC)

    def test_header(self):
        self.assertIn("Session   Build(13220821) 26 Nov 26 (15 11 12)", self.text)
        self.assertIn("Started   Thu Nov 26, 2026 3:11:20 PM (PST)", self.text)
        self.assertIn("PASS: AB6 is joystick 1 and MTQ joystick 2", self.text)
        self.assertIn("1 MOZA AB6 FFB Base  2 MOZA MTQ Throttle Panel  3 Joystick (Razer Huntsman V3 Pro)", self.text)

    def test_the_run_in_local_time(self):
        for line in ("3:14:48 PM  Ship retrieved (XL Hangar)",
                     "3:17:10 PM  Hangar queue: place 2, up to 3 min 20 s",
                     "3:18:01 PM  Quantum destination obstructed",
                     "3:18:28 PM  Hangar ready after 1 min 18 s",
                     "3:19:04 PM  Quantum target: ARC-L4 Faint Glen Station, from New Babbage, fuel estimate 153,453",
                     "3:22:51 PM  Arrived at ARC-L4 Faint Glen Station",
                     "4:03:04 PM  Arrived at MIC-L2 Long Forest Station",
                     "4:05:32 PM  Left the pilot seat of the Drake Golem",
                     "4:21:31 PM  Refinery order completed at MIC-L2 Long Forest Station",
                     "4:37:29 PM  Left the server and quit the game"):
            self.assertIn(line, self.text)

    def test_summary(self):
        self.assertIn("Ended       quit at 4:37:29 PM", self.text)
        self.assertIn("Places      New Babbage -> ARC-L4 Faint Glen Station -> MIC-L2 Long Forest Station -> New Babbage",
                      self.text)
        self.assertIn("Deaths      none", self.text)

    def test_no_player_names(self):
        self.assertNotIn("Pilot_Example", self.text)
        js = json.dumps(timeline.render_json(self.reader, self.summary, tz=PACIFIC))
        self.assertNotIn("Pilot_Example", js)
        self.assertNotIn("OtherPilot", js)

    def test_json_has_the_same_lines(self):
        js = timeline.render_json(self.reader, self.summary, tz=PACIFIC)
        texts = [e["text"] for e in js["events"]]
        self.assertIn("Arrived at ARC-L4 Faint Glen Station", texts)
        self.assertEqual(js["events"][0]["t"], "2026-11-26T15:11:20-08:00")
        self.assertEqual(js["summary"]["session"], "Build(13220821) 26 Nov 26 (15 11 12)")

    def test_unfinished_log_is_running_not_crashed(self):
        data = lib.sample_bytes("run_a.log")
        cut = data.index(b"<2026-11-27T00:21:31")
        with lib.TempDir() as d:
            p = d / "Game.log"
            lib.write(p, data[:cut])
            reader, sm = timeline.run(p, lib.NAMES)
            self.assertEqual(sm["ended"]["how"], "running")
            q = d / "Game Build(13220821) 26 Nov 26 (15 11 12).log"
            lib.write(q, data[:cut])
            reader, sm = timeline.run(q, lib.NAMES)
            self.assertEqual(sm["ended"]["how"], "no quit line (crash or kill)")


class Stage3LinesTest(unittest.TestCase):
    """The summary's new lines: contract kinds, the tally, the law and pay (on built samples, whose
    line shapes are unverified)."""

    def test_tally_kinds_law_and_pay_unverified_shapes(self):
        names = timeline.load_names()
        reader, sm = timeline.run(lib.sample_path("built_bounty.log"), names)
        text = timeline.render_text(reader, sm, tz=PACIFIC)
        self.assertIn("Terrorist Rel Hosk to be Neutralized (combat, active)", text)
        self.assertIn("Combat      destroyed 2, crippled 0, lost 0, downed 0", text)
        self.assertEqual(sm["tally"]["destroyed"], 2)
        reader, sm = timeline.run(lib.sample_path("built_law.log"), names)
        text = timeline.render_text(reader, sm, tz=PACIFIC)
        self.assertIn("Law         Crime committed: Assault against someone", text)
        self.assertIn("Pay         50,250 aUEC (11:09:00 PM)", text)
        self.assertNotIn("Fined 1,500 UEC (11:06:00 PM); Vehicle", text.split("Notices")[-1])   # not twice
        js = json.dumps(timeline.render_json(reader, sm, tz=PACIFIC))
        for name in ("OtherPilot_2", "OtherPilot_3"):
            self.assertNotIn(name, text)
            self.assertNotIn(name, js)


class SessionListTest(unittest.TestCase):
    def test_list_skips_psocachegen_and_reads_head_and_tail(self):
        with lib.TempDir() as live:
            (live / "logbackups").mkdir()
            shutil.copy(lib.sample_path("run_a.log"), live / "logbackups" / "Game Build(13220821) 26 Nov 26 (15 11 12).log")
            shutil.copy(lib.sample_path("courier.log"), live / "logbackups" / "PSOCacheGen Build(1) 05 Nov 26 (10 07 12).log")
            shutil.copy(lib.sample_path("menu_return.log"), live / "Game.log")
            rows = timeline.list_sessions(live)
            self.assertEqual([r["session"] for r in rows],
                             ["Build(13220821) 21 Nov 26 (11 15 16)", "Build(13220821) 26 Nov 26 (15 11 12)"])
            self.assertEqual(rows[1]["ended"], "quit")
            self.assertAlmostEqual(rows[1]["length_s"], 5169.6, delta=1)
            self.assertTrue(rows[0]["current"])
            with self.assertRaises(SystemExit):
                timeline.run(live / "logbackups" / "PSOCacheGen Build(1) 05 Nov 26 (10 07 12).log")
            self.assertEqual(timeline.find_log("26 Nov 26 (15 11 12)", live).name,
                             "Game Build(13220821) 26 Nov 26 (15 11 12).log")

    def test_summary_of_a_session_that_never_quit(self):
        data = lib.sample_bytes("run_a.log")
        mem = lib.MemoryLog(data[:data.index(b"<2026-11-27T00:37:29")])
        from scdash import pipeline
        r = pipeline.LogReader("x.log", lib.NAMES, opener=mem.opener)
        r.poll()
        self.assertEqual(build_summary(r.state, complete=True)["ended"]["how"], "no quit line (crash or kill)")


class CommandLineTest(unittest.TestCase):
    """`import scdash` must find the package, not the script beside it, however it is run."""

    def test_package_not_script(self):
        self.assertTrue(hasattr(scdash, "__path__"))

    def run_cli(self, cwd, script):
        out = subprocess.run([sys.executable, script, "timeline", str(lib.sample_path("run_a.log"))],
                             cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Session   Build(13220821) 26 Nov 26 (15 11 12)", out.stdout)
        return out.stdout

    def test_from_project_root(self):
        self.run_cli(lib.DASHBOARD.parent, "dashboard/scdash.py")

    def test_from_inside_dashboard(self):
        self.run_cli(lib.DASHBOARD, "scdash.py")

    def test_json_option(self):
        out = subprocess.run([sys.executable, "dashboard/scdash.py", "timeline", str(lib.sample_path("courier.log")),
                              "--json"], cwd=str(lib.DASHBOARD.parent), capture_output=True, text=True,
                             encoding="utf-8", timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(len(data["summary"]["contracts"]), 5)


if __name__ == "__main__":
    unittest.main()
