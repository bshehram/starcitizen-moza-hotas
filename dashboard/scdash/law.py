"""The notices that can name someone else, as the game writes them, and the rule for which of
their words may be learned as another player's name (stage 3 review, rounds 2 and 3).

The shapes are the game's own text: `global.ini` of build 4.10.201.48085 (Alpha 4.10.3), read
from Data.p4k with tools/gamedata.py on 2026-11-27 and again on 2026-11-28 [game]. %ls, %S and
%s are where the game puts a name, `~mission(...)`, `~playerTrade(...)` and `~quantumLink(...)`
a value it fills in. **Only the ship channel shapes are seen in a log** [seen: the user's logs of
2026-11, samples/courier.log, run_a.log]; every other shape here is read from the game's text and
has never been seen in a log [game, not seen], so whether and how the game logs it is unverified.

The law (hud_law_*) [game, not seen]:

    hud_law_CrimeCommitted               "Crime Committed: %ls"                       the crime
    hud_law_CrimeCommitted_VictimName    "Crime Committed: %ls\\nagainst %ls"          crime, victim
    hud_law_charge_player_crime          "%ls committed %ls against you"              a player, crime
    hud_law_charge_player_crime_party    "Party member %ls committed %ls against you" a player, crime
    hud_law_Victim                       "Victim: %ls"                                the victim
    hud_law_PlayerAreaWarning            "Trespassing on %ls's Private Property\\n..." a player
    hud_law_TrespassPropertyWarning_Named "WARNING: %ls's Private Property. ..."      an owner
    hud_law_OrganizationControlledWarning "Trespassing in %s-Controlled Area ..."    an organization
    hud_law_OrgControlledHostileWarning   "Entering %s-Controlled Territory ..."     an organization
    hud_law_AreaAnnouncement              "%s-Controlled Area"                       an organization
    hud_law_InfractionWarning             "%ls"         what fills it is not known: a notice of one
                                                        word that can be a handle is not shown

Comms (comms_*). A suffix %s is "group '%S'" (comms_suffix_group) or "channel '%S'"
(comms_suffix_ship_channel, %S = "<ship> : <owner>"):

    comms_local_player_joined_auto       "You have joined %s."              [seen with a channel]
    comms_local_player_left              "You have left the %s."            [seen with a channel]
    comms_local_player_joined            "You have joined %S's %s."         a player
    comms_local_player_kicked            "You have been kicked from the %s."
    comms_member_left / _kicked          "%S has left the %s." / "%S has been kicked from the %s."
    comms_invite_accepted / _declined    "%S has joined the %s." / "%S has declined invitation to %s."
    comms_invite_received / _sent        "%S has invited you to their %s." / "%S invited to %s."
    comms_invite_sent_target             "Target player invited to %s."
    comms_invite_timeout                 "The invitation you sent to %S has timed out."
    comms_leader_changed                 "%S is now %s leader."             a player, a suffix
    comms_group_created / _disbanded     "Created %s." / "The %s has been disbanded."
    comms_channel_joined / _disconnected "Comms Channel Joined: %S" / "Comms Channel Disconnected: %S"
    comms_channel_invited                "Invited to Comms Channel: %S"
    comms_target_contact                 "Hail Target: %S"                  the contact hailed

The same in the mobiGlas (mobiGlas_ui_notification_*): "%S has accepted your invitation.",
"%S has declined your invitation.", "%S is now the party leader.", "%S is already in a party.",
"%S has accepted your party launch.", "Party launch received from party leader %S. ...",
"%S has sent you a contact request.", "You have added %S to your Contacts.", "Sent contact
request to %S", "%S has granted you access to their hangar. ...", "%S has revoked your access to
their hangar.", "%S has accepted your hangar invite." [game, not seen].

Toasts (notification_*): a title and a description, how the log would join them is unknown; the
dashboard reads "<title>: <description>", the description alone, and the title alone. Most
descriptions are a comms text (`notification_member_left_Desc = %s`); these carry their own name
[game, not seen]:

    notification_leader_toPU             "Party Launching" / "Initiated by %S"
    notification_party_launched          "Initiated by party leader %S."
    notification_party_launch_already_in_session  "Party Launch" / "%S is already in your instance."
    notification_party_member_connected / _disconnected  "%S connected." / "%S disconnected."
    notification_party_member_canceled_queue   "%S canceled their join queue."
    notification_party_leader_canceled_queue   "Join queue canceled by party leader %S."
    notification_party_member_started_QT_to_you  "%s has started to QT to your current location."
    notification_calibration_*           "Quantum Travel Calibration Started By <player>" (and
                                         Complete By, Cancelled By); "<player> is starting to
                                         calibrate coordinates towards <place>." and the like
    notification_PlayerTrade_*           "Currency Transfer Request" / "%s wants to send you %s %s";
                                         "Transfer Recieved" (sic) / "<player> has sent you: ...";
                                         "Transfer Sent" / "You sent <player>: ..."; "Transfer
                                         Failed" / "Your transfer to <player> has failed to send.";
                                         "The transfer from <player> has failed."
    notification_beacon_*, ServiceBeacon_*  "Beacon Accepted" / "<provider> accepted your <kind>
                                         contract."; "Provider Arrived" / "<provider> has arrived
                                         at your location."; "Contract Complete" / "Your <kind>
                                         contract's complete. Please rate <player>."; "Combat
                                         Assistance Request From: <player>. Payment: ..." and the
                                         escort, medical, refuel and transport requests
    ServiceBeacon_Revive_Detected_Notification  "Rescue Beacon Activated By: <player>. Payment: ...
                                         Distance: ..." (title "Medical Rescue Requested")
    hud_incapacitated_downedReviveRequestAccepted  "%s accepted the Rescue Beacon and is %s away."
    friend toasts (notification_invite_friend_*)  "Friend Request" / "Friend Added" / "Friend
                                         Request Declined", their descriptions empty in the game's
                                         text (filled in by code): "<title>: <name>" is read as a
                                         title with a bare name [inferred, not in the game's text]

Every toast title of these families (TOAST_TITLES) puts a notice in its family: a description
under one that no pattern reads is never shown as written.

Contracts that name a player (round 4) [game, not seen]. The game fills ~mission(InitiatorName)
with the player who set a service beacon, and ~mission(TargetName) of a player bounty (template
PVP_KillPlayerBounty) with the player hunted. A contract is one of these by its kind or its marker
names (ReviveBeacon, BeaconContractGenerator, NorthRock_PVP, ..._PVP) or by its title
(PLAYER_CONTRACT_TITLES). Its objectives of a known shape (PLAYER_OBJECTIVES, the objective
titles below, in their New and Complete forms) are worded without the name and the name is
learned; an objective of such a contract in any other shape is not shown (it is counted as
withheld), unless it is one of the game's own nameless objectives (NAMELESS_OBJECTIVES):

    ServiceBeacon_Revive_Obj_Title        "Rescue <player>"
    ServiceBeacon_Heal_Obj_Title          "Treat <player>"
    ServiceBeacon_Escort_Obj_Title        "Escort <player> until contract is completed."
    ServiceBeacon_PersonalTransport_Pickup_Obj_Title / _Delivery_Obj_Title  "Pick up <player>" /
                                          "Drop Off <player>"
    ServiceBeacon_CombatAssist_*_Obj_Title  "Protect <player>", "Avenge <player>.", "Go to
                                          <player>", "Eliminate <player>" (a beacon that was a trap)
    ShipRefuel_obj_short                  "Reach <ship>'s Beacon" (a ship: worded, nothing learned)
    bounty_obj_short_01 / _02             "Locate <target>" / "Neutralize <target>" (a player in a
                                          player bounty; which objectives that template uses is not
                                          in the text)
    northrock_bounty_PVP_title_001        contract title "Apprehend Suspect: <player>"
    northrock_bounty_prisoner_title_001   contract title "Escapee Bounty Assignment: <player>"

An objective of these shapes in a contract that is not known at all (no title, no marker: one
accepted in an earlier launch) is worded the same way when its slot can be a handle and is no
word of the game's notices; one in a contract known to be of another kind is left as it is.

The victim of the user's own crime can be anyone: a player, a civilian, a security force. The
charge notices ("... against you") carry the forgive-or-report choice the game gives for a
player's crime, so their first slot is a player [my reading of hud_law_charge_by_default].

None of these texts is kept with the other party's name in it: the parser words each one with the
name left out (events.NAMED_NOTICES). A notice of these families in a shape the parser does not
read is not shown either: it is worded as its family's neutral text and counted
(events.FAMILIES, state.session["withheld"]; a tip-shaped one in "withheld_tips"). The game's own
texts of these families that name nobody (NAMELESS_TEXTS, keyed by their global.ini key) are
shown as they are. A word from a name slot is learned as a name (so the scrubber also hides it in
other texts) only when `learnable()` says it can be a handle and is no word of the game; a word
the parser can only guess at (a shape it does not read) also has to pass `guessable()`: no word of
the game's notices (NOTICE_WORDS, "Share", "Contract", "Beacon"). When in doubt, nothing is
learned, and the notice is safe anyway.
"""
import re
from pathlib import Path

# Handles: letters, digits, "_" and "-", at least 3 characters [RSI's rule as the reviewer gave it;
# RSI's rules on where a "-" may stand are not known, so a leading, trailing or doubled "-" is
# accepted]. The scrubber's lookup of forgotten names (state._RUN_RE) is built from the same
# characters, so every name this accepts is also found again once forgotten (stage 3 review,
# round 3).
HANDLE_CHARS = "A-Za-z0-9_-"
HANDLE_RE = re.compile(r"^[%s]{3,60}$" % HANDLE_CHARS)
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
# who else a crime can be against, and the roles a victim of one word can have (stage 3 review,
# round 3: "Officer", "Captain" and "Turret" passed) [mine].
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
officer officers deputy deputies marshal marshals ranger rangers soldier soldiers trooper troopers
captain captains commander commanders admiral admirals lieutenant lieutenants sergeant sergeants
bodyguard bodyguards prisoner prisoners inmate inmates worker workers miner miners scientist
scientists doctor doctors nurse nurses medic medics passenger passengers hostage hostages witness
witnesses vendor vendors citizen citizens traveler travelers bandit bandits smuggler smugglers thug
thugs raider raiders scavenger scavengers mercenary mercenaries marauder marauders enforcer enforcers
grunt grunts gunner gunners turret turrets drone drones sentry sentries hunter hunters contractor
contractors operator operators engineer engineers technician technicians agent agents courier
couriers hauler haulers trader traders merchant merchants
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
    if _plural_of(low, game_words):
        return None
    return t


def _plural_of(low, game_words):
    """Is the word a plural of a game word or a stoplist word ("Drakes", "Golems", "Securities")?
    Such a word is not learned either (stage 3 review, round 3: they passed)."""
    if not low.endswith("s") or len(low) < 4:
        return False
    stems = [low[:-1]]
    if low.endswith("es"):
        stems.append(low[:-2])
    if low.endswith("ies"):
        stems.append(low[:-3] + "y")
    return any(s in game_words or s in STOPWORDS for s in stems)


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


# ---------------------------------------------------------------------- round 4: what a guess
# may learn, the game's nameless texts, the contracts that name a player

def _load_words():
    """NOTICE_WORDS from notice_words.txt beside this file (game text, see its header)."""
    path = Path(__file__).with_name("notice_words.txt")
    with open(path, encoding="utf-8") as f:
        return frozenset(w for line in f if not line.startswith("#") for w in line.split())


NOTICE_WORDS = _load_words()


def guessable(word, game_words):
    """The word, if a guess may learn it: `learnable()`, and no word of the game's notices nor a
    plural of one ("Share is unavailable if ..." taught "Share" as a handle: stage 3 review,
    round 4). For the fallback's candidates only; a name slot of a known shape uses learnable()."""
    t = learnable(word, game_words)
    if t is None:
        return None
    low = t.lower()
    if low in NOTICE_WORDS or _plural_of(low, NOTICE_WORDS):
        return None
    return t


# The game's own texts of the notice families that name nobody, as notice_text() makes them,
# keyed by their global.ini key [game, not seen]: shown as they are, never withheld (round 4:
# 58 of them were withheld and counted). Most are toast titles and descriptions; the
# missionManager_ and MG_ ones are mission texts a review paired into "<title>: <description>".
NAMELESS_TEXTS = {
    'chat_handle_not_in_convo': 'You are not in this conversation anymore.',
    'chat_notification_btn_tooltip': 'Pending Invitations',
    'comms_suffix_party': 'party',
    'dfm_ac_ui_NotificationPartyInvite': 'Squad Invite',
    'Frontend_shard_queue_canceled': 'Join queue canceled.',
    'Frontend_SoloPlay_Warning': 'Your party leader has yet to launch you into a server! Do you still wish to continue?',
    'hud_ActiveGroup': 'Group',
    'hud_Group1': 'Group 1',
    'hud_Group2': 'Group 2',
    'hud_incapacitated_downedReviveRequestAbandoned': 'Rescue attempt interrupted. Searching for additional assistance.',
    'hud_incapacitated_downedReviveRequestAccepted_Generic': 'Your Rescue Beacon has been accepted. Assistance is on the way.',
    'hud_incapacitated_downedReviveWasRequestedMessage': 'Rescue Beacon activated. Searching for available assistance.',
    'hud_Label_Group': 'GROUP',
    'hud_PowerContext_Allocation_HelpText': 'Adjust the POWER ALLOCATION to change the ratio of power assigned to the three power groups. NOTE: This is only active when there is insufficient power to cover all systems.',
    'hud_qt_group_leader': 'Group Leader',
    'MG_hurston_invite_desc': 'PLACEHOLDER',
    'MG_hurston_invite_title': 'Hurston Invite - PLACEHOLDER',
    'missionManager_Homestead01_Mission_Title': 'Investigate Distress Beacon',
    'missionManager_Homestead02_Mission_Title': 'Investigate New Distress Beacon',
    'missionManager_Homestead03_Mission_Title': 'Investigate Distress Beacon Cluster',
    'mobiGlas_ui_CreateBeacon_Heading': 'Create Service Beacon',
    'mobiGlas_ui_notification_Group_Created': 'Group created.',
    'mobiGlas_ui_notification_Group_Self_Kicked': 'You have been kicked from the group.',
    'mobiGlas_ui_notification_Group_Self_Left': 'You have left the group.',
    'mobiGlas_ui_notification_Hangar_Access_Title': 'Hangar invite',
    'mobiGlas_ui_notification_Party_Created': 'Party created',
    'mobiGlas_ui_notification_Party_Disband': 'Your party has disbanded.',
    'mobiGlas_ui_notification_Party_Launch_Failed': 'Party launch failed.',
    'mobiGlas_ui_notification_Party_Launch_InstanceNotFound': 'Party launch failed because instance was not found.',
    'mobiGlas_ui_notification_Party_Launch_NotInInstance': 'Party launch failed because you are currently not in an instance.',
    'mobiGlas_ui_notification_Party_Launch_NotInParty': 'Party launched failed because your are not in a party.',
    'mobiGlas_ui_notification_Party_Launch_NotLeader': 'Party launched failed because you are not the party leader.',
    'mobiGlas_ui_notification_Party_Launch_Sent': 'Party launch sent.',
    'mobiGlas_ui_notification_Party_Self_Kicked': 'You have been kicked from the party.',
    'mobiGlas_ui_notification_Party_Self_Left': 'You have left the party.',
    'mobiGlas_ui_notification_Party_Title': 'Party',
    'notification_beacon_accepted_title': 'Beacon Accepted',
    'notification_beacon_cancelled_title': 'Beacon Cancelled',
    'notification_beacon_personalTransport_detected_title': 'Transport Beacon Detected',
    'notification_beacon_providerArrived_title': 'Provider Arrived',
    'notification_group_disbanded_Desc': 'Leader Disbanded Party',
    'notification_group_disbanded_Title': 'Party Disbanded',
    'notification_invite_declined_Title': 'Invitation Declined',
    'notification_invite_failed_Title': 'Invite Failed',
    'notification_invite_lobby_Prompt': 'Accept Invitation?',
    'notification_invite_lobby_Title': 'Invited To Lobby',
    'notification_invite_received_Prompt': 'Accept Invitation?',
    'notification_invite_received_Title': 'Party Invite Received',
    'notification_invite_sent_Title': 'Invite Sent',
    'notification_invite_sent_to_target_Title': 'Invite Sent To',
    'notification_invite_timeout_Title': 'Invite Expired',
    'notification_leader_changed_Title': 'New Party Leader',
    'notification_leader_toPU_Prompt': 'Join Party In PU?',
    'notification_leader_toPU_Title': 'Party Launching',
    'notification_party_launch_accepted_Title': 'Party Launch Accepted',
    'notification_party_launch_already_in_session_Title': 'Party Launch',
    'notification_party_launch_declined_Title': 'Party Launch Declined',
    'notification_party_launch_failed_Title': 'Party Launch Failed',
    'notification_party_launch_full_Desc': 'Not enough room for Party',
    'notification_party_launch_not_in_party_Desc': 'You are not a Party Member',
    'notification_party_launch_not_in_party_Title': 'Party Launch Failed',
    'notification_party_launch_not_in_session_Desc': 'Not in a session',
    'notification_party_launch_not_in_session_Title': 'Party Launch Failed',
    'notification_party_launch_not_leader_Desc': 'You are not a Party Leader',
    'notification_party_launch_not_leader_Title': 'Party Launch Failed',
    'notification_party_launch_sent_notifications': 'Notifications sent to party members.',
    'notification_party_launch_sent_Desc': 'Notice sent to members',
    'notification_party_launch_sent_Title': 'Party Launch Sent',
    'notification_party_launch_session_not_found_Desc': 'Session not found',
    'notification_party_launch_session_not_found_Title': 'Party Launch Failed',
    'notification_party_launch_Title': 'Party Launch',
    'notification_party_session_full_Desc': 'Cannot Join With Party',
    'notification_PlayerTrade_Notification_RecipientSuccess_Title': 'Transfer Recieved',
    'notification_PlayerTrade_Notification_SenderFailure_Title': 'Transfer Failed',
    'notification_PlayerTrade_Notification_SenderSuccess_Title': 'Transfer Sent',
    'notification_PlayerTrade_TradeExpired_Desc': 'Your currency transfer request has expired.',
    'notification_PlayerTrade_TradeOffer_Title': 'Currency Transfer Request',
    'pause_OptionsPartyInvitesNotifications': 'Social - Party Invite Notifications',
    'ServiceBeacon_CombatAssist_GoTo_Obj_Marker': 'Respond to Beacon',
    'ServiceBeacon_NoLongerAvailable': 'Service Beacon Is No Longer Available',
    'ui_CancelMission': 'Cancel Beacon',
    'ui_error_title_0': 'Party Error',
    'ui_menu_lobby_error_46': "Cannot join party member's game server (or session) because it is currently full.",
    'ui_menu_lobby_error_48': 'Game server (or session) currently does not have enough space for all party members.',
    'ui_ShareMission_Unavailable': 'Share is unavailable if there are no eligible party members.',
    'ui_ShareMission_Unavailable_NotEligible': 'Contracts are shared only with eligible party members.',
    'ui_TransferFailed': 'Transfer Failed!',
}
NAMELESS = frozenset(NAMELESS_TEXTS.values())
# Nameless texts with a number in them [game: hud_incapacitated_downedReviveInsufficientFunds].
NAMELESS_NUMBER_RE = re.compile(
    r"^Rescue Beacon: Current Balance: [\d,.]{1,20} aUEC - Insufficient funds for activation\.?$")


def nameless(text):
    """Is the text one of the game's nameless texts, or a "<title>: <description>" of two? A
    title with an empty description ("Party Launch Failed:") counts as the title."""
    if text.endswith(":"):
        text = text[:-1].rstrip()
    if text in NAMELESS or NAMELESS_NUMBER_RE.match(text):
        return True
    head, sep, rest = text.partition(": ")
    return bool(sep) and head in NAMELESS and (rest in NAMELESS or NAMELESS_NUMBER_RE.match(rest) is not None)


# Which contracts name a player in their objectives (round 5) [game]:
# - service beacons: kind "service beacon" in reference/contracts.json (contract ReviveBeacon,
#   generator BeaconContractGenerator), the beacons' mission titles (ServiceBeacon_*_Mission_Title,
#   SB_Refuel_Answer_Mission_Title), the marker names ReviveBeacon, BeaconContractGenerator and
#   ServiceBeacon...; the objectives carry ~mission(InitiatorName), the player who set it;
# - player bounties: the four contracts of generator NorthRock_PVP (NorthRock_Bounty_PVP_Intro,
#   _General_PVP, _EscapedConvict_PVP, _EscapedConvict_PVP_Intro), all of template
#   PVP_KillPlayerBounty and type PVPMission, whose ~mission(TargetName) is a player, and their
#   titles (northrock_bounty_*_title_*, and the Bounty Hunters Guild's two certifications
#   BHG_Certification_Criminal_Title and _EscapedConvict_Title, which NorthRock_Bounty_General_PVP
#   uses). Not these: the Guild's other certifications (BountyHuntersGuild_Certification_*,
#   template Bounty, generator BountyHuntersGuild_KIllShip) and its FPS bounties, whose targets
#   are NPCs.
BEACON_TITLES = frozenset((
    "Medical Rescue", "Medical Assistance", "Combat Assistance", "Combat Assistance - LOW THREAT",
    "Combat Assistance - MODERATE THREAT", "Combat Assistance - HIGH THREAT",
    "Combat Assistance - CRITICAL THREAT", "Escort", "Personal Transport", "Refuel"))
BOUNTY_TITLES = frozenset((
    "Pro Tem Suspect Apprehension", "Pro Tem Suspect Apprehension (Reevaluation)",
    "Suspect Apprehension Certification", "Fugitive Recovery Certification",
    "Pro Tem Escapee Bounty Contract", "Pro Tem Escapee Bounty Contract (Reevaluation)"))
PLAYER_CONTRACT_TITLES = BEACON_TITLES | BOUNTY_TITLES
BEACON_MARKER_RE = re.compile(r"^(?:BeaconContractGenerator|ReviveBeacon|ServiceBeacon\w{0,80})$", re.I)
BOUNTY_MARKER_RE = re.compile(r"^NorthRock_PVP$|_PVP(?:_|$)", re.I)
PLAYER_KINDS = ("service beacon",)

# Contract titles with a player in them: (key, pattern, wording). The slot is learned when it is
# one word [game: northrock_bounty_PVP_title_001, northrock_bounty_prisoner_title_001].
PLAYER_TITLES = [(k, re.compile(p), w) for k, p, w in (
    ("northrock_bounty_PVP_title_001", r"^Apprehend Suspect: (.{1,200})$", "Apprehend Suspect: another player"),
    ("northrock_bounty_prisoner_title_001", r"^Escapee Bounty Assignment: (.{1,200})$",
     "Escapee Bounty Assignment: another player"),
)]
PLAYER_TITLE_WORDINGS = frozenset(w for _, _, w in PLAYER_TITLES)

# Objective titles with a player (or the beacon's ship) in them: (key, pattern, wording, the slot
# is a player). Matched on the objective's text without "OPTIONAL:"; one word per slot, so an
# objective of these words naming more than one word is not this shape [game, not seen].
PLAYER_OBJECTIVES = [(k, re.compile(p), w, who) for k, p, w, who in (
    ("ServiceBeacon_Revive_Obj_Title", r"^Rescue (\S{1,100})$", "Rescue the player who set the beacon", True),
    ("ServiceBeacon_Heal_Obj_Title", r"^Treat (\S{1,100})$", "Treat the player who set the beacon", True),
    ("ServiceBeacon_Escort_Obj_Title", r"^Escort (\S{1,100}) until contract is completed\.?$",
     "Escort the player who set the beacon until the contract is completed", True),
    ("ServiceBeacon_PersonalTransport_Pickup_Obj_Title", r"^Pick up (\S{1,100})$",
     "Pick up the player who set the beacon", True),
    ("ServiceBeacon_PersonalTransport_Delivery_Obj_Title", r"^Drop Off (\S{1,100})$",
     "Drop off the player who set the beacon", True),
    ("ServiceBeacon_CombatAssist_Protect_Obj_Title", r"^Protect (\S{1,100})$",
     "Protect the player who set the beacon", True),
    ("ServiceBeacon_CombatAssist_Avenge_Obj_Title", r"^Avenge (\S{1,100}?)\.?$",
     "Avenge the player who set the beacon", True),
    ("ServiceBeacon_CombatAssist_GoTo_Obj_Title", r"^Go to (\S{1,100})$", "Go to the player who set the beacon", True),
    ("ServiceBeacon_CombatAssist_Trap_Obj_Title", r"^Eliminate (\S{1,100})$",
     "Eliminate the player who set the beacon (a trap: they broke the beacon contract)", True),
    ("ShipRefuel_obj_short", r"^Reach (.{1,200}?)'s Beacon$", "Reach the ship's beacon", False),
    ("bounty_obj_short_01", r"^Locate (\S{1,100})$", "Locate the target", True),
    ("bounty_obj_short_02", r"^Neutralize (\S{1,100})$", "Neutralize the target", True),
    ("bounty_obj_long_02", r"^Locate and neutralize (\S{1,100}?)\.?$", "Locate and neutralize the target", True),
    ("bounty_obj_long_02_target01", r"^Locate and neutralize (\S{1,100}) at .{1,200}$",
     "Locate and neutralize the target", True),
)]
# The same shapes worded for a contract that is not a beacon (a player bounty) or not placed at
# all: "the target", never the beacon's words; in a contract not placed, nothing is learned.
NEUTRAL_OBJECTIVES = {k: w for k, w in (
    ("ServiceBeacon_Revive_Obj_Title", "Rescue the target"), ("ServiceBeacon_Heal_Obj_Title", "Treat the target"),
    ("ServiceBeacon_Escort_Obj_Title", "Escort the target until the contract is completed"),
    ("ServiceBeacon_PersonalTransport_Pickup_Obj_Title", "Pick up the target"),
    ("ServiceBeacon_PersonalTransport_Delivery_Obj_Title", "Drop off the target"),
    ("ServiceBeacon_CombatAssist_Protect_Obj_Title", "Protect the target"),
    ("ServiceBeacon_CombatAssist_Avenge_Obj_Title", "Avenge the target"),
    ("ServiceBeacon_CombatAssist_GoTo_Obj_Title", "Go to the target"),
    ("ServiceBeacon_CombatAssist_Trap_Obj_Title", "Eliminate the target"))}
# Objectives of these contracts that name nobody [game: SB_Refuel_Request_*_Obj_Title,
# bounty_obj_marker_01a and _02, bounty_fps_*_short_01, dfmcrusader_playerbounty_objective0*,
# ServiceBeacon_CombatAssist_GoTo_Obj_Marker].
NAMELESS_OBJECTIVES = frozenset((
    "Move to an Open Space.", "Stay at Current Location.", "Maintain Current Position.",
    "Reach Target's Location", "Neutralize", "Eliminate Hostiles To Draw Out Target",
    "Don't Harm Non-Combatants", "No Collateral Damage", "Locate the Outlaw", "Eliminate the Outlaw",
    "Claim Bounty", "Remove Criminal Record", "Respond to Beacon"))
WITHHELD_OBJECTIVE = "An objective the dashboard does not show (it may name a player)"
# A notice whose whole text is one word that can be a handle [game: hud_law_InfractionWarning is
# "%ls"; what fills it is not known].
ONE_WORD_WITHHELD = "A one-word notice the dashboard does not show (it may be a player's name)"


def player_contract(c):
    """"beacon" or "bounty" when a contract record names a player in its objectives (a service
    beacon, a player bounty), False when it is known to be another kind, None when nothing about
    it is known (no title, no marker: a contract accepted in an earlier launch)."""
    title = c.get("title")
    names = [n[:200] for n in (c.get("internal"), c.get("giver")) if isinstance(n, str)]
    if c.get("kind") in PLAYER_KINDS or title in BEACON_TITLES or any(BEACON_MARKER_RE.match(n) for n in names):
        return "beacon"
    if title in BOUNTY_TITLES or title in PLAYER_TITLE_WORDINGS or any(BOUNTY_MARKER_RE.search(n) for n in names):
        return "bounty"
    return False if (title or names) else None


def player_title(title):
    """(wording, slot) for a contract title with a player in it, else None."""
    for _key, rx, words in PLAYER_TITLES:
        m = rx.match(title)
        if m:
            return words, m.group(1)
    return None


def player_objective(text):
    """(wording, slot, the slot is a player, the neutral wording) for an objective of a known
    shape, else None. The neutral wording is the same as the wording for the bounty shapes."""
    for key, rx, words, who in PLAYER_OBJECTIVES:
        m = rx.match(text)
        if m:
            return words, m.group(1), who, NEUTRAL_OBJECTIVES.get(key, words)
    return None
