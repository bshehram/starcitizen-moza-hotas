"""One request path, forever (PLAN §8, §12 stage 6). The game's program file names 12 other
local gRPC paths besides the stream (an editor query engine and a bridge with pause and resume
commands) and 5.0 test builds add methods that make the game act; the dashboard must never be
able to call any of them.

The guarantee is structural, and this file tests each layer:

1. **The choke point** (runtime): every byte the client sends passes `GrpcStream._write()`,
   which refuses any HEADERS frame but the one built at import from STREAM_PATH, any second
   request, and any frame type the client has no reason to send. The socket is private.
2. **The source** (static, every non-test file under dashboard/): no gRPC path but STREAM_PATH,
   no other service or method name, only telemetry.py imports the client, no function in the
   telemetry files takes a path, host, method or endpoint, the client has one socket write and
   one connect, and nothing reaches into the private socket.
3. **The wire** (runtime): every path any fake server in the run was asked for.

Each of the three mutations the stage 6 review got past the first version is tested: a path
parameter named `endpoint`, a second module sending its own HEADERS on the stream's socket, and
a fallback path built by string concatenation and sent after a few trailers-only answers.
"""
import ast
import inspect
import re
import socket
import time
import unittest

import scdash_testlib as lib
import test_telemetry_fake as fake

from scdash import telemetry as tm
from scdash import telemetry_h2 as h2
from scdash import telemetry_proto as proto

DASH = lib.DASHBOARD
TELEMETRY = sorted((DASH / "scdash").glob("telemetry*.py"))
GRPC_PATH = re.compile(r"(?<![/\w:])/[A-Za-z_][\w.]*\.[A-Za-z_]\w*/\w+")   # not inside a //URL
OTHER_NAMES = ("TriggerGameAction", "ListTriggerableActions", "TriggerableAction",
               "VqlEngineService", "MightyBridgeService", "MightyStream")
FORBIDDEN_PARAMS = {"path", "host", "hostname", "address", "addr", "method", "rpc", "url", "uri",
                    "authority", "service", "endpoint", "target", "request_path", "headers",
                    "header_block", "block"}
OTHER_PATH = "/sc.game.telemetry.v1.GameTelemetryService/" + "Trigger" + "GameAction"


def scope():
    """Every non-test file under dashboard/ that could hold code: Python, the page's script and
    markup. tests/ is the fake server's side and data/ is the user's (git-ignored)."""
    for p in sorted(DASH.rglob("*")):
        rel = p.relative_to(DASH)
        if not p.is_file() or rel.parts[0] in ("tests", "data") or "__pycache__" in rel.parts:
            continue
        if p.suffix in (".py", ".js", ".html", ".htm", ".mjs"):
            yield p


def py_strings(text):
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


# --------------------------------------------------------------------------- the checkers

def foreign_paths(text, suffix=".py"):
    """gRPC-shaped paths other than STREAM_PATH, and other service or method names. For
    Python, in string literals (what code can send); for the page, anywhere in the text."""
    strings = list(py_strings(text)) if suffix == ".py" else [text]
    bad = []
    for s in strings:
        bad += [m for m in GRPC_PATH.findall(s) if m != h2.STREAM_PATH]
        bad += [n for n in OTHER_NAMES if n in s]
    return bad


def forbidden_params(text):
    bad = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = node.args
            names = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
            names |= {x.arg for x in (a.vararg, a.kwarg) if x}
            bad += sorted(names & FORBIDDEN_PARAMS)
    return bad


def imports_client(text):
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import) and any("telemetry_h2" in a.name for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom):
            if "telemetry_h2" in (node.module or "") or any(a.name == "telemetry_h2" for a in node.names):
                return True
    return False


def reaches_private_socket(text):
    return "GrpcStream__" in text or re.search(r"\.__sock\b", text) is not None


def socket_calls(text):
    """(socket writes, socket connects) in a source: sendall/send/sendto calls, and connect
    calls with an address argument (GrpcStream's own .connect() takes none)."""
    writes = connects = 0
    for n in ast.walk(ast.parse(text)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr in ("sendall", "send", "sendto", "sendmsg", "write") and "sock" in ast.unparse(n.func.value):
                writes += 1
            if n.func.attr in ("connect", "connect_ex", "create_connection") and (n.args or n.keywords):
                connects += 1
    return writes, connects


def bad_paths(paths):
    return sorted({p for p in paths if p != h2.STREAM_PATH})


# --------------------------------------------------------------------------- the source

class SourceTest(unittest.TestCase):
    def test_the_constant(self):
        self.assertEqual(h2.STREAM_PATH, "/%s/%s" % (proto.SERVICE, proto.METHOD))
        self.assertEqual(h2.STREAM_PATH, "/sc.game.telemetry.v1.GameTelemetryService/TelemetryStream")
        self.assertIs(tm.STREAM_PATH, h2.STREAM_PATH)
        self.assertEqual(h2.LOOPBACK, "127.0.0.1")
        self.assertEqual(h2.path_in_block(h2._PATH_BLOCK + h2._TAIL_BLOCK), h2.STREAM_PATH)

    def test_no_other_path_or_name_anywhere_in_the_dashboard(self):
        files = list(scope())
        self.assertTrue(any(p.name == "telemetry_h2.py" for p in files))
        literal = 0
        for p in files:
            text = p.read_text(encoding="utf-8")
            self.assertEqual(foreign_paths(text, p.suffix), [], p.relative_to(DASH))
            if p.suffix == ".py":
                literal += sum(s == h2.STREAM_PATH for s in py_strings(text))
            elif h2.STREAM_PATH in text:
                literal += 1
        self.assertEqual(literal, 1, "STREAM_PATH must be written out exactly once, in telemetry_h2.py")

    def test_only_telemetry_py_imports_the_client(self):
        for p in scope():
            if p.suffix == ".py" and p.name != "telemetry.py":
                self.assertFalse(imports_client(p.read_text(encoding="utf-8")), p.relative_to(DASH))

    def test_nothing_reaches_into_the_private_socket(self):
        for p in scope():
            if p.name != "telemetry_h2.py":
                self.assertFalse(reaches_private_socket(p.read_text(encoding="utf-8")), p.relative_to(DASH))

    def test_no_telemetry_function_takes_a_path_host_or_method(self):
        for p in TELEMETRY:
            self.assertEqual(forbidden_params(p.read_text(encoding="utf-8")), [], p.name)
        self.assertEqual(list(inspect.signature(h2.request_headers).parameters), ["port"])

    def test_one_socket_write_and_one_connect(self):
        for p in TELEMETRY:
            writes, connects = socket_calls(p.read_text(encoding="utf-8"))
            if p.name == "telemetry_h2.py":
                self.assertEqual((writes, connects), (1, 1), "one write, in _write; one connect")
            else:
                self.assertEqual((writes, connects), (0, 0), p.name)
        # Read from the file, not the live class: the test helpers wrap connect() with a guard.
        tree = ast.parse((DASH / "scdash" / "telemetry_h2.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GrpcStream")
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        self.assertIn("_check_outgoing", ast.unparse(methods["_write"]))
        target = next(n for n in ast.walk(methods["connect"]) if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Attribute) and n.func.attr == "connect" and n.args)
        self.assertEqual(ast.unparse(target.args[0].elts[0]), "LOOPBACK")
        sends = [n for n in ast.walk(cls) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "sendall"]
        self.assertEqual(len(sends), 1)
        self.assertTrue(any(s is sends[0] for s in ast.walk(methods["_write"])))


class MutationTest(unittest.TestCase):
    """The three mutations that got past the first version, each caught."""

    def setUp(self):
        self.h2_text = (DASH / "scdash" / "telemetry_h2.py").read_text(encoding="utf-8")

    def test_a_path_parameter_named_endpoint(self):
        mutated = self.h2_text + "\n\ndef call_other(port, endpoint):\n    return endpoint\n"
        self.assertEqual(forbidden_params(mutated), ["endpoint"])

    def test_a_second_module_sending_its_own_headers(self):
        # Statically: the import and the reach into the socket are both flagged ...
        other = ("from scdash import telemetry_h2 as h2\n"
                 "def go(stream, block):\n"
                 "    stream._GrpcStream__sock.sendall(h2.frame(h2.HEADERS, 4, 3, block))\n")
        self.assertTrue(imports_client(other))
        self.assertTrue(reaches_private_socket(other))
        self.assertTrue(imports_client("from .telemetry_h2 import GrpcStream\n"))
        # ... and at run time there is no `sock` to use, and _write refuses the frame.
        with fake.FakeServer([fake.snapshot(fake.make_schema())], record_global=False) as srv:
            s = h2.GrpcStream(srv.port, read_timeout=0.2)
            try:
                self.assertFalse(hasattr(s, "sock"))
                block = h2.request_headers(srv.port).replace(
                    h2.STREAM_PATH.encode(), OTHER_PATH.encode()[:len(h2.STREAM_PATH)])
                for bad in (h2.frame(h2.HEADERS, h2.F_END_HEADERS, 3, block),
                            h2.frame(h2.HEADERS, h2.F_END_HEADERS, 1, h2.request_headers(srv.port)),
                            h2.frame(h2.DATA, h2.F_END_STREAM, 1, b"\0\0\0\0\0"),
                            h2.frame(h2.RST_STREAM, 0, 1, b"\0\0\0\0"),
                            h2.frame(h2.PING, 0, 0, b"\0" * 8),
                            h2.frame(h2.GOAWAY, 0, 0, b"\0" * 8)):
                    with self.assertRaises(h2.SendRefused):
                        s._write(bad)
            finally:
                s.close()
            time.sleep(0.2)
        self.assertEqual(srv.paths, [h2.STREAM_PATH])

    def test_a_concatenated_fallback_path_cannot_be_sent(self):
        schema = fake.make_schema()
        # The mutation's way in: whatever builds the request now builds another path.
        real_headers, real_path = h2.request_headers, h2.STREAM_PATH
        with fake.FakeServer([fake.snapshot(schema)], record_global=False) as srv:
            try:
                h2.request_headers = lambda port: (h2._PATH_BLOCK.replace(real_path.encode(), b"")[:-1]
                                                   + h2.hpack_str(OTHER_PATH) + h2._authority(port)
                                                   + h2._TAIL_BLOCK)
                with self.assertRaises(h2.SendRefused):
                    h2.GrpcStream(srv.port)
            finally:
                h2.request_headers = real_headers
            try:
                h2.STREAM_PATH = OTHER_PATH          # the constant itself rebound at run time
                with self.assertRaises(h2.SendRefused):
                    h2.GrpcStream(srv.port)
            finally:
                h2.STREAM_PATH = real_path
            time.sleep(0.2)
        self.assertEqual(srv.paths, [])
        # And through the reader, after three trailers-only answers, still only the stream.
        with fake.FakeServer([fake.snapshot(schema)],
                             modes=("trailers", "trailers", "trailers", "normal")) as srv:
            r = tm.TelemetryReader(schema=schema, port=srv.port, read_timeout=0.2,
                                   retry_steps=((None, 0.1),))
            r.start()
            try:
                deadline = time.monotonic() + 6
                while r.latest()[0] is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertIsNotNone(r.latest()[0])
            finally:
                r.stop()
                r.join(3)
        self.assertGreaterEqual(len(srv.paths), 4)
        self.assertEqual(bad_paths(srv.paths), [])


# --------------------------------------------------------------------------- the wire

class WireTest(unittest.TestCase):
    def test_what_the_client_sends(self):
        schema = fake.make_schema(other_methods=True)
        with fake.FakeServer([fake.snapshot(schema)]) as srv:
            s = h2.GrpcStream(srv.port, read_timeout=0.2)
            try:
                got = []
                for _ in range(50):
                    got += s.poll()
                    if got:
                        break
                self.assertTrue(got)
            finally:
                s.close()
        self.assertEqual(srv.paths, [h2.STREAM_PATH])
        sent = [(t, sid) for _, t, _, sid in srv.client_frames]
        self.assertEqual([t for t, _ in sent].count(h2.HEADERS), 1)
        self.assertLessEqual({sid for _, sid in sent}, {0, 1})
        self.assertLessEqual({t for t, _ in sent}, {h2.SETTINGS, h2.WINDOW_UPDATE, h2.HEADERS,
                                                    h2.DATA, h2.PING})

    def test_the_checker_catches_another_path(self):
        # Proves the recording works: a hand-made request for an action method is recorded
        # (by a server kept out of the run-wide list) and the check flags it.
        with fake.FakeServer([b""], record_global=False) as srv:
            block = (bytes([0x83, 0x86]) + h2.hpack_int(4, 4, 0) + h2.hpack_str(OTHER_PATH)
                     + h2.hpack_int(1, 4, 0) + h2.hpack_str("127.0.0.1:%d" % srv.port))
            c = socket.create_connection(("127.0.0.1", srv.port), timeout=2)
            try:
                c.sendall(h2.PREFACE + h2.frame(h2.SETTINGS, 0, 0)
                          + h2.frame(h2.HEADERS, h2.F_END_HEADERS, 1, block)
                          + h2.frame(h2.DATA, h2.F_END_STREAM, 1, b"\0\0\0\0\0"))
                for _ in range(100):
                    if srv.paths:
                        break
                    c.settimeout(0.02)
                    try:
                        c.recv(100)
                    except OSError:
                        pass
            finally:
                c.close()
        self.assertEqual(bad_paths(srv.paths), [OTHER_PATH])
        self.assertNotIn(OTHER_PATH, fake.PATHS_SEEN)


class RunWideTest(unittest.TestCase):
    def test_every_path_any_fake_server_saw(self):
        # Runs after test_telemetry.py in a full discovery run (alphabetical order), so it
        # covers every connection the reader made in this run.
        with fake.FakeServer([fake.snapshot(fake.make_schema())]) as srv:
            r = tm.TelemetryReader(schema=fake.make_schema(), port=srv.port, read_timeout=0.2)
            r.start()
            try:
                for _ in range(250):
                    if r.latest()[0] is not None:
                        break
                    time.sleep(0.02)
            finally:
                r.stop()
                r.join(3)
        self.assertTrue(fake.PATHS_SEEN)
        self.assertEqual(bad_paths(fake.PATHS_SEEN), [])


if __name__ == "__main__":
    unittest.main()
