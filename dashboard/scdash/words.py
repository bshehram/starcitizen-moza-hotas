"""Small helpers for plain words: times, durations, money, ship class names.

Nothing here looks at the wall clock: local time is computed from an event's own time, in the
time zone the caller passes (the computer's own when it passes none).
"""
import re
import unicodedata
from datetime import datetime, timezone

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
