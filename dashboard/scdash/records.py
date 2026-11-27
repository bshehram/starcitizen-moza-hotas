"""Line to record: the time prefix, the level part, the tag, and joined continuation pieces.

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES). Everything else in this file is
this project's own.

What a log line looks like [seen: 69 logs from 2026-11, 545,399 lines]:

    <2026-11-26T23:17:10.584Z> [Notice] <SHUDEvent_OnNotification> Added notification "...
    |--- fixed-width time ---| |level-| |----------- tag ---------| |--- the rest ---

- The time prefix is always 26 characters and a space: `<YYYY-MM-DDTHH:MM:SS.mmmZ> `.
- The level part is a run of bracket groups, not always one: `[Notice]`, `[SPAM 119][Error]`, and
  also names such as `[CSessionManager::OnClientSpawned]` with no `<tag>` after them.
- Lines with no level part are of three sorts: their own markers (`- Connected joystick0: ...`,
  `BackupNameAttachment=...`, `  planet cells: ...`), echoes of HUD notices, and continuation
  pieces of a record whose text held a line break.
- 7,983 lines (1.5%) have no time at all: inner lines of multi-line debug dumps. Skipped.

The one cheap test (PLAN §9): take the tag after the time prefix (or the first bracket name, or a
fixed prefix for level-less markers) and look it up in a table. Every other line is dropped there,
before any decoding or regular expression.

Continuation pieces [seen]:
- A HUD notice whose text holds a line break is split; each piece has its own time prefix but no
  level part (191 of 2,086 notices; never more than 3 pieces). The piece usually has the same
  millisecond as the first, sometimes the next one (12 of 191).
- `SetVehicleSpawningInformations` is split the same way, every time it names a personal hangar:
  `... LandingArea: <handle>'s` then `<time> XL Hangar [Team_GameServices][ASOP]` (78 of 80).
- Once in 2,086 notices, a line with its own level part (a `<Vehicle Destroyed>` record, same
  millisecond) sat between a notice's first piece and its closing piece.
So a pending record is continued by the next timed line that has no level part; lines with their
own level part in between are never swallowed: they are read normally, and the records they
yield are held back until the pending one is done, so records come out in file order.
"""
import calendar
import re

# From CSR sc_livelog.py line 46 (commit ba6dad0): a notice is complete once its closing quote
# and notification id have arrived. CSR's other line-42-48 patterns are replaced: the time prefix
# is required here (CSR stripped any `<...>`), and a level part is any leading bracket (CSR's list
# of six level names missed `[SPAM 119][Error]` and the `[CSessionManager::...]` names).
NOTICE_END_RE = re.compile(r'" \[\d+\]')
# This project's own: the team tags every complete record of interest ends with [seen].
TEAM_END_RE = re.compile(r"\[Team_[^\]]*\](?:\[[^\]]*\])*\s*$")

MAX_PIECES = 8          # CSR's cap (line 180); the most seen is 3
MAX_INTERLEAVE = 4      # lines with their own level read while a record waits; the most seen is 1

_LT, _GT, _Z, _LB = 0x3C, 0x3E, 0x5A, 0x5B          # '<', '>', 'Z', '['
_NOTICE_FAST = b"[Notice] <"
_ECHO = b'   "'                                     # the indented echo of a HUD notice


def parse_ts(ts):
    """'2026-11-26T23:17:10.584' (UTC) -> seconds since the epoch, to the millisecond."""
    secs = calendar.timegm((int(ts[0:4]), int(ts[5:7]), int(ts[8:10]),
                            int(ts[11:13]), int(ts[14:16]), int(ts[17:19]), 0, 0, 0))
    return secs + int(ts[20:23]) / 1000.0


UNREADABLE = "?unreadable"          # the key of a record standing for a line that could not be read


class Record:
    """One logical log record: its first line's offset and time, its key, and its text."""
    __slots__ = ("offset", "ts", "t", "level", "key", "text", "complete")

    def __init__(self, offset, ts, level, key, text, complete=True, t=None):
        self.offset = offset        # byte offset of the record's first line in the file
        self.ts = ts                # 'YYYY-MM-DDTHH:MM:SS.mmm', UTC, as logged (None if unreadable)
        self.t = t if t is not None or ts is None else parse_ts(ts)   # seconds since the epoch
        self.level = level          # e.g. 'Notice', 'SPAM 119][Error', '' for level-less lines
        self.key = key              # the table key that matched (str), or UNREADABLE
        self.text = text            # what follows the key; continuation pieces joined by '\n'
        self.complete = complete    # False if a multi-line record never got its closing piece

    def __repr__(self):
        return "Record(%d, %s, %r, %r)" % (self.offset, self.ts, self.key, self.text[:60])


class _Pending:
    __slots__ = ("record", "notice", "others", "held")

    def __init__(self, record, notice):
        self.record = record
        self.notice = notice
        self.others = 0
        self.held = []


class RecordReader:
    """Turns complete lines into records of interest, in file order.

    `tags` maps a `<tag>` (bytes) to its table entry, `brackets` maps a first bracket name (bytes),
    `prefixes` maps a level-less line's start (bytes). `multiline` is the set of tag keys whose
    records may continue on the next level-less line. Feed with `lines(lines, offsets)`; collect
    with `take()`. `reset()` starts a new session; `flush()` closes a record still waiting.
    """

    def __init__(self, tags, brackets, prefixes, multiline):
        self._tags = tags
        self._brackets = brackets
        self._prefixes = prefixes
        self._prefix_tuple = tuple(prefixes)
        self._multiline = multiline
        self._pending = None
        self._out = []
        self._last_line = None
        self.lines_seen = 0
        self.bad_lines = 0

    def reset(self):
        self._pending = None
        self._out = []
        self._last_line = None
        self.bad_lines = 0

    @property
    def last_time(self):
        """The time of the last timed line read so far, or None. Parsed only when asked for."""
        if self._last_line is None:
            return None
        try:
            return parse_ts(self._last_line[1:24].decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return None

    def take(self):
        out, self._out = self._out, []
        return out

    def flush(self):
        if self._pending is not None:
            self._close(False)

    def lines(self, lines, offsets):
        self.lines_seen += len(lines)
        tags, brackets, prefixes = self._tags, self._brackets, self._prefix_tuple
        for line, off in zip(lines, offsets):
            # the fixed-width time prefix: '<' at 0, 'Z' at 24, '>' at 25, a space at 26
            if len(line) < 28 or line[0] != _LT or line[25] != _GT or line[24] != _Z:
                continue                                    # no time: skipped, never a piece
            try:
                if self._pending is not None:
                    if line[27] != _LB and self._piece(line):
                        continue
                    # a line of its own while a record waits: read normally, never swallowed
                    self._pending.others += 1
                    if self._pending.others > MAX_INTERLEAVE:
                        self._close(False)
                if line[27] == _LB:
                    if line.startswith(_NOTICE_FAST, 27):       # the common case, one test
                        s = 37
                        e = line.find(b">", s)
                        key = line[s:e]
                        if key not in tags:
                            continue
                        self._emit(off, line, b"Notice", key, e + 1, key in self._multiline)
                        continue
                    i, first = 27, None
                    while line[i:i + 1] == b"[":
                        j = line.find(b"]", i)
                        if j < 0:
                            break
                        if first is None:
                            first = line[i + 1:j]
                        i = j + 1
                    level = line[28:i - 1]
                    if line[i:i + 1] == b" ":
                        i += 1
                    if line[i:i + 1] == b"<":
                        e = line.find(b">", i)
                        key = line[i + 1:e]
                        if e > i and key in tags:
                            self._emit(off, line, level, key, e + 1, key in self._multiline)
                            continue
                    if first is not None and first in brackets:
                        self._emit(off, line, level, first, i, False)
                elif line.startswith(prefixes, 27):
                    for p in prefixes:
                        if line.startswith(p, 27):
                            self._emit(off, line, b"", p, 27 + len(p), False)
                            break
            except Exception as exc:                        # noqa: BLE001 - no line may stop us
                self.bad_lines += 1
                self._put(Record(off, None, "", UNREADABLE, type(exc).__name__))
        for line in reversed(lines):                        # usually the very last one
            if len(line) >= 28 and line[0] == _LT and line[24] == _Z and line[25] == _GT:
                self._last_line = line
                break

    # -- internals -------------------------------------------------------------------------

    def _emit(self, off, line, level, key, start, multiline):
        if line.endswith(b"\r"):
            line = line[:-1]
        text = line[start:].decode("utf-8", "replace")
        ts = line[1:24].decode("ascii")                 # raises on a broken prefix: see lines()
        rec = Record(off, ts, level.decode("ascii", "replace"),
                     key.decode("utf-8", "replace"), text.lstrip(" ") if start > 27 else text,
                     t=parse_ts(ts))                    # raises on bad digits: see lines()
        if multiline:
            # From CSR sc_livelog.py lines 248-252: a notice without its closing quote waits for
            # its pieces. Changed: SetVehicleSpawningInformations waits the same way, for its
            # team tags.
            notice = "Added notification \"" in text
            done = NOTICE_END_RE.search(text) if notice else TEAM_END_RE.search(text)
            if not done:
                if self._pending is not None:      # a second record waiting: close the first
                    self._close(False)
                self._pending = _Pending(rec, notice)
                return
        self._put(rec)

    def _put(self, rec):
        if self._pending is not None:
            self._pending.held.append(rec)
        else:
            self._out.append(rec)

    def _piece(self, line):
        """A level-less timed line while a record waits. True if it was taken as a piece."""
        body = line[27:]
        if body.startswith(_ECHO) or body.startswith(self._prefix_tuple):
            return False                               # an echo or a marker of its own
        if body.endswith(b"\r"):
            body = body[:-1]
        # From CSR sc_livelog.py lines 173-182 (commit ba6dad0): append the piece, and the
        # record is whole once the closing quote has arrived; give up after 8 pieces.
        # Changed: a record that never completes is still emitted (marked incomplete) rather
        # than dropped, and non-notice records end on their team tags instead of a quote.
        p = self._pending
        rec = p.record
        piece = body.decode("utf-8", "replace")
        rec.text += "\n" + piece
        done = NOTICE_END_RE.search(piece) if p.notice else TEAM_END_RE.search(piece)
        if done:
            self._close(True)
        elif rec.text.count("\n") + 1 >= MAX_PIECES:
            self._close(False)
        return True

    def _close(self, complete):
        p, self._pending = self._pending, None
        p.record.complete = complete
        self._out.append(p.record)
        self._out.extend(p.held)
