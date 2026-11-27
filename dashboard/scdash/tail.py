"""The log follower: reads only what is new in Game.log, without ever holding the file open.

Each poll opens the log (sharing read, write and delete, see winutil), reads its first line and
compares it with the one it knows, reads the bytes past its saved offset in pieces of at most
1 MB, hands the complete lines on, and closes the file again (PLAN §8, §9).

A new session starts at offset 0 when the first line has changed or the file has become shorter
than the offset. The size test alone is not enough: the game empties Game.log in place at each
launch and writes 18 KB in the first 10 seconds, so after any pause a new log can already be
longer than the old offset [seen 2026-11-27, PLAN §8]. The first line holds the launch time,
so it changes with every launch.

A partial last line is held back until its newline arrives. A line longer than MAX_LINE is cut to
that length (the rest is dropped up to its newline), so a flood with no newlines cannot grow
memory. Lines are handed on as raw bytes without the newline; a trailing CR is left for the next
layer, which strips it only from the few lines it keeps.

Nothing a line holds can stop or stall the follower: the offset and the held-back line are
settled before the lines are handed on, and a failure in the receiver is counted
(`sink_errors`) and passed over. The layers above also catch failures line by line.

Copyright (c) 2026 archelium (support@archelium.com) for the part marked "From CSR" below, used
under the MIT License (see dashboard/THIRD_PARTY_NOTICES).
"""
from pathlib import Path

from . import config
from .winutil import open_shared


class Follower:
    """Follows one log file by polling. Keeps no file handle between polls."""

    def __init__(self, path, opener=open_shared, piece=config.READ_PIECE,
                 max_line=config.MAX_LINE, head_bytes=config.HEAD_BYTES):
        self.path = Path(path)
        self._open = opener
        self._piece = piece
        self._max_line = max_line
        self._head_bytes = head_bytes
        self.first_line = None      # the session's first line (bytes), or None before one is seen
        self.offset = 0             # file offset of the next byte to read
        self.sessions = 0           # sessions started by this follower
        self.sink_errors = 0        # batches whose receiver failed; the reading went on
        self._partial = b""         # an unfinished last line
        self._partial_at = 0        # its offset in the file
        self._skip = False          # inside an overlong line: drop bytes up to its newline

    def poll(self, sink, budget=None):
        """Read what is new and hand it to `sink`.

        `sink.reset()` is called when a new session starts (not before the very first one);
        `sink.lines(lines, offsets)` receives complete lines and the file offset of each.
        `budget` caps the bytes read in this poll (None: read to the end of the file).
        Returns 'missing' (no file), 'waiting' (no complete first line yet), 'idle' or 'read'.
        """
        try:
            f = self._open(self.path)
        except FileNotFoundError:
            return "missing"
        try:
            # The size from the open handle: sound, where a directory listing lags [seen, §8].
            size = f.seek(0, 2)
            f.seek(0)
            head = f.read(self._head_bytes)
            nl = head.find(b"\n")
            if nl < 0 and len(head) < self._head_bytes:
                # Empty, or the first line is still being written. If we were inside a session,
                # the file has been emptied or replaced: that session is over.
                if self.first_line is not None and (size < self.offset or
                                                    not self.first_line.startswith(head)):
                    self._new_session(None, sink)
                return "waiting"
            first = (head[:nl] if nl >= 0 else head).rstrip(b"\r")
            # From CSR sc_livelog.py line 454 (LiveTail.poll): a file shorter than the offset is
            # a new log. Changed: a changed first line is one too (see above).
            if first != self.first_line or size < self.offset:
                self._new_session(first, sink)
            if size <= self.offset:
                return "idle"
            f.seek(self.offset)
            left = budget
            while left is None or left > 0:
                want = self._piece if left is None else min(self._piece, left)
                piece = f.read(want)
                if not piece:
                    break
                at = self.offset
                self.offset += len(piece)          # settled first: a failure below cannot stall us
                if left is not None:
                    left -= len(piece)
                self._feed(piece, at, sink)
            return "read"
        finally:
            f.close()

    def flush(self, sink):
        """Hand on a final line that has no newline. Only for a log that is known to be finished."""
        if self._partial:
            line, at = self._partial, self._partial_at
            self._partial, self._skip = b"", False
            self._hand_on(sink, [line], [at])

    def _hand_on(self, sink, lines, offsets):
        try:
            sink.lines(lines, offsets)
        except Exception:                          # noqa: BLE001 - never let one batch stop the reader
            self.sink_errors += 1

    def _new_session(self, first, sink):
        if self.first_line is not None or self.offset:
            try:
                sink.reset()
            except Exception:                      # noqa: BLE001
                self.sink_errors += 1
        self.first_line = first
        self.offset = 0
        self._partial, self._partial_at, self._skip = b"", 0, False
        if first is not None:
            self.sessions += 1

    def _feed(self, piece, at, sink):
        """Split one piece into complete lines; keep an unfinished last line for the next piece.

        From CSR sc_livelog.py lines 462-465 (LiveTail.poll): the unread rest of the last line is
        kept for the next read. Changed: the kept line is capped, lines carry their offsets, and
        everything is settled before the receiver is called, which is the last step."""
        lines, offs = [], []
        pos, n, cap = 0, len(piece), self._max_line
        if self._partial:
            nl = piece.find(b"\n")
            if nl < 0:
                if not self._skip:
                    room = cap - len(self._partial)
                    if n > room:
                        self._partial += piece[:room]
                        self._skip = True
                    else:
                        self._partial += piece
                return
            line = self._partial if self._skip else (self._partial + piece[:nl])[:cap]
            lines.append(line)
            offs.append(self._partial_at)
            self._partial, self._skip = b"", False
            pos = nl + 1
        last = piece.rfind(b"\n")
        if last >= pos:
            o = at + pos
            for part in piece[pos:last].split(b"\n"):
                offs.append(o)
                o += len(part) + 1
                lines.append(part if len(part) <= cap else part[:cap])
            pos = last + 1
        if pos < n:
            rest = piece[pos:]
            self._partial_at = at + pos
            if len(rest) > cap:
                self._partial, self._skip = rest[:cap], True
            else:
                self._partial = rest
        if lines:
            self._hand_on(sink, lines, offs)
