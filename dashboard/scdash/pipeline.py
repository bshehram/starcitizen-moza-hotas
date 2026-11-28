"""Follower -> records -> events -> state, for one log path. What the stage 2 service calls.

    reader = LogReader(config.game_log(live), names)
    reader.poll()                 # once a second: reads only what is new, never holds the file
    reader.state                  # the current State (to_dict() for the page)
    reader.take_lines()           # feed lines new or changed since the last call (to push)
    reader.take_finished()        # summaries of sessions that ended (to write to data/sessions/)
    reader.summary(complete)      # the current session's summary, e.g. when the game has exited

`read_whole(path)` reads a finished log in one go, for `timeline` and the tests.

No line can stop or stall the reading (PLAN §7, §8): the follower settles its offset before it
hands lines on, the record and event layers turn an unreadable line into an `unreadable` event,
and a failure while applying an event is counted here. All of them show in
`state.session["unreadable"]`.
"""
from .events import EventParser
from .names import LocationNames
from .state import State
from .summary import build_summary
from .tail import Follower
from .winutil import open_shared


class LogReader:
    def __init__(self, path, names=None, opener=open_shared, keep_events=False, **follower_args):
        self.names = names if names is not None else LocationNames()
        self.follower = Follower(path, opener, **follower_args)
        self.parser = EventParser()
        self.keep_events = keep_events
        self.events = []              # every event, only when keep_events (timeline, tests)
        self._all_lines = []          # every feed line once, only when keep_events (all_lines)
        self._held_names = []         # names forgotten since all_lines was last read
        self._sealed = 0              # all_lines before this index belong to sessions that ended
        self.state = self._new_state()
        self.apply_errors = 0
        self._new_lines = []
        self._finished = []
        self._forgotten = 0

    def _new_state(self):
        st = State(self.names)
        if self.keep_events:
            st.forget_hook = self._held_names.extend
        return st

    @property
    def all_lines(self):
        """Every feed line once (keep_events only), with every name forgotten so far replaced by
        "another player" (as the state's own texts have them). Taken out here, once, when the
        list is read: at every forgetting pass, a walk of the whole list made `timeline`
        quadratic in the number of names (stage 3 review, round 3)."""
        self._redact_all_lines()
        return self._all_lines

    def _redact_all_lines(self):
        if self._held_names:
            names = list(self._held_names)
            del self._held_names[:]                   # the same list: the state's hook holds it
            self.state.redact_names(self._all_lines, names)

    def _seal(self):
        """The session's state is about to be replaced (a new session in the same file, or a
        session line inside it): its lines still held here are scrubbed with it, while it still
        knows their names. The new state does not, and scrubbed them as written (stage 3 review,
        round 4): the lines waiting for take_lines() become scrubbed copies, and the lines of
        `all_lines` not yet sealed have their text scrubbed in place (the old state no longer
        changes them)."""
        st = self.state
        if self._new_lines:
            self._new_lines = st.scrub(self._new_lines)
        if self.keep_events:
            self._redact_all_lines()
            for line in self._all_lines[self._sealed:]:
                line["text"] = st.scrub(line["text"])
            self._sealed = len(self._all_lines)

    # The follower's sink -------------------------------------------------------------------

    def reset(self):
        """A new session starts in the same file: the old one is over."""
        self.parser.flush()
        self._drain()
        if self.state.session["id"] is not None:
            self._finished.append(self.summary(complete=True))
        self.parser.reset()
        self._seal()                                  # while the old state still knows its names
        self.state = self._new_state()
        self._forgotten = 0

    def lines(self, lines, offsets):
        if not self.parser.session and self.follower.first_line is not None:
            self.parser.begin(self.follower.first_line)
        self.parser.lines(lines, offsets)
        self._drain()

    # Driving --------------------------------------------------------------------------------

    def poll(self, budget=None):
        """One poll of the follower. Returns its status ('missing', 'waiting', 'idle', 'read')."""
        return self.follower.poll(self, budget)

    def finish(self):
        """The log is known to be complete: hand on a last line without a newline, close a
        record still waiting for its continuation."""
        self.follower.flush(self)
        self.parser.flush()
        self._drain()

    def summary(self, complete=False):
        """The current session's summary. A session with no quit line ends at its last line."""
        return build_summary(self.state, complete, last_line_t=self.parser.last_line_t)

    def take_lines(self):
        """Feed lines new or changed since the last call, each once, by id: a line already
        handed out comes again when its text changes (a jump's route and fuel), with the same id.

        Scrubbed as `State.to_dict(private=False)` scrubs (other players' names read "another
        player", the user's handle "you", no control or bidi character): they were handed out as
        read (stage 3 review, round 3). The lines are copies."""
        by_id = {}
        for line in self._new_lines:
            by_id[line["id"]] = line
        self._new_lines = []
        if not by_id:
            return []
        return self.state.scrub(list(by_id.values()))

    def take_finished(self):
        out, self._finished = self._finished, []
        return out

    def _drain(self):
        for ev in self.parser.take():
            st = self.state.session
            if st["events"] and ev.kind != "unreadable" and (
                    ev.kind == "session_start" or (ev.session and ev.session != st["id"])):
                self._seal()                          # State.apply resets itself for this event
            try:
                lines = self.state.apply(ev)
            except Exception:                         # noqa: BLE001 - one event must not stop us
                self.apply_errors += 1
                self.state.session["unreadable"] += 1
                continue
            if self.state.forgotten != self._forgotten:
                # The state forgot some names after taking them out of all it holds; the lines
                # waiting here for take_lines() lose them the same way. The list of every feed
                # line (keep_events) loses them when it is read (all_lines).
                self._forgotten = self.state.forgotten
                self.state.redact_held(self._new_lines)
            if self.keep_events:
                self.events.append(ev)
                self._all_lines.extend(x for x in lines if x["rev"] == 0)
            if lines:
                self._new_lines.extend(lines)
                if len(self._new_lines) > 500:        # nobody is taking them: keep it bounded
                    del self._new_lines[:-100]


def read_whole(path, names=None, opener=open_shared, keep_events=True, **follower_args):
    """Read a whole log (to its current end) and return the LogReader."""
    reader = LogReader(path, names, opener, keep_events, **follower_args)
    while reader.poll() == "read":
        pass
    reader.finish()
    return reader
