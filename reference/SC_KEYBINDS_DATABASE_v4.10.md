# Star Citizen - Master Keybinding Reference (all bindable actions)

> Every action the installed game build defines, grouped by its **actionmap** - the name that goes in
> `<actionmap name="...">` in a profile XML. An action placed in any other actionmap is silently dropped.
> **Source:** the game's own `Data\Libs\Config\defaultProfile.xml` + English `global.ini`, read from `Data.p4k`.
> **Game build:** Star Citizen Alpha **4.10** (build 4.10.201.48085, branch sc-alpha-4.10.0, change 13220821, built Wed Nov 18 2026).
> **Actions:** 1104 entries across 50 actionmaps.
>
> `Action` is the internal name for `<action name="...">`. The default columns are what the game binds
> out of the box; **joystick defaults apply to joystick 1 (`js1`)** and stay live under a custom profile
> unless that profile rebinds or clears the action. Actions with no label are hidden from the in-game
> Keybindings menu. Regenerate with `python tools/gamedata.py catalog`.

## Contents

- [`seat_general`](#seat_general) - Vehicles - Seats and Operator Modes (28)
- [`spaceship_general`](#spaceship_general) - Vehicles - Cockpit (19)
- [`vehicle_mfd`](#vehicle_mfd) - Vehicles - Multi Function Displays (MFDs) (55)
- [`spaceship_view`](#spaceship_view) - Vehicles - View (28)
- [`spaceship_movement`](#spaceship_movement) - Flight - Movement (103)
- [`spaceship_quantum`](#spaceship_quantum) - Flight - Quantum Travel (1)
- [`spaceship_docking`](#spaceship_docking) - Flight - Docking (2)
- [`spaceship_targeting`](#spaceship_targeting) - Vehicles - Targeting (25)
- [`spaceship_targeting_advanced`](#spaceship_targeting_advanced) - Vehicles - Target Cycling (22)
- [`spaceship_target_hailing`](#spaceship_target_hailing) - Flight - Target Hailing (1)
- [`spaceship_radar`](#spaceship_radar) - Flight - Radar (1)
- [`spaceship_scanning`](#spaceship_scanning) - Vehicles - Scanning (11)
- [`spaceship_mining`](#spaceship_mining) - Vehicles - Mining (10)
- [`spaceship_salvage`](#spaceship_salvage) - Vehicles - Salvage (31)
- [`turret_movement`](#turret_movement) - Turret Movement (17)
- [`turret_advanced`](#turret_advanced) - Turret Advanced (9)
- [`spaceship_weapons`](#spaceship_weapons) - Vehicles - Weapons (49)
- [`spaceship_missiles`](#spaceship_missiles) - Vehicles - Missiles (14)
- [`spaceship_defensive`](#spaceship_defensive) - Vehicles - Shields and Countermeasures (12)
- [`spaceship_auto_weapons`](#spaceship_auto_weapons) (1)
- [`spaceship_power`](#spaceship_power) - Flight - Power (29)
- [`spaceship_hud`](#spaceship_hud) - Flight - HUD (27)
- [`lights_controller`](#lights_controller) - Lights (5)
- [`vehicle_mobiglas`](#vehicle_mobiglas) - Vehicle - Mobiglas (28)
- [`stopwatch`](#stopwatch) - Stop Watch (2)
- [`player`](#player) - On Foot - All (144)
- [`prone`](#prone) - On Foot - All (2)
- [`mapui`](#mapui) (19)
- [`hacking`](#hacking) (22)
- [`tractor_beam`](#tractor_beam) - On Foot - All (10)
- [`mining`](#mining) (1)
- [`incapacitated`](#incapacitated) - On Foot - All (1)
- [`zero_gravity_eva`](#zero_gravity_eva) - E.V.A - All (23)
- [`zero_gravity_traversal`](#zero_gravity_traversal) - E.V.A. - Zero-G Traversal (4)
- [`vehicle_general`](#vehicle_general) - Ground Vehicle - General (27)
- [`vehicle_driver`](#vehicle_driver) - Ground Vehicle - Movement (20)
- [`debug`](#debug) (14)
- [`IFCS_controls`](#ifcs_controls) (4)
- [`spectator`](#spectator) - Electronic Access - Spectator (28)
- [`default`](#default) - Social - General (57)
- [`ui_textfield`](#ui_textfield) (6)
- [`ui_notification`](#ui_notification) - Social - Invites (3)
- [`player_emotes`](#player_emotes) - Social - Emotes (40)
- [`player_input_optical_tracking`](#player_input_optical_tracking) - VOIP, FOIP and Head Tracking (13)
- [`player_choice`](#player_choice) - Quick Keys, Interactions, and Inner Thought (39)
- [`flycam`](#flycam) (19)
- [`view_director_mode`](#view_director_mode) - Camera - Advanced Camera Controls (32)
- [`character_customizer`](#character_customizer) (28)
- [`RemoteRigidEntityController`](#remoterigidentitycontroller) (17)
- [`server_renderer`](#server_renderer) (1)

## seat_general

*In-game group: Vehicles - Seats and Operator Modes*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_emergency_exit` | Emergency Exit Seat | Press LShift + H to engage emergency exit | u+lshift |  |  | tap |
| `v_eject` | Eject |  | ralt+y |  |  | press |
| `v_view_look_behind` | Look behind |  | comma |  | shoulderl+a | delayed_hold_no_retrigger |
| `v_toggle_mining_mode` | Toggle Mining Operator Mode | Mining Mode Toggle |  |  |  | press |
| `v_toggle_salvage_mode` | Toggle Salvage Operator Mode | Activate salvage mode when seated. |  |  |  | press |
| `v_cycle_industrial_mode` | Cycle Industrial Operator Modes | Next Industrial Mode | m |  |  | press |
| `v_toggle_refuel_mode` | Toggle Refuel Operator Mode |  | m |  |  | press |
| `v_toggle_scan_mode` | Toggle Scanning Operator Mode | Scanning Mode Toggle | v |  | dpad_right | press |
| `v_toggle_quantum_mode` | Toggle Quantum Operator Mode |  |  |  |  | press |
| `v_toggle_missile_mode` | Toggle Missile Operator Mode |  |  |  |  | press |
| `v_toggle_guns_mode` | Toggle Guns Operator Mode |  |  |  |  | press |
| `v_toggle_flight_mode` | Toggle Flight Operator Mode |  |  |  |  | press |
| `v_set_mining_mode` | Set Mining Operator Mode | Set Mining Operator Mode |  |  |  | press |
| `v_set_salvage_mode` | Set Salvage Operator Mode | Set Salvage Operator Mode |  |  |  | press |
| `v_set_refuel_mode` | Set Refuel Operator Mode |  |  |  |  | press |
| `v_set_scan_mode` | Set Scanning Operator Mode | Set Scanning Operator Mode |  |  |  | press |
| `v_set_quantum_mode` | Set Quantum Operator Mode | Set Quantum Operator Mode |  |  |  | press |
| `v_set_missile_mode` | Set Missile Operator Mode | Set Missile Operator Mode |  |  |  | press |
| `v_set_guns_mode` | Set Guns Operator Mode | Set Guns Operator Mode |  |  |  | press |
| `v_set_flight_mode` | Set Flight Operator Mode | Set Flight Operator Mode |  |  |  | press |
| `v_enter_remote_turret_1` | Enter Remote Turret 1 |  |  |  |  | press |
| `v_enter_remote_turret_2` | Enter Remote Turret 2 |  |  |  |  | press |
| `v_enter_remote_turret_3` | Enter Remote Turret 3 |  |  |  |  | press |
| `v_operator_mode_cycle_forward` | Next Operator Mode |  | mouse3 |  |  | tap |
| `v_operator_mode_cycle_back` | Previous Operator Mode |  |  |  |  | tap |
| `v_light_amplification_toggle` | Light Amplification Toggle |  | ralt+l |  |  | tap |
| `v_light_amplification_on` | Light Amplification On |  |  |  |  | tap |
| `v_light_amplification_off` | Light Amplification Off |  |  |  |  | tap |

## spaceship_general

*In-game group: Vehicles - Cockpit*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_self_destruct` | Self Destruct |  | backspace |  |  | delayed_press_medium |
| `v_cooler_throttle_up` | Increase Cooler Rate |  |  |  |  | press+hold |
| `v_cooler_throttle_down` | Decrease Cooler Rate |  |  |  |  | press+hold |
| `spectate_enterpuremode` | - |  |  |  |  | delayed_press |
| `v_flightready` | Flight / Systems Ready | Flight / Systems Ready | ralt+r |  |  | press |
| `v_toggle_all_doors` | Open/Close Doors (Toggle) | Toggle Open/Close Doors |  |  |  | press |
| `v_open_all_doors` | Open All Doors | Open All Doors |  |  |  | press |
| `v_close_all_doors` | Close All Doors | Close All Doors |  |  |  | press |
| `v_toggle_all_doorlocks` | Lock/Unlock Doors (Toggle) | Toggle Lock/Unlock Doors |  |  |  | press |
| `v_lock_all_doors` | Lock All Doors | Lock All Doors |  |  |  | press |
| `v_unlock_all_doors` | Unlock All Doors | Unlock All Doors |  |  |  | press |
| `v_toggle_all_portlocks` | Port Lock Toggle All | Toggle Open/Close Ports | ralt+K |  |  | press |
| `v_lock_all_ports` | Port Lock All |  |  |  |  | press |
| `v_unlock_all_ports` | Port Unlock All |  |  |  |  | press |
| `pc_conversation_option1` | - |  | 1 |  |  | all |
| `pc_conversation_option2` | - |  | 2 |  |  | all |
| `pc_conversation_option3` | - |  | 3 |  |  | all |
| `pc_conversation_option4` | - |  | 4 |  |  | all |
| `pc_conversation_option5` | - |  | 5 |  |  | all |

## vehicle_mfd

*In-game group: Vehicles - Multi Function Displays (MFDs)*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_mfd_interact_cycle_forwards_short` | MFD - Cycle Page - Forwards (Short Press) |  | lalt+e |  |  | tap |
| `v_mfd_interact_cycle_forwards_long` | MFD - Cycle Page - Forwards (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_interact_cycle_backwards_short` | MFD - Cycle Page - Backwards (Short Press) |  | lalt+q |  |  | tap |
| `v_mfd_interact_cycle_backwards_long` | MFD - Cycle Page - Backwards (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_movement_up_short` | MFD - Movement - Up (Short Press) |  |  |  |  | tap |
| `v_mfd_movement_up_long` | MFD - Movement - Up (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_movement_down_short` | MFD - Movement - Down (Short Press) |  |  |  |  | tap |
| `v_mfd_movement_down_long` | MFD - Movement - Down (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_movement_left_short` | MFD - Movement - Left (Short Press) |  |  |  |  | tap |
| `v_mfd_movement_left_long` | MFD - Movement - Left (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_movement_right_short` | MFD - Movement - Right (Short Press) |  |  |  |  | tap |
| `v_mfd_movement_right_long` | MFD - Movement - Right (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_primary_short` | MFD - Select - Primary (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_primary_long` | MFD - Select - Primary (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_cast_left_short` | MFD - Select - Left Cast (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_cast_left_long` | MFD - Select - Left Cast (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_cast_right_short` | MFD - Select - Right Cast (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_cast_right_long` | MFD - Select - Right Cast (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_1_short` | MFD - Select - MFD 1 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_1_long` | MFD - Select - MFD 1 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_2_short` | MFD - Select - MFD 2 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_2_long` | MFD - Select - MFD 2 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_3_short` | MFD - Select - MFD 3 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_3_long` | MFD - Select - MFD 3 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_4_short` | MFD - Select - MFD 4 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_4_long` | MFD - Select - MFD 4 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_5_short` | MFD - Select - MFD 5 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_5_long` | MFD - Select - MFD 5 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_6_short` | MFD - Select - MFD 6 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_6_long` | MFD - Select - MFD 6 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_7_short` | MFD - Select - MFD 7 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_7_long` | MFD - Select - MFD 7 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_8_short` | MFD - Select - MFD 8 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_8_long` | MFD - Select - MFD 8 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_9_short` | MFD - Select - MFD 9 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_9_long` | MFD - Select - MFD 9 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_soft_select_mfd_10_short` | MFD - Select - MFD 10 (Short Press) |  |  |  |  | tap |
| `v_mfd_soft_select_mfd_10_long` | MFD - Select - MDF 10 (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_quick_action_repair_all` | MFD - Quick Action - Self Repair All | ui_CIMFD_Quick_Action_Repair_All_Desc |  |  |  | tap |
| `v_mfd_select_view_self_status_short` | MFD - Set Page - Self Status (Short Press) |  |  |  |  | tap |
| `v_mfd_select_view_self_status_long` | MFD - Set Page - Self Status (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_select_view_target_status_short` | MFD - Set Page - Target Status (Short Press) |  |  |  |  | tap |
| `v_mfd_select_view_target_status_long` | MFD - Set Page - Target Status (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_select_view_scanning_short` | MFD - Set Page - Scanning (Short Press) |  |  |  |  | tap |
| `v_mfd_select_view_scanning_long` | MFD - Set Page - Scanning (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_select_view_configuration_short` | MFD - Set Page - Vehicle Configuration (Short Press) |  |  |  |  | tap |
| `v_mfd_select_view_configuration_long` | MFD - Set Page - Vehicle Configuration (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_select_view_comms_short` | MFD - Set Page - Communications (Short Press) |  |  |  |  | tap |
| `v_mfd_select_view_comms_long` | MFD - Set Page - Communications (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_select_view_ifcs_short` | MFD - Set Page - IFCS (Short Press) |  |  |  |  | tap |
| `v_mfd_select_view_ifcs_long` | MFD - Set Page - IFCS (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_select_view_diagnostics_short` | MFD - Set Page - Diagnostics (Short Press) |  |  |  |  | tap |
| `v_mfd_select_view_diagnostics_long` | MFD - Set Page - Diagnostics (Long Press) |  |  |  |  | delayed_press |
| `v_mfd_select_view_resource_network_short` | MFD - Set Page - Resource Network (Short Press) |  |  |  |  | tap |
| `v_mfd_select_view_resource_network_long` | MFD - Set Page - Resource Network (Long Press) |  |  |  |  | delayed_press |

## spaceship_view

*In-game group: Vehicles - View*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_view_yaw_left` | Look left |  |  |  |  | press+release |
| `v_view_yaw_right` | Look right |  |  |  |  | press+release |
| `v_view_yaw` | Look left / right |  |  | x | thumbrx |  |
| `v_view_yaw_mouse` | Look left / right |  | maxis_x |  |  |  |
| `v_view_yaw_absolute` | - |  | HMD_Yaw |  |  |  |
| `v_view_pitch_up` | Look up |  |  |  |  | press+release |
| `v_view_pitch_down` | Look down |  |  |  |  | press+release |
| `v_view_pitch` | Look up / down |  |  | y | thumbry |  |
| `v_view_pitch_mouse` | Look up / down |  | maxis_y |  |  |  |
| `v_view_pitch_absolute` | - |  | HMD_Pitch |  |  |  |
| `v_view_roll_absolute` | - |  | HMD_Roll |  |  |  |
| `v_view_cycle_fwd` | Cycle camera view |  | f4 |  | shoulderl+y | tap |
| `v_view_cycle_internal_fwd` | - |  |  |  |  | press |
| `v_view_option` | - |  |  |  |  | press+release |
| `v_view_mode` | Cycle camera orbit mode |  |  |  |  | press |
| `v_view_zoom_in` | Zoom in (3rd person view) |  | mwheel_up |  |  | press+hold |
| `v_view_zoom_out` | Zoom out (3rd person view) |  | mwheel_down |  |  | press+hold |
| `v_view_interact` | - |  | f |  | a | press+release |
| `v_view_freelook_mode` | Freelook (Hold) |  | z |  |  | hold |
| `v_view_dynamic_zoom_rel` | Dynamic Zoom In and Out (rel.) |  |  |  |  |  |
| `v_view_dynamic_zoom_rel_in` | Dynamic Zoom In (rel.) |  |  |  |  | all |
| `v_view_dynamic_zoom_rel_out` | Dynamic Zoom Out (rel.) |  |  |  |  | all |
| `v_view_dynamic_zoom_abs` | Dynamic Zoom In and Out (abs.) | Axis assignment for dynamic zoom |  |  |  |  |
| `v_view_dynamic_zoom_abs_toggle` | Dynamic Zoom Toggle (abs.) | Holds the dynamic zoom as long as the button is held |  |  |  | smart_toggle |
| `v_ads_hold` | Precision Targeting - Hold |  |  |  |  | hold |
| `v_ads_toggle` | Precision Targeting - Toggle On / Off |  | mouse2 |  | triggerl_btn | tap |
| `v_ads_stable_max_zoom_hold` | Precision Targeting - Maximum Zoom (hold) |  | mouse2 |  |  | delayed_hold |
| `v_ads_cycle_tracking` | Precision Targeting - Toggle Camera Tracking |  | ralt+mouse2 |  |  | tap |

## spaceship_movement

*In-game group: Flight - Movement*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_pitch_up` | Pitch up |  | down |  |  | press+release |
| `v_pitch_down` | Pitch down |  | up |  |  | press+release |
| `v_pitch` | Pitch |  |  | y | thumbry |  |
| `v_pitch_mouse` | Pitch |  | maxis_y |  |  |  |
| `v_yaw_left` | Yaw left |  | left |  |  | press+release |
| `v_yaw_right` | Yaw right |  | right |  |  | press+release |
| `v_yaw` | Yaw |  |  | x | thumblx |  |
| `v_yaw_mouse` | Yaw |  | maxis_x |  |  |  |
| `v_roll_left` | Roll left |  | q |  |  | press+release |
| `v_roll_right` | Roll right |  | e |  |  | press+release |
| `v_roll` | Roll |  |  | rotz | thumbrx |  |
| `v_roll_mouse` | Roll |  |  |  |  |  |
| `v_toggle_relative_mouse_mode` | Cycle mouse mode (VJoy / Relative) | Switches the mouse behavior for ship rotations between a relative (FPS style) and a Vjoy mode. |  |  |  | smart_toggle |
| `v_toggle_yaw_roll_swap` | Swap Yaw / Roll (Toggle) |  |  |  | thumbr | smart_toggle |
| `v_strafe_up` | Strafe up (abs.) |  | space | button9 |  | press+release |
| `v_strafe_down` | Strafe down (abs.) |  | lctrl | button10 |  | press+release |
| `v_strafe_vertical` | Strafe up / down (abs.) |  |  |  | shoulderl+thumbly |  |
| `v_strafe_left` | Strafe left (abs.) |  | a | hat1_left |  | press+release |
| `v_strafe_right` | Strafe right (abs.) |  | d | hat1_right |  | press+release |
| `v_strafe_lateral` | Strafe left / right (abs.) |  |  |  | shoulderl+thumblx |  |
| `v_strafe_forward` | Throttle - Increase |  | w |  |  | press+release |
| `v_strafe_back` | Throttle - Decrease |  | s |  |  | press+release |
| `v_strafe_longitudinal` | Throttle - Forward / Back |  |  |  | thumbly |  |
| `v_strafe_longitudinal_invert` | Throttle - Forward / Back Invert | Inverts Strafe Longitudinal Absolute Axis Half (Neutral - Backward) |  |  |  | press+release |
| `v_ifcs_throttle_swap_mode` | Throttle - Cruise Mode - Toggle |  | lalt+c |  |  | press |
| `v_ifcs_throttle_set_sticky` | Throttle - Cruise Mode - Enable |  |  |  |  | press |
| `v_ifcs_throttle_set_normal` | Throttle - Cruise Mode - Disable |  |  |  |  | press |
| `v_strafe_trim_set_long` | Throttle - Trim - Set (Long Press) | Throttle - Trim - Set (Long Press) |  |  |  | delayed_press |
| `v_strafe_trim_set_short` | Throttle - Trim - Set (Short Press) | Throttle - Trim - Set (Short Press) |  |  |  | tap |
| `v_strafe_trim_set_100_long` | Throttle - Trim - Set To 100% (Long Press) | Throttle - Trim - Set To 100% (Long Press) |  |  |  | delayed_press |
| `v_strafe_trim_set_100_short` | Throttle - Trim - Set To 100% (Short Press) | Throttle - Trim - Set To 100% (Short Press) |  |  |  | tap |
| `v_strafe_trim_set_50_long` | Throttle - Trim - Set To 50% (Long Press) | Throttle - Trim - Set To 50% (Long Press) |  |  |  | delayed_press |
| `v_strafe_trim_set_50_short` | Throttle - Trim - Set To 50% (Short Press) | Throttle - Trim - Set To 50% (Short Press) |  |  |  | tap |
| `v_strafe_trim_reset_long` | Throttle - Trim - Release (Long Press) | Throttle - Trim - Release (Long Press) | x |  |  | delayed_press |
| `v_strafe_trim_reset_short` | Throttle - Trim - Release (Short Press) | Throttle - Trim - Release (Short Press) | x |  |  | tap |
| `v_ifcs_vector_decoupling_toggle` | Enable / Disable decoupled mode | Switch between coupled or decoupled mode | c |  | b | tap |
| `v_ifcs_vector_decoupling_on` | Enable decoupled mode | Enable decoupled mode |  |  |  | press |
| `v_ifcs_vector_decoupling_off` | Disable decoupled mode | Disable decoupled mode |  |  |  | press |
| `v_afterburner` | Boost |  | lshift | button8 | thumbl | all |
| `v_ifcs_speed_limiter_up` | Speed Limiter - Increase (hold) | Speed Limiter - Increase (hold) |  |  |  | press+release |
| `v_ifcs_speed_limiter_down` | Speed Limiter - Decrease (hold) | Speed Limiter - Decrease (hold) |  |  |  | press+release |
| `v_ifcs_speed_limiter_increment` | Speed Limiter - Step Up (tap) | Speed Limiter - Step Up (tap) | lalt+mwheel_up |  |  | press |
| `v_ifcs_speed_limiter_decrement` | Speed Limiter - Step Down (tap) | Speed Limiter - Step Down (tap) | lalt+mwheel_down |  |  | press |
| `v_ifcs_speed_limiter_rel` | Speed Limiter (rel) | Speed Limiter (rel) |  |  |  |  |
| `v_ifcs_speed_limiter_abs` | Speed Limiter (abs) | Speed Limiter (abs) |  |  |  |  |
| `v_ifcs_speed_limiter_toggle` | Speed Limiter - Enable / Disable | Speed Limiter - Enable / Disable |  |  |  | tap |
| `v_ifcs_speed_limiter_on` | Speed Limiter - Enable | Speed Limiter - Enable |  |  |  | press |
| `v_ifcs_speed_limiter_off` | Speed Limiter - Disable | Speed Limiter - Disable |  |  |  | press |
| `v_accel_range_up` | Acceleration Limiter - Increase (hold) | Acceleration Limiter - Increase (hold) |  |  |  | press+release |
| `v_accel_range_down` | Acceleration Limiter - Decrease (hold) | Acceleration Limiter - Decrease (hold) |  |  |  | press+release |
| `v_accel_range_increment` | Acceleration Limiter - Step Up (tap) | Acceleration Limiter - Step Up (tap) | ralt+mwheel_up |  |  | press |
| `v_accel_range_decrement` | Acceleration Limiter - Step Down (tap) | Acceleration Limiter - Step Down (tap) | ralt+mwheel_down |  |  | press |
| `v_accel_range_rel` | Acceleration Limiter (rel) | Acceleration Limiter (rel) |  |  |  |  |
| `v_accel_range_abs` | Acceleration Limiter (abs) | Acceleration Limiter (abs) |  |  |  |  |
| `v_space_brake` | Spacebrake |  | x |  |  | press+release |
| `v_lock_rotation` | Lock Pitch / Yaw Movement (Toggle / Hold) | While active no rotational inputs are allowed to your ship. This is useful for arresting movement when you lost control using a mouse. | rshift |  |  | smart_toggle |
| `v_ifcs_gsafe_on` | G-Force safety on | G-Force safety on |  |  |  | press |
| `v_ifcs_gsafe_off` | G-Force safety off | G-Force safety off |  |  |  | press |
| `v_ifcs_toggle_gforce_safety` | G-Force Safety On/Off (Toggle / Hold) |  |  |  |  | tap |
| `v_ifcs_toggle_esp` | E.S.P. - Toggle On / Off (Press) |  |  |  |  | smart_toggle |
| `v_ifcs_esp_hold` | E.S.P. - Enable Temporarily (Hold) |  |  |  |  | hold |
| `v_toggle_landing_system` | Landing System (Toggle) |  | n | button12 | dpad_down | tap |
| `v_deploy_landing_system` | Landing System (Deploy) |  |  |  |  | press |
| `v_retract_landing_system` | Landing System (Retract) |  |  |  |  | press |
| `v_vtol_toggle` | Toggle VTOL | Enable / Disable Vertical Take-Off and Landing | k |  |  | tap |
| `v_vtol_on` | Enable VTOL | Enable Vertical Take-Off and Landing |  |  |  | press |
| `v_vtol_off` | Disable VTOL | Disable Vertical Take-Off and Landing |  |  |  | press |
| `v_transform_deploy` | Expand Configuration | Expands the vehicle's configuration. |  |  |  | press |
| `v_transform_retract` | Retract Configuration | Retracts the vehicle's configuration. |  |  |  | press |
| `v_transform_cycle` | Cycle Configuration | Cycle between the vehicle's expanded and retracted configurations. | lalt+k |  |  | tap |
| `v_autoland` | Autoland | Activate Autoland | n | button12 | dpad_down | delayed_press |
| `v_atc_request` | Request Landing | Contacts ATC and other landing services. | lalt+n |  |  | tap |
| `v_atc_loading_area_request` | Request Cargo Loading |  | ralt+n |  |  | tap |
| `v_master_mode_cycle` | Cycle Master Mode (Short Press) |  |  |  |  | tap |
| `v_master_mode_cycle_long` | Cycle Master Mode (Long Press) |  | b |  |  | delayed_press |
| `v_master_mode_set_nav` | Set Master Mode to Nav |  |  |  |  | press |
| `v_master_mode_set_scm` | Set Master Mode to SCM |  |  |  |  | press |
| `v_toggle_jump_request` | Jump Drive - Request Jump |  | mouse1 |  |  | tap |
| `v_ifcs_gravity_compensation_toggle` | IFCS - Gravity Compensation - Toggle | IFCS - Gravity Compensation - Toggle |  |  |  | tap |
| `v_ifcs_gravity_compensation_on` | IFCS - Gravity Compensation - Enable | IFCS - Gravity Compensation - Enable |  |  |  | press |
| `v_ifcs_gravity_compensation_off` | IFCS - Gravity Compensation - Disable | IFCS - Gravity Compensation - Disable |  |  |  | press |
| `v_ifcs_wind_compensation_toggle` | IFCS - Wind Compensation - Toggle | IFCS - Wind Compensation - Toggle |  |  |  | tap |
| `v_ifcs_wind_compensation_on` | IFCS - Wind Compensation - Enable | IFCS - Wind Compensation - Enable |  |  |  | press |
| `v_ifcs_wind_compensation_off` | IFCS - Wind Compensation - Disable | IFCS - Wind Compensation - Disable |  |  |  | press |
| `v_auto_precision_mode_toggle` | Automatic Precision Mode - Toggle |  |  |  |  | tap |
| `v_auto_precision_mode_on` | Automatic Precision Mode - Enable |  |  |  |  | press |
| `v_auto_precision_mode_off` | Automatic Precision Mode - Disable |  |  |  |  | press |
| `v_ifcs_proximity_assist_toggle` | IFCS - Proximity Assist - Toggle | IFCS - Proximity Assist - Toggle |  |  |  | tap |
| `v_ifcs_proximity_assist_on` | IFCS - Proximity Assist - Enable | IFCS - Proximity Assist - Enable |  |  |  | press |
| `v_ifcs_proximity_assist_off` | IFCS - Proximity Assist - Disable | IFCS - Proximity Assist - Disable |  |  |  | press |
| `v_ifcs_stability_toggle` | IFCS - Stability - Toggle | IFCS - Stability - Toggle |  |  |  | tap |
| `v_ifcs_stability_on` | IFCS - Stability - Enable | IFCS - Stability - Enable |  |  |  | press |
| `v_ifcs_stability_off` | IFCS - Stability - Disable | IFCS - Stability - Disable |  |  |  | press |
| `v_ifcs_command_toggle` | IFCS Command Behaviour Toggle | IFCS Command Behaviour Toggle |  |  |  | tap |
| `v_ifcs_command_on` | IFCS Command Behaviour On | IFCS Command Behaviour On |  |  |  | press |
| `v_ifcs_command_off` | IFCS Command Behaviour Off | IFCS Command Behaviour Off |  |  |  | press |
| `v_ifcs_core_toggle` | IFCS - Core - Toggle On / Off | IFCS - Core - Toggle On / Off |  |  |  | tap |
| `v_ifcs_core_on` | IFCS - Core - Enable | IFCS - Core - Enable |  |  |  | press |
| `v_ifcs_core_off` | IFCS - Core - Disable | IFCS - Core - Disable |  |  |  | press |
| `v_ifcs_reset_gmeter_max` | Reset Flight Accelerometer | Resets the max endured Gs for the accelerometer. | ralt+c |  |  | tap |
| `v_flight_advanced_hud_toggle` | Advanced HUD - Toggle | Advanced HUD - Toggle |  |  |  | tap |
| `v_flight_advanced_hud_on` | Advanced HUD - Enable | Advanced HUD - Enable |  |  |  | press |
| `v_flight_advanced_hud_off` | Advanced HUD - Disable | Advanced HUD - Disable |  |  |  | press |

## spaceship_quantum

*In-game group: Flight - Quantum Travel*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_toggle_qdrive_engagement` | Engage Quantum Drive (Hold) | Engages the quantum drive. | mouse1 | button1 | triggerr_btn | delayed_press |

## spaceship_docking

*In-game group: Flight - Docking*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_toggle_docking_request` | Docking (Initiate) | ui_CIToggleLandingSystem_DockDesc | ralt+n |  |  | tap |
| `v_dock_toggle_view` | Toggle Docking Camera | Toggles the docking camera. | 0 |  |  | delayed_press |

## spaceship_targeting

*In-game group: Vehicles - Targeting*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_auto_targeting_toggle_long` | Auto Targeting - Toggle On/Off (Long Press) | Auto Targeting - Toggle On/Off (Long Press) | t |  |  | delayed_press |
| `v_auto_targeting_toggle_short` | Auto Targeting - Toggle On/Off (Short Press) | Auto Targeting - Toggle On/Off (Short Press) |  |  |  | tap |
| `v_auto_targeting_enable_short` | Auto Targeting - Toggle On (Short Press) | Auto Targeting - Toggle On (Short Press) |  |  |  | tap |
| `v_auto_targeting_enable_long` | Auto Targeting - Toggle On (Long Press) | Auto Targeting - Toggle On (Long Press) |  |  |  | delayed_press |
| `v_auto_targeting_disable_short` | Auto Targeting - Toggle Off (Short Press) | Auto Targeting - Toggle Off (Short Press) |  |  |  | tap |
| `v_auto_targeting_disable_long` | Auto Targeting - Toggle Off (Long Press) | Auto Targeting - Toggle Off (Long Press) |  |  |  | delayed_press |
| `v_target_toggle_lock_index_1` | Pin Index 1 - Lock / Unlock Pinned Target |  | 1 |  |  | tap |
| `v_target_toggle_lock_index_2` | Pin Index 2 - Lock / Unlock Pinned Target |  | 2 |  |  | tap |
| `v_target_toggle_lock_index_3` | Pin Index 3 - Lock / Unlock Pinned Target |  | 3 |  |  | tap |
| `v_target_toggle_pin_index_1` | Pin Index 1 - Pin / Unpin Selected Target |  | lalt+1 |  |  | tap |
| `v_target_toggle_pin_index_2` | Pin Index 2 - Pin / Unpin Selected Target |  | lalt+2 |  |  | tap |
| `v_target_toggle_pin_index_3` | Pin Index 3 - Pin / Unpin Selected Target |  | lalt+3 |  |  | tap |
| `v_target_toggle_pin_index_1_hold` | Pin Index 1 - Pin / Unpin Selected Target (Hold) |  |  |  |  | delayed_press |
| `v_target_toggle_pin_index_2_hold` | Pin Index 2 - Pin / Unpin Selected Target (Hold) |  |  |  |  | delayed_press |
| `v_target_toggle_pin_index_3_hold` | Pin Index 3 - Pin / Unpin Selected Target (Hold) |  |  |  |  | delayed_press |
| `v_target_pin_selected` | Pin Selected Target |  |  |  |  | tap |
| `v_target_unpin_selected` | Unpin Selected Target |  |  |  |  | tap |
| `v_target_pin_selected_hold` | Pin Selected Target (Hold) |  |  |  |  | delayed_press |
| `v_target_unpin_selected_hold` | Unpin Selected Target (Hold) |  |  |  |  | delayed_press |
| `v_target_remove_all_pins` | Remove All Pinned Targets |  | 0 |  |  | tap |
| `v_target_lock_selected` | Lock Selected Target | Lock Selected Target |  |  |  | tap |
| `v_target_unlock` | Unlock Current Target | Unlock Current Target | lalt+t |  |  | tap |
| `v_look_ahead_enable` | Enable / Disable Look Ahead | Enables and disables Look Ahead Mode | lalt+l |  |  | smart_toggle |
| `v_look_ahead_start_target_tracking` | Enable / Disable Target Padlock (Toggle, Hold) | Allows you to track a locked target with your head |  |  |  | smart_toggle |
| `v_target_tracking_auto_zoom` | Auto Zoom On Selected Target On / Off (Toggle, Hold) | Allows you to enable and disable auto zoom on selected targets. |  |  |  | smart_toggle |

## spaceship_targeting_advanced

*In-game group: Vehicles - Target Cycling*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_target_under_reticle` | Lock Target Under Reticle | Lock Target Under Reticle |  |  |  | tap |
| `v_target_cycle_in_view_back` | Cycle Lock - In View - Back |  |  |  |  | tap |
| `v_target_cycle_in_view_fwd` | Cycle Lock - In View - Forward |  | t |  |  | tap |
| `v_target_cycle_in_view_reset` | Cycle Lock - In View - Under Reticle |  | t |  |  | tap |
| `v_target_cycle_pinned_back` | Cycle Lock - Pinned - Back |  |  |  |  | tap |
| `v_target_cycle_pinned_fwd` | Cycle Lock - Pinned - Forward |  |  |  |  | tap |
| `v_target_cycle_pinned_reset` | Cycle Lock - Pinned - Reset to First |  |  |  |  | tap |
| `v_target_cycle_attacker_back` | Cycle Lock - Attackers - Back |  |  |  |  | tap |
| `v_target_cycle_attacker_fwd` | Cycle Lock - Attackers - Forward |  | 4 |  |  | tap |
| `v_target_cycle_attacker_reset` | Cycle Lock - Attackers - Reset to Closest |  | 4 |  |  | tap |
| `v_target_cycle_hostile_back` | Cycle Lock - Hostiles - Back |  |  |  |  | tap |
| `v_target_cycle_hostile_fwd` | Cycle Lock - Hostiles - Forward |  | 5 |  |  | tap |
| `v_target_cycle_hostile_reset` | Cycle Lock - Hostiles - Reset to Closest |  | 5 |  |  | tap |
| `v_target_cycle_friendly_back` | Cycle Lock - Friendlies - Back |  |  |  |  | tap |
| `v_target_cycle_friendly_fwd` | Cycle Lock - Friendlies - Forward |  | 6 |  |  | tap |
| `v_target_cycle_friendly_reset` | Cycle Lock - Friendlies - Reset to Closest |  | 6 |  |  | tap |
| `v_target_cycle_all_back` | Cycle Lock - All - Back |  |  |  |  | tap |
| `v_target_cycle_all_fwd` | Cycle Lock - All - Forward |  | 7 |  |  | tap |
| `v_target_cycle_all_reset` | Cycle Lock - All - Reset to Closest |  | 7 |  |  | tap |
| `v_target_cycle_subitem_back` | Cycle Lock - Sub-Target - Back |  |  |  |  | tap |
| `v_target_cycle_subitem_fwd` | Cycle Lock - Sub-Target - Forward |  | r |  |  | tap |
| `v_target_cycle_subitem_reset` | Cycle Lock - Sub-Target - Reset to Main Target |  | lalt+r |  |  | tap |

## spaceship_target_hailing

*In-game group: Flight - Target Hailing*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_target_hail` | Hail Target | HailTarget | 9 |  |  | tap |

## spaceship_radar

*In-game group: Flight - Radar*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_invoke_ping` | Activate Ping (Hold & Release) | Activates the Ping Wave | tab |  | y | hold |

## spaceship_scanning

*In-game group: Vehicles - Scanning*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_scanning_trigger_scan` | Activate Scanning | Activates the Scanning | mouse1 |  | shoulderl+shoulderr | hold |
| `v_inc_scan_focus_level` | Increase Scanning Angle | Increase the angle of the Scanning Cone | mwheel_up | button3 | triggerr_btn | press |
| `v_dec_scan_focus_level` | Decrease Scanning Angle | Decrease the angle of the Scanning Cone | mwheel_down | button4 | triggerl_btn | press |
| `v_ui_prev_scan_tab` | - |  | left |  |  | tap |
| `v_ui_next_scan_tab` | - |  | right |  |  | tap |
| `v_ui_prev_scan_page` | - |  | up |  |  | tap |
| `v_ui_next_scan_page` | - |  | down |  |  | tap |
| `v_ui_prev_contact_page` | - |  | rctrl+left |  |  | tap |
| `v_ui_next_contact_page` | - |  | rctrl+right |  |  | tap |
| `v_ui_prev_contact` | - |  | rctrl+up |  |  | tap |
| `v_ui_next_contact` | - |  | rctrl+down |  |  | tap |

## spaceship_mining

*In-game group: Vehicles - Mining*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_toggle_mining_laser_fire` | Fire Mining Laser (Toggle) | Fire Mining Laser (Toggle) | mouse1 | button1 | shoulderr | smart_toggle |
| `v_toggle_mining_laser_type` | Switch Mining Laser (Toggle) | Switch Mining Laser (Toggle) | lalt+mouse1 | button2 | shoulderl+shoulderr | press |
| `v_increase_mining_throttle` | Increase Mining Laser Power | Increase Mining Laser Power | maxis_z | button3 | triggerr_btn | press |
| `v_decrease_mining_throttle` | Decrease Mining Laser Power | Decrease Mining Laser Power |  | button4 | triggerl_btn | press |
| `v_mining_throttle` | Increase / Decrease Mining Laser Power | Increase / Decrease Mining Laser Power |  |  |  | press |
| `v_mining_use_consumable1` | Activate Mining Module (Slot 1) | Activate a Mining Module | lalt+1 |  |  | press |
| `v_mining_use_consumable2` | Activate Mining Module (Slot 2) | Activate a Mining Module | lalt+2 |  |  | press |
| `v_mining_use_consumable3` | Activate Mining Module (Slot 3) | Activate a Mining Module | lalt+3 |  |  | press |
| `v_mining_use_permanent_modifier` | Toggle Laser Beam (High / low) | Activate a Mining Module | lalt+4 |  |  | press |
| `v_jettison_volatile_cargo` | Jettison Cargo | Jettison Cargo | lalt+j |  |  | press |

## spaceship_salvage

*In-game group: Vehicles - Salvage*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `tractor_beam_vehicle_increase_distance` | Tractor Beam Vehicle- Increase Distance | Increases the target distance for an object controlled with the Vehicle Tractor Beam. | mwheel_up |  | shoulderr | press |
| `tractor_beam_vehicle_decrease_distance` | Tractor Beam Vehicle - Decrease Distance | Decreases the target distance for an object controlled with the Vehicle Tractor Beam. | mwheel_down |  | shoulderl | press |
| `v_salvage_toggle_fire_focused` | Toggle Fire Focused | Toggle firing the Focused salvage tools | mouse1 | button1 | shoulderr | smart_toggle |
| `v_salvage_toggle_fire_left` | Toggle Fire Left | Toggle firing the Left salvage tool | ralt+a |  |  | smart_toggle |
| `v_salvage_toggle_fire_right` | Toggle Fire Right | Toggle firing the Right salvage tool | ralt+d |  |  | smart_toggle |
| `v_salvage_toggle_fire_fracture` | Toggle Fire Fracture | Toggle firing the Fracturing tool | ralt+w |  |  | smart_toggle |
| `v_salvage_toggle_fire_disintegrate` | Toggle Fire Disintegrate | Toggle firing the Disintegration tool | ralt+s |  |  | smart_toggle |
| `v_salvage_toggle_gimbal_mode` | Salvage Mode Gimbal (Toggle) | Toggle between gimbled and fixed salvage targeting modes. | g |  | b | press |
| `v_salvage_reset_gimbal` | Salvage Mode Gimbal Reset |  | lalt+g |  |  |  |
| `v_salvage_increase_beam_spacing` | Increase Beam Spacing | Increase the spacing between the Vulture's two salvage heads. |  |  |  | press |
| `v_salvage_decrease_beam_spacing` | Decrease Beam Spacing | Decrease the spacing between the Vulture's two salvage heads. |  |  |  | press |
| `v_salvage_beam_spacing_rel` | Relative Beam Spacing | Adjust the relative spacing between the Vulture's two salvage heads. | maxis_z |  |  |  |
| `v_salvage_beam_spacing_abs` | Absolute Beam Spacing | Adjust the absolute spacing between the Vulture's two salvage heads. |  |  |  |  |
| `v_salvage_toggle_beam_spacing_axis` | Salvage Beam Axis (Toggle) | Set the orientation axis of the salvage beam to vertical or horizontal. | lalt+mouse2 |  |  |  |
| `v_salvage_cycle_modifiers_focused` | Cycle Focused Salvage Modifiers | Cycle through available modifiers on the Focused salvage head(s) | mouse2 |  |  |  |
| `v_salvage_cycle_modifiers_left` | Cycle Left Salvage Modifiers | Cycle through available modifiers on the left salvage head or salvage turret. |  |  |  |  |
| `v_salvage_cycle_modifiers_right` | Cycle Right Salvage Modifiers | Cycle through available modifiers on the right salvage head or salvage turret. |  |  |  |  |
| `v_salvage_cycle_modifiers_structural` | Cycle Structural Salvage Modes | Cycle through available modes on the Structural Salvage tool. |  |  |  |  |
| `v_salvage_focus_all_heads` | Focus all salvage heads | Focus all salvage heads | lalt+s |  |  |  |
| `v_salvage_focus_left` | Focus left salvage head | Focus left salvage head | lalt+a |  |  |  |
| `v_salvage_focus_right` | Focus right salvage head | Focus right salvage head | lalt+d |  |  |  |
| `v_salvage_focus_fracture` | Focus Fracture tool | Focus Fracture tool | lalt+w |  |  |  |
| `v_salvage_focus_disintegrate` | Focus Disintegration tool | Focus Disintegration tool |  |  |  |  |
| `v_salvage_nudge_up__left` | Nudge left salvage tool up | Nudge left salvage tool up |  |  |  |  |
| `v_salvage_nudge_down__left` | Nudge left salvage tool down | Nudge left salvage tool down |  |  |  |  |
| `v_salvage_nudge_left__left` | Nudge left salvage tool left | Nudge left salvage tool left |  |  |  |  |
| `v_salvage_nudge_right__left` | Nudge left salvage tool right | Nudge left salvage tool right |  |  |  |  |
| `v_salvage_nudge_up__right` | Nudge right salvage tool up | Nudge right salvage tool up |  |  |  |  |
| `v_salvage_nudge_down__right` | Nudge right salvage tool down | Nudge right salvage tool down |  |  |  |  |
| `v_salvage_nudge_left__right` | Nudge right salvage tool left | Nudge right salvage tool left |  |  |  |  |
| `v_salvage_nudge_right__right` | Nudge right salvage tool right | Nudge right salvage tool right |  |  |  |  |

## turret_movement

*In-game group: Turret Movement*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `turret_pitch_up` | Pitch up |  |  |  |  | press+release |
| `turret_pitch_down` | Pitch down |  |  |  |  | press+release |
| `turret_pitch` | Pitch |  |  | y | thumbry |  |
| `turret_pitch_mouse` | Pitch |  | maxis_y |  |  |  |
| `turret_yaw_left` | Yaw left |  |  |  |  | press+release |
| `turret_yaw_right` | Yaw right |  |  |  |  | press+release |
| `turret_yaw` | Yaw |  |  | x | thumbrx |  |
| `turret_yaw_mouse` | Yaw |  | maxis_x |  |  |  |
| `turret_toggle_mouse_mode` | Toggle Turret Mouse Movement (VJoy, FPS style) | Enables / Disables relative mouse mode for turrets | q |  |  | smart_toggle |
| `turret_mouse_mode_cycle` | Turret Mouse Mode - Cycle Modes |  | q |  |  | press |
| `turret_mouse_mode_set_vjoy` | Turret Mouse Mode - VJoy Dragging |  |  |  |  | press |
| `turret_mouse_mode_set_1to1` | Turret Mouse Mode - Relative Dragging |  |  |  |  | press |
| `turret_mouse_mode_set_pointer` | Turret Mouse Mode - Pointer |  |  |  |  | press |
| `turret_remote_exit` | Exit Remote Turret |  | y |  | shoulderl+b | press+hold+release |
| `turret_gyromode` | Turret Gyro Stabilization (Toggle) | Turret Gyro Stabilization (Toggle) | e |  |  | press |
| `turret_remote_cycle_next` | Next Remote Turret |  | d |  |  | press |
| `turret_remote_cycle_prev` | Previous Remote Turret |  | a |  |  | press |

## turret_advanced

*In-game group: Turret Advanced*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `turret_esp_toggle` | Turret E.S.P. Toggle On / Off | Enables / Disables Turret E.S.P. |  |  |  | press |
| `turret_esp_hold` | Turret E.S.P. - Enable Temporarily (Hold) |  |  |  |  | hold |
| `turret_recenter` | Recenter Turret (Hold) |  | c |  |  | hold_no_retrigger |
| `turret_limiter_toggle` | Turret - Speed Limiter - On/Off (Hold/Toggle) | Toggles the limiter for the rotational turret speed |  |  |  | smart_toggle |
| `turret_limiter_rel` | Turret - Speed Limiter (rel) |  | lalt+maxis_z |  |  |  |
| `turret_limiter_rel_increase` | Turret - Speed Limiter - Increase (rel) | Increases the speed of the turret. |  |  |  | all |
| `turret_limiter_rel_decrease` | Turret - Speed Limiter - Decrease (rel) | Decreases the speed of the turret. |  |  |  | all |
| `turret_limiter_abs` | Turret - Speed Limiter (abs) |  |  |  |  |  |
| `turret_change_position` | Change Turret Position |  | s |  |  | press |

## spaceship_weapons

*In-game group: Vehicles - Weapons*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_weapon_gimbals_state_toggle` | Gimbal State - Toggle Locked / Unlocked |  | g |  |  | tap |
| `v_weapon_gimbals_state_set_locked` | Gimbal State - Set Locked |  |  |  |  | press |
| `v_weapon_gimbals_state_set_unlocked` | Gimbal State - Set Unlocked |  |  |  |  | press |
| `v_weapon_gimbals_unlocked_cycle_source` | Gimbal State - Unlocked - Cycle Source (VJoy / View) |  |  |  |  | press |
| `v_weapon_aim_type_cycle` | Aim Mode - Cycle |  | ralt+g |  |  | tap |
| `v_weapon_aim_type_set_pip_aiming` | Aim Mode - Set to PIP Aiming |  |  |  |  | press |
| `v_weapon_aim_type_set_painting` | Aim Mode - Set to Painting |  |  |  |  | press |
| `v_weapon_aim_type_set_auto` | Aim Mode - Set to Automatic |  |  |  |  | press |
| `v_weapon_staggered_fire_toggle` | Staggered Fire - Toggle On / Off |  |  |  |  | tap |
| `v_weapon_staggered_fire_on` | Staggered Fire - On |  |  |  |  | press |
| `v_weapon_staggered_fire_off` | Staggered Fire - Off |  |  |  |  | press |
| `v_weapon_suppress_aim_assists_hold` | Suppress Aim Assists (Hold) |  |  |  |  | hold |
| `v_weapon_pip_toggle_lead_lag` | Toggle Lead / Lag PIPs |  |  |  |  | tap |
| `v_weapon_pip_set_lag` | Set Lag PIPs |  |  |  |  | tap |
| `v_weapon_pip_set_lead` | Set Lead PIPs |  |  |  |  | tap |
| `v_weapon_pip_combination_type_toggle` | PIP Combination Type: Toggle |  |  |  |  | tap |
| `v_weapon_pip_combination_type_set_single` | PIP Combination Type: Set One PIP Per Weapon |  |  |  |  | tap |
| `v_weapon_pip_combination_type_set_combined_weapon_group` | PIP Combination Type: Set One PIP Per Weapon Type |  |  |  |  | tap |
| `v_weapon_pip_prec_line_toggle` | PIP Precision Lines Toggle | PIP Precision Lines Toggle |  |  |  | tap |
| `v_weapon_pip_prec_line_on` | PIP Precision Lines On | PIP Precision Lines On |  |  |  | tap |
| `v_weapon_pip_prec_line_off` | PIP Precision Lines Off | PIP Precision Lines Off |  |  |  | tap |
| `v_weapon_pip_fade_toggle` | PIP Fading Toggle | PIP Fading Toggle |  |  |  | tap |
| `v_weapon_pip_fade_on` | PIP Fading On | PIP Fading On |  |  |  | tap |
| `v_weapon_pip_fade_off` | PIP Fading Off | PIP Fading Off |  |  |  | tap |
| `v_weapon_ui_scale_toggle` | Gunnery UI Magnification Toggle |  |  |  |  | tap |
| `v_weapon_ui_scale_on` | Gunnery UI Magnification On | Gunnery UI Magnification On |  |  |  | tap |
| `v_weapon_ui_scale_off` | Gunnery UI Magnification Off | Gunnery UI Magnification Off |  |  |  | tap |
| `v_weapon_convergence_distance_rel` | Manual Convergence Distance (rel.) | Sets the manual convergence distance on a relative axis |  |  |  |  |
| `v_weapon_convergence_distance_rel_increase` | Manual Convergence Distance - Increase | Increases the Manual Convergence Distance |  |  |  | press |
| `v_weapon_convergence_distance_rel_decrease` | Manual Convergence Distance - Decrease | Decreases the Manual Convergence Distance |  |  |  | press |
| `v_weapon_convergence_distance_abs` | Manual Convergence Distance (abs.) | Manual Convergence Distance (abs.) |  |  |  |  |
| `v_weapon_convergence_distance_set_default` | Manual Convergence Distance - Reset | Resets the Manual Convergence Distance to the default value |  |  |  | press |
| `v_weapon_preset_attack` | Weapon Preset - Fire |  | mouse1 | button1 | triggerr_btn | all |
| `v_weapon_preset_fire_guns0` | Weapon Presets - Fire Guns Group 1 | Weapon Presets - Fire Guns Group 1 |  |  |  | all |
| `v_weapon_preset_fire_guns1` | Weapon Presets - Fire Guns Group 2 | Weapon Presets - Fire Guns Group 2 |  |  |  | all |
| `v_weapon_preset_fire_guns2` | Weapon Presets - Fire Guns Group 3 | Weapon Presets - Fire Guns Group 3 |  |  |  | all |
| `v_weapon_preset_fire_guns3` | Weapon Presets - Fire Guns Group 4 | Weapon Presets - Fire Guns Group 4 |  |  |  | all |
| `v_weapon_preset_next` | Weapon Presets - Next |  | mwheel_down | button1 | triggerr_btn | press |
| `v_weapon_preset_prev` | Weapon Presets - Previous |  | mwheel_up | button1 | triggerr_btn | press |
| `v_weapon_preset_next_overflow` | Weapon Presets - Next (Overflow) | Weapon Presets - Next (Overflow) |  |  |  | press |
| `v_weapon_preset_prev_overflow` | Weapon Presets - Previous (Overflow) | Weapon Presets - Previous (Overflow) |  |  |  | press |
| `v_weapon_preset_guns0` | Weapon Presets - Set Guns Group 1 | Weapon Presets - Set Guns Group 1 |  |  |  | press |
| `v_weapon_preset_guns1` | Weapon Presets - Set Guns Group 2 | Weapon Presets - Set Guns Group 2 |  |  |  | press |
| `v_weapon_preset_guns2` | Weapon Presets - Set Guns Group 3 | Weapon Presets - Set Guns Group 3 |  |  |  | press |
| `v_weapon_preset_guns3` | Weapon Presets - Set Guns Group 4 | Weapon Presets - Set Guns Group 4 |  |  |  | press |
| `v_weapon_preset_emp` | Weapon Presets - Set EMPs | Weapon Presets - Set EMPs |  |  |  | press |
| `v_weapon_preset_qid_jammer` | Weapon Presets - Set Quantum Jammers (short range) | Weapon Presets - Set Quantum Jammers (short range) |  |  |  | press |
| `v_weapon_preset_qid_pulse` | Weapon Presets - Set Quantum Snares / Pulse (long range) | Weapon Presets - Set Quantum Snares / Pulse (long range) |  |  |  | press |
| `v_weapon_preset_qid` | Weapon Presets - Set QIDs | Weapon Presets - Set QIDs |  |  |  | press |

## spaceship_missiles

*In-game group: Vehicles - Missiles*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_weapon_toggle_launch_missile` | Launch Missiles (Tap) |  | mouse1 | button1 | triggerr_btn | press |
| `v_weapon_launch_missile` | Launch Missiles (Hold) |  |  |  |  | delayed_press |
| `v_weapon_cycle_missile_fwd` | Cycle Next Missile Type |  | mwheel_down | button2 | triggerl_btn | press |
| `v_weapon_cycle_missile_back` | Cycle Previous Missile Type |  | mwheel_up |  |  | press |
| `v_weapon_increase_max_missiles` | Increase Number of Armed Missiles |  | g |  |  | tap |
| `v_weapon_decrease_max_missiles` | Decrease Number of Armed Missiles |  |  |  |  | tap |
| `v_weapon_reset_max_missiles` | Reset Number of Armed Missiles |  | lalt+g |  |  | tap |
| `v_weapon_bombing_toggle_desired_impact_point` | Bombs - Toggle Desired Impact Point (Tap) |  | lalt+b |  |  | tap |
| `v_weapon_bombing_toggle_desired_impact_point_hold` | Bombs - Toggle Desired Impact Point (Hold) |  |  |  |  | delayed_press |
| `v_weapon_bombing_hud_range_increase` | Bombs - Increase HUD Range | Increases range by one step in the bomb alignment HUD |  |  |  | tap |
| `v_weapon_bombing_hud_range_decrease` | Bombs - Decrease HUD Range |  |  |  |  | tap |
| `v_weapon_bombing_hud_range_reset` | Bombs - Reset HUD Range | Resets to the default range in the bomb alignment HUD |  |  |  | tap |
| `v_weapon_launch_missile_cinematic` | Enable Cinematic Camera (Toggle) |  |  |  |  | tap |
| `v_weapon_launch_missile_cinematic_hold` | Enable Cinematic Camera (Hold) |  |  |  |  | press+hold+release |

## spaceship_defensive

*In-game group: Vehicles - Shields and Countermeasures*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_weapon_countermeasure_decoy_launch` | Decoy - Launch Burst (tap), Set and Launch Burst (hold) | Launches a decoy countermeasure. | h | button3 | x | press+hold+release |
| `v_weapon_countermeasure_decoy_burst_increase` | Decoy - Increase Burst Size (tap) | Increases the burst size by one. | ralt+h |  |  | press |
| `v_weapon_countermeasure_decoy_burst_decrease` | Decoy - Decrease Burst Size (tap) | Decreases the burst size by one. | lalt+h |  |  | press |
| `v_weapon_countermeasure_decoy_launch_panic` | Decoy - Panic Launch (tap) | Launches a large percentage of the countermeasure magazine. |  |  |  | press |
| `v_weapon_countermeasure_noise_launch` | Noise - Deploy (Tap) | Deploys a noise countermeasure. | j | button5 |  | press |
| `v_shield_raise_level_forward` | Shield raise level front |  |  |  |  | press |
| `v_shield_raise_level_back` | Shield raise level back |  |  |  |  | press |
| `v_shield_raise_level_left` | Shield raise level left |  |  |  |  | press |
| `v_shield_raise_level_right` | Shield raise level right |  |  |  |  | press |
| `v_shield_raise_level_up` | Shield raise level top |  |  |  |  | press |
| `v_shield_raise_level_down` | Shield raise level bottom |  |  |  |  | press |
| `v_shield_reset_level` | Shield reset levels |  |  |  |  | press |

## spaceship_auto_weapons

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_weapon_toggle_ai` | - |  | slash |  |  | press |

## spaceship_power

*In-game group: Flight - Power*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_power_toggle` | Toggle Power - All | Toggle Power - All | u |  |  | press |
| `v_power_set_on` | Set Power On | Set Power On |  |  |  | press |
| `v_power_set_off` | Set Power Off | Set Power Off |  |  |  | press |
| `v_power_toggle_thrusters` | Toggle Power - Thrusters |  | i |  |  | press |
| `v_power_set_thrusters_on` | Set Thrusters Power On |  |  |  |  | press |
| `v_power_set_thrusters_off` | Set Thrusters Power Off | Set Thrusters Power Off |  |  |  | press |
| `v_power_toggle_shields` | Toggle Power - Shields |  | o |  |  | press |
| `v_power_set_shields_on` | Set Shields Power On | Set Shields Power On |  |  |  | press |
| `v_power_set_shields_off` | Set Shields Power Off | Set Shields Power Off |  |  |  | press |
| `v_power_toggle_weapons` | Toggle Power - Weapons |  | p |  |  | press |
| `v_power_set_weapons_on` | Set Weapons Power On | Set Weapons Power On |  |  |  | press |
| `v_power_set_weapons_off` | Set Weapons Power Off | Set Weapons Power Off |  |  |  | press |
| `v_power_throttle_down` | Decrease Throttle |  | f9 |  |  | press+hold |
| `v_power_throttle_min` | Decrease Throttle to Min |  | f9 |  |  | double_tap |
| `v_power_throttle_up` | Increase Throttle |  | f10 |  |  | press+hold |
| `v_power_throttle_max` | Increase Throttle to Max |  | f10 |  |  | double_tap |
| `v_engineering_assignment_engine_increase` | Engines - Increase (Tap) |  | f6 |  |  | tap |
| `v_engineering_assignment_engine_decrease` | Engines - Decrease (Tap) |  | f6+lalt |  |  | tap |
| `v_engineering_assignment_engine_max` | Engines - Set to Max (Hold) |  | f6 |  |  | hold |
| `v_engineering_assignment_engine_min` | Engines - Set to Min (Hold) |  | f6+lalt |  |  | hold |
| `v_engineering_assignment_shields_increase` | Shields - Increase (Tap) |  | f7 |  |  | tap |
| `v_engineering_assignment_shields_decrease` | Shields - Decrease (Tap) |  | f7+lalt |  |  | tap |
| `v_engineering_assignment_shields_max` | Shields - Set to Max (Hold) |  | f7 |  |  | hold |
| `v_engineering_assignment_shields_min` | Shields - Set to Min (Hold) |  | f7+lalt |  |  | hold |
| `v_engineering_assignment_weapons_increase` | Weapons - Increase (Tap) |  | f5 |  |  | tap |
| `v_engineering_assignment_weapons_decrease` | Weapons - Decrease (Tap) |  | f5+lalt |  |  | tap |
| `v_engineering_assignment_weapons_max` | Weapons - Set to Max (Hold) |  | f5 |  |  | hold |
| `v_engineering_assignment_weapons_min` | Weapons - Set to Min (Hold) |  | f5+lalt |  |  | hold |
| `v_engineering_assignment_reset` | Reset Assignments |  | f8 |  |  | press |

## spaceship_hud

*In-game group: Flight - HUD*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_cycle_pitch_ladder_mode` | Cycle Pitch Ladder Mode | Cycles the pitch ladder mode between off, HUD, look direction and mixed. |  |  |  | press |
| `mobiglas` | mobiGlas (Toggle) |  | f1 |  | shoulderl+back | press |
| `toggle_ar_mode` | - |  |  |  |  | press |
| `v_hud_open_scoreboard` | Scoreboard |  | f1 |  | shoulderl+start | all |
| `v_hud_interact_toggle` | - |  |  |  |  | press |
| `v_hud_cycle_mode_fwd` | - |  |  |  |  | press+release |
| `v_hud_cycle_mode_back` | - |  |  |  |  | press+release |
| `v_hud_focused_cycle_mode_fwd` | - |  |  |  |  | press+release |
| `v_hud_focused_cycle_mode_back` | - |  |  |  |  | press+release |
| `v_hud_left_panel_up` | - |  |  |  |  | press+release |
| `v_hud_left_panel_down` | - |  |  |  |  | press+release |
| `v_hud_left_panel_left` | - |  |  |  |  | press+release |
| `v_hud_left_panel_right` | - |  |  |  |  | press+release |
| `v_hud_confirm` | - |  |  |  | a | press+release |
| `v_hud_cancel` | - |  |  |  | b | press+release |
| `v_hud_stick_x` | - |  |  |  |  | press+release |
| `v_hud_stick_y` | - |  |  |  |  | press+release |
| `v_comm_open_chat` | - |  |  |  |  | press+release |
| `v_comm_show_chat` | - |  |  |  |  | press+release |
| `v_comm_open_precanned` | - |  |  |  |  | press+release |
| `v_comm_select_precanned_1` | - |  |  |  |  | press+release |
| `v_comm_select_precanned_2` | - |  |  |  |  | press+release |
| `v_comm_select_precanned_3` | - |  |  |  |  | press+release |
| `v_comm_select_precanned_4` | - |  |  |  |  | press+release |
| `v_comm_select_precanned_5` | - |  |  |  |  | press+release |
| `v_starmap` | Map | Map | f2 |  | shoulderl+back | press |
| `visor_wipe` | Wipe Helmet Visor | Quickly wipe your helmet visor to improve visibility | lalt+x |  |  | press |

## lights_controller

*In-game group: Lights*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_lights` | Headlights (Toggle) |  | l |  |  | press |
| `v_lights_on` | Headlights (Enable) |  |  |  |  | press |
| `v_lights_off` | Headlights (Enable) |  |  |  |  | press |
| `v_toggle_running_lights` | - |  |  |  |  | smart_toggle |
| `v_toggle_cabin_lights` | - |  |  |  |  | smart_toggle |

## vehicle_mobiglas

*In-game group: Vehicle - Mobiglas*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `ui_3d_display_select` | - |  | mouse1 |  |  | tap |
| `ui_3d_display_reorient` | - |  | r |  | thumbr | tap |
| `ui_3d_display_center` | - |  | e, mouse1 |  | thumbl | double_tap_nonblocking |
| `ui_3d_display_decenter` | - |  | mouse2 |  |  | double_tap_nonblocking |
| `ui_3d_display_zoom_out_button` | - |  | np_subtract |  | triggerl_btn | press+hold |
| `ui_3d_display_zoom_in_button` | - |  | np_add |  | triggerr_btn | press+hold |
| `ui_3d_display_zoom_in_analog` | - |  |  |  |  |  |
| `ui_3d_display_zoom_out_analog` | - |  |  |  |  |  |
| `ui_3d_display_zoom_out_wheel` | - |  | mwheel_down |  |  | press |
| `ui_3d_display_zoom_in_wheel` | - |  | mwheel_up |  |  | press |
| `ui_3d_display_pan_toggle` | - |  | mouse2 |  |  | press+hold+release |
| `ui_3d_display_rotate_toggle` | - |  | mouse1 |  |  | press+hold+release |
| `ui_3d_display_zoom_toggle` | - |  | mouse3 |  | triggerr_btn | press+hold+release |
| `ui_3d_display_toggledPanX` | - |  | maxis_x |  |  |  |
| `ui_3d_display_toggledPanY` | - |  | maxis_y |  |  |  |
| `ui_3d_display_toggledYaw` | - |  | maxis_x |  |  |  |
| `ui_3d_display_toggledPitch` | - |  | maxis_y |  |  |  |
| `ui_3d_display_toggledZoom` | - |  | maxis_y |  |  |  |
| `ui_3d_display_nonToggledPanUp` | - |  | w |  | thumbl_up | press+hold |
| `ui_3d_display_nonToggledPanDown` | - |  | s |  | thumbl_down | press+hold |
| `ui_3d_display_nonToggledPanLeft` | - |  | a |  | thumbl_left | press+hold |
| `ui_3d_display_nonToggledPanRight` | - |  | d |  | thumbl_right | press+hold |
| `ui_3d_display_nonToggledYawUp` | - |  | up |  | thumbr_up | press+hold |
| `ui_3d_display_nonToggledYawDown` | - |  | down |  | thumbr_down | press+hold |
| `ui_3d_display_nonToggledPitchLeft` | - |  | left |  | thumbr_left | press+hold |
| `ui_3d_display_nonToggledPitchRight` | - |  | right |  | thumbr_right | press+hold |
| `ui_3d_display_pinMode` | - |  | lctrl |  |  | hold |
| `ui_3d_display_pinSelect` | - |  | mouse1 |  |  | tap |

## stopwatch

*In-game group: Stop Watch*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `stopwatch_reset` | Reset (Long Press) |  |  |  |  |  |
| `stopwatch_trigger` | Start / Pause (Short Press) |  |  |  |  |  |

## player

*In-game group: On Foot - All*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `moveleft` | Move Left |  | a |  |  | hold |
| `moveright` | Move Right |  | d |  |  | hold |
| `moveforward` | Move Forward |  | w |  |  | hold |
| `moveback` | Move Backwards |  | s |  |  | hold |
| `rotateyaw` | - |  | maxis_x |  |  |  |
| `rotatepitch` | - |  | maxis_y |  |  |  |
| `gp_movex` | Move Left / Right |  |  |  | thumblx |  |
| `gp_movey` | Move Forward / Backward |  |  |  | thumbly |  |
| `gp_rotateyaw` | Look (Yaw) |  |  |  | thumbrx |  |
| `gp_rotatepitch` | Look (Pitch) |  |  |  | thumbry |  |
| `jump` | Jump |  | space |  |  | press |
| `jump_hold` | Jump Thrusters - Activate (hold) |  | space |  |  | hold |
| `jump_release` | Jump Thrusters - Release |  | space |  |  | release |
| `crouch` | Crouch |  | c |  |  | hold_toggle |
| `gp_jump` | Jump |  |  |  | a | press |
| `gp_crouch` | Crouch |  |  |  | b | press |
| `prone` | Prone |  | lctrl |  | b | press |
| `sprint` | Sprint |  | lshift |  | thumbl | hold_toggle |
| `walk` | Walk |  |  |  |  | tap |
| `leanleft` | Lean Left |  | q |  | shoulderl+thumbl | hold |
| `leanright` | Lean Right |  | e |  | shoulderl+thumbr | hold |
| `ledgegrab` | Climb Ledges |  | space |  | a | hold |
| `attack1` | Firearm - Attack |  | mouse1 |  | triggerr_btn | all |
| `attackSecondary` | Tool - Secondary Fire |  | mouse2 |  | triggerr_btn | all |
| `melee_AttackLightLeft` | Melee - Attack Light Left |  | mouse1 |  | triggerl_btn | tap |
| `melee_AttackLightRight` | Melee - Attack Light Right |  | mouse2 |  | triggerr_btn | tap |
| `melee_AttackHeavyLeft` | Melee - Attack Heavy Left (Hold) |  | mouse1 |  | triggerl_btn | delayed_press |
| `melee_AttackHeavyRight` | Melee - Attack Heavy Right (Hold) |  | mouse2 |  | triggerr_btn | delayed_press |
| `melee_block` | Melee - Block (Hold) |  | mouse1_2 |  | triggerl_r_btn | hold |
| `melee_AttackSyringeStab` | Medical Pen - Inject Other |  | mouse2 |  | triggerr_btn | tap |
| `melee_dodgeLeft` | Dodge left |  | a |  | shoulderl+thumbl_left | double_tap_nonblocking |
| `melee_dodgeRight` | Dodge Right |  | d |  | shoulderl+thumbl_right | double_tap_nonblocking |
| `melee_dodgeBack` | Dodge Back |  | s |  | shoulderl+thumbl_down | double_tap_nonblocking |
| `restrain` | - |  |  |  |  | tap |
| `weapon_melee` | Melee - Attack (Ranged Weapon + Takedowns) |  | mouse3 |  | thumbr | delayed_press |
| `takedown_nonLethal` | Melee - Attack (Ranged Weapon + Takedowns) |  | mouse3 |  | thumbr | delayed_press |
| `takedown_lethal` | - |  | mouse3 |  | thumbr | tap |
| `throw_overhand` | Throw - Overarm & Two-Handed |  | mouse1 |  | a | hold |
| `throw_underhand` | Throw - Underarm |  | mouse2 |  | b | hold |
| `zoom` | Aim Down Sight |  | mouse2 |  | triggerl_btn | all |
| `interact_with_scope` | Interact With Scope (ADS) | Interact With Scope (ADS) | lshift |  | dpad_up | tap |
| `toggle_lowered` | Weapon Stance (Toggle) |  | lalt+r |  |  | tap |
| `select_primary_pit` | Select Primary Weapon |  | 1 |  |  | tap |
| `select_secondary_pit` | Select Secondary Weapon |  | 2 |  | dpad_left | tap |
| `select_sidearm_pit` | Select Sidearm |  | 3 |  | dpad_right | tap |
| `select_meleeweapon_pit` | Select Melee | Select Melee | v |  | shoulderl+dpad_right | tap |
| `select_gadget_pit` | Select Gadget |  | 5 |  | dpad_down | tap |
| `selectUnarmedCombat` | Unarmed Combat |  | 6 |  | shoulderl+dpad_left | tap |
| `nextitem` | - |  |  |  |  | press |
| `prevItem` | - |  |  |  |  | press |
| `nextweapon` | Next Weapon |  |  |  |  | press |
| `prevweapon` | Previous Weapon |  |  |  |  | press |
| `reload` | Reload |  | r |  | x | tap |
| `reloadSecondary` | Reload Secondary Fire |  | lalt+b |  |  | tap |
| `ammoRepool` | Repool Ammunition |  | lalt+1 |  |  | press |
| `holster` | Holster Weapon |  | r |  | x | delayed_press_medium |
| `drop` | Drop Item | Drop Item |  |  |  | press |
| `inspect` | Inspect Item | Inspect Item |  |  | dpad_left | tap |
| `customize` | Customize Weapon | Customize Weapon | j |  | shoulderl+x | tap |
| `stabilize` | Hold Breath (ADS) |  | lshift |  | thumbl | hold |
| `weapon_auxiliary_action` | FPS Underbarrel Attachment Action | ui_CIFPSAuxiliaryWeaponActionDesc | u |  | shoulderl+dpad_left | press |
| `weapon_change_firemode` | Change Fire Mode |  | b |  | shoulderl+dpad_up | press |
| `weapon_zeroing_decrease` | Weapon Zeroing Decrease | Adjust the weapon scope to accommodate a closer target distance into sighting. | pgdn |  |  | press |
| `weapon_zeroing_increase` | Weapon Zeroing Increase / Auto | Adjust the weapon scope to accommodate a farther target distance into sighting. | pgup |  |  | press |
| `fixed_speed_increment` | Default Movement Speed Increase |  | mwheel_up |  |  | press |
| `fixed_speed_decrement` | Default Movement Speed Decrease |  | mwheel_down |  |  | press |
| `use` | - |  | e |  | a | press+release |
| `useAttachmentBottom` | - |  |  |  |  | all |
| `useAttachmentTop` | - |  |  |  |  | all |
| `downedRevivalRequest` | Request Rescue (while Incapacitated) |  | m |  |  | delayed_hold_long |
| `toggle_flashlight` | Flashlight (Toggle) |  | t |  | shoulderl+dpad_down | press |
| `combathealtarget` | - |  |  |  |  | delayed_hold |
| `toggleEquipHelmet` | Toggle Equip Helmet | Toggle Equip Helmet | ralt+h |  |  | tap |
| `toggleAttachHelmet` | Helmet (Equip) | Toggle Equip Helmet | lalt+h |  |  | tap |
| `toggleHelmetState` | Default Movement Speed Increase |  |  |  |  | press |
| `visor_next_mode` | - |  |  |  |  | press |
| `visor_prev_mode` | - |  |  |  |  | press |
| `visor_wipe` | Wipe Helmet Visor | Quickly wipe your helmet visor to improve visibility | lalt+x |  |  | press |
| `selectitem` | - |  | mouse1 |  | a | press |
| `cancelselect` | - |  | mouse2 |  | b | press |
| `thirdperson` | Third Person View (Toggle) |  | f4 |  | shoulderl+y | tap |
| `toggle_cursor_input` | - |  | f11 |  |  | press |
| `free_thirdperson_camera` | Free View Camera (Hold) | Holding allows free view camera in third person | z |  |  | hold |
| `pan_thirdperson_up` | - |  | up |  |  | press |
| `pan_thirdperson_down` | - |  | down |  |  | press |
| `zoom_out` | Zoom Out |  | mwheel_down |  |  | press |
| `zoom_in` | Zoom In |  | mwheel_up |  |  | press |
| `break_conversation_effects` | - |  |  |  |  | press+release |
| `hmd_rotateyaw` | - |  | HMD_Yaw |  |  |  |
| `hmd_rotatepitch` | - |  | HMD_Pitch |  |  |  |
| `hmd_rotateroll` | - |  | HMD_Roll |  |  |  |
| `mobiglas` | mobiGlas (Toggle) |  | f1 |  | shoulderl+back | press |
| `ship_recall` | Recall Last Vehicle | Activate ship recall on the last flying vehicle used |  |  |  | press |
| `pl_hud_open_scoreboard` | Scoreboard |  | f1 |  | shoulderl+start |  |
| `pl_hud_confirm` | - |  | enter |  | a | press |
| `toggle_ar_mode` | - |  |  |  |  | press |
| `ar_mode_scroll_action_up` | - |  | mwheel_up |  | dpad_up | press |
| `ar_mode_scroll_action_down` | - |  | mwheel_down |  | dpad_down | press |
| `shop_camera_zoom_in` | - |  | mwheel_up |  | triggerl_btn | press+hold |
| `shop_camera_zoom_out` | - |  | mwheel_down |  | triggerr_btn | press+hold |
| `shop_camera_mouseyaw` | - |  | maxis_x |  |  |  |
| `shop_camera_mousepitch` | - |  | maxis_y |  |  |  |
| `spectate_enterpuremode` | - |  |  |  |  | delayed_press |
| `dismiss_corpse_marker` | Dismiss Corpse Marker |  |  |  |  | press |
| `consume` | Firearm - Attack |  | mouse1 |  | triggerr_btn | hold |
| `ui_3d_display_select` | - |  | mouse1 |  |  | tap |
| `ui_3d_display_reorient` | - |  | r |  | thumbr | tap |
| `ui_3d_display_center` | - |  | e, mouse1 |  | thumbl | double_tap_nonblocking |
| `ui_3d_display_decenter` | - |  | mouse2 |  |  | double_tap_nonblocking |
| `ui_3d_display_zoom_out_button` | - |  | np_subtract |  | triggerl_btn | press+hold |
| `ui_3d_display_zoom_in_button` | - |  | np_add |  | triggerr_btn | press+hold |
| `ui_3d_display_zoom_in_analog` | - |  |  |  |  |  |
| `ui_3d_display_zoom_out_analog` | - |  |  |  |  |  |
| `ui_3d_display_zoom_out_wheel` | - |  | mwheel_down |  |  | press |
| `ui_3d_display_zoom_in_wheel` | - |  | mwheel_up |  |  | press |
| `ui_3d_display_pan_toggle` | - |  | mouse2 |  |  | press+hold+release |
| `ui_3d_display_rotate_toggle` | - |  | mouse1 |  |  | press+hold+release |
| `ui_3d_display_zoom_toggle` | - |  | mouse3 |  | triggerr_btn | press+hold+release |
| `ui_3d_display_toggledPanX` | - |  | maxis_x |  |  |  |
| `ui_3d_display_toggledPanY` | - |  | maxis_y |  |  |  |
| `ui_3d_display_toggledYaw` | - |  | maxis_x |  |  |  |
| `ui_3d_display_toggledPitch` | - |  | maxis_y |  |  |  |
| `ui_3d_display_toggledZoom` | - |  | maxis_y |  |  |  |
| `ui_3d_display_nonToggledPanUp` | - |  | w |  | thumbl_up | press+hold |
| `ui_3d_display_nonToggledPanDown` | - |  | s |  | thumbl_down | press+hold |
| `ui_3d_display_nonToggledPanLeft` | - |  | a |  | thumbl_left | press+hold |
| `ui_3d_display_nonToggledPanRight` | - |  | d |  | thumbl_right | press+hold |
| `ui_3d_display_nonToggledYawUp` | - |  | up |  | thumbr_up | press+hold |
| `ui_3d_display_nonToggledYawDown` | - |  | down |  | thumbr_down | press+hold |
| `ui_3d_display_nonToggledPitchLeft` | - |  | left |  | thumbr_left | press+hold |
| `ui_3d_display_nonToggledPitchRight` | - |  | right |  | thumbr_right | press+hold |
| `ui_3d_display_pinMode` | - |  | lctrl |  |  | hold |
| `ui_3d_display_pinSelect` | - |  | mouse1 |  |  | tap |
| `port_modification_select` | Port Modification Interact |  | mouse1 |  | a | press |
| `v_starmap` | Map | Map | f2 |  | shoulderl+back | press |
| `force_respawn` | Force Re-spawn (E.V.A. / On Foot) |  | backspace |  |  | delayed_press_medium |
| `pc_conversation_option1` | - |  | 1 |  |  | all |
| `pc_conversation_option2` | - |  | 2 |  |  | all |
| `pc_conversation_option3` | - |  | 3 |  |  | all |
| `pc_conversation_option4` | - |  | 4 |  |  | all |
| `pc_conversation_option5` | - |  | 5 |  |  | all |
| `pc_conversation_option_up` | - |  | mwheel_up |  |  | all |
| `pc_conversation_option_down` | - |  | mwheel_down |  |  | all |
| `pc_conversation_option_select` | - |  | mouse1 |  |  | all |

## prone

*In-game group: On Foot - All*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `prone_rollleft` | Roll Left (while Prone) |  | q |  | shoulderl+thumbl_left |  |
| `prone_rollright` | Roll Right (while Prone) |  | e |  | shoulderl+thumbl_right |  |

## mapui

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `mapui_pan_left` | - |  | a |  |  | hold |
| `mapui_pan_right` | - |  | d |  |  | hold |
| `mapui_pan_forward` | - |  | w |  |  | hold |
| `mapui_pan_back` | - |  | s |  |  | hold |
| `mapui_pan_up` | - |  | space |  |  | press+release |
| `mapui_pan_down` | - |  | lctrl |  |  | press+release |
| `mapui_cycle_section_forward` | - |  | e |  |  | press+release |
| `mapui_cycle_section_backward` | - |  | q |  |  | press+release |
| `mapui_cycle_zone_forward` | - |  | lshift+e |  |  | press+release |
| `mapui_cycle_zone_backward` | - |  | lshift+q |  |  | press+release |
| `mapui_action_planroute` | - |  | r |  |  | press+release |
| `mapui_action_clearroute` | - |  | c |  |  | press+release |
| `mapui_action_togglepin` | - |  | t |  |  | press+release |
| `mapui_action_mylocation` | - |  | 2 |  |  | press+release |
| `mapui_action_toggle_view_entire_zone` | - |  | z |  |  | press+release |
| `mapui_action_toggleQTActions` | - |  | lshift |  |  | hold |
| `mapui_action_goto_selection` | - |  | 3 |  |  | press+release |
| `mapui_action_step_back` | - |  | 4 |  |  | press+release |
| `mapui_action_goto_localmap` | - |  | 1 |  |  | press+release |

## hacking

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `hacking_minigame_debug_toggle_command_input` | - |  | rshift |  |  | double_tap |
| `hacking_minigame_debug_mouse_x` | - |  | maxis_x |  |  |  |
| `hacking_minigame_debug_mouse_y` | - |  | maxis_y |  |  |  |
| `hacking_minigame_mouse_lmb` | - |  | mouse1 |  |  | hold |
| `hacking_minigame_mouse_rmb` | - |  | mouse2 |  |  | press |
| `hacking_minigame_abort` | - |  | y |  |  | press |
| `hacking_minigame_help_window_toggle` | - |  | h |  |  | press |
| `hacking_minigame_camera_control` | - |  | mouse3 |  |  | hold |
| `hacking_minigame_camera_x` | - |  | maxis_x |  |  |  |
| `hacking_minigame_camera_y` | - |  | maxis_y |  |  |  |
| `hacking_minigame_movement_up` | - |  | w |  |  | hold |
| `hacking_minigame_movement_down` | - |  | s |  |  | hold |
| `hacking_minigame_movement_left` | - |  | a |  |  | hold |
| `hacking_minigame_movement_right` | - |  | d |  |  | hold |
| `hacking_minigame_swap_rotate_cw` | - |  | mwheel_down |  |  | press |
| `hacking_minigame_swap_rotate_ccw` | - |  | mwheel_up |  |  | press |
| `hacking_minigame_ability_inject` | - |  | f |  |  | press |
| `hacking_minigame_ability_ping` | - |  | tab |  |  | delayed_press |
| `hacking_minigame_ability_slowdown` | - |  | q |  |  | press |
| `hacking_minigame_ability_swap` | - |  | r |  |  | press |
| `hacking_minigame_ability_wraparound` | - |  | e |  |  | press |
| `hacking_minigame_cycle_input_mode` | - |  | i |  |  | press |

## tractor_beam

*In-game group: On Foot - All*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `tractor_beam_increase_distance` | Tractor Beam - Increase Distance | Increases the target distance for an object controlled with the Tractor Beam. | mwheel_up | button3 | shoulderr | press |
| `tractor_beam_decrease_distance` | Tractor Beam - Decrease Distance | Decreases the target distance for an object controlled with the Tractor Beam. | mwheel_down | button4 | shoulderl | press |
| `tractor_beam_rotate` | - |  | r |  |  | hold |
| `tractor_beam_rotate_x` | - |  | maxis_x |  |  |  |
| `tractor_beam_rotate_y` | - |  | maxis_y |  |  |  |
| `tractor_beam_rotate_z_up` | - |  | mwheel_up |  |  | press |
| `tractor_beam_rotate_z_down` | - |  | mwheel_down |  |  | press |
| `tractor_beam_detach` | - |  | b |  |  | press |
| `tractor_beam_throw` | - |  | mouse2 |  |  | all |
| `tractor_beam_reset_rotation` | - |  | mouse3 |  |  | press |

## mining

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `weapon_change_mining_throttle` | - |  | lalt+maxis_z | button3 |  | press |

## incapacitated

*In-game group: On Foot - All*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `incapacitatedRespawn` | Regen (while Incapacitated) |  | backspace |  | x | delayed_hold_long |

## zero_gravity_eva

*In-game group: E.V.A - All*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `eva_view_yaw_left` | View Left |  |  |  |  | hold |
| `eva_view_yaw_right` | View Right |  |  |  |  | hold |
| `eva_view_yaw` | View Left/Right |  |  |  | thumbrx |  |
| `eva_view_yaw_mouse` | View Left/Right |  | maxis_x |  |  |  |
| `eva_view_pitch_up` | View Up |  |  |  |  | hold |
| `eva_view_pitch_down` | View Down |  |  |  |  | hold |
| `eva_view_pitch` | View Up/Down |  |  |  | thumbry |  |
| `eva_view_pitch_mouse` | View Up/Down |  | maxis_y |  |  |  |
| `eva_roll_left` | Roll Left |  | q |  |  | hold |
| `eva_roll_right` | Roll Right |  | e |  |  | hold |
| `eva_roll` | Roll Left/Right |  |  |  | shoulderl+thumblx |  |
| `eva_strafe_up` | Strafe Up |  | space |  |  | hold |
| `eva_strafe_down` | Strafe Down |  | lctrl |  |  | hold |
| `eva_strafe_vertical` | Strafe Up/Down |  |  |  | shoulderl+thumbry |  |
| `eva_strafe_left` | Strafe Left |  | a |  |  | hold |
| `eva_strafe_right` | Strafe Right |  | d |  |  | hold |
| `eva_strafe_lateral` | Strafe Left/Right |  |  |  | thumblx |  |
| `eva_strafe_forward` | Strafe Forward |  | w |  |  | hold |
| `eva_strafe_back` | Strafe Backward |  | s |  |  | hold |
| `eva_strafe_longitudinal` | Strafe Forward/Backward |  |  |  | thumbly |  |
| `eva_brake` | Brake |  | x |  |  | hold |
| `eva_boost` | Boost |  | lshift |  | thumbl | hold |
| `eva_toggle_headlook_mode` | Freelook (Hold) |  | z |  |  | hold |

## zero_gravity_traversal

*In-game group: E.V.A. - Zero-G Traversal*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `zgt_launch` | Launch from Surface |  | space |  |  | hold |
| `zgt_detach` | Detach from Surface |  | y |  | shoulderl+b | press |
| `zgt_roll_left` | Roll Left |  | q |  |  | press |
| `zgt_roll_right` | Roll Right |  | e |  |  | press |

## vehicle_general

*In-game group: Ground Vehicle - General*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_horn` | Horn |  | space | button8 | dpad_down | press+release |
| `v_view_cycle_fwd` | Cycle camera view |  | f4 |  | shoulderl+y | tap |
| `v_view_option` | - |  |  |  |  | press+release |
| `v_view_zoom_in` | Zoom in (3rd person view) |  | mwheel_up |  |  | press+hold |
| `v_view_zoom_out` | Zoom out (3rd person view) |  | mwheel_down |  |  | press+hold |
| `v_view_yaw_mouse` | Look left / right |  | maxis_x |  |  |  |
| `v_view_pitch_mouse` | Look up / down |  | maxis_y |  |  |  |
| `v_view_yaw` | Look left / right |  |  | x | thumbrx |  |
| `v_view_pitch` | Look up / down |  |  | y | thumbry |  |
| `v_view_freelook_mode` | Freelook (Hold) |  | z |  |  | hold |
| `v_toggle_cursor_input` | - |  | f11 |  |  | tap |
| `v_view_yaw_absolute` | - |  | HMD_Yaw |  |  |  |
| `v_view_pitch_absolute` | - |  | HMD_Pitch |  |  |  |
| `v_view_roll_absolute` | - |  | HMD_Roll |  |  |  |
| `mobiglas` | mobiGlas (Toggle) |  | f1 |  | shoulderl+back | press |
| `v_flightready` | Flight / Systems Ready | Flight / Systems Ready | ralt+r |  | shoulderl+shoulderr | press |
| `v_toggle_all_doors` | Open/Close Doors (Toggle) | Toggle Open/Close Doors |  |  |  | press |
| `v_open_all_doors` | Open All Doors | Open All Doors |  |  |  | press |
| `v_close_all_doors` | Close All Doors | Close All Doors |  |  |  | press |
| `v_toggle_all_doorlocks` | Lock/Unlock Doors (Toggle) | Toggle Lock/Unlock Doors |  |  |  | press |
| `v_lock_all_doors` | Lock All Doors | Lock All Doors |  |  |  | press |
| `v_unlock_all_doors` | Unlock All Doors | Unlock All Doors |  |  |  | press |
| `v_toggle_all_portlocks` | Port Lock Toggle All | Toggle Open/Close Ports | ralt+K |  |  | press |
| `v_lock_all_ports` | Port Lock All |  |  |  |  | press |
| `v_unlock_all_ports` | Port Unlock All |  |  |  |  | press |
| `v_starmap` | Map | Map | f2 |  | shoulderl+back | press |
| `visor_wipe` | Wipe Helmet Visor | Quickly wipe your helmet visor to improve visibility | lalt+x |  |  | press |

## vehicle_driver

*In-game group: Ground Vehicle - Movement*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_move_forward` | Drive Forward |  | w |  |  | press+release |
| `v_move_back` | Drive Backward |  | s |  |  | press+release |
| `v_move` | Drive Forward / Backward |  |  | slider1 | thumbly |  |
| `v_yaw_left` | Turn Left |  | a |  |  | press+release |
| `v_yaw_right` | Turn Right |  | d |  |  | press+release |
| `v_yaw` | Yaw Left / Right (Axis / HOTAS) | Yaw Left / Right (HOTAS) |  | x | thumblx |  |
| `v_yaw_mouse` | Yaw Left / Right (Mouse) | Yaw Left / Right (Mouse) |  |  |  |  |
| `v_pitch_up` | Ground Vehicles - Pitch Up |  |  |  |  | press+release |
| `v_pitch_down` | Ground Vehicles - Pitch Down |  |  |  |  | press+release |
| `v_pitch` | Pitch Up / Down (Axis / HOTAS) | Pitch Up / Down (HOTAS) |  | y | thumblx |  |
| `v_pitch_mouse` | Pitch Up / Down (Mouse) | Pitch Up / Down (Mouse) |  |  |  |  |
| `v_brake` | Brake |  | x | button7 | shoulderl+thumbr | hold |
| `v_view_dynamic_zoom_rel` | Dynamic Zoom In and Out (rel.) |  |  |  |  |  |
| `v_view_dynamic_zoom_rel_in` | Dynamic Zoom In (rel.) |  |  |  |  | all |
| `v_view_dynamic_zoom_rel_out` | Dynamic Zoom Out (rel.) |  |  |  |  | all |
| `v_view_dynamic_zoom_abs` | Dynamic Zoom In and Out (abs.) | Axis assignment for dynamic zoom |  |  |  |  |
| `v_view_dynamic_zoom_abs_toggle` | Dynamic Zoom Toggle (abs.) | Holds the dynamic zoom as long as the button is held |  |  |  | hold |
| `v_boost` | Boost |  | lshift | button8 | thumbl | all |
| `v_lock_rotation` | Lock Pitch / Yaw Movement (Toggle / Hold) | While active no rotational inputs are allowed to your ship. This is useful for arresting movement when you lost control using a mouse. | rshift |  |  | smart_toggle |
| `v_mgv_switch_brake_on_idle` | Toggle Auto Braking On Idle |  | c |  |  | press |

## debug

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `godmode` | - |  | f9 |  |  | press |
| `debug_pause` | - |  | pause |  |  | press |
| `pause_and_fly` | - |  | rctrl+p |  |  | press |
| `debug_pause_alt` | - |  | rctrl+o |  |  | press |
| `debug_time_slower` | - |  | rctrl+minus |  |  | press |
| `debug_time_faster` | - |  | rctrl+equals |  |  | press |
| `teleport_to_camera` | - |  | rctrl+t |  |  | press |
| `toggleaidebugdraw` | - |  | f11 |  |  | press |
| `ai_DebugCenterViewAgent` | - |  | np_divide |  |  | press |
| `togglepdrawhelpers` | - |  | f10 |  |  | press |
| `mannequin_debugai` | - |  | np_multiply |  |  | press |
| `pl_result_state_debug_target` | - |  | np_period |  |  | press |
| `mov_advance_all_sequences` | - |  | end |  |  | press |
| `mov_pause_resume_all_sequences` | - |  | home |  |  | press |

## IFCS_controls

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_IFCS_A` | - |  | rctrl+a |  | a | press+release |
| `v_IFCS_B` | - |  | rctrl+b |  | b | press+release |
| `v_IFCS_X` | - |  | rctrl+x |  | x | press+release |
| `v_IFCS_Y` | - |  | rctrl+y |  | y | press+release |

## spectator

*In-game group: Electronic Access - Spectator*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `spectate_next_target` | Spectator Camera Target (Next) |  | mouse2 | button1 | dpad_right | press |
| `spectate_prev_target` | Spectator Camera Target (Previous) |  | mouse1 | button2 | dpad_left | press |
| `spectate_toggle_lock_target` | Spectator Camera Lock Target |  | 1 |  | a | press |
| `spectate_zoom` | Spectator Camera Zoom |  | maxis_z |  |  |  |
| `spectate_zoom_in` | Spectator Camera Zoom In |  | mwheel_up | hat1_up | dpad_up | press+hold |
| `spectate_zoom_out` | Spectator Camera Zoom Out |  | mwheel_down | hat1_down | dpad_down | press+hold |
| `spectate_rotateyaw_mouse` | Spectator Camera Rotate Yaw |  | maxis_x | x |  |  |
| `spectate_rotatepitch_mouse` | Spectator Camera Rotate Pitch |  | maxis_y | y |  |  |
| `spectate_rotateyaw` | Spectator Camera Rotate Yaw |  |  | x | thumbrx |  |
| `spectate_rotatepitch` | Spectator Camera Rotate Pitch |  |  | y | thumbry |  |
| `spectate_toggle_hud` | Spectator Camera HUD (Toggle) |  | b |  | b | press |
| `spectate_gen_nextcamera` | - |  | n |  |  | press |
| `spectate_gen_nextmode` | Spectator Camera Mode (Next) |  | f4 |  | shoulderl+y | press |
| `spectate_gen_prevmode` | Spectator Camera Mode (Previous) |  |  |  |  | press |
| `spectate_moveleft` | - |  | a |  | thumbl_left | hold |
| `spectate_moveright` | - |  | d |  | thumbl_right | hold |
| `spectate_moveforward` | - |  | w |  | thumbl_up | hold |
| `spectate_moveback` | - |  | s |  | thumbl_down | hold |
| `spectate_moveup` | - |  | space |  | shoulderl+thumbr_up | hold |
| `spectate_movedown` | - |  | lctrl |  | shoulderl+thumbr_down | hold |
| `spectate_freecam_sprint` | - |  | lshift |  | thumbl | hold |
| `spectate_toggle_freecam` | - |  | z |  | thumbr | press |
| `spectate_toggle_thirdperson` | - |  | f4 |  | shoulderl+y | press |
| `spectate_roll_left` | - |  | q |  | shoulderl+thumbl_left | hold |
| `spectate_roll_right` | - |  | e |  | shoulderl+thumbl_right | hold |
| `spectate_speed_increment` | - |  | mwheel_up |  |  | press |
| `spectate_speed_decrement` | - |  | mwheel_down |  |  | press |
| `spectate_free_look` | - |  | z |  |  | hold |

## default

*In-game group: Social - General*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `skip_cutscene` | - |  |  |  |  | press |
| `cam_toggle_cinematic` | - |  | backspace |  | shoulderl+back | tap |
| `objectives` | - |  | o |  |  | press+release |
| `toggle_trackview` | - |  | ] |  |  | press |
| `toggle_action_profile` | - |  |  |  |  | press |
| `respawn` | Re-spawn |  | f | button1 | x | all |
| `retry` | - |  | x | button1 | x | press |
| `ready` | - |  | x | button1 | x | press |
| `pl_exit` | Exit seat |  | y |  | shoulderl+b | press+hold |
| `flymode` | - |  | f3 |  |  | press |
| `flymode_strafe_up` | - |  | space |  |  | hold |
| `flymode_strafe_down` | - |  | lctrl |  |  | hold |
| `flymode_roll_left` | - |  | q |  |  | hold |
| `flymode_roll_right` | - |  | e |  |  | hold |
| `ui_toggle_pause` | - |  | escape |  | start | press |
| `ui_click` | - |  | enter |  | a | release |
| `ui_back` | - |  | escape |  | b | press+release |
| `ui_up` | - |  | up |  | dpad_up, thumbr_up | press+hold |
| `ui_down` | - |  | down |  | dpad_down, thumbr_down | press+hold |
| `ui_left` | - |  | left |  | dpad_left, thumbr_left | press+hold |
| `ui_right` | - |  | right |  | dpad_right, thumbr_right | press+hold |
| `ui_select` | - |  | enter | button1 | a | release |
| `ui_secondary_select` | - |  |  | button2 | x | release |
| `ui_radialmenu_pageleft` | - |  | left |  | dpad_left | press+hold |
| `ui_radialmenu_pageright` | - |  | right |  | dpad_right | press+hold |
| `ui_confirm` | - |  |  |  | shoulderr | press+release |
| `ui_reset` | - |  |  |  | x | press+release |
| `ui_skip_video` | - |  | space |  | shoulderr | press+release |
| `ui_hide_hint` | - |  | f | button2 | a | press |
| `ui_primaryTab_increment` | - |  | e |  | shoulderr | press |
| `ui_primaryTab_decrement` | - |  | q |  | shoulderl | press |
| `ui_secondaryTab_increment` | - |  |  |  | triggerr_btn | press |
| `ui_secondaryTab_decrement` | - |  |  |  | triggerl_btn | press |
| `ui_focus_increment` | - |  | tab |  | x | release |
| `ui_focus_decrement` | - |  | lshift+tab |  | y | release |
| `flashui_mouse` | - |  | mouse1, maxis_x, maxis_y, mwheel_up, mwheel_down |  |  |  |
| `flashui_return` | - |  | enter, np_enter | button2 | a | press+release |
| `flashui_backspace` | - |  | backspace | button3 | b | press+release |
| `flashui_spacebar` | - |  | space |  |  | press+release |
| `flashui_tab` | - |  | tab |  | thumbl | press+release |
| `flashui_kp_2` | - |  |  | button7 | x | press+release |
| `flashui_kp_3` | - |  |  | button4 | y | press+release |
| `flashui_kp_4` | - |  |  | button5 | dpad_left | press+release |
| `flashui_kp_7` | - |  |  | button6 | dpad_right | press+release |
| `flashui_up` | - |  | up | hat1_up | dpad_up, thumbr_up | press+hold+release |
| `flashui_down` | - |  | down | hat1_down | dpad_down, thumbr_down | press+hold+release |
| `flashui_left` | - |  | left | hat1_left | dpad_left, thumbr_left | press+hold+release |
| `flashui_right` | - |  | right | hat1_right | dpad_right, thumbr_right | press+hold+release |
| `notification_accept` | Notifications - Accept Prompt | Notifications - Accept Prompt | lbracket |  |  | press |
| `notification_decline` | Notifications - Decline Prompt | Notifications - Decline Prompt | rbracket |  |  | press |
| `toggle_contact` | CommLink App (Toggle) |  | f11 |  |  | press |
| `toggle_chat` | Chat Window (Toggle) |  | f12 |  |  | press |
| `cycle_chat_lobby` | Cycle Chat Lobby | Press to cycle through subscribed lobbies in chat | tab |  |  | press |
| `focus_on_chat_textinput` | Chat Window Focus |  | enter, np_enter |  |  | press |
| `ui_copy` | - |  | lctrl+c |  |  | press |
| `ui_cut` | - |  | lctrl+x |  |  | press |
| `ui_paste` | - |  | lctrl+v |  |  | press |

## ui_textfield

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `ui_textfield_enter` | - |  | enter, np_enter |  |  | press+release |
| `ui_textfield_backspace` | - |  | backspace |  |  | press+hold+release |
| `ui_textfield_arrow_up` | - |  | up |  |  | press+hold+release |
| `ui_textfield_arrow_down` | - |  | down |  |  | press+hold+release |
| `ui_textfield_arrow_left` | - |  | left |  |  | press+hold+release |
| `ui_textfield_arrow_right` | - |  | right |  |  | press+hold+release |

## ui_notification

*In-game group: Social - Invites*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `ui_notification_accept` | Accept Invite |  | lbracket |  |  | press |
| `ui_notification_decline` | Reject Invite |  | rbracket |  |  | tap |
| `ui_notification_ignore` | Ignore Invite (hold) | Ignore Invite | rbracket |  |  | delayed_hold |

## player_emotes

*In-game group: Social - Emotes*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `emote_cs_forward` | Forward |  | np_5 |  |  | press |
| `emote_cs_left` | Left |  | np_1 |  |  | press |
| `emote_cs_right` | Right |  | np_3 |  |  | press |
| `emote_cs_stop` | Stop |  | np_2 |  |  | press |
| `emote_cs_yes` | Yes |  | np_4 |  |  | press |
| `emote_cs_no` | No |  | np_6 |  |  | press |
| `emote_agree` | Agree |  |  |  |  | press |
| `emote_angry` | Angry |  |  |  |  | press |
| `emote_atease` | At Ease |  |  |  |  | press |
| `emote_attention` | Attention |  |  |  |  | press |
| `emote_blah` | Blah |  |  |  |  | press |
| `emote_bored` | Bored |  |  |  |  | press |
| `emote_bow` | Bow |  |  |  |  | press |
| `emote_burp` | Burp |  |  |  |  | press |
| `emote_cheer` | Cheer |  |  |  |  | press |
| `emote_chicken` | Chicken |  |  |  |  | press |
| `emote_clap` | Clap |  |  |  |  | press |
| `emote_come` | Come |  |  |  |  | press |
| `emote_cry` | Cry |  |  |  |  | press |
| `emote_dance` | Dance |  |  |  |  | press |
| `emote_disagree` | Disagree |  |  |  |  | press |
| `emote_failure` | Failure |  |  |  |  | press |
| `emote_flex` | Flex |  |  |  |  | press |
| `emote_flirt` | Flirt |  |  |  |  | press |
| `emote_gasp` | Gasp |  |  |  |  | press |
| `emote_gloat` | Gloat |  |  |  |  | press |
| `emote_greet` | Greet |  |  |  |  | press |
| `emote_laugh` | Laugh |  |  |  |  | press |
| `emote_launch` | Confirm Launch | Confirms the launch of the vehicle |  |  |  | press |
| `emote_point` | Point |  |  |  |  | press |
| `emote_rude` | Rude |  |  |  |  | press |
| `emote_salute` | Salute |  |  |  |  | press |
| `emote_sit` | Sit |  |  |  |  | press |
| `emote_sleep` | Sleep |  |  |  |  | press |
| `emote_smell` | Smell |  |  |  |  | press |
| `emote_taunt` | Taunt |  |  |  |  | press |
| `emote_threaten` | Threaten |  |  |  |  | press |
| `emote_wait` | Wait |  |  |  |  | press |
| `emote_wave` | Wave |  |  |  |  | press |
| `emote_whistle` | Whistle |  |  |  |  | press |

## player_input_optical_tracking

*In-game group: VOIP, FOIP and Head Tracking*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `hmd_toggle` | [Experimental] VR - Toggle On / Off | Enables/disables VR gameplay | np_divide |  |  | press |
| `hmd_recenter` | [Experimental] VR - Recenter Device | Recenters the VR headset | np_5 |  |  | press |
| `hmd_theater_mode_toggle` | [Experimental] VR - Toggle Theater Mode | Enables / Disables Theater Mode | lalt+np_5 |  |  | press |
| `hmd_lens_display_toggle` | [Experimental] VR - Visor Toggle On / Off | Enables / Disables the Visor |  |  |  | press |
| `headtrack_enabled` | Enable Head Tracking (Toggle) | Switches head tracking on / off (Toggle) | np_divide |  |  | press |
| `headtrack_hold` | Head Tracking (Hold) | Enables head tracking as long as the button is held down |  |  |  | hold |
| `headtrack_recenter_device` | Recenter Head Tracking Device (except TrackIR) | Recenters head tracking device inputs. | np_5 |  |  | press |
| `headtrack_camera_enabled` | Enable / Disable Head Tracking for 3rd Person Camera (Toggle) | Enables or disables head tracking in external cameras. |  |  |  | press |
| `foip_pushtotalk` | VOIP Push To Talk | VOIP Push To Talk | np_add |  |  | hold |
| `foip_pushtotalk_proximity` | VOIP Push To Talk (Proximity only) | VOIP Push To Talk (Proximity only) | lalt+np_add |  |  | hold |
| `foip_viewownplayer` | FOIP Selfie Cam | FOIP Selfie Cam | np_subtract |  |  | delayed_hold |
| `foip_recalibrate` | FOIP Recalibrate | FOIP Recalibrate | np_multiply |  |  | press |
| `foip_cyclechannel` | Cycle through audio channels | Cycle through audio channels | np_period |  |  | press |

## player_choice

*In-game group: Quick Keys, Interactions, and Inner Thought*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `pc_item_primary` | - |  | mouse1 |  |  | press+hold+release |
| `pc_item_secondary` | - |  | mouse2 |  |  | press+hold+release |
| `pc_interaction_mode` | Interaction Mode | Interaction Mode | f | button6 | shoulderr | hold+release |
| `pc_interaction_select` | Activate Inner Thought | Activate Interaction | mouse2 |  |  | press |
| `pc_select` | Activate Inner Thought | Activate Interaction | mouse1 | button1 | a | press+hold+release |
| `pc_focus` | Focus | Focus | mouse3 | button7 | triggerl_btn | tap |
| `pc_zoom_in` | Interaction Mode Zoom In | Interaction Mode Zoom In | mwheel_up |  | triggerl_btn | press |
| `pc_zoom_out` | Interaction Mode Zoom Out | Interaction Mode Zoom Out | mwheel_down |  | triggerr_btn | press |
| `pc_screen_focus_left` | MFD Left |  | a |  | dpad_left | press |
| `pc_screen_focus_right` | MFD Right |  | d |  | dpad_right | press |
| `pc_screen_focus_up` | MFD Up |  | w |  | dpad_up | press |
| `pc_screen_focus_down` | MFD Down |  | s |  | dpad_down | press |
| `pc_personal_thought` | Personal Inner Thought (PIT) | Personal Inner Thought | lalt+f |  | back, back | press |
| `pc_camera_orbit` | Inventory Orbit Camera Mode |  | mouse2 |  |  | hold |
| `pc_personal_back` | Exit |  | np_0 |  | thumbr | press |
| `pc_ui_back` | - |  | mouse2 |  |  | press |
| `pc_pit_inventory` | Toggle Inventory (short press) |  | i |  |  | tap |
| `pc_pit_looting` | Toggle Loot Screen (hold) |  | i |  |  | delayed_press |
| `pc_pit_looting_toggle_view` | Toggle Looting View |  | tab |  |  | press |
| `pc_pit_looting_toggle_weapon_attachments` | Looting - Toggle Weapon Attachments |  | q |  |  | press |
| `pc_pit_item_unstown` | - |  |  |  |  | press |
| `pc_pit_item_drop` | Drop Item |  |  |  |  | press |
| `pc_pit_empty_backpack` | Store All Commodities |  |  |  |  | press |
| `pc_pit_player_actions` | Player Actions - PIT Category |  |  |  |  | press |
| `pc_pit_emotes` | Emotes - PIT Category |  |  |  |  | press |
| `pc_pit_ship_systems` | Ship Systems - PIT Category |  |  |  |  | press |
| `pc_pit_flight_systems` | Flight Systems - PIT Category |  |  |  |  | press |
| `pc_pit_vehicle_actions` | Vehicle Actions - PIT Category |  |  |  |  | press |
| `pc_pit_weapons_systems` | Weapon Systems - PIT Category |  |  |  |  | press |
| `pc_pit_remote_turrets` | Remote Turret - PIT Category |  |  |  |  | press |
| `pc_pit_item_actions` | Item Actions - PIT Category |  |  |  |  | press |
| `pc_pit_weapon_selection` | Weapon Selection - PIT Category |  |  |  |  | press |
| `pc_pit_mobiglas_actions` | Mobiglas Actions - PIT Category |  |  |  |  | press |
| `pc_pit_miningmode_actions` | Mining Mode Actions - PIT Category |  | lalt+m |  |  | press |
| `pc_qs_weapons_pit_primary` | Weapon Select Radial Menu |  | 1 |  | dpad_up | all |
| `pc_qs_weapons_pit_secondary` | Weapon Select Radial Menu |  | 2 |  | dpad_up | all |
| `pc_qs_weapons_pit_sidearm` | Weapon Select Radial Menu |  | 3 |  | dpad_up | all |
| `pc_qs_grenades` | Throwable Select Radial Menu |  | g |  | dpad_right | all |
| `pc_qs_consumables` | Consumable Select Radial Menu |  | 4 |  | dpad_left | all |

## flycam

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `flycam_rotateyaw` | - |  |  |  | thumbrx |  |
| `flycam_rotatepitch` | - |  |  |  | thumbry |  |
| `flycam_rotateyaw_mouse` | - |  | maxis_x |  |  |  |
| `flycam_rotatepitch_mouse` | - |  | maxis_y |  |  |  |
| `flycam_movey` | - |  |  |  | thumbly |  |
| `flycam_movefwd` | - |  | w |  |  | press+release |
| `flycam_moveback` | - |  | s |  |  | press+release |
| `flycam_movex` | - |  |  |  | thumblx |  |
| `flycam_moveright` | - |  | d |  |  | press+release |
| `flycam_moveleft` | - |  | a |  |  | press+release |
| `flycam_movez` | - |  |  |  | shoulderl+thumbry |  |
| `flycam_moveup` | - |  | q |  |  | press+release |
| `flycam_movedown` | - |  | e |  |  | press+release |
| `flycam_speedup` | - |  | up |  | dpad_up | press |
| `flycam_speeddown` | - |  | down |  | dpad_down | press |
| `flycam_turbo` | - |  | space |  | a | press+release |
| `flycam_setpoint` | - |  | z |  | x | press |
| `flycam_play` | - |  | x |  | b | press |
| `flycam_clear` | - |  | c |  | y | press |

## view_director_mode

*In-game group: Camera - Advanced Camera Controls*

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `view_enable_camview_mode` | Advanced Camera Controls Modifier (Hold) |  | f4 |  | shoulderl+y | press+release |
| `view_switch_to_alternative` | Advanced Camera Controls Modifier (Hold) |  | z |  |  | press |
| `view_save_view_1` | Save View 1 |  | np_1 |  |  | delayed_press |
| `view_save_view_2` | Save View 2 |  | np_2 |  |  | delayed_press |
| `view_save_view_3` | Save View 3 |  | np_3 |  |  | delayed_press |
| `view_save_view_4` | Save View 4 |  | np_4 |  |  | delayed_press |
| `view_save_view_5` | Save View 5 |  | np_5 |  |  | delayed_press |
| `view_save_view_6` | Save View 6 |  | np_6 |  |  | delayed_press |
| `view_save_view_7` | Save View 7 |  | np_7 |  |  | delayed_press |
| `view_save_view_8` | Save View 8 |  | np_8 |  |  | delayed_press |
| `view_save_view_9` | Save View 9 |  | np_9 |  |  | delayed_press |
| `view_load_view_1` | Load View 1 |  | np_1 |  |  | tap |
| `view_load_view_2` | Load View 2 |  | np_2 |  |  | tap |
| `view_load_view_3` | Load View 3 |  | np_3 |  |  | tap |
| `view_load_view_4` | Load View 4 |  | np_4 |  |  | tap |
| `view_load_view_5` | Load View 5 |  | np_5 |  |  | tap |
| `view_load_view_6` | Load View 6 |  | np_6 |  |  | tap |
| `view_load_view_7` | Load View 7 |  | np_7 |  |  | tap |
| `view_load_view_8` | Load View 8 |  | np_8 |  |  | tap |
| `view_load_view_9` | Load View 9 |  | np_9 |  |  | tap |
| `view_reset_saved` | Clear Saved View |  | np_0 |  |  | delayed_press |
| `view_move_target_X_pos` | X Offset Positive |  | right |  |  | press+hold |
| `view_move_target_X_neg` | X Offset Negative |  | left |  |  | press+hold |
| `view_move_target_Y_pos` | Y Offset Positive / Spectator Freecam Focal Point Forward |  | up |  |  | press+hold |
| `view_move_target_Y_neg` | Y Offset Negative / Spectator Freecam Focal Point Backward |  | down |  |  | press+hold |
| `view_move_target_Z_pos` | Z Offset Positive |  | pgup |  |  | press+hold |
| `view_move_target_Z_neg` | Z Offset Negative |  | pgdn |  |  | press+hold |
| `view_fov_in` | Increase FoV |  | np_add |  |  | press |
| `view_fov_out` | Decrease FoV |  | np_subtract |  |  | press |
| `view_fstop_in` | Increase DoF |  | home |  |  | press |
| `view_fstop_out` | Decrease DoF |  | end |  |  | press |
| `view_restore_defaults` | Reset Current View |  | np_multiply |  |  | press+release |

## character_customizer

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `character_customizer_yaw` | - |  | maxis_x |  |  |  |
| `character_customizer_pitch` | - |  | maxis_y |  |  |  |
| `character_customizer_gp_yaw` | - |  |  |  | thumblx |  |
| `character_customizer_gp_pitch` | - |  |  |  | thumbly |  |
| `character_customizer_zoom_in` | - |  | mwheel_up |  |  | press+hold |
| `character_customizer_zoom_out` | - |  | mwheel_down |  |  | press+hold |
| `character_customizer_select` | - |  | f, mouse1 |  | a | release |
| `character_customizer_enable_dna_edit` | - |  | mouse1 |  |  | press+release |
| `character_customizer_enable_rotation` | - |  | lshift |  |  | hold |
| `character_customizer_enable_mouse_rotation` | - |  | mouse2 |  | thumbr | hold |
| `character_customizer_library_scroll_up` | - |  | up, mwheel_up |  |  | press+hold+release |
| `character_customizer_library_scroll_down` | - |  | down, mwheel_down |  |  | press+hold+release |
| `character_customizer_edit_dna_pos` | - |  | right |  |  | press+release |
| `character_customizer_edit_dna_neg` | - |  | left |  |  | press+release |
| `character_customizer_yaw_left` | - |  | left |  |  | press+release |
| `character_customizer_yaw_right` | - |  | right |  |  | press+release |
| `character_customizer_pitch_up` | - |  | up |  |  | press+release |
| `character_customizer_pitch_down` | - |  | down |  |  | press+release |
| `character_customizer_step_up` | - |  | e |  |  | press |
| `character_customizer_step_down` | - |  | q |  |  | press |
| `character_customizer_feature_up` | - |  | d |  |  | press |
| `character_customizer_feature_down` | - |  | a |  |  | press |
| `character_customizer_dnamode_up` | - |  | d |  |  | press |
| `character_customizer_dnamode_down` | - |  | a |  |  | press |
| `character_customizer_next_material_region` | - |  | f |  |  | press |
| `character_customizer_toggle_face_tracking` | - |  | space |  | thumbl | press |
| `character_customizer_dnaHandle_select` | - |  |  |  | a | release |
| `character_customizer_dnaHandle_deselect` | - |  |  |  | b | release |

## RemoteRigidEntityController

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `remote_moveForward` | - |  | w |  |  | hold |
| `remote_moveBack` | - |  | s |  |  | hold |
| `remote_moveLeft` | - |  | a |  |  | hold |
| `remote_moveRight` | - |  | d |  |  | hold |
| `remote_moveUp` | - |  | space |  |  | hold |
| `remote_moveDown` | - |  | lctrl |  |  | hold |
| `remote_scaleUp` | - |  | c |  |  | hold |
| `remote_scaleDown` | - |  | z |  |  | hold |
| `remote_rollLeft` | - |  | q |  |  | hold |
| `remote_rollRight` | - |  | e |  |  | hold |
| `remote_rotatePitch` | - |  | maxis_x |  |  |  |
| `remote_rotateYaw` | - |  | maxis_y |  |  |  |
| `remote_switchControl` | - |  | v |  |  | tap |
| `remote_stopControl` | - |  | y |  |  | tap |
| `remote_action1` | - |  | mouse1 |  |  | tap |
| `remote_action2` | - |  | mouse2 |  |  | tap |
| `remote_switchTarget` | - |  | b |  |  | tap |

## server_renderer

| Action | In-Game Label | Description | Keyboard / Mouse | Joystick | Gamepad | Activation |
| --- | --- | --- | --- | --- | --- | --- |
| `v_view_cycle_fwd` | - |  | f4 |  | shoulderl+y | tap |
