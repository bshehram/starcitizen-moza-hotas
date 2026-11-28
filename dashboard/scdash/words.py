"""Small helpers for plain words: times, durations, money, ship class names.

Nothing here looks at the wall clock: local time is computed from an event's own time, in the
time zone the caller passes (the computer's own when it passes none).
"""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

# Characters a text from the log must not carry onto a screen or a console: the C0 and C1 control
# characters (ESC sequences, a bell, a NUL) and the bidirectional controls, which can reverse the
# order of the dashboard's own words after them (U+202A-202E, U+2066-2069, and the marks
# U+200E/U+200F/U+061C). Tabs and line breaks become a space; the rest are dropped.
_UNSAFE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f؜‎‏‪-‮⁦-⁩]")
_SPACES = re.compile("[\t\n\r]")


def clean_text(s):
    """`s` with the control and bidi characters taken out (PLAN §8: what the log says is data)."""
    if not s or not isinstance(s, str):
        return s
    if _UNSAFE.search(s) is None and _SPACES.search(s) is None:
        return s
    return _UNSAFE.sub("", _SPACES.sub(" ", s))


def clean_all(obj):
    """Every string in a JSON-like object (keys too) through `clean_text`."""
    if isinstance(obj, str):
        return clean_text(obj)
    if isinstance(obj, dict):
        return {clean_text(k) if isinstance(k, str) else k: clean_all(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_all(v) for v in obj]
    return obj


MAKERS = {"AEGS": "Aegis", "ANVL": "Anvil", "ARGO": "Argo", "BANU": "Banu", "CNOU": "C.O.",
          "CRUS": "Crusader", "DRAK": "Drake", "ESPR": "Esperia", "GAMA": "Gatac", "GLSN": "Gallenson",
          "GRIN": "Greycat", "KRIG": "Kruger", "MISC": "MISC", "MRAI": "Mirai", "ORIG": "Origin",
          "RSI": "RSI", "TMBL": "Tumbril", "VNCL": "Vanduul", "XIAN": "Aopoa", "XNAA": "Aopoa"}


def iso(t):
    """Seconds since the epoch -> '2026-11-26T23:11:20.067Z', or None. Never raises: a time no
    date can show (inf, nan, year 9999 on Windows) gives None."""
    if t is None:
        return None
    try:
        dt = datetime.fromtimestamp(t, timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (dt.microsecond // 1000)
    except (OverflowError, OSError, ValueError, TypeError):
        return None


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


# ---------------------------------------------------------------------------- stage 3 display

def short_day(t, tz=None):
    """'Nov 26' (month first, no year)."""
    dt = local(t, tz)
    return dt.strftime("%b ") + str(dt.day)


def week_day(t, tz=None):
    """'Fri, Nov 27', as the status strip shows the date."""
    dt = local(t, tz)
    return dt.strftime("%a, %b ") + str(dt.day)


def day_clock(t, tz=None):
    """'Nov 26, 4:12 PM': a time that may not be today."""
    return "%s, %s" % (short_day(t, tz), clock(t, tz, seconds=False))


def hours_minutes(seconds):
    """'1:47' for a session length, '0:05' under an hour."""
    if seconds is None:
        return None
    m = int(max(0, seconds) // 60)
    return "%d:%02d" % divmod(m, 60)


def number(x, places=0):
    """'11,655', or '2.66' with places=2; None stays None."""
    if x is None:
        return None
    return ("{:,.%df}" % places).format(x)


def scu(x):
    """An amount of SCU as people write it: '64', '2.66', '0.5'."""
    if x is None:
        return None
    if abs(x - round(x)) < 1e-9:
        return number(round(x))
    return ("{:,.2f}".format(x)).rstrip("0").rstrip(".")


def signed_percent(x):
    """'+8%', '-3%', '0%'."""
    if x is None:
        return None
    return "%+d%%" % round(x) if round(x) else "0%"


def next_midnight(t, tz=None):
    """The next local midnight after `t` (seconds since the epoch), in `tz` or this computer's
    zone: the moment every "today" time is worded with its date instead. None if it cannot be
    told."""
    try:
        if tz is None:
            d = datetime.fromtimestamp(t)                       # naive local, with its own DST
            return (datetime(d.year, d.month, d.day) + timedelta(days=1)).timestamp()
        d = datetime.fromtimestamp(t, tz)
        return (datetime(d.year, d.month, d.day, tzinfo=tz) + timedelta(days=1)).timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def parse_time(text):
    """A time written with its offset ('2026-11-26T17:30:00-08:00', or 'Z') -> seconds since the
    epoch, or None. A time without an offset is read as this computer's local time. Read with
    `datetime.fromisoformat` and no zone database (PLAN §10: `zoneinfo` has no data on Windows)."""
    if not isinstance(text, str) or not 10 <= len(text) <= 40:
        return None
    try:
        dt = datetime.fromisoformat(text.strip())
        if dt.tzinfo is None:
            dt = dt.astimezone()                    # naive: this computer's zone
        t = dt.timestamp()
    except (ValueError, OverflowError, OSError):
        return None
    if not 1420070400 <= t < 4102444800:            # 2015 to 2099, as for log times
        return None
    return t


ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
MK_RE = re.compile(r"mk(i{1,3}|iv|vi?|\d+)")


def _model_words(text, skip_first):
    """Lower-case words without accents; "Mk II", "MkII", "Mk 2" and "Mk2" all become "mk2"."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    words = [w for w in re.split(r"[^a-z0-9]+", t) if w]
    out, i = [], 0
    while i < len(words):
        w = words[i]
        m = MK_RE.fullmatch(w)
        if m:
            w = "mk" + ROMAN.get(m.group(1), m.group(1))
        elif w == "mk" and i + 1 < len(words) and (words[i + 1] in ROMAN or words[i + 1].isdigit()):
            w = "mk" + ROMAN.get(words[i + 1], words[i + 1])
            i += 1
        out.append(w)
        i += 1
    return set(out[1:] if skip_first else out)


def fit(name, cls):
    """How well a ship channel's name ('Anvil C8R Pisces Rescue') fits a vehicle class
    ('ANVL_C8R_Pisces'): 2 exactly, 1 with one extra word in the name, 0 not at all.

    The class's model words, after the maker, must all be in the name; the name may add one more
    word only when the class has two or more model words, so 'Drake Golem OX' is not a
    'DRAK_Golem' [names and classes seen together in 2026-11: Pisces, Golem, Golem OX, Liberator,
    M80, Ursa Medivac, Avenger Titan, Salvation, Perseus, ROC, Hyun, Corsair]. A longer variant
    name ('Aegis Avenger Titan Renegade') still fits the shorter class with 1, so where two
    classes compete the exact one (2) wins. An unknown name or class fits with 1."""
    if not name or not cls:
        return 1
    model = _model_words(cls.replace("_", " "), True)
    have = _model_words(name, True)
    if not model or not model <= have:
        return 0
    extra = have - model
    if not extra:
        return 2
    return 1 if (len(model) >= 2 and len(extra) <= 1) else 0


def compatible(name, cls):
    """Could a ship channel's name be this vehicle class? (`fit` above it, for a yes or no.)"""
    return fit(name, cls) > 0


def ship_class(cls):
    """'DRAK_Golem_OX' -> 'Drake Golem OX'. Unknown makers are left as they are."""
    if not cls:
        return "ship"
    maker, _, rest = cls.partition("_")
    if maker in MAKERS and rest:
        return MAKERS[maker] + " " + rest.replace("_", " ")
    return cls.replace("_", " ")
