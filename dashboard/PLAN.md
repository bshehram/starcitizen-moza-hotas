# Side-screen dashboard: implementation plan

**Status: being built, stage by stage (§12).** Written 2026-11-26. Reviewed 2026-11-27 against
the user's logs and this PC: the corrections are marked **[seen 2026-11-27]**, and the user's
decisions are in §15. The build started later that day.

| Stage | State on 2026-11-27 |
| --- | --- |
| Reference tables (§10) | Built, checked, committed. |
| 1. Parser and state | Built, reviewed twice by an independent agent, committed. `python dashboard/scdash.py timeline` works. |
| 2. Service and a minimal page | Not started. |
| 3. Views and plan data | Not started. The look is chosen: direction B, mocked up in every screen (§11). |
| 4. Autostart and the window | Not started. Waits for the side monitor. |
| 4b. The Claude terminal | Not started. |
| 5. A flown session | The user's. |
| 6. The telemetry source | Not started. |
| 7. Docs and routines | Kept up as stages land; the final pass is not done. |

How the build is run: each stage is built by one agent, checked by the orchestrating session
(tests, the stage's own check, a scan for the user's private identifiers), reviewed by a second
agent that tries to break it, fixed, and only then committed, one commit per stage or fix round.
[`CLAUDE.md`](CLAUDE.md) in this folder has the working notes for what exists.

This file is the brief for the Claude session that builds the dashboard. The user starts that
session with `@STARCITIZEN.md` and asks for the dashboard to be built from this plan. It says what
to build, why each constraint exists, what is already known and what still has to be checked, and
how to tell that each stage is done. It does not repeat the project's own rules: read
[`../STARCITIZEN.md`](../STARCITIZEN.md) and [`../CLAUDE.md`](../CLAUDE.md) first, and follow them
where this plan is silent.

Each fact below carries how it is known, the same way the rest of the project does:

- **[seen]** read from the user's own game logs or files on this PC.
- **[ref]** from documentation or a community source, with the source named. Second-hand.
- **[verify]** my reasoning or an open question. Check it before relying on it.

## 1. What this is

A small background program that reads Star Citizen's own log file while the user plays and shows
what matters right now on a second monitor: where they are, what the plan says to do next, the
numbers they need for the job in hand, timers, and alerts.

The side monitor is a 15.6-inch 1920x1080 screen **without touch**. The user stands it either
way up, landscape (1920x1080) or portrait (1080x1920), as they feel like on the day, so the page
has a layout for each (§11). The user's hands are on a stick and throttle, so nobody operates the
dashboard during play. It has to run itself: pick the right view from what the log shows, and be
readable at a glance from a seat away.

## 2. What the user asked for

| Their words | What it means here |
| --- | --- |
| "a dashboard or something for star citizen" on a second screen | A glance-only display that follows the game by itself. |
| "an html thing in a browser" | A web page, fed by a small Python script. Agreed with the user. |
| "run from within this project in a sub folder that way we keep everything in git" | Code, docs and generic game reference data live in `dashboard/` in this repo. The user's own play data stays in a git-ignored folder, because the repo is public (agreed with the user). |
| "make sure its a service" | It starts by itself, runs in the background, and never runs twice. §6. |
| "idempotent" | Every command can be repeated with the same end result, and the same log always produces the same state. §7. |
| "safe to run" | It cannot harm the game, the PC, the account or the user's privacy. §8. |
| "performant as much as possible" | Memory is tight on this PC while the game runs, and adding RAM is not an option. Every megabyte and every wake-up is a cost. §9. |
| "it will be in either portrait or landscape mode ... depending on my mood" (2026-11-27) | The page has two layouts, 1920x1080 and 1080x1920, and picks one from the shape of its window. There is no setting to change. §11. |
| "a terminal window running claude inside of this dashboard ... so instead of it being a read only dashboard i can alt-tab to it while in quantum and ask questions"; "i dont want to type in claude to start it" (2026-11-27) | A terminal panel in the page that runs Claude Code, and only Claude Code, started by the dashboard itself in this folder. §4 (*The Claude terminal*), §8, §12 stage 4b. |

## 3. What it can and cannot know

The dashboard reads files only. The game does have a live data feed, but it is off by default
and undocumented, and using it is the user's decision: see *The game's telemetry stream* at the
end of this section.

**Can know, from `LIVE\Game.log` [seen]:** the markers below are in the user's logs. Memory note
`sc-game-log-reading` has the full list with caveats; derive the real patterns from recent files
in `LIVE\logbackups\`, not from the wording here.

| Event | Marker in the log |
| --- | --- |
| Joysticks found at launch, in order | `Connected joystick0: <name> {GUID}` |
| Session start, and its backup name | first line `<time> BackupNameAttachment=" Build(<n>) <date> (<HH MM SS>)"  -- used by backup system`, then `Log started on ...`. Like every line, it starts with the UTC time in angle brackets. |
| Reached the main menu, entered the game world, or respawned | `[CSessionManager::OnClientSpawned] Spawned!`. The same line means three things **[seen 2026-11-27, 69 November logs: 99 at the menu, 80 world entries, 44 respawns]**. At every launch and every return to the menu it marks the menu. The first one after `<Join PU>` is entering the game world. One while already in the world is a respawn, and all 44 followed a downing or a death. On a respawn, `Update Inventory Location` is logged a few milliseconds *before* it, not after. |
| Quantum target chosen | `<Player Selected Quantum Target - Local> ... selected point <CODE>` |
| Route start and fuel estimate | `<Calculate Route> ... Projected Start Location is <name> for route to destination <CODE>` and `... fuel estimate <n>`. These are also logged when a route is only plotted on the map (`Player Requested Fuel to Quantum Target`), so a route line by itself is not a chosen target: only the selection line above is **[seen 2026-11-27: 114 route targets for 99 selections]**. |
| Quantum arrival | `<Quantum Drive Arrived - Arrived at Final Destination>`. The line can be for someone else's ship: on 2026-11-27 one named a Golem OX that was not the user's, while the user's own jump logged a target and no arrival. Match the vehicle id **[seen 2026-11-27]**. Of 83 arrivals in the November logs, 4 were other players' ships. |
| Arrival at a station or landing zone | `RequestLocationInventory Location[<name>]`, `Update Inventory Location`. The first is also written every time the storage screen is opened (93 of 322), so it says where the user is, not that they just arrived **[seen 2026-11-27]**. |
| Ship retrieved | `SetVehicleSpawningInformations - VehicleEntityId: [<id>]`. Usually split over two lines (78 of 80): the first ends with `LandingArea: <handle>'s`, and the second, with its own time prefix, holds the hangar size **[seen 2026-11-27]**. |
| Ship name | notice `You have joined channel '<Ship name> : <handle>'` |
| Left the pilot seat, with ship class | `<Vehicle Control Flow> ... ClearDriver ... '<CLASS>_<id>'` |
| HUD notices | `<SHUDEvent_OnNotification> Added notification "<text>"`: jurisdiction, armistice, monitored space, hangar queue and "Hangar Request Completed", "A Refinery Work Order has been Completed at <station>", "destination is obstructed", medical bed, "Regeneration - Location", "Local Emergency Services". Each notice is logged up to three times and can span lines: see *Reading the lines* below. |
| Contract accepted, completed | notices `Contract Accepted:  <title>: ` and `Contract Complete: <title>: `, each line carrying `MissionId: [<guid>]` (39 and 13 notices in the November logs; counted as lines they are 272 and 77, because each notice is logged up to three times) **[seen 2026-11-27]** |
| Objectives | notices `New Objective: <text>` and `Objective Complete: <text>` (85 and 33 notices) **[seen 2026-11-27]** |
| Contract ended, and how | `<EndMission> Ending mission for player. MissionId[<guid>] ... CompletionType[Complete]` or `[Abandon]`, then `Reason[...]` (20) **[seen 2026-11-27]** |
| Fatal crash into something | `<FatalCollision> Fatal Collision occured for vehicle <CLASS>_<id> [Part: ..., Zone: <zone>, PlayerPilot: 1] after hitting entity: ...` (4) **[seen 2026-11-27]** |
| Blueprint received | `Received Blueprint` |
| Ship destroyed | `<Vehicle Destroyed> Vehicle '<CLASS>_<id>' ... reason [<r>] ... killer '<name>'` (other players' ships appear too: match the entity id) |
| Thrown out of a destroyed ship | `<[ActorState] Dead> ... Actor '<handle>' ... ejected from zone '<CLASS>_<id>' ... due to previous zone being in a destroyed vehicle` (19 in November) **[seen 2026-11-27]**. It is not a death marker by itself: another tool's notes say only about 60% of these coincide with a death **[ref]**. |
| Death with gear lost | a burst of `ItemRecoveryEntitlement` lines, one per item. A fall that only downs the user logs neither this nor the line above (memory note `sc-game-log-reading`). Another tool warns the burst can also be for a body nearby **[ref: CSR]**. |
| Downed, injured | notices `Incapacitated: ...` (36) and `<Minor/Moderate/Severe> Injury Detected - <part> - Tier <n> Treatment Required` (2) **[seen 2026-11-27]**. Downed is not dead: of the 36, 27 were followed by a respawn, 8 by normal activity with no respawn, and 1 by a quit. The "Local Emergency Services" notice was followed by a respawn 23 times out of 23. |
| Refinery order(s) done | notice `A Refinery Work Order has been Completed at <station>` or, for several at once, `<n> Refinery Work Orders have been Completed at <station>` (8 notices and 1) **[seen 2026-11-27]** |
| Clean exit from the game | `<SystemQuit> CSystem::Quit invoked with - cause=30016, reason=Quit via console command, exitCode=0`, in 68 of the 69 November logs **[seen 2026-11-27]**. The reason reads `User closed the application` instead in 12 of them. A log that ends without the line ended in a crash or a kill. |
| The user's own handle | `<Legacy login response> [CIG-net] User Login Success - Handle[<handle>]`, once per launch **[seen 2026-11-27]** |
| A planet or moon coming into range | `<InvalidateAllTerrainCells> Planet OOC_Stanton_4_Microtech invalidated all terrain cells` (376 in 16 logs) **[seen 2026-11-27]**. Fires on loading and on unloading, so it says "near", not "at". |
| What a supply shop offers | `LoadShopInventoryData ... AddingCommodityBox ... shopName[...] commodityName[ResourceType.<Name>]` when a shop lists its goods (153 lines in one log, at a base's admin shop: fuel, ammunition, RMC, metals) **[seen 2026-11-27]**. The line has the name but no resource id, so it cannot name the ids in a sale line: `resources.json` still comes from `Game2.dcb` (§10). |
| Which contract a mission id is | `<CLocalMissionPhaseMarker::CreateMarker> ... missionId [<guid>], generator name [<giver>_<kind>], contract [<internal name>]` (110) **[seen 2026-11-27]** |
| Shop purchases and sales | `SendShopBuyRequest` / `SendShopSellRequest` (shop, price, item) and `ShopFlowResponse ... result[...]` |
| Ore sold to a refinery | `<...FlashCallback_OnSellToRefineryPressed>`, then about a second later `OnRefineryRequest ... SShopRefineryRequest ... shopName[SCShop_RefineryAdmin_ORE]`. Neither says what was sold or for how much. Seen on 2026-11-26 and 2026-11-27. |
| The fabricator screen opened | `ReuseChannel ... blueprint_library.v1.BlueprintLibraryService`, then at once `<Query Inventory> ... Inventory[<fabricator id>:Container:0]`. Nothing else names a placed fabricator: placing it logs nothing, and so does its disappearing **[seen 2026-11-27]**. |
| Commodity sold or bought at a trade terminal | `SendCommoditySellRequest` / `SendCommodityBuyRequest`: shop name, amount in aUEC, a resource id, quantity and box size. Seen 2026-11-26 at the New Babbage TDD. The commodity is an id, not a name. |
| Joined a server | `<Join PU> ... shard[...]` |
| A ship stowed: the user's, or anyone's nearby | `[STOWING ON UNREGISTER] ... Attempting to stow current vehicle [<id>]`. Logged for every hangar around, 1,042 times in the November logs. It is the user's ship only when `<id>` matches their own `SetVehicleSpawningInformations` **[seen 2026-11-27]**. |
| Storage item count | `Freight Inventory Grid InventoryDataRequest Successful ... Item Count:[<n>]`. The count follows the storage screen's filter (156, 34, 42, 156 within 71 seconds with nothing moved), so a change in it is not cargo being loaded or unloaded **[seen 2026-11-27]**. |
| Mining gadget placed, with the rock's ore | `placed 'Mining_Gadget_<name>_<id>' on entity 'MineableRock_<kind>_<ore>_<id>'` |
| Which planet or moon, every 10 minutes | `PHYSICS INSTANCE STATS` block, the `planet cells:` line with a non-zero count |
| Screenshot taken | `ScreenShot: ScreenShots/<name>.jpg` |
| Leaving the game world, and why | `<Channel Disconnected> cause=<n> reason="..."`, with a twin `<Channel Process Disconnection>` line. Counted in the November logs **[seen 2026-11-27]**: 30016 "Player requested disconnect" (54) is the user leaving the server: a quit when `<SystemQuit>` follows (row above), otherwise a return to the menu. 30016 "DisconnectCmd: disconnect light ExitToMenu" (2) is also a return to the menu. After either return the session goes on. 30028 "player inactive" (1) is the inactivity kick. 30010 "Nub destroyed" (160) appears between the menu and the game and is not an end. 30013 appears only on `<Channel Process Disconnection>` (3), with a reason starting "Remote Disconnect - Signal raised ...": the *server* crashed. A crash of the game itself leaves no line at all (the log just stops), so that case is read from the process going away. Other tools say 30016 is also logged for a server drop **[ref, §14]**. One more cause turned up on 2026-11-27, in two launches: 41058 "Player Query failed". |

Markers other tools use that are **not** in the user's November logs **[seen 2026-11-27]**:
`Contract Failed:` (perhaps only because no contract failed), `granted control token for
'<CLASS>_<id>'` on taking the pilot seat (the logs have only the *releasing* line on leaving it,
so taking a seat is still read from the `You have joined channel` notice), and `<Actor Death>` /
`CActor::Kill` (another tool's code says the publisher removed these in late 2025). Don't build on
them.

**Reading the lines [seen 2026-11-27: 65 November logs, 528,724 lines].**

- **Encoding.** UTF-8 with no byte-order mark. Every line decoded cleanly, and the longest was
  1,181 bytes. Decode with replacement all the same, never strictly: another tool's notes record
  a stray Windows-1252 byte in mission text that stalled its reader for good **[ref: StarStats]**.
- **A notice can span lines.** When a notice's text contains a line break, the log splits it, and
  each piece gets its own time prefix but only the first has the `[Notice] <Tag>` part:

  ```
  <time> [Notice] <SHUDEvent_OnNotification> Added notification "Joined hangar queue.
  <time> Your place: 2. Max. estimated wait: 200.000000 s.: " [3] to queue. New queue size: 1, MissionId: [...]
  ```

  The second line holds the wait estimate that the stuck-queue alert needs. So a timed line with
  no `[Level]` part continues the record above it, and a notice is complete only once its closing
  quote has arrived. The continuation is nearly always the very next line with the same time,
  but not always: once in 2,086 notices a complete `<Vehicle Destroyed>` line sat between the
  two pieces, and 12 of 191 pieces carry a time one millisecond later. Other records split the
  same way (the ship-retrieved line in the table above).
- **A notice is logged up to three times:** the `<SHUDEvent_OnNotification> Added notification`
  record, an indented echo of the quoted text, and an `<UpdateNotificationItem>` line. Match the
  first only, or every notice counts two or three times.
- **Some lines have no time at all:** 7,983 of them (1.5%). They are the inner lines of
  multi-line debug dumps. Skip them, and tell them by the missing time prefix only: the line
  ending does not separate them (2,981 untimed lines end in CR LF, and 2,981 timed lines end in
  a bare LF).
- **No line may stop the reader.** A line that cannot be read (a damaged time prefix, a number
  that is not a number) is skipped and counted, and the offset moves on. The first build of the
  reader stalled for good on one such line; review caught it.
- **Checked because other tools get these wrong.** Across 2,021 notices: every continuation
  piece carried a time prefix (191 of 191), the longest notice was three physical lines, and the
  number after a notice's closing quote never repeated or went backwards inside one log. All 302
  `RequestLocationInventory` lines were for the user, none for another player. The level part is
  not always a single tag: `[SPAM 119][Error]` occurs, so don't assume one bracket.
- **Two families of location code.** Quantum targets look like `LOC_RR_S3_L1` and
  `OOC_Stanton_3b_Wala`. Inventory locations look like `RR_ARC_L1` and `Stanton4_NewBabbage`.
  `locations.json` needs both, and a leg in `plan.json` may list codes from either.
- **Size and speed.** November logs run from 32 KB to 5.4 MB (median 1.4 MB) and grow at about
  0.6 KB a second over a session, with 18 KB written in the first 10 seconds of a launch and
  160 KB in the first 30. Five older logs are far larger: 376 MB, 208 MB, 54 MB, 48 MB and 13 MB,
  all from February and March 2026, from error floods that reached about 3.7 MB a second. A plain
  Python loop with one compiled filter read all of these at about 120 MB a second on this PC.
- **More than the handle is personal.** A log also carries the Windows user name (`username ...
  signedIn`), the PC's name (`<Hostname>`), the account id and character id
  (`<AccountLoginCharacterStatus_Character>`), the player id on many lines, session ids, and
  server addresses. §8 and §13 cover what that means for test samples.

**Where the location codes come from [seen in the game's files, 2026-11-27, build
4.10.201.48085].** The quantum-target codes (`LOC_RR_S3_L1`, `OOC_Stanton_3b_Wala`,
`NewBabbage_LOC`) are not in `global.ini`. They are entity names in the solar system's object
containers inside `Data.p4k`. Each points to a star-map record in `Game2.dcb`, and that record's
own name is the inventory code (`RR_ARC_L1`), with a label that gives the display name. So one
record ties both code families to one place, and `reference/build_reference.py` reads the whole
table from the game (§10). `S1` to `S4` are Stanton 1 to 4: Hurston, Crusader, ArcCorp and
microTech, the same as `HUR` / `CRU` / `ARC` / `MIC`. Three things to know:

- **There are more than two families.** Runtime codes also occur: `NavPoint_Dynamic_<n>`,
  `MISSION_QT_...`, `rs_ext_...`. `locations.json` carries a list of prefixes for those.
- **A code can mean several places.** `ObjectContainer_RestStop` is Baijini Point, Everus Harbor
  or Port Tressler; the inventory location logged on arrival tells which.
- **An L-point's code is its station, not its asteroid field.** `LOC_RR_S3_L4` is ARC-L4 Faint
  Glen Station; the field the user mines is a separate record about 3,500 km away, and nothing
  is logged on reaching it. Leaving the field does show: the route's start is then named
  "ARC L4", the field's own name. So a plan leg, not the log, says that a jump to an L-point is
  a mining stop.
- Some names mislead: Stanton's Nyx Gateway is `RR_JP_StantonMagnus`.

**Can know, from other files:** new Game Bar captures in `%USERPROFILE%\Videos\Captures` (name and
time only), and the plan data Claude maintains (§10).

**Cannot know from the log [seen]:** speed, fuel, shields, cargo, what was mined, the quality of
anything, or the start of a refinery order. The log only records a refinery order when it
completes. Show nothing for these; a gap is better than a guess. The telemetry stream below
covers speed and fuel and nothing else on this list.

**The game's telemetry stream [ref, 2026-11-27: other tools' code and notes, and the names of
settings read from the installed game's program file; it has never been switched on here].**

- **What it is.** Since about 4.10.2 the game holds a small local server,
  `sc.game.telemetry.v1.GameTelemetryService`, at `127.0.0.1:2942`: gRPC over plain HTTP/2, no
  sign-in, read-only in this build. The publisher built it. It grew out of the motion-seat
  support announced in May 2026, where staff wrote that telemetry output would be expanded "to
  support other channels and integrations". It is not in any patch notes, and no statement
  permits or forbids outside programs using it.
- **How it is switched on.** Two ways are reported for the user's build. An environment variable
  on the launcher, `GRPC_CLIENT_SERVER_ENABLED=true` (CommandGlass, Wingman AI and others), which
  touches no file. Or a line in `LIVE\user.cfg`, `grpc.client.server.enabled = true` (CSR's
  notes, dated 2026-11-24 on build 13220821). Neither was tried here. On this PC `user.cfg` does
  not exist, the variable is not set, and the logs show the service was never registered
  **[seen 2026-11-27]**. The earlier note that a `user.cfg` line switches it on was half right:
  the other line in circulation, `server.game.telemetry.enabled`, belongs to the 5.0 test builds.
- **What it would add** (build 4.10.201): the aUEC balance, hydrogen fuel, speed, health and the
  other vitals, taking and leaving a seat as events (the log only has leaving), landing gear and
  VTOL state, coupled or decoupled, the ship's warning lights, which systems are powered, and
  countermeasure counts. About 15 to 18 full snapshots a second.
- **What it still would not give:** position or location, shield or hull values, cargo, anything
  about mining, contracts. So it does not close the gaps that matter most to the mining and
  crafting plans.
- **What the installed build really declares [seen 2026-11-27: read from `StarCitizen.exe`,
  build 4.10.201.48085, by two agents with separate extractors that agreed byte for byte].**
  - Two layout files, 28 messages, 131 fields. One service,
    `sc.game.telemetry.v1.GameTelemetryService`, with one method, `TelemetryStream`, which takes
    an empty request and streams snapshots.
  - A snapshot has six parts: vehicle, weapons, events, actor, force feedback, turret.
  - Every reading the plan wants has a field: hydrogen fuel, speed, the aUEC balance (a whole
    number), landing gear, VTOL, coupled, 10 warning lights, 9 power flags, countermeasures by
    type and amount.
  - No field for position or location, shields or hull, master mode, quantum state, cargo or
    contracts. That part of the list above is now first-hand.
  - Four settings exist in the program file, with descriptions: `grpc.client.server.address`
    (default `127.0.0.1:2942`), `server.game.telemetry.stream.interval.ms`,
    `server.game.telemetry.generate.without.clients`, and `server.game.telemetry.test.data`,
    which makes the game send made-up data. None has been set here.
  - **The same program file names other local services** that have nothing to do with
    telemetry: a query service with 11 methods and an editor bridge with pause and resume
    commands. Whether the game answers them on this port is not known. So "read-only" is proven
    for the telemetry service only, and the rule that the dashboard calls one method and no
    other (§8) matters in this build already, not only in 5.0.
  - A connection that is refused takes about 2 seconds to fail on this PC, so each attempt while
    the stream is off costs that long **[seen]**.
- **Quirks other tools recorded on the live build [ref: Starglance's `docs/FIELDS.md`, CSR's
  `docs/telemetry/NOTES.md`].** Check each against the cockpit before showing it.
  - Ship data arrives 5 to 6 seconds after sitting down, and only while seated.
  - The enter-seat event arrived 3 times in 6. The ship block appearing is the safer signal.
  - `vtol` always reads deployed, `quantum_fuel` always reads 0, and `manufacturer` is empty.
  - Hydrogen fuel is a fraction from 0 to 1 and reads 0 with the engines off.
  - Altitude reads as the largest possible number in space. Treat anything that large as none.
  - Whether decoupled is the `enabled` or the `active` part of `ifcs_coupled` is disputed between
    tools.
  - Two programs can read the stream at once.
- **Its rate can probably be set in the game.** The installed build has a setting
  `server.game.telemetry.stream.interval.ms`, described there as the write interval per client
  ("50 = ~20Hz") **[ref: an agent's read of the setting names in the program file]**. No tool uses
  it and it is untested. If it is honored, 1000 would make the game send one snapshot a second.
  The same strings suggest the game builds no snapshots while nothing is connected.
- **Where it stands (the user, 2026-11-27).** 5.0 is expected within weeks and is expected to
  make this stream much bigger. The 5.0 test builds add shields, master mode, quantum state and
  destination, a named location, jurisdiction and the tracked contract **[ref]**. Only part of
  that is backed by a layout anyone here has seen: CSR's own copy of a 5.0 test-build layout
  adds shields, hull health, master mode and two action methods, and nothing on location,
  quantum state or contracts **[ref, 2026-11-27]**. Treat the longer list as hearsay until 5.0
  is installed and its program file has been read. The user wants
  the dashboard able to use it. So it is designed in from the start as a second, optional source
  (§5) with its own build stage (§12), and the dashboard must work fully without it.
- **Cautions that still hold.**
  - It is undocumented, and the terms of service have a clause against using "features which are
    not documented" for advantage and one against connections "not expressly approved". Whether
    either reaches a read-only local display is unsettled. No trouble has been reported.
  - It may change or vanish: the publisher switched it off in the two newest 5.0 test builds. So
    every telemetry panel disappears cleanly when the stream is not there, and nothing else
    depends on it.
  - In the 5.0 test builds the same port also accepts game actions. The dashboard never uses
    them: it calls the one read-only stream method and nothing else (§8).
  - Switching it on changes something outside this repo (an environment variable for the
    launcher, or a line in the game's `user.cfg`), so the user is asked first, with both ways
    explained (§15).
  - Python's standard library has no HTTP/2 client. CSR has a small one, with a protobuf decoder,
    under the MIT license.

**Others have built this before, and none of them is this [ref: source audits, 2026-11-27].**
The user asked whether an existing community tool could be used instead, on one condition: open
source and run from source, not a precompiled Windows program. A survey found about 90 projects.
Nine were cloned and read line by line; none was run. Almost all are one person's work, weeks or
months old.

| Tool | License, and how it runs | What it is | Why it is not the dashboard |
| --- | --- | --- | --- |
| QuantumWake (`peans99/QuantumWake`) | Apache-2.0. .NET 10 from source; this PC has only .NET 8. | The closest by function: a Now page, flight plans, shopping lists, checklists, and an interface an assistant can push a plan through. | A plan pushed while the page is open does not show until the page is reloaded. No timers beyond refinery orders it reads off screenshots. No joystick check, no telemetry and no plan for it. Small type. An estimated 150 to 350 MB, with a spike near 1 GB after each patch. It can write into the game folder on request, including this repo's folder, and any program on the PC can ask it to. |
| CSR (`archelium/csr`) | MIT. Python, standard library only. | A career-stats report over all the logs, a crash watcher, and a beta live page built around telemetry. | Not a live plan display. **Its code is the best to reuse:** `sc_livelog.py` and `sc_telemetry.py` (§5, §12). |
| Starglance (`bradqui/starglance`) | MIT. Python with heavy packages, plus Node to build its page. | A cockpit gauge page for a second monitor, telemetry first. | Shows only "waiting" without telemetry. No place for the user's own content. |
| SC Telemetry Local (`cariboudundee/sc-telemetry-local`) | MIT. Go. | Telemetry gauges with custom boards. | Boards bind to game fields only. Needs Go. |
| SC Companion (`Na0f3l/Sc-companion`) | MIT. Node 24. | Telemetry HUD, alerts, a memory watch. | Listens on the whole network by default and does not check who is asking. No place for the user's content. |
| sc-log-tracker (`DefaultHahn/sc-log-tracker`) | MIT. One Python file, standard library. | An event feed and session history, built the way this plan is. | Dropped its Now panel, and quits when its tab closes. Good server hardening to learn from. |
| star-citizen-live (`Neorion/star-citizen-live`) | MIT declared. Node, no packages. | An event feed for an org. | Open on all network interfaces, memory grows without limit. |
| StarStats (`TheCodeSaiyan/StarStats-Platform`) | MPL-2.0. Rust; shipped as an installer. | A stats platform around a hosted account. | Calls its server by default; its main views are on a website. |
| CommandGlass (`robertogeek/CommandGlass`) | **No license.** Node from source. | A live page for a tablet, with a key-sending control panel. | Not open source. Spanish first. Listens on the whole network and can send key presses. The user put it at the bottom of the list. |

So the recommendation stands: build this one. The reasons are the things no existing tool does
together: it shows the user's own plan and the numbers for the job in hand, it runs timers, it
checks this rig's joystick order at launch, it switches views by itself for a screen nobody
touches, it is readable from a seat away, it stays light, and it is ready for telemetry. The user
agreed on 2026-11-27: we build (§15).

What the audits change in how it is built:

- **Reuse code from one project, CSR, under its MIT license** (§5). Take ideas, not code, from
  the rest.
- **Traps the other tools hit**, each to be checked against a real log before relying on it
  **[ref]**:
  - A commodity buy line gives its quantity in hundredths of an SCU; a sell line gives SCU.
  - The game announces a contract again after a relog. Keep one contract per mission id.
  - Quantum targets outnumber arrivals about 1.4 to 1: a target is an intention.
  - A shop's name in a purchase line is a template shared across a chain. The place is the last
    inventory location before it.
  - The channel "left" notice is often missing, so leaving a ship is read from the seat line.
  - Tags get renamed between patches (the stow tag was, in mid-2026) and the trailing team tags
    change. Match on the stable middle of a line.
  - A `PSOCacheGen ...log` file in `logbackups` is a launcher shader run, not a session. One is
    there, dated 2026-11-05 **[seen]**. Skip them.
  - With a community language pack, notice text gains markup (`<EM4>`, `[BP]`, `[N Rep]`). The
    user's logs have none **[seen]**, but strip it anyway.

## 4. Features

### First version

1. **Status strip, always visible.** Local time, session length, game state (not running, menu, in
   game, ended), current location, current ship.
2. **Preflight check at launch.** A large pass or fail for the joystick order: the AB6 must be
   joystick 1 and the MTQ joystick 2. When the stick base is not detected, the keyboard takes its
   slot and every binding lands on the wrong device ([`../CLAUDE.md`](../CLAUDE.md) §1). This has
   cost the user sessions, so it gets the loudest alert on the page. Also shows the plan's
   "before you fly" notes.
3. **Now view.** Objectives in order, the next step, needed against held for each material,
   pending orders and timers, what there is to do at the current location, and the active
   contract with its current objective (contract tracking is in the first version: the user's
   decision, §15).
4. **Travel view.** Destination, the legs of the current run with the finished ones marked, and
   what to do on arrival.
5. **Activity views: Mining, Salvage, Combat and Cargo.** One family of four, shown according to
   what the user is doing (§11). The first plan had Mining only; on 2026-11-27 the user asked
   for "the other stuff like salvaging and combat and cargo hauling etc". The four share one
   skeleton, so the same kind of thing is always in the same place.
   - **Mining.** For the run's target ores: the scan numbers for each cluster size in large
     type, the quality figure to take a rock at and the one to skip, look-alike readings for
     that spot, and where to refine with the bonus.
   - **Salvage.** The plan's goal as needed against held (RMC for repairs, for example), the
     next step, the ship's hold in SCU, where to sell RMC and construction materials and at
     what price, and the salvage contract with its current objective when there is one.
   - **Combat.** Ship combat in space first, and on-foot missions as well (the user: "combat as
     in space combat too not just bounty hunting on foot"). It does not need a contract: a fight
     that simply happens still has the ship, the session tally and the controls.
     - *In the pilot seat:* the contract when there is one (bounty, patrol, defense) with its
       reward and its current objective in large type; the session so far (ships the user
       destroyed, ships lost, times downed); the jurisdiction and whether the user is in an
       armistice zone or monitored space; the controls strip; and the telemetry group when the
       stream is on.
     - *On foot (FPS missions):* the rig is not in use there (the user plays on foot with an Xbox controller,
       [`../CLAUDE.md`](../CLAUDE.md) §1), so the controls strip and the ship group go away and
       the contract, the objective, the downed or injured state and where the ship was left
       remain. The log does not record kills on foot (§3), so there is no tally of them.
   - **Cargo.** A hauling contract as a checklist of pickups and drop-offs with the SCU at each
     stop, the current stop and the next, and the total against the ship's cargo grid. For a
     trade run: what was bought, how much and at what price, where the plan says to sell it and
     the expected return, and the session's earnings.
   - **Mission.** The view for a contract that is none of the four above, and the same block
     inside every other view. The user's words: "FPS", "basically missions, etc". Whatever the
     mission is, it is shown one way: who gave it, its title, its reward, and its objectives as
     a checklist with the current one in large type, then where to go next. Several contracts
     can be active at once, so the others are listed under it. The log does not say which one
     the user is tracking; 5.0's telemetry stream is expected to (§3).
   - **Contract kinds are data, not code,** so that new kinds need no new code. The user wants
     5.0's mission types covered: "include the 5.0 shit like guild missions or whatever". What
     5.0 adds is not known here **[verify when 5.0 is installed]**. So a table in `reference/`
     maps a contract's generator name and title to a kind and a view, anything it does not know
     lands on the Mission view and is written to `data/unmapped.json`, and after a patch the
     table is extended from that build's mission list (the game's files first; SCMDB is the
     scriptable community source for missions) and from the first logs. The giver is shown as
     the log names it, whether that is a faction or a guild.
   - **Each carries the controls for its mode:** a short strip of the handful of stick and
     throttle controls that matter there, because this rig's bindings change with the operator
     mode ([`../CLAUDE.md`](../CLAUDE.md) §5). It is built from the same tables as the printed
     reference cards, so it cannot drift from them.
   - **What they cannot show (§3).** The log has contracts, objectives, places, ships,
     purchases, sales and deaths. It has nothing on cargo aboard, how much was salvaged,
     shields, hull or targets. So these views lean on the contract, the plan and reference
     figures, and show no gauge for anything that cannot be measured. With the telemetry stream
     on, Combat also shows countermeasures left and which systems are powered (feature 14).
   - More activities (medical runs in the Pisces, crafting at the fabricator) get a view when
     the user asks; until then the Now view covers them.
6. **Refinery view.** Which lines to refine and which to leave out, the method the user prefers,
   and the timers.
7. **Selling view.** The sell list with prices, when the plan has one for the current location.
8. **Alerts.** Red: joystick order wrong, downed or dead. Amber: hangar queue stuck past twice its
   estimate, quantum destination obstructed. Green: refinery order completed, blueprint received.
9. **Event feed.** The last 50 events in plain words with local times.
10. **Timers.** From the plan data, plus quick timers added from the page when the user is at
    their desk. A "work order completed" notice clears the matching refinery timer.
11. **Session summary.** When a session ends, a compact record is written to
    `data/sessions/`: duration, places, ships, notices, purchases, deaths. Claude's "check the
    logs" routine can read that instead of parsing the raw log again.
12. **`timeline` command.** Prints the same compact timeline for any log file. It replaces the
    scratch scripts sessions keep rewriting.
13. **`replay` command.** Feeds a past log through the dashboard at speed, so it can be built,
    tested and shown without the game running.

**Views switch by themselves.** A small table of rules maps the state to a view (§11). A view
picked by hand stays until the context next changes.

### With the telemetry stream (its own stage, §12)

Everything above works from the log alone. When the game's telemetry stream (§3) is on, the
dashboard adds:

14. **Ship state on the status strip.** Hydrogen fuel, speed, the aUEC balance, coupled or
    decoupled, landing gear, which systems are powered, and countermeasures left. Several of
    these are things the rig switches with no light of its own: the AB6 wing power panel, the
    decoupled toggle, the gear lever ([`../CLAUDE.md`](../CLAUDE.md) §4). VTOL is left off until a
    build reports it truthfully (§3, quirks).
15. **Taking the pilot seat.** The log only records leaving it. Read it from the ship block
    appearing in the stream, not from the stream's own seat event, which is unreliable (§3).
16. **Whatever 5.0 adds that the views can use:** a named location, quantum destination and
    state, the tracked contract. To be read from the stream itself once 5.0 is installed, not
    from this list.

These parts are hidden whenever the stream is not connected. Nothing in the log-driven views
waits for them.

### The Claude terminal (its own stage, §12 stage 4b)

The user asked for this on 2026-11-27, after the build had started: the dashboard should not be
a read-only display only. They want to alt-tab to it, in quantum for example, and ask Claude a
question with this project's context, without a second window and without typing anything to
get Claude going.

17. **A terminal panel that runs Claude Code.** A real terminal drawn in the page, connected to a
    Claude Code process that the service starts in the project root. It is the same program the
    user runs today, so everything works as they know it: `@STARCITIZEN.md`, approvals, a log
    check that updates memory and the game plan page.
    - **Dedicated.** The panel runs that one program. It is not a general shell, and nothing the
      page sends can choose a different program or different arguments (§8).
    - **It starts with the session brief already loaded** (the user, 2026-11-27: "that
      particular claude that starts in the dashboard uses our starcitizen.md file"). The service
      hands [`../STARCITIZEN.md`](../STARCITIZEN.md) to Claude Code as an addition to its system
      prompt when it starts it, read fresh from the file each time, so the user types a question
      and nothing before it. Loading the brief this way does not set off the ramp-up the brief
      describes for a session opened with the file alone: that takes minutes and would run every
      time the window opens. One line added in front of the brief says so: this session was
      started by the dashboard, the brief applies to every message, and a ramp-up happens only
      when asked for. That line lives in the config, so the user can change it.
    - **Starts with the dashboard window** (the user's choice, §15): Claude is up and waiting by
      the time the user first looks at it. When Claude exits, the panel offers to start it again
      with one key.
    - **Takes the keyboard only when the user comes to it.** The dashboard still never takes
      focus by itself (§11). When the user switches to the window, the terminal has the keyboard.
    - **Does not cost the views their room for nothing.** Each layout gives the terminal a fixed
      region (§11). The views are designed around it, not hidden behind it.
    - **Nothing it shows is kept.** The dashboard does not log, store or parse what passes
      through the terminal. Scrollback lives in the page and is bounded.

The log-driven views work with the terminal switched off (a setting), and `replay` never starts
one.

### Later, each only if the user asks

- Switching views from the keyboard while the game has focus, through a system-wide hotkey
  registered by the service. The hotkey is taken away from every other program, so choose
  combinations the game does not use (check the keyboard column of the action catalog) and ask
  the user first.
- A device watch that flags a stick or throttle dropping off USB.
- A controls view per operator mode, from the same tables the reference cards use.
- Switching views from the stick base's two unbound levers. The page cannot read them: the browser
  exposes at most 32 buttons per device and these are numbered 57 to 62 **[ref: Chromium source,
  §14]**. The service would have to read the stick itself through DirectInput.
- More on contracts than the first version shows: a history, pay and standing per contract, and
  the contract's internal name from the marker line (§3).

## 5. Shape

```
dashboard/
  PLAN.md  README.md  CLAUDE.md
  scdash.py            command-line entry point, run from the project root
  scdash/              the program: Python standard library only
    config.py          paths and defaults
    tail.py            log follower
    events.py          log line -> event
    telemetry.py       the game's telemetry stream -> events (optional second source, §3)
    state.py           events -> state (a pure function)
    server.py          local web server and event stream
    service.py         main loop, single instance, lifecycle
    terminal.py        the Claude terminal: one pseudo-console, one fixed program (§4, stage 4b)
    winutil.py         the Windows-only calls, each with a harmless fallback elsewhere
  web/                 index.html, app.js, style.css: no outside resources
    vendor/xterm/      the one outside library, a pinned release of xterm.js (§5, stage 4b)
  reference/           generic game data, committed (§10)
  tests/               unit tests and sanitized log samples
  data/                git-ignored: the user's plan data, config, state, session records, logs
```

Data flows one way: `Game.log` -> follower -> events -> state -> page. The state is always a pure
function of the log read so far plus the plan data. That one property gives most of the
idempotence in §7.

**Two sources, one state.** The telemetry stream, when it is on, is a second producer into the
same state: stream -> reader -> readings -> state. It comes in through an entry point of its own
and fills a slot of its own, so that it can never move what belongs to the log: the session's
last-event time, the event count, and the end time written for a crashed session. The views read
one state and never ask where a value came from. Telemetry values are live readings, not history, so they are shown while the
stream is connected and dropped when it is not; they are never written into the session records
as if the log had said them. The reader decodes about one snapshot a second and lets the rest go
by, since the stream sends 15 or more.

**Where each part starts from [ref: source audit of five log readers, 2026-11-27].** No existing
reader is a base to adopt whole, so the shape above stands. These parts need not be written from
nothing. Line numbers are for CSR at commit `ba6dad0`.

| Part | Start from | Change on the way in |
| --- | --- | --- |
| `tail.py` | §8 as written. sc-log-tracker's tailer shows the same design working (head bytes compared on every poll, bounded reads, the partial last line kept). Idea only. | - |
| Joining a notice's lines | CSR `sc_livelog.py`, lines 42-48 and 173-182 | Require the time prefix on each continuation piece. End only on the closing `" [<id>] to queue`. Never swallow a line that has its own level part, whatever its shape. |
| `events.py` | Written here as small typed records, one per marker in §3. SC Game-log Parser shows the pattern (idea only). Its notice-cleaning helper and several of its line patterns are CSR's (`sc_livelog.py` lines 16-119), credited like the rest: this plan first named only the two ranges above and `LogState`, and was widened on 2026-11-27 when review found those pieces in use. | One cheap test before any pattern: take the tag that follows the fixed-width time prefix and look it up in a table. |
| `state.py` | CSR's `LogState`, `sc_livelog.py` lines 128-434: contracts by mission id, objectives by objective id, quantum target, place history, size caps. | Feed it events, not lines. Remove its fall-back to the wall clock for untimed lines, which breaks §7. Keep one contract per mission id. Add what it lacks: session, ship, hangar queue, refinery, trade, the preflight check. |
| `telemetry.py` | CSR `sc_telemetry.py`, lines 1-450 | §12, stage 6. |
| `server.py` | Written here. sc-log-tracker's checks are the model (idea only): `Host` on every request, a custom header on writes, no address reuse on Windows, and noticing a closed page by peeking at its socket. | - |

Code copied from CSR keeps its copyright line and the MIT permission text, in a
`THIRD_PARTY_NOTICES` file in `dashboard/`. Thirteen of sc-log-tracker's patterns are identical to
older ones in CSR, so anything of that kind is credited to CSR. Nothing is copied from a project
with no license.

**Standard library only**, so there is nothing to install and nothing extra in memory. The repo's
tools must stay usable on a Mac ([`../tools/CLAUDE.md`](../tools/CLAUDE.md)), so keep every
Windows-only call in `winutil.py`: the parser, `timeline` and the tests then run anywhere.

**The one outside library: xterm.js, for the Claude terminal.** Drawing a terminal that Claude
Code's interface works in means handling cursor movement, colors, the alternate screen, pasted
text and a long list of control sequences. Writing that by hand would be the riskiest code in the
project, so the page uses xterm.js (MIT), the terminal that VS Code itself is built on. The user
chose how it comes in (§15): the file its authors publish for one pinned version, copied into
`web/vendor/xterm/` with its license, and its SHA-256 recorded in `THIRD_PARTY_NOTICES`, with a
test that the file still matches. It is served from the repo like the rest of the page; nothing
is fetched at run time. The same goes for its small fit add-on (same project, same license),
which sizes the terminal to its panel. The Python side stays standard library only: the
pseudo-console is reached through `ctypes` (`CreatePseudoConsole`, in Windows since 2018), in
`winutil.py` with the other Windows calls. Elsewhere the standard `pty` module does the same
job, so the panel can work on a Mac too, but that is not a goal.

**The event stream on `http.server` [ref, §14].** Keep the server's default HTTP/1.0 responses:
HTTP/1.1 would need an exact length on every response. Each connected page holds one thread. A
closed page is only noticed when a write fails, so send a comment line every 15 seconds and catch
the connection errors. Send a `retry:` value so the page reconnects quickly, and cap the number of
connected pages: the browser allows six connections to one address.

## 6. The service

"Service" here means a per-user background process, not a Windows service in the Service Control
Manager sense. A real Windows service is the wrong tool **[ref: Microsoft's service
documentation, §14]**: creating one needs administrator rights, it runs in a separate session
that cannot show a window on the user's desktop, and under the system account it does not see the
user's own settings. The project also asks the user before anything that needs admin rights.

- **Process:** `pythonw.exe dashboard\scdash.py run --background`. No console window. Under
  `pythonw` the standard output streams can be missing, so everything is logged to a file.
  `pythonw.exe` is at `%LOCALAPPDATA%\Programs\Python\Python312\` on this PC, and the `pyw.exe`
  launcher is installed too **[seen 2026-11-27]**. The task names the interpreter by its full
  path, which stops working when Python moves to a new folder on an upgrade: `install` records
  the path it used, and `status` says so when that path is gone.
- **Starts by itself:** a Task Scheduler task registered from an XML file **[ref, §14]**:
  - The logon trigger names the user's own account. That is the only form a non-admin may
    register. `schtasks /Create /SC ONLOGON` means "any user" and is refused with "Access is
    denied".
  - `InteractiveToken`, so it runs inside the user's desktop session and can open a window.
  - `ExecutionTimeLimit` `PT0S`. Without it Windows stops the task after 72 hours.
  - `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries` both false. Both default to true.
  - `MultipleInstancesPolicy` `IgnoreNew`, and a `WorkingDirectory` set to the project root. The
    default working directory is System32.
  - A five-minute repetition on the trigger. With `IgnoreNew` it does nothing while the service
    is alive, and relaunches it within five minutes if it has died.
  - If registration is still refused without elevation, fall back to a shortcut in the user's
    Startup folder and say so. Never elevate.
- **Stays up by itself:** do not count on the task's `RestartOnFailure`. Field reports say it
  does not fire after a crash or a kill. The main loop catches its own errors, logs them and
  carries on, and the repeating trigger is the backstop.
- **One way in, and a stop that stays stopped.** The repeating trigger has two side effects to
  design around (found in review, 2026-11-27):
  - The scheduler only knows about an instance it started itself. A copy started any other way
    would make it launch a second one every five minutes, each finding the lock and exiting. So
    when the task is installed, `start` goes through it (`schtasks /Run`).
  - A deliberate `stop` would be undone within five minutes. So `stop` also writes a marker file
    in `data/`, a background start that finds the marker exits at once, and `start` removes it.
- **Idles cheaply:** with no game running it does nothing but look for the game process every 10
  seconds. Read the process list with the Toolhelp snapshot calls (`CreateToolhelp32Snapshot`,
  `Process32NextW`) through `ctypes`: they return the names without opening any process. Do not
  run `tasklist`, PowerShell or a WMI query for this: starting a program every 10 seconds costs
  far more than the whole budget in §9.
- **Priority is inherited.** A program started by a below-normal process starts below normal
  too **[seen 2026-11-27 with a Python parent and child]**, so the browser window the service
  opens runs below normal as well. That suits a display that should yield to the game; just
  don't be surprised by it when measuring.
- **Follows the game:** when the game starts it begins reading the log, and can open the
  dashboard window on the side monitor. When the game has been closed for a few minutes it can
  close the window it opened, to give the memory back. Both are settings (§15).
- **Single instance:** a named mutex is the lock. Binding the port is not enough: Python's
  `http.server` sets `SO_REUSEADDR`, and on Windows that lets a second process bind the same port
  **[seen: local test, 2026-11-26]**. So the listening socket also sets
  `allow_reuse_address = False` and `SO_EXCLUSIVEADDRUSE`, which the same test showed refuses a
  second bind. The scheduler's `IgnoreNew` only stops copies the scheduler itself starts, so the
  mutex has to cover a manual `start` as well. `data/run.json` records the process id, port,
  start time and a random token. A health endpoint returns the program's name, process id and
  start time, which the commands compare with `run.json`, so a foreign program on the port is
  never mistaken for the service. It does not return the token (§8).

| Command | What it does | When repeated |
| --- | --- | --- |
| `run` | Runs in the foreground until Ctrl+C. For development. | Refuses if an instance is healthy. |
| `start` | Starts the background process and waits until it answers. | Already running: says so, exits 0. |
| `stop` | Asks the instance to shut down, using the token. | Not running: says so, exits 0. |
| `status` | State, uptime, port, game seen or not, memory in use, last event. `--json` for scripts. | Read-only. |
| `open` | Opens the dashboard window on the side monitor. | A page is already connected: does nothing. |
| `install` | Registers the logon task. | Replaces the same single task. |
| `uninstall` | Removes it. | Nothing to remove: exits 0. |
| `timeline [log]` | Prints the compact timeline of a log. | Read-only. |
| `replay <log>` | Serves the dashboard from a past log on a separate port, with its own data folder. | Never touches the live instance. |

Registering the logon task changes how Windows starts. The user asked for a service, so it is part
of this build, but tell them before running `install` and show them `uninstall`.

`install` runs `schtasks /Create /TN <name> /XML <file> /F`, which creates the task or overwrites
it. `schtasks /Delete /TN <name> /F` exits 1 when there is no task **[seen: local test by the
research agent]**, so `uninstall` treats that as success. After installing, read the task back
with `schtasks /Query /TN <name> /XML` and compare it with what was intended.

## 7. Idempotence

- **Commands:** the table above. Starting twice gives one instance; stopping twice is not an
  error.
- **State from the log:** each event is identified by the session and the byte offset of its
  line. Reading a log in one pass, in pieces of any size, or again after a restart gives the same
  state. Nothing is counted twice.
- **Restart mid-session:** the service reads the current log from the top and arrives at the same
  state as if it had watched live.
- **What the state depends on besides the log.** Three things: the plan data, what the user set
  on the page (quick timers, a view picked by hand), and the clock (countdowns, a queue that has
  waited too long). So the precise promise is: the same log, plan, user settings and clock give
  the same state. To keep it, everything derived from an event uses the event's own time, never
  the time it was read. Two things go wrong otherwise when a restart rereads the log:
  - An alert for something that happened two hours ago pops up again. Alerts expire by event
    time.
  - An old "work order completed" notice clears a newer timer at the same station. A notice
    clears a timer only when the timer's `ready_at` is at or before the notice's time, give or
    take a few minutes. The notice names the station and nothing else ("... Completed at MIC-L2
    Long Forest Station"), so with two orders at one station it clears the earliest that fits.
- **The one thing that cannot be rebuilt** is what the user entered on the page. Quick timers
  live only in `data/state.json`, so that file is their record, not a cache.
- **Files it writes:** written to a temporary file and then renamed into place, so a crash never
  leaves half a file. Only `data/` is ever written.
- **Plan data:** Claude rewrites `data/plan.json` whole each time. The dashboard never edits it.
- **Install:** `install` after `install` leaves one task, and `uninstall` puts things back as
  they were.

## 8. Safety

**The game.**

- Read-only toward the game, always. None of the game's own files is ever written, moved or
  locked. This repo sits inside `LIVE\user\`, so the dashboard's own files are the one thing
  written under `LIVE\`; §10 (*Where its own files live*) keeps those few and small.
- It stays outside the game process: no memory reading, no injection, no overlay in the game
  window, no input sent to the game. It never opens a handle to `StarCitizen.exe`; it only looks
  for the name in the process list.
- Where that stands with the publisher **[ref, §14]**: the game runs with Easy Anti-Cheat, and the
  publisher's notices about it are aimed at programs that change or interfere with game files.
  The terms of service ban macro and cheat utilities and harvesting other players' information.
  Nothing was found that mentions reading the log, in either direction, and no report of trouble
  from a tool that only reads it. That is an absence of objection, not an approval, so stay
  strictly read-only.
- **Telemetry, when it is on (§3).** The reader connects only to `127.0.0.1` on the game's
  telemetry port and calls only the read-only stream method. It never calls a method that makes
  the game do something, whatever a later build offers. It caps the size of what it will accept
  and treats every byte as untrusted. It does not switch the stream on: that is a step the user
  takes.
  - **The one method is enforced in the running code, not only promised.** The request the
    client sends is built once from a single constant, and the one function that writes to the
    socket refuses any other request. A test scans the whole of `dashboard/` for a second path,
    and others try to slip one through. Review found three ways past an earlier, weaker test.
  - **Everything is capped at the scale of a real snapshot** (about 700 bytes): message size,
    bytes and snapshots per second, fields walked, events kept. A server that floods any of
    these is dropped and retried later. Review showed that without those caps a hostile or
    broken stream could hold a core at 100% or grow the service by hundreds of megabytes.
  - **The program file is read with the same full sharing as the log** (§8, *The log must never
    be held open*), and only once its size and date have settled, so reading the stream's layout
    can never get in the way of the launcher patching the game.
- Other players' names appear in the log. Show them at most in the live feed, and never write
  them to the session records.
- **The log must never be held open.** At each launch the game copies the old `Game.log` into
  `logbackups\` and starts `Game.log` again **[seen 2026-11-26: each backup's creation time is the
  next launch's start, and it has its own file id]**. It empties `Game.log` in place; it does not
  delete and recreate it **[seen 2026-11-27: the file id was still `0x...2800000001d25f` after the
  6:23 PM launch on 2026-11-26, the same id noted before that launch, and the file's creation
  time is still 2026-02-02, the date of the oldest backup; and again across a launch at 5:41 AM
  on 2026-11-27, watched from this side: same id, new first line, and the old session's backup
  created eight seconds after the launch]**. So in this build there is no delete for a reader to
  block. Keep the careful form anyway, in case a patch changes that: open the file
  through `CreateFileW` with read, write and delete sharing, read the new bytes, and close it
  again on every poll. Other tools reopen the file on every read too, and no report of one
  blocking the game turned up **[ref]**. Then prove it: run the follower across a real game
  launch and confirm the backup appears and the new log starts.
  - **Proved [seen 2026-11-27, 12:57 PM].** The stage 1 follower polled `Game.log` once a second
    across a real launch. At 12:57:28 the game emptied the log in place (same file id before and
    after, 117,663 bytes down to 4,457), the old session's backup appeared in `logbackups` in the
    same second at the full 117,663 bytes, and the follower saw the new first line and began the
    new session at offset 0. Over 328 polls, up to the user standing in the game world: no
    error, no unreadable line, and the slowest poll took 2.6 ms. Still to do: the same launch
    check with the stage 2 service, whose log records these facts by itself.
- **Where the size comes from matters.** With the game running, `os.stat` gave the same size as
  an open handle in 20 samples out of 20, while the size in a directory listing (`os.scandir`)
  was behind in 4 of the 20, by up to 4 KB **[seen 2026-11-27, Python 3.12, game running]**. So
  `os.stat` or the open handle are both sound, and a directory listing is not. Opening the log
  with full sharing, reading its size and 400 bytes, and closing it took 0.3 ms. The simplest
  sound poll is: open, seek to the saved offset, read to the end, close.
- A session is identified by the first line of the log (`BackupNameAttachment=...`). Compare that
  line on **every** poll, and start a new session from offset 0 when it has changed or the file
  is shorter than the saved offset. The size test alone is not enough: a new log passes 18 KB
  within 10 seconds of a launch and 160 KB within 30, and the shortest November log is 32 KB, so
  after any pause the new log can already be longer than the old offset **[seen 2026-11-27]**.

**The PC.**

- No administrator rights, at install or at run time.
- The server binds to `127.0.0.1` only, so nothing else on the network can reach it.
- It makes no outbound connections, and the page loads nothing from the internet: system fonts,
  no CDN. That covers the service and the page. The browser that shows the page is another
  matter: a new browser profile contacts its maker by itself (updates, safety checks) unless told
  not to. So the switches in §11 that turn that off are required, and what still goes out is
  checked once with the window open **[verify]**.
- It serves a fixed list of its own files. No path from a request is ever used to open a file.
- **Every** request, reads included, must carry a `Host` header of `127.0.0.1:<port>` or
  `localhost:<port>`; anything else is refused. Without that check on reads, a web page that
  points its own domain name at 127.0.0.1 could read the state and the event stream, which hold
  the user's handle and location.
- Requests that change anything (timers, forced view, shutdown) also need the token in a custom
  header and a JSON body. The page finds the token in the HTML the service serves to it; no
  endpoint hands it out. Together with the `Host` check, this stops another web page in the
  user's browser from reading or driving the dashboard.
- Bounded everything: line length, feed length, session records kept, its own log size.
- It runs at below-normal priority, so it yields to the game.
- It only ever closes a browser window it opened itself, identified by process id and start time.

**The Claude terminal (§4).** This is the one part of the dashboard that is not read-only, so it
is fenced on every side.

- **One fixed program.** The service starts Claude Code's own executable with the project root
  as its working directory. It finds the program the way a terminal would, by looking up
  `claude` on the user's PATH once at start (`shutil.which`), and writes the full path it found
  to its log; a path in the local config overrides that. The program and its arguments
  come from the config file and nowhere else: no request carries a command, a path, an argument
  or an environment variable. A test proves that nothing sent to the server can change what is
  started. The session brief it is given (§4) is the file the config names, inside the repo, read
  by the service itself.
- **It is Claude Code that acts, under its own rules.** What the terminal can do to the PC is
  what Claude Code can do in any terminal, with the user's own permission settings and approval
  prompts. The dashboard adds no permissions and skips none: it never starts Claude with a flag
  that turns approvals off.
- **Only the dashboard's own page can reach it.** The terminal's endpoints need the token, the
  `Host` check and a matching `Origin`, like every changing request. Keystrokes are a changing
  request. If the token were known to another page it could type into Claude, which is why no
  endpoint hands the token out and why the server answers 127.0.0.1 only.
- **Still nothing toward the game.** The terminal sends no input to the game and reads nothing
  from it. Claude reads the log files the way it always has.
- **No leftovers.** When the window closes, the service stops, or the user ends the panel, the
  Claude process and everything it started are ended (a Windows job object does this even if the
  service is killed). Closing the pseudo-console is not enough by itself **[verify]**.
- **Nothing kept.** No terminal output or input is written to the service log, the state file or
  the session records.
- **Off switch.** `terminal.enabled` in the config. With it off, the endpoints do not exist.
- **Claude Code itself** is not installed as a program of its own on this PC: the only copy is
  inside the VS Code extension, in a folder whose name changes with each update **[seen
  2026-11-27]**. The stage installs Anthropic's own per-user copy (no administrator rights). If
  it is missing, the panel says so and nothing else is tried.
  - **Install it the way the user's system-refresh kit does,** so a rebuilt PC matches this one:
    `winget install --id Anthropic.ClaudeCode -e --source winget --scope user`, after checking
    that `claude --version` does not already work. (The kit is the user's own, outside this
    repo; a Windows reinstall was planned as of 2026-11-27.)
  - What is known about the two ways to install it **[ref: the session that built the kit, from
    Anthropic's set-up documentation, 2026-11-27; neither was run]**: the winget package is one
    portable `claude.exe`, expected under `%LOCALAPPDATA%\Microsoft\WinGet\` with a link on the
    user's PATH, and it does not update itself (`winget upgrade Anthropic.ClaudeCode`).
    Anthropic's own installer script puts it in `%USERPROFILE%\.local\bin`, does not add that
    folder to PATH, and updates itself. The two places differ, which is why the dashboard looks
    on PATH and not at a fixed path.

**Privacy.** The repo is public.

- The user's handle appears in log lines (channel names, hangar names). It stays in memory and in
  `data/`, and never goes into a tracked file.
- `dashboard/data/` is git-ignored.
- A log line carries more than the handle (§3, *Reading the lines*): the Windows user name, the
  PC's name, the account id, the character and player ids, session ids and server addresses.
  Test samples have every one of these replaced with invented values, not just the handle.
- Before each commit, search the staged changes for the real handle, Windows user name, PC name,
  account id and player id. A test can do this too, reading them from the local config and the
  current log, and skipping when there is none.
- `data/plan.json` holds the user's progress and is never committed. `plan.example.json` shows
  the schema with invented content.

## 9. Performance

Budgets to measure against, not promises. Record the measured figures in `dashboard/CLAUDE.md`.

| What | Budget | Measured 2026-11-27 with a stand-in, game not running **[seen]** |
| --- | --- | --- |
| Service memory | 30 MB or less | 12 MB private, 22 MB working set: Python with a web server, one event stream, `json`, `re`, `ctypes` |
| Service CPU, game running | 0.2% of one core or less, averaged over 10 minutes | No measurable CPU over 10 seconds while pushing one update a second to one page. Log reading not included. |
| Service CPU, no game | effectively zero: one process check every 10 seconds | not measured |
| Reading a whole 5 MB log at startup | 1 second or less | About 0.04 seconds (120 MB a second). The 376 MB log took about 3 seconds. |
| Dashboard window, whole browser process tree | 250 MB or less of *private working set*, the figure Task Manager shows as memory | Edge app window with its own profile, 1100x700: 11 processes, **108 MB** private working set, 292 MB committed, 0.6% of one core for an update a second. The summed working sets read 552 MB, because shared pages are counted in every process: don't use that figure. |
| For comparison, a native window | none set | The same content drawn by Python's own `tkinter`: one process, **12 MB** private working set, 15 MB committed (§15) |
| Telemetry reader, when the stream is on | 1% of one core or less, and no more than 5 MB added to the service | not built. One other tool's author reports about 59 MB and 1% of a core for a whole Node service doing this **[ref: SC Companion's README]**. |
| The Claude terminal: what it adds to the service and the window | 5 MB or less in the service; 40 MB or less in the window, with scrollback capped | not built |
| The Claude Code process the terminal runs | None set: it is the user's choice to have it, and it is not the dashboard's own memory. Measure it and write it down. | About **200 MB** private working set each for the two Claude Code processes of a busy VS Code session (194 and 234 MB) **[seen 2026-11-27]**. A fresh one is not measured. |

The stand-in scripts were scratch files and are not in the repo. The figures need taking again on
the real program, with the game running and the window on the side monitor.

How to stay inside them:

- **Read only what is new.** Once a second, open the log, read just the bytes past the saved
  offset, and close it (§8). Never reread the file. Read in pieces of at most 1 MB, so that an
  error flood (§3: up to 3.7 MB a second) or a restart on a very large log cannot grow the
  service's memory. A flood costs a few percent of one core while it lasts; that is accepted.
- **Filter before matching.** One cheap test decides whether a line matters at all: the tag that
  follows the fixed-width time prefix, looked up in a table (§5). Most lines are discarded after
  that single test. Of the five other readers audited, only one does this; the rest run a pattern
  on every line.
- **Push, never poll.** The page holds one event stream open. The server sends the state only
  when it changes, and merges bursts into at most two sends a second. The state is a few
  kilobytes.
- **A page that does almost nothing.** No framework, no web fonts, no image files (icons are
  inline SVG), and nothing that animates while the page is idle. A short one-off transition when
  a view or an alert changes is allowed: it costs nothing between changes. One one-second timer
  drives the clocks and countdowns. Only the parts that changed are redrawn.
- **Write to disk rarely.** The state file is saved at most every 10 seconds, and only when
  something changed.
- **Clocks from the system time.** Each tick computes the time from the clock instead of counting
  ticks, so a page that was paused or slowed is right again the moment it is visible.
- **Give memory back.** The window can close itself a few minutes after the game exits.

If the window goes over budget, measure with the browser's own task manager (Shift+Esc) before
changing anything. Showing the page in the browser the user already has open would cost roughly
one page less **[ref]**, but the placement switches are then ignored and their extensions run in
the page. The research turned up no way to show an HTML page in tens of megabytes. A native
window does fit in tens of megabytes, at the price of not being a web page: that choice is the
user's, in §15.

## 10. Data

**Where its own files live.** `dashboard/data/` (git-ignored) holds only small text files: the
plan, the config, the state, session records and the service's log. The browser's profile folder
does not go there. It goes in `%LOCALAPPDATA%\scdash\browser`: one 35-second run left 284 files
and 18 MB in it **[seen 2026-11-27]**, and it keeps changing for as long as the window is open.
Inside the repo it would sit in the game's folder and in the VS Code workspace, where the
editor's file watcher would follow every change (the watcher part is my reasoning, not measured).

**`data/plan.json`: the user's plan, local only.** Claude writes it in the same routine that
updates the game plan page, so the page, memory and the dashboard always agree. The dashboard
rereads it when its modified time changes. If it is missing or invalid, the dashboard keeps the
last good copy and shows a small notice.

```json
{
  "updated": "2026-11-26T17:30:00-08:00",
  "preflight": ["Load the MOZA profile in the Keybindings menu"],
  "objectives": [
    {
      "id": "drive-ore",
      "title": "High-quality ore for the Agni and the Huracan",
      "status": "in_progress",
      "next_step": "Run B: mine Agricium and Beryl at CRU-L5",
      "materials": [
        {"name": "Tungsten", "need_scu": 2.22, "held_scu": 2.66, "min_quality": 600}
      ]
    }
  ],
  "run": {
    "name": "Run B",
    "targets": ["Agricium", "Beryl"],
    "legs": [
      {"to": "CRU-L5 field", "codes": ["LOC_RR_S2_L5"], "gm": 40.8, "view": "mining",
       "do": "Mine Agricium and Beryl"},
      {"to": "CRU-L1", "codes": ["LOC_RR_S2_L1"], "gm": 18.3, "view": "refinery",
       "do": "Refine the Beryl only"}
    ]
  },
  "timers": [
    {"id": "t1", "kind": "refinery", "label": "Tungsten order", "location": "MIC-L2",
     "ready_at": "2026-11-26T16:21:00-08:00"}
  ],
  "sell": [
    {"ore": "Taranite", "scu": 7.8, "quality": 310, "price": 28000, "where": "TDD New Babbage"}
  ],
  "notes": ["Free text shown on the Now view"]
}
```

Use the codes the log actually prints, from either family (§3, *Reading the lines*);
`reference/locations.json` has every one. A leg to an L-point field lists the station's
quantum code (`LOC_RR_S2_L5` is CRU-L5 Beautiful Glen Station), because that is the jump the log
shows; the leg's `view` is what makes it a mining stop (§3).

Two things the page has to be honest about:

- **Held amounts are only as fresh as `updated`.** The log cannot see what is mined or carried
  (§3), so nothing moves `held_scu` during play. The page prints the `updated` time beside every
  held figure.
- **Times carry their offset.** Read them with `datetime.fromisoformat` and convert with
  `astimezone()` and no argument. Python's `zoneinfo` has no time-zone data on Windows without an
  extra package, so a zone name such as `America/Los_Angeles` would break the
  standard-library-only rule **[ref: Python's `zoneinfo` documentation]**.

**`reference/`: generic game data, committed.** Nothing here is personal. Every file carries its
source and date, and marks each figure as read from the game's files or taken from a community
source, as [`../CLAUDE.md`](../CLAUDE.md) §11 does. Build them from the memory notes
`sc-4103-gameplay-facts`, `sc-ore-quality-mechanics` and `goal-drive-ore-agni-huracan`:

- `locations.json`: log code -> display name, kind (station, field, landing zone, gateway), body.
- `ores.json`: scan value per rock, cluster sizes, the fixed quality figures, look-alikes.
- `refineries.json`: yield bonus by station and ore. Player-reported, so dated.
- `resources.json`: the resource id in a commodity sale line -> the commodity's name. The names
  come from the `ResourceType.<Name>` records in the game's `Game2.dcb` **[seen 2026-11-26: nine
  ids from a real sale were named this way]**. Memory note `sc-game-log-reading` has those nine
  and the method.

An unknown location code is shown raw and added to `data/unmapped.json`, so the table can grow
from real play.

**Built 2026-11-27.** The four tables are in `reference/`, made by `build_reference.py` from the
installed game's files (about 90 seconds; `--check` says whether they are current). Run it after
every game patch.

- Generated and hand-entered data are separate files: `<name>.json` is output only, and
  `<name>.hand.json` is the only place to type anything in. The generator refuses to overwrite
  an output that was edited by hand.
- What they hold: 3,415 location codes for 1,517 places, all 207 commodity ids, 39 ores with
  their scan readings per cluster size, quality figures and look-alikes, and refinery yields for
  20 stations.
- How it was checked: every location code in the user's November logs resolves (716 of 719
  across all 409 logs; the three that don't are generic names from February and March), every
  commodity id in their sale and purchase lines resolves (28 of 28), and all 23 ores that memory
  holds a scan value for match the game exactly.
- Refinery yields are the one part not from the game: no station yields are in the client's
  records. They are a UEX snapshot (its open API, rows dated 2026-10-16 to 2026-11-19) plus 12
  readings off a refinery terminal on 2026-11-26, which agree with UEX on every value. Each
  figure carries its date and source.
- **Not in the tables yet**, wanted by the views: commodity prices and which shop name in a sale
  line is which place (Selling), method cost and time and which stations have a refinery
  (Refinery), and distances (Travel). Stage 3 adds what its views need.
- The scan rule, reading = one rock's value x the number of rocks, is community knowledge, not
  from the files. It matches what the user has seen in play.

**`data/state.json`, `data/sessions/`, `data/run.json`, `data/service.log`:** the service's own
files, all local, all bounded.

## 11. The page

- One page, read at arm's length and beyond: large type, high contrast, a dark theme, few things
  per view. If it cannot be read in two seconds, it has too much on it.
- **It has to look good and modern** (the user, 2026-11-27: "make sure our design aesthetic
  looks good and modern"). Readable is the floor, not the goal. How that is made sure of:
  - **One design system, in the stylesheet.** Named colors, a type scale, spacing and corner
    sizes are defined once as CSS custom properties, and every view is built from them. No view
    invents its own color or size.
  - **The user picks the look.** Three different visual directions are mocked up as real HTML
    and CSS with invented data, in both orientations, before the views are built. The user
    chooses one, and its stylesheet becomes the dashboard's (§15).
  - **Checked by looking.** Every view is captured at 1920x1080 and 1080x1920 and looked at by
    the agent that built it and by the reviewing session: alignment, spacing, hierarchy, nothing
    clipped. A view that works but looks rough is not done.
  - **Inside the performance rules (§9).** System fonts only (Windows 11 ships good ones), no
    image files (icons are inline SVG), no outside resources, nothing that moves while the page
    is idle.
- **Two layouts, landscape (1920x1080) and portrait (1080x1920): the user's requirement of
  2026-11-27.** The monitor is stood either way up from one day to the next. The page chooses by
  the shape of its own window (the CSS `orientation` media query), so rotating the display in
  Windows is all the user does: no setting, no reload, no second page. Each view is designed for
  both shapes and checked in both, not designed for one and squeezed into the other.
  - Landscape: the status strip across the full width at the top; under it the current view on
    the left and the Claude terminal down the right; the feed at the bottom of the view.
  - Portrait: the status strip across the top (two rows), the current view at full width, the
    feed under it, and the terminal as a band across the bottom.
  - **Alerts sit across the top of the view in both layouts, and timers live inside the views**
    (the countdown on Now, the timer line on Travel). The first plan put alerts and timers in a
    rail down the side; in landscape that side is the terminal's, and the mockups showed a
    full-width alert reads better anyway.
  - With the terminal on, the view area is close to square in both layouts (1140x1080 and
    1080x1200), so a view keeps one internal arrangement and only its widest pairs stack in
    portrait.
  - The feed is short: 4 lines on Now and 3 on the activity views in landscape, up to 6 in
    portrait.
  - The type sizes in each layout are set for that layout. Do not scale the whole page by the
    window's width: at 1080 wide everything would shrink to just over half.
- **The look is direction B, "Avionics"** (the user's choice on 2026-11-27, §15): a well-made
  instrument panel without the sci-fi costume. Bahnschrift in its condensed and normal widths
  (set with `font-stretch`; it ships with Windows), 1-pixel line work, panes with bracketed
  corners, segmented meters, labeled data blocks, controls as a dotted-leader checklist, an
  ink-blue ground and one cyan accent. Red, amber and green always come with a shape and a word:
  an octagon, a triangle, a check. The terminal's type is Cascadia Mono with Consolas behind it
  (Cascadia comes with Windows Terminal, not with Windows).
  - The mockup is the starting point for the real page: `dashboard/data/design/b/` holds its
    `index.html` and `style.css`, with every screen reachable by a `#name` on the address, and
    `dashboard/data/design/shots/` holds the captures. The folder is git-ignored; the two
    directions that were turned down are beside it.
  - **Make the small labels bigger than the mockup's.** Its condensed capital labels are 14
    pixels, the smallest text of the three directions. Nothing on the real page is under 18.
  - Rough spots the designer listed, to fix when the views are built: an empty band above the
    controls on portrait Combat, loose gaps on the on-foot portrait, stretched side panes on
    Mission, and two cases never captured (six objectives, a very long giver name).
  - Travel shows the short place name large ("CRU-L1") with the full name on the line below.
- **The Claude terminal has a fixed region in each layout** (§4): a column down the right side in
  landscape, 780 pixels wide (41%, about 76 columns of 16-pixel type), and a band across the
  bottom in portrait, 720 pixels tall (37.5%, about 27 lines). The views are laid out in what remains and stay fully visible
  while the terminal is in use. With the terminal switched off, the views take the whole screen.
  The terminal's type is sized for someone sitting at the keyboard; the views' type is still
  sized for the pilot's seat.
- Numbers the user acts on (scan values, quality figures, countdowns) get the largest type.
- Times are local. American spelling and month-first dates, as everywhere in this project.
- No sound: browsers block it until someone clicks the page.

**Opening the window [ref, §14].** Use the browser's app mode with a profile folder of its own:

```
msedge.exe --user-data-dir=<%LOCALAPPDATA%\scdash\browser> --app=http://127.0.0.1:<port>/
           --window-position=<x>,<y> --start-fullscreen --no-first-run
           --no-default-browser-check --disable-background-networking
           --disable-component-update --disable-sync
```

- The separate profile folder is required. Without it the launch is handed to the browser that is
  already running, and the placement switches are dropped.
- `<x>,<y>` is any point well inside the side monitor. Full screen then fills that monitor. F11
  leaves full screen and Alt+F4 closes the window.
- Take the side monitor's bounds from Windows each time the window is opened, never from a
  stored size: a monitor turned to portrait reports 1080x1920 and can sit at a different place on
  the desktop. Whether a full-screen window follows a rotation made while it is open, without
  being reopened, is not known **[verify in stage 4]**.
- Do not use `--kiosk`: it ignores placement and is awkward to leave.
- `--disable-background-networking`, `--disable-component-update`, `--disable-sync` and
  `--no-default-browser-check` are required: they keep the new profile from going online by
  itself (§8). The stand-in window in §9 ran with them **[seen 2026-11-27]**. Leave
  `--disable-gpu` and `--single-process` alone.
- A window that is visible but not focused keeps updating at full rate. One that is minimized or
  fully covered is slowed down, which costs nothing here.
- The game should run in borderless window mode, so a click on the side screen does not minimize
  it.
- Whether the game keeps taking stick and throttle input while another window has focus is not
  known for 4.10. An old report (2020) had the throttle latching when the game lost focus. Until
  it has been tested on the ground, the user should not click the side screen while flying, and
  the dashboard must never take focus by itself.
- Opening the window did not take focus in one test: a background process started the Edge app
  window while another program was in front, and that program was still in front 3 and 25
  seconds later **[seen 2026-11-27; the game was not running]**. Stage 4 repeats it with the game
  in front.
- A service that restarts mid-session must not open a second window. The old page reconnects by
  itself within seconds, so wait for that before deciding a window is needed.

View rules, kept as a small table in code so they are easy to tune. The first row that fits
wins:

| State | View |
| --- | --- |
| No game running | Now, with the last session's summary |
| Game starting or in the menu | Preflight |
| Downed or dead | Now, with the alert on top |
| Quantum target chosen, until arrival | Travel |
| Arrived at a leg of the current run | The view that leg names: Mining, Salvage, Combat, Cargo, Refinery or Selling |
| At a place with a sell list | Selling |
| An active contract | Combat, Cargo or Salvage when its kind is one of those; Mission for any other kind, known or not. The kind comes from the contract-kinds table (§4), which reads the generator name in the mission marker line (§3) **[verify: which names occur]**. |
| In the pilot seat of a ship that has one job | That job's view: the Golem is Mining, the Salvation Salvage, the Golem OX Cargo, the M80 Combat. A ship with two jobs (the Hyūn mines and salvages) decides nothing. The ship-to-job table is in `reference/`, with the fleet in [`../CLAUDE.md`](../CLAUDE.md) §11 as its source. |
| Anything else in game | Now, for the current location |

The log does not say which operator mode the seat is in, so the rules above are the best
available signal for the activity. The telemetry stream may say more (§3); if it does, it goes
above the contract row.

## 12. Build order

Commit and push after each stage that works, as the project always does. Each stage ends with a
check that can actually fail.

1. **Parser and state, no server.** `tail.py`, `events.py`, `state.py`, `timeline`, tests.
   *Done when:* `timeline` on the log of 2026-11-26 afternoon reproduces the write-up in memory
   (`sc-4103-gameplay-facts`, "Tungsten Run A"), and feeding a log in random-sized pieces gives
   the same state as feeding it whole.
2. **Service and a minimal page.** `run`, `start`, `stop`, `status`, single instance, the event
   stream, the status strip and the feed, `replay`.
   *Done when:* `start` twice leaves one instance, `stop` twice is clean, `replay` of a past log
   shows the session unfolding, a 100 MB flood of junk lines does not grow the service's memory,
   and the follower has been run across a real game launch without disturbing the log rotation.
3. **Views and plan data.** The reference files, `plan.json`, the views, the view rules, alerts,
   timers. The look comes from the direction the user picked (§11, §15).
   - **Before the Salvage, Combat and Cargo views: find out what those activities leave in the
     log.** The stage 1 survey was built around mining sessions. Go through all the logs, not
     only November's, for sessions with bounty, hauling and salvage contracts and with commodity
     trades, and list what is there: objective texts for pickups and drop-offs, the contract's
     generator name, the user's own kills in `<Vehicle Destroyed>` lines, jurisdiction and
     armistice notices, anything on cargo or salvage. For combat, look at ship fights in space
     as well as on-foot missions, with and without a contract: is there any line that shows a
     fight has started (a ship destroyed nearby, damage to the user's ship, a missile warning),
     so the view can come up for a fight nobody planned? CSR's reader tracks hauling drops from the
     log; stage 1 left that out because no November log has one. Add events for what is found,
     with tests, and mark what could not be seen in any log as unverified until the user flies
     it.
   - **Reference data the new views need:** a ship table (class name in the log, display name,
     job, cargo grid in SCU), commodity prices with their date, which shop name in a sale line
     is which place, and a controls table per operator mode generated from the card tables in
     [`../tools/regen_cards.py`](../tools/regen_cards.py), with a test that it still matches
     them.
   - **Plan data for every activity.** `plan.json` (§10) was drawn up for a mining run. A leg's
     `view` can name any activity view, and the run carries what that view shows: targets for
     mining, a goal and a sell point for salvage, the trade for a cargo run. Settle the shape in
     this stage and write `plan.example.json` with one run of each kind.
   *Done when:* a replay of a mining session shows Preflight, Travel, Mining and Refinery at the
   right moments, a replay of a session with a contract shows Combat, Cargo or Salvage as its
   kind requires (a real session where the logs have one, a built sample where they don't, and
   the report says which), a deliberately wrong joystick order in a test log raises the red
   alert, and
   every view has been captured at 1920x1080 and at 1080x1920 (a headless browser screenshot of
   the replay) and looked at: nothing clipped, nothing overlapping, and the numbers still the
   largest thing on the screen.
4. **Autostart and the window.** `install`, `uninstall`, `open`, opening on the side monitor,
   closing after the game exits.
   *Done when:* after signing out and back in the service is running, starting the game opens the
   window on the side monitor, the window fills it in landscape and in portrait, the game keeps
   focus and stick input when it opens, a `stop` is
   still stopped ten minutes later, and the measured figures are inside the budgets in §9 or the
   overrun is written down with its cause. The side monitor was not connected yet on 2026-11-27,
   so this stage waits for it.
   **4b. The Claude terminal** (§4, §8). Built after the window works, because it lives in that
   window. `terminal.py`, the pseudo-console calls in `winutil.py`, the xterm.js files, the
   panel in both layouts, the settings.
   - **Carrying the bytes.** Output goes to the page on an event stream of its own, and
     keystrokes come back as small posts, both with what the server already has. Try that first:
     everything is on 127.0.0.1, so the delay should not be felt **[verify by typing in it]**. A
     hand-written WebSocket is the fallback if it is.
   - **Start and end.** The service starts Claude when the dashboard window's page connects, and
     ends it when that page has been gone for a minute (a reload must not kill it). A service
     that restarts mid-session cannot keep the old process, so the panel says the session ended
     and offers to continue the last conversation (`claude --continue`).
   - **The window must not close under a conversation.** The setting that closes the window a
     few minutes after the game exits (§6) waits while the terminal has had a key press in the
     last 30 minutes or Claude is still writing.
   - **Size.** The terminal is told its size in rows and columns whenever its panel changes
     shape, so turning the monitor re-fits it.
   - **The brief.** Find out from the installed Claude Code's own help which option adds a file
     or a text to the system prompt of an interactive session, and use that. If only a text
     option exists, the service reads the file and passes its text as one argument (the brief is
     about 15 KB; a Windows command line holds 32 KB).
   *Done when:* opening the window brings Claude up in the project root with nothing typed; a
   plain question with no `@STARCITIZEN.md` in front is answered by a session that already has
   the brief (ask it what needs the user's approval and compare with the file), and it did not
   start a ramp-up by itself; an approval prompt can be answered from the panel; keys, paste, arrow keys and Ctrl+C behave as in a normal terminal; it re-fits in
   landscape and portrait; closing the window leaves no Claude process or child behind; a request
   without the token, with a foreign `Host` or with a foreign `Origin` cannot reach it; the test
   that nothing sent can change the program passes; and the measured memory of each part is
   written down.
5. **A flown session.** The user plays one session with it running.
   *Done when:* its session summary agrees with Claude's own reading of the same log, and the user
   has said what they want changed.
6. **The telemetry source.** `telemetry.py`, the ship-state parts of the strip, and the seat
   event. It starts with the user's go-ahead to switch the stream on (§15), and with a fresh read
   of what the installed build really sends, because 5.0 changes the list (§3).
   - **Start from CSR's reader, not from nothing.** The first 450 lines of CSR's
     `sc_telemetry.py` are a protobuf decoder, a schema loader and a small HTTP/2 stream client,
     standard library only, MIT: lift them with the copyright notice **[ref: source audit,
     2026-11-27]**. Fix on the way in: no limit on message size, an unbounded number loop, a
     fixed port (take it from the log's `GameTelemetryService]: 127.0.0.1:<port>` line, else
     2942).
   - **Decode on demand.** Keep only the newest raw message and decode it once a second, so 15
     or more snapshots a second cost almost nothing even if the game-side rate setting is
     ignored.
   - **One request path, as a constant,** with a test that fails if any other path is ever
     requested (§8).
   - **The reader learns the stream's layout from the installed game's program file,** read-only,
     at start, and keeps it in `data/`, never in git: the user's decision (§15). CSR's loader
     does this, keyed on the file's size and date so it rereads after a patch.
   - Retry quietly every 5 to 10 seconds while the game runs, slowing to once a minute after a
     few minutes of refusals. That also covers a build that ships with the stream switched off.
   *Done when:* with the stream on, the strip shows fuel, speed and the coupled, gear and power
   states and they match the cockpit; with the stream off or refused, those parts are simply
   absent and everything else works; the reader stays inside its budget in §9; and a recorded
   stream replays through the tests without the game.
7. **Docs and routines** (§16).

## 13. Tests

Use `unittest` from the standard library, run from the project root.

- Events: one test per marker, on sanitized lines copied from real logs.
- Records: a notice split across lines is read as one notice with its whole text, a notice
  logged three times counts once, and lines with no time are skipped (§3, *Reading the lines*).
- State: the session life cycle, quantum travel, arrivals, a destroyed or stowed ship that is not
  the user's, death and respawn, a return to the menu that is not a session end.
- Restart: rereading a session from the top does not raise old alerts again, and an old
  completion notice does not clear a newer timer (§7).
- Flood: 100 MB of lines that match nothing is read in pieces, without the memory growing.
- Incremental reading: random-sized pieces give the same state as one pass. A partial last line
  is held until its newline arrives.
- Rotation: the log getting shorter, or its first line changing, starts a new session.
- Not a session: a `PSOCacheGen` file in `logbackups` is skipped by `timeline` and the summaries.
- Credit: every file that holds code copied from another project is listed in
  `THIRD_PARTY_NOTICES` (§5).
- Service: second `start`, `stop` with nothing running, the port already taken by something else.
- Server: a changing request without the token is refused, and so is one with a foreign `Host`.
- Terminal: the program started is the configured one whatever a request holds; the endpoints
  refuse a missing token, a foreign `Host` and a foreign `Origin`; they do not exist when the
  terminal is switched off or in `replay`; ending the panel ends the whole process tree (with a
  harmless stand-in program, not Claude); the xterm.js files match their recorded SHA-256.
- Privacy: no tracked file under `dashboard/` contains the user's handle, Windows user name, PC
  name, account id or player id (§8).
- Speed: a 5 MB log parses inside the budget.

## 14. To check before relying on it

Research on the first three points was started on 2026-11-26. Findings are second-hand until the
build confirms them on this PC; each names its source.

1. **Answered, autostart [ref].** A non-admin may register a logon trigger only when it names the
   registering user
   ([Microsoft, MS-TSCH](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-tsch/d90eccec-83e9-450c-b144-17633c47be9a)),
   and `schtasks /SC ONLOGON` is documented as "any user"
   ([Microsoft, schtasks create](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create)).
   Task defaults, including the 72-hour limit, are in
   [Microsoft's task settings reference](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-settingstype-complextype).
   Why a real service does not fit is in
   [Microsoft's notes on interactive services](https://learn.microsoft.com/en-us/windows/win32/services/interactive-services).
   That `RestartOnFailure` does not fire after a crash comes from other projects' issue trackers,
   not from Microsoft. Still open: whether the task's command needs quotes around a path with
   spaces, which file encoding `schtasks /XML` accepts, and whether PowerShell's
   `Register-ScheduledTask -AtLogOn -User <self>` also works without elevation. The quoting
   question decides whether the task runs at all here, because the repo's path has spaces in it.
   Giving the script as a relative path (`dashboard\scdash.py`) with the working directory set
   keeps spaces out of the arguments; expect the working directory itself to be wanted without
   quotes **[verify]**. Also open: whether Task Scheduler lowers a task's priority by itself (its
   default task priority is said to be below normal, with lower disk and memory priority too),
   which would make the service's own priority call redundant **[verify]**.
2. **Answered, the window [ref].** Placement switches are read only from a browser process's own
   command line, which is why the separate profile folder is needed
   ([Chromium source](https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/ui/browser_window_state.cc),
   [Eric Lawrence on Chromium startup](https://textslashplain.com/2022/06/15/chromium-startup/)).
   Throttling follows visibility, not focus
   ([Chrome's timer throttling notes](https://developer.chrome.com/blog/timer-throttling-in-chrome-88)).
   The 32-button limit is in
   [Chromium's gamepad code](https://chromium.googlesource.com/chromium/src/+/main/device/gamepad/public/cpp/gamepad.h).
   Event stream behavior is in the
   [HTML standard](https://html.spec.whatwg.org/multipage/server-sent-events.html) and
   [Python's `http.server`](https://docs.python.org/3/library/http.server.html). Memory has no
   official figure: two project reports measured the same engine at about 76 MB for a blank page
   and 113 MB for a small app, and a separate profile cost about 75 MB more than a shared one.
   Still open: the window's real memory on this PC, whether `<x>,<y>` are scaled or physical
   pixels when the main monitor uses display scaling, and whether a game in exclusive full screen
   counts as covering the side monitor.
3. **Answered in part, other tools and policy [ref].** The tools are named in §3; their code is
   the source of the extra markers listed there. Policy sources: the publisher's
   [anti-cheat announcement](https://robertsspaceindustries.com/spectrum/community/SC/forum/1/thread/easy-anti-cheat-coming-in-alpha-3-15-1),
   its [anti-cheat support article](https://support.robertsspaceindustries.com/hc/en-us/articles/4412276152343)
   and the [terms of service](https://robertsspaceindustries.com/en/tos). Community sources say
   the publisher has removed some data from the log over time (other players' deaths, for
   example), so a marker can vanish in a patch: after each patch, run the tests against a fresh
   log. Still open:
   - Whether the game takes stick input while unfocused. Test it on the ground.
   - **Answered [ref, 2026-11-27]:** the opt-in local data stream is real. §3 (*The game's
     telemetry stream*) has what it is, how it is switched on, what it gives and why the first
     version leaves it alone. Still open: any word from the publisher on whether outside programs
     may use it, and whether it survives into the next release.
4. **Answered [seen 2026-11-27].** The game empties `Game.log` in place at launch: the same file
   id before and after a launch, and a creation time that has not changed since February (§8).
5. **Answered in part [seen 2026-11-27].** Contract and objective notices and `<EndMission>` are
   in the user's logs (§3). Nothing marks a refinery order being placed: `OnRefineryRequest`
   appears once in the 65 November logs (the day raw ore was sold at a refinery kiosk) against 58
   completion notices. Still open: what a failed contract logs.
6. **Answered [seen in the game's files, 2026-11-27].** The location codes are not in
   `global.ini`; they come from the solar system's object containers and the star-map records
   (§3, *Where the location codes come from*). `S1` to `S4` and `HUR` / `CRU` / `ARC` / `MIC` are
   the four Stanton planets, as two other tools' tables also have it.
7. Whether below-normal priority has any drawback for a process that wakes once a second. One
   effect is known: the browser window the service starts inherits it (§6) **[seen
   2026-11-27]**.
8. **Answered [seen 2026-11-27, game running].** `os.stat` reports the live log's true size; a
   directory listing lags (§8).
9. Whether opening the window takes focus from the game, and whether a second window can appear
   after a mid-session restart (§11). One test without the game was clean.
10. For the Claude terminal (stage 4b), all **[verify]**: that Claude Code's interface runs
    correctly under a pseudo-console created through `ctypes` by a windowless (`pythonw`) parent;
    that it is usable at the below-normal priority it would inherit from the service (§6), or
    whether it should be started at normal priority; where the winget package really puts the
    program and whether the service, started by Task Scheduler, sees it on PATH (§8 has what is
    known second-hand); which xterm.js release to pin; and what a
    fresh Claude Code process really costs in memory. The open question in point 3 matters more
    now: the user will switch away from the game on purpose, so test on the ground whether the
    game still takes stick and throttle input while the dashboard has the keyboard.

## 15. The user's decisions

Use the default unless they say otherwise, and tell them what was chosen.

| Decision | Default |
| --- | --- |
| Start at logon | Yes: they asked for a service |
| Open the window when the game starts | Yes |
| Close the window a few minutes after the game exits | Yes, to give memory back |
| Which monitor | The one that is not the primary |
| Port | 47826 |
| Commit the generic reference data | Yes |
| Keyboard hotkeys for views | Not in the first version |
| Where the browser profile lives | `%LOCALAPPDATA%\scdash\browser`, outside the repo and the game folder (§10) |

**Decided by the user on 2026-11-27**, after the review and the survey of community tools:

| Decision | Their answer | What was turned down |
| --- | --- | --- |
| Build this, or adopt a community tool (§3) | **Build it**, reusing CSR's code for the log state and the telemetry reader (§5). | QuantumWake, the nearest existing tool, with Claude pushing the plan into it. |
| What draws the display | **The web page**, in an Edge app window: about 108 MB in 11 processes (§9). | A native window drawn with Python's `tkinter`: about 12 MB, no web server, plainer. |
| Contract tracking | **In the first version:** the active contract and its current objective on the Now view (§4). | Leaving it for later. |
| The game's telemetry stream (§3) | **Supported**, as stage 6 (§12), with 5.0 close. | Leaving it out. |
| How the telemetry reader learns the stream's layout | **Read it from the installed game's program file**, read-only, at start: "most reliable", in their words. It follows a patch by itself. | Field numbers written into the code by hand. |
| Community tools in general | **No precompiled binaries.** A community tool has to be open source and built or run from source here; otherwise we build our own. Now a standing rule in [`../STARCITIZEN.md`](../STARCITIZEN.md). | - |
| Which way up the side monitor stands | **Either: landscape or portrait, "depending on my mood".** The page has a layout for each and picks by the shape of its window (§11). | A page designed for landscape only, which is what this plan said before. |

**Decided by the user on 2026-11-27, at the start of the build session:**

| Decision | Their answer | What was turned down |
| --- | --- | --- |
| Registering the logon task (§6) | **Claude registers it** once that stage is built and tested, tells the user, and shows them `uninstall`. | The user running `install` themselves; no autostart at all. |
| How the telemetry stream is switched on (§3) | **The launcher variable, permanently:** a per-user Windows environment variable, `GRPC_CLIENT_SERVER_ENABLED=true` (`setx`). No game file is touched. It takes effect the next time the RSI Launcher is started. Set it when the reader exists (stage 6) and tell the user when it is done. | The variable for one session only (the recommendation); a line in the game's `user.cfg`; leaving the stream off until 5.0. |

| Claude inside the dashboard (§4) | **A real terminal in the page**, running Claude Code and nothing else, started by the dashboard. | A question box that can only read; a separate Windows Terminal window placed beside the dashboard. |
| When that Claude starts | **With the dashboard window**, so it is always ready. It holds about 200 MB for the whole play session. | Starting it the first time the user switches to the window (the recommendation, to save the memory in sessions where nothing is asked). |
| How xterm.js comes into the repo (§5) | **The pinned published release file**, with its license and a recorded checksum. | Installing Node.js and building it from source here. |
| Which activities get a view (§4) | **Mining, salvage, combat and cargo hauling**: "the other stuff like salvaging and combat and cargo hauling etc". Medical runs and crafting stay on the Now view until asked for (Claude's reading of "etc"). | Mining only, which is what this plan had. |
| How the page looks (§11) | **"Good and modern": direction B, "Avionics",** picked on 2026-11-27 from three directions mocked up in every screen and both orientations. | A, "Cluster" (calm, typographic, light figures) and C, "Signal" (bold, color-blocked, very large numerals). |
| What the dashboard's Claude knows when it starts | **`STARCITIZEN.md`, loaded by the dashboard**, so nothing is typed before the question. (Loading it without setting off a ramp-up is Claude's design, §4.) | - |

What "permanent" means, so nobody is surprised later: while the game runs, any program on this PC
can read the stream, not only the dashboard. To undo it, delete the variable
(`reg delete HKCU\Environment /v GRPC_CLIENT_SERVER_ENABLED`) and restart the launcher.

## 16. When it ships

- `dashboard/README.md` for people and `dashboard/CLAUDE.md` for Claude, following the docs
  convention in [`../CLAUDE.md`](../CLAUDE.md). Replace the stubs that sit there now.
- **A "set up on a fresh Windows install" section in `dashboard/README.md`,** complete enough to
  follow with nothing else open. The user's system-refresh kit restores the project folder and
  the tools (Python, Git, Edge, Claude Code) and then only points at this README, so everything
  the dashboard changes outside the repo has to be listed there, in order, each step safe to
  repeat: `python dashboard\scdash.py install` for the logon task, the
  `GRPC_CLIENT_SERVER_ENABLED` variable for telemetry, Claude Code's install command and its
  one-time sign-in, and how to check each one took (`status`). Keep the list true as stages add
  to it. Where a step fetches the repo, it uses `gh repo clone` or the HTTPS address, never an
  SSH one: since 2026-11-27 this PC reaches GitHub only over HTTPS, signed in through the GitHub
  CLI (`gh auth login`, once after a reinstall), and holds no SSH key (the user's instruction).
- [`../CLAUDE.md`](../CLAUDE.md): the folder layout, and a short pointer to this folder.
- `dashboard/THIRD_PARTY_NOTICES`: CSR's copyright line and license text, if its code was used
  (§5), and a pointer to it from `dashboard/README.md`.
- `../README.md`: one line that the repo also holds the dashboard.
- [`../STARCITIZEN.md`](../STARCITIZEN.md): a row in "Where things live", and in "Check the logs"
  that `timeline` and the session records exist and that `plan.json` is updated together with the
  game plan page.
- Memory: the update routine in `game-plan-artifact` gains the `plan.json` step, and
  `sc-dashboard-project` records what was built and measured.
- Turn this file into a short record of what was decided and why, or delete it once
  `dashboard/CLAUDE.md` covers it.

## 17. Out of scope

- Anything that reads or writes the game's memory, draws over the game, or sends it input.
- Reading the screen (OCR) to recover what the log leaves out.
- Anything served beyond this PC, or any account or online feature. (Claude Code in the terminal
  panel talks to Anthropic as it always does; that is the user's own program, not the dashboard.)
- Usage reporting of any kind: the dashboard sends nothing about itself or the user anywhere.
  (Reading the *game's* telemetry stream is in scope: §3, stage 6.)
- A general shell in the page. The terminal panel runs Claude Code and nothing else (§8).
