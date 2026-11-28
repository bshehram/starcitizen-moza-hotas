# What each activity leaves in the log

*A survey for the dashboard's stage 3 views ([`PLAN.md`](PLAN.md) §12), rebuilt on 2026-11-27
after a Windows reinstall. It is a research record, kept in git so it cannot be lost the way the
logs were. `activity_survey.md` and `scripts/scan2.py`, which it corrects, are the first, partial
survey in the git-ignored `data/handoff/`.*

What salvage, hauling, ship combat, on-foot combat and missions leave in `Game.log`. The user's
409 old logs did not survive the reinstall, so nothing here is newly read from them. As new
sessions settle an item, change its mark here and move the fact into `PLAN.md` §3. Every item
says how it is known:

- **[seen]**: in the project's own record of the user's logs (`dashboard/PLAN.md` §3,
  `dashboard/CLAUDE.md` "What the logs showed", `activity_survey.md`) or in the sanitized samples
  `dashboard/tests/samples/*.log` (file:line given).
- **[game]**: in the installed build's files, 4.10.201.48085 (Alpha 4.10.3): a `global.ini` key, or a
  `Game2.dcb` record or enum. For a notice text this means **"text exists, not seen in a log"**.
- **[ref: tool, file:line, version]**: another tool's parser or notes. Clones read, never run:
  - CSR `archelium/csr` at `ba6dad0` (2026-11-26). README says tested 4.1 to 4.10.3.
  - QuantumWake `peans99/QuantumWake` at `19e2c47` (2026-11-24). Its docs were measured on
    4.9.188 and 4.10.2.
  - star-citizen-live `Neorion/star-citizen-live`: master `5f739b5` (2026-09-07), plus branches
    `feat/cargo-log-board` `156c63a`, `feature/cargo-router` `9f3fd51` and
    `feature/insurance-claims`. Its comments say 4.7 to 4.8.0, a few say 4.9.0.
  - SC-Game-log-Parser `CasualAlacrity/SC-Game-log-Parser` at `f5e0609` (2026-11-05). Its samples
    are from 4.10.197.
  - sc-log-tracker `DefaultHahn/sc-log-tracker` at `d6865cb` (2026-10-05). README says tested
    4.3 to 4.10, and the changelog says it recognizes "all HUD notifications seen in 4.10".
- **[mine]**: my own reading, not a fact from any source.

Line shapes below use invented names and ids (`Pilot_Example`, `OtherPilot_1`, `9000...`,
`e0000001-...`). A notice is always the first form only: `<time> [Notice] <SHUDEvent_OnNotification>
Added notification "<text>: " [<n>] to queue. ..., MissionId: [<guid>], ObjectiveId: [<id>]`.

---

## 0. What contradicts or sharpens the earlier notes

1. **`activity_survey.md`'s ship-destroyed row has the old shape.** It reads "destroy level from
   '<a>' to '<b>' ... caused by ... damage type". That is the pre-4.4 `<Vehicle Destruction>
   CVehicle::OnAdvanceDestroyLevel` line [ref: CSR sc_stats.py:2242-2245, legacy;
   QuantumWake docs/log-format-reference.md:53-69]. The 4.10.3 line is `<Vehicle Destroyed> ...
   destroyed: reason [..] level [a] -> [b] ... killer '..' [id]` [seen: markers.log:36,
   courier.log:283]. The `VDEST` regex in `scripts/scan2.py` is written for the old shape and
   would match no 4.10.3 line. So the "killer is the user" count it was computing would have come
   out empty. `events.py` already has the right shape.
2. **`activity_survey.md` says both commodity lines print the unit `cSCU`.** The sanitized sell
   line does not: `quantity[9] transactionMode[ResourceContainer]` [seen: markers.log:73-74],
   while the buy line does: `quantity[3200.000000 cSCU]` [seen: markers.log:71]. SC-Game-log-Parser
   reads the buy quantity as centi-SCU and the sell quantity as SCU
   [ref: SC-Game-log-Parser docs/event-reference.md:85-86, 4.10.197]. PLAN §3's trap list holds.
3. **`Contract Failed:` is real, not just unseen.** The text exists as
   `mobiGlas_ui_MissionEvent_Fail=Contract Failed: %s` [game]. Across QuantumWake's backups there
   were 40 such notices [ref: QuantumWake src/Quantumwake.Data/MissionWatch.cs:11-15, 4.9-4.10.2].
   Three other tools parse it. The user simply had no failed contract in November.
4. **The generator name is a record name, not always `<giver>_<kind>`.** The marker's
   `generator name [X]` is the short name of a `ContractGenerator` record in `Game2.dcb`
   (`ContractGenerator.FTL_Courier`, `ContractGenerator.CitizensForProsperity_Mercenary_FPS`) [game,
   matched against seen]. Twelve generators are a giver's catch-all with mixed kinds:
   `CitizensForProsperity_Generator`, for example, holds hauling, on-foot salvage and comms-tower
   contracts. So the kind has to come from the `contract [...]` name, and the generator only
   narrows it (section 7).
5. **The marker's contract name can carry a sub-contract index.** The sample logs
   `contract [FTL_Courier_Stanton_Iron_Rank0_2]` [seen: menu_return.log:145].
   `Game2.dcb` has `FTL_Courier_Stanton_Iron_Rank0` with 3 `subContracts` [game]. QuantumWake writes
   "A sub-contract is logged under its parent's name plus its index"
   [ref: QuantumWake docs/missions.md:28, 4.10.2]. CSR strips it with
   `contract \[([A-Za-z][A-Za-z0-9_]+?)(?:_\d+)?\]` [ref: CSR sc_stats.py:2211]. The contract-kinds
   table should strip a trailing `_<digits>` before its lookup.
6. **The notice "hint" rule would swallow some of the new notices.** `events.py` marks a notice
   without a kind of its own as a tutorial tip when the text after its first `": "` is longer than
   40 characters, and `state.py:1033-1036` then drops it from the feed. `Contract Failed: Claim
   #4521: Drake Cutlass Black Salvage Rights` and `Objective Failed: Deliver 0/24 SCU of Agricium to
   MIC-L1 Shallow Frontier Station` would both vanish today. Every new kind below has to be an
   entry in `NOTICE_KINDS`, which is matched before the catch-all.
7. **`state.py` would show a failure as "Contract fail".** `END_STATUS` (state.py:43) maps only
   `complete` and `abandon`. The other `CompletionType` values are `Fail` and `Deactivate`
   (section 1), and fall through as the raw word.
8. **Hauling SCU per stop is only partly in the log.** PLAN §4 wants "a checklist of pickups and
   drop-offs with the SCU at each stop". Drop-offs get a notice with commodity, place and SCU, but
   only on about half the hauls. Hauling pickups get no notice at all; courier pickups do
   (section 2).

---

## 1. Missions in general

Notice templates [game], all in `global.ini` (two spaces after "Accepted:" and "Withdrawn:"):

| Notice | Key |
| --- | --- |
| `Contract Accepted:  %s` | `mobiGlas_ui_MissionEvent_Activated` |
| `Contract Available: %s` | `mobiGlas_ui_MissionEvent_Available` |
| `Contract Complete: %s` | `mobiGlas_ui_MissionEvent_Complete` |
| `Contract Withdrawn:  %s` | `mobiGlas_ui_MissionEvent_Deactivate` |
| `Contract Failed: %s` | `mobiGlas_ui_MissionEvent_Fail` |
| `Contract Shared: %s` | `mobiGlas_ui_Mission_Shared` |
| `Reward Updated: %s` | `mobiGlas_ui_MissionRewardUpdated` |
| `New Objective: %s` | `mobiGlas_ui_ObjectiveEvent_Activated` |
| `Objective Complete: %s` | `mobiGlas_ui_ObjectiveEvent_Complete` |
| `Objective Withdrawn: %s` | `mobiGlas_ui_ObjectiveEvent_Deactivated` |
| `Objective Failed: %s` | `mobiGlas_ui_ObjectiveEvent_Fail` |
| `Journal Entry Added` (+ `: <title>`) | `mobiGlas_ui_JournalEntry_Added` |

Enums [game]: `EMissionResult` = Completed, InProgress, Failed, Abandoned, Withdrawn;
`ContractEndCommsReason` = Complete, Fail, Abandon; `EMissionPhaseStates` = NotStarted, Active,
Completed, Failed, Abandoned.

| What | Line shape | How known | events.py today | Recommendation |
| --- | --- | --- | --- | --- |
| Contract accepted | `"Contract Accepted:  ENTRY LVL. COURIER NEEDED IN STANTON: "`, `MissionId: [e0000001-...]` | [seen] 39 notices; courier.log:57 | `contract_accepted` | Nothing to add |
| Contract complete | `"Contract Complete: <title>: "` | [seen] 13 | `contract_complete` | Nothing |
| Contract failed | `"Contract Failed: <title>: "`, real MissionId | [game] key above; [ref: QuantumWake MissionWatch.cs:11-15, 40 notices, 4.9-4.10.2]; [ref: CSR sc_livelog.py:17]; [ref: sc-log-tracker sc_log_tracker.py:656-669, 4.10]; not seen | generic `notice` (dropped if the title is over 40 chars) | **Add now** `contract_failed`, built sample marked unverified; map `fail` to "failed" in `END_STATUS` |
| Contract withdrawn | `"Contract Withdrawn:  <title>: "` | [game]; [ref: sc-log-tracker sc_log_tracker.py:685-687, 4.10]; not seen | generic `notice` | **Add now** `contract_withdrawn` with the failed one, unverified |
| Contract available (offer) | `"Contract Available: <title>: "` | [game]; [ref: sc-log-tracker sc_log_tracker.py:670-671] | generic `notice` | Nothing: an offer, not a contract the user holds |
| Contract shared with you | `"Contract Shared: <title>: "`; the title keeps `~mission(...)` placeholders [ref: CSR sc_livelog.py:122-125, 368-369]. Twin: `<MissionShared> Received share push message: ownerId[900000000009] - missionId[e0000001-...]` | [game] key; [ref: SC-Game-log-Parser docs/event-reference.md:258-262, parser.py:65, 4.10.197] | generic `notice`; the push line is not read | Nothing: the user plays solo |
| Reward updated | `"Reward Updated: <...>: "` | [game] only; no tool parses it | generic `notice` | Wait for a real log |
| New objective / objective complete | `"New Objective: Deliver Food Supplies To Storehouse: "`, `ObjectiveId: [dropoff_e0000003-..._0]` | [seen] 85 / 33; courier.log:59-61 | `objective_new` / `objective_complete` | Nothing (hauling and courier parsing in section 2) |
| Objective failed | `"Objective Failed: <text>: "` | [game]; [ref: QuantumWake MissionWatch.cs:13, 7 notices]; [ref: CSR sc_livelog.py:53] | generic `notice` | **Add now** `objective_failed`, unverified. It is not the contract's end: a patrol's optional objective can fail and the contract still completes [ref: QuantumWake src/Quantumwake.Core/State/SessionBuilder.cs:1049-1054] |
| Objective withdrawn | `"Objective Withdrawn: <text>: "` | [game]; [ref: QuantumWake docs/screen-insight.md:625-627, 100 notices] | generic `notice` | **Add now** `objective_withdrawn` |
| Contract ended | `<EndMission> Ending mission for player. MissionId[e0000001-...] Player[Pilot_Example] PlayerId[900000000002] CompletionType[Complete] Reason[Mission Ended]` | [seen] 20 (Complete 13, Abandon 7) | `mission_ended` | Nothing in the parser; `END_STATUS` needs `fail` and `deactivate` |
| `CompletionType` values | `Complete`, `Abandon` [seen]; `Fail` [ref: QuantumWake docs/delivery-run.md:106-108, Complete/Fail/Abandon 313/16/76]; `Deactivate` [ref: star-citizen-live feature/cargo-router DESIGN-mission-dashboard.md:28-35, Complete 1043, Abandon 292, Fail 98, Deactivate 20, 4.7-4.8.0] | as left | as left | `Deactivate` reads as "withdrawn" (star-citizen-live calls it "mission pulled/expired") |
| `Reason` values | `Mission Ended` on Complete, `Player left` on Abandon [seen]. `Mission Ended` on Abandon [ref: sc-log-tracker tests/test_parser.py:205]. `Mission timer expired` on Fail [ref: star-citizen-live test/fixtures/sample-missions.log:11, a fixture, 4.8.0]. `Player left` on Deactivate [ref: QuantumWake tests/Quantumwake.Tests/MissionEndingParserTests.cs:108]. Not in `global.ini` [game], so they are code strings, not text. A hauling deadline's own end reason is `@HaulCargo_Fail_TimeOut` = "Delivery Window Expired" on 258 templates [game]; whether `Reason[...]` prints it is unknown | as left | `reason` kept | Show the reason as logged |
| Second end signal | `<MissionEnded> Received MissionEnded push message for: mission_id e0000001-... - mission_state MISSION_STATE_COMPLETED` (also `_FAILED`, `_WITHDRAWN`) | [ref: QuantumWake src/Quantumwake.Core/Events/CommerceEvents.cs:178-182 and Parsing/LogEventParser.cs:252-258, 4.9-4.10.2: agrees with EndMission on 230 of 230 completions, and alone covers 50 completions with no journal objectives]; [ref: star-citizen-live DESIGN-mission-dashboard.md:23, 37: also `EXPIRED`, `ENDED`]; not in the project's record | not read | Wait: check whether 4.10.3 writes it, then add as a fallback end |
| Objective state push | `<ObjectiveUpserted> Received ObjectiveUpserted push message for: mission_id e0000001-... - objective_id dropoff_e0000003-..._0 - state MISSION_OBJECTIVE_STATE_COMPLETED - created 0 - flags=ShowInLog\|` (also `INPROGRESS`, `WITHDRAWN`) | [ref: QuantumWake docs/untapped-signals.md:44-57, 4.9]; [ref: star-citizen-live feat/cargo-log-board functions/parser.js:241, 4.9.0] | not read | Wait |
| Mission start | `<CSCPlayerMissionLog::MissionStartCommsNotification> MissionStart comms notification will not be sent - ... ContractId: [e0000004-...]. MissionId: e0000001-...` | [ref: star-citizen-live app/parser.js:78, 4.8.0] | not read | Nothing: the accept notice and the marker cover it |
| Which contract it is | `<CLocalMissionPhaseMarker::CreateMarker> Creating objective marker: missionId [e0000001-...], generator name [FTL_Courier], contract [FTL_Courier_Stanton_Iron_Rank0_2], contractDefinitionId[e0000002-...], objectiveId [pickup_e0000003-..._0], ...` | [seen] 110; courier.log:55, menu_return.log:145 | `mission_marker` | Nothing; strip the `_<n>` suffix in the kinds lookup (section 0.5). `contractDefinitionId` is the contract's inline id in `Game2.dcb`, not a record id [ref: QuantumWake docs/missions.md:17-31] |
| Objective HUD text | `<CMissionLogEntry::UpdateActiveObjective> Objective updated id=e0000001-..., flags=MarkerHidden\|ShowInLog\|ShowProgress\|, ..., uiDisplay[Priority=1][Text=Hostiles Remaining]` | [seen: records.log:23]; [ref: QuantumWake docs/hauling.md:53-59: 4,867 lines, all templates or combat lines, never a hauling step]; [ref: star-citizen-live app/parser.js:92] | not read | Nothing: no mission id, no numbers |
| Another player on your mission | `<PlayerJoined> Received PlayerJoined push message for: mission_id e0000001-... - player_id 900000000099` | [ref: star-citizen-live app/parser.js:140, 4.7] | not read | Nothing (solo) |
| Item rewards | `"You've Earned: 3 Rewards` / `Access Them at Your Primary Residence's Inventory: "` (two lines) | [game] `Mission_MultiReward_Notification`, `Mission_Reward_Notification`; [ref: CSR sc_stats.py:3808, 4503]; [ref: sc-log-tracker sc_log_tracker.py:691-693] | generic `notice` | Wait; at most a minor line |
| Journal entry | `"Journal Entry Added: <title>: "`, e.g. a license or "Criminal Record" | [game] key, and 96 `ReputationJournal` title keys such as `BHG_ReputationJournal_Easy_ShortTitle` "Tracker Beginner's Permit Earned (LRT)"; [ref: sc-log-tracker sc_log_tracker.py:711-713]; [ref: CSR sc_livelog.py:18] | generic `notice` | Wait. [mine] Rank promotions probably show here, by title only |

---

## 2. Hauling (and courier)

| What | Line shape | How known | events.py today | Recommendation |
| --- | --- | --- | --- | --- |
| Hauling contract accepted | `"Contract Accepted:  Junior Rank - Direct Small Cargo Haul: "` | Title templates [game]: `Covalex_HaulCargo_AToB_title` "~mission(ReputationRank) Rank - Direct ~mission(CargoGradeToken) Cargo Haul", `RedWind_HaulCargo_AToB_title_01` "... Hauler Needed for Direct ... Shipment", `LingFamily_HaulCargo_AToB_title`. A vanilla title names no place [ref: QuantumWake docs/hauling.md:26-35, 4.9] | `contract_accepted` | Nothing; the kind comes from the marker |
| Drop-off manifest | `"New Objective: Deliver 0/177 SCU of Potassium to Ruin Station above Pyro VI: "`, `ObjectiveId: [dropoff_e0000003-..._0]`. Some read `Deliver 0/12 Cargo Boxes to <place>` | [game] `HaulCargo_obj_itemspecifics_01` "Deliver ~mission(amount)/~mission(total) SCU of ~mission(item) to ~mission(Destination\|ListAll)" ([mine] the logged text has no closing period, so this key rather than `hauling_deliver_resource_objective`), and `hauling_deliver_boxes_objective`. [ref: CSR sc_stats.py:2169-2170, 4.5+]. [ref: QuantumWake docs/delivery-run.md:57-81: on 106 of 205 hauls only, the first number almost always 0, drop indices `_0` to `_5`]. [ref: SC-Game-log-Parser docs/event-reference.md:246-250, 4.10.197]. [ref: star-citizen-live feat/cargo-log-board functions/parser.js:124, 4.8.0]. The project's record shows no hauling contract (courier only) | `objective_new`, raw text | **Add now in the state**, no new line kind: read amount, total, unit (SCU or boxes), commodity and place from `objective_new`, and the drop index from the objective id. Built sample marked unverified |
| Hauling pickup | none: "No haul gets a pickup toast" | [ref: QuantumWake docs/delivery-run.md:83-89] | n/a | Nothing; the Cargo view shows pickups as unknown, or takes them from the plan |
| Courier pickup and drop-off | `"New Objective: Collect Data Probe From HUR-L1 Green Glade Station: "` (`ObjectiveId: [pickup_..._0]`) and `"New Objective: Deliver Data Probe To HUR-L3 Thundering Express Station: "` (`[dropoff_..._0]`); then `"Objective Complete: Collect Data Probe From ...` / `: "` over two lines | [seen: courier.log:119-121, 142-143]; [game] `delivery_pickup_short` "Collect ~mission(item) From ~mission(Location)", `delivery_dropoff_short` "Deliver ~mission(item) To ~mission(Destination\|Target\|Address)" | `objective_new` / `objective_complete` | **Add now in the state** from the seen samples: item and place from the text, pickup or drop-off from the id prefix |
| Drop-off station by objective id | `<CreateHaulingObjectiveHandler> Dropoff created - [Cient] sourcename: X, missionId: 00000000-..., locationName: HUR-L2 Faithful Dream Station [Stanton_1_...], locationHash: 1615454559, objectiveId: dropoff_e0000003-..._0_0` | [ref: star-citizen-live feature/cargo-router services/CargoRouter.js:96 and test/cargo.test.js:14 (a 2025-08 fixture), 4.7-4.8.0] | not read | Wait |
| Per-drop done | `Objective Complete:` for the drop, or an `ObjectiveUpserted ... COMPLETED` (section 1) | [ref: QuantumWake docs/delivery-run.md:91-98: only 36 of 101 completed hauls had a per-drop completion] | `objective_complete` | Nothing; a single-drop contract that completes has delivered |
| Freight elevator sent | `<CEntityComponentFreightElevatorUIProvider::FillUnstowRequest> [FreightElevatorKioskUIProvider] FreightElevatorKiosk_FreightElevator_Util_HangarLarge[900000000015] - Processed bindings into transfer request - Entities: 4, Location: 1510935576 - RequestId: 4, ItemBank: 0` | [ref: SC-Game-log-Parser docs/event-reference.md:228-232, parser.py:75, 4.10.197]; [ref: QuantumWake docs/untapped-signals.md:136-150, 4.9: an entity count and a location id, no commodity or SCU] | not read | Wait; at most "elevator used, N items" |
| Storage grid count | `Freight Inventory Grid InventoryDataRequest Successful ... Item Count:[156]` | [seen]: follows the screen's filter, not the cargo | `storage_count` | Nothing |
| Trade-run purchase | `SendCommodityBuyRequest ... price[25025.000000] shopPricePerCentiSCU[7.820000] resourceGUID[...] autoLoading[1] quantity[3200.000000 cSCU] Cargo Box Data: boxSize[8.000000] \| unitAmount[4]` | [seen: markers.log:71] | `commodity_buy` | Nothing; `autoLoading[1]` (the terminal loads the ship) could be kept |
| Kiosk ship picked | `<CEntityComponentCommodityUIProvider::LoadSelectedShipBindings> Sending VehicleCargoDataRequest for vehicleEntityId[900000000021]` | [ref: SC-Game-log-Parser docs/event-reference.md:162-166] | not read | Nothing |
| Commodity transaction refused | `[Error] <CEntityComponentCommodityUIProvider::RmToken_CommodityTransactionResponse> Commodity Transaction Response Error - result[AutoLoadStartFailed] type[Buying]` | [ref: SC-Game-log-Parser docs/event-reference.md:180-184]; it names no request, so it cannot be matched to one | not read | Wait |
| Cargo deck transfer | `"Cargo Transfer Complete: "`, `Cargo Transfer Interrupted: Loading Area Obstruction`, `Assigned Loading Area Revoked: Failure to Report`, `Cargo Repossessed: Failure to Collect` | [game] `cargo_notify_*` keys, text exists, not seen; no tool reads them. The matching tutorial tips name the Hull series (`Hints_Cargo_*`) | generic `notice` | Wait |
| Hauling pay | `"Awarded 50250 aUEC: "` | [game] `text_UEC_reward_text` "Awarded %i aUEC"; [ref: QuantumWake docs/missions.md:207-215 and docs/delivery-run.md:118-120, 4.10.2: 14 in 282 logs, all Covalex legacy hauls; 12 equal the record's reward] | generic `notice` | **Add now** `reward` (amount), unverified; most contracts will not log it |

Hauling generators: `Covalex_Hauling`, `RedWind_Hauling`, `LingFamilyHauling_Hauling`,
`LingFamilyHauling_Delivery`, `DeadSaints_Hauling`. Hauling handlers also sit inside
`CitizensForProsperity_Generator` (`CFP_Hauling`), `HeadHunters_Generator` (`HH_Hauling`),
`FoxwellEnforcement_Generator` (`FoxwellEnforcement_Hauling`) and the events `CleanAir`,
`VisitingIasi` and `TheBackpocket` [game]. Contract names start `HaulCargo_` or end `_Hauling`
[game], for example `HaulCargo_AToB_Stanton1_Intro` or `CFP_Pyro_Intro_Hauling`. The
`*_RecoverCargo` generators are combat contracts that end in a haul (section 7).

---

## 3. Salvage

| What | Line shape | How known | events.py today | Recommendation |
| --- | --- | --- | --- | --- |
| Amount scraped, RMC made, hold filling | none | [ref: QuantumWake docs/salvage.md:30-33 and docs/untapped-signals.md:258-261, 4.9: the only salvage lines are `SetSalvageRepairAmmoCount_NoTarget` warnings and damage-map paths]; [game] the `salvage_HUD_*` strings are HUD labels | n/a | Nothing |
| Salvage contract objectives | `"New Objective: Locate Salvage Claim #4521: "`, `Salvage the Drake Cutlass Black`, `Salvage Scrap at <place>`; progress labels `Remaining Salvage`, `Remaining Hull` | [game] `LocateSalvage_obj_short_01`, `LocateSalvage_obj_short_02`, `BasicSalvage_subobj_short_01b`, `FPSSalvage_obj_short_01`, `SalvageContractor_obj_progress_short(_2)`: text exists, not seen | `objective_new` | Nothing new; the Salvage view shows the objective |
| Salvage contract titles | `"Contract Accepted:  Claim #4521: Drake Cutlass Black Salvage Rights: "`; `Salvager Needed (Small Supply of RMC)` | [game] `Adagio_BasicSalvage_Title_01`, `Adagio_Industrial_Salvage_Universal_E_Title_001` | `contract_accepted` | Nothing |
| RMC or construction materials sold | `SendCommoditySellRequest ... shopName[...] amount[<aUEC>] resourceGUID[a0e6c4cf-face-4f52-a020-dfa869607901] ... quantity[<n>] transactionMode[ResourceContainer]` | The line shape is [seen] (markers.log:73), RMC itself was never seen sold. The ids [game] from `reference/resources.json`: RMC `a0e6c4cf-...`, Construction Materials `98aa6a70-...`, Construction Pieces `0de337b5-...`, Rubble `344b54b4-...`, Salvage `ebacf963-...`, Scrap `dae3efcb-...` | `commodity_sell` | Nothing new; name it through `resources.json` |
| Salvage wrecks removed | `<Vehicle Destroyed> Vehicle 'AEGS_Sabre_Unmanned_Salvage_900000000011' [900000000011] class 'AEGS_Sabre_Unmanned_Salvage' (owner player [0], driver [0]) destroyed: reason [GameRules] level [0] -> [2] flags [2030] killer 'OtherPilot_1' [900000000012] authority [0]` | [seen: markers.log:36, menu_return.log:133], killer another player both times | `vehicle_destroyed` | Nothing. [mine] Mission wrecks being cleaned up; leave them out of the kill tally |
| Multi-tool salvage tip | `"Salvage - Hull Scraping: The Salvage Beam strips vehicle hulls into Recycled Material Composite (RMC). ..."` | [seen: menu_return.log:72]; [game] `Hints_SalvageBeam_HullOverview_Title`, a hand-tool tip | `notice`, dropped as a hint | Nothing |

Salvage generators [game]: `Adagio_Generator` (salvage claims), `Adagio_ResourceGathering_ShipSalvage`
(mostly type Collection: deliver RMC), `Adagio_ResourceGathering_FPSSalvage`, `RR_Salvage`.
Salvage handlers also sit inside `CitizensForProsperity_Generator` (`CFP_FPSSalvage`),
`HeadHunters_Generator` (`HH_FPSSalvage`), `TarPits_Generator`, `Clovus_Generator`,
`Unaffiliated_Generator`, `Battaglia_Generator` and `VisitingIasi`. Contract names contain
`Salvage`, for example `Adaigo_Stanton1_Lawful_Salvage_Easy` (the game's own spelling) or
`Adagio_RG_ShipSalvage_Stanton_Rank0_RMCSmall`.

---

## 4. Ship combat

| What | Line shape | How known | events.py today | Recommendation |
| --- | --- | --- | --- | --- |
| Ship destroyed or crippled | `<Vehicle Destroyed> Vehicle 'ORIG_m80_900000000031' [900000000031] class 'ORIG_m80' (owner player [900000000003], driver [0]) destroyed: reason [SelfDestruct] level [0] -> [2] flags [2022] killer 'Pilot_Example' [900000000003] authority [0]` | [seen: courier.log:283, markers.log:36]; [ref: CSR sc_stats.py:2246-2250, "4.10.3+: one line per vehicle damage-state change"; CHANGELOG.md:288-293] | `vehicle_destroyed` (driver id not kept) | See the next rows |
| Its fields | vehicle id; class; `owner player` (0 for an NPC ship [seen]); `driver` (0 when empty [seen]); `reason`; `level [from] -> [to]`; `flags`; `killer` name and id; `authority` | [seen]. Level 1 = crippled (soft death), 2 = destroyed [ref: CSR sc_stats.py:4128-4137]. Reasons seen: `SelfDestruct`, `GameRules` [seen]. CSR splits combat, collision and self-destruct [ref: CSR CHANGELOG.md:288-293]; the exact word for a gun kill is not in any source read | as left | Keep `driver` too |
| The user's kill | the killer's id equals the user's player id, which is the `geid` on the `<AccountLoginCharacterStatus_Character>` line, and the owner is not the user | Both ids come from the same series [seen: courier.log:12 geid and courier.log:283, the user's own self-destruct]. The kill side has not been seen; CSR's rule is the same [ref: CSR sc_stats.py:4106-4139: one event per vehicle, the line with the highest level; a victim counts only if its class starts with a maker code, because the line also fires for things like `Orbital_Sentry_SecurityNetwork`] | `vehicle_destroyed` + `character` | **Add now in the state**: per session, ships the user destroyed or crippled and ships lost. Never trust the killer on a `SelfDestruct`: it can be another player's name [seen, dashboard/CLAUDE.md]. Kill side unverified |
| The user's loss | owner id equals the user's player id, level reaches 2 | [seen: courier.log:283] | as above | Same |
| CrimeStat up | `"CrimeStat Rating Increased: "` | [game] `text_hostility_Wanted`; [ref: CSR sc_stats.py:4541]; [ref: sc-log-tracker sc_log_tracker.py:792-794]; [ref: star-citizen-live feat/cargo-log-board functions/parser.js:162, about 409 lines in Jul 2026] (it also matches "Decreased", which has no text in `global.ini` [game]) | generic `notice` | **Add now** `crime` (alert), unverified |
| Crime committed | `"Crime Committed: Assault` / `against OtherPilot_1: "` (the victim part is on a second line) | [game] `hud_law_CrimeCommitted`, `hud_law_CrimeCommitted_VictimName`; [ref: sc-log-tracker sc_log_tracker.py:795-798] | generic `notice` | **Add now** with the one above |
| A crime against the user | `"OtherPilot_1 committed Assault against you: "` | [game] `hud_law_charge_player_crime`; [ref: sc-log-tracker sc_log_tracker.py:799-801] | generic `notice` | **Add now** as an alert: a fight with a player has started. The name must join the session's other-player names so the scrubber replaces it |
| Fined | `"Fined 1500 UEC: "` | [game] `hud_law_FinePaid` "Fined %i UEC"; [ref: sc-log-tracker sc_log_tracker.py:802-805] | generic `notice` | **Add now** `fine` (amount) |
| Ship impounded | `"Vehicle Impounded: Drake Golem: "` | [game] `hud_law_ImpoundingNotification`; [ref: sc-log-tracker sc_log_tracker.py:779-781] | generic `notice` | Add with the law group |
| Monitored space down or restored | `"Monitored Space Down: "` / `"Monitored Space Restored: "` | [game] `hud_monitored_space_disable` / `_enable`; [ref: sc-log-tracker sc_log_tracker.py:738-743] | generic `notice` | **Add now** to `monitored` |
| Hostile territory | `"Entering Hostile Territory - Caution Advised: "`, `"Leaving Hostile Territory: "` | [game] `hud_enter_hostile_territory`, `hud_leave_hostile_territory`; no tool reads them, not seen | generic `notice` | Wait |
| Bounty or kill objectives | `"New Objective: Neutralize <target name>: "`, `Defeat Hostile Ships`, `Waves Destroyed: 2`, `New wave incoming:` | [game] `KillShip_Neutralize_Short_01`, `ShipWaveAttack_obj_short_01`, `KillShip_WaveTracker_Short_01`, `KillShip_NextWave_Short_01`. Objectives update without kill counts [ref: QuantumWake MissionWatch.cs:13-15] | `objective_new` | Nothing new |
| Fatal crash; thrown out of a destroyed ship | as PLAN §3 | [seen] | `fatal_collision`, `thrown_out` | Nothing |
| Insurance claim after a loss | `<CWallet::ProcessClaimToNextStep> New Insurance Claim Request - entitlementURN: urn:sc:global:entitlement:uuid:e0000005-..., requestId : 12` | [ref: star-citizen-live feature/insurance-claims app/parser.js, +20 lines, Aug 2025 to May 2026 corpus: repeats dozens of times per claim and names no ship] | not read | Wait |
| Damage to the user's ship, missile lock or launch, a hostile nearby | none found | [game] `MISSILE INBOUND`, `INBOUND MISSILE`, `SHIELDS DOWN` and `LOCK-ON` are HUD labels (`hud_MissileWarning`, `hud_InboundMissile`, `hud_ShieldsDown`, `hud_Label_LockOn`), not notices. No tool finds such a line. CSR reads missile and hit from the telemetry stream's warning lights [ref: CSR sc_stats.py:10894] | n/a | Nothing from the log; telemetry (stage 6) |

Ship-combat generators [game, 37]: the `*_KillShip` and `*_Mercenary_Ship` ones (bounties:
`BountyHuntersGuild_KIllShip`, the game's spelling; `HeadHunters_Mercenary_Ship`;
`CitizensForProsperity_Mercenary_Ship`; `EckhartSecurity_KillShip`; `InterSec_KillShip`), and the
`*_ShipWaveAttack`, `*_Patrol`, `*_DefendShip`, `*_EscortShips`, `*_Ambush` / `*_ShipAmbush`,
`*_DefendDestructibleEntities` and `*_DefendEntitiesAndEscort` ones. Also `*_DestroyItems`: the
bombing runs are ship work, `HH_Sabotage` may be on foot [mine, from the name]. Also
`Vaughn_Assassination`, `HeadHunters_HijackedShip_Caterpillar`, `InterSec_BoardShip` (boarding, so
on foot inside a ship), `NorthRock_PVP` and `CDF_Generator`.

---

## 5. On-foot combat

| What | Line shape | How known | events.py today | Recommendation |
| --- | --- | --- | --- | --- |
| Downed, emergency services, injury | as PLAN §3 | [seen] | `incapacitated`, `emergency`, `injury` | Nothing |
| Death marker | the first line of the item burst is the body: `<Adding non kept item [CSCActorCorpseUtils::PopulateItemPortForItemRecoveryEntitlement]> Item 'body_01_noMagicPocket_900000000004 - Class(body_01_noMagicPocket) - ...', Recorded data is: Port Name 'Body_ItemPort', ...` | [seen: markers.log:59, courier.log:287]; [ref: star-citizen-live app/parser.js:113-124, 4.7.175 to 4.8.180: "the FIRST line of that burst is ALWAYS the body", and a loot burst from a corpse starts with gear] | `item_lost`, one per item | **Add now in the state**: a death is the `body_01_noMagicPocket` item, not the burst |
| Mission progress label | `uiDisplay[Priority=1][Text=Hostiles Remaining]` | [seen: records.log:23]; [game] `Blood_HostilesRemaining_HUD`, `bounty_fps_boss_obj_HUD` "Hostiles Remaining: " | not read | Nothing: no count, no mission id |
| On-foot objectives | `"New Objective: Neutralize <name>: "`, `Draw out <name> by eliminating enough hostile forces` | [game] `bounty_fps_boss_obj_kill_HUD`, `bounty_fps_boss_obj_long` | `objective_new` | Nothing new |
| Med bed surgery | `<MED BED HEAL> Actor: Pilot_Example ... Perform surgery event Success, med bed name: <bed>, vehicle name: <ship or none>, head: true, ...` | [ref: CSR sc_stats.py:2172-2173] | not read | Wait |
| Weapon drawn, reloads | `<AttachmentReceived> Player[Pilot_Example] Attachment[<item>_900000000020, <class>, 900000000020] Status[persistent] Port[weapon_attach_hand_right]`; reloads on `magazine_attach` | [ref: QuantumWake docs/untapped-signals.md:73-96: fires on every spawn and inventory refresh]; [ref: CSR sc_stats.py:4157 comment: reloads read from the magazine port from 4.10] | not read | Nothing now (noisy) |
| Kills on foot | none since 4.3 | [ref: CSR sc_stats.py:2236-2241, legacy]; [ref: sc-log-tracker README.md:141] | n/a | Nothing |
| Rescue beacon prompts | `Rescue Beacon activated. Searching for available assistance.` | [game] `hud_incapacitated_downedRevive*`: HUD prompts, not seen as notices | n/a | Nothing |

On-foot generators [game, 11]: the `*_Mercenary_FPS` ones, `BountyHuntersGuild_FPS`,
`InterSec_KillFPS`, `NorthRock_FPSKill`, `EckhartSecurity_KillNPC`, `Vaughn_Generator`,
`InterSec_StationAssault`, `HockrowAgency_FacilityDelve`, `EckhartSecuirty_DestroyObject`
(the game's spelling) and `HighpointWildernessSpecialists_KillAnimals` (hunting). The user's
CFP run was `CitizensForProsperity_Mercenary_FPS` [seen, activity_survey.md].

---

## 6. Trading and pay

| What | Line shape | How known | events.py today | Recommendation |
| --- | --- | --- | --- | --- |
| Commodity buy and sell, shop buy and sell, refinery sale, rental | as PLAN §3 | [seen] | parsed | Nothing; units in section 0.2 |
| Transaction done | `"Transaction Complete: "` | [seen: courier.log:169]; [game] `kiosk_TransactionComplete`, `shop_ui_transaction_complete`; [ref: sc-log-tracker sc_log_tracker.py:818-819] | generic `notice` | Nothing: it carries no figure |
| Contract pay | `"Awarded 50250 aUEC: "` | section 2 | generic `notice` | **Add now** `reward` |
| Money from or to another player | title `Transfer Recieved` (the game's spelling), body `OtherPilot_1 has sent you:` / `25000 aUEC`; `You sent OtherPilot_1:` / `25000 aUEC`; offer `OtherPilot_1 wants to send you 25000 UEC` | [game] `notification_PlayerTrade_*`; [ref: CSR sc_livelog.py:58-59]; [ref: sc-log-tracker sc_log_tracker.py:808-817] | generic `notice` | Nothing (solo) |
| aUEC balance | none | [ref: sc-log-tracker README.md:141]; the telemetry stream has it (PLAN §3) | n/a | Telemetry only |
| Reputation change | none | [ref: CSR sc_stats.py:11345-11347, "the game never writes reputation to the log"]. The amounts per contract and ending are in `Game2.dcb` (`contractResults`) [ref: QuantumWake docs/missions.md:37-60] | n/a | A reference-table job, not an event |

---

## 7. Generator names and what they mean

There are 113 `ContractGenerator` records in `Game2.dcb`, holding 2,997 contracts at the handler
level, before sub-contracts [game]. The log prints the record's short name. Mission type comes from
the contract template's `contractDisplayInfo.type` [game]. Suggested kind and view:

| Kind (view) | Generators | Mission types of their contracts [game] |
| --- | --- | --- |
| Hauling (Cargo) | Covalex_Hauling, RedWind_Hauling, LingFamilyHauling_Hauling, LingFamilyHauling_Delivery, DeadSaints_Hauling | Hauling, Hauling_Solar / _Interstellar / _Planetary; Covalex has 419 legacy contracts with no template |
| Courier (Cargo or Mission) | FTL_Courier [seen], CFP_Courier, HH_Courier, Covalex_DeliveryPilot | Delivery |
| Item recovery (Mission) | FTL_RecoverItem, RedWind_RecoverItem, BitZeros_RecoverItem, DeadSaints_RecoverItem, HockrowAgency_RecoverItem, Rayari_RecoverItem | Delivery, Collection |
| Cargo recovery (Combat, then Cargo) | CitizensForProsperity_, Covalex_, DeadSaints_, EckhartSecurity_, HeadHunters_, LingFamilyHauling_, RedWind_ `RecoverCargo` | Mercenary |
| Salvage (Salvage) | Adagio_Generator, Adagio_ResourceGathering_ShipSalvage, Adagio_ResourceGathering_FPSSalvage, RR_Salvage | Salvage, Collection |
| Mining (Mining) | Shubin_ResourceGathering_ShipMining / _GroundMining / _FPSMining, ShubinInterstellar, InterSec_ResourceGathering, HockrowAgency_ResourceGathering | Collection, ShipMining |
| Ship combat (Combat) | the 37 in section 4 | BountyHunter, Mercenary |
| On-foot combat (Combat, on foot) | the 11 in section 5 | Mercenary, BountyHunter, Investigation |
| Investigation (Mission) | CitizensForProsperity_MissingPersons, CitizensForProsperity_Investigation, HeadHunters_Investigation, HockrowAgency_MissingPerson, Vaughn_MissingPerson, InterSec_RecoverData | Investigation, Maintenance, Mercenary |
| Mixed, decide by contract name (any) | CitizensForProsperity_Generator, HeadHunters_Generator, FoxwellEnforcement_Generator, RoughAndReady_Generator, TarPits_Generator, Battaglia_Generator, Ruto_Generator, Pacheco_Generator, Clovus_Generator, WallaceKlim_Generator, Unaffiliated_Generator, TheBackpocket | several each |
| Other (Mission) | UnitedWayfarersClub (refueling), WildstarRacing_Generator (racing), TheCollector (Wikelo), Klescher_Generator (prison), Tutorial_Generator_Stanton1-4 and _TEMPLATE, BeaconContractGenerator (service beacons), events 2025Content / CleanAir / VisitingIasi / NorthRock_SOO2, FTL (empty) | Priority, Refueling, Race, Collection, Local |

For the mixed ones, keywords in the contract name decide [game]. `HaulCargo` or `_Hauling` means
Cargo. `Salvage` means Salvage. `KillShip`, `BombingRun`, `ShipWaveAttack`, `Patrol`,
`DefendShip`, `Escort` or `Ambush` means Combat. `EliminateAll`, `EliminateSpecific`,
`EliminateBoss`, `KillNPC` or `_FPS` means Combat on foot. Anything else goes to Mission.
The 5.0 test build adds contracts but no new mission types
[ref: PLAN §4, SCMDB 5.0 PTU list], so the table grows by rows.

---

## To check in the user's first real sessions

Each item, and the line that settles it. Grep the session's `Game.log` (or its backup) afterwards.

1. **Do `<MissionEnded>` and `<ObjectiveUpserted>` exist in 4.10.3?** Any contract: grep
   `<MissionEnded>` and `<ObjectiveUpserted>` near its `<EndMission>`.
2. **What a failed contract logs.** Let a timed contract run out, or fail one: expect
   `"Contract Failed: <title>: "` and `<EndMission> ... CompletionType[Fail] Reason[...]`. Record the
   reason text; check whether a hauling time-out reads `Delivery Window Expired`.
3. **What withdrawn logs.** If a contract is pulled: `"Contract Withdrawn:  ..."`, and
   `CompletionType[Deactivate]`?
4. **Hauling drop-offs.** Take a haul with the Golem OX. Then check:
   - whether `"New Objective: Deliver 0/<N> SCU of <commodity> to <place>: "` appears with
     `ObjectiveId: [dropoff_..._<i>]` for every drop;
   - whether it appears for a second haul that is not tracked;
   - whether `Objective Complete: Deliver ...` or an `ObjectiveUpserted ... COMPLETED` comes at
     each drop;
   - whether a partial delivery changes the first number.
5. **Hauling pickups.** Confirm no `New Objective: Collect ...` notice comes for a haul, and look
   for `<CreateHaulingObjectiveHandler> Dropoff created` (and any "Pickup created").
6. **Freight elevator.** At the hangar kiosk, send cargo to the elevator, then unload: look for
   `FillUnstowRequest ... Entities: <n>` and for any matching line on unloading.
7. **Pay.** After the haul completes, look for `"Awarded <n> aUEC: "`. Do the same after a courier
   run and a salvage contract.
8. **RMC sale.** Sell RMC at a terminal: `SendCommoditySellRequest` with
   `resourceGUID[a0e6c4cf-face-4f52-a020-dfa869607901]`. Check `quantity[...]` against the SCU sold.
9. **Salvage contract.** Note the marker's `generator name [...]` and `contract [...]`, the
   objective texts, and whether any line appears while scraping (expect none). Look for a
   `<Vehicle Destroyed>` of the claimed wreck when it is disintegrated or despawns.
10. **A ship kill by the user.** Expect `<Vehicle Destroyed>` with `killer '<handle>' [<geid>]`.
    Record the `reason [...]` word for a gun kill, and whether level 0 -> 1 and 1 -> 2 come as two
    lines.
11. **Crime.** After any crime or fine, expect `"CrimeStat Rating Increased: "`,
    `"Crime Committed: ..."` and `"Fined <n> UEC: "`. Note the exact text and its line split.
12. **Attacked by a player.** Expect `"<name> committed <crime> against you: "`.
13. **Death on foot.** Expect the first item line `body_01_noMagicPocket_...`, and see whether a
    loot burst from another body starts differently.
14. **Bounty contract.** Expect a `New Objective: Neutralize <name>` text, a
    `CompletionType[Complete]`, and possibly a `Journal Entry Added:` license notice.
15. **Insurance.** After losing a ship, look for `<CWallet::ProcessClaimToNextStep> New Insurance
    Claim Request`.
16. **Monitored space down.** When a comm array is out: `"Monitored Space Down: "`.

---

## What the log cannot show (every source agrees)

- **Salvage amounts:** RMC scraped, material disintegrated, what is in the hold.
  [ref: QuantumWake salvage.md:30-33]
- **Cargo aboard:** crate sizes and counts loaded or unloaded at a freight elevator. The elevator
  logs an entity count only. A hauling contract states its drop-off target, and only on about half
  the hauls. Hauling pickup places are not in the text.
  [ref: QuantumWake delivery-run.md:83-89, 112-117; untapped-signals.md:136-150]
- **Damage and combat state:** hull or shield damage, a missile lock or launch warning, hostile
  contacts nearby. The telemetry stream's warning lights are the only source
  [ref: CSR sc_stats.py:10894; PLAN §3].
- **Kills on foot**, since 4.3. [ref: CSR; sc-log-tracker README.md:141]
- **Kill counts inside a contract:** objectives update without numbers.
  [ref: QuantumWake MissionWatch.cs:13-15]
- **The aUEC balance**, and what most contracts paid. Only legacy contracts log `Awarded N aUEC`;
  a generator contract's reward is computed on the server.
  [ref: QuantumWake missions.md:199-215; sc-log-tracker README.md:141]
- **Reputation standing and its changes.** [ref: CSR sc_stats.py:11345-11347]
- **What an NPC ship carries, and which encounter a contract spawns.**
  [ref: QuantumWake encounters.md:14-16, untapped-signals.md:351-366]
- **Which contract the user is tracking.** [PLAN §4; 5.0 telemetry is expected to carry it, ref]
- **Mining amounts and quality, and the start of a refinery order.** As PLAN §3 already says
  [seen].
