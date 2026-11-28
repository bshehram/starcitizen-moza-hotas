#!/usr/bin/env python3
"""Tests for tools/scbot.py. Run from the project root:  python tools/test_scbot.py

Everything runs in temporary folders: the script is pointed at a sandbox (SCBOT_ROOT, and
configure() for the calls made in this process), the transcripts are made up here, and install
is given --root and --home. Nothing under the real .claude folders is read or written.

Most hook calls run in this process, with a clock the tests can move (scbot.now). The launcher,
unreadable input and the parallel starts run as real processes, the way Claude Code runs them.
"""
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SCRIPT = Path(__file__).resolve().with_name("scbot.py")
sys.path.insert(0, str(SCRIPT.parent))
import scbot  # noqa: E402

FABLE, OPUS = "claude-fable-5-2", "claude-opus-5-5"
WINDOWS = os.name == "nt"
MIN = 60.0
HOUR = 3600.0


def entry(tokens, model=FABLE, sidechain=False, kind="assistant", out=500):
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 1000,
             "cache_read_input_tokens": tokens - 1002 - out, "output_tokens": out}
    return json.dumps({"type": kind, "isSidechain": sidechain,
                       "message": {"model": model, "usage": usage}})


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root, self.proj, self.home = base / "repo", base / "projects", base / "home"
        for path in (self.root, self.proj, self.home):
            path.mkdir()
        self.saved_env = os.environ.copy()
        for name in list(os.environ):
            if name.startswith("SCBOT_") or name in ("CLAUDE_CODE_DISABLE_1M_CONTEXT",
                                                     "CLAUDE_CONFIG_DIR"):
                del os.environ[name]
        os.environ["SCBOT_ROOT"] = str(self.root)
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home))
        scbot.configure(self.root)
        scbot.LEARNED = None
        self.shift = 0.0
        self.real_now, self.real_wait = scbot.now, scbot.LOCK_WAIT
        scbot.now = lambda: time.time() + self.shift
        scbot.LOCK_WAIT = 0.3
        self.errors_ok = False

    def tearDown(self):
        scbot.now, scbot.LOCK_WAIT = self.real_now, self.real_wait
        os.environ.clear()
        os.environ.update(self.saved_env)
        scbot.configure(scbot.find_root())
        scbot.LEARNED = None
        scbot.load_limits()
        for path in Path(self.tmp.name).rglob("*"):
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
        self.tmp.cleanup()

    # --- making things
    def transcript(self, sid, tokens=None, model=FABLE, agent=None, extra=(), out=500):
        path = self.proj / ("%s.jsonl" % sid)
        if agent:
            path = self.proj / sid / "subagents" / ("agent-%s.jsonl" % agent)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({"type": "user", "message": {"content": "hi"}})]
        lines += list(extra)
        if tokens:
            lines.append(entry(tokens, model, sidechain=bool(agent), out=out))
        lines.append(json.dumps({"type": "user", "message": {"content": "tool result"}}))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def session_file(self, sid="s1"):
        return self.root / ".claude/scbot/state" / sid / "session.json"

    def session(self, sid="s1"):
        return json.loads(self.session_file(sid).read_text(encoding="utf-8"))

    def edit_session(self, sid, **change):
        record = self.session(sid)
        record.update(change)
        self.session_file(sid).write_text(json.dumps(record), encoding="utf-8")

    def log(self):
        path = self.root / ".claude/scbot/guard.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # --- calling the hook
    def hook(self, event, sid="s1", **fields):
        payload = {"hook_event_name": event, "session_id": sid,
                   "transcript_path": str(self.proj / ("%s.jsonl" % sid)),
                   "cwd": str(self.root)}
        payload.update(fields)
        result = scbot.run_hook(json.loads(json.dumps(payload)))
        json.dumps(result).encode("ascii")            # what cmd_hook writes must be ASCII JSON
        if not self.errors_ok:
            self.assertNotIn("fault error", self.log())
        return result

    def tool(self, name, sid="s1", agent=None, agent_type=None, tool_use_id=None,
             **tool_input):
        fields = {"tool_name": name, "tool_input": tool_input}
        if tool_use_id:
            fields["tool_use_id"] = tool_use_id
        if agent:
            fields.update(agent_id=agent, agent_type=agent_type or "scbot-worker")
        return self.hook("PreToolUse", sid, **fields)

    def start(self, agent, sid="s1", kind="scbot-worker"):
        return self.hook("SubagentStart", sid, agent_id=agent, agent_type=kind)

    def stop(self, agent, sid="s1", kind="scbot-worker", message="done", **extra):
        return self.hook("SubagentStop", sid, agent_id=agent, agent_type=kind,
                         last_assistant_message=message, **extra)

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = scbot.main(["scbot.py"] + list(args))
        return code, out.getvalue()

    def run_script(self, args, data=b"{}", env=None, timeout=60):
        run = subprocess.run([sys.executable] + list(args), input=data, capture_output=True,
                             env=env or self.env, timeout=timeout)
        return run.returncode, run.stdout, run.stderr

    # --- reading results
    def denied(self, result):
        return bool(result) and result.get("hookSpecificOutput", {}).get(
            "permissionDecision") == "deny"

    def reason(self, result):
        return result["hookSpecificOutput"].get("permissionDecisionReason", "")

    def context(self, result):
        return (result or {}).get("hookSpecificOutput", {}).get("additionalContext", "")

    def told_user(self, result):
        return (result or {}).get("systemMessage", "")

    def running(self, sid="s1"):
        record = self.session(sid)
        running, reserved = scbot.crew_count(record)
        return len(running) + len(reserved)


# ============================================================================================
class Measuring(Sandbox):
    def test_newest_main_entry_wins_and_sidechains_are_skipped(self):
        path = self.transcript("s1", extra=[entry(100_000), entry(250_000),
                                            entry(400_000, sidechain=True),
                                            entry(999_000, kind="progress")])
        self.assertEqual(scbot.last_usage(path, main_only=True), (250_000, FABLE))

    def test_every_usage_figure_counts_output_included(self):
        path = self.transcript("s1", 300_000, out=40_000)
        self.assertEqual(scbot.last_usage(path, main_only=True)[0], 300_000)

    def test_zero_usage_and_synthetic_entries_are_passed_over(self):
        zero = json.dumps({"type": "assistant", "message": {"model": FABLE, "usage": {
            "input_tokens": 0, "output_tokens": 0}}})
        synthetic = entry(700_000, "<synthetic>")
        path = self.transcript("s1", extra=[entry(321_000), zero, synthetic])
        self.assertEqual(scbot.last_usage(path, main_only=True), (321_000, FABLE))

    def test_a_very_long_line_after_the_entry_is_read_past(self):
        blob = json.dumps({"type": "user", "message": {"content": "x" * 3_000_000}})
        path = self.transcript("s1", extra=[entry(321_000), blob, blob])
        self.assertEqual(scbot.last_usage(path, main_only=True)[0], 321_000)

    def test_no_usage_gives_none_and_a_missing_file_is_a_fault(self):
        self.assertIsNone(scbot.last_usage(self.transcript("s1"), main_only=True))
        self.assertIsNone(scbot.measure(self.proj / "s1.jsonl"))
        self.assertEqual(scbot.measure(self.proj / "missing.jsonl")["fault"], "missing")
        self.assertEqual(scbot.measure(self.proj)["fault"], "unreadable")      # a folder

    def test_window_table(self):
        for model, want in ((FABLE, 1_000_000), (OPUS, 1_000_000), ("claude-opus-4-7", 1_000_000),
                            ("claude-opus-4-6", 200_000), ("claude-sonnet-5", 1_000_000),
                            ("claude-sonnet-4-5-20250929", 200_000),
                            ("claude-haiku-5-5", 1_000_000), ("claude-haiku-4-5", 200_000),
                            ("claude-opus-4-6[1m]", 1_000_000), ("claude-mythos-1", 1_000_000)):
            self.assertEqual(scbot.window_for(model), want, model)
        for model in ("something-else", "", "<synthetic>", "gpt-9"):
            self.assertIsNone(scbot.window_for(model), model)

    def test_both_window_overrides(self):
        os.environ["CLAUDE_CODE_DISABLE_1M_CONTEXT"] = "1"
        self.assertEqual(scbot.window_for(OPUS), 200_000)
        del os.environ["CLAUDE_CODE_DISABLE_1M_CONTEXT"]
        os.environ["SCBOT_CONTEXT_WINDOW"] = "500000"
        self.assertEqual(scbot.window_for(OPUS), 500_000)
        self.assertEqual(scbot.window_for("unknown-model"), 500_000)

    def windows(self):
        path = self.root / ".claude/scbot/state/windows.json"
        return json.loads(path.read_text()) if path.exists() else None

    def test_three_separate_readings_above_the_table_correct_it_and_say_so(self):
        sonnet = "claude-sonnet-4-6"
        for n, tokens in enumerate((300_000, 300_000, 310_000)):
            self.transcript("s1", tokens, sonnet)
            result = self.tool("Read", file_path="x")
            self.assertFalse(self.denied(result))
            self.assertNotIn("table is wrong", self.told_user(result))
        self.assertEqual(len(self.windows()["seen"][sonnet]), 2)      # the repeat is one reading
        self.assertNotIn(sonnet, self.windows()["windows"])
        self.transcript("s1", 150_000, sonnet)
        self.assertIn("75%", self.context(self.tool("Read", file_path="y")))   # still the table's
        self.transcript("s2", 320_000, sonnet)
        result = self.tool("Read", "s2", file_path="x")
        self.assertIn("table is wrong", self.context(result))
        self.assertIn("table is wrong", self.told_user(result))
        self.assertEqual(self.windows()["windows"][sonnet], 1_000_000)
        scbot.LEARNED = None                     # a later process reads the correction back
        self.assertEqual(scbot.window_for(sonnet, 150_000), 1_000_000)

    def test_one_odd_reading_never_switches_the_limits_off(self):
        self.transcript("s1", 100_000)
        self.transcript("s1", 1_500_000, OPUS, agent="odd")
        result = self.tool("Read", agent="odd", file_path="x")
        self.assertFalse(self.denied(result))
        self.assertIn("cannot believe", self.told_user(result))
        self.assertIsNone(self.windows())
        self.transcript("s1", 850_000, OPUS, agent="b1")
        self.assertTrue(self.denied(self.tool("Read", agent="b1", file_path="x")))
        self.transcript("s2", 950_000, OPUS)
        self.assertTrue(self.denied(self.tool("Agent", "s2", subagent_type="scbot-worker")))
        os.environ["SCBOT_CONTEXT_WINDOW"] = "2000000"          # only the user can go higher
        self.transcript("s3", 1_500_000, OPUS)
        self.assertIn("75%", self.context(self.tool("Read", "s3", file_path="x")))

    def test_a_learned_window_is_never_above_one_million(self):
        path = self.root / ".claude/scbot/state/windows.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"windows": {OPUS: 2_000_000, "claude-sonnet-4-6": 5_000_000}}))
        self.assertEqual(scbot.window_for(OPUS), 1_000_000)
        self.assertEqual(scbot.window_for("claude-sonnet-4-6"), 1_000_000)

    def test_no_command_writes_the_window_table(self):
        odd = self.proj / "elsewhere.jsonl"
        for tokens, model in ((1_200_000, FABLE), (300_000, "claude-sonnet-4-6")):
            odd.write_text(entry(tokens, model) + "\n", encoding="utf-8")
            for _ in range(3):
                self.cli("meter", "--transcript", str(odd))
        self.transcript("s1", 300_000, "claude-sonnet-4-6")
        self.hook("SessionStart", source="startup")
        self.edit_session("s1", transcript=str(odd))
        for _ in range(3):
            self.cli("status", "--session", "SCBOT-1")
        self.assertIsNone(self.windows())


# ============================================================================================
class Launcher(Sandbox):
    """Finding 1: the hook can never block by accident."""

    def launch(self, script, data=b"{}"):
        return self.run_script(["-I", "-S", "-c", scbot.LAUNCHER, str(script)], data)

    def test_the_launcher_text_survives_any_quoting(self):
        for bad in ('"', "\\", "\n", "\r"):
            self.assertNotIn(bad, scbot.LAUNCHER)
        self.assertIn(scbot.HOOK_MARK, scbot.LAUNCHER)

    def test_a_missing_script_lets_everything_through(self):
        code, out, err = self.launch(self.root / "nowhere" / "scbot.py",
                                     b'{"hook_event_name": "PreToolUse"}')
        self.assertEqual((code, out, err), (0, b"", b""))       # silent, not just exit 0
        code, out, _ = self.run_script(["-I", "-S", "-c", scbot.LAUNCHER])     # no path at all
        self.assertEqual((code, out), (0, b""))

    def test_a_broken_script_exits_0(self):
        for body in ("import sys\nsys.exit(2)\n", "def broken(:\n", "raise MemoryError\n",
                     "import os\nos.environ['X'] = 1\n"):
            bad = self.root / "bad.py"
            bad.write_text(body, encoding="utf-8")
            code, out, _ = self.launch(bad)
            self.assertEqual(code, 0, body)
        main = self.root / "exits.py"
        main.write_text("def main(argv):\n    raise SystemExit(2)\n", encoding="utf-8")
        self.assertEqual(self.launch(main)[0], 0)

    def test_the_real_script_decides_through_the_launcher(self):
        self.transcript("s1", 910_000)
        payload = {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Agent",
                   "tool_input": {"subagent_type": "scbot-worker"},
                   "transcript_path": str(self.proj / "s1.jsonl")}
        code, out, _ = self.launch(SCRIPT, json.dumps(payload).encode())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_garbage_input_and_guard_off(self):
        for data in (b"not json", b"[1, 2]", b"null", b'"hi"', b'{"hook_event_name": 5}',
                     b'{"hook_event_name":"PreToolUse","x":"\xff\xfe"}'):
            code, out, _ = self.run_script(["-S", str(SCRIPT), "hook"], data)
            self.assertEqual(code, 0, data)
        code, out, _ = self.run_script(["-S", str(SCRIPT), "hook"], b"not json")
        self.assertEqual(code, 0)
        self.transcript("s1", 990_000)
        off = dict(self.env, SCBOT_GUARD="off")
        code, out, _ = self.run_script(["-S", str(SCRIPT), "hook"], json.dumps(
            {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Agent",
             "transcript_path": str(self.proj / "s1.jsonl")}).encode(), env=off)
        self.assertEqual((code, out), (0, b""))

    def test_unreadable_input_is_said_once(self):
        code, first, _ = self.run_script(["-S", str(SCRIPT), "hook"], b"not json")
        code, second, _ = self.run_script(["-S", str(SCRIPT), "hook"], b"not json")
        self.assertIn("could not read", json.loads(first)["systemMessage"])
        self.assertEqual(second, b"")


# ============================================================================================
class FailOpen(Sandbox):
    """Findings 2 and 3 (part): the guard fails open, visibly, and still decides on what it
    can read."""

    def test_state_it_cannot_write_still_refuses_and_says_so(self):
        self.transcript("s1", 970_000)
        self.hook("SessionStart", source="startup")
        self.edit_session("s1", seen_t=0)               # forces a write on the next call
        os.chmod(self.session_file(), stat.S_IREAD)
        result = self.tool("Read", file_path=str(self.root / "x.py"))
        self.assertTrue(self.denied(result))
        self.assertIn("cannot write", self.reason(result))
        self.assertIn("cannot write", self.told_user(result))
        again = self.tool("Read", file_path=str(self.root / "x.py"))
        self.assertTrue(self.denied(again))
        self.assertNotIn("cannot write", self.reason(again))          # said once, not each call
        self.shift = 6 * MIN
        self.assertIn("cannot write", self.told_user(self.tool("Read", file_path="x")))
        self.assertIn("fault state in session s1", self.log())

    def test_a_sub_agent_whose_marker_cannot_be_written_is_still_held(self):
        self.transcript("s1", 100_000)
        self.start("a1")
        self.transcript("s1", 850_000, OPUS, agent="a1")
        seen = self.root / ".claude/scbot/state/s1/crew/a1.seen"
        seen.write_text("")
        os.utime(seen, (0, 0))
        os.chmod(seen, stat.S_IREAD)
        result = self.tool("Read", agent="a1", file_path="x")
        self.assertTrue(self.denied(result))
        self.assertIn("cannot write", self.told_user(result))

    @unittest.skipUnless(WINDOWS, "share modes are a Windows matter")
    def test_a_record_held_open_with_no_sharing_is_not_replaced(self):
        import ctypes
        self.transcript("s1", 970_000)
        self.hook("SessionStart", source="startup")
        label = self.session()["label"]
        kernel = ctypes.windll.kernel32
        kernel.CreateFileW.restype = ctypes.c_void_p
        handle = kernel.CreateFileW(str(self.session_file()), 0x80000000, 0, None, 3, 0x80, None)
        try:
            result = self.tool("Read", file_path="x")
            self.assertTrue(self.denied(result))
            self.assertIn("cannot read", self.told_user(result))
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
        self.assertEqual(self.session()["label"], label)

    def test_a_missing_transcript_is_said(self):
        self.transcript("s1", 100_000)
        self.start("a1")                                    # its own transcript never written
        result = self.tool("Read", agent="a1", file_path="x")
        self.assertFalse(self.denied(result))
        self.assertIn("cannot find", self.context(result))
        self.assertIn("cannot find", self.told_user(result))
        lead = self.hook("PreToolUse", "s9", tool_name="Read", tool_input={},
                         transcript_path=str(self.proj / "nope.jsonl"))
        self.assertIn("cannot find", self.told_user(lead))
        none = self.hook("PreToolUse", "s8", tool_name="Read", tool_input={}, transcript_path="")
        self.assertIn("cannot find", self.told_user(none))

    def test_a_sub_agent_given_its_own_transcript_path_is_measured_on_it(self):
        self.transcript("s1", 100_000)
        own = self.transcript("s1", 850_000, OPUS, agent="a1")
        result = self.hook("PreToolUse", "s1", tool_name="Read", tool_input={}, agent_id="a1",
                           agent_type="scbot-worker", transcript_path=str(own))
        self.assertTrue(self.denied(result))
        self.assertEqual(self.session()["transcript"], str(self.proj / "s1.jsonl")) \
            if self.session_file().exists() and self.session().get("transcript") else None

    def test_an_unreadable_transcript_is_said_for_a_lead_and_for_a_sub_agent(self):
        junk = json.dumps({"type": "user", "message": {"content": "y" * 400_000}})
        self.transcript("s1", extra=[junk])
        first = self.tool("Read", file_path="x")
        self.assertFalse(self.denied(first))
        self.assertIn("not enforced", self.context(first))
        self.assertIsNone(self.tool("Read", file_path="x"))
        self.transcript("s1", extra=[junk], agent="a1")
        sub = self.tool("Read", agent="a1", file_path="x")
        self.assertFalse(self.denied(sub))
        self.assertIn("not enforced", self.context(sub))

    def test_an_unknown_model_is_said_and_not_enforced(self):
        self.transcript("s1", 950_000, "totally-new-model-9")
        result = self.tool("Agent", subagent_type="scbot-worker", prompt="p")
        self.assertFalse(self.denied(result))
        self.assertIn("no context window", self.told_user(result))

    def test_a_fault_of_its_own_lets_the_call_through_and_says_so(self):
        self.errors_ok = True
        self.transcript("s1", 970_000)
        real = scbot.measure_path
        scbot.measure_path = lambda *a, **k: 1 / 0
        try:
            result = self.tool("Read", file_path="x")
        finally:
            scbot.measure_path = real
        self.assertFalse(self.denied(result))
        self.assertIn("fault of its own", self.told_user(result))
        self.assertIn("ZeroDivisionError", self.log())

    def test_a_record_another_process_holds_for_a_moment_is_read_again(self):
        self.transcript("s1", 100_000)
        self.hook("SessionStart", source="startup")
        real, held = open, {"n": 0}

        def busy_once(path, *a, **k):
            if str(path).endswith("session.json") and held["n"] < 2:
                held["n"] += 1
                raise PermissionError("held by another process")
            return real(path, *a, **k)
        scbot.open = busy_once
        try:
            result = self.tool("Read", file_path="x")
        finally:
            del scbot.open
        self.assertNotIn("cannot read", self.told_user(result))
        self.assertEqual(held["n"], 2)

    def test_a_rename_refused_for_a_moment_is_tried_again(self):
        target = self.root / "x.json"
        real, held = os.replace, {"n": 0}

        def busy_twice(src, dst):
            if held["n"] < 3:
                held["n"] += 1
                raise PermissionError("in use")
            return real(src, dst)
        scbot.os.replace = busy_twice
        try:
            ok = scbot.write_json(target, {"a": 1})
        finally:
            scbot.os.replace = real
        self.assertTrue(ok)
        self.assertEqual(json.loads(target.read_text()), {"a": 1})

    def test_odd_tool_input_is_handled(self):
        self.transcript("s1", 100_000)
        self.transcript("s1", 850_000, OPUS, agent="a1")
        for odd in ("x", [1], None, 5):
            result = self.hook("PreToolUse", tool_name="Read", tool_input=odd, agent_id="a1",
                               agent_type="scbot-worker")
            self.assertTrue(self.denied(result), odd)


# ============================================================================================
class Lead(Sandbox):
    def test_quiet_below_the_heads_up_line(self):
        self.transcript("s1", 300_000)
        self.assertIsNone(self.tool("Read", file_path="x"))
        self.assertIsNone(self.tool("Agent", subagent_type="scbot-worker", prompt="p"))

    def test_heads_up_from_70_exactly_and_said_once(self):
        self.transcript("s1", 699_999)
        self.assertIsNone(self.tool("Read", file_path="x"))
        self.transcript("s1", 700_000)
        self.assertIn("70%", self.context(self.tool("Read", file_path="x")))
        self.assertIsNone(self.tool("Read", file_path="y"))
        self.transcript("s1", 720_000)
        self.assertIsNone(self.tool("Read", file_path="y"))           # once per band

    def test_pending_from_90_exactly(self):
        self.transcript("s1", 899_999)
        self.assertIsNone(self.tool("Agent", subagent_type="scbot-worker", prompt="p"))
        self.transcript("s2", 900_000)
        self.assertTrue(self.denied(self.tool("Agent", "s2", subagent_type="scbot-worker")))

    def test_pending_closing_refuses_new_sub_agents_and_lets_closing_work_through(self):
        self.transcript("s1", 910_000)
        self.start("a1")
        result = self.tool("Agent", subagent_type="scbot-worker", prompt="p")
        self.assertTrue(self.denied(result))
        self.assertIn("pending closing", self.reason(result))
        self.assertIn("1 sub-agent is still running", self.reason(result))
        self.assertTrue(self.denied(self.tool("Workflow", script="x")))
        for name in ("Write", "Edit", "Bash", "Read", "Grep", "AskUserQuestion", "Artifact",
                     "Skill", "mcp__x__y"):
            self.assertFalse(self.denied(self.tool(name, file_path="notes.md")), name)
        prompt = self.hook("UserPromptSubmit", prompt="one more thing")
        self.assertIn("pending closing", self.context(prompt))
        self.assertTrue(self.session()["pending"])

    def test_the_pending_notice_comes_once_per_percent(self):
        self.transcript("s1", 912_000)
        self.assertIn("91%", self.context(self.tool("Write", file_path="n.md")))
        self.assertIsNone(self.tool("Write", file_path="n.md"))
        self.transcript("s1", 922_000)
        self.assertIn("92%", self.context(self.tool("Write", file_path="n.md")))

    def test_pending_follows_the_meter_down_again(self):
        self.transcript("s1", 910_000)
        self.assertTrue(self.denied(self.tool("Agent", subagent_type="scbot-worker")))
        self.transcript("s1", 100_000)                 # a typed /compact
        result = self.tool("Agent", subagent_type="scbot-worker", prompt="p")
        self.assertFalse(self.denied(result))
        self.assertIn("no longer pending closing", self.context(result))
        self.assertNotIn("pending", self.session())
        self.assertNotIn("pending closing", self.context(
            self.hook("UserPromptSubmit", prompt="next")))

    def test_pending_follows_the_meter_in_a_prompt_too(self):
        self.transcript("s1", 910_000)
        self.assertIn("pending closing", self.context(self.hook("UserPromptSubmit", prompt="a")))
        self.transcript("s1", 600_000)
        text = self.context(self.hook("UserPromptSubmit", prompt="b"))
        self.assertIn("no longer pending", text)
        self.assertNotIn("is pending closing", text)

    def test_a_reading_above_the_table_clears_pending(self):
        self.transcript("s1", 185_000, "claude-sonnet-4-6")
        self.assertTrue(self.denied(self.tool("Agent", subagent_type="scbot-worker")))
        self.transcript("s1", 300_000, "claude-sonnet-4-6")
        result = self.tool("Agent", subagent_type="scbot-worker", prompt="p")
        self.assertFalse(self.denied(result))
        self.assertIn("no longer pending", self.context(result))

    def test_a_resume_of_a_finished_sub_agent_is_refused_when_pending_by_id_or_name(self):
        self.transcript("s1", 905_000)
        self.start("a1")
        self.start("a2")
        self.hook("PostToolUse", tool_name="Agent", tool_input={"name": "helper"},
                  tool_response={"agentId": "a1"})
        self.stop("a1")
        self.assertTrue(self.denied(self.tool("SendMessage", to="a1", message="go on")))
        self.assertTrue(self.denied(self.tool("SendMessage", to="helper", message="go on")))
        self.assertFalse(self.denied(self.tool("SendMessage", to="a2", message="status?")))

    def test_the_reserve_from_96_exactly(self):
        self.transcript("s1", 959_999)
        self.assertFalse(self.denied(self.tool("Grep", pattern="x")))
        self.transcript("s2", 960_000)
        self.assertTrue(self.denied(self.tool("Grep", "s2", pattern="x")))

    def test_six_running_is_the_most_and_a_slot_frees_when_one_stops(self):
        self.transcript("s1", 100_000)
        for n in range(6):
            self.start("a%d" % n)
        result = self.tool("Agent", subagent_type="scbot-worker", prompt="p")
        self.assertTrue(self.denied(result))
        self.assertIn("6 sub-agents are running", self.reason(result))
        self.assertIn("crew --session SCBOT-1", self.reason(result))
        self.assertNotIn("crew clear", self.reason(result))
        self.stop("a3")
        self.assertIsNone(self.tool("Agent", subagent_type="scbot-worker", prompt="p"))
        self.start("a9")
        self.assertTrue(self.denied(self.tool("SendMessage", to="a3", message="more")))

    def test_each_role_runs_on_its_own_model_and_effort(self):
        self.transcript("s1", 100_000)
        ok = [dict(subagent_type="scbot-architect"), dict(subagent_type="scbot-architect",
              model="fable"), dict(subagent_type="scbot-worker", model="opus", effort="xhigh"),
              dict(subagent_type="scbot-worker", model=OPUS),
              dict(subagent_type="scbot-architect", model=FABLE),
              dict(subagent_type="general-purpose", model="haiku")]
        bad = [dict(subagent_type="scbot-architect", model="opus"),
               dict(subagent_type="scbot-worker", model="fable"),
               dict(subagent_type="scbot-worker", effort="high")]
        for call in ok:
            self.assertIsNone(self.tool("Agent", prompt="p", **call), call)
            self.hook("PostToolUse", tool_name="Agent", tool_input={}, tool_response={})
        for call in bad:
            self.assertTrue(self.denied(self.tool("Agent", prompt="p", **call)), call)

    def test_a_fork_is_refused_from_40_exactly(self):
        self.transcript("s1", 399_999)
        self.assertIsNone(self.tool("Agent", subagent_type="fork", prompt="p"))
        self.transcript("s2", 400_000)
        self.assertTrue(self.denied(self.tool("Agent", "s2", subagent_type="fork", prompt="p")))

    def test_limits_come_from_the_environment(self):
        self.transcript("s1", 520_000)
        os.environ["SCBOT_LEAD_LIMIT"] = "50"
        self.assertTrue(self.denied(self.tool("Agent", subagent_type="scbot-worker")))


# ============================================================================================
class Counting(Sandbox):
    """Finding 3 and 7: the running count reserves, and heals itself."""

    def test_four_starts_in_one_message_while_four_run_let_two_through(self):
        self.transcript("s1", 100_000)
        for n in range(4):
            self.start("p%d" % n)
        results = [self.tool("Agent", tool_use_id="t%d" % n, subagent_type="scbot-worker")
                   for n in range(4)]
        self.assertEqual([self.denied(r) for r in results], [False, False, True, True])
        self.assertIn("2 starting", self.reason(results[2]))

    def test_four_resumes_while_four_run_let_two_through(self):
        self.transcript("s1", 100_000)
        for n in range(4):
            self.start("f%d" % n)
            self.stop("f%d" % n)
        for n in range(4):
            self.start("p%d" % n)
        results = [self.tool("SendMessage", to="f%d" % n, message="go") for n in range(4)]
        self.assertEqual([self.denied(r) for r in results], [False, False, True, True])

    def test_workflow_counts_like_agent(self):
        self.transcript("s1", 100_000)
        for n in range(6):
            self.start("a%d" % n)
        self.assertTrue(self.denied(self.tool("Workflow", script="x")))
        self.transcript("s1", 100_000, agent="a0")
        self.assertTrue(self.denied(self.tool("Workflow", agent="a0", script="x")))

    def test_a_start_takes_the_slot_held_for_it(self):
        self.transcript("s1", 100_000)
        for n in range(5):
            self.start("a%d" % n)
        self.assertIsNone(self.tool("Agent", tool_use_id="t1", subagent_type="scbot-worker"))
        self.assertEqual(self.running(), 6)
        self.start("a5")
        self.assertEqual(self.running(), 6)                 # not seven
        self.assertTrue(self.denied(self.tool("Agent", tool_use_id="t2",
                                              subagent_type="scbot-worker")))

    def test_a_held_slot_lapses_and_the_calls_result_frees_it(self):
        self.transcript("s1", 100_000)
        os.environ["SCBOT_CREW_MAX"] = "1"
        self.assertIsNone(self.tool("Agent", tool_use_id="t1", subagent_type="scbot-worker"))
        self.assertTrue(self.denied(self.tool("Agent", tool_use_id="t2",
                                              subagent_type="scbot-worker")))
        self.hook("PostToolUse", tool_name="Agent", tool_use_id="t1", tool_input={},
                  tool_response={"agentId": "x"})          # the call ended, no start seen
        self.assertIsNone(self.tool("Agent", tool_use_id="t3", subagent_type="scbot-worker"))
        self.shift = 110                                    # a start has not come yet
        self.assertTrue(self.denied(self.tool("Agent", tool_use_id="t4",
                                              subagent_type="scbot-worker")))
        self.shift = 125                                    # it never came: the slot lapsed
        self.assertIsNone(self.tool("Agent", tool_use_id="t5", subagent_type="scbot-worker"))

    def test_a_tool_call_refreshes_the_members_mark_within_minutes(self):
        self.transcript("s1", 100_000)
        self.start("k1")
        self.transcript("s1", 50_000, OPUS, agent="k1")
        seen = self.root / ".claude/scbot/state/s1/crew/k1.seen"
        self.tool("Bash", agent="k1", command="ls")
        first = os.stat(seen).st_mtime
        self.shift = 2 * MIN
        self.tool("Bash", agent="k1", command="ls")
        self.assertGreater(os.stat(seen).st_mtime, first + 100)

    def test_a_held_lock_costs_a_call_two_seconds_at_most(self):
        scbot.LOCK_WAIT = self.real_wait
        self.transcript("s1", 100_000)
        (self.root / ".claude/scbot/state/s1/crew").mkdir(parents=True)
        (self.root / ".claude/scbot/state/s1/crew/.lock").write_text("1")
        began = time.time()
        self.assertFalse(self.denied(self.tool("Agent", subagent_type="scbot-worker")))
        self.assertLess(time.time() - began, 3.5)       # the hooks' timeout is 10 s

    def test_a_silent_member_stops_counting_and_a_busy_one_does_not(self):
        self.transcript("s1", 100_000)
        for n in range(6):
            self.start("k%d" % n)
        busy = self.transcript("s1", 50_000, OPUS, agent="k0")
        self.shift = 31 * MIN
        os.utime(busy, (time.time() + self.shift, time.time() + self.shift))
        self.transcript("s1", 100_000)
        result = self.tool("Agent", subagent_type="scbot-worker", prompt="p")
        self.assertFalse(self.denied(result))
        code, out = self.cli("crew", "--session", "SCBOT-1")
        self.assertIn("k0", out)
        self.assertIn("silent", out)
        self.assertEqual(self.running(), 2)          # k0, still writing, and the new start

    def test_a_tool_call_keeps_a_member_counted(self):
        self.transcript("s1", 100_000)
        self.start("k1")
        self.transcript("s1", 50_000, OPUS, agent="k1")
        self.shift = 25 * MIN
        self.tool("Bash", agent="k1", command="x")         # refreshes its .seen marker
        self.shift = 50 * MIN
        os.utime(self.proj / "s1/subagents/agent-k1.jsonl", (0, 0))
        self.transcript("s1", 100_000)
        self.assertEqual(self.running(), 1)

    def test_session_end_and_resume_end_the_crew(self):
        self.transcript("s1", 100_000)
        for n in range(6):
            self.start("k%d" % n)
        self.hook("SessionEnd")
        self.assertEqual(self.session()["ended"][:2], "20")
        self.assertIn("ended", self.cli("status", "--all")[1])
        self.assertEqual(self.running(), 0)
        for n in range(6):
            self.start("m%d" % n)
        self.hook("SessionStart", source="resume")
        self.assertEqual(self.running(), 0)
        self.assertIsNone(self.tool("Agent", subagent_type="scbot-worker", prompt="p"))

    def test_crew_clear_frees_a_stuck_slot_but_not_a_busy_one(self):
        self.transcript("s1", 100_000)
        for n in range(6):
            self.start("k%d" % n)
        self.assertTrue(self.denied(self.tool("Agent", subagent_type="scbot-worker")))
        code, out = self.cli("crew", "clear", "--session", "SCBOT-1", "k3")
        self.assertEqual(code, 1)                           # active a moment ago
        self.assertIn("--force", out)
        self.assertEqual(self.cli("crew", "clear", "--session", "SCBOT-1", "--all")[0], 1)
        self.assertEqual(self.running(), 6)
        self.shift = 6 * MIN                                # quiet for six minutes
        self.assertEqual(self.cli("crew", "clear", "--session", "SCBOT-1", "k3")[0], 0)
        self.assertIsNone(self.tool("Agent", subagent_type="scbot-worker", prompt="p"))
        self.assertEqual(self.cli("crew", "clear", "--session", "SCBOT-1", "zz")[0], 1)
        self.shift = 0
        self.start("k9")
        self.assertEqual(self.cli("crew", "clear", "--session", "SCBOT-1", "--all")[0], 1)
        self.assertEqual(self.cli("crew", "clear", "--session", "SCBOT-1", "--all",
                                  "--force")[0], 0)
        self.assertEqual(self.running(), 0)

    def test_a_cleared_or_silent_member_that_acts_again_counts_again(self):
        self.transcript("s1", 100_000)
        for n in range(6):
            self.start("k%d" % n)
        self.cli("crew", "clear", "--session", "SCBOT-1", "k0", "--force")
        self.assertEqual(self.running(), 5)
        self.shift = 2 * MIN
        self.tool("Bash", agent="k0", command="ls")         # it was still at work
        self.assertEqual(self.running(), 6)
        self.assertTrue(self.denied(self.tool("Agent", subagent_type="scbot-worker")))
        self.shift = 40 * MIN                               # all six silent past the bound
        self.transcript("s1", 100_000)
        self.assertEqual(self.running(), 0)
        self.tool("Bash", agent="k1", command="ls")
        self.assertEqual(self.running(), 1)

    def test_a_workflow_that_fans_out_is_counted_and_blocks_the_next_start(self):
        self.transcript("s1", 100_000)
        for n in range(5):
            self.start("q%d" % n)
        self.assertIsNone(self.tool("Workflow", tool_use_id="wf1", script="x"))
        for n in range(4):
            self.start("wf%d" % n, kind="general-purpose")
        self.assertEqual(self.running(), 9)
        self.assertTrue(self.denied(self.tool("Agent", subagent_type="scbot-worker")))
        self.assertTrue(self.denied(self.tool("Workflow", script="y")))

    def test_a_held_crew_lock_lets_the_start_through_and_says_so(self):
        self.transcript("s1", 100_000)
        self.start("k1")
        lock = self.root / ".claude/scbot/state/s1/crew/.lock"
        lock.write_text("99999")
        result = self.tool("Agent", subagent_type="scbot-worker", prompt="p")
        self.assertFalse(self.denied(result))
        self.assertIn("lock file", self.told_user(result))

    def test_a_leftover_lock_cannot_lose_a_stop(self):
        self.transcript("s1", 100_000)
        self.start("L1")
        (self.root / ".claude/scbot/state/s1/crew/.lock").write_text("99999")
        began = time.time()
        self.stop("L1")
        self.assertLess(time.time() - began, 3)
        self.assertEqual(self.running(), 0)

    def test_an_old_or_future_dated_lock_is_broken(self):
        self.transcript("s1", 100_000)
        lock = self.root / ".claude/scbot/state/s1/crew/.lock"
        for offset in (-60, 600):
            self.start("k1")
            lock.write_text("1")
            os.utime(lock, (time.time() + offset, time.time() + offset))
            result = self.tool("Agent", subagent_type="scbot-worker", prompt="p")
            self.assertFalse(self.denied(result))
            self.assertNotIn("lock file", self.told_user(result), offset)
            self.assertFalse(lock.exists())

    def test_a_reader_holding_the_record_cannot_lose_a_stop(self):
        self.transcript("s1", 100_000)
        self.start("h1")
        meta = self.root / ".claude/scbot/state/s1/crew/h1.json"
        with open(meta, "rb"):                     # on Windows this blocks a rename onto it
            self.stop("h1")
        self.assertEqual(self.running(), 0)

    def test_a_mismatched_id_in_the_agent_result_makes_no_phantom(self):
        self.transcript("s1", 100_000)
        self.start("agent-x1")
        self.hook("PostToolUse", tool_name="Agent", tool_input={"description": "d"},
                  tool_response={"agentId": "task_x1"})
        self.stop("agent-x1")
        self.assertEqual(self.running(), 0)

    def test_the_result_of_an_agent_call_names_the_member(self):
        self.transcript("s1", 100_000)
        self.start("a1")
        self.hook("PostToolUse", tool_name="Agent", tool_input={"description": "wire stage 3"},
                  tool_response={"agentId": "a1", "resolvedModel": OPUS})
        self.assertIn("wire stage 3", self.cli("crew", "--session", "SCBOT-1")[1])

    def test_starts_from_real_processes_at_once_never_pass_the_cap(self):
        self.transcript("s1", 100_000)
        self.hook("SessionStart", source="startup")

        def call(n):
            payload = {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Agent",
                       "tool_use_id": "par%d" % n, "tool_input": {"subagent_type": "Explore"},
                       "transcript_path": str(self.proj / "s1.jsonl")}
            return self.run_script(["-S", str(SCRIPT), "hook"], json.dumps(payload).encode())

        with ThreadPoolExecutor(10) as pool:
            results = list(pool.map(call, range(10)))
        allowed = [r for r in results if b'"deny"' not in r[1]]
        self.assertTrue(all(r[0] == 0 for r in results))
        self.assertLessEqual(len(allowed), 6)
        self.assertGreaterEqual(len(allowed), 1)


# ============================================================================================
class Crew(Sandbox):
    def test_a_sub_agent_cannot_start_sub_agents(self):
        self.transcript("s1", 100_000)
        self.transcript("s1", 50_000, OPUS, agent="a1")
        for name in ("Agent", "Task", "Workflow"):
            self.assertTrue(self.denied(self.tool(name, agent="a1", subagent_type="Explore")),
                            name)
        self.start("a2")
        self.stop("a2")
        self.assertTrue(self.denied(self.tool("SendMessage", agent="a1", to="a2", message="x")))
        self.assertFalse(self.denied(self.tool("SendMessage", agent="a1", to="main",
                                               message="a question")))

    def test_notices_at_60_and_75_exactly_then_the_cap_at_80_exactly(self):
        self.transcript("s1", 100_000)
        self.transcript("s1", 599_999, OPUS, agent="a1")
        self.assertIsNone(self.tool("Read", agent="a1", file_path="x"))
        self.transcript("s1", 600_000, OPUS, agent="a1")
        self.assertIn("60%", self.context(self.tool("Read", agent="a1", file_path="x")))
        self.assertIsNone(self.tool("Read", agent="a1", file_path="x"))
        self.transcript("s1", 749_999, OPUS, agent="a1")
        self.assertIsNone(self.tool("Read", agent="a1", file_path="x"))
        self.transcript("s1", 750_000, OPUS, agent="a1")
        wrap = self.tool("Grep", agent="a1", pattern="x")
        self.assertFalse(self.denied(wrap))
        self.assertIn("clean boundary", self.context(wrap))
        self.transcript("s1", 799_999, OPUS, agent="a1")
        self.assertFalse(self.denied(self.tool("Read", agent="a1", file_path="x")))
        self.transcript("s1", 800_000, OPUS, agent="a1")
        self.assertTrue(self.denied(self.tool("Read", agent="a1", file_path="x")))

    def test_the_wrap_and_cap_notices_come_once_per_percent(self):
        self.transcript("s1", 100_000)
        self.transcript("s1", 760_000, OPUS, agent="a1")
        self.assertIn("76%", self.context(self.tool("Bash", agent="a1", command="x")))
        self.assertIsNone(self.tool("Bash", agent="a1", command="x"))
        self.transcript("s1", 770_000, OPUS, agent="a1")
        self.assertIn("77%", self.context(self.tool("Bash", agent="a1", command="x")))
        self.transcript("s1", 810_000, OPUS, agent="a1")
        self.assertIn("81%", self.context(self.tool("Bash", agent="a1", command="x")))
        self.assertIsNone(self.tool("Bash", agent="a1", command="x"))
        self.transcript("s1", 820_000, OPUS, agent="a1")
        self.assertIn("82%", self.context(self.tool("Bash", agent="a1", command="x")))

    def test_the_cap_is_measured_on_the_sub_agents_own_transcript(self):
        self.transcript("s1", 950_000)
        self.transcript("s1", 100_000, OPUS, agent="a1")
        self.assertIsNone(self.tool("Read", agent="a1", file_path="x"))
        self.transcript("s1", 100_000)
        self.transcript("s1", 170_000, "claude-haiku-4-5", agent="a2")
        self.assertTrue(self.denied(self.tool("Read", agent="a2", file_path="x")))

    def test_start_notice_and_resume_counts_as_running_again(self):
        self.transcript("s1", 100_000)
        text = self.context(self.start("agent-a1", kind="scbot-architect"))
        for part in ("crew member of session SCBOT-1", "cannot start sub-agents", "80%",
                     ".claude/scbot/notes/agent-a1/", "SendMessage", "6,000 characters"):
            self.assertIn(part, text)
        self.assertNotIn("characters", self.context(self.start("e1", kind="Explore")))
        self.stop("e1", kind="Explore")
        self.stop("a1", kind="scbot-architect")
        code, out = self.cli("status", "--session", "SCBOT-1")
        self.assertIn("running 0 of 6", out)
        self.start("a1", kind="scbot-architect")
        self.assertIn("running 1 of 6", self.cli("status", "--session", "SCBOT-1")[1])

    def test_the_architect_does_not_edit_the_implementation(self):
        self.transcript("s1", 100_000)
        root = self.root.as_posix()
        blocked = ["tools/gamedata.py", "MOZA.xml", "dashboard/scdash/service.py",
                   "dashboard/web/app.js", ".claude/worktrees/agent-x/dashboard/web/style.css",
                   "cards/MOZA_MTQ_ref.svg", "reference/SC_KEYBINDS_DATABASE_v4.10.md",
                   "Tools/GameData.py"]
        allowed = ["dashboard/PLAN.md", "dashboard/design/avionics/index.html",
                   "dashboard/data/design/rig/NOTES.md", ".claude/scbot/notes/T001/PLAN.md",
                   "prompts/SCBOT-WORKER.md"]
        for path in blocked:
            result = self.tool("Write", agent="a1", agent_type="scbot-architect",
                               file_path="%s/%s" % (root, path))
            self.assertTrue(self.denied(result), path)
        relative = self.tool("Edit", agent="a1", agent_type="scbot-architect",
                             file_path="tools\\scbot.py")
        self.assertTrue(self.denied(relative))
        for path in allowed:
            self.assertFalse(self.denied(self.tool("Edit", agent="a1",
                             agent_type="scbot-architect", file_path="%s/%s" % (root, path))))
        self.assertFalse(self.denied(self.tool("Write", agent="a2", agent_type="scbot-worker",
                                               file_path=root + "/tools/gamedata.py")))


# ============================================================================================
class AllowLists(Sandbox):
    """Finding 8: every entry of OPEN_AT is open in its state, and what is not listed is shut."""

    def setUp(self):
        super().setUp()
        self.memory = str(self.home / ".claude/projects/c--repo/memory/MEMORY.md")
        self.note = str(self.root / ".claude/scbot/notes/agent-a1/HANDOFF.md")

    def walk(self, state, call):
        for name, scope in scbot.OPEN_AT[state].items():
            if scope == "any":
                self.assertFalse(self.denied(call(name, file_path=str(self.root / "x.py"))), name)
            else:
                self.assertFalse(self.denied(call(name, file_path=self.note)), name)
                self.assertTrue(self.denied(call(name, file_path=str(self.root / "unread.py"))),
                                name)

    def test_a_sub_agent_at_its_cap(self):
        self.transcript("s1", 100_000)
        self.transcript("s1", 810_000, OPUS, agent="a1")

        def call(name, **ti):
            return self.tool(name, agent="a1", message="m", **ti)
        self.walk("crew-cap", call)
        for name in ("PowerShell", "ToolSearch", "SendMessage", "TaskStop", "SubagentHandback"):
            self.assertIn(name, scbot.OPEN_AT["crew-cap"])
        for name in ("Read", "Grep", "Glob", "WebFetch", "WebSearch", "Skill", "LSP",
                     "Artifact", "mcp__a__b", "AskUserQuestion", "SomeNewTool"):
            self.assertTrue(self.denied(call(name, file_path=str(self.root / "unread.py"))),
                            name)

    def test_at_its_cap_a_sub_agent_reads_only_its_own_files(self):
        self.transcript("s1", 100_000)
        self.start("a1")
        self.transcript("s1", 500_000, OPUS, agent="a1")
        mine = str(self.root / ".claude/scbot/fix-x/NOTES.md")     # where its brief put them
        self.tool("Write", agent="a1", file_path=mine, content="n")
        self.tool("Edit", agent="a1", file_path="docs\\draft.md")    # relative, to cwd
        self.transcript("s1", 810_000, OPUS, agent="a1")
        scbase = self.root / ".claude/scbot"
        for path in (mine, self.note, str(self.root / "docs/draft.md"),
                     str(scbase / "reports/SCBOT-1/a1.md"), str(scbase / "reports/SCBOT-1/a1.full.md")):
            self.assertFalse(self.denied(self.tool("Read", agent="a1", file_path=path)), path)
        for path in (str(scbase / "notes/agent-b2/HANDOFF.md"), str(scbase / "reports/SCBOT-1/b2.md"),
                     str(scbase / "state/s1/session.json"), str(scbase / "fix-x/OTHER.md"),
                     str(self.root / ".claude/settings.json"), self.memory):
            self.assertTrue(self.denied(self.tool("Read", agent="a1", file_path=path)), path)

    def test_a_lead_in_its_reserve_reads_only_notes_and_memory(self):
        self.transcript("s1", 970_000)
        for path in (str(self.root / ".claude/settings.json"),
                     str(self.root / ".claude/agents/scbot-worker.md"),
                     str(Path(self.tmp.name) / "elsewhere/memory/x.md"),
                     str(self.home / ".claude/projects/memory.md")):
            self.assertTrue(self.denied(self.tool("Read", file_path=path)), path)

    def test_a_lead_in_its_reserve(self):
        self.transcript("s1", 970_000)

        def call(name, **ti):
            return self.tool(name, to="main", message="m", **ti)
        self.walk("lead-reserve", call)
        self.assertFalse(self.denied(call("Read", file_path=self.memory)))
        self.assertFalse(self.denied(call("Read", file_path=str(
            self.root / ".claude/scbot/reports/SCBOT-1/a1.md"))))
        for name in ("Grep", "Glob", "WebFetch", "Skill", "mcp__claude_ai_Claude_Docs__update",
                     "Agent", "Workflow", "SomeNewTool"):
            self.assertTrue(self.denied(call(name, file_path=str(self.root / "x.py"))), name)


# ============================================================================================
class Reports(Sandbox):
    """Finding 10."""

    def test_a_crew_report_is_held_to_6000_and_saved(self):
        self.transcript("s1", 100_000)
        self.start("a1")
        self.assertTrue(self.denied(self.tool("SubagentHandback", agent="a1", message="z" * 6001)))
        reports = self.root / ".claude/scbot/reports/SCBOT-1"
        self.assertEqual(len((reports / "a1.full.md").read_text()), 6001)
        self.assertIsNone(self.tool("SubagentHandback", agent="a1", message="y" * 6000))
        self.assertEqual(len((reports / "a1.md").read_text()), 6000)
        self.assertIsNone(self.stop("a1", message="closing words"))
        self.assertEqual(len((reports / "a1.md").read_text()), 6000)

    def test_other_agent_types_have_no_length_rule(self):
        self.transcript("s1", 100_000)
        self.start("e1", kind="Explore")
        self.assertIsNone(self.tool("SubagentHandback", agent="e1", agent_type="Explore",
                                    message="w" * 9000))
        self.start("e2", kind="web-fetch")
        self.assertIsNone(self.stop("e2", kind="web-fetch", message="w" * 9000))

    def test_a_send_back_can_never_loop(self):
        self.transcript("s1", 100_000)
        self.start("a1")
        back = self.stop("a1", message="w" * 7000, stop_hook_active=False)
        self.assertEqual(back["decision"], "block")
        self.assertIsNone(self.stop("a1", message="w" * 7000, stop_hook_active=True))
        self.start("a2")
        self.assertEqual(self.stop("a2", message="v" * 7000)["decision"], "block")
        self.assertEqual(self.stop("a2", message="v" * 7000)["decision"], "block")
        self.assertIsNone(self.stop("a2", message="v" * 7000))     # third time: taken
        self.start("a3")
        for _ in range(2):
            self.assertTrue(self.denied(self.tool("SubagentHandback", agent="a3",
                                                  message="u" * 7000)))
        self.assertIsNone(self.tool("SubagentHandback", agent="a3", message="u" * 7000))
        self.assertIsNone(self.hook("SubagentStop", agent_id="zz", agent_type=""))

    def test_a_plain_final_message_is_saved(self):
        self.transcript("s1", 100_000)
        self.start("a1")
        self.stop("a1", message="summary")
        self.assertEqual((self.root / ".claude/scbot/reports/SCBOT-1/a1.md").read_text(),
                         "summary")


# ============================================================================================
class Sessions(Sandbox):
    def test_labels_and_closing(self):
        self.transcript("s1", 100_000)
        self.transcript("s2", 100_000)
        one = self.context(self.hook("SessionStart", "s1", source="startup", model=OPUS))
        self.assertIn("this top-level session is SCBOT-1", one)
        self.assertIn("No other live SCBOT session", one)
        two = self.context(self.hook("SessionStart", "s2", source="startup", model=FABLE))
        self.assertIn("SCBOT-2", two)
        self.assertIn("SCBOT-1", two)
        self.start("a1", "s2")
        self.assertEqual(self.cli("close", "--session", "SCBOT-2")[0], 1)
        self.stop("a1", "s2")
        code, out = self.cli("close", "--session", "SCBOT-2", "--note", "stage 3 wired; see PLAN")
        self.assertEqual(code, 0, out)
        shut = self.hook("UserPromptSubmit", "s2", prompt="hello?")
        self.assertEqual(shut["decision"], "block")
        self.assertIn("stage 3 wired; see PLAN", shut["reason"])
        self.transcript("s3", 100_000)
        self.assertIn("is SCBOT-2", self.context(self.hook("SessionStart", "s3",
                                                           source="startup")))
        self.assertEqual(self.cli("reopen", "--session", "s2")[0], 0)
        self.assertIsNone(self.hook("UserPromptSubmit", "s2", prompt="hello?"))

    def test_close_does_not_offer_force(self):
        self.transcript("s1", 100_000)
        self.start("a1")
        code, out = self.cli("close", "--session", "SCBOT-1", "--note", "n")
        self.assertEqual(code, 1)
        self.assertNotIn("--force", out)
        self.assertNotIn("crew clear", out)
        self.assertIn("crew --session SCBOT-1", out)

    def test_a_lead_is_never_fenced_whatever_prompt_it_names(self):
        self.transcript("c", 100_000, OPUS)
        self.hook("UserPromptSubmit", "c",
                  prompt="@SCBOT.md then fix a typo in prompts/SCBOT-ARCHITECT.md")
        for f in ("MOZA.xml", "tools/gamedata.py", "dashboard/scdash/server.py"):
            self.assertFalse(self.denied(self.tool("Write", "c",
                                                   file_path=self.root.as_posix() + "/" + f)))
        self.assertEqual(self.session("c")["prompt_file"], "SCBOT.md")
        self.transcript("d", 100_000, OPUS)
        said = self.context(self.hook("UserPromptSubmit", "d",
                                      prompt="@prompts/SCBOT-ARCHITECT.md design the page"))
        self.assertIn("written for claude-fable-5-2", said)
        self.assertFalse(self.denied(self.tool("Write", "d",
                                               file_path=self.root.as_posix() + "/tools/x.py")))
        self.transcript("e", 100_000, OPUS)
        self.hook("UserPromptSubmit", "e", prompt="hi")
        self.hook("UserPromptSubmit", "e", prompt="read prompts/SCBOT-WORKER.md please")
        self.assertEqual(self.session("e")["prompt_file"], "")

    def test_a_session_is_live_for_a_day_and_a_call_keeps_it_so(self):
        self.transcript("s1", 100_000)
        self.hook("SessionStart", "s1", source="startup")
        self.shift = 2 * HOUR
        self.transcript("s2", 100_000)
        self.assertIn("is SCBOT-2", self.context(self.hook("SessionStart", "s2",
                                                           source="startup")))
        self.shift = 23.5 * HOUR
        self.tool("Read", "s1", file_path="x")              # s1 is still at work
        self.shift = 26.5 * HOUR                            # s2 idle 24.5 h, s1 idle 3 h
        self.transcript("s3", 100_000)
        text = self.context(self.hook("SessionStart", "s3", source="startup"))
        self.assertIn("is SCBOT-2", text)                   # s2 went stale, s1 did not
        self.assertIn("SCBOT-1", text)

    def test_labels_stay_unique_when_an_idle_session_comes_back(self):
        self.transcript("old", 100_000)
        self.hook("SessionStart", "old", source="startup")
        self.edit_session("old", seen_t=time.time() - 25 * HOUR)
        os.utime(self.session_file("old").parent, (time.time() - 25 * HOUR,) * 2)
        self.transcript("new", 100_000)
        self.assertIn("is SCBOT-1", self.context(self.hook("SessionStart", "new",
                                                           source="startup")))
        back = self.context(self.hook("UserPromptSubmit", "old", prompt="back again"))
        self.assertIn("now SCBOT-2", back)
        labels = [self.session(s)["label"] for s in ("old", "new")]
        self.assertEqual(sorted(labels), ["SCBOT-1", "SCBOT-2"])
        self.assertEqual(self.cli("close", "--session", "SCBOT-1", "--note", "n")[0], 0)
        self.assertTrue(self.session("new").get("closed"))
        self.assertFalse(self.session("old").get("closed"))

    def test_close_refuses_a_label_two_live_sessions_hold(self):
        for sid in ("x1", "x2"):
            self.transcript(sid, 100_000)
            self.hook("SessionStart", sid, source="startup")
        self.edit_session("x2", label="SCBOT-1")
        code, out = self.cli("close", "--session", "SCBOT-1", "--note", "n")
        self.assertEqual(code, 1)
        self.assertIn("held by 2 live sessions", out)
        self.assertEqual(self.cli("close", "--session", "x2", "--note", "n")[0], 0)

    def test_a_held_state_lock_still_gives_a_label_and_says_so(self):
        lock = self.root / ".claude/scbot/state/.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("1")
        self.transcript("s1", 100_000)
        result = self.hook("SessionStart", "s1", source="startup")
        self.assertIn("SCBOT-1", self.context(result))
        self.assertIn("lock file", self.told_user(result))

    def test_automatic_compaction_is_blocked_and_manual_is_left_alone(self):
        self.assertEqual(self.hook("PreCompact", trigger="auto")["decision"], "block")
        self.assertIsNone(self.hook("PreCompact", trigger="manual"))


# ============================================================================================
class Meter(Sandbox):
    """Finding 12."""

    def test_meter_shows_the_session_and_its_sub_agents(self):
        folder = self.home / ".claude/projects" / scbot.re.sub(r"[^A-Za-z0-9]", "-",
                                                               str(self.root)).lower()
        folder.mkdir(parents=True)
        self.proj = folder
        self.transcript("s1", 530_000)
        self.transcript("s1", 610_000, OPUS, agent="b1")
        self.start("b1")
        code, out = self.cli("meter", "--root", str(self.root), "--home", str(self.home))
        self.assertEqual(code, 0, out)
        self.assertIn("session s1 (SCBOT-1): 53%", out)
        self.assertIn("b1", out)
        self.assertIn("61%", out)
        self.assertIn("running", out)
        code, out = self.cli("meter", "--session", "SCBOT-1")
        self.assertIn("53%", out)


# ============================================================================================
class Queue(Sandbox):
    def sessions(self):
        for sid in ("s1", "s2"):
            self.transcript(sid, 100_000)
            self.hook("SessionStart", sid, source="startup")

    def test_claims_do_not_collide_and_a_close_hands_over(self):
        self.sessions()
        self.assertIn("T001", self.cli("queue", "add", "--title", "Wire stage 3", "--role",
                                       "worker", "--files", "dashboard/scdash/*")[1])
        self.cli("queue", "add", "--title", "Fix the server", "--files",
                 "dashboard/scdash/server.py")
        self.cli("queue", "add", "--title", "Review it", "--after", "T001")
        self.assertEqual(self.cli("queue", "claim", "T001", "--session", "SCBOT-1")[0], 0)
        code, out = self.cli("queue", "claim", "T001", "--session", "SCBOT-2")
        self.assertEqual(code, 1)
        self.assertIn("claimed by SCBOT-1", out)
        self.assertIn("--take", out)
        code, out = self.cli("queue", "claim", "T002", "--session", "SCBOT-2")
        self.assertEqual(code, 1)
        self.assertIn("already holds", out)
        self.assertEqual(self.cli("queue", "claim", "T003", "--session", "SCBOT-2")[0], 1)
        self.cli("close", "--session", "SCBOT-1", "--note", "notes/T001/HANDOFF.md")
        self.assertIn("T001  handed-over", self.cli("queue", "list")[1])
        self.assertEqual(self.cli("queue", "claim", "T001", "--session", "SCBOT-2")[0], 0)
        self.cli("queue", "done", "T001", "--session", "SCBOT-2", "--commit", "abc123")
        self.assertEqual(self.cli("queue", "claim", "T003", "--session", "SCBOT-2")[0], 0)
        self.assertNotIn("T001", self.cli("queue", "list")[1])
        self.assertIn("handed over", self.cli("queue", "show", "T001")[1])

    def test_a_pending_holder_keeps_its_claim_and_take_takes_it(self):
        self.sessions()
        self.cli("queue", "add", "--title", "t")
        self.cli("queue", "claim", "T001", "--session", "SCBOT-1")
        self.transcript("s1", 950_000)
        self.tool("Read", "s1", file_path="x")                 # s1 is now pending closing
        self.assertEqual(self.cli("queue", "claim", "T001", "--session", "SCBOT-2")[0], 1)
        self.assertEqual(self.cli("queue", "claim", "T001", "--session", "SCBOT-2",
                                  "--take")[0], 0)

    def test_only_the_holder_marks_a_claimed_task_done(self):
        self.sessions()
        self.cli("queue", "add", "--title", "t")
        self.cli("queue", "claim", "T001", "--session", "SCBOT-1")
        for verb in ("done", "drop", "handover"):
            code, out = self.cli("queue", verb, "T001", "--session", "SCBOT-2")
            self.assertEqual(code, 1, verb)
            self.assertIn("--take", out)
        self.assertEqual(self.cli("queue", "done", "T001")[0], 1)
        self.assertEqual(self.cli("queue", "done", "T001", "--session", "SCBOT-1")[0], 0)
        self.cli("queue", "add", "--title", "unclaimed")
        self.assertEqual(self.cli("queue", "done", "T002")[0], 0)          # before the install

    def test_ids_cannot_leave_the_folder(self):
        self.sessions()
        settings = self.root / ".claude/settings.json"
        settings.write_text('{"permissions": {}}')
        for tid in ("../../settings", "../state/s1/session", "T1", "t001", "T001/../x"):
            self.assertEqual(self.cli("queue", "done", tid, "--session", "SCBOT-1")[0], 1, tid)
            self.assertEqual(self.cli("queue", "show", tid)[0], 1, tid)
        self.assertEqual(settings.read_text(), '{"permissions": {}}')
        self.assertEqual(self.cli("queue", "add", "--title", "x", "--after", "../x")[0], 1)

    def test_overlaps_are_found_after_normalizing(self):
        pairs = [("dashboard/x.py", "./dashboard/x.py"), ("dashboard", "dashboard/scdash/a.py"),
                 ("Dashboard/Scdash/*", "dashboard/scdash/a.py"),
                 ("dashboard\\scdash\\a.py", "dashboard/scdash/a.py"),
                 ("dashboard/scdash/**", "dashboard/scdash/a/b.py"),
                 ("tools/*.py", "tools/sub/x.py"), ("memory/x.md/", "memory/x.md")]
        for a, b in pairs:
            self.assertTrue(scbot.overlap([a], [b]), (a, b))
        self.assertFalse(scbot.overlap(["dashboard/a.py"], ["dashboard/b.py"]))
        self.assertFalse(scbot.overlap(["tools/*.py"], ["tools/*.md"]))


# ============================================================================================
class Install(Sandbox):
    """Finding 9."""

    def setUp(self):
        super().setUp()
        (self.home / ".claude").mkdir()
        (self.root / ".claude").mkdir()
        self.where = ["--root", str(self.root), "--home", str(self.home)]
        self.project = self.root / ".claude/settings.json"
        self.user = self.home / ".claude/settings.json"

    def test_install_merges_keeps_what_was_there_and_uninstall_puts_it_back(self):
        mine = {"model": "opus", "env": {"KEEP": "1", "DISABLE_AUTO_COMPACT": "0"},
                "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
                    {"type": "command", "command": "python tools/scbot.py status"}]}]}}
        self.user.write_text(json.dumps({"model": "opus"}))
        self.project.write_text(json.dumps(mine))
        before_user, before_project = self.user.read_bytes(), self.project.read_bytes()
        self.assertEqual(self.cli("check", *self.where)[0], 1)
        self.assertEqual(self.cli("install", "--scope", "all", *self.where)[0], 0)
        backups = sorted(self.project.parent.glob("settings.json.scbot-backup-*"))
        self.assertTrue(backups)
        self.assertEqual(backups[0].read_bytes(), before_project)
        self.assertEqual(self.cli("install", "--scope", "all", *self.where)[0], 0)
        project = json.loads(self.project.read_text())
        self.assertEqual(project["model"], "opus")
        self.assertIs(project["autoCompactEnabled"], False)
        self.assertEqual(project["env"]["KEEP"], "1")
        self.assertEqual(project["env"]["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"], "6")
        self.assertEqual(len(project["hooks"]["PreToolUse"]), 2)
        self.assertNotIn("_about", project)
        hook = project["hooks"]["PreToolUse"][1]["hooks"][0]
        self.assertTrue(Path(hook["command"]).is_absolute())
        self.assertTrue(Path(hook["args"][-1]).is_absolute())
        self.assertEqual(hook["args"][:4], ["-I", "-S", "-c", scbot.LAUNCHER])
        user = json.loads(self.user.read_text())
        self.assertEqual((user["autoCompactEnabled"], user["idleCompaction"]), (False, False))
        self.assertNotIn("hooks", user)
        self.assertTrue((self.root / ".claude/agents/scbot-worker.md").exists())
        code, out = self.cli("check", *self.where)
        self.assertEqual(code, 0, out)
        self.assertIn("SCBOT_FORK_MAX", out)
        self.assertEqual(self.cli("uninstall", *self.where)[0], 0)
        self.assertEqual(self.project.read_bytes(), before_project)
        self.assertEqual(self.user.read_bytes(), before_user)
        self.assertFalse((self.root / ".claude/agents/scbot-worker.md").exists())
        self.assertFalse((self.root / ".claude/scbot/bin/scbot.py").exists())

    def test_a_file_that_is_not_strict_json_is_refused_untouched(self):
        for text in ('{\n  // my notes\n  "model": "opus"\n}\n', '[]', '{"hooks": []}',
                     '{"a": 1,}'):
            self.project.write_text(text, encoding="utf-8")
            code, out = self.cli("install", "--scope", "project", *self.where)
            self.assertEqual(code, 1, text)
            self.assertIn("refused", out)
            self.assertEqual(self.project.read_text(encoding="utf-8"), text)
            self.assertFalse((self.root / ".claude/scbot/bin/scbot.py").exists())
            code, out = self.cli("uninstall", *self.where)
            self.assertEqual(self.project.read_text(encoding="utf-8"), text)

    def test_formatting_and_the_users_own_hooks_survive_and_an_untouched_file_is_left(self):
        original = ('﻿{\r\n    "model": "opus",\r\n    "statusLine": {"type": "command", '
                    '"command": "échø"},\r\n    "env": {},\r\n    "hooks": {"Stop": '
                    '[{"hooks": [{"type": "command", "command": "python tools/scbot.py status"}]}'
                    ']}\r\n}\r\n').encode("utf-8")
        user = b'{\r\n    "theme": "dark",\r\n    "hooks": {}\r\n}\r\n'
        self.project.write_bytes(original)
        self.user.write_bytes(user)
        self.cli("install", "--scope", "project", *self.where)
        self.cli("install", "--scope", "project", *self.where)
        merged = json.loads(self.project.read_text(encoding="utf-8-sig"))
        self.assertEqual(len(merged["hooks"]["PreToolUse"]), 1)
        self.assertIn("Stop", merged["hooks"])
        self.assertIn(b"\r\n    \"model\"", self.project.read_bytes())
        self.assertTrue(self.project.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.cli("uninstall", *self.where)[0], 0)
        self.assertEqual(self.project.read_bytes(), original)
        self.assertEqual(self.user.read_bytes(), user)
        self.assertFalse(list(self.user.parent.glob("*scbot*")))

    def test_an_edit_after_the_install_is_kept_and_only_ours_comes_out(self):
        self.project.write_text(json.dumps({"autoCompactEnabled": True, "env": {"A": "1"}}))
        self.cli("install", "--scope", "project", *self.where)
        now = json.loads(self.project.read_text())
        now["permissions"] = {"allow": ["Bash(git status)"]}
        now["hooks"]["Stop"] = [{"hooks": [{"type": "command", "command": "echo mine"}]}]
        self.project.write_text(json.dumps(now, indent=2))
        self.assertEqual(self.cli("uninstall", "--scope", "project", *self.where)[0], 0)
        after = json.loads(self.project.read_text())
        self.assertEqual(after["permissions"], {"allow": ["Bash(git status)"]})
        self.assertIs(after["autoCompactEnabled"], True)
        self.assertNotIn("idleCompaction", after)
        self.assertEqual(after["env"], {"A": "1"})
        self.assertEqual(list(after["hooks"]), ["Stop"])

    def test_an_interrupted_install_is_undone_by_uninstall(self):
        original = json.dumps({"model": "opus"}).encode()
        self.project.write_bytes(original)
        self.user.mkdir()                                     # a folder where the file goes
        code, out = self.cli("install", "--scope", "all", *self.where)
        self.assertEqual(code, 1)
        self.assertEqual(self.project.read_bytes(), original)   # checked before any write
        self.user.rmdir()
        self.user.write_text("{}")
        real = scbot.write_bytes

        def fail_on_user(path, data):
            if Path(path) == self.user:
                return False
            return real(path, data)
        scbot.write_bytes = fail_on_user
        try:
            code, out = self.cli("install", "--scope", "all", *self.where)
        finally:
            scbot.write_bytes = real
        self.assertEqual(code, 1)
        self.assertIn("autoCompactEnabled", self.project.read_text())
        self.assertEqual(self.cli("uninstall", *self.where)[0], 0)
        self.assertEqual(self.project.read_bytes(), original)
        self.assertEqual(self.user.read_text(), "{}")

    def test_check_proves_the_interpreter_runs(self):
        self.cli("install", "--scope", "all", *self.where)
        self.assertEqual(self.cli("check", *self.where)[0], 0)
        settings = json.loads(self.project.read_text())
        for groups in settings["hooks"].values():
            for group in groups:
                for hook in group["hooks"]:
                    hook["command"] = str(self.root / "no-python.exe")
        self.project.write_text(json.dumps(settings))
        code, out = self.cli("check", *self.where)
        self.assertEqual(code, 1)
        self.assertIn("FAIL  the hooks' interpreter runs", out)
        self.assertEqual(self.cli("install", "--scope", "project", "--python",
                                  str(self.root / "no-python.exe"), *self.where)[0], 1)

    def old_install(self, record=True):
        """What the previous version of the script left: its hook form, its install record."""
        old = {"type": "command", "command": "python",
               "args": ["-S", "${CLAUDE_PROJECT_DIR}/.claude/scbot/bin/scbot.py", "hook"],
               "timeout": 10}
        mine = {"type": "command", "command": "python tools/scbot.py status"}
        settings = {"model": "opus", "autoCompactEnabled": False, "env": {
            "DISABLE_AUTO_COMPACT": "1", "KEEP": "1"}, "hooks": {
            "PreToolUse": [{"matcher": "*", "hooks": [old]}],
            "SessionEnd": [{"hooks": [old]}], "Stop": [{"hooks": [mine]}]}}
        self.project.write_text(json.dumps(settings, indent=2))
        (self.root / ".claude/scbot/bin").mkdir(parents=True, exist_ok=True)
        (self.root / ".claude/scbot/bin/scbot.py").write_text("# the old copy\n")
        if record:
            (self.root / ".claude/scbot/installed.json").write_text(json.dumps({
                str(self.project): {"keys": {"autoCompactEnabled": None},
                                    "env": {"DISABLE_AUTO_COMPACT": None}}}))

    def hooks_left(self):
        settings = json.loads(self.project.read_text())
        return [h for groups in settings.get("hooks", {}).values() for g in groups
                for h in g["hooks"]]

    def test_an_install_by_the_previous_version_is_replaced(self):
        for record in (True, False):
            self.old_install(record)
            code, out = self.cli("install", "--scope", "project", *self.where)
            self.assertEqual(code, 0, out)
            left = self.hooks_left()
            self.assertFalse(any("${CLAUDE_PROJECT_DIR}" in json.dumps(h) for h in left))
            self.assertEqual(sum(1 for h in left if scbot.HOOK_MARK in json.dumps(h)), 8)
            self.assertIn({"type": "command", "command": "python tools/scbot.py status"}, left)
            self.assertEqual(self.cli("uninstall", *self.where)[0], 0)
            after = json.loads(self.project.read_text())
            self.assertEqual(list(after["hooks"]), ["Stop"])
            self.assertEqual(after["env"]["KEEP"], "1")
            (self.root / ".claude/scbot/installed.json").unlink(missing_ok=True)

    def test_uninstall_removes_the_previous_versions_install(self):
        self.old_install()
        self.assertEqual(self.cli("uninstall", *self.where)[0], 0)
        after = json.loads(self.project.read_text())
        self.assertEqual(list(after["hooks"]), ["Stop"])
        self.assertNotIn("autoCompactEnabled", after)
        self.assertEqual(after["env"], {"KEEP": "1"})
        self.assertFalse((self.root / ".claude/scbot/bin/scbot.py").exists())

    def test_install_prints_any_path_on_any_console(self):
        root = Path(self.tmp.name) / "repo 漢 é"
        (root / ".claude").mkdir(parents=True)
        env = dict(self.env, SCBOT_ROOT=str(root), PYTHONIOENCODING="ascii")
        run = subprocess.run([sys.executable, str(SCRIPT), "install", "--scope", "project",
                              "--root", str(root), "--home", str(self.home)],
                             capture_output=True, env=env, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(scbot.HOOK_MARK, (root / ".claude/settings.json").read_text("utf-8"))

    def test_the_hooks_keep_the_fragments_timeout(self):
        self.cli("install", "--scope", "project", *self.where)
        fragment = json.loads((SCRIPT.parents[1] / "prompts/settings/"
                               "scbot.project-settings.json").read_text(encoding="utf-8"))
        for event, groups in json.loads(self.project.read_text())["hooks"].items():
            want = fragment["hooks"][event][0]["hooks"][0]["timeout"]
            self.assertEqual(groups[0]["hooks"][0]["timeout"], want, event)
            self.assertLessEqual(want, 10)

    def test_an_interpreter_that_is_not_python_3_is_refused(self):
        if WINDOWS:
            fake = self.root / "fake-python.cmd"
            fake.write_text("@echo off\r\nexit /b 0\r\n")
        else:
            fake = self.root / "fake-python"
            fake.write_text("#!/bin/sh\nexit 0\n")
            fake.chmod(0o755)
        code, out = self.cli("install", "--scope", "project", "--python", str(fake),
                             *self.where)
        self.assertEqual(code, 1)
        self.assertIn("does not run as Python 3", out)
        self.cli("install", "--scope", "project", *self.where)
        settings = json.loads(self.project.read_text())
        settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = str(fake)
        self.project.write_text(json.dumps(settings))
        code, out = self.cli("check", *self.where)
        self.assertIn("FAIL  the hooks' interpreter runs: %s" % fake, out)

    def test_check_runs_the_hook_command_as_written(self):
        self.cli("install", "--scope", "project", *self.where)
        settings = json.loads(self.project.read_text())
        hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
        hook["args"] = ["-I", "-S", "-c", "M='%s';import sys;sys.exit(3)" % scbot.HOOK_MARK,
                        hook["args"][-1]]
        self.project.write_text(json.dumps(settings))
        code, out = self.cli("check", "--root", str(self.root), "--home", str(self.home))
        self.assertEqual(code, 1)
        self.assertIn("PASS  the hooks' interpreter runs", out)
        self.assertIn("FAIL  the hook command, as written in the settings, runs and exits 0", out)

    def test_check_reports_compaction_turned_back_on(self):
        self.cli("install", "--scope", "all", *self.where)
        (self.root / ".claude/settings.local.json").write_text('{"autoCompactEnabled": true}')
        code, out = self.cli("check", *self.where)
        self.assertEqual(code, 1)
        self.assertIn("project local settings turn autoCompactEnabled back on", out)

    def test_sessions_past_their_line_are_listed_before_installing(self):
        folder = scbot.project_folder(self.root, self.home)
        folder.mkdir(parents=True)
        self.proj = folder
        self.transcript("hot", 915_000)
        self.transcript("hot", 820_000, OPUS, agent="q1")
        self.transcript("cool", 300_000)
        code, out = self.cli("install", "--scope", "project", *self.where)
        self.assertEqual(code, 1)
        self.assertIn("session hot at 92%", out)
        self.assertIn("agent-q1", out)
        self.assertNotIn("cool", out)
        self.assertFalse(self.project.exists())
        self.assertEqual(self.cli("install", "--scope", "project", "--yes", *self.where)[0], 0)

    def test_an_installed_hook_runs_and_a_removed_script_blocks_nothing(self):
        self.cli("install", "--scope", "project", *self.where)
        hook = json.loads(self.project.read_text())["hooks"]["PreToolUse"][0]["hooks"][0]
        self.transcript("s1", 910_000)
        payload = json.dumps({"hook_event_name": "PreToolUse", "session_id": "s1",
                              "tool_name": "Agent", "tool_input": {},
                              "transcript_path": str(self.proj / "s1.jsonl")}).encode()
        run = subprocess.run([hook["command"]] + hook["args"], input=payload,
                             capture_output=True, env=self.env)
        self.assertEqual(run.returncode, 0)
        self.assertIn(b'"deny"', run.stdout)
        (self.root / ".claude/scbot/bin/scbot.py").unlink()
        run = subprocess.run([hook["command"]] + hook["args"], input=payload,
                             capture_output=True, env=self.env)
        self.assertEqual((run.returncode, run.stdout), (0, b""))


if __name__ == "__main__":
    unittest.main(verbosity=1)
