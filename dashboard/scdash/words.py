"""Small helpers for plain words: times, durations, money, ship class names.

Nothing here looks at the wall clock: local time is computed from an event's own time, in the
time zone the caller passes (the computer's own when it passes none).
"""
import re
import unicodedata
from datetime import datetime, timezone

MAKERS = {"AEGS": "Aegis", "ANVL": "Anvil", "ARGO": "Argo", "BANU": "Banu", "CNOU": "C.O.",
          "CRUS": "Crusader", "DRAK": "Drake", "ESPR": "Esperia", "GAMA": "Gatac", "GLSN": "Gallenson",
          "GRIN": "Greycat", "KRIG": "Kruger", "MISC": "MISC", "MRAI": "Mirai", "ORIG": "Origin",
          "RSI": "RSI", "TMBL": "Tumbril", "VNCL": "Vanduul", "XIAN": "Aopoa", "XNAA": "Aopoa"}


def iso(t):
    """Seconds since the epoch -> '2026-11-26T23:11:20.067Z', or None."""
    if t is None:
        return None
    dt = datetime.fromtimestamp(t, timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (dt.microsecond // 1000)


def local(t, tz=None):
    """The event's time as an aware datetime in `tz` (None: this computer's zone)."""
    dt = datetime.fromtimestamp(t, timezone.utc)
    return dt.astimezone(tz) if tz is not None else dt.astimezone()


def clock(t, tz=None, seconds=True):
    """'3:11:20 PM' (American, no leading zero)."""
    dt = local(t, tz)
    s = dt.strftime("%I:%M:%S %p" if seconds else "%I:%M %p")
    return s[1:] if s.startswith("0") else s


def day(t, tz=None):
    """'Thu Nov 26, 2026' (month first)."""
    dt = local(t, tz)
    return dt.strftime("%a %b ") + str(dt.day) + dt.strftime(", %Y")


def duration(seconds):
    if seconds is None:
        return "unknown"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%d h %02d min" % (h, m)
    if m:
        return "%d min %02d s" % (m, s)
    return "%d s" % s


def money(x):
    if x is None:
        return "?"
    return "{:,.0f}".format(x)


def _model_words(text, skip_first):
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    words = [w for w in re.split(r"[^a-z0-9]+", t) if w]
    return set(words[1:] if skip_first else words)


def compatible(name, cls):
    """Could a ship channel's name ('Anvil C8R Pisces Rescue') be this vehicle class
    ('ANVL_C8R_Pisces')? The class's model words, after the maker, must all be in the name, and
    the name may add one more word only when the class has two or more model words, so
    'Drake Golem OX' is not a 'DRAK_Golem' [names and classes seen together in 2026-11: Pisces,
    Golem, Golem OX, Liberator, M80, Ursa Medivac, Avenger Titan, Salvation, Perseus, ROC, Hyun,
    Corsair]."""
    if not name or not cls:
        return True
    model = _model_words(cls.replace("_", " "), True)
    have = _model_words(name, True)
    if not model or not model <= have:
        return False
    extra = have - model
    return not extra or (len(model) >= 2 and len(extra) <= 1)


def ship_class(cls):
    """'DRAK_Golem_OX' -> 'Drake Golem OX'. Unknown makers are left as they are."""
    if not cls:
        return "ship"
    maker, _, rest = cls.partition("_")
    if maker in MAKERS and rest:
        return MAKERS[maker] + " " + rest.replace("_", " ")
    return cls.replace("_", " ")
