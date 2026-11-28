#!/usr/bin/env python3
"""SCBOT crew guard, work queue and installer.

One file, standard library only. It does three jobs:

  hook      Run by Claude Code hooks (JSON on stdin). It measures how full a session's or a
            sub-agent's context is from the transcript, tells the agent at set lines, refuses
            what the user's rules refuse (new sub-agents past the session's line, a seventh
            running sub-agent, a sub-agent starting sub-agents, reading past a sub-agent's cap,
            an over-long final report from a crew role, automatic compaction), and saves every
            sub-agent's final report to a file.
  queue     A small board of task files that several sessions can claim from without colliding.
  install   Copies this script, the sub-agent definitions and the settings into place
            (uninstall, check, status, crew and meter go with it).

The design and the reasons are in prompts/SCBOT-README.md. Nothing here runs until `install`
has been run: the hooks call the installed copy under .claude/scbot/bin/, not this file.

Two properties hold everywhere, and the tests check both:

- The guard never stops an agent. It only refuses a new tool call, with the reason.
- It fails open, and says so. When it cannot do its job (state it cannot write, a transcript it
  cannot find or read, a model it has no window for, a fault of its own) the call goes ahead,
  the session and the user are told (at most once every few minutes per cause), and the fault
  goes to .claude/scbot/guard.log. The hooks start it through LAUNCHER, which cannot exit with
  code 2, the code Claude Code reads as "block": a missing, moved or broken script lets every
  call and prompt through.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ONE_M = 1_000_000
SMALL = 200_000
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
              "output_tokens")
# The two crew roles: sub-agent type -> (the model the role is written for, the alias the Agent
# tool takes). A role is only ever read from the agent type Claude Code puts in the hook input.
CREW_ROLES = {
    "scbot-architect": ("claude-fable-5-2", "fable"),
    "scbot-worker": ("claude-opus-5-5", "opus"),
}
# The documented way to start a lead is to type one of these first (prompts/SCBOT-README.md).
# It only names the prompt in `status` and lets the guard mention a model mismatch; nothing is
# refused because of it.
PROMPT_FILES = {"SCBOT.md": "", "SCBOT-ARCHITECT.md": "scbot-architect",
                "SCBOT-WORKER.md": "scbot-worker"}
# Every tool the hook can see that starts an agent.
AGENT_TOOLS = ("Agent", "Task", "Workflow")
# Paths (relative to the repo root) that are implementation. A sub-agent of type
# scbot-architect plans and designs; it does not edit these with Write or Edit.
ARCHITECT_NO_WRITE = ("MOZA.xml", "tools/*.py", "dashboard/scdash.py", "dashboard/scdash/*",
                      "dashboard/web/*", "dashboard/tests/*", "dashboard/reference/*.py",
                      "cards/*", "reference/*")

# What stays open once a line is passed. Every tool not listed is refused in that state. "any"
# means the call is open whatever it touches. "own" (a sub-agent) means only its own notes
# folder (.claude/scbot/notes/agent-<id>/), its saved report files, and files it wrote or
# edited itself in this run, so that Edit on its own handoff note keeps working (Edit needs
# the file read first) wherever its brief put it. "notes" (a lead) means a file under
# .claude/scbot/ (its notes, its crew's saved reports) or in a Claude memory folder
# (~/.claude/projects/<project>/memory/). One table, so that the tests can walk it
# (test_scbot.AllowLists).
OPEN_AT = {
    # A sub-agent at its cap: bring the work to a boundary, write the handoff, report.
    # ToolSearch is here because SendMessage, TaskStop and Monitor can be deferred tools that
    # have to be loaded first.
    "crew-cap": {
        "Write": "any", "Edit": "any", "MultiEdit": "any", "NotebookEdit": "any",
        "Bash": "any", "PowerShell": "any", "TaskOutput": "any", "Monitor": "any",
        "TaskStop": "any", "KillShell": "any", "SendMessage": "any",
        "SubagentHandback": "any", "TodoWrite": "any", "ToolSearch": "any", "Read": "own",
    },
    # A lead past its reserve line: record the results, leave the notes and memory, commit,
    # tell the user, close.
    "lead-reserve": {
        "Write": "any", "Edit": "any", "MultiEdit": "any", "NotebookEdit": "any",
        "Bash": "any", "PowerShell": "any", "TaskOutput": "any", "Monitor": "any",
        "TaskStop": "any", "KillShell": "any", "SendMessage": "any", "TodoWrite": "any",
        "ToolSearch": "any", "AskUserQuestion": "any", "Artifact": "any", "Read": "notes",
    },
}

# The hooks run this with the interpreter that ran `install`, as
#   <python> -I -S -c LAUNCHER <absolute path of .claude/scbot/bin/scbot.py>
# It cannot exit with code 2: the first atexit entry (run last) ends the process with 0 whatever
# happened before, after stdout and stderr are flushed; a missing script ends it at once. It
# holds no double quote, backslash or line break, so it survives any quoting on the way. The
# script is loaded through the import system, so its compiled copy is cached between calls.
HOOK_MARK = "scbot-guard-hook"
LAUNCHER = ("import os,sys,atexit;atexit.register(os._exit,0);"
            "atexit.register(sys.stderr.flush);atexit.register(sys.stdout.flush);"
            "M='" + HOOK_MARK + "';p=sys.argv[1] if len(sys.argv)>1 else '';"
            "os.path.isfile(p) or sys.exit();"
            "import importlib.util as u;s=u.spec_from_file_location('scbot_guard',p);"
            "m=u.module_from_spec(s);s.loader.exec_module(m);m.main([p,'hook'])")


def env_int(name, default):
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


# Every value a user can set, with its default: `check` prints them all with their current
# values, so the guide's table can be held against the script.
SETTINGS = (
    ("SCBOT_LEAD_LIMIT", 90, "percent at which a lead is pending closing"),
    ("SCBOT_CREW_LIMIT", 80, "percent at which a sub-agent is at its cap"),
    ("SCBOT_CREW_MAX", 6, "sub-agents running at once per session"),
    ("SCBOT_REPORT_MAX_CHARS", 6000, "longest final report from a crew role"),
    ("SCBOT_FORK_MAX", 40, "a fork is refused from this percent of the lead's context"),
    ("SCBOT_SILENT_MINUTES", 30, "a sub-agent silent this long no longer counts as running"),
    ("SCBOT_WARN_MINUTES", 5, "a fail-open warning is repeated at most this often per cause"),
    ("SCBOT_CONTEXT_WINDOW", 0, "overrides every window size, in tokens (0: not set)"),
    ("SCBOT_TITLE", "", "1 names each session's tab after its label"),
    ("SCBOT_GUARD", "", "off switches the guard off"),
    ("SCBOT_ROOT", "", "the repo root (for tests; found from the script's path otherwise)"),
    ("CLAUDE_CODE_DISABLE_1M_CONTEXT", "", "Claude Code's own: 1 makes every window 200,000"),
)
DERIVED = ("lead heads-up = lead limit - 20; lead reserve = lead limit + 6 (at most 98); "
           "crew heads-up = crew limit - 20; crew wrap-up = crew limit - 5; a session is live "
           "for 24 h after its last call; a start that was let through holds a slot for 120 s "
           "until Claude Code reports it; `crew clear` needs --force for a sub-agent active in "
           "the last 5 minutes; a window is corrected after 3 separate readings above the "
           "table, and never above 1,000,000 unless SCBOT_CONTEXT_WINDOW says so")
LIVE_HOURS = 24          # a lead can sit open overnight; after this its label is free again
RESERVE_TTL = 120        # seconds a start that was let through holds a slot before it is seen
RECENT = 300             # `crew clear` leaves alone a sub-agent active this recently (seconds)


def load_limits():
    """The lines, from the environment. Read at every call, so tests and settings can change
    them; the defaults are in SETTINGS."""
    global LEAD_LIMIT, CREW_LIMIT, CREW_MAX, REPORT_MAX, FORK_MAX, SILENT, WARN_EVERY
    global LEAD_HEADS_UP, LEAD_LOW, CREW_HEADS_UP, CREW_WRAP
    defaults = {name: value for name, value, _ in SETTINGS}
    LEAD_LIMIT = env_int("SCBOT_LEAD_LIMIT", defaults["SCBOT_LEAD_LIMIT"])
    CREW_LIMIT = env_int("SCBOT_CREW_LIMIT", defaults["SCBOT_CREW_LIMIT"])
    CREW_MAX = env_int("SCBOT_CREW_MAX", defaults["SCBOT_CREW_MAX"])
    REPORT_MAX = env_int("SCBOT_REPORT_MAX_CHARS", defaults["SCBOT_REPORT_MAX_CHARS"])
    FORK_MAX = env_int("SCBOT_FORK_MAX", defaults["SCBOT_FORK_MAX"])
    # How long a running sub-agent's transcript may stay silent before it no longer counts.
    # The longest silence a live one has is one tool call plus one reply: a Bash call is capped
    # at 10 minutes by default, and a long reply at xhigh takes a few. 30 minutes is three
    # times the longest tool call, so a live sub-agent is never dropped, while a dead one (a
    # crash, Esc, a closed window: no stop event) holds a slot for half an hour at most, and
    # `crew clear` frees it at once.
    SILENT = 60 * env_int("SCBOT_SILENT_MINUTES", defaults["SCBOT_SILENT_MINUTES"])
    WARN_EVERY = 60 * env_int("SCBOT_WARN_MINUTES", defaults["SCBOT_WARN_MINUTES"])
    LEAD_HEADS_UP = LEAD_LIMIT - 20
    LEAD_LOW = min(LEAD_LIMIT + 6, 98)                # the reserve is nearly used
    CREW_HEADS_UP = CREW_LIMIT - 20
    CREW_WRAP = CREW_LIMIT - 5


load_limits()


def now():
    """The clock. One function, so that a test can move it."""
    return time.time()


# --------------------------------------------------------------------------------------------
# Paths and small helpers

def find_root():
    """The repo's main checkout. Works from tools/, from the installed copy under
    .claude/scbot/bin/, and from a worktree under .claude/worktrees/<name>/."""
    forced = os.environ.get("SCBOT_ROOT")
    if forced:
        return Path(forced)
    here = Path(__file__).resolve()
    parts = here.parts
    for i, part in enumerate(parts):
        if part == ".claude" and i > 0:
            return Path(*parts[:i])
    return here.parents[1]


def configure(root):
    global ROOT, ROOT_REAL, BASE, STATE, QUEUE, REPORTS, NOTES
    ROOT = Path(root)
    try:
        ROOT_REAL = ROOT.resolve()
    except OSError:
        ROOT_REAL = ROOT
    BASE = ROOT / ".claude" / "scbot"
    STATE = BASE / "state"
    QUEUE = BASE / "queue"
    REPORTS = BASE / "reports"
    NOTES = BASE / "notes"


configure(find_root())


def stamp(t=None):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now() if t is None else t))


def rel(path):
    """A path as the agent should type it: relative to the repo root, forward slashes."""
    try:
        return Path(path).resolve().relative_to(ROOT_REAL).as_posix()
    except (ValueError, OSError):
        return str(path)


def clean(text, limit=96):
    """An id as one safe file name: letters, digits, '-', '_' and '.', never '.' or '..'."""
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(text or ""))[:limit]
    return "" if not name.strip(".") else name


def bare_id(agent_id):
    text = str(agent_id or "")
    return clean(text[6:] if text.startswith("agent-") else text)


# --------------------------------------------------------------------------------------------
# Faults: what keeps the guard from doing its job. None of them refuses anything.

FAULT_TEXT = {
    "state": ("it cannot write its records under .claude/scbot/ ({detail}). Its checks ran on "
              "what it could read, but what it keeps (labels, the crew count, notices) may be "
              "out of date"),
    "lock": ("a lock file under .claude/scbot/ stayed held ({detail}), so this call went ahead "
             "without the step that needed it"),
    "missing": ("it cannot find this conversation's transcript ({detail}), so the context limits "
                "are not enforced here"),
    "unreadable": ("it cannot read this conversation's context use from its transcript "
                   "({detail}), so the context limits are not enforced here"),
    "model": ("it has no context window for the model {detail}, so the context limits are not "
              "enforced here. SCBOT_CONTEXT_WINDOW sets one"),
    "window": ("{detail}"),
    "reading": ("it read a context figure it cannot believe ({detail}), so it left the limits "
                "off for this call and did not use the figure to correct its window table"),
    "error": ("it hit a fault of its own ({detail}) and let this call through unchecked"),
    "input": ("it got hook input it could not read ({detail}), so nothing was checked"),
}


class Call:
    """What one hook call found wrong with the guard itself, by cause. A cause is said once
    per WARN_EVERY to each actor (the lead, or one sub-agent), since each has to know."""

    def __init__(self, session_id="", event="", actor="lead"):
        self.session_id, self.event, self.actor, self.faults = session_id, event, actor, {}


CALL = None


def fault(cause, detail):
    """Note that the guard could not do part of its job. In a hook the call goes ahead and the
    fault is said (see add_faults); on the command line it is printed."""
    detail = str(detail)[:300]
    if CALL is None:
        print("scbot: %s" % FAULT_TEXT.get(cause, "{detail}").format(detail=detail),
              file=sys.stderr)
        return
    CALL.faults.setdefault(cause, detail)


def log(message):
    try:
        BASE.mkdir(parents=True, exist_ok=True)
        with open(BASE / "guard.log", "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (stamp(), message))
    except OSError:
        pass


# --------------------------------------------------------------------------------------------
# Files. Nothing here raises in a hook: a failed write is a fault, and the decision goes on.

def read_record(path, tries=3):
    """(object, status) with status 'ok', 'missing' or 'unreadable'. A file another process
    holds, or one caught half written, is tried again before it counts as unreadable."""
    for attempt in range(tries):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f), "ok"
        except FileNotFoundError:
            return None, "missing"
        except (OSError, ValueError):
            if attempt + 1 < tries:
                time.sleep(0.01 * (attempt + 1))
    return None, "unreadable"


def read_json(path, default=None):
    value, status = read_record(path, tries=2)
    return value if status == "ok" else default


def write_bytes(path, data):
    """Write a whole file through a temporary file and a rename. On Windows the rename fails
    while another process has the target open, so it is tried again for about half a second.
    False (and a fault) if it cannot be done."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not os.access(path, os.W_OK):
            raise PermissionError("read-only: %s" % rel(path))
        tmp = path.with_name("%s.%d-%d.tmp" % (path.name, os.getpid(), int(time.time() * 1e6)))
        with open(tmp, "wb") as f:
            f.write(data)
    except OSError as error:
        fault("state", "%s: %s" % (rel(path), error))
        return False
    for attempt in range(8):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(0.015 * (attempt + 1))
        except OSError:
            break
    try:
        os.unlink(tmp)
    except OSError:
        pass
    fault("state", "could not replace %s" % rel(path))
    return False


def write_json(path, obj):
    return write_bytes(path, (json.dumps(obj, indent=1, ensure_ascii=False) + "\n")
                       .encode("utf-8"))


def write_text(path, text):
    return write_bytes(path, text.encode("utf-8"))


def set_marker(path, t, text=""):
    """A marker file whose modified time is the moment of an event. It is written in place (no
    rename), so a reader holding it open cannot make the write fail, and no lock is needed."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        os.utime(path, (t, t))
        return True
    except OSError as error:
        fault("state", "%s: %s" % (rel(path), error))
        return False


def mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


class LockBusy(Exception):
    pass


LOCK_WAIT = 2.0        # seconds; well inside the hooks' 10 s timeout


class Lock:
    """A lock file made with exclusive create. A holder does a few file operations and lets go
    within milliseconds, so a lock older than `stale` seconds, or dated in the future (a clock
    set back), was left by a killed process and is broken."""

    def __init__(self, path, wait=None, stale=10.0):
        self.path, self.stale = Path(path), stale
        self.wait = LOCK_WAIT if wait is None else wait

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        end = time.time() + self.wait
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if abs(time.time() - self.path.stat().st_mtime) > self.stale:
                        os.unlink(self.path)
                        continue
                except OSError:
                    pass
            except PermissionError:        # Windows: the old lock is being deleted
                pass
            if time.time() > end:
                raise LockBusy(rel(self.path))
            time.sleep(0.02)

    def __exit__(self, *exc):
        try:
            os.unlink(self.path)
        except OSError:
            pass


# --------------------------------------------------------------------------------------------
# Measuring a context from its transcript

def read_usage(path, main_only):
    """(tokens, model) from the newest assistant entry that carries usage, or None when there
    is none. Raises OSError when the file cannot be read.

    The transcript format is internal to Claude Code and can change with a version. A
    synthetic entry (model '<synthetic>', written for an error) and one with no usage are
    passed over."""
    size = os.path.getsize(path)
    block, scanned, tail = 1 << 18, 0, b""
    with open(path, "rb") as f:
        pos = size
        while pos > 0 and scanned < (96 << 20):
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            chunk = f.read(step)
            scanned += step
            if b"\n" not in chunk and pos > 0:
                tail = chunk + tail          # one very long line: keep going, in bigger steps
                block = min(block * 2, 8 << 20)
                continue
            lines = (chunk + tail).split(b"\n")
            if pos > 0:
                tail, lines = lines[0], lines[1:]
            else:
                tail = b""
            for line in reversed(lines):
                if b'"usage"' not in line or b"assistant" not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "assistant" or \
                        (main_only and entry.get("isSidechain")):
                    continue
                message = entry.get("message") or {}
                if not isinstance(message, dict):
                    continue
                model = str(message.get("model") or "")
                if model.startswith("<"):
                    continue
                usage = message.get("usage") or {}
                try:
                    total = sum(int(usage.get(k) or 0) for k in USAGE_KEYS)
                except (TypeError, ValueError, AttributeError):
                    continue
                if total > 0:
                    return total, model
    return None


def last_usage(path, main_only):
    """read_usage, with None for a file that cannot be read."""
    try:
        return read_usage(path, main_only)
    except OSError:
        return None


def table_window(model):
    """The context window Claude Code gives a model, from the model configuration docs, or
    None for a model the table does not know. The transcript does not record it."""
    name = (model or "").lower()
    family = re.search(r"(fable|mythos|opus|sonnet|haiku)", name)
    if not family and "[1m]" not in name:
        return None
    if os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT") == "1":
        return SMALL
    if "[1m]" in name or family.group(1) in ("fable", "mythos"):
        return ONE_M
    digits = [int(p) for p in re.split(r"[-\[\]._]", name) if p.isdigit() and len(p) < 3]
    version = tuple(digits[:2]) if digits else (0,)
    first_big = {"opus": (4, 7), "sonnet": (5,), "haiku": (5, 5)}[family.group(1)]
    return ONE_M if version >= first_big else SMALL


LEARNED = None
CONFIRM_READINGS = 3     # separate readings above the table's window before it is corrected


def learned_windows():
    """state/windows.json: {"windows": {model: window}, "seen": {model: [reading, ...]}}."""
    global LEARNED
    if LEARNED is None:
        data = read_json(STATE / "windows.json", {}) or {}
        if not isinstance(data, dict):
            data = {}
        windows = data.get("windows") if isinstance(data.get("windows"), dict) else {}
        seen = data.get("seen") if isinstance(data.get("seen"), dict) else {}
        LEARNED = {"windows": windows, "seen": seen}
    return LEARNED


def window_for(model, tokens=0, source=""):
    """The window to measure against, or None for a model the guard does not know.

    SCBOT_CONTEXT_WINDOW sets it outright, to any size. Otherwise it is the table's figure,
    unless readings have proved the table wrong. One reading never does: a reading above the
    table's window is measured against 1,000,000 for that reading only, and the table is
    corrected (to 1,000,000, never more) once the same model has gone past it on
    CONFIRM_READINGS separate readings (another transcript, or another count). Only a hook
    call writes the correction (state/windows.json); a command never does. A reading above
    1,000,000 is not a window at all: measure_path treats it as a bad reading."""
    forced = env_int("SCBOT_CONTEXT_WINDOW", 0)
    if forced > 0:
        return forced
    table = table_window(model)
    if table is None:
        return None
    learned = learned_windows()
    window = max(table, min(ONE_M, int(learned["windows"].get(model) or 0)))
    if tokens <= window or tokens > ONE_M:
        return window
    if CALL is not None:                         # a hook call: count this reading
        reading = "%s|%d" % (Path(str(source)).name, tokens)
        seen = [r for r in learned["seen"].get(model, []) if isinstance(r, str)]
        if reading not in seen:
            seen = (seen + [reading])[-10:]
            learned["seen"][model] = seen
            if len(seen) >= CONFIRM_READINGS:
                learned["windows"][model] = ONE_M
                log("window for %s corrected from %d to %d (%d readings above it, the latest "
                    "%d tokens)" % (model, window, ONE_M, len(seen), tokens))
                fault("window", "the guard's table gave model %s a window of %s tokens, and "
                      "%d separate readings have gone past it (the latest %s), so the table is "
                      "wrong. The guard now measures that model against %s. Tell the user, so "
                      "that the table in tools/scbot.py can be fixed" % (
                          model, format(window, ","), len(seen), format(tokens, ","),
                          format(ONE_M, ",")))
            write_json(STATE / "windows.json", learned)
    return ONE_M


def agent_transcript(main_transcript, agent_id):
    """<project>/<session>.jsonl -> <project>/<session>/subagents/agent-<id>.jsonl, or the path
    itself when it already names that sub-agent's own file."""
    path = Path(main_transcript)
    bare = bare_id(agent_id)
    if path.name in ("agent-%s.jsonl" % bare, "%s.jsonl" % bare):
        return path
    folder = path.with_suffix("") / "subagents"
    for name in ("agent-%s.jsonl" % bare, "%s.jsonl" % bare):
        if (folder / name).exists():
            return folder / name
    return folder / ("agent-%s.jsonl" % bare)


def measure_path(path, main_only):
    """{'pct','tokens','window','model','path'}, or {'fault': cause, 'detail': ...}, or None
    when there is nothing to measure yet (a small transcript with no usage in it)."""
    try:
        found = read_usage(path, main_only)
    except FileNotFoundError:
        return {"fault": "missing", "detail": rel(path)}
    except OSError as error:
        return {"fault": "unreadable", "detail": "%s: %s" % (rel(path), error.__class__.__name__)}
    if not found:
        try:
            if os.path.getsize(path) > 300_000:
                return {"fault": "unreadable", "detail": "no usage in %s" % rel(path)}
        except OSError:
            pass
        return None
    tokens, model = found
    largest = env_int("SCBOT_CONTEXT_WINDOW", 0) or ONE_M
    if tokens > largest and table_window(model) is not None:
        return {"fault": "reading", "detail": "%s tokens for model %s in %s, more than any "
                "window it has" % (format(tokens, ","), model, rel(path)),
                "model": model, "tokens": tokens}
    window = window_for(model, tokens, path)
    if not window:
        return {"fault": "model", "detail": "'%s'" % model, "model": model, "tokens": tokens}
    return {"pct": 100.0 * tokens / window, "tokens": tokens, "window": window, "model": model,
            "path": str(path)}


def measure(transcript, agent_id=None):
    """Context use of a main conversation, or of one of its sub-agents when agent_id is given.
    See measure_path for what comes back; None also when no transcript is named."""
    if not transcript:
        return None
    path = Path(os.path.expanduser(str(transcript)))
    if agent_id:
        path = agent_transcript(path, agent_id)
    return measure_path(path, main_only=not agent_id)


def figure(m):
    return "%.0f%% (%s of %s tokens)" % (m["pct"], format(m["tokens"], ","),
                                         format(m["window"], ","))


def shown(m):
    if not m:
        return "not measured yet"
    if "pct" in m:
        return figure(m)
    return "unknown (%s: %s)" % (m["fault"], m.get("detail", ""))


# --------------------------------------------------------------------------------------------
# Sessions

def session_dir(session_id):
    return STATE / (clean(session_id) or "unknown")


def all_sessions():
    out = []
    if STATE.is_dir():
        for folder in STATE.iterdir():
            if folder.is_dir():
                record = read_json(folder / "session.json")
                if isinstance(record, dict) and record.get("id"):
                    out.append(record)
    return out


def is_live(record):
    return not record.get("ended") and not record.get("closed") and \
        now() - record.get("seen_t", 0) < LIVE_HOURS * 3600


def live_sessions():
    """The live session records. A folder untouched for longer than a session stays live is
    passed over unread, so the cost does not grow with every session ever registered."""
    out = []
    try:
        entries = list(os.scandir(STATE))
    except OSError:
        return out
    for entry in entries:
        try:          # a file's age, so the file clock: time.time(), not now()
            if not entry.is_dir() or \
                    time.time() - entry.stat().st_mtime > (LIVE_HOURS + 1) * 3600:
                continue
        except OSError:
            continue
        record = read_json(Path(entry.path) / "session.json")
        if isinstance(record, dict) and record.get("id") and is_live(record):
            out.append(record)
    return out


def save_session(record):
    if record.get("_volatile"):
        return False
    return write_json(session_dir(record["id"]) / "session.json", record)


def assign_label(record):
    """Give a record the lowest label no other live session holds, and save it, under the
    state lock so that two new sessions cannot take the same one."""
    def pick():
        taken = {r.get("label") for r in live_sessions() if r.get("id") != record["id"]}
        number = 1
        while "SCBOT-%d" % number in taken:
            number += 1
        record["label"], record["label_t"] = "SCBOT-%d" % number, now()
        save_session(record)
    try:
        with Lock(STATE / ".lock"):
            pick()
    except LockBusy as busy:
        fault("lock", busy)
        pick()                     # a clash this leaves is mended by keep_label_unique


def keep_label_unique(record):
    """Labels are unique among live sessions. When two hold one (a session that sat idle past
    LIVE_HOURS lost its label to a new one, then came back; or a label given without the
    lock), the one that took it last keeps it and the other is given a new one. Returns the
    old label when this record was the one renamed."""
    mine = (record.get("label_t", 0), record["id"])
    rivals = [r for r in live_sessions()
              if r.get("id") != record["id"] and r.get("label") == record.get("label")]
    if not rivals or all(mine > (r.get("label_t", 0), r["id"]) for r in rivals):
        return None
    old = record.get("label")
    assign_label(record)
    log("session %s renamed from %s to %s (the label was held by another live session)"
        % (record["id"], old, record["label"]))
    return old


def load_session(inp, create=True):
    sid = clean(inp.get("session_id")) or "unknown"
    path = session_dir(sid) / "session.json"
    record, status = read_record(path)
    if status == "ok" and isinstance(record, dict) and record.get("label"):
        record["id"] = sid
        return record
    if status == "unreadable":
        # Held by another process, or damaged. Do not make a new record over it: work on a
        # copy in memory that is never saved, and say so.
        fault("state", "cannot read %s" % rel(path))
        return {"id": sid, "label": "SCBOT-?", "_volatile": True, "seen_t": now()}
    if not create:
        return None
    record = {"id": sid, "label": "", "started": stamp(), "seen_t": now(),
              "transcript": lead_transcript_of(inp) or "", "model": str(inp.get("model") or "")}
    assign_label(record)
    return record


def lead_transcript_of(inp):
    """The main transcript named in a hook input. Inside a sub-agent the path may already be the
    sub-agent's own file, which is not the lead's."""
    path = str(inp.get("transcript_path") or "")
    if not path or Path(path).parent.name == "subagents":
        return ""
    return path


def touch_session(record, inp):
    """Keep the record current without writing it on every call. Returns the old label when
    the session had to be renamed."""
    renamed = None
    changed = False
    if now() - record.get("seen_t", 0) > 60:
        record["seen_t"] = now()
        changed = True
        renamed = keep_label_unique(record)
    path = lead_transcript_of(inp)
    if path and record.get("transcript") != path:
        record["transcript"] = path
        changed = True
    if record.get("ended"):        # a call after SessionEnd: the session is running again
        record.pop("ended", None)
        changed = True
    if changed:
        save_session(record)
    return renamed


def renamed_text(record, old):
    return ("SCBOT guard: this session is now %s. Its label %s was given to another live "
            "session while this one was idle. Use %s from here on." % (
                record["label"], old, record["label"]))


# --------------------------------------------------------------------------------------------
# The crew of a session
#
# A member's state is kept in marker files in state/<session>/crew/, named by its agent id:
#   <id>.start   modified time = its last start (SubagentStart)
#   <id>.stop    modified time = its last stop (SubagentStop, SessionEnd, crew clear); the text
#                says why
#   <id>.seen    modified time = its last tool call, refreshed at most once a minute
#   <id>.json    what is known about it: type, description, model, report, transcript
#   <token>.res  a start the guard let through and has not seen begin yet (RESERVE_TTL)
# A member runs when its start is newer than its stop and something of it (start, tool call or
# transcript) is newer than SILENT. Stops and starts need no lock and no rename, so neither a
# leftover lock nor a reader holding a file can lose one.

def crew_dir(session_id):
    return session_dir(session_id) / "crew"


def member_meta(session_id, bare):
    meta = read_json(crew_dir(session_id) / ("%s.json" % bare), {})
    return meta if isinstance(meta, dict) else {}


def update_meta(session_id, bare, change):
    """Read, change and write one member's facts. Facts are for display; if the lock stays
    held the change is made without it rather than lost."""
    path = crew_dir(session_id) / ("%s.json" % bare)

    def apply():
        meta = member_meta(session_id, bare)
        change(meta)
        meta["id"] = bare
        write_json(path, meta)
        return meta
    try:
        with Lock(crew_dir(session_id) / ".lock", wait=min(LOCK_WAIT, 0.5)):
            return apply()
    except LockBusy as busy:
        fault("lock", busy)
        return apply()


def member_transcript(record, bare, meta=None):
    meta = member_meta(record["id"], bare) if meta is None else meta
    if meta.get("transcript"):
        return meta["transcript"]
    if record.get("transcript"):
        return str(agent_transcript(record["transcript"], bare))
    return ""


def crew_marks(session_id):
    """(marks by member id, live reservations as (time, path, target))."""
    marks, reserved = {}, []
    try:
        entries = list(os.scandir(crew_dir(session_id)))
    except OSError:
        return marks, reserved
    for entry in entries:
        stem, _, kind = entry.name.rpartition(".")
        if kind not in ("start", "stop", "seen", "res"):
            continue
        try:
            t = entry.stat().st_mtime
        except OSError:
            continue
        if kind == "res":
            if now() - t < RESERVE_TTL:
                try:
                    target = Path(entry.path).read_text(encoding="utf-8").strip()
                except OSError:
                    target = ""
                reserved.append((t, entry.path, target))
            else:
                try:
                    os.unlink(entry.path)
                except OSError:
                    pass
        else:
            marks.setdefault(stem, {})[kind] = t
    return marks, reserved


def member_state(record, bare, mark, meta=None):
    """'running', 'silent' (started, never stopped, but quiet past SILENT), 'done' or 'new'.

    A tool call of its own after its stop (one cleared by hand, or resumed without a start
    event) means it is at work: it counts again. So does a silent one that acts again."""
    start, stop, seen = mark.get("start", 0.0), mark.get("stop", 0.0), mark.get("seen", 0.0)
    if not start:
        return "new"
    if start <= stop and seen <= stop:
        return "done"
    last = max(start, seen)
    if now() - last <= SILENT:
        return "running"
    path = member_transcript(record, bare, meta)
    if start > stop and path and now() - mtime(path) <= SILENT:
        return "running"
    return "silent"


def crew_count(record):
    """(running member ids, live reservations)."""
    marks, reserved = crew_marks(record["id"])
    running = [bare for bare, mark in sorted(marks.items())
               if member_state(record, bare, mark) == "running"]
    return running, reserved


def reserve(record, token, target=""):
    """Count the running sub-agents and, if there is room, hold a slot for a start the guard
    lets through, all under the crew lock: four starts in one message cannot all pass the
    count. Returns (allowed, running ids, reservations)."""
    folder = crew_dir(record["id"])
    try:
        with Lock(folder / ".lock"):
            running, reserved = crew_count(record)
            if target and target in running:
                return True, running, reserved
            if len(running) + len(reserved) >= CREW_MAX:
                return False, running, reserved
            set_marker(folder / ("%s.res" % (clean(token) or "r%d" % int(now() * 1e6))),
                       now(), target)
            return True, running, reserved
    except LockBusy as busy:
        fault("lock", "%s; the crew count was not checked" % busy)
        return True, [], []


def record_start(record, bare, t):
    """A start was seen: mark it, and let it take the slot held for it (one for this id, else
    the oldest), both under the crew lock so that a count in between sees it once. If the lock
    stays held, both are done without it rather than lost."""
    def take():
        set_marker(crew_dir(record["id"]) / ("%s.start" % bare), t)
        _, reserved = crew_marks(record["id"])
        mine = [r for r in reserved if r[2] == bare] or sorted(r for r in reserved if not r[2])
        if mine:
            try:
                os.unlink(mine[0][1])
            except OSError:
                pass
    try:
        with Lock(crew_dir(record["id"]) / ".lock"):
            take()
    except LockBusy as busy:
        fault("lock", busy)
        take()


def end_crew(record, reason):
    """Mark every running or silent member stopped, for an event that ends them all."""
    marks, reserved = crew_marks(record["id"])
    for bare, mark in marks.items():
        if member_state(record, bare, mark) in ("running", "silent"):
            set_marker(crew_dir(record["id"]) / ("%s.stop" % bare), now(), reason)
    for _, path, _ in reserved:
        try:
            os.unlink(path)
        except OSError:
            pass


def crew_line(record, bare):
    meta = member_meta(record["id"], bare)
    text = "%s %s" % (meta.get("type") or "agent", bare[:10])
    if meta.get("desc"):
        text += " (%s)" % meta["desc"][:40]
    return text


def running_list(record, running, reserved):
    parts = [crew_line(record, bare) for bare in running]
    if reserved:
        parts.append("%d starting" % len(reserved))
    return "; ".join(parts)


def finished_member(record, target):
    """The id of a crew member that has started before and is not running now, named by its id
    or its name, or None."""
    target = str(target or "")
    if not target or target == "main":
        return None
    marks, _ = crew_marks(record["id"])
    bare = bare_id(target)
    if bare not in marks:
        bare = next((b for b in marks if member_meta(record["id"], b).get("name") == target),
                    None)
    if bare is None or not marks[bare].get("start"):
        return None
    return None if member_state(record, bare, marks[bare]) == "running" else bare


def report_path(record, bare):
    return REPORTS / (record.get("label") or "unlabeled") / ("%s.md" % bare)


def step_notice(session_id, actor, pct, band):
    """True once per whole percent per band, so a notice is not repeated on every call."""
    path = session_dir(session_id) / "actors" / ("%s.json" % clean(actor))
    seen = read_json(path, {}) or {}
    key = "%s:%d" % (band, int(pct) if band in ("limit", "wrap", "low", "pending") else 0)
    if seen.get("last") == key:
        return False
    seen["last"] = key
    write_json(path, seen)
    return True


def clear_hint(record):
    return ("`python tools/scbot.py crew --session %s` lists them with when each was last "
            "active. Wait for one to finish: a sub-agent whose stop was never seen stops "
            "counting by itself once it has been silent for %d minutes. Do not clear one "
            "yourself; if one looks stuck, tell the user." % (record["label"], SILENT // 60))


# --------------------------------------------------------------------------------------------
# Hook outputs

CONTEXT_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
                  "SubagentStart", "SubagentStop")


def out_context(event, text):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def out_deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def out_block(reason):
    return {"decision": "block", "reason": reason}


def warned_recently(session_id, cause):
    """True when this cause was already said in this session within WARN_EVERY. Kept beside the
    state, or in the temp folder when the state cannot be written."""
    import tempfile
    key = "%s|%s" % (session_id or "-", cause)
    places = [BASE / "warned.json",
              Path(tempfile.gettempdir()) / ("scbot-warned-%s.json" % clean(
                  ROOT.as_posix().lower())[-60:])]
    for place in places:
        seen = read_json(place, {}) or {}
        if not isinstance(seen, dict):
            seen = {}
        if now() - float(seen.get(key, 0) or 0) < WARN_EVERY:
            return True
        seen = {k: t for k, t in seen.items() if now() - float(t or 0) < max(WARN_EVERY, 3600)}
        seen[key] = now()
        global CALL
        held, CALL = CALL, None          # a failure here is not itself a fault to say
        try:
            ok = write_json_quiet(place, seen)
        finally:
            CALL = held
        if ok:
            return False
    return False


def write_json_quiet(path, obj):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(path).with_name("%s.%d.tmp" % (Path(path).name, os.getpid()))
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def add_faults(event, result):
    """Say the call's faults: to the model through the event's context (or the refusal's
    reason) and to the user through systemMessage, each cause at most once per WARN_EVERY."""
    if CALL is None or not CALL.faults:
        return result
    said, causes = [], []
    for cause, detail in CALL.faults.items():
        if not warned_recently("%s/%s" % (CALL.session_id, CALL.actor), cause):
            log("fault %s in session %s (%s): %s" % (cause, CALL.session_id, event, detail))
            said.append(FAULT_TEXT.get(cause, "{detail}").format(detail=detail))
            causes.append(cause)
    if not said:
        return result
    text = "SCBOT guard: " + ". Also, ".join(said) + "."
    if any(cause != "window" for cause in causes):
        text += " The call went ahead. Tell the user; `python tools/scbot.py check` may say why."
    result = dict(result or {})
    result["systemMessage"] = (result.get("systemMessage", "") + " " + text).strip()
    specific = result.get("hookSpecificOutput")
    if specific and specific.get("permissionDecision") == "deny":
        specific["permissionDecisionReason"] += " " + text
    elif event in CONTEXT_EVENTS and not result.get("decision"):
        specific = result.setdefault("hookSpecificOutput", {"hookEventName": event})
        specific["additionalContext"] = (specific.get("additionalContext", "") + "\n" + text) \
            .strip()
    return result


def note_measure_fault(m, missing_ok=False):
    """A reading that failed is a fault, except a missing file where one is not expected yet."""
    if m and "fault" in m and not (missing_ok and m["fault"] == "missing"):
        fault(m["fault"], m.get("detail", ""))


# --------------------------------------------------------------------------------------------
# Hook events

def on_session_start(inp):
    record = load_session(inp)
    if inp.get("model"):
        record["model"] = str(inp["model"])
    record["seen_t"] = now()
    record.pop("ended", None)
    if lead_transcript_of(inp):
        record["transcript"] = lead_transcript_of(inp)
    if str(inp.get("source") or "") == "resume":
        # The sub-agents of the earlier run of this session ended with its process.
        end_crew(record, "session resumed: its earlier sub-agents did not survive")
    renamed = keep_label_unique(record) if not record.get("_volatile") else None
    save_session(record)
    others = [r for r in live_sessions() if r.get("id") != record["id"]]
    lines = []
    if renamed:
        lines.append(renamed_text(record, renamed))
    lines += [
        "SCBOT guard (installed by the user): this top-level session is %s." % record["label"],
        "Rules it enforces here: automatic compaction is off. At %d%% of its context a "
        "top-level session is pending closing: it takes on no new work, starts no new "
        "sub-agents, waits for the ones still running, records their results and closes. "
        "A sub-agent is capped at %d%% of its own context. At most %d sub-agents run at once, "
        "and a sub-agent cannot start sub-agents. The guard says when a line is reached; "
        "it shows no running meter." % (LEAD_LIMIT, CREW_LIMIT, CREW_MAX),
    ]
    if others:
        lines.append("Other live sessions in this repo, each with its own crew: %s."
                     % "; ".join(r["label"] for r in others))
    else:
        lines.append("No other live SCBOT session is registered in this repo.")
    tasks = queue_tasks()
    if tasks:
        count = {}
        for task in tasks:
            key = "handed over" if task["state"] == "open" and task.get("handover") \
                else task["state"]
            count[key] = count.get(key, 0) + 1
        listed = ", ".join("%d %s" % (n, k) for k, n in sorted(count.items())
                           if k not in ("done", "dropped"))
        if listed:
            lines.append("Work queue: %s. `python tools/scbot.py queue list` shows it." % listed)
    lines.append("`python tools/scbot.py status --session %s` shows this session and its crew "
                 "with each one's context use." % record["label"])
    if record.get("closed"):
        lines.append("This session closed itself on %s. Its closing note: %s." % (
            record["closed"], record.get("note") or "none recorded"))
    result = out_context("SessionStart", "\n".join(lines))
    if os.environ.get("SCBOT_TITLE") == "1" and not inp.get("session_title"):
        result["hookSpecificOutput"]["sessionTitle"] = record["label"]
    return result


def prompt_file_of(prompt):
    """The role prompt a lead was started with: the first thing typed is `@<file>` (the guide's
    way to start one). Anything else names none. A name somewhere inside a prompt never counts."""
    found = re.match(r"\s*@(?:\./)?(?:prompts[/\\])?(SCBOT(?:-ARCHITECT|-WORKER)?\.md)\b",
                     prompt or "")
    return found.group(1) if found else ""


def lead_line(record, m):
    """Pending closing follows the meter: on at LEAD_LIMIT, off again when a reading falls
    below it (a typed /compact, a corrected window, a reopened session). Without a reading the
    guard fails open and nothing is pending. Returns (pct, pending, change)."""
    if not m or "pct" not in m:
        return None, False, None
    pct = m["pct"]
    pending = pct >= LEAD_LIMIT
    change = None
    if pending and not record.get("pending"):
        record["pending"], record["pending_pct"], change = stamp(), round(pct, 1), "on"
    elif not pending and record.get("pending"):
        record.pop("pending", None)
        record.pop("pending_pct", None)
        change = "off"
    if change:
        save_session(record)
    return pct, pending, change


def back_under_text(m):
    return ("SCBOT guard: this session's context is back to %s, under its %d%% line, so it is "
            "no longer pending closing." % (figure(m), LEAD_LIMIT))


def on_user_prompt(inp):
    record = load_session(inp)
    renamed = touch_session(record, inp)
    if record.get("closed"):
        return out_block(
            "%s closed itself on %s and takes no more prompts. Start a new session. Its closing "
            "note: %s. To reopen it anyway: python tools/scbot.py reopen --session %s" % (
                record["label"], record["closed"], record.get("note") or "none recorded",
                record["id"]))
    lines = [renamed_text(record, renamed)] if renamed else []
    m = measure(record.get("transcript") or lead_transcript_of(inp))
    note_measure_fault(m, missing_ok=True)          # a new session may have no file yet
    if not record.get("prompt_checked"):
        record["prompt_checked"] = True
        record["prompt_file"] = prompt_file_of(str(inp.get("prompt") or ""))
        save_session(record)
        want = CREW_ROLES.get(PROMPT_FILES.get(record["prompt_file"], ""), ("",))[0]
        model = (m or {}).get("model") or record.get("model") or ""
        if want and model and want not in model:
            lines.append("SCBOT guard: %s was started with %s, which is written for %s at xhigh "
                         "effort. Its model is %s. The model of a top-level session is the "
                         "user's choice in the client." % (record["label"],
                                                          record["prompt_file"], want, model))
    pct, pending, change = lead_line(record, m)
    if pending:
        lines.append(pending_text(record, m))
    elif change == "off":
        lines.append(back_under_text(m))
    elif pct is not None and pct >= LEAD_HEADS_UP and step_notice(
            record["id"], "lead-prompt", pct, "heads-up"):
        lines.append(heads_up_text(m))
    if lines:
        return out_context("UserPromptSubmit", "\n".join(lines))
    return None


def heads_up_text(m):
    return ("SCBOT guard: this session's context is at %s. At %d%% it becomes pending closing "
            "(no new work, no new sub-agents). Start nothing large that cannot finish or be "
            "handed over before then." % (figure(m), LEAD_LIMIT))


def pending_text(record, m):
    running, reserved = crew_count(record)
    text = ("SCBOT guard: this session's context is at %s, past its %d%% line. It is pending "
            "closing: it takes on no new work and starts or resumes no sub-agents. "
            % (figure(m), LEAD_LIMIT))
    if running or reserved:
        n = len(running) + len(reserved)
        text += ("%d sub-agent%s still running (%s). They finish on their own boundary; do not "
                 "stop them. " % (n, "s are" if n > 1 else " is",
                                  running_list(record, running, reserved)))
    else:
        text += "No sub-agent is running. "
    text += ("Each final report is saved under %s. What is left for this session: record each "
             "result and where its notes are, bring the repo, memory and notes to a state the "
             "next session can start from, tell the user it is pending closing or closed, then "
             "run `python tools/scbot.py close --session %s --note \"<closing note>\"`."
             % (rel(REPORTS / record["label"]), record["label"]))
    return text


def role_mismatch(tool_input):
    kind = str(tool_input.get("subagent_type") or "")
    if kind not in CREW_ROLES:
        return None
    model_id, alias = CREW_ROLES[kind]
    asked = str(tool_input.get("model") or "")
    if asked and asked != alias and asked != model_id:
        return ("The %s role runs on %s only (the user's rule). This call asks for model '%s'. "
                "Leave `model` out: the definition sets it." % (kind, model_id, asked))
    effort = str(tool_input.get("effort") or "")
    if effort and effort != "xhigh":
        return ("The %s role runs at xhigh effort only (the user's rule). This call asks for "
                "'%s'. Leave `effort` out: the definition sets it." % (kind, effort))
    return None


def repo_path(raw, cwd=None):
    """A tool's file path relative to the repo root (or to its worktree), lower case with
    forward slashes; None for a path outside the repo."""
    text = str(raw or "").replace("\\", "/")
    if not text:
        return None
    if not (text.startswith("/") or re.match(r"[A-Za-z]:/", text)):
        text = (str(cwd or ROOT).replace("\\", "/").rstrip("/") + "/" + text)
    text = os.path.normpath(text).replace("\\", "/").lower()
    for root in {ROOT.as_posix().lower().rstrip("/"), ROOT_REAL.as_posix().lower().rstrip("/")}:
        if text.startswith(root + "/"):
            text = text[len(root) + 1:]
            parts = text.split("/")
            if len(parts) > 3 and parts[0] == ".claude" and parts[1] == "worktrees":
                text = "/".join(parts[3:])
            return text
    return None


def architect_write_block(tool, tool_input, cwd=None):
    if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return None
    path = repo_path(tool_input.get("file_path") or tool_input.get("notebook_path"), cwd)
    if not path:
        return None
    from fnmatch import fnmatchcase
    for pattern in ARCHITECT_NO_WRITE:
        if fnmatchcase(path, pattern.lower()):
            return ("%s is part of the implementation, and the Architect role does not change "
                    "it (the user's rule: its output is plans, designs, mockups and reviews). "
                    "Write the change as a plan or as a brief for a Worker instead." % path)
    return None


def is_note_path(raw, cwd=None):
    """A file under .claude/scbot/ in the repo, or in a Claude memory folder."""
    path = repo_path(raw, cwd)
    if path is not None and path.startswith(".claude/scbot/"):
        return True
    text = str(raw or "").replace("\\", "/").lower()
    return bool(re.search(r"/\.claude/projects/[^/]+/memory/", text))


WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def norm_path(raw, cwd=None):
    """A tool's file path, absolute, forward slashes, lower case: for comparing two paths."""
    text = str(raw or "").replace("\\", "/")
    if not text:
        return ""
    if not (text.startswith("/") or re.match(r"[A-Za-z]:/", text)):
        text = str(cwd or ROOT).replace("\\", "/").rstrip("/") + "/" + text
    return os.path.normpath(text).replace("\\", "/").lower()


def note_written(record, bare, raw, cwd=None):
    """Remember a file a sub-agent wrote or edited, so that it may still read it at its cap."""
    path = norm_path(raw, cwd)
    if not path:
        return
    wrote = crew_dir(record["id"]) / ("%s.wrote" % bare)
    try:
        if path in wrote.read_text(encoding="utf-8").splitlines():
            return
    except OSError:
        pass
    try:
        wrote.parent.mkdir(parents=True, exist_ok=True)
        with open(wrote, "a", encoding="utf-8") as f:
            f.write(path + "\n")
    except OSError as error:
        fault("state", "%s: %s" % (rel(wrote), error))


def is_own_path(record, bare, raw, cwd=None):
    """A sub-agent's own notes folder, its report files, or a file it wrote in this run."""
    inside = repo_path(raw, cwd)
    if inside is not None:
        if inside.startswith(".claude/scbot/notes/agent-%s/" % bare.lower()):
            return True
        report = rel(report_path(record, bare)).lower()
        if inside in (report, report[:-3] + ".full.md"):
            return True
    path = norm_path(raw, cwd)
    try:
        return bool(path) and path in (crew_dir(record["id"]) / ("%s.wrote" % bare)).read_text(
            encoding="utf-8").splitlines()
    except OSError:
        return False


def open_in(state, tool, tool_input, cwd=None, own=None):
    """Whether OPEN_AT leaves this call open in that state. `own` tells a sub-agent's own
    files (see is_own_path)."""
    scope = OPEN_AT[state].get(tool)
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if scope == "any":
        return True
    if scope == "notes":
        return is_note_path(raw, cwd)
    if scope == "own":
        return bool(own and own(raw, cwd))
    return False


def on_pre_tool(inp):
    record = load_session(inp)
    agent_id = bare_id(inp.get("agent_id"))
    renamed = touch_session(record, inp) if not agent_id else None
    tool = str(inp.get("tool_name") or "")
    tool_input = inp.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if agent_id:
        return crew_pre_tool(inp, record, agent_id, tool, tool_input)
    result = lead_pre_tool(inp, record, tool, tool_input)
    if renamed:
        text = renamed_text(record, renamed)
        if result and "permissionDecisionReason" in result.get("hookSpecificOutput", {}):
            result["hookSpecificOutput"]["permissionDecisionReason"] += " " + text
        elif result:
            spec = result["hookSpecificOutput"]
            spec["additionalContext"] = text + "\n" + spec.get("additionalContext", "")
        else:
            result = out_context("PreToolUse", text)
    return result


def crew_pre_tool(inp, record, bare, tool, tool_input):
    """A tool call inside a sub-agent."""
    if tool in AGENT_TOOLS:
        return out_deny("Sub-agents cannot start sub-agents in this setup (the user's rule). "
                        "Do the work yourself. If the task should be split, say so in your "
                        "report and your lead will split it.")
    if tool == "SendMessage" and finished_member(record, tool_input.get("to")):
        return out_deny("A message to a finished sub-agent starts it running again, and a "
                        "sub-agent does not start sub-agents (the user's rule). Ask your lead.")
    if str(inp.get("agent_type") or "") == "scbot-architect":
        blocked = architect_write_block(tool, tool_input, inp.get("cwd"))
        if blocked:
            return out_deny(blocked)
    seen = crew_dir(record["id"]) / ("%s.seen" % bare)
    if now() - mtime(seen) > 60:
        set_marker(seen, now())
    if tool in WRITE_TOOLS:
        note_written(record, bare, tool_input.get("file_path") or tool_input.get(
            "notebook_path"), inp.get("cwd"))
    if tool == "SubagentHandback":
        return handback(record, inp, bare, str(tool_input.get("message") or ""))
    path = None
    own = str(inp.get("transcript_path") or "")
    candidates = []
    if own:
        candidates.append(agent_transcript(own, bare))
    if record.get("transcript"):
        candidates.append(agent_transcript(record["transcript"], bare))
    meta_path = member_meta(record["id"], bare).get("transcript") if not any(
        c.exists() for c in candidates) else None
    if meta_path:
        candidates.insert(0, Path(meta_path))
    for candidate in candidates:
        if candidate.exists():
            path = candidate
            break
    if path is None:
        fault("missing", "no transcript for sub-agent %s (looked for %s)" % (
            bare, ", ".join(rel(c) for c in candidates) or "nothing named"))
        return None
    m = measure_path(path, main_only=False)
    note_measure_fault(m)
    if not m or "pct" not in m:
        return None
    pct = m["pct"]
    if pct >= CREW_LIMIT:
        text = ("SCBOT guard: your context is at %s, at the %d%% cap for a sub-agent (the "
                "user's rule). Reading and searching are closed. Bring your work to a clean "
                "boundary, write your handoff note (what is done, what is left, where "
                "everything is, what you would do next) in your notes folder, then hand "
                "back your report. Still open: %s." % (figure(m), CREW_LIMIT, open_list(
                    "crew-cap")))
        if not open_in("crew-cap", tool, tool_input, inp.get("cwd"),
                       own=lambda raw, cwd: is_own_path(record, bare, raw, cwd)):
            return out_deny(text)
        if step_notice(record["id"], bare, pct, "limit"):
            return out_context("PreToolUse", text)
        return None
    if pct >= CREW_WRAP and step_notice(record["id"], bare, pct, "wrap"):
        return out_context("PreToolUse", (
            "SCBOT guard: your context is at %s. Your cap is %d%%. Finish the step in hand "
            "and bring the work to a clean boundary now, then write your handoff note and "
            "report. Open nothing large." % (figure(m), CREW_LIMIT)))
    if CREW_HEADS_UP <= pct < CREW_WRAP and step_notice(record["id"], bare, pct, "heads-up"):
        return out_context("PreToolUse", (
            "SCBOT guard: your context is at %s. Your cap is %d%%: at %d%% you are asked to "
            "wrap up, and at the cap reading and searching close. Plan to finish or to hand "
            "over before then, and keep detail in files." % (figure(m), CREW_LIMIT, CREW_WRAP)))
    return None


def open_list(state):
    names = sorted(k for k, v in OPEN_AT[state].items() if v == "any")
    notes = sorted(k for k, v in OPEN_AT[state].items() if v == "notes")
    own = sorted(k for k, v in OPEN_AT[state].items() if v == "own")
    text = ", ".join(names)
    if notes:
        text += ", and %s for files under .claude/scbot/ and memory files" % ", ".join(notes)
    if own:
        text += (", and %s for your own notes folder, your report files and the files you "
                 "wrote yourself" % ", ".join(own))
    return text


def lead_pre_tool(inp, record, tool, tool_input):
    """A tool call of the top-level session."""
    m = measure(record.get("transcript") or lead_transcript_of(inp))
    if m is None and not (record.get("transcript") or lead_transcript_of(inp)):
        m = {"fault": "missing", "detail": "no transcript_path in the hook input"}
    note_measure_fault(m)
    pct, pending, change = lead_line(record, m)

    if tool in AGENT_TOOLS:
        if pending:
            return out_deny(pending_text(record, m))
        if tool != "Workflow" and str(tool_input.get("subagent_type") or "") == "fork" \
                and pct is not None and pct >= FORK_MAX:
            return out_deny(
                "A fork starts with this whole conversation, so it would begin at about %.0f%% "
                "of its context against a cap of %d%%. Start a scbot-worker or scbot-architect "
                "with a written brief instead." % (pct, CREW_LIMIT))
        wrong = role_mismatch(tool_input) if tool != "Workflow" else None
        if wrong:
            return out_deny(wrong)
        token = str(inp.get("tool_use_id") or "")
        allowed, running, reserved = reserve(record, token)
        if not allowed:
            return out_deny(
                "SCBOT guard: %d sub-agents are running, the most one session runs at once (the "
                "user's rule): %s. Start the next one when one of them has finished. %s"
                % (len(running) + len(reserved), running_list(record, running, reserved),
                   clear_hint(record)))
        return out_context("PreToolUse", back_under_text(m)) if change == "off" else None
    if tool == "SendMessage":
        bare = finished_member(record, tool_input.get("to"))
        if bare and pending:
            return out_deny("This session is pending closing. A message to a finished "
                            "sub-agent starts it running again, which is new work. Record where "
                            "its notes are instead: the next session can resume it.")
        if bare:
            allowed, running, reserved = reserve(record, "resume-%s" % bare, target=bare)
            if not allowed:
                return out_deny(
                    "A message to a finished sub-agent starts it running again, and %d are "
                    "already running (%s). Send it when one has finished. %s"
                    % (len(running) + len(reserved), running_list(record, running, reserved),
                       clear_hint(record)))
        if change != "off":
            return None
    if pct is None:
        return None
    if pct >= LEAD_LOW and not open_in("lead-reserve", tool, tool_input, inp.get("cwd")):
        return out_deny(
            "SCBOT guard: this session's context is at %s and its reserve is nearly used. Open "
            "no more files or reports beyond its own notes, memory and the saved reports. "
            "Still open: %s. Write one line per sub-agent in the closing note (what it was "
            "doing and that its report is under %s), tell the user, and run "
            "`python tools/scbot.py close --session %s --note \"<closing note>\"`."
            % (figure(m), open_list("lead-reserve"), rel(REPORTS / record["label"]),
               record["label"]))
    if pending and step_notice(record["id"], "lead", pct, "pending"):
        return out_context("PreToolUse", pending_text(record, m))
    if change == "off":
        return out_context("PreToolUse", back_under_text(m))
    if LEAD_HEADS_UP <= pct < LEAD_LIMIT and step_notice(record["id"], "lead", pct, "heads-up"):
        return out_context("PreToolUse", heads_up_text(m))
    return None


def handback(record, inp, bare, message):
    """Save a sub-agent's final report. A crew role's report is held to a length the lead's
    reserve can take, and sent back at most twice in one run, so a refusal can never loop."""
    path = report_path(record, bare)
    crew_role = str(inp.get("agent_type") or "") in CREW_ROLES
    if crew_role and len(message) > REPORT_MAX:
        full = path.with_name(path.stem + ".full.md")
        write_text(full, message)
        run = mtime(crew_dir(record["id"]) / ("%s.start" % bare))
        meta = member_meta(record["id"], bare)
        count = meta.get("sent_back") or [0, 0]
        sent = count[1] if count[0] == run else 0
        if sent < 2:
            update_meta(record["id"], bare, lambda m: m.update(sent_back=[run, sent + 1]))
            return out_deny(
                "Your report is %s characters, and a final report is held to %s so that a lead "
                "waiting on %d sub-agents can take them all in. Nothing is lost: the full text "
                "is saved at %s. Hand back a summary under the limit that names that file and "
                "your notes folder." % (format(len(message), ","), format(REPORT_MAX, ","),
                                        CREW_MAX, rel(full)))
    write_text(path, message)

    def change(meta):
        meta["report"] = rel(path)
        meta["handback_t"] = now()
    update_meta(record["id"], bare, change)
    return None


def on_post_tool(inp):
    """After an Agent call of the lead: the slot held for it is no longer needed (the agent
    started, or never will), and the new sub-agent's description is kept. The call's agentId
    is never used to make a running member: only SubagentStart does that."""
    if inp.get("tool_name") not in ("Agent", "Task") or inp.get("agent_id"):
        return None
    record = load_session(inp, create=False)
    if not record:
        return None
    token = clean(inp.get("tool_use_id"))
    if token:
        try:
            os.unlink(crew_dir(record["id"]) / ("%s.res" % token))
        except OSError:
            pass
    response = inp.get("tool_response")
    if not isinstance(response, dict) or not response.get("agentId"):
        return None
    tool_input = inp.get("tool_input") if isinstance(inp.get("tool_input"), dict) else {}
    bare = bare_id(response["agentId"])

    def change(meta):
        desc = tool_input.get("description") or response.get("description")
        if desc:
            meta["desc"] = str(desc)
        if tool_input.get("name"):
            meta["name"] = str(tool_input["name"])
        if response.get("resolvedModel"):
            meta["model"] = str(response["resolvedModel"])
    update_meta(record["id"], bare, change)
    return None


def on_subagent_start(inp):
    bare = bare_id(inp.get("agent_id"))
    if not bare:
        return None
    record = load_session(inp)
    kind = str(inp.get("agent_type") or "")
    t = now()
    record_start(record, bare, t)

    def change(meta):
        meta["runs"] = int(meta.get("runs", 0) or 0) + 1
        meta["type"] = kind or meta.get("type") or ""
        meta.setdefault("started", stamp(t))
        if inp.get("agent_transcript_path"):
            meta["transcript"] = str(inp["agent_transcript_path"])
    update_meta(record["id"], bare, change)
    text = (
        "SCBOT guard (installed by the user): you are a sub-agent, a crew member of session %s "
        "in the repo at %s. Your agent id is %s. What holds for every sub-agent here: you "
        "cannot start sub-agents. You have no AskUserQuestion tool, so a question for the user "
        "goes to your lead, who asks: send it with SendMessage to \"main\" and carry on with "
        "what does not depend on the answer, or put it at the top of your report if nothing "
        "else is left. Your context cap is %d%% of your window: the guard tells you at %d%% and "
        "%d%%, and at the cap reading and searching close while writing your handoff and "
        "reporting stay open." % (record["label"], ROOT.as_posix(), bare, CREW_LIMIT,
                                  CREW_HEADS_UP, CREW_WRAP))
    if kind in CREW_ROLES:
        text += (" A final report over %s characters is sent back with a request for a summary, "
                 "so keep detail in files and report their paths." % format(REPORT_MAX, ","))
    text += (" Unless your brief names a notes folder, use %s. Your final report is also saved "
             "at %s." % (rel(NOTES / ("agent-%s" % bare)) + "/", rel(report_path(record, bare))))
    return out_context("SubagentStart", text)


def on_subagent_stop(inp):
    bare = bare_id(inp.get("agent_id"))
    if not bare:
        return None
    record = load_session(inp, create=False)
    if not record:
        return None
    folder = crew_dir(record["id"])
    start = mtime(folder / ("%s.start" % bare))
    meta = member_meta(record["id"], bare)
    if not start and not meta:                 # one of Claude Code's own helper agents
        return None
    final = str(inp.get("last_assistant_message") or "")
    handed = float(meta.get("handback_t") or 0) >= start > 0
    saved = None
    if not handed and final:
        target = report_path(record, bare)
        sent = (meta.get("sent_back") or [0, 0])
        sent = sent[1] if sent[0] == start else 0
        if str(inp.get("agent_type") or meta.get("type") or "") in CREW_ROLES and \
                len(final) > REPORT_MAX and not inp.get("stop_hook_active") and sent < 2:
            full = target.with_name(target.stem + ".full.md")
            write_text(full, final)
            update_meta(record["id"], bare, lambda m: m.update(sent_back=[start, sent + 1]))
            return out_block(
                "Your final message is %s characters, and a final report is held to %s. The "
                "full text is saved at %s. End with a summary under the limit that names that "
                "file and your notes folder." % (format(len(final), ","),
                                                 format(REPORT_MAX, ","), rel(full)))
        if write_text(target, final):
            saved = rel(target)
    set_marker(folder / ("%s.stop" % bare), now(), "stopped")

    def change(m):
        if saved:
            m["report"] = saved
        m["stopped"] = stamp()
        if inp.get("agent_transcript_path"):
            m["transcript"] = str(inp["agent_transcript_path"])
    update_meta(record["id"], bare, change)
    return None


def on_pre_compact(inp):
    if str(inp.get("trigger") or "auto") != "auto":
        return None
    log("blocked an automatic compaction in session %s" % inp.get("session_id"))
    return out_block("Automatic compaction is switched off in this setup (the user's rule): a "
                     "session closes itself at its limit instead. A settings file has turned "
                     "it back on. Run `python tools/scbot.py check` to find which.")


def on_session_end(inp):
    record = load_session(inp, create=False)
    if record:
        record["ended"] = stamp()
        save_session(record)
        end_crew(record, "session ended")
    return None


HOOKS = {"SessionStart": on_session_start, "UserPromptSubmit": on_user_prompt,
         "PreToolUse": on_pre_tool, "PostToolUse": on_post_tool,
         "SubagentStart": on_subagent_start, "SubagentStop": on_subagent_stop,
         "PreCompact": on_pre_compact, "SessionEnd": on_session_end}


def run_hook(inp):
    """One hook call: the handler's decision plus any faults, said. Never raises."""
    global CALL
    event = str(inp.get("hook_event_name") or "")
    CALL = Call(clean(inp.get("session_id")), event, bare_id(inp.get("agent_id")) or "lead")
    result = None
    try:
        load_limits()
        handler = HOOKS.get(event)
        result = handler(inp) if handler else None
    except Exception as error:          # fail open: a guard fault must not stop the work
        import traceback
        where = traceback.extract_tb(error.__traceback__)[-1]
        fault("error", "%s: %s, at line %d" % (error.__class__.__name__, error, where.lineno))
        result = None
    try:
        return add_faults(event, result)
    except Exception as error:
        log("could not say a fault: %r" % (error,))
        return result
    finally:
        CALL = None


def cmd_hook(_args):
    if os.environ.get("SCBOT_GUARD", "").lower() == "off":
        return 0
    try:
        raw = sys.stdin.buffer.read()
        try:
            inp = json.loads(raw.decode("utf-8", "replace") or "{}")
        except ValueError:
            inp = None
        if isinstance(inp, dict):
            result = run_hook(inp)
        else:
            log("hook input is not a JSON object: %r" % raw[:80])
            result = None if warned_recently("", "input") else {
                "systemMessage": "SCBOT guard: " + FAULT_TEXT["input"].format(
                    detail="not a JSON object") + "."}
        if result:
            sys.stdout.buffer.write(json.dumps(result).encode("ascii"))
            sys.stdout.flush()
    except Exception as error:          # fail open
        log("hook error: %r" % (error,))
    return 0


# --------------------------------------------------------------------------------------------
# status, crew, meter, close, reopen

def option(args, name, default=None):
    if name in args:
        index = args.index(name)
        if index + 1 < len(args):
            return args[index + 1]
    return default


def resolve_session(name):
    """(record, error). A label is looked up among live sessions only, so a closed or stale
    session that once had it cannot be hit; any session is found by its id."""
    if not name:
        return None, "needs --session <label or session id>"
    records = all_sessions()
    by_id = [r for r in records if r.get("id") == name]
    if by_id:
        return by_id[0], None
    live = [r for r in records if r.get("label") == name and is_live(r)]
    if len(live) == 1:
        return live[0], None
    if len(live) > 1:
        return None, ("%s is held by %d live sessions (%s). Name one by its session id."
                      % (name, len(live), ", ".join(r["id"] for r in live)))
    old = [r for r in records if r.get("label") == name]
    if old:
        return None, ("no live session is %s now. Sessions that had that label: %s. Name one "
                      "by its session id." % (name, ", ".join(
                          "%s (%s)" % (r["id"], session_state(r)) for r in old)))
    return None, "no session %s is registered" % name


def session_state(record):
    if record.get("closed"):
        return "closed"
    if record.get("ended"):
        return "ended"
    if not is_live(record):
        return "stale"
    return "pending closing" if record.get("pending") else "live"


def member_rows(record):
    marks, reserved = crew_marks(record["id"])
    rows = []
    for bare in sorted(marks, key=lambda b: marks[b].get("start", 0)):
        if not marks[bare].get("start"):
            continue
        meta = member_meta(record["id"], bare)
        state = member_state(record, bare, marks[bare], meta)
        stop_text = ""
        if state == "done":
            try:
                stop_text = (crew_dir(record["id"]) / ("%s.stop" % bare)).read_text(
                    encoding="utf-8").strip()
            except OSError:
                pass
        last = max(marks[bare].get("start", 0), marks[bare].get("seen", 0),
                   mtime(member_transcript(record, bare, meta)) if member_transcript(
                       record, bare, meta) else 0)
        rows.append({"id": bare, "meta": meta, "state": state, "last": last, "why": stop_text})
    return rows, reserved


def cmd_status(args):
    label = option(args, "--session")
    records = sorted(all_sessions(), key=lambda r: r.get("seen_t", 0), reverse=True)
    if label:
        record, error = resolve_session(label)
        if not record:
            print(error)
            return 1
        records = [record]
    elif "--all" not in args:
        records = [r for r in records if session_state(r) in ("live", "pending closing")]
    if not records:
        print("no live SCBOT session is registered (use --all for ended ones)")
        return 0
    for record in records:
        m = measure(record.get("transcript"))
        running, reserved = crew_count(record)
        print("%s  %s  %s  context %s  running %d of %d  started %s%s" % (
            record["label"], record.get("id"), session_state(record), shown(m),
            len(running) + len(reserved), CREW_MAX, record.get("started", "?"),
            "  prompt %s" % record["prompt_file"] if record.get("prompt_file") else ""))
        if label:
            print_crew(record)
            if record.get("note"):
                print("  closing note: %s" % record["note"])
    return 0


def print_crew(record):
    rows, reserved = member_rows(record)
    for row in rows:
        meta = row["meta"]
        mm = measure_path(Path(member_transcript(record, row["id"], meta)), False) \
            if member_transcript(record, row["id"], meta) else None
        print("  %-12s %-16s %-8s last active %s  context %s  %s" % (
            row["id"][:12], meta.get("type") or "agent", row["state"],
            stamp(row["last"]) if row["last"] else "?", shown(mm),
            meta.get("report") or meta.get("desc") or row["why"] or ""))
    if reserved:
        print("  %d start(s) let through and not seen yet (each holds a slot for at most %d s)"
              % (len(reserved), RESERVE_TTL))
    if not rows and not reserved:
        print("  no sub-agents")


def cmd_crew(args):
    """crew --session L: the members and what each counts as. crew clear --session L ID|--all:
    mark a member that has really ended as stopped, for one whose stop was never seen."""
    record, error = resolve_session(option(args, "--session"))
    if not record:
        print("crew %s" % error)
        return 1
    if args and args[0] == "clear":
        rest = [a for a in args[1:] if not a.startswith("--") and a != option(args, "--session")]
        rows, reserved = member_rows(record)
        if "--all" in args:
            targets = [r["id"] for r in rows if r["state"] in ("running", "silent")]
            for _, path, _ in reserved:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        elif rest:
            want = bare_id(rest[0])
            targets = [r["id"] for r in rows if r["id"] == want or r["id"].startswith(want)
                       or r["meta"].get("name") == rest[0]]
            if len(targets) != 1:
                print("crew clear: %s matches %d members of %s. `crew --session %s` lists them."
                      % (rest[0], len(targets), record["label"], record["label"]))
                return 1
        else:
            print("crew clear needs a member id (or --all)")
            return 1
        last = {r["id"]: r["last"] for r in rows}
        recent = [b for b in targets if now() - last.get(b, 0) < RECENT]
        if recent and "--force" not in args:
            print("Nothing was cleared. %s %s active in the last %d minutes, so %s probably still "
                  "running. Wait, or pass --force (a cleared sub-agent that makes another tool "
                  "call counts again)." % (", ".join(crew_line(record, b) for b in recent),
                                           "was" if len(recent) == 1 else "were", RECENT // 60,
                                           "it is" if len(recent) == 1 else "they are"))
            return 1
        for bare in targets:
            set_marker(crew_dir(record["id"]) / ("%s.stop" % bare), now(), "cleared by hand")
            print("cleared: %s" % crew_line(record, bare))
        return 0
    running, reserved = crew_count(record)
    print("%s: %d of %d running" % (record["label"], len(running) + len(reserved), CREW_MAX))
    print_crew(record)
    return 0


def claude_dir(home=None):
    if home:
        return Path(home) / ".claude"
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        return Path(os.environ["CLAUDE_CONFIG_DIR"])
    return Path.home() / ".claude"


def project_folder(root, home=None):
    """Claude Code's transcript folder for a project: its path with every character that is
    not a letter or a digit turned into '-'. Matched without regard to case."""
    projects = claude_dir(home) / "projects"
    want = re.sub(r"[^A-Za-z0-9]", "-", str(Path(root)))
    if (projects / want).is_dir():
        return projects / want
    try:
        for entry in os.scandir(projects):
            if entry.is_dir() and entry.name.lower() == want.lower():
                return Path(entry.path)
    except OSError:
        pass
    return projects / want


def recent_transcripts(folder, hours):
    out = []
    try:
        for entry in os.scandir(folder):
            if entry.name.endswith(".jsonl") and now() - entry.stat().st_mtime < hours * 3600:
                out.append((entry.stat().st_mtime, Path(entry.path)))
    except OSError:
        pass
    return [p for _, p in sorted(out, reverse=True)]


def cmd_meter(args):
    """The context of the current session and of each of its sub-agents, in percent."""
    root = Path(option(args, "--root") or ROOT)
    folder = project_folder(root, option(args, "--home"))
    path = option(args, "--transcript")
    name = option(args, "--session")
    record = None
    if name:
        record, error = resolve_session(name)
        if record and record.get("transcript"):
            path = record["transcript"]
        elif (folder / ("%s.jsonl" % clean(name))).exists():
            path = str(folder / ("%s.jsonl" % clean(name)))
        else:
            print("meter: %s" % (error or "no transcript known for %s" % name))
            return 1
    if not path:
        for var in ("CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
            sid = clean(os.environ.get(var))
            if sid and (folder / ("%s.jsonl" % sid)).exists():
                path = str(folder / ("%s.jsonl" % sid))
                break
    if not path:
        newest = recent_transcripts(folder, 24 * 365)
        if not newest:
            print("meter: no transcript in %s" % folder)
            return 1
        path = str(newest[0])          # the session running this command wrote last
    path = Path(path)
    if record is None:
        record = read_json(session_dir(path.stem) / "session.json")
    label = record.get("label") if isinstance(record, dict) else None
    print("session %s%s: %s" % (path.stem, " (%s)" % label if label else "",
                                shown(measure_path(path, True))))
    sub = path.with_suffix("") / "subagents"
    window = 24 * 365 if "--all" in args else 24
    for agent in recent_transcripts(sub, window):
        bare = bare_id(agent.stem)
        kind = state = ""
        if isinstance(record, dict) and record.get("id"):
            meta = member_meta(record["id"], bare)
            kind = meta.get("type") or ""
            marks, _ = crew_marks(record["id"])
            if bare in marks:
                state = member_state(record, bare, marks[bare], meta)
        print("  sub-agent %-12s %-16s %-8s %s" % (bare[:12], kind or "-", state or "-",
                                                   shown(measure_path(agent, False))))
    return 0


def cmd_close(args):
    record, error = resolve_session(option(args, "--session"))
    if not record:
        print("close %s" % error)
        return 1
    running, reserved = crew_count(record)
    if (running or reserved) and "--force" not in args:
        print("%s still has %d sub-agent(s) running: %s" % (
            record["label"], len(running) + len(reserved),
            running_list(record, running, reserved)))
        print("Wait for them: each finishes on its own, and its report is saved under %s. %s"
              % (rel(REPORTS / record["label"]), clear_hint(record)))
        return 1
    note = option(args, "--note") or ""
    handed = []
    try:
        with Lock(QUEUE / ".lock"):
            for task in queue_tasks():
                if task["state"] == "claimed" and task.get("owner_id") == record["id"]:
                    task.update({"state": "open", "handover": note or "closed without a note",
                                 "owner": "", "owner_id": ""})
                    task_log(task, record["label"], "handed over at close")
                    save_task(task)
                    handed.append(task["id"])
    except LockBusy as busy:
        print("the queue is locked (%s); its tasks were not handed over" % busy)
    record["closed"] = stamp()
    record["note"] = note
    if not save_session(record):
        print("could not save the session record; it is not closed")
        return 1
    print("%s is closed. It takes no more prompts (reopen: python tools/scbot.py reopen "
          "--session %s)." % (record["label"], record["id"]))
    if handed:
        print("handed over: %s" % ", ".join(handed))
    return 0


def cmd_reopen(args):
    name = option(args, "--session") or ""
    record = next((r for r in all_sessions() if r.get("id") == name), None)
    if record is None:
        record, error = resolve_session(name)
        if not record:
            closed = [r for r in all_sessions() if r.get("label") == name and r.get("closed")]
            if len(closed) == 1:
                record = closed[0]
            else:
                print("reopen %s" % error)
                return 1
    for key in ("closed", "ended"):
        record.pop(key, None)
    record["seen_t"] = now()
    keep_label_unique(record)
    save_session(record)
    print("%s is open again. Pending closing follows its meter: it is pending again if its "
          "context is still past its line." % record["label"])
    return 0


# --------------------------------------------------------------------------------------------
# The work queue

TASK_ID = re.compile(r"T\d{3,6}$")


def queue_tasks():
    tasks = []
    if QUEUE.is_dir():
        for path in sorted(QUEUE.glob("T*.json")):
            task = read_json(path)
            if isinstance(task, dict) and TASK_ID.match(str(task.get("id", ""))):
                tasks.append(task)
    return tasks


def save_task(task):
    task["updated"] = stamp()
    write_json(QUEUE / ("%s.json" % task["id"]), task)


def task_log(task, who, what):
    task.setdefault("log", []).append("%s %s: %s" % (stamp(), who or "?", what))


def norm_files(path):
    """A file or pattern in a task's list, compared without case, './', backslashes or a
    trailing slash."""
    text = str(path).strip().replace("\\", "/").lower()
    while text.startswith("./"):
        text = text[2:]
    return re.sub(r"/+", "/", text).rstrip("/")


def overlap(a, b):
    from fnmatch import fnmatchcase
    for x in a:
        for y in b:
            xs, ys = norm_files(x), norm_files(y)
            xd = re.sub(r"(/\*\*?)+$", "", xs)          # dashboard/scdash/** -> dashboard/scdash
            yd = re.sub(r"(/\*\*?)+$", "", ys)
            if xs == ys or fnmatchcase(xs, ys) or fnmatchcase(ys, xs) \
                    or xs.startswith(yd + "/") or ys.startswith(xd + "/") or xd == yd:
                return "%s and %s" % (x, y)
    return None


def cmd_queue(args):
    if not args:
        args = ["list"]
    verb, rest = args[0], args[1:]
    who = option(rest, "--session", "")
    owner, owner_error = resolve_session(who) if who else (None, None)
    if verb == "list":
        tasks = queue_tasks()
        if "--all" not in rest:
            tasks = [t for t in tasks if t["state"] not in ("done", "dropped")]
        if not tasks:
            print("the queue is empty")
        for task in tasks:
            state = task["state"]
            if state == "open" and task.get("handover"):
                state = "handed-over"
            print("%s  %-11s %-9s %-8s %s" % (task["id"], state, task.get("role") or "-",
                                             task.get("owner") or "-", task["title"]))
        return 0
    if verb == "add":
        title = option(rest, "--title")
        if not title:
            print("queue add needs --title")
            return 1
        after = [a for a in (option(rest, "--after", "") or "").split(",") if a]
        bad = [a for a in after if not TASK_ID.match(a)]
        if bad:
            print("queue add: --after takes task ids like T001, not %s" % ", ".join(bad))
            return 1
        with Lock(QUEUE / ".lock"):
            numbers = [int(t["id"][1:]) for t in queue_tasks()]
            task = {"id": "T%03d" % (max(numbers, default=0) + 1), "title": title,
                    "role": option(rest, "--role", ""), "state": "open", "owner": "",
                    "owner_id": "",
                    "files": [f for f in (option(rest, "--files", "") or "").split(",") if f],
                    "brief": option(rest, "--brief", ""), "notes": option(rest, "--notes", ""),
                    "after": after, "created": stamp(), "log": []}
            task_log(task, who, "added")
            save_task(task)
        print("%s added. Brief file: %s" % (task["id"], task["brief"] or rel(
            QUEUE / ("%s.brief.md" % task["id"]))))
        return 0
    task_id = rest[0] if rest and not rest[0].startswith("--") else None
    if not task_id or not TASK_ID.match(task_id) or not (QUEUE / ("%s.json" % task_id)).exists():
        print("queue %s needs a task id that exists, like T001 (python tools/scbot.py queue list)"
              % verb)
        return 1
    path = QUEUE / ("%s.json" % task_id)
    if verb == "show":
        print(json.dumps(read_json(path), indent=1, ensure_ascii=False))
        return 0
    with Lock(QUEUE / ".lock"):
        task = read_json(path)
        if not isinstance(task, dict):
            print("%s cannot be read" % task_id)
            return 1
        holder_id = task.get("owner_id") or ""
        if verb in ("done", "drop", "handover") and task["state"] == "claimed" and \
                holder_id and (not owner or owner["id"] != holder_id):
            print("%s is claimed by %s. Only its holder marks it %s. If %s has really ended "
                  "without closing, take the task over first: python tools/scbot.py queue claim "
                  "%s --session <your label> --take" % (task_id, task.get("owner"), verb,
                                                        task.get("owner"), task_id))
            return 1
        if verb == "claim":
            if not owner:
                print("queue claim needs --session <your label>%s" % (
                    " (%s)" % owner_error if owner_error else ""))
                return 1
            if task["state"] == "claimed" and holder_id != owner["id"]:
                holder = next((r for r in all_sessions() if r.get("id") == holder_id), None)
                if holder and session_state(holder) in ("live", "pending closing") \
                        and "--take" not in rest:
                    print("%s is claimed by %s, which is %s. Not claimed. If %s has really "
                          "ended (it crashed or was closed without `close`), take it over with: "
                          "python tools/scbot.py queue claim %s --session %s --take"
                          % (task_id, task["owner"], session_state(holder), task["owner"],
                             task_id, owner["label"]))
                    return 1
            elif task["state"] not in ("open", "claimed"):
                print("%s is %s. Not claimed." % (task_id, task["state"]))
                return 1
            for other in queue_tasks():
                if other["id"] != task_id and other["state"] == "claimed" \
                        and other.get("owner_id") != owner["id"]:
                    clash = overlap(task.get("files", []), other.get("files", []))
                    if clash and "--force" not in rest:
                        print("%s touches files that %s (%s, %s) already holds: %s. "
                              "Not claimed." % (task_id, other["id"], other["owner"],
                                                other["title"], clash))
                        return 1
            waiting = [a for a in task.get("after", []) if not TASK_ID.match(a) or
                       (read_json(QUEUE / ("%s.json" % a)) or {}).get("state") != "done"]
            if waiting and "--force" not in rest:
                print("%s waits for %s. Not claimed." % (task_id, ", ".join(waiting)))
                return 1
            if holder_id and holder_id != owner["id"]:
                task_log(task, who, "taken over from %s" % task.get("owner"))
            task.update({"state": "claimed", "owner": owner["label"], "owner_id": owner["id"]})
            task_log(task, who, "claimed")
        elif verb == "note":
            task_log(task, who, " ".join(a for a in rest[1:] if a != "--session" and a != who))
        elif verb == "handover":
            task.update({"state": "open", "owner": "", "owner_id": "",
                         "handover": option(rest, "--notes", "") or "no notes named"})
            if option(rest, "--left"):
                task["left"] = option(rest, "--left")
            task_log(task, who, "handed over")
        elif verb == "block":
            task["state"] = "blocked"
            task["question"] = option(rest, "--question", "")
            task_log(task, who, "blocked: %s" % task["question"])
        elif verb == "unblock":
            task["state"] = "claimed" if task.get("owner") else "open"
            task_log(task, who, "unblocked")
        elif verb in ("done", "drop"):
            task["state"] = "done" if verb == "done" else "dropped"
            if option(rest, "--commit"):
                task["commit"] = option(rest, "--commit")
            task_log(task, who, verb)
        else:
            print("unknown queue command %s" % verb)
            return 1
        save_task(task)
    print("%s: %s" % (task_id, task["state"]))
    return 0


# --------------------------------------------------------------------------------------------
# install, uninstall, check
#
# The installer touches a settings file only through these rules: it refuses a file it cannot
# parse as strict JSON (comments included) and says why; it backs the file up before it writes;
# it adds only hook entries marked with HOOK_MARK and removes only those; it never rewrites a
# file where nothing of it is; it keeps the file's indent, line endings and byte order mark. It
# records what it is about to do in installed.json before doing it, so that an interrupted
# install can be undone by `uninstall`, and an untouched file is restored byte for byte.

def sha(path):
    import hashlib
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def sha_text(path):
    """A hash that ignores line endings: a copy checked out with CRLF is still current."""
    import hashlib
    try:
        return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


OLD_HOOK = re.compile(r"\.claude[/\\]scbot[/\\]bin[/\\]scbot\.py")


def is_our_hook(hook):
    """A hook entry this script installed: the launcher's mark, or the previous version's form,
    `python -S ${CLAUDE_PROJECT_DIR}/.claude/scbot/bin/scbot.py hook` (or any entry that runs the
    installed copy under .claude/scbot/bin/)."""
    if not isinstance(hook, dict):
        return False
    parts = [str(hook.get("command", ""))] + [str(a) for a in (hook.get("args") or [])]
    return any(HOOK_MARK in p or OLD_HOOK.search(p) for p in parts)


def install_record(path):
    """installed.json, in this version's form. The previous version kept {target: {"keys":
    {key: old value or null}, "env": {...}}} with no version: read as such, with no byte
    restore (its backups are not known), and null taken as "was not there"."""
    record = read_json(path, {}) or {}
    if not isinstance(record, dict):
        return {}
    if record.get("version") == 2:
        return record
    targets = {}
    for target, memo in record.items():
        if not isinstance(memo, dict):
            continue
        rec = {"keys": {}, "env": {}, "state": "installed", "existed": True,
               "byte_restore": False, "backup": "", "before_sha": None, "after_sha": None}
        for kind in ("keys", "env"):
            for name, old in (memo.get(kind) or {}).items():
                rec[kind][name] = {"had": old is not None, "value": old}
        targets[target] = rec
    return {"version": 2, "targets": targets, "migrated": True} if targets else {}


def hook_entry(python, script, timeout=10):
    return {"type": "command", "command": str(python),
            "args": ["-I", "-S", "-c", LAUNCHER, str(script)], "timeout": timeout}


def read_settings(path):
    """(object, style, raw bytes, error). A missing file is ({}, default style, None, None)."""
    path = Path(path)
    if path.is_dir():
        return None, None, None, "%s is a folder, not a file" % path
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}, ("\n", "  ", True, False), None, None
    except OSError as error:
        return None, None, None, "cannot read %s: %s" % (path, error)
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, None, raw, "%s is not UTF-8" % path
    if not text.strip():
        return {}, ("\n", "  ", True, bom), raw, None
    try:
        obj = json.loads(text)
    except ValueError as error:
        return None, None, raw, ("%s is not strict JSON (%s). Claude Code may read it, comments "
                                 "and all, but merging into it would lose what JSON cannot "
                                 "hold. Remove the comments or trailing commas, or add the "
                                 "entries by hand" % (path, error))
    if not isinstance(obj, dict):
        return None, None, raw, "%s holds a JSON %s, not an object" % (path, type(obj).__name__)
    for key, kind in (("hooks", dict), ("env", dict)):
        if key in obj and not isinstance(obj[key], kind):
            return None, None, raw, "%s: \"%s\" is not an object" % (path, key)
    for event, groups in (obj.get("hooks") or {}).items():
        if not isinstance(groups, list):
            return None, None, raw, "%s: hooks.%s is not a list" % (path, event)
    newline = "\r\n" if "\r\n" in text else "\n"
    found = re.search(r'^([ \t]+)"', text, re.M)
    return obj, (newline, found.group(1) if found else "  ", text.endswith("\n"), bom), raw, None


def dump_settings(obj, style):
    newline, indent, trailing, bom = style
    text = json.dumps(obj, indent=indent, ensure_ascii=False).replace("\n", newline)
    data = (text + (newline if trailing else "")).encode("utf-8")
    return (b"\xef\xbb\xbf" + data) if bom else data


def without_ours(obj):
    """A copy of a settings object with every hook entry marked as ours taken out. A group, an
    event or a hooks block that taking ours out leaves empty is dropped; one that was empty
    already is the user's and stays."""
    obj = json.loads(json.dumps(obj))
    hooks = obj.get("hooks")
    if not isinstance(hooks, dict):
        return obj
    took = False
    for event in list(hooks):
        groups, emptied = [], False
        for group in hooks[event]:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list) and \
                    any(is_our_hook(h) for h in group["hooks"]):
                group = dict(group, hooks=[h for h in group["hooks"] if not is_our_hook(h)])
                took = emptied = True
                if not group["hooks"]:
                    continue
            groups.append(group)
        if groups or not emptied:
            hooks[event] = groups
        else:
            del hooks[event]
    if took and not hooks:
        del obj["hooks"]
    return obj


def has_ours(obj):
    return json.dumps(without_ours(obj), sort_keys=True) != json.dumps(obj, sort_keys=True)


def merged(current, fragment, memo, python, script):
    """The settings with the fragment merged in. memo keeps, per key and env name, whether it
    was there before the first install and its value then."""
    obj = without_ours(current)
    for key, value in fragment.items():
        if key == "env":
            env = obj.setdefault("env", {})
            for name, val in value.items():
                memo["env"].setdefault(name, {"had": name in env, "value": env.get(name)})
                memo["env"][name]["set"] = val
                env[name] = val
        elif key == "hooks":
            hooks = obj.setdefault("hooks", {})
            for event, groups in value.items():
                for group in groups:
                    ours = dict((k, v) for k, v in group.items() if k != "hooks")
                    ours["hooks"] = [hook_entry(python, script, h.get("timeout", 10))
                                     for h in group.get("hooks", [])]
                    hooks.setdefault(event, []).append(ours)
        elif not key.startswith("_"):
            memo["keys"].setdefault(key, {"had": key in obj, "value": obj.get(key)})
            memo["keys"][key]["set"] = value
            obj[key] = value
    return obj


def install_paths(args):
    root = Path(option(args, "--root") or ROOT)
    home = Path(option(args, "--home") or Path.home())
    source = Path(__file__).resolve().parents[1]
    return root, home, source


def python_runs(python):
    import subprocess
    try:
        run = subprocess.run([str(python), "-I", "-S", "-c", "import sys;print(sys.version_info[0])"],
                             capture_output=True, timeout=20)
        return run.returncode == 0 and run.stdout.strip() == b"3"
    except Exception:              # not found, not runnable, refused arguments: not Python 3
        return False


def lines_crossed(root, home):
    """Sessions of this repo that the guard would hold at once: leads whose transcript was
    written in the last day and is at or past the lead's line, and sub-agents active within
    SILENT at or past their cap."""
    found = []
    for path in recent_transcripts(project_folder(root, home), LIVE_HOURS):
        m = measure_path(path, True)
        if m and "pct" in m and m["pct"] >= LEAD_LIMIT:
            found.append("session %s at %s: it would be pending closing at its next tool call"
                         % (path.stem, figure(m)))
        for agent in recent_transcripts(path.with_suffix("") / "subagents", SILENT / 3600.0):
            mm = measure_path(agent, False)
            if mm and "pct" in mm and mm["pct"] >= CREW_LIMIT:
                found.append("sub-agent %s of session %s at %s: reading would close for it"
                             % (agent.stem, path.stem, figure(mm)))
    return found


def cmd_install(args):
    root, home, source = install_paths(args)
    if not (source / "prompts" / "settings").is_dir():
        print("run install from the repo's own copy: python tools/scbot.py install")
        return 1
    scope = option(args, "--scope", "project")
    dry = "--dry-run" in args
    base = root / ".claude" / "scbot"
    python = Path(option(args, "--python") or sys.executable)
    try:
        python = python.resolve()
    except OSError:
        pass
    script = Path(os.path.abspath(base / "bin" / "scbot.py"))
    if not python_runs(python):
        print("refused: %s does not run as Python 3 with -I -S. Pass --python <path>." % python)
        return 1
    plan = []
    if scope in ("project", "all"):
        plan.append((root / ".claude" / "settings.json", "project"))
    if scope in ("user", "all"):
        plan.append((home / ".claude" / "settings.json", "user"))
    if not plan:
        print("--scope is project, user or all")
        return 1
    record_path = base / "installed.json"
    record = install_record(record_path)
    if record.pop("migrated", None):
        print("found an install by the previous version: its hooks are replaced by this one's")
    record.update(version=2, python=str(python), script=str(script))
    targets = record.setdefault("targets", {})
    work = []
    for target, label in plan:                  # every check before any write
        current, style, raw, error = read_settings(target)
        if error:
            print("refused: %s. Nothing was changed." % error)
            return 1
        fragment = read_json(source / "prompts" / "settings" / ("scbot.%s-settings.json" % label))
        if not isinstance(fragment, dict):
            print("refused: the settings fragment for %s cannot be read" % label)
            return 1
        rec = targets.get(str(target)) or {"keys": {}, "env": {}}
        rec = json.loads(json.dumps(rec))
        new = merged(current, fragment, rec, python, script)
        work.append((target, label, current, style, raw, new, rec))
    crossed = lines_crossed(root, home)
    if crossed:
        print("Installing would hold these at once:")
        for line in crossed:
            print("  " + line)
        if not dry and "--yes" not in args:
            print("refused: pass --yes to install anyway, or install when they have closed.")
            return 1
    if dry:
        for target, _, _, style, _, new, _ in work:
            print("--- %s would be:" % target)
            print(dump_settings(new, style).decode("utf-8"))
        print("would copy %s -> %s" % (source / "tools" / "scbot.py", script))
        return 0
    import hashlib
    if scope in ("project", "all"):
        # The script first, so that the hooks never point at a file that is not there yet.
        copies = [(source / "tools" / "scbot.py", base / "bin" / "scbot.py")]
        copies += [(p, root / ".claude" / "agents" / p.name)
                   for p in sorted((source / "prompts" / "agents").glob("scbot-*.md"))]
        record["copies"] = sorted(set(record.get("copies", [])) | {str(d) for _, d in copies})
        if not write_json(record_path, record):
            print("refused: cannot write %s" % record_path)
            return 1
        for src, dst in copies:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            print("copied: %s" % dst)
    for target, label, current, style, raw, new, rec in work:
        data = dump_settings(new, style)
        old = targets.get(str(target))
        if raw is not None and data == raw:
            print("same:   %s" % target)
            if not old:            # ours already there with no record: never restore by bytes
                rec.update(state="installed", existed=True, byte_restore=False,
                           after_sha=sha(target), before_sha=None, backup="")
            targets[str(target)] = rec
            continue
        if old and old.get("state") == "installed" and old.get("after_sha") != sha(target):
            rec["byte_restore"] = False       # edited since our last write: restore surgically
        stamp_now = time.strftime("%Y%m%d-%H%M%S")
        if not old:
            # A file that already holds entries of ours (the previous version's form) must
            # never get those bytes back: they would run a script that is gone.
            rec.update(existed=raw is not None, byte_restore=not has_ours(current), backup="",
                       before_sha=hashlib.sha256(raw).hexdigest() if raw is not None else None)
        if raw is not None:                    # always a backup before a write
            backup = target.with_name("%s.scbot-backup-%s" % (target.name, stamp_now))
            backup.write_bytes(raw)
            print("backup: %s" % backup)
            if not old:
                rec["backup"] = str(backup)
        rec.update(state="installing", after_sha=hashlib.sha256(data).hexdigest())
        targets[str(target)] = rec
        if not write_json(record_path, record):        # the record first, then the file
            print("refused: cannot write %s" % record_path)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        if not write_bytes(target, data):
            print("failed: could not write %s; `uninstall` undoes what was done" % target)
            return 1
        rec["state"] = "installed"
        write_json(record_path, record)
        print("wrote:  %s" % target)
    write_json(record_path, record)
    print("done. New sessions pick this up when they start; a running session picks up the "
          "hooks at once and the environment values at its next start. Run "
          "`python tools/scbot.py check`.")
    return 0


def restore_value(holder, name, memo):
    """Put a key or env value back as it was before the install, unless it was changed by hand
    since (then it is left as the user set it)."""
    if "set" in memo and name in holder and holder[name] != memo["set"]:
        return "kept %s (changed since the install)" % name
    if memo.get("had"):
        holder[name] = memo.get("value")
    else:
        holder.pop(name, None)
    return None


def cmd_uninstall(args):
    root, home, _source = install_paths(args)
    scope = option(args, "--scope", "all")
    base = root / ".claude" / "scbot"
    record_path = base / "installed.json"
    record = install_record(record_path)
    record.pop("migrated", None)
    targets = record.get("targets", {})
    paths = []
    if scope in ("project", "all"):
        paths.append(root / ".claude" / "settings.json")
    if scope in ("user", "all"):
        paths.append(home / ".claude" / "settings.json")
    failed = False
    for target in paths:
        rec = targets.get(str(target))
        current, style, raw, error = read_settings(target)
        if error:
            print("left alone: %s" % error)
            failed = True
            continue
        if not rec and not has_ours(current):
            print("nothing installed: %s (not touched)" % target)
            continue
        now_sha = sha(target) if raw is not None else None
        targets.pop(str(target), None)
        if rec and rec.get("state") == "installing" and now_sha == rec.get("before_sha"):
            print("unchanged (the install stopped before writing it): %s" % target)
            continue
        if rec and rec.get("byte_restore") and now_sha == rec.get("after_sha"):
            # Untouched since the install wrote it: put the old bytes back exactly.
            if not rec.get("existed"):
                target.unlink()
                print("removed (it did not exist before the install): %s" % target)
                continue
            if rec.get("backup") and sha(rec["backup"]) == rec.get("before_sha"):
                write_bytes(target, Path(rec["backup"]).read_bytes())
                print("restored byte for byte: %s" % target)
                continue
        # Edited since, or no usable backup: take out only what the install put in.
        obj = without_ours(current)
        notes = []
        for name, memo in (rec or {}).get("env", {}).items():
            env = obj.setdefault("env", {})
            notes.append(restore_value(env, name, memo))
            if not env:
                del obj["env"]
        for key, memo in (rec or {}).get("keys", {}).items():
            notes.append(restore_value(obj, key, memo))
        data = dump_settings(obj, style)
        if data != raw:
            backup = target.with_name("%s.scbot-uninstall-%s" % (
                target.name, time.strftime("%Y%m%d-%H%M%S")))
            backup.write_bytes(raw)
            write_bytes(target, data)
            print("cleaned: %s (backup %s)" % (target, backup.name))
        for text in filter(None, notes):
            print("  " + text)
        if not rec:
            print("  no install record for it: only the guard's hooks were taken out")
    if scope in ("project", "all"):
        listed = record.get("copies") or [str(base / "bin" / "scbot.py")] + [
            str(p) for p in sorted((root / ".claude" / "agents").glob("scbot-*.md"))]
        for name in listed:
            path = Path(name)
            if path.exists():
                path.unlink()
                print("removed: %s" % path)
        record["copies"] = []
        cache = base / "bin" / "__pycache__"
        if cache.is_dir():
            import shutil
            shutil.rmtree(cache, ignore_errors=True)
    if record:
        if targets or record.get("copies"):
            record["targets"] = targets
            write_json(record_path, record)
        else:
            try:
                record_path.unlink()
            except OSError:
                pass
    print("done. The queue, notes and reports under %s are left in place." % base)
    return 1 if failed else 0


def cmd_check(args):
    import subprocess
    root, home, source = install_paths(args)
    base = root / ".claude" / "scbot"
    ok = True

    def line(good, text):
        nonlocal ok
        ok = ok and good
        print("%s  %s" % ("PASS" if good else "FAIL", text))

    line(sha_text(base / "bin" / "scbot.py") == sha_text(source / "tools" / "scbot.py"),
         "installed guard matches tools/scbot.py")
    for src in sorted((source / "prompts" / "agents").glob("scbot-*.md")):
        line(sha_text(root / ".claude" / "agents" / src.name) == sha_text(src),
             "sub-agent definition %s is installed and current" % src.name)
    files = {"project local": root / ".claude" / "settings.local.json",
             "project": root / ".claude" / "settings.json",
             "user": home / ".claude" / "settings.json"}
    settings = {}
    for label, path in files.items():
        obj, _, _, error = read_settings(path)
        if error:
            line(False, "%s settings: %s" % (label, error))
            obj = {}
        settings[label] = obj
    ran = set()
    for label in ("project", "user"):
        wanted = read_json(source / "prompts" / "settings" / (
            "scbot.%s-settings.json" % label), {}) or {}
        for event in wanted.get("hooks", {}):
            ours = [h for g in settings[label].get("hooks", {}).get(event, [])
                    if isinstance(g, dict) for h in g.get("hooks", []) if is_our_hook(h)]
            line(bool(ours), "%s settings run the guard on %s" % (label, event))
            for hook in ours:
                command = [hook.get("command", "")] + list(hook.get("args") or [])
                if json.dumps(command) in ran:
                    continue
                ran.add(json.dumps(command))
                line(python_runs(hook.get("command", "")),
                     "the hooks' interpreter runs: %s" % hook.get("command"))
                try:
                    run = subprocess.run(command, input=b'{"hook_event_name": "ScbotCheck"}',
                                         capture_output=True, timeout=20)
                    good = run.returncode == 0
                except Exception:
                    good = False
                line(good, "the hook command, as written in the settings, runs and exits 0")
                script = Path(command[-1]) if command else None
                line(bool(script) and script.is_file(),
                     "the hook names the installed script: %s" % script)
        for name, value in wanted.get("env", {}).items():
            line(settings[label].get("env", {}).get(name) == value,
                 "%s settings env %s = %s" % (label, name, value))
        for key, value in wanted.items():
            if key not in ("env", "hooks") and not key.startswith("_"):
                line(settings[label].get(key) == value, "%s settings %s = %s" % (
                    label, key, json.dumps(value)))
    for label, obj in settings.items():
        for key in ("autoCompactEnabled", "idleCompaction"):
            if obj.get(key) is True:
                line(False, "%s settings turn %s back on" % (label, key))
        if str((obj.get("env") or {}).get("DISABLE_AUTO_COMPACT", "")) == "0":
            line(False, "%s settings set DISABLE_AUTO_COMPACT to 0" % label)
        if obj.get("disableAllHooks"):
            line(False, "%s settings set disableAllHooks, so the guard does not run" % label)
    print("")
    print("values that can be set (environment of this command, then the default):")
    for name, default, what in SETTINGS:
        current = os.environ.get(name)
        for label in ("project local", "project", "user"):
            value = (settings[label].get("env") or {}).get(name)
            if value is not None and current is None:
                current = "%s (%s settings)" % (value, label)
        print("  %-32s default %-8s now %-24s %s" % (
            name, default if default != "" else "-", current if current is not None else "-",
            what))
    print("  derived: %s" % DERIVED)
    print("all good" if ok else "not fully installed: see the FAIL lines")
    return 0 if ok else 1


USAGE = """usage: python tools/scbot.py <command>

  status [--session LABEL] [--all]      sessions, and one session's crew with context use
  meter [--session LABEL|ID] [--transcript PATH] [--all]
                                        the context of this session and of each sub-agent, in %
  crew --session LABEL                  a session's sub-agents and whether each counts as running
  crew clear --session LABEL ID|--all [--force]
                                        free the slot of a sub-agent that has really ended (one
                                        active in the last 5 minutes only with --force)
  queue list [--all]                    the work queue
  queue add --title T [--role architect|worker] [--files a,b] [--after T001] [--session L]
  queue show|claim|note|handover|block|unblock|done|drop <id> [--session L] ...
  close --session LABEL --note "TEXT"   close a session (TEXT is the closing note itself, a
                                        line or two) and hand over its claimed tasks
  reopen --session LABEL|ID
  install [--scope project|user|all] [--dry-run] [--yes] [--python PATH]
                                        see prompts/SCBOT-README.md first
  uninstall [--scope project|user|all]
  check                                 is everything installed and current; every setting
  hook                                  (called by Claude Code, JSON on stdin)
"""


def main(argv):
    commands = {"hook": cmd_hook, "status": cmd_status, "meter": cmd_meter, "crew": cmd_crew,
                "queue": cmd_queue, "close": cmd_close, "reopen": cmd_reopen,
                "install": cmd_install, "uninstall": cmd_uninstall, "check": cmd_check}
    if len(argv) < 2 or argv[1] != "hook":
        # A path the console cannot print (a piped console on Windows takes the ANSI code page)
        # must not stop a command half way: print it escaped instead.
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(errors="backslashreplace")
            except (AttributeError, ValueError, OSError):
                pass
    if len(argv) < 2 or argv[1] not in commands:
        print(USAGE)
        return 0 if len(argv) < 2 else 1
    if argv[1] != "hook":
        load_limits()
    return commands[argv[1]](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
