"""The notices that can name someone else, as the game writes them, and the rule for which of
their words may be learned as another player's name (stage 3 review, round 2).

The shapes are the game's own text: `global.ini` of build 4.10.201.48085 (Alpha 4.10.3), read
with tools/gamedata.py on 2026-11-27 [game]. %ls and %S are where the game puts a name:

    hud_law_CrimeCommitted               "Crime Committed: %ls"                       the crime
    hud_law_CrimeCommitted_VictimName    "Crime Committed: %ls\\nagainst %ls"          crime, victim
    hud_law_charge_player_crime          "%ls committed %ls against you"              a player, crime
    hud_law_charge_player_crime_party    "Party member %ls committed %ls against you" a player, crime
    hud_law_Victim                       "Victim: %ls"                                the victim
    hud_law_PlayerAreaWarning            "Trespassing on %ls's Private Property\\n..." a player
    hud_law_TrespassPropertyWarning_Named "WARNING: %ls's Private Property. ..."      an owner
    comms_suffix_ship_channel            "channel '%S'", %S = "<ship> : <owner>", in
    comms_local_player_joined_auto       "You have joined %s." and
    comms_local_player_left              "You have left the %s."
    comms_local_player_joined            "You have joined %S's %s."                   a player
    comms_member_left / _kicked, comms_invite_accepted / _declined / _received,
    comms_leader_changed, comms_invite_timeout                                        a player

The victim of the user's own crime can be anyone: a player, a civilian, a security force. The
charge notices ("... against you") carry the forgive-or-report choice the game gives for a
player's crime, so their first slot is a player [my reading of hud_law_charge_by_default].

None of these texts is kept with the other party's name in it: the state words each one with
the name left out. A word from them is learned as a name (so the scrubber also hides it in other
texts) only when `learnable()` says it can be a handle and is no word of the game: when in doubt,
nothing is learned, and the notice is safe anyway.
"""
import re

# Handles: letters, digits, "_" and "-", at least 3 characters [RSI's rule as the reviewer gave it].
HANDLE_RE = re.compile(r"^[A-Za-z0-9_-]{3,60}$")
_PUNCT = ".,;:!?()[]{}\"'"

# Infractions_Name_001 to 047 [game].
CRIMES = (
    "Homicide", "Unlawful Discharge of a Weapon", "Brandishing a Weapon", "Parking Violation",
    "Destruction of Property", "Damage of Property", "Possession of Prohibited Goods",
    "Trespassing (Second Degree)", "Sabotage", "Resisting Arrest",
    "Trafficking of Class A Controlled Substance", "Possession of Class A Controlled Substance",
    "Trafficking of Stolen Property", "Possession of Stolen Property", "Harboring a Fugitive",
    "Operating a Stolen Vehicle", "Aggravated Assault", "Assaulting Security Personnel",
    "Evading Arrest", "Failure to Comply", "Unauthorized Computer Access",
    "Trafficking of Class B Controlled Substance", "Trafficking of Class C Controlled Substance",
    "Possession of Class B Controlled Substance", "Possession of Class C Controlled Substance",
    "Destruction of Vehicle", "Vehicular Collision", "Delinquent Restitution",
    "Unauthorized Interdiction", "Trespassing (First Degree)", "Battery (Second Degree)",
    "Battery (First Degree)", "Actively Incarcerated", "Escaped from Custody",
    "Attempted Escape from Custody", "Insurance Fraud", "Inmate Homicide",
    "Reckless Vehicle Operation", "Negligent Homicide", "Armistice Violation",
    "Aggravated Criminal Damage", "Grievous Bodily Harm", "Attempted Homicide", "Vehicle Theft",
    "Abandoning Klescher Equipment", "Property Theft", "Illegal Towing")

# Jurisdictions_Name_001 to 009, Maps_Jurisdiction_Unaffiliated, the Grim HEX journal [game].
JURISDICTIONS = ("UEE", "United Empire of Earth", "Crusader Industries", "Hurston Dynamics",
                 "ArcCorp", "microTech", "Autonomous", "People's Alliance",
                 "Klescher Rehabilitation Facilities", "Ungoverned", "Unaffiliated",
                 "Green Imperial HEX")

# Words that are never a handle in these notices: articles, pronouns, the notices' own words,
# who else a crime can be against [mine].
STOPWORDS = frozenset("""
a an the this that these those some any all no none null unknown invalid nobody
i me my mine you your yours yourself we us our he him his she her hers it its they them their
theirs who whom someone somebody anyone anybody everyone everybody something
another other others player players party member members group channel crew pilot pilots ship
ships vehicle vehicles owner private property area zone space station
security police guard guards navy advocacy civilian civilians bystander npc ai target
crime crimes committed against victim criminal criminals outlaw outlaws pirate pirates
hostile hostiles enemy enemies attacker attackers jurisdiction law lawful unlawful
warning trespassing restricted monitored armistice prison
""".split())

CRIME_WORDS = frozenset(w for c in CRIMES for w in re.findall(r"[a-z]+", c.lower()))
_WORDS_RE = re.compile(r"[A-Za-z0-9_-]+")
_PARTS_RE = re.compile(r"[A-Za-z0-9]+")


def words_of(text):
    """The words a name is made of, lower case, both as handle-shaped runs ('mic-l2') and as
    their letter-and-digit parts ('mic', 'l2')."""
    if not isinstance(text, str):
        return ()
    t = text.lower()
    return _WORDS_RE.findall(t) + _PARTS_RE.findall(t)


def fixed_words():
    """The game words this module knows by itself: crimes, jurisdictions, the stoplist."""
    out = set(STOPWORDS) | CRIME_WORDS
    for j in JURISDICTIONS:
        out.update(words_of(j))
    return out


def token(text):
    """A word as a name would stand in a notice: punctuation and a possessive "'s" off."""
    t = (text or "").strip().strip(_PUNCT)
    if t.lower().endswith("'s"):
        t = t[:-2]
    return t.strip(_PUNCT)


def learnable(word, game_words):
    """The word, if it can be another player's handle and is no word of the game; else None.

    `game_words` is the set of lower-case words of every place, maker, ship, commodity, shop and
    contract giver in the reference tables, with `fixed_words()` (refdata.RefData.game_words)."""
    t = token(word)
    if not HANDLE_RE.match(t) or not any(c.isalpha() for c in t):
        return None
    low = t.lower()
    if low in game_words or low in STOPWORDS:
        return None
    return t


def crime_name(text):
    """The crime as the dashboard may show it: made only of the words of the game's crime
    names ('Assault', 'Trespassing (First Degree)'), else None. A slot holding anything else
    is not a crime name, and might be a name."""
    if not isinstance(text, str) or not text.strip() or len(text) > 80:
        return None
    ws = re.findall(r"[A-Za-z]+|[^A-Za-z\s()]", text)
    if not ws or not all(w.lower() in CRIME_WORDS for w in ws):
        return None
    return text.strip()
