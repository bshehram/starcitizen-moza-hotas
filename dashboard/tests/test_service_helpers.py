"""Helpers for the service, server, command-line and replay tests (no tests of its own).

Nothing here touches the real dashboard/data/, the real port or the real Game.log: every test
instance gets a temporary data folder, a free port, a log of its own, and a process name to
watch that no real program has."""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import scdash_testlib as lib
from scdash import config, service, winutil

REPO = lib.DASHBOARD.parent
SCRIPT = lib.DASHBOARD / "scdash.py"
RUN_A = lib.sample_path("run_a.log")          # the afternoon of 2026-11-26, sanitized


def free_port():
    """A port nothing listens on now (never the live or replay default)."""
    for _ in range(20):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        if port not in (config.PORT, config.REPLAY_PORT):
            return port
    raise RuntimeError("no free port")


def wait_until(fn, timeout=10.0, step=0.05):
    end = time.monotonic() + timeout
    while True:
        v = fn()
        if v or time.monotonic() >= end:
            return v
        time.sleep(step)


def raw_request(port, data, timeout=5.0):
    """Send raw bytes, return (status, {header: value}, body bytes). Gives up after `timeout`
    seconds in all, so a server that keeps a connection open (an event stream) cannot hang a test."""
    end = time.monotonic() + timeout
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(data)
        chunks = []
        while True:
            left = end - time.monotonic()
            if left <= 0:
                break
            s.settimeout(left)
            try:
                b = s.recv(65536)
            except (socket.timeout, ConnectionResetError, ConnectionAbortedError):
                break
            if not b:
                break
            chunks.append(b)
    raw = b"".join(chunks)
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split()[1]) if lines and len(lines[0].split()) > 1 else 0
    headers = {}
    for ln in lines[1:]:
        k, _, v = ln.partition(":")
        headers[k.strip().lower()] = v.strip()
    return status, headers, body


def request(port, method, path, headers=None, body=None, host=None):
    """Build and send one HTTP/1.0 request. `host=False` sends no Host header."""
    hdr = {} if headers is None else dict(headers)
    if host is None:
        host = "127.0.0.1:%d" % port
    lines = ["%s %s HTTP/1.0" % (method, path)]
    if host is not False:
        lines.append("Host: %s" % host)
    data = b""
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        hdr.setdefault("Content-Length", str(len(data)))
    for k, v in hdr.items():
        lines.append("%s: %s" % (k, v))
    return raw_request(port, ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + data)


def cli(*args, timeout=60):
    """Run `python dashboard/scdash.py <args>` from the repo root."""
    env = dict(os.environ)
    env.pop(config.LIVE_ENV, None)
    p = subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in args], cwd=str(REPO),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env=env)
    return p


def log_bytes(fraction=1.0):
    """run_a.log cut at a line boundary near `fraction` of its length."""
    data = RUN_A.read_bytes()
    if fraction >= 1.0:
        return data
    cut = data.rfind(b"\n", 0, int(len(data) * fraction)) + 1
    return data[:cut]


def without_quit(data):
    """The log with its quit line (and what follows it) removed: a crash."""
    at = data.find(b"<SystemQuit>")
    if at < 0:
        return data
    return data[:data.rfind(b"\n", 0, at) + 1]


class FakeGame:
    """A harmless stand-in for the game's process: a copy of a small system program under a name
    nothing else uses, so the service's process check finds it by name."""

    def __init__(self, folder):
        self.name = "scdashfake%s.exe" % uuid.uuid4().hex[:8]
        self.folder = Path(folder)
        self.proc = None

    def start(self):
        if winutil.IS_WINDOWS:
            src = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "PING.EXE"
            exe = self.folder / self.name
            shutil.copyfile(src, exe)
            self.proc = subprocess.Popen([str(exe), "-n", "3600", "127.0.0.1"], stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            self.name = self.name[:15].replace(".exe", "")
            exe = self.folder / self.name
            shutil.copyfile(shutil.which("sleep"), exe)
            os.chmod(exe, 0o755)
            self.proc = subprocess.Popen([str(exe), "3600"])
        wait_until(lambda: winutil.process_running(self.name), 10)
        return self

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(10)
        wait_until(lambda: not winutil.process_running(self.name), 10)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def end_instance(data_dir):
    """Clean-up: stop whatever instance belongs to this data folder, by request, then by force."""
    paths = service.Paths(data_dir)
    run = service.read_json(paths.run)
    if service.valid_run(run):
        info = service.instance_info(paths)
        if info["healthy"]:
            try:
                service.ask_to_stop(info, "test clean-up")
            except Exception:                          # noqa: BLE001
                pass
            wait_until(lambda: not paths.lock().held_elsewhere(), 10)
        kill_pid(run["pid"], run.get("created"))
    wait_until(lambda: not paths.lock().held_elsewhere(), 10)


def kill_pid(pid, created):
    """End one of our own test instances, by force (tests only: nothing in scdash ends a process).
    Only a Python process created at the time its run.json recorded: after a pid reuse that id can
    belong to an unrelated program."""
    if not isinstance(created, (int, float)) or not service.run_process_alive({"pid": pid, "created": created}):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    wait_until(lambda: winutil.process_name(pid) is None, 10)


def kill_instance(data_dir):
    """Kill the instance whose run.json is in this data folder (the crash a test needs)."""
    run = service.read_json(service.Paths(data_dir).run)
    kill_pid(run["pid"], run.get("created"))
    return run["pid"]


def remove_tree(path, seconds=15.0):
    """Remove a folder, retrying while a process that is ending still holds a file in it."""
    end = time.monotonic() + seconds
    while True:
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path) or time.monotonic() >= end:
            return not os.path.exists(path)
        time.sleep(0.2)


class Instance:
    """A temporary data folder and a log for one test instance; cleans up after itself."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="scdash-test-"))
        self.data = self.dir / "data"
        self.log = self.dir / "Game.log"
        self.port = free_port()

    def write_log(self, data, mode="wb"):
        with open(self.log, mode) as f:
            f.write(data)

    def args(self, *extra, process=None):
        out = ["--data", self.data, "--port", self.port, "--log", self.log]
        if process:
            out += ["--process", process]
        return out + list(extra)

    def cleanup(self):
        try:
            end_instance(self.data)
        finally:
            if not remove_tree(self.dir):
                raise AssertionError("could not remove %s" % self.dir)


def state(port):
    status, raw = service.http_call(port, "GET", "/api/state")
    return json.loads(raw.decode("utf-8")) if status == 200 else None


def status(port):
    st, raw = service.http_call(port, "GET", "/api/status")
    return json.loads(raw.decode("utf-8")) if st == 200 else None
