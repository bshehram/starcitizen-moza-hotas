"""Record to event: one small typed record per log marker (PLAN §3).

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES): several line patterns and the
notice-cleaning helper come from CSR's sc_livelog.py (commit ba6dad0). Everything else in this
file is this project's own.

Every pattern here was checked against the user's own logs [seen: the 69 logs of 2026-11 in
LIVE\\logbackups plus Game.log, read 2026-11-27]; counts are physical lines unless they say
notices. Markers PLAN §3 lists as absent from those logs (`granted control token`, `<Actor
Death>`) are not built on. Stage 3 adds the notices SURVEY.md recommends (a failed or withdrawn
contract or objective, the law group, pay): their texts are in the game's files and other tools
read them, but no log here has shown them yet, so each is marked unverified where it is defined.

Every event carries its session (the log's first line) and the byte offset of its first line:
together they are its identity (PLAN §7). `t` is the line's own UTC time in seconds since the
epoch, never the time it was read.

What an event may hold: other players' names (a killer, a ship channel's owner) stay in events
and the live feed only; nothing here keeps the Windows user name, the PC name, the account id,
session ids or server addresses, and the parser never captures them.
"""
import hashlib
import math
import re
from dataclasses import asdict, dataclass, fields
from typing import ClassVar, Optional

from .records import UNREADABLE, RecordReader


# --------------------------------------------------------------------------- event types

@dataclass(frozen=True, slots=True)
class Event:
    session: str
    offset: int
    t: float
    kind: ClassVar[str] = "event"

    def to_dict(self):
        d = {"kind": self.kind}
        d.update(asdict(self))
        return d

    @property
    def ident(self):
        return (self.session, self.offset)


def _event(kind):
    def wrap(cls):
        cls.kind = kind
        return dataclass(frozen=True, slots=True)(cls)
    return wrap


# Session and launch
@_event("session_start")
class SessionStart(Event):          # first line: BackupNameAttachment=" Build(n) 26 Nov 26 (15 11 12)"
    name: str                       # 'Build(13220821) 26 Nov 26 (15 11 12)': the backup file's name
    build: Optional[str]
    local: Optional[str]            # '26 Nov 26 (15 11 12)', the launch in the user's local time


@_event("game_version")
class GameVersion(Event):           # `FileVersion: 4.10.201.48085`
    version: str


@_event("joystick")
class Joystick(Event):              # `- Connected joystick0: <name>  {GUID}`, only at launch [seen]
    index: int                      # the game's 0 is the profile's js1
    name: str
    guid: Optional[str]


@_event("login")
class Login(Event):                 # `<Legacy login response> ... Handle[<handle>]`, once per launch
    handle: str


@_event("character")
class Character(Event):             # `<AccountLoginCharacterStatus_Character> ... geid <n> ...`
    player_id: str                  # geid = the player id on later lines; the account id is never read
    current: bool


@_event("profile_loaded")
class ProfileLoaded(Event):         # `%SAVEDATA%/Controls/Mappings/MOZA.xml loaded. Enjoy!`
    name: str


@_event("front_end")
class FrontEnd(Event):              # `[CSessionManager::RequestFrontEnd] Started - RequestFrontEndReason="..."`
    reason: str                     # ProcessBootRequest at launch, OnLobbyPostGameUnload after leaving


@_event("connecting")
class Connecting(Event):            # `[CSessionManager::ConnectCmd] Connect started!` (also Arena Commander)
    pass


@_event("join_server")
class JoinServer(Event):            # `<Join PU> address[..] port[..] shard[<shard>]`; the address is not kept
    shard: Optional[str]


@_event("spawned")
class Spawned(Event):               # `[CSessionManager::OnClientSpawned] Spawned!`: menu, world, respawn
    pass


@_event("disconnected")
class Disconnected(Event):          # `<Channel Disconnected>` / `<Channel Process Disconnection>`
    cause: int
    reason: str
    process: bool                   # True for the `Process Disconnection` twin


@_event("quit")
class Quit(Event):                  # `<SystemQuit> CSystem::Quit invoked with - cause=.., reason=..`
    cause: int
    reason: str


# Travel and places
@_event("quantum_target")
class QuantumTarget(Event):         # `<Player Selected Quantum Target - Local> ... selected point <CODE>`
    vehicle_class: Optional[str]
    vehicle_id: Optional[str]
    code: str


@_event("route_start")
class RouteStart(Event):            # `<Calculate Route> ... Projected Start Location is <name> for route to destination <CODE>`
    vehicle_id: Optional[str]
    start: str                      # a display name as the game prints it, not a code
    code: str


@_event("route_fuel")
class RouteFuel(Event):             # `<Calculate Route> ... Successfully calculated route to <CODE> fuel estimate <n>`
    vehicle_id: Optional[str]
    code: str
    fuel: float


@_event("quantum_arrived")
class QuantumArrived(Event):        # `<Quantum Drive Arrived - Arrived at Final Destination>`: can be another ship
    vehicle_class: Optional[str]
    vehicle_id: Optional[str]


@_event("inventory_location")
class InventoryLocation(Event):     # `<Update Inventory Location> ... Landing [a] -> [b]. Location [c] -> [d]`
    landing_from: str
    landing_to: str
    location_from: str
    location_to: str


@_event("location_inventory")
class LocationInventory(Event):     # `<RequestLocationInventory> ... Location[<code>]`: arrival, or storage opened
    code: str


@_event("planet_cells")
class PlanetCells(Event):           # PHYSICS INSTANCE STATS `  planet cells: <n> ... name: <body>`, n > 0
    body: str
    cells: int


@_event("terrain_loaded")
class TerrainLoaded(Event):         # `<InvalidateAllTerrainCells> Planet <body> invalidated...`: near, not at
    body: str


# Ships
@_event("ship_retrieved")
class ShipRetrieved(Event):         # `SetVehicleSpawningInformations - VehicleEntityId: [<id>], LandingArea: ...`
    vehicle_id: str
    hangar: Optional[str]           # 'XL Hangar'; the owner's handle in front of it is dropped


@_event("seat_left")
class SeatLeft(Event):              # `<Vehicle Control Flow> ...ClearDriver ... '<CLASS>_<id>' [<id>]`
    vehicle_class: str
    vehicle_id: str


@_event("vehicle_destroyed")
class VehicleDestroyed(Event):      # `<Vehicle Destroyed>`: any ship nearby, so match the id
    vehicle_class: str
    vehicle_id: str
    owner_id: str
    reason: str
    level_from: int
    level_to: int
    killer: str                     # a player's or NPC's name: live feed only, never a summary
    killer_id: str
    driver_id: Optional[str] = None  # 0 when nobody sits in it [seen]; kept for stage 3's tally


@_event("fatal_collision")
class FatalCollision(Event):        # `<FatalCollision> Fatal Collision occured for vehicle <CLASS>_<id> [...]`
    vehicle_class: str
    vehicle_id: str
    zone: Optional[str]
    player_pilot: bool


@_event("stowed")
class Stowed(Event):                # `[STOWING ON UNREGISTER] ... stow current vehicle [<id>]`: every hangar around
    vehicle_id: str
    landing_area: str


# Body and health
@_event("thrown_out")
class ThrownOut(Event):             # `<[ActorState] Dead> ... Actor '<name>' ... ejected from zone '<CLASS>_<id>'`
    actor: str
    vehicle_class: Optional[str]
    vehicle_id: Optional[str]


@_event("item_lost")
class ItemLost(Event):              # `... PopulateItemPortForItemRecoveryEntitlement]> Item '...'`, one per item
    item_class: str
    port: Optional[str]


# Missions
@_event("mission_ended")
class MissionEnded(Event):          # `<EndMission> ... MissionId[..] ... CompletionType[..] Reason[..]`
    mission_id: str
    completion: str
    reason: Optional[str]


@_event("mission_marker")
class MissionMarker(Event):         # `<CLocalMissionPhaseMarker::CreateMarker> ... missionId [..], generator name [..], contract [..]`
    mission_id: str
    giver: str
    contract: str


# Shops and trade
@_event("shop_buy")
class ShopBuy(Event):               # `SendShopBuyRequest ... shopName[..] client_price[..] itemName[..] quantity[..]`
    shop: str
    item: str
    price: float
    quantity: Optional[int]


@_event("shop_sell")
class ShopSell(Event):
    shop: str
    item: str
    price: float
    quantity: Optional[int]


@_event("shop_result")
class ShopResult(Event):            # `RmShopFlowResponse ... result[Success] type[Buying]`
    shop: Optional[str]
    result: str
    trade: Optional[str]            # 'Buying', 'Selling', or None on the short form


@_event("commodity_sell")
class CommoditySell(Event):         # `SendCommoditySellRequest ... amount[..] resourceGUID[..] quantity[..]`
    shop: str
    resource_id: str
    amount: float
    quantity: str                   # as logged: a bare number (unit not stated)
    box: Optional[str]


@_event("commodity_buy")
class CommodityBuy(Event):          # `SendCommodityBuyRequest ... price[..] resourceGUID[..] quantity[3200.000000 cSCU]`
    shop: str
    resource_id: str
    price: float
    quantity: str                   # as logged, with its unit


@_event("refinery_sell")
class RefinerySell(Event):          # `OnRefineryRequest ... shopName[SCShop_RefineryAdmin_ORE]`: no amount logged
    shop: str


@_event("rental")
class Rental(Event):                # `SendRentalRequest ... client_price[..] itemName[..]`
    shop: str
    item: str
    price: float


@_event("shop_offer")
class ShopOffer(Event):             # `LoadShopInventoryData ... AddingCommodityBox ... commodityName[..]`
    shop: str
    commodity: str


@_event("fabricator_opened")
class FabricatorOpened(Event):      # `<ReuseChannel> ... blueprint_library.v1.BlueprintLibraryService`
    pass


@_event("storage_count")
class StorageCount(Event):          # `Freight Inventory Grid InventoryDataRequest Successful for ... Item Count:[n]`
    location_id: str
    count: int


@_event("gadget_placed")
class GadgetPlaced(Event):          # `<[ActorState] Place> ... placed 'Mining_Gadget_<name>_<id>' on entity 'MineableRock_...'`
    gadget: str
    rock: Optional[str]             # None when placed loosely in the environment


@_event("screenshot")
class Screenshot(Event):            # `ScreenShot: ScreenShots/<name>.jpg`
    name: str


# HUD notices (`<SHUDEvent_OnNotification> Added notification "<text>" [<n>]`); only that first
# form is read, so a notice logged three times counts once.
@_event("notice")
class Notice(Event):                # any notice without a kind of its own
    text: str
    hint: bool                      # a tutorial tip ("Topic: a long sentence")
    names: tuple = ()               # words that may be a player's name (a crime notice not read)


@_event("contract_accepted")
class ContractAccepted(Event):
    title: str
    mission_id: Optional[str]


@_event("contract_complete")
class ContractComplete(Event):
    title: str
    mission_id: Optional[str]


@_event("objective_new")
class ObjectiveNew(Event):
    text: str
    mission_id: Optional[str]
    objective_id: Optional[str]


@_event("objective_complete")
class ObjectiveComplete(Event):
    text: str
    mission_id: Optional[str]
    objective_id: Optional[str]


# Stage 3, from dashboard/SURVEY.md. None of these is in the project's record of the user's logs:
# each text is in the game's global.ini [game] and read by other tools [ref], so every line shape
# is unverified until a session logs it (SURVEY.md, "To check in the user's first real sessions").
@_event("contract_failed")
class ContractFailed(Event):        # "Contract Failed: <title>" (mobiGlas_ui_MissionEvent_Fail)
    title: str
    mission_id: Optional[str]


@_event("contract_withdrawn")
class ContractWithdrawn(Event):     # "Contract Withdrawn:  <title>" (..._MissionEvent_Deactivate)
    title: str
    mission_id: Optional[str]


@_event("objective_failed")
class ObjectiveFailed(Event):       # "Objective Failed: <text>": not the contract's end [ref]
    text: str
    mission_id: Optional[str]
    objective_id: Optional[str]


@_event("objective_withdrawn")
class ObjectiveWithdrawn(Event):    # "Objective Withdrawn: <text>"
    text: str
    mission_id: Optional[str]
    objective_id: Optional[str]


@_event("reward")
class Reward(Event):                # "Awarded 50250 aUEC" (text_UEC_reward_text): legacy contracts only [ref]
    amount: float
    mission_id: Optional[str]


@_event("crimestat")
class CrimeStat(Event):             # "CrimeStat Rating Increased" (text_hostility_Wanted)
    up: bool


@_event("crime")
class CrimeCommitted(Event):        # "Crime Committed: Assault\nagainst <victim>" (hud_law_CrimeCommitted)
    crime: str
    victim: Optional[str]           # anyone, a player too: the state keeps no text with it (law.py)


@_event("crime_against_you")
class CrimeAgainstYou(Event):       # "[Party member ]<name> committed Assault against you" (hud_law_charge_player_crime)
    attacker: str                   # another player's name: the state keeps no text with it
    crime: str


@_event("fined")
class Fined(Event):                 # "Fined 1500 UEC" (hud_law_FinePaid)
    amount: float


@_event("impounded")
class Impounded(Event):             # "Vehicle Impounded: <ship>" (hud_law_ImpoundingNotification)
    vehicle: str


@_event("monitored_down")
class MonitoredDown(Event):         # "Monitored Space Down" / "Monitored Space Restored"
    down: bool


@_event("hangar_queue")
class HangarQueue(Event):           # "Joined hangar queue.\nYour place: 2. Max. estimated wait: 200.000000 s."
    place: Optional[int]
    wait_s: Optional[float]


@_event("hangar_ready")
class HangarReady(Event):           # "Hangar Request Completed"
    pass


@_event("refinery_done")
class RefineryDone(Event):          # "A Refinery Work Order has been Completed at <station>" / "<n> ... Orders have been"
    count: int
    station: str


@_event("blueprint")
class BlueprintReceived(Event):     # "Received Blueprint: <name>"
    name: str


@_event("quantum_obstructed")
class QuantumObstructed(Event):     # "Quantum Travel: Your destination is obstructed ..."
    pass


@_event("jurisdiction")
class Jurisdiction(Event):          # "Entered <name> Jurisdiction"
    name: str


@_event("armistice")
class Armistice(Event):             # "Entering Armistice Zone ..." / "Leaving Armistice Zone ..."
    inside: bool


@_event("monitored")
class MonitoredSpace(Event):        # "Entered Monitored Space" / "Exited Monitored Space"
    inside: bool


@_event("channel_joined")
class ChannelJoined(Event):         # "You have joined channel '<Ship name> : <owner>'."
    name: str
    owner: str                      # the user's handle, or another player's: live feed only


@_event("channel_left")
class ChannelLeft(Event):           # "You have left the channel '<Ship name> : <owner>'."
    name: str
    owner: str


@_event("incapacitated")
class Incapacitated(Event):         # "Incapacitated: While incapacitated, ..."
    pass


@_event("emergency")
class EmergencyServices(Event):     # "Standby, Local Emergency Services Are En Route"
    pass


@_event("injury")
class Injury(Event):                # "Severe Injury Detected - Torso - Tier 1 Treatment Required"
    severity: str
    part: str
    tier: int


@_event("regen_set")
class RegenSet(Event):              # "Regeneration - Location: ..."
    pass


@_event("medical_bed")
class MedicalBed(Event):            # "Medical Bed: The bed has restored ..."; repeats every 120 s [seen: 34 gaps]
    pass


@_event("unreadable")
class Unreadable(Event):            # a line of interest that could not be read; it is skipped
    what: str                       # why, briefly: the exception's name and the line's key
    # `t` is the time of the last readable record before it (the line's own may be the problem)


EVENT_TYPES = {cls.kind: cls for cls in [
    SessionStart, GameVersion, Joystick, Login, Character, ProfileLoaded, FrontEnd, Connecting,
    JoinServer, Spawned, Disconnected, Quit, QuantumTarget, RouteStart, RouteFuel, QuantumArrived,
    InventoryLocation, LocationInventory, PlanetCells, TerrainLoaded, ShipRetrieved, SeatLeft,
    VehicleDestroyed, FatalCollision, Stowed, ThrownOut, ItemLost, MissionEnded, MissionMarker,
    ShopBuy, ShopSell, ShopResult, CommoditySell, CommodityBuy, RefinerySell, Rental, ShopOffer,
    FabricatorOpened, StorageCount, GadgetPlaced, Screenshot, Notice, ContractAccepted,
    ContractComplete, ObjectiveNew, ObjectiveComplete, ContractFailed, ContractWithdrawn,
    ObjectiveFailed, ObjectiveWithdrawn, Reward, CrimeStat, CrimeCommitted, CrimeAgainstYou, Fined,
    Impounded, MonitoredDown, HangarQueue, HangarReady, RefineryDone,
    BlueprintReceived, QuantumObstructed, Jurisdiction, Armistice, MonitoredSpace, ChannelJoined,
    ChannelLeft, Incapacitated, EmergencyServices, Injury, RegenSet, MedicalBed, Unreadable]}


def event_from_dict(d):
    """The inverse of Event.to_dict (for replays and tests). A field added later with a default
    (VehicleDestroyed.driver_id) may be missing from an older dict."""
    cls = EVENT_TYPES[d["kind"]]
    return cls(**{f.name: tuple(d[f.name]) if isinstance(d[f.name], list) else d[f.name]
                  for f in fields(cls) if f.name in d})


# --------------------------------------------------------------------------- session identity

# Bounded runs of space, on at most 200 characters (session_id slices): a 60 KB first line of
# spaces made the unbounded form backtrack for minutes (stage 3 review).
SESSION_RE = re.compile(r'^"\s{0,10}(Build\((\d{1,12})\)\s{1,10}([^"]{0,100}?))\s{0,10}"')


def session_id(first_line):
    """A session's id from its log's first line (str or bytes): the backup name the game gives it,
    e.g. 'Build(13220821) 26 Nov 26 (15 11 12)', the same as the backup file's name without
    'Game ' and '.log'. Any other first line gets a short hash of itself."""
    if isinstance(first_line, bytes):
        first_line = first_line.decode("utf-8", "replace")
    i = first_line.find("BackupNameAttachment=")
    if i >= 0:
        m = SESSION_RE.match(first_line[i + len("BackupNameAttachment="):][:200])
        if m:
            return m.group(1)
    return "log-" + hashlib.sha1(first_line.encode("utf-8", "replace")).hexdigest()[:12]


# --------------------------------------------------------------------------- notice text

# From CSR sc_livelog.py lines 16 and 45 (NOTIF_RE, NOTIF_ML_RE): the notice text and its id.
# Changed: anchored at the start of the record's text.
NOTICE_RE = re.compile(r'^Added notification "(.*?)" \[(\d+)\]', re.S)
NOTICE_OPEN_RE = re.compile(r'^Added notification "(.*)', re.S)
# From CSR sc_livelog.py line 36 (NOTIF_MISSION_RE). Changed: upper-case hex accepted too.
NOTICE_MISSION_RE = re.compile(r"MissionId: \[([0-9a-fA-F-]{1,40})\], ObjectiveId: \[([^\]]{0,200})\]")
# From CSR sc_livelog.py lines 84-90 (`clean`): the markup a community language pack adds
# (PLAN §3). Changed: the patterns joined into one, and the rank markup bounded (40 characters,
# no "[" inside): unbounded, a notice of 60 KB of "[" took 43 s (stage 3 review).
MARKUP_RE = re.compile(r"</?EM\d>|\[BP\]\*?|\[[^\]\[]{0,40}\bRep\]\*?")


def notice_text(raw):
    """A notice as the player read it: markup removed, line breaks and runs of spaces made one
    space, and the trailing ': ' the game adds to every notice taken off.
    From CSR sc_livelog.py lines 84-90 (`clean`), the same steps in the same order."""
    t = MARKUP_RE.sub("", raw).replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip(":").strip()


def real_mission(mid):
    """Notices outside a mission carry an all-zero MissionId [seen].
    From CSR sc_livelog.py lines 117-119 (`real_mid`). Changed: returns the id or None."""
    return mid if mid and mid.strip("0-") else None


# --------------------------------------------------------------------------- handlers

# Every pattern below is bounded (stage 3 review: "no line may stall the reader"). A record's text
# is cut to MAX_TEXT before any of them runs; on top of that, no lazy run, class repeat or
# optional group may scan the whole text again from each of many starting points, so each one
# costs about the length of the text, whatever it holds. A number is left unbounded where it
# cannot backtrack (`\d+` then a fixed character), so an absurd one still reaches _num() and
# makes its line unreadable instead of silently dropping it. A real line was never longer than
# 1,181 bytes [seen: 69 logs of 2026-11].
VEHICLE_RE = re.compile(r"\| ([A-Za-z0-9_]{1,120}?)_(\d{1,20})\[(\d{1,20})\]\|")
# From CSR sc_livelog.py line 51 (QT_SEL_RE). Changed: without its first word, and bounded.
QT_SELECT_RE = re.compile(r"selected point (\S{1,200}) as their destination")
ROUTE_START_RE = re.compile(r"Projected Start Location is (.{1,200}?) for route to destination (\S{1,200})")
# From CSR sc_livelog.py line 52 (QT_ROUTE_RE). Changed: bounded.
ROUTE_FUEL_RE = re.compile(r"Successfully calculated route to (\S{1,200}) fuel estimate ([\d.]+)")
# From CSR sc_livelog.py line 33 (LOGIN_RE). Changed: the login words in front.
LOGIN_RE = re.compile(r"User Login Success - Handle\[([^\]]{1,100})\]")
CHARACTER_RE = re.compile(r"\bgeid (\d{1,20})\b.{0,300}?\bstate (\w{1,40})")
FRONT_RE = re.compile(r'^Started - RequestFrontEndReason="([^"]*)"')
SHARD_RE = re.compile(r"\bshard\[([^\]]{0,200})\]")
DISCONNECT_RE = re.compile(r'^cause=(\d+) reason="([^"]*)"')
QUIT_RE = re.compile(r"cause=(\d+), reason=([^,]*)")
JOYSTICK_RE = re.compile(r"^(\d+):\s*(.*)$", re.S)
JOYSTICK_GUID_RE = re.compile(r"\{([0-9A-Fa-f-]{1,64})\}$")
INV_LOC_RE = re.compile(r"Landing \[(\d+)\] -> \[(\d+)\]\. Location \[(\d+)\] -> \[(\d+)\]")
# From CSR sc_livelog.py line 29 (PLACE_RE). Changed: the player part left out, bounded.
LOC_INV_RE = re.compile(r"requested inventory for Location\[([^\]]{1,200})\]")
SPAWN_INFO_RE = re.compile(r"VehicleEntityId: \[(\d+)\](?:, LandingArea: (.*))?", re.S)
SEAT_RE = re.compile(r"ClearDriver: .{0,300}?releasing control token for '([A-Za-z0-9_]{1,120}?)_(\d{1,20})' \[(\d{1,20})\]")
# From CSR sc_livelog.py lines 20-23 (VKILL_RE). Changed: the tag left out, `[^']` for the name,
# the driver's id captured (stage 3), and bounded.
DESTROYED_RE = re.compile(
    r"Vehicle '[^']{0,200}' \[(\d{1,20})\] class '([^']{1,200})' \(owner player \[(\d{1,20})\], driver \[(\d{1,20})\]\) "
    r"destroyed: reason \[(\w{1,40})\] level \[(\d+)\] -> \[(\d+)\].{0,300}?killer '([^']{0,200})' \[(\d{1,20})\]")
FATAL_RE = re.compile(r"for vehicle ([A-Za-z0-9_]{1,120}?)_(\d{1,20}) \[[^\]]{0,300}?Zone: ([^,\]]{0,200}), PlayerPilot: (\d)")
STOW_RE = re.compile(r"\[STOWING ON UNREGISTER\] (.{0,300}?) \[\d{1,20}\] - Attempting to stow current vehicle \[(\d{1,20})\]")
THROWN_RE = re.compile(r"Actor '([^']{0,200})' \[\d{1,20}\] ejected from zone '([A-Za-z0-9_]{1,120}?)_(\d{1,20})' \[(\d{1,20})\]")
ITEM_LOST_RE = re.compile(r"Item '[^']{0,300}? - Class\(([^)]{0,200})\).{0,300}?Port Name '([^']{0,200})'")
# From CSR sc_livelog.py line 35 (MISSION_RE). Changed: the reason captured too, and bounded.
END_MISSION_RE = re.compile(r"MissionId\[([^\]]{1,100})\].{0,300}?CompletionType\[([^\]]{1,50})\](?: Reason\[([^\]]{0,200})\])?")
MARKER_RE = re.compile(r"missionId \[([^\]]{1,100})\], generator name \[([^\]]*)\], contract \[([^\]]*)\]")
# Shop and commodity lines: each field found on its own (one linear search each), not one
# pattern with several lazy runs between them, which a line with many "shopName[" and no
# "itemName[" made scan the text again from every one of them.
FIELD_RES = {name: re.compile(r"\b%s\[([^\]]*)\]" % name) for name in
             ("shopName", "client_price", "itemName", "quantity", "amount", "price", "resourceGUID",
              "result", "type", "commodityName")}
BOX_RE = re.compile(r"boxSize\[([\d.]{1,30})\] \| unitAmount\[(\d{1,10})\]")
STORAGE_RE = re.compile(r"InventoryDataRequest Successful for .{0,300}?Inventory\[\d{1,20}:Location:(\d{1,20})\].{0,300}?Item Count:\[(\d+)\]")
GADGET_RE = re.compile(r"placed '(Mining_Gadget_[A-Za-z0-9_]{1,120}?)_\d{1,20}' \[\d{1,20}\] (?:on entity '([A-Za-z0-9_]{1,120}?)_\d{1,20}'|loosely)")
CELLS_RE = re.compile(r"^\s*(\d+) .{0,300}?name: (\S{1,200})")
TERRAIN_RE = re.compile(r"Planet (\S{1,200}) invalidated")
OWNER_RE = re.compile(r"^.*?'s\s+(\S.*)$", re.S)     # "<owner>'s XL Hangar": the owner is dropped
TEAM_GROUPS_RE = re.compile(r"(?:\[[^\[\]]*\])+")
MAX_TEXT = 2048           # a record's text, before any pattern (the longest real line: 1,181 bytes)
MAX_FIELD = 200           # a marker's generator and contract names: real ones are under 80


def strip_team_tail(text):
    """`text` without the team tags it ends with ("XL Hangar [Team_GameServices][ASOP]" -> "XL
    Hangar"). Linear: one search from the last "[Team_" (a pattern anchored at the end with a
    repeated group backtracked over every group from every start)."""
    s = text.rstrip()
    i = s.rfind("[Team_")
    if i >= 0 and TEAM_GROUPS_RE.fullmatch(s, i):
        return s[:i].rstrip()
    return s


def _field(name, text):
    m = FIELD_RES[name].search(text)
    return m.group(1) if m else None


MAX_DIGITS = 30     # longer than any number in the user's logs [seen: the longest are 13-digit ids]


def _num(text):
    """A float from the log, or ValueError, which makes the line unreadable: never inf or nan,
    and never from an absurdly long string (400 digits would become inf)."""
    if text is None:
        return None
    if len(text) > MAX_DIGITS:
        raise ValueError("number too long")
    x = float(text)
    if not math.isfinite(x):
        raise ValueError("number not finite")
    return x


def _int(text):
    """An int from the log, or ValueError for an absurdly long string."""
    if text is None:
        return None
    if len(text) > MAX_DIGITS:
        raise ValueError("number too long")
    return int(text)


def _vehicle(text):
    m = VEHICLE_RE.search(text)
    return (m.group(1), m.group(3)) if m else (None, None)


def _h_session(rec, base):
    name = session_id("BackupNameAttachment=" + rec.text)
    m = SESSION_RE.match(rec.text[:200])
    return SessionStart(name, base[1], base[2], name, m.group(2) if m else None,
                        m.group(3) if m else None)


def _h_version(rec, base):
    return GameVersion(*base, rec.text.strip())


def _h_joystick(rec, base):
    # The name and its {GUID} split by hand: the one-pattern form (a lazy name, optional spaces,
    # an optional GUID, spaces, end) backtracked over every run of spaces (stage 3 review).
    m = JOYSTICK_RE.match(rec.text)
    if m:
        rest = m.group(2).strip()
        g = JOYSTICK_GUID_RE.search(rest)
        guid = g.group(1) if g else None
        name = rest[:g.start()].rstrip() if g else rest
        return Joystick(*base, _int(m.group(1)), name, guid)


def _h_login(rec, base):
    m = LOGIN_RE.search(rec.text)
    if m:
        return Login(*base, m.group(1))


def _h_character(rec, base):
    m = CHARACTER_RE.search(rec.text)
    if m:
        return Character(*base, m.group(1), m.group(2) == "STATE_CURRENT")


def _h_profile(rec, base):
    m = re.match(r"^(.+?) loaded\b", rec.text)
    if m:
        return ProfileLoaded(*base, m.group(1))


def _h_front(rec, base):
    m = FRONT_RE.match(rec.text)
    if m:
        return FrontEnd(*base, m.group(1))


def _h_connect(rec, base):
    if rec.text.startswith("Connect started"):
        return Connecting(*base)


def _h_spawned(rec, base):
    if rec.text.startswith("Spawned"):
        return Spawned(*base)


def _h_join(rec, base):
    m = SHARD_RE.search(rec.text)
    return JoinServer(*base, m.group(1) if m else None)


def _disconnect(process):
    def handler(rec, base):
        m = DISCONNECT_RE.match(rec.text)
        if m:
            return Disconnected(*base, _int(m.group(1)), m.group(2), process)
    return handler


def _h_quit(rec, base):
    m = QUIT_RE.search(rec.text)
    if m:
        return Quit(*base, _int(m.group(1)), m.group(2).strip())
    return Quit(*base, 0, "")


def _h_qt_target(rec, base):
    m = QT_SELECT_RE.search(rec.text)
    if m:
        return QuantumTarget(*base, *_vehicle(rec.text), m.group(1))


def _h_route(rec, base):
    m = ROUTE_FUEL_RE.search(rec.text)
    if m:
        return RouteFuel(*base, _vehicle(rec.text)[1], m.group(1), _num(m.group(2)))
    m = ROUTE_START_RE.search(rec.text)
    if m:
        return RouteStart(*base, _vehicle(rec.text)[1], m.group(1), m.group(2))


def _h_arrived(rec, base):
    return QuantumArrived(*base, *_vehicle(rec.text))


def _h_inv_location(rec, base):
    m = INV_LOC_RE.search(rec.text)
    if m:
        return InventoryLocation(*base, *m.groups())


def _h_loc_inventory(rec, base):
    m = LOC_INV_RE.search(rec.text)
    if m and not m.group(1).startswith("INVALID"):
        return LocationInventory(*base, m.group(1))


def _h_cells(rec, base):
    m = CELLS_RE.match(rec.text)
    if m and _int(m.group(1)) > 0:
        return PlanetCells(*base, m.group(2), _int(m.group(1)))


def _h_terrain(rec, base):
    m = TERRAIN_RE.search(rec.text)
    if m:
        return TerrainLoaded(*base, m.group(1))


def _h_spawn_info(rec, base):
    m = SPAWN_INFO_RE.search(rec.text)
    if not m:
        return None
    hangar = None
    if m.group(2):
        area = strip_team_tail(m.group(2))
        owned = OWNER_RE.match(area)
        if owned:                           # "<handle>'s\nXL Hangar", or all on one line
            hangar = owned.group(1).strip() or None
        elif area.rstrip().endswith("'s"):  # the hangar piece never arrived
            hangar = None
        else:
            hangar = re.sub(r"\s*\[\d+\]", "", area).strip() or None
    return ShipRetrieved(*base, m.group(1), hangar)


def _h_seat(rec, base):
    m = SEAT_RE.search(rec.text)
    if m:
        return SeatLeft(*base, m.group(1), m.group(3))


def _h_destroyed(rec, base):
    m = DESTROYED_RE.search(rec.text)
    if m:
        return VehicleDestroyed(*base, m.group(2), m.group(1), m.group(3), m.group(5),
                                _int(m.group(6)), _int(m.group(7)), m.group(8), m.group(9), m.group(4))


def _h_fatal(rec, base):
    m = FATAL_RE.search(rec.text)
    if m:
        return FatalCollision(*base, m.group(1), m.group(2), m.group(3).strip() or None,
                              m.group(4) == "1")


def _h_stow(rec, base):
    m = STOW_RE.search(rec.text)
    if m:
        return Stowed(*base, m.group(2), m.group(1))


def _h_thrown(rec, base):
    m = THROWN_RE.search(rec.text)
    if m:
        return ThrownOut(*base, m.group(1), m.group(2), m.group(4))


def _h_item_lost(rec, base):
    m = ITEM_LOST_RE.search(rec.text)
    if m:
        return ItemLost(*base, m.group(1), m.group(2) or None)


def _h_end_mission(rec, base):
    m = END_MISSION_RE.search(rec.text)
    if m:
        return MissionEnded(*base, m.group(1), m.group(2), m.group(3))


def _h_marker(rec, base):
    m = MARKER_RE.search(rec.text)
    if m:
        # Cut where they are parsed: no real generator or contract name is near this, and the
        # contract lookup runs patterns over them (a 60 KB marker took 8.9 s, stage 3 review).
        return MissionMarker(*base, m.group(1), m.group(2)[:MAX_FIELD], m.group(3)[:MAX_FIELD])


def _shop(cls):
    def handler(rec, base):
        shop, price, item = (_field(k, rec.text) for k in ("shopName", "client_price", "itemName"))
        if shop is not None and price is not None and item is not None:
            q = _field("quantity", rec.text)
            qty = _int(q) if q and q.isdigit() else None
            return cls(*base, shop, item, _num(price), qty)
    return handler


def _h_shop_result(rec, base):
    result = _field("result", rec.text)
    if result is not None:
        return ShopResult(*base, _field("shopName", rec.text), result, _field("type", rec.text))


def _h_commodity_sell(rec, base):
    shop, amount, rid, qty = (_field(k, rec.text) for k in ("shopName", "amount", "resourceGUID", "quantity"))
    if None not in (shop, amount, rid, qty):
        b = BOX_RE.search(rec.text)
        box = "%s x %s" % (b.group(2), b.group(1)) if b else None
        return CommoditySell(*base, shop, rid, _num(amount), qty, box)


def _h_commodity_buy(rec, base):
    shop, price, rid, qty = (_field(k, rec.text) for k in ("shopName", "price", "resourceGUID", "quantity"))
    if None not in (shop, price, rid, qty):
        return CommodityBuy(*base, shop, rid, _num(price), qty)


def _h_refinery_sell(rec, base):
    shop = _field("shopName", rec.text)
    if shop is not None and "SShopRefineryRequest" in rec.text:
        return RefinerySell(*base, shop)


def _h_rental(rec, base):
    shop, price, item = (_field(k, rec.text) for k in ("shopName", "client_price", "itemName"))
    if shop is not None and price is not None and item is not None:
        return Rental(*base, shop, item, _num(price))


def _h_offer(rec, base):
    shop, commodity = _field("shopName", rec.text), _field("commodityName", rec.text)
    if shop is not None and commodity is not None:
        return ShopOffer(*base, shop, commodity)


def _h_reuse_channel(rec, base):
    if "blueprint_library" in rec.text and "BlueprintLibraryService" in rec.text:
        return FabricatorOpened(*base)


def _h_storage(rec, base):
    m = STORAGE_RE.search(rec.text)
    if m:
        return StorageCount(*base, m.group(1), _int(m.group(2)))


def _h_gadget(rec, base):
    m = GADGET_RE.search(rec.text)
    if m:
        return GadgetPlaced(*base, m.group(1), m.group(2))


def _h_screenshot(rec, base):
    name = rec.text.strip().replace("\\", "/").rsplit("/", 1)[-1]
    if name:
        return Screenshot(*base, name)


# Notices: the text decides the kind. Order matters only where two patterns could both match.
# From CSR sc_livelog.py, with each pattern split per kind and anchored on the cleaned text:
# the contract notices from line 17 (CONTRACT_NOTIF_RE; `Failed` left out there, and added in
# stage 3 with this project's own patterns below, as the survey's other kinds are), the
# objective notices from line 53 (OBJ_RE; only the two kinds in the user's logs), the
# jurisdiction notice from line 18 (JURIS_RE), the armistice notices from lines 395-400, the
# blueprint notice from line 28 (BLUEPRINT_RE), and the injury notice from line 19 (INJURY_RE).
def _amount(text):
    """'50,250' or '50250' -> 50250.0 (ValueError makes the line unreadable, as elsewhere)."""
    return _num(text.replace(",", ""))


NOTICE_KINDS = [
    (re.compile(r"^Contract Accepted:\s*(.+)$"), lambda b, m, mid, oid: ContractAccepted(*b, m.group(1), mid)),
    (re.compile(r"^Contract Complete:\s*(.+)$"), lambda b, m, mid, oid: ContractComplete(*b, m.group(1), mid)),
    (re.compile(r"^New Objective:\s*(.+)$"), lambda b, m, mid, oid: ObjectiveNew(*b, m.group(1), mid, oid)),
    (re.compile(r"^Objective Complete:\s*(.+)$"), lambda b, m, mid, oid: ObjectiveComplete(*b, m.group(1), mid, oid)),
    # Stage 3 (SURVEY.md §0.6): each of these has to be matched here, before the catch-all, or a
    # long one would be taken for a tutorial tip and dropped from the feed. Unverified shapes.
    (re.compile(r"^Contract Failed:\s*(.+)$"), lambda b, m, mid, oid: ContractFailed(*b, m.group(1), mid)),
    (re.compile(r"^Contract Withdrawn:\s*(.+)$"), lambda b, m, mid, oid: ContractWithdrawn(*b, m.group(1), mid)),
    (re.compile(r"^Objective Failed:\s*(.+)$"), lambda b, m, mid, oid: ObjectiveFailed(*b, m.group(1), mid, oid)),
    (re.compile(r"^Objective Withdrawn:\s*(.+)$"), lambda b, m, mid, oid: ObjectiveWithdrawn(*b, m.group(1), mid, oid)),
    (re.compile(r"^Awarded ([\d,]{1,20}) a?UEC\b"), lambda b, m, mid, oid: Reward(*b, _amount(m.group(1)), mid)),
    (re.compile(r"^CrimeStat Rating (Increased|Decreased)"), lambda b, m, mid, oid: CrimeStat(*b, m.group(1) == "Increased")),
    # notice_text() makes every run of white space one space, so these `\s+` cannot backtrack.
    (re.compile(r"^Crime Committed:\s*(.+?)(?:\s+against\s+(.+))?$"),
     lambda b, m, mid, oid: CrimeCommitted(*b, m.group(1), m.group(2))),
    # Loose on purpose (stage 3 review): a trailing period or more words after "against you"
    # must not let the notice fall through. The party form is hud_law_charge_player_crime_party.
    (re.compile(r"^(?:Party member )?(\S+) committed (.+?) against you\b"),
     lambda b, m, mid, oid: CrimeAgainstYou(*b, m.group(1), m.group(2))),
    (re.compile(r"^Fined ([\d,]{1,20}) a?UEC\b"), lambda b, m, mid, oid: Fined(*b, _amount(m.group(1)))),
    (re.compile(r"^Vehicle Impounded:?\s*(.*)$"), lambda b, m, mid, oid: Impounded(*b, m.group(1).strip())),
    (re.compile(r"^Monitored Space (Down|Restored)"), lambda b, m, mid, oid: MonitoredDown(*b, m.group(1) == "Down")),
    (re.compile(r"^Joined hangar queue\.(?:\s*Your place: (\d+)\. Max\. estimated wait: ([\d.]+) s)?"),
     lambda b, m, mid, oid: HangarQueue(*b, _int(m.group(1)), _num(m.group(2)))),
    (re.compile(r"^Hangar Request Completed"), lambda b, m, mid, oid: HangarReady(*b)),
    (re.compile(r"^(?:A|(\d+)) Refinery Work Orders? (?:has|have) been Completed at (.+)$"),
     lambda b, m, mid, oid: RefineryDone(*b, _int(m.group(1) or "1"), m.group(2))),
    (re.compile(r"^Received Blueprint:\s*(.+)$"), lambda b, m, mid, oid: BlueprintReceived(*b, m.group(1))),
    (re.compile(r"^Quantum Travel: Your destination is obstructed"), lambda b, m, mid, oid: QuantumObstructed(*b)),
    (re.compile(r"^Entered (.{1,200}?) Jurisdiction$"), lambda b, m, mid, oid: Jurisdiction(*b, m.group(1))),
    (re.compile(r"^(Entering|Leaving) Armistice Zone"), lambda b, m, mid, oid: Armistice(*b, m.group(1) == "Entering")),
    (re.compile(r"^(Entered|Exited) Monitored Space"), lambda b, m, mid, oid: MonitoredSpace(*b, m.group(1) == "Entered")),
    (re.compile(r"^You have joined channel '(.{1,200}) : ([^']{1,100})'\.?$"),
     lambda b, m, mid, oid: ChannelJoined(*b, m.group(1), m.group(2))),
    (re.compile(r"^You have left the channel '(.{1,200}) : ([^']{1,100})'\.?$"),
     lambda b, m, mid, oid: ChannelLeft(*b, m.group(1), m.group(2))),
    (re.compile(r"^Incapacitated:"), lambda b, m, mid, oid: Incapacitated(*b)),
    (re.compile(r"^Standby, Local Emergency Services Are En Route"), lambda b, m, mid, oid: EmergencyServices(*b)),
    (re.compile(r"^(Minor|Moderate|Severe|Critical) Injury Detected - (.{1,100}?) - Tier (\d)"),
     lambda b, m, mid, oid: Injury(*b, m.group(1), m.group(2), _int(m.group(3)))),
    (re.compile(r"^Regeneration - Location"), lambda b, m, mid, oid: RegenSet(*b)),
    (re.compile(r"^Medical Bed:"), lambda b, m, mid, oid: MedicalBed(*b)),
]


def _h_notice(rec, base):
    m = NOTICE_RE.match(rec.text)
    if m:
        raw = m.group(1)
    else:
        m = NOTICE_OPEN_RE.match(rec.text)      # the closing piece never came: use what there is
        if not m:
            return None
        raw = m.group(1)
    mm = NOTICE_MISSION_RE.search(rec.text)
    mid = real_mission(mm.group(1)) if mm else None
    oid = (mm.group(2) or None) if mm else None
    text = notice_text(raw)
    if not text:
        return None
    for rx, make in NOTICE_KINDS:
        k = rx.match(text)
        if k:
            return make(base, k, mid, oid)
    head, sep, body = text.partition(": ")
    hint = bool(sep) and len(body) > 40
    for rx, words in NAMED_NOTICES:
        k = rx.match(text)
        if k:
            # A known shape with someone's name in it (law.py): worded without it. The slot is
            # passed on as a word to learn, which the state does only under law.learnable().
            return Notice(*base, words, hint, tuple(g for g in k.groups() if g))
    if LAW_LIKE_RE.search(text):
        # It looks like a crime notice but has a shape none of the patterns above reads: it may
        # name a player in a place we cannot tell, so its text is not shown at all (fail closed).
        return Notice(*base, REDACTED, hint, loose_names(text))
    if COMMS_LIKE_RE.search(text) and not COMMS_SAFE_RE.match(text):
        # A ship channel whose name is too long for the pattern, a cut record, or another comms
        # notice: the owner or the member is a player (stage 3 review, round 2).
        return Notice(*base, REDACTED_COMMS, hint, comms_names(text))
    return Notice(*base, text, hint)


LAW_LIKE_RE = re.compile(r"\bcommitted\b|\bagainst you\b|^Crime Committed|^Victim:|'s Private Property|"
                         r"^Party member\b", re.I)
REDACTED = "A law notice the dashboard does not show (it may name a player)"
REDACTED_COMMS = "A comms notice the dashboard does not show (it may name a player)"
_PUNCT = ".,;:!?()[]{}\"'"

# The known shapes that name someone in a fixed place [game, law.py]: each is shown worded
# without the name. Bounded runs only (a notice is at most MAX_TEXT here).
NAMED_NOTICES = [
    (re.compile(r"^Victim:\s*(?:(\S{1,100})$)?"), "Victim: someone"),     # a name of one word is a candidate
    (re.compile(r"^Trespassing on (\S{1,100})'s Private Property"), "Trespassing on another player's private property"),
    (re.compile(r"^WARNING: (\S{1,100})'s Private Property"), "WARNING: someone's private property. Enter at own risk"),
    (re.compile(r"^You have joined (\S{1,100})'s (?:party|group)"), "You have joined another player's party or group"),
    (re.compile(r"^(\S{1,100}) has joined the (?:party|group)"), "Another player has joined the party or group"),
    (re.compile(r"^(\S{1,100}) has left the (?:party|group)"), "Another player has left the party or group"),
    (re.compile(r"^(\S{1,100}) has been kicked from the (?:party|group)"), "Another player has been kicked from the party or group"),
    (re.compile(r"^(\S{1,100}) has declined invitation to "), "Another player has declined your invitation"),
    (re.compile(r"^(\S{1,100}) has invited you to their "), "Another player has invited you"),
    (re.compile(r"^The invitation you sent to (\S{1,100}) has timed out"), "The invitation you sent has timed out"),
    (re.compile(r"^(\S{1,100}) is now .{0,60}\bleader\b"), "Another player is now the leader"),
]

# The other comms_* templates, and the ship channel when its pattern did not read it [game]: a
# channel's owner or a member is a player.
COMMS_LIKE_RE = re.compile(
    r"^You have (?:joined|left|been kicked from) (?:the )?(?:channel|group|party)\b|"
    r"^(?:Comms Channel \w{1,20}|Invited to Comms Channel|Hail Target):|"
    r"^\S{1,100} (?:has (?:joined|left|invited|declined|been kicked)|invited to)\b")
# The ones that name nobody (comms_local_player_left and _kicked with the party or group).
COMMS_SAFE_RE = re.compile(r"^You have (?:left|been kicked from) the (?:group|party)\.?$")


def loose_names(text):
    """Words in a crime notice of a shape we do not read that could be a player's name: the
    word just before " committed " and the word just after "against ". Only candidates: the
    state learns one only under law.learnable() ("player", "your", "Drake" are not learned)."""
    out = []
    i = text.find(" committed ")
    if i > 0:
        before = text[:i].split()
        if before:
            out.append(before[-1].strip(_PUNCT))
    j = text.find("against ")
    if j >= 0:
        after = text[j + len("against "):].split()
        if after:
            out.append(after[0].strip(_PUNCT))
    return tuple(w for w in out if w)


def comms_names(text):
    """Candidates in a comms notice: the channel owner (after " : "), else the first word when
    the notice starts with a member's name."""
    i = text.rfind(" : ")
    if i >= 0:
        rest = text[i + 3:].split("'")[0].split()
        return (rest[0].strip(_PUNCT),) if rest else ()
    if text.startswith(("You have", "Comms Channel", "Invited to")):
        return ()
    first = text.split(maxsplit=1)
    return (first[0].strip(_PUNCT),) if first else ()


# The table (PLAN §9): key -> handler. Only lines whose key is here are ever decoded.
TAG_HANDLERS = {
    "SHUDEvent_OnNotification": _h_notice,
    "CEntityComponentShipListProvider::SetVehicleSpawningInformations": _h_spawn_info,
    "Legacy login response": _h_login,
    "AccountLoginCharacterStatus_Character": _h_character,
    "Join PU": _h_join,
    "Channel Disconnected": _disconnect(False),
    "Channel Process Disconnection": _disconnect(True),
    "SystemQuit": _h_quit,
    "Player Selected Quantum Target - Local": _h_qt_target,
    "Calculate Route": _h_route,
    "Quantum Drive Arrived - Arrived at Final Destination": _h_arrived,
    "Update Inventory Location": _h_inv_location,
    "RequestLocationInventory": _h_loc_inventory,
    "Vehicle Control Flow": _h_seat,
    "Vehicle Destroyed": _h_destroyed,
    "FatalCollision": _h_fatal,
    "LandingArea_UnregisterFromExternalSystems_StowingVehicle": _h_stow,
    "[ActorState] Dead": _h_thrown,
    "Adding non kept item [CSCActorCorpseUtils::PopulateItemPortForItemRecoveryEntitlement]": _h_item_lost,
    "[ActorState] Place": _h_gadget,
    "EndMission": _h_end_mission,
    "CLocalMissionPhaseMarker::CreateMarker": _h_marker,
    "CEntityComponentShopUIProvider::SendShopBuyRequest": _shop(ShopBuy),
    "CEntityComponentShopUIProvider::SendShopSellRequest": _shop(ShopSell),
    "CEntityComponentShopUIProvider::RmShopFlowResponse": _h_shop_result,
    "CEntityComponentShoppingProvider::RmShopFlowResponse": _h_shop_result,
    "CEntityComponentCommodityUIProvider::SendCommoditySellRequest": _h_commodity_sell,
    "CEntityComponentCommodityUIProvider::SendCommodityBuyRequest": _h_commodity_buy,
    "CEntityComponentMiningShopUIProvider::OnRefineryRequest": _h_refinery_sell,
    "CEntityComponentShoppingProvider::SendRentalRequest": _h_rental,
    "CEntityComponentCommodityUIProvider::LoadShopInventoryData::<lambda_1": _h_offer,
    "ReuseChannel": _h_reuse_channel,
    "InventoryManagement": _h_storage,
    "InvalidateAllTerrainCells": _h_terrain,
}
BRACKET_HANDLERS = {               # lines whose first bracket is a name with no `<tag>` after it
    "CSessionManager::OnClientSpawned": _h_spawned,
    "CSessionManager::RequestFrontEnd": _h_front,
    "CSessionManager::ConnectCmd": _h_connect,
}
PREFIX_HANDLERS = {                # level-less lines, matched on how they start
    "BackupNameAttachment=": _h_session,
    "- Connected joystick": _h_joystick,
    "FileVersion: ": _h_version,
    "  planet cells:": _h_cells,
    "ScreenShot: ": _h_screenshot,
    "%SAVEDATA%/Controls/Mappings/": _h_profile,
}
MULTILINE = {"SHUDEvent_OnNotification", "CEntityComponentShipListProvider::SetVehicleSpawningInformations"}

HANDLERS = {}
HANDLERS.update(TAG_HANDLERS)
HANDLERS.update(BRACKET_HANDLERS)
HANDLERS.update(PREFIX_HANDLERS)


def new_record_reader():
    enc = lambda d: {k.encode("utf-8"): v for k, v in d.items()}
    return RecordReader(enc(TAG_HANDLERS), enc(BRACKET_HANDLERS), enc(PREFIX_HANDLERS),
                        {k.encode("utf-8") for k in MULTILINE})


class EventParser:
    """Lines in, events out, in file order. One parser follows one log; `reset()` between sessions.

    No record can stop it: a line the record layer could not read, and a record whose handler
    fails (an unparsable number, say), both become an `Unreadable` event and reading goes on."""

    def __init__(self):
        self.reader = new_record_reader()
        self.session = ""
        self._last_t = 0.0

    def reset(self):
        self.reader.reset()
        self.session = ""
        self._last_t = 0.0

    def begin(self, first_line):
        """Name the session from the log's first line before reading it (the follower knows it)."""
        self.session = session_id(first_line)

    def lines(self, lines, offsets):
        self.reader.lines(lines, offsets)

    def flush(self):
        self.reader.flush()

    @property
    def last_line_t(self):
        """The time of the last timed line read, whatever it was (for a log with no quit line)."""
        return self.reader.last_time

    def take(self):
        out = []
        for rec in self.reader.take():
            ev = self.event(rec)
            if ev is not None:
                out.append(ev)
        return out

    def event(self, rec):
        if rec.key == UNREADABLE:
            return Unreadable(self.session, rec.offset, self._last_t, rec.text)
        if len(rec.text) > MAX_TEXT:
            # Cut before any pattern runs: every handler then costs at most a few thousand
            # characters' work, and no text the state keeps can be longer (stage 3 review: one
            # 60 KB notice in 8 pieces took 158 s, and long objectives held 69 MB).
            rec.text = rec.text[:MAX_TEXT]
        try:
            ev = HANDLERS[rec.key](rec, (self.session, rec.offset, round(rec.t, 3)))
        except Exception as exc:                        # noqa: BLE001 - no line may stop us
            return Unreadable(self.session, rec.offset, self._last_t,
                              "%s in %s" % (type(exc).__name__, rec.key))
        if ev is not None:
            self._last_t = ev.t
            if isinstance(ev, SessionStart):
                self.session = ev.name
        return ev
