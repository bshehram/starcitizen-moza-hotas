"""Record to event: one small typed record per log marker (PLAN §3).

Copyright (c) 2026 archelium (support@archelium.com) for the parts marked "From CSR" below,
used under the MIT License (see dashboard/THIRD_PARTY_NOTICES): several line patterns and the
notice-cleaning helper come from CSR's sc_livelog.py (commit ba6dad0). Everything else in this
file is this project's own.

Every pattern here was checked against the user's own logs [seen: the 69 logs of 2026-11 in
LIVE\\logbackups plus Game.log, read 2026-11-27]; counts are physical lines unless they say
notices. Markers PLAN §3 lists as absent from those logs (`Contract Failed:`, `granted control
token`, `<Actor Death>`) are not built on.

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
    ContractComplete, ObjectiveNew, ObjectiveComplete, HangarQueue, HangarReady, RefineryDone,
    BlueprintReceived, QuantumObstructed, Jurisdiction, Armistice, MonitoredSpace, ChannelJoined,
    ChannelLeft, Incapacitated, EmergencyServices, Injury, RegenSet, MedicalBed, Unreadable]}


def event_from_dict(d):
    """The inverse of Event.to_dict (for replays and tests)."""
    cls = EVENT_TYPES[d["kind"]]
    return cls(**{f.name: d[f.name] for f in fields(cls)})


# --------------------------------------------------------------------------- session identity

SESSION_RE = re.compile(r'^"\s*(Build\((\d+)\)\s+(.*?))\s*"')


def session_id(first_line):
    """A session's id from its log's first line (str or bytes): the backup name the game gives it,
    e.g. 'Build(13220821) 26 Nov 26 (15 11 12)', the same as the backup file's name without
    'Game ' and '.log'. Any other first line gets a short hash of itself."""
    if isinstance(first_line, bytes):
        first_line = first_line.decode("utf-8", "replace")
    i = first_line.find("BackupNameAttachment=")
    if i >= 0:
        m = SESSION_RE.match(first_line[i + len("BackupNameAttachment="):])
        if m:
            return m.group(1)
    return "log-" + hashlib.sha1(first_line.encode("utf-8", "replace")).hexdigest()[:12]


# --------------------------------------------------------------------------- notice text

# From CSR sc_livelog.py lines 16 and 45 (NOTIF_RE, NOTIF_ML_RE): the notice text and its id.
# Changed: anchored at the start of the record's text.
NOTICE_RE = re.compile(r'^Added notification "(.*?)" \[(\d+)\]', re.S)
NOTICE_OPEN_RE = re.compile(r'^Added notification "(.*)', re.S)
# From CSR sc_livelog.py line 36 (NOTIF_MISSION_RE). Changed: upper-case hex accepted too.
NOTICE_MISSION_RE = re.compile(r"MissionId: \[([0-9a-fA-F-]+)\], ObjectiveId: \[([^\]]*)\]")
# From CSR sc_livelog.py lines 84-90 (`clean`): the markup a community language pack adds
# (PLAN §3). Changed: the patterns joined into one.
MARKUP_RE = re.compile(r"</?EM\d>|\[BP\]\*?|\[[^\]]*\bRep\]\*?")


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

VEHICLE_RE = re.compile(r"\| ([A-Za-z0-9_]+?)_(\d+)\[(\d+)\]\|")
# From CSR sc_livelog.py line 51 (QT_SEL_RE). Changed: without its first word.
QT_SELECT_RE = re.compile(r"selected point (\S+) as their destination")
ROUTE_START_RE = re.compile(r"Projected Start Location is (.+?) for route to destination (\S+)")
# From CSR sc_livelog.py line 52 (QT_ROUTE_RE), unchanged.
ROUTE_FUEL_RE = re.compile(r"Successfully calculated route to (\S+) fuel estimate ([\d.]+)")
# From CSR sc_livelog.py line 33 (LOGIN_RE). Changed: the login words in front.
LOGIN_RE = re.compile(r"User Login Success - Handle\[([^\]]+)\]")
CHARACTER_RE = re.compile(r"\bgeid (\d+)\b.*?\bstate (\w+)")
FRONT_RE = re.compile(r'^Started - RequestFrontEndReason="([^"]*)"')
SHARD_RE = re.compile(r"\bshard\[([^\]]*)\]")
DISCONNECT_RE = re.compile(r'^cause=(\d+) reason="([^"]*)"')
QUIT_RE = re.compile(r"cause=(\d+), reason=([^,]*)")
JOYSTICK_RE = re.compile(r"^(\d+):\s*(.*?)\s*(\{[0-9A-Fa-f-]+\})?\s*$")
INV_LOC_RE = re.compile(r"Landing \[(\d+)\] -> \[(\d+)\]\. Location \[(\d+)\] -> \[(\d+)\]")
# From CSR sc_livelog.py line 29 (PLACE_RE). Changed: the player part left out.
LOC_INV_RE = re.compile(r"requested inventory for Location\[([^\]]+)\]")
SPAWN_INFO_RE = re.compile(r"VehicleEntityId: \[(\d+)\](?:, LandingArea: (.*))?", re.S)
SEAT_RE = re.compile(r"ClearDriver: .*?releasing control token for '([A-Za-z0-9_]+?)_(\d+)' \[(\d+)\]")
# From CSR sc_livelog.py lines 20-23 (VKILL_RE). Changed: the tag left out, `[^']*` for the name.
DESTROYED_RE = re.compile(
    r"Vehicle '[^']*' \[(\d+)\] class '([^']+)' \(owner player \[(\d+)\], driver \[\d+\]\) "
    r"destroyed: reason \[(\w+)\] level \[(\d+)\] -> \[(\d+)\].*?killer '([^']*)' \[(\d+)\]")
FATAL_RE = re.compile(r"for vehicle ([A-Za-z0-9_]+?)_(\d+) \[[^\]]*?Zone: ([^,\]]*), PlayerPilot: (\d)")
STOW_RE = re.compile(r"\[STOWING ON UNREGISTER\] (.*?) \[\d+\] - Attempting to stow current vehicle \[(\d+)\]")
THROWN_RE = re.compile(r"Actor '([^']*)' \[\d+\] ejected from zone '([A-Za-z0-9_]+?)_(\d+)' \[(\d+)\]")
ITEM_LOST_RE = re.compile(r"Item '[^']*? - Class\(([^)]*)\).*?Port Name '([^']*)'")
# From CSR sc_livelog.py line 35 (MISSION_RE). Changed: the reason captured too.
END_MISSION_RE = re.compile(r"MissionId\[([^\]]+)\].*?CompletionType\[([^\]]+)\](?: Reason\[([^\]]*)\])?")
MARKER_RE = re.compile(r"missionId \[([^\]]+)\], generator name \[([^\]]*)\], contract \[([^\]]*)\]")
SHOP_RE = re.compile(r"shopName\[([^\]]*)\].*?client_price\[([\d.]+)\].*?itemName\[([^\]]*)\](?: quantity\[(\d+)\])?")
SHOP_RESULT_RE = re.compile(r"(?:shopName\[([^\]]*)\].*?)?result\[([^\]]*)\](?: type\[([^\]]*)\])?")
COMMODITY_SELL_RE = re.compile(r"shopName\[([^\]]*)\].*?amount\[([\d.]+)\] resourceGUID\[([^\]]*)\].*?quantity\[([^\]]*)\]")
COMMODITY_BUY_RE = re.compile(r"shopName\[([^\]]*)\].*?\bprice\[([\d.]+)\].*?resourceGUID\[([^\]]*)\].*?quantity\[([^\]]*)\]")
BOX_RE = re.compile(r"boxSize\[([\d.]+)\] \| unitAmount\[(\d+)\]")
SHOP_NAME_RE = re.compile(r"shopName\[([^\]]*)\]")
OFFER_RE = re.compile(r"shopName\[([^\]]*)\] commodityName\[([^\]]*)\]")
STORAGE_RE = re.compile(r"InventoryDataRequest Successful for .*?Inventory\[\d+:Location:(\d+)\].*?Item Count:\[(\d+)\]")
GADGET_RE = re.compile(r"placed '(Mining_Gadget_[A-Za-z0-9_]+?)_\d+' \[\d+\] (?:on entity '([A-Za-z0-9_]+?)_\d+'|loosely)")
CELLS_RE = re.compile(r"^\s*(\d+) .*?name: (\S+)")
TERRAIN_RE = re.compile(r"Planet (\S+) invalidated")
OWNER_RE = re.compile(r"^.*?'s\s+(\S.*)$", re.S)     # "<owner>'s XL Hangar": the owner is dropped
TEAM_TAIL_RE = re.compile(r"\s*(?:\[Team_[^\]]*\](?:\[[^\]]*\])*)?\s*$")


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
    m = SESSION_RE.match(rec.text)
    return SessionStart(name, base[1], base[2], name, m.group(2) if m else None,
                        m.group(3) if m else None)


def _h_version(rec, base):
    return GameVersion(*base, rec.text.strip())


def _h_joystick(rec, base):
    m = JOYSTICK_RE.match(rec.text)
    if m:
        guid = m.group(3).strip("{}") if m.group(3) else None
        return Joystick(*base, _int(m.group(1)), m.group(2), guid)


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
        area = TEAM_TAIL_RE.sub("", m.group(2))
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
        return VehicleDestroyed(*base, m.group(2), m.group(1), m.group(3), m.group(4),
                                _int(m.group(5)), _int(m.group(6)), m.group(7), m.group(8))


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
        return MissionMarker(*base, *m.groups())


def _shop(cls):
    def handler(rec, base):
        m = SHOP_RE.search(rec.text)
        if m:
            qty = _int(m.group(4)) if m.group(4) else None
            return cls(*base, m.group(1), m.group(3), _num(m.group(2)), qty)
    return handler


def _h_shop_result(rec, base):
    m = SHOP_RESULT_RE.search(rec.text)
    if m:
        return ShopResult(*base, m.group(1), m.group(2), m.group(3))


def _h_commodity_sell(rec, base):
    m = COMMODITY_SELL_RE.search(rec.text)
    if m:
        b = BOX_RE.search(rec.text)
        box = "%s x %s" % (b.group(2), b.group(1)) if b else None
        return CommoditySell(*base, m.group(1), m.group(3), _num(m.group(2)), m.group(4), box)


def _h_commodity_buy(rec, base):
    m = COMMODITY_BUY_RE.search(rec.text)
    if m:
        return CommodityBuy(*base, m.group(1), m.group(3), _num(m.group(2)), m.group(4))


def _h_refinery_sell(rec, base):
    m = SHOP_NAME_RE.search(rec.text)
    if m and "SShopRefineryRequest" in rec.text:
        return RefinerySell(*base, m.group(1))


def _h_rental(rec, base):
    m = SHOP_RE.search(rec.text)
    if m:
        return Rental(*base, m.group(1), m.group(3), _num(m.group(2)))


def _h_offer(rec, base):
    m = OFFER_RE.search(rec.text)
    if m:
        return ShopOffer(*base, m.group(1), m.group(2))


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
# the contract notices from line 17 (CONTRACT_NOTIF_RE; `Failed` left out, PLAN §3), the
# objective notices from line 53 (OBJ_RE; only the two kinds in the user's logs), the
# jurisdiction notice from line 18 (JURIS_RE), the armistice notices from lines 395-400, the
# blueprint notice from line 28 (BLUEPRINT_RE), and the injury notice from line 19 (INJURY_RE).
NOTICE_KINDS = [
    (re.compile(r"^Contract Accepted:\s*(.+)$"), lambda b, m, mid, oid: ContractAccepted(*b, m.group(1), mid)),
    (re.compile(r"^Contract Complete:\s*(.+)$"), lambda b, m, mid, oid: ContractComplete(*b, m.group(1), mid)),
    (re.compile(r"^New Objective:\s*(.+)$"), lambda b, m, mid, oid: ObjectiveNew(*b, m.group(1), mid, oid)),
    (re.compile(r"^Objective Complete:\s*(.+)$"), lambda b, m, mid, oid: ObjectiveComplete(*b, m.group(1), mid, oid)),
    (re.compile(r"^Joined hangar queue\.(?:\s*Your place: (\d+)\. Max\. estimated wait: ([\d.]+) s)?"),
     lambda b, m, mid, oid: HangarQueue(*b, _int(m.group(1)), _num(m.group(2)))),
    (re.compile(r"^Hangar Request Completed"), lambda b, m, mid, oid: HangarReady(*b)),
    (re.compile(r"^(?:A|(\d+)) Refinery Work Orders? (?:has|have) been Completed at (.+)$"),
     lambda b, m, mid, oid: RefineryDone(*b, _int(m.group(1) or "1"), m.group(2))),
    (re.compile(r"^Received Blueprint:\s*(.+)$"), lambda b, m, mid, oid: BlueprintReceived(*b, m.group(1))),
    (re.compile(r"^Quantum Travel: Your destination is obstructed"), lambda b, m, mid, oid: QuantumObstructed(*b)),
    (re.compile(r"^Entered (.+?) Jurisdiction$"), lambda b, m, mid, oid: Jurisdiction(*b, m.group(1))),
    (re.compile(r"^(Entering|Leaving) Armistice Zone"), lambda b, m, mid, oid: Armistice(*b, m.group(1) == "Entering")),
    (re.compile(r"^(Entered|Exited) Monitored Space"), lambda b, m, mid, oid: MonitoredSpace(*b, m.group(1) == "Entered")),
    (re.compile(r"^You have joined channel '(.+) : ([^']+)'\.?$"), lambda b, m, mid, oid: ChannelJoined(*b, m.group(1), m.group(2))),
    (re.compile(r"^You have left the channel '(.+) : ([^']+)'\.?$"), lambda b, m, mid, oid: ChannelLeft(*b, m.group(1), m.group(2))),
    (re.compile(r"^Incapacitated:"), lambda b, m, mid, oid: Incapacitated(*b)),
    (re.compile(r"^Standby, Local Emergency Services Are En Route"), lambda b, m, mid, oid: EmergencyServices(*b)),
    (re.compile(r"^(Minor|Moderate|Severe|Critical) Injury Detected - (.+?) - Tier (\d)"),
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
    return Notice(*base, text, bool(sep) and len(body) > 40)


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
