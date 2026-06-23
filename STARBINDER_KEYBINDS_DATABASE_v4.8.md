# Star Citizen — Master Keybinding Reference (all available bindings)

> Complete catalogue of every bindable Star Citizen action and what it does.
> **Source:** the master keybind database behind <https://starbinder.space/> (`keybinds.json` + `localisation.json`).
> **Game version:** Star Citizen Alpha **4.8** (starbinder homepage reads "UPDATED FOR 4.8").
> **Actions:** 714 across 39 categories.  **Snapshot:** 2026-06-22.
>
> The `Action` column is the internal action name you put inside `<rebind input="..."/>` `<action name="...">` in your `.xml` profile. The `In-Game Label` is what appears in the Keybindings menu. This is a *reference of what exists* — see `CLAUDE.md` for what is actually bound on the MOZA rig.

## Contents

- [flight - movement](#flight-movement) (100)
- [flight - power](#flight-power) (29)
- [flight - HUD](#flight-hud) (5)
- [quantum travel](#quantum-travel) (1)
- [vehicle](#vehicle) (25)
- [vehicles - seats and operator modes](#vehicles-seats-and-operator-modes) (21)
- [operator modes](#operator-modes) (1)
- [vehicles - weapons](#vehicles-weapons) (49)
- [vehicles - missiles](#vehicles-missiles) (14)
- [vehicles - shields and countermeasures](#vehicles-shields-and-countermeasures) (12)
- [targeting](#targeting) (24)
- [target cycling](#target-cycling) (22)
- [radar](#radar) (1)
- [scanning](#scanning) (3)
- [mining](#mining) (10)
- [salvage](#salvage) (31)
- [vehicles - view](#vehicles-view) (22)
- [camera - advanced camera controls](#camera-advanced-camera-controls) (32)
- [vehicles - multi function displays (mfds)](#vehicles-multi-function-displays-mfds) (55)
- [lights](#lights) (3)
- [nightvision](#nightvision) (3)
- [fuel](#fuel) (2)
- [docking](#docking) (3)
- [cockpit](#cockpit) (13)
- [ground vehicle - general](#ground-vehicle-general) (1)
- [ground vehicle - movement](#ground-vehicle-movement) (6)
- [on foot](#on-foot) (108)
- [quick keys, interactions, and inner thought](#quick-keys-interactions-and-inner-thought) (35)
- [social - general](#social-general) (8)
- [social - emotes](#social-emotes) (40)
- [social - invites](#social-invites) (3)
- [comms/social](#commssocial) (1)
- [voip, foip and head tracking](#voip-foip-and-head-tracking) (9)
- [command module](#command-module) (1)
- [stopwatch](#stopwatch) (2)
- [arena commander](#arena-commander) (13)
- [view](#view) (1)
- [Other](#other) (4)
- [(uncategorised)](#uncategorised) (1)

## flight - movement

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_accel_range_abs` | Acceleration Limiter (abs) | Acceleration Limiter (abs) |
| `v_accel_range_decrement` | Acceleration Limiter - Step Down (tap) | Acceleration Limiter - Step Down (tap) |
| `v_accel_range_down` | Acceleration Limiter - Decrease (hold) | Acceleration Limiter - Decrease (hold) |
| `v_accel_range_increment` | Acceleration Limiter - Step Up (tap) | Acceleration Limiter - Step Up (tap) |
| `v_accel_range_rel` | Acceleration Limiter (rel) | Acceleration Limiter (rel) |
| `v_accel_range_up` | Acceleration Limiter - Increase (hold) | Acceleration Limiter - Increase (hold) |
| `v_afterburner` | Boost |  |
| `v_atc_loading_area_request` | Request Cargo Loading | Request landing access for cargo haulers |
| `v_atc_request` | Request Landing | Contacts Air Traffic Control and other landing services to open/close hangar doors etc. |
| `v_auto_precision_mode_off` | Automatic Precision Mode - Disable |  |
| `v_auto_precision_mode_on` | Automatic Precision Mode - Enable |  |
| `v_auto_precision_mode_toggle` | Automatic Precision Mode - Toggle |  |
| `v_autoland` | Autoland | Activate Autoland - Automatically land when landing gear is out and you're close to a landable pad. |
| `v_deploy_landing_system` | Landing Gear Deploy |  |
| `v_flight_advanced_hud_off` | Advanced HUD - Disable | Advanced HUD - Disable |
| `v_flight_advanced_hud_on` | Advanced HUD - Enable | Advanced HUD - Enable |
| `v_flight_advanced_hud_toggle` | Advanced HUD - Toggle | Advanced HUD - Toggle |
| `v_ifcs_command_off` | Flight Model Command Off |  |
| `v_ifcs_command_on` | Flight Model Command On |  |
| `v_ifcs_command_toggle` | Flight Model Command Toggle |  |
| `v_ifcs_core_off` | Flight Model Core Off |  |
| `v_ifcs_core_on` | Flight Model Core On |  |
| `v_ifcs_core_toggle` | Flight Model Core Toggle |  |
| `v_ifcs_esp_hold` | ESP - Enable Temporarily (Hold) | Enhanced Stick Precision, also known as ESP, dulls the sensitivity curves of the player input on the fly when the crosshair is near the target in order to minimize overshooting and help stay on target. It is similar to aim assist and is primarily intended for joystick users. There is an invisible circle around the player crosshair. When the pip enters the circle, the joystick input is dampened on a curve. This softens jerky or excessive stick movement common for a lot of people when trying to stay aimed at the pip during hard maneuvering at an evasive target. (https://starcitizen.tools/ESP) |
| `v_ifcs_gravity_compensation_off` | Gravity Compensation - Disable |  |
| `v_ifcs_gravity_compensation_on` | Gravity Compensation - Enable |  |
| `v_ifcs_gsafe_off` | G-Force safety off | When on, this will limit your thrust along certain vectors, when necessary, in order to prevent the pilot from passing out from the G-forces. |
| `v_ifcs_gsafe_on` | G-Force safety on | When on, this will limit your thrust along certain vectors, when necessary, in order to prevent the pilot from passing out from the G-forces. |
| `v_ifcs_proximity_assist_off` | Flight Model Proximity Assist Off |  |
| `v_ifcs_proximity_assist_on` | Flight Model Proximity Assist On |  |
| `v_ifcs_proximity_assist_toggle` | Flight Model Proximity Assist Toggle |  |
| `v_ifcs_reset_gmeter_max` | Reset Flight Accelerometer | Resets the max endured Gs for the accelerometer. |
| `v_ifcs_speed_limiter_abs` | Speed Limiter (abs) | Speed Limiter (abs) |
| `v_ifcs_speed_limiter_decrement` | Speed Limiter - Step Down (tap) | Speed Limiter - Step Down (tap) |
| `v_ifcs_speed_limiter_down` | Speed Limiter - Decrease (hold) | Speed Limiter - Decrease (hold) |
| `v_ifcs_speed_limiter_increment` | Speed Limiter - Step Up (tap) | Speed Limiter - Step Up (tap) |
| `v_ifcs_speed_limiter_off` | Speed Limiter - Disable | Speed Limiter - Disable |
| `v_ifcs_speed_limiter_on` | Speed Limiter - Enable | Speed Limiter - Enable |
| `v_ifcs_speed_limiter_rel` | Speed Limiter (rel) | Speed Limiter (rel) |
| `v_ifcs_speed_limiter_toggle` | Speed Limiter - Enable / Disable | Speed Limiter - Enable / Disable |
| `v_ifcs_speed_limiter_up` | Speed Limiter - Increase (hold) | Speed Limiter - Increase (hold) |
| `v_ifcs_stability_off` | Flight Model Stability Off |  |
| `v_ifcs_stability_on` | Flight Model Stability On |  |
| `v_ifcs_stability_toggle` | Flight Model Stability Toggle |  |
| `v_ifcs_throttle_set_normal` | Throttle - Cruise Mode - Disable |  |
| `v_ifcs_throttle_set_sticky` | Throttle - Cruise Mode - Enable |  |
| `v_ifcs_throttle_swap_mode` | Throttle - Cruise Mode - Toggle |  |
| `v_ifcs_toggle_esp` | ESP - Toggle On / Off (Press) | Enhanced Stick Precision, also known as ESP, dulls the sensitivity curves of the player input on the fly when the crosshair is near the target in order to minimize overshooting and help stay on target. It is similar to aim assist and is primarily intended for joystick users. There is an invisible circle around the player crosshair. When the pip enters the circle, the joystick input is dampened on a curve. This softens jerky or excessive stick movement common for a lot of people when trying to stay aimed at the pip during hard maneuvering at an evasive target. (https://starcitizen.tools/ESP) |
| `v_ifcs_toggle_gforce_safety` | G-Force Safety On/Off (Toggle / Hold) | When on, this will limit your thrust along certain vectors, when necessary, in order to prevent the pilot from passing out from the G-forces. |
| `v_ifcs_toggle_gravity_compensation` | Gravity Compensation - Toggle | Gravity Compensation - Toggle |
| `v_ifcs_vector_decoupling_off` | Decoupled Mode Off | Decoupled Off: The ship will automatically counter-thrust based on your vector to feel as though you're flying in atmosphere. Decoupled On: Newtonian(ish) physics are applied withtout counter thrust. |
| `v_ifcs_vector_decoupling_on` | Decoupled Mode On | Decoupled Off: The ship will automatically counter-thrust based on your vector to feel as though you're flying in atmosphere. Decoupled On: Newtonian(ish) physics are applied withtout counter thrust. |
| `v_ifcs_vector_decoupling_toggle` | Decoupled Mode Toggle | Decoupled Off: The ship will automatically counter-thrust based on your vector to feel as though you're flying in atmosphere. Decoupled On: Newtonian(ish) physics are applied withtout counter thrust. |
| `v_lock_rotation` | Lock Pitch / Yaw Movement (Toggle / Hold) | While active no rotational inputs are allowed to your ship. This is useful for arresting movement when you lost control using a mouse. |
| `v_master_mode_cycle` | Master mode cycle |  |
| `v_master_mode_cycle_long` | Cycle Master Mode (Long Press) |  |
| `v_master_mode_set_nav` | Set Master Mode to Nav |  |
| `v_master_mode_set_scm` | Set Master Mode to SCM |  |
| `v_pitch` | Pitch |  |
| `v_pitch_down` | Pitch down |  |
| `v_pitch_mouse` | Pitch |  |
| `v_pitch_up` | Pitch up |  |
| `v_retract_landing_system` | Landing Gear Retract |  |
| `v_roll` | Roll |  |
| `v_roll_left` | Roll left |  |
| `v_roll_mouse` | Roll |  |
| `v_roll_right` | Roll right |  |
| `v_space_brake` | Spacebrake | Reverse thrust on all velocity vectors |
| `v_strafe_back` | Throttle - Decrease |  |
| `v_strafe_down` | Strafe down (abs.) |  |
| `v_strafe_forward` | Throttle - Increase |  |
| `v_strafe_lateral` | Strafe left / right (abs.) |  |
| `v_strafe_left` | Strafe left (abs.) |  |
| `v_strafe_longitudinal` | Throttle - Forward / Back |  |
| `v_strafe_longitudinal_invert` | Throttle - Forward / Back Invert | Inverts Strafe Longitudinal Absolute Axis Half (Neutral - Backward) |
| `v_strafe_right` | Strafe right (abs.) |  |
| `v_strafe_trim_reset_long` | Throttle - Trim - Release (Long Press) | Throttle - Trim - Release (Long Press) |
| `v_strafe_trim_reset_short` | Throttle - Trim - Release (Short Press) | Throttle - Trim - Release (Short Press) |
| `v_strafe_trim_set_100_long` | Throttle - Trim - Set To 100% (Long Press) | Throttle - Trim - Set To 100% (Long Press) |
| `v_strafe_trim_set_100_short` | Throttle - Trim - Set To 100% (Short Press) | Throttle - Trim - Set To 100% (Short Press) |
| `v_strafe_trim_set_50_long` | Throttle - Trim - Set To 50% (Long Press) | Throttle - Trim - Set To 50% (Long Press) |
| `v_strafe_trim_set_50_short` | Throttle - Trim - Set To 50% (Short Press) | Throttle - Trim - Set To 50% (Short Press) |
| `v_strafe_trim_set_long` | Throttle - Trim - Set (Long Press) | Throttle - Trim - Set (Long Press) |
| `v_strafe_trim_set_short` | Throttle - Trim - Set (Short Press) | Throttle - Trim - Set (Short Press) |
| `v_strafe_up` | Strafe up (abs.) |  |
| `v_strafe_vertical` | Strafe up / down (abs.) |  |
| `v_toggle_jump_request` | Jump Drive - Request Jump |  |
| `v_toggle_landing_system` | Landing Gear Toggle |  |
| `v_toggle_relative_mouse_mode` | Cycle mouse mode (VJoy / Relative) | Switches the mouse behavior for ship rotations between a relative (FPS style) and a Vjoy mode. |
| `v_toggle_yaw_roll_swap` | Swap Yaw / Roll (Toggle) |  |
| `v_transform_cycle` | Cycle Configuration | Cycle between the vehicle's expanded and retracted configurations. |
| `v_transform_deploy` | Expand Configuration | Expands the vehicle's configuration. |
| `v_transform_retract` | Retract Configuration | Retracts the vehicle's configuration. |
| `v_vtol_off` | VTOL Off | Ships with VTOL mode will shift thrust or rotate entire thrusters to increase vertical thrust flight mode. VTOL = Vertical Take Off and Landing |
| `v_vtol_on` | VTOL On | Ships with VTOL mode will shift thrust or rotate entire thrusters to increase vertical thrust flight mode. VTOL = Vertical Take Off and Landing |
| `v_vtol_toggle` | VTOL Toggle | Ships with VTOL mode will shift thrust or rotate entire thrusters to increase vertical thrust flight mode. VTOL = Vertical Take Off and Landing |
| `v_yaw` | Yaw |  |
| `v_yaw_left` | Yaw left |  |
| `v_yaw_mouse` | Yaw |  |
| `v_yaw_right` | Yaw right |  |

## flight - power

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_engineering_assignment_engine_decrease` | Power Allocation - Engines - Decrease (Tap) |  |
| `v_engineering_assignment_engine_increase` | Power Allocation - Engines - Increase (Tap) |  |
| `v_engineering_assignment_engine_max` | Power Allocation - Engines - Set To Max (Hold) |  |
| `v_engineering_assignment_engine_min` | Power Allocation - Engines - Set To Min (Hold) |  |
| `v_engineering_assignment_reset` | Power Allocation - Reset All |  |
| `v_engineering_assignment_shields_decrease` | Power Allocation - Shields - Decrease (Tap) |  |
| `v_engineering_assignment_shields_increase` | Power Allocation - Shields - Increase (Tap) |  |
| `v_engineering_assignment_shields_max` | Power Allocation - Shields - Set to Max (Hold) |  |
| `v_engineering_assignment_shields_min` | Power Allocation - Shields - Set to Min (Hold) |  |
| `v_engineering_assignment_weapons_decrease` | Power Allocation - Weapons - Decrease (Tap) |  |
| `v_engineering_assignment_weapons_increase` | Power Allocation - Weapons - Increase (Tap) |  |
| `v_engineering_assignment_weapons_max` | Power Allocation - Weapons - Set to Max (Hold) |  |
| `v_engineering_assignment_weapons_min` | Power Allocation - Weapons - Set to Min (Hold) |  |
| `v_power_set_off` | Vehicle Power - Off |  |
| `v_power_set_on` | Vehicle Power - On |  |
| `v_power_set_shields_off` | Shield Power - Off |  |
| `v_power_set_shields_on` | Shield Power - On |  |
| `v_power_set_thrusters_off` | Thruster Power - Off |  |
| `v_power_set_thrusters_on` | Thruster Power - On |  |
| `v_power_set_weapons_off` | Weapons Power - Off |  |
| `v_power_set_weapons_on` | Weapons Power - On |  |
| `v_power_throttle_down` | Decrease Throttle |  |
| `v_power_throttle_max` | Increase Throttle to Max |  |
| `v_power_throttle_min` | Decrease Throttle to Min |  |
| `v_power_throttle_up` | Increase Throttle |  |
| `v_power_toggle` | Vehicle Power - Toggle |  |
| `v_power_toggle_shields` | Shield Power - Toggle |  |
| `v_power_toggle_thrusters` | Thruster Power - Toggle |  |
| `v_power_toggle_weapons` | Weapons Power - Toggle |  |

## flight - HUD

| Action | In-Game Label | Description |
| --- | --- | --- |
| `mobiglas` | Mobiglas |  |
| `v_cycle_pitch_ladder_mode` | — | Used to show/hide the ladder in your HUD that indicates your angle relative to the horizon. Now seems to do nothing as the ladder is just always on by default. Also does not seem to be bindable in game, and even when bound via Star Binder it doesn't appear to do anything. |
| `v_hud_open_scoreboard` | — | Arena Commander action |
| `v_starmap` | Starmap | Go to Starmap in Mobiglas |
| `visor_wipe` | Wipe Helmet Visor | Wipe away anything covering your view on your helmet. Can be used while flying or on foot. |

## quantum travel

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_toggle_qdrive_engagement` | Engage Quantum Drive |  |

## vehicle

| Action | In-Game Label | Description |
| --- | --- | --- |
| `turret_change_position` | Change Turret Position | For turrets that have two or more possible positions. Such as the tractor turret on the Crusader C1 Spirit` |
| `turret_esp_hold` | Turret - ESP While Held | Enhanced Stick Precision, also known as ESP, dulls the sensitivity curves of the player input on the fly when the crosshair is near the target in order to minimize overshooting and help stay on target. It is similar to aim assist and is primarily intended for joystick users. There is an invisible circle around the player crosshair. When the pip enters the circle, the joystick input is dampened on a curve. This softens jerky or excessive stick movement common for a lot of people when trying to stay aimed at the pip during hard maneuvering at an evasive target. (https://starcitizen.tools/ESP) |
| `turret_esp_toggle` | Turret - ESP Toggle | Enhanced Stick Precision, also known as ESP, dulls the sensitivity curves of the player input on the fly when the crosshair is near the target in order to minimize overshooting and help stay on target. It is similar to aim assist and is primarily intended for joystick users. There is an invisible circle around the player crosshair. When the pip enters the circle, the joystick input is dampened on a curve. This softens jerky or excessive stick movement common for a lot of people when trying to stay aimed at the pip during hard maneuvering at an evasive target. (https://starcitizen.tools/ESP) |
| `turret_gyromode` | Turret - Gyromode Toggle | Toggle whether the turret aim is independent or affect by the roll/pitch/yaw of the ship itself. |
| `turret_limiter_abs` | Turret - Speed Limit Increase/Decrease (abs) | This should be set to a slider or similar control |
| `turret_limiter_rel` | Turret - Speed Limit Increase/Decrease |  |
| `turret_limiter_rel_decrease` | Turret - Speed Limit Decrease |  |
| `turret_limiter_rel_increase` | Turret - Speed Limit Increase |  |
| `turret_limiter_toggle` | Turret - Speed Limiter On/off | This is a 'smart toggle' by default, meaning you can hold/release to temporarily toggle, or tap to permanently toggle. Turns the turret pitch/yaw speed limiter on or off. |
| `turret_mouse_mode_cycle` | Turret - Mouse Movement Type - Cycle | Similar to 'Turret Mouse Movement Toggle' but cycles between more modes |
| `turret_mouse_mode_set_1to1` | Turret - Mouse Movement Type - Set Absolute | Set the current mouse movement mode to FPS style aim. |
| `turret_mouse_mode_set_pointer` | Turret - Mouse Movement Type - Set Pointer | Set the current mouse movement mode to the pointer style. |
| `turret_mouse_mode_set_vjoy` | Turret - Mouse Movement Type - Set Vjoy | Set the current mouse mode to virtual joystick. |
| `turret_pitch` | Turret - Pitch |  |
| `turret_pitch_down` | Turret - Pitch Down |  |
| `turret_pitch_mouse` | Turret - Pitch | Up/Down movement of your turret |
| `turret_pitch_up` | Turret - Pitch Up |  |
| `turret_recenter` | Recenter Turret | Automatically reorients the turret to face its default position relative to the ship while held. |
| `turret_remote_cycle_next` | Cycle Next Remote Turret | Take control of the next remote turret that can be controlled from your seat/station. |
| `turret_remote_cycle_prev` | Cycle Prev Remote Turret | Take control of the previous remote turret that can be controlled from your seat/station. |
| `turret_remote_exit` | Exit Remote Turret | Exit remote turret control mode. |
| `turret_toggle_mouse_mode` | Turret - Mouse Movement Type - Toggle | Switch between 'vjoy' mouse aim and an FPS style aim. |
| `turret_yaw` | Turret - Yaw |  |
| `turret_yaw_left` | Turret - Yaw Left |  |
| `turret_yaw_right` | Turret - Yaw Right |  |

## vehicles - seats and operator modes

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_eject` | Eject | Emergency eject from your ship's seat, assuming the ship has this feature. |
| `v_emergency_exit` | Emergency Exit | Powers off the ship (including shields) and makes the user get out of their chair at a normal speed (???) |
| `v_enter_remote_turret_1` | Enter Remote Turret (1) | While operating an appropriate station/seat, take control of the ship's first remote turret without needing to cycle through them. |
| `v_enter_remote_turret_2` | Enter Remote Turret (2) | While operating an appropriate station/seat, take control of the ship's second remote turret without needing to cycle through them. |
| `v_enter_remote_turret_3` | Enter Remote Turret (3) | While operating an appropriate station/seat, take control of the ship's third remote turret without needing to cycle through them. |
| `v_operator_mode_cycle_back` | Previous Operator Mode |  |
| `v_operator_mode_cycle_forward` | Next Operator Mode |  |
| `v_set_flight_mode` | Flight Mode On | Set your ship to flight mode |
| `v_set_guns_mode` | Guns Mode On | Set your ship to guns mode |
| `v_set_mining_mode` | Mining Mode On | Set your ship to mining mode |
| `v_set_missile_mode` | Missile Mode On | Set your ship to missile mode |
| `v_set_quantum_mode` | Quantum Mode On | Set your ship to quantum/nav mode |
| `v_set_salvage_mode` | Salvage Mode On | Set your ship to salvage mode |
| `v_set_scan_mode` | Scan Mode On | Set your ship to scan mode |
| `v_toggle_guns_mode` | Guns Mode Toggle | Toggle guns mode in your vehicle |
| `v_toggle_mining_mode` | Mining Mode Toggle | Toggle mining mode in your vehicle. |
| `v_toggle_missile_mode` | Missile Mode Toggle | Toggle missile mode in your vehicle |
| `v_toggle_quantum_mode` | Quantum Mode Toggle | Toggle Nav/Quantum mode |
| `v_toggle_salvage_mode` | Salvage Mode Toggle | Toggle salvage mode in your vehicle. |
| `v_toggle_scan_mode` | Scan Mode Toggle | Toggle scan mode in your vehicle. |
| `v_view_look_behind` | Look behind | Rear view camera for your vehicle |

## operator modes

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_toggle_flight_mode` | Flight Mode Toggle | Toggle flight mode in your vehicle |

## vehicles - weapons

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_weapon_aim_type_cycle` | Weapon Aim Type - Cycle |  |
| `v_weapon_aim_type_set_auto` | Weapon Aim Type - Set Auto |  |
| `v_weapon_aim_type_set_painting` | Weapon Aim Type - Set Painting |  |
| `v_weapon_aim_type_set_pip_aiming` | Weapon Aim Type - Set PIP |  |
| `v_weapon_convergence_distance_abs` | Manual Convergence Distance (abs.) | This kind of action (absolute) is best set to something like a slider |
| `v_weapon_convergence_distance_rel` | Manual Convergence Distance (rel.) | Set the distance at which your weapons naturally converge to a single focal point. |
| `v_weapon_convergence_distance_rel_decrease` | Manual Convergence Distance Decrease |  |
| `v_weapon_convergence_distance_rel_increase` | Manual Convergence Distance Increase |  |
| `v_weapon_convergence_distance_set_default` | Manual Convergence Distance Reset |  |
| `v_weapon_gimbals_state_set_locked` | Gimbals State - Locked |  |
| `v_weapon_gimbals_state_set_unlocked` | Gimbals State - Unlocked |  |
| `v_weapon_gimbals_state_toggle` | Gimbals State - Toggle |  |
| `v_weapon_gimbals_unlocked_cycle_source` | Gimbals Unlocked Cycle Source |  |
| `v_weapon_pip_combination_type_set_combined_weapon_group` | PIP Combination Type Set One PIP per weapon type |  |
| `v_weapon_pip_combination_type_set_single` | PIP Combination Type Set One PIP per weapon |  |
| `v_weapon_pip_combination_type_toggle` | PIP Combination Type Toggle |  |
| `v_weapon_pip_fade_off` | PIP Fading Off |  |
| `v_weapon_pip_fade_on` | PIP Fading On |  |
| `v_weapon_pip_fade_toggle` | PIP Fading Toggle |  |
| `v_weapon_pip_prec_line_off` | PIP Precision Lines Off |  |
| `v_weapon_pip_prec_line_on` | PIP Precision Lines On |  |
| `v_weapon_pip_prec_line_toggle` | PIP Precision Lines Toggle |  |
| `v_weapon_pip_set_lag` | Set Lag PIPs |  |
| `v_weapon_pip_set_lead` | Set Lead PIPs |  |
| `v_weapon_pip_toggle_lead_lag` | Lead/Lag PIP toggle |  |
| `v_weapon_preset_attack` | Weapon Preset - Fire |  |
| `v_weapon_preset_emp` | Weapon Preset - Set EMPs |  |
| `v_weapon_preset_fire_guns0` | Weapon Preset - Fire Guns Group 1 |  |
| `v_weapon_preset_fire_guns1` | Weapon Preset - Fire Guns Group 2 |  |
| `v_weapon_preset_fire_guns2` | Weapon Preset - Fire Guns Group 3 |  |
| `v_weapon_preset_fire_guns3` | Weapon Preset - Fire Guns Group 4 |  |
| `v_weapon_preset_guns0` | Weapon Preset - Set Guns Group 1 |  |
| `v_weapon_preset_guns1` | Weapon Preset - Set Guns Group 2 |  |
| `v_weapon_preset_guns2` | Weapon Preset - Set Guns Group 3 |  |
| `v_weapon_preset_guns3` | Weapon Preset - Set Guns Group 4 |  |
| `v_weapon_preset_next` | Weapon Preset - Next |  |
| `v_weapon_preset_next_overflow` | Weapon Preset - Next (overflow) |  |
| `v_weapon_preset_prev` | Weapon Preset - Previous |  |
| `v_weapon_preset_prev_overflow` | Weapon Preset - Previous (overflow) |  |
| `v_weapon_preset_qid` | Weapon Preset - Set QIDs | QID = Quantum Interdiction Device. Prevents the Quantum Drive from functioning in ships within the area of effect, which prevents jumping and limits speed to SCM speeds. |
| `v_weapon_preset_qid_jammer` | Weapon Preset - Set Quantum Jammers (short range) |  |
| `v_weapon_preset_qid_pulse` | Weapon Preset - Set Quantum Snares/Pulse (long range) |  |
| `v_weapon_staggered_fire_off` | Staggered Fire Off | In normal fire mode, your guns will fire at the same time. |
| `v_weapon_staggered_fire_on` | Staggered Fire On | In staggered fire mode, your guns will fire one after the other instead of at the same time. |
| `v_weapon_staggered_fire_toggle` | Staggered Fire Toggle | In staggered fire mode, your guns will fire one after the other instead of at the same time. |
| `v_weapon_suppress_aim_assists_hold` | Suppress Aim Assists (Hold) |  |
| `v_weapon_ui_scale_off` | Gunnery UI Magnification Off |  |
| `v_weapon_ui_scale_on` | Gunnery UI Magnification On |  |
| `v_weapon_ui_scale_toggle` | Gunnery UI Magnification Toggle |  |

## vehicles - missiles

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_weapon_bombing_hud_range_decrease` | Bombs - HUD Range - Decrease |  |
| `v_weapon_bombing_hud_range_increase` | Bombs - HUD Range - Increase |  |
| `v_weapon_bombing_hud_range_reset` | Bombs - HUD Range - Reset |  |
| `v_weapon_bombing_toggle_desired_impact_point` | Bombs - Desired Impact Point Toggle |  |
| `v_weapon_bombing_toggle_desired_impact_point_hold` | Bombs - Desired Impact Point Toggle (Hold) |  |
| `v_weapon_cycle_missile_back` | Missile Type - Cycle Previous |  |
| `v_weapon_cycle_missile_fwd` | Missile Type - Cycle Next |  |
| `v_weapon_decrease_max_missiles` | Armed Missiles - Decrease |  |
| `v_weapon_increase_max_missiles` | Armed Missiles - Increase |  |
| `v_weapon_launch_missile` | Lanch Missiles (Hold) |  |
| `v_weapon_launch_missile_cinematic` | Enable Cinematic Camera (Toggle) |  |
| `v_weapon_launch_missile_cinematic_hold` | Enable Cinematic Camera (Hold) |  |
| `v_weapon_reset_max_missiles` | Armed Missiles - Reset |  |
| `v_weapon_toggle_launch_missile` | Launch Missiles (Tap) |  |

## vehicles - shields and countermeasures

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_shield_raise_level_back` | Shield - Raise Level - Rear | Shield - Raise Level - Aft |
| `v_shield_raise_level_down` | Shield - Raise Level - Down |  |
| `v_shield_raise_level_forward` | Shield - Raise Level - Front | Shield - Raise Level - Fore |
| `v_shield_raise_level_left` | Shield - Raise Level - Left | Shield - Raise Level - Port |
| `v_shield_raise_level_right` | Shield - Raise Level - Right | Shield - Raise Level - Starboard |
| `v_shield_raise_level_up` | Shield - Raise Level - Up |  |
| `v_shield_reset_level` | Shield - Reset Levels |  |
| `v_weapon_countermeasure_decoy_burst_decrease` | Decoy - Burst Size - Decrease |  |
| `v_weapon_countermeasure_decoy_burst_increase` | Decoy - Burst Size - Increase |  |
| `v_weapon_countermeasure_decoy_launch` | Decoy - Launch Burst (tap), Set and Launch Burst (hold) |  |
| `v_weapon_countermeasure_decoy_launch_panic` | Decoy - Panic Launch |  |
| `v_weapon_countermeasure_noise_launch` | Noise Launch |  |

## targeting

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_auto_targeting_disable_long` | Auto Targeting - Off (Long Press) |  |
| `v_auto_targeting_disable_short` | Auto Targeting - Off (Short Press) |  |
| `v_auto_targeting_enable_long` | Auto Targeting - On (Long Press) |  |
| `v_auto_targeting_enable_short` | Auto Targeting - On (Short Press) |  |
| `v_auto_targeting_toggle_long` | Auto Targeting - Toggle (Long Press) |  |
| `v_auto_targeting_toggle_short` | Auto Targeting - Toggle (Short Press) |  |
| `v_look_ahead_start_target_tracking` | Target Padlock Toggle (Hold) | The name of this bind in the XML is 'look ahead start target tracking' - This probably toggles whether your Look Ahead mode will look towards the current target. |
| `v_target_lock_selected` | Lock current target |  |
| `v_target_pin_selected` | Pin Target |  |
| `v_target_pin_selected_hold` | Pin Target (Hold) |  |
| `v_target_remove_all_pins` | Remove All Pinned Targets |  |
| `v_target_toggle_lock_index_1` | Pin Index 1 - Lock/Unlock Pinned Target |  |
| `v_target_toggle_lock_index_2` | Pin Index 2 - Lock/Unlock Pinned Target |  |
| `v_target_toggle_lock_index_3` | Pin Index 3 - Lock/Unlock Pinned Target |  |
| `v_target_toggle_pin_index_1` | Pin/Unpin Target 1 |  |
| `v_target_toggle_pin_index_1_hold` | Pin/Unpin Target 1 (Hold) |  |
| `v_target_toggle_pin_index_2` | Pin/Unpin Target 2 |  |
| `v_target_toggle_pin_index_2_hold` | Pin/Unpin Target 1 (Hold) |  |
| `v_target_toggle_pin_index_3` | Pin/Unpin Target 3 |  |
| `v_target_toggle_pin_index_3_hold` | Pin/Unpin Target 1 (Hold) |  |
| `v_target_tracking_auto_zoom` | Auto Zoom on selected target toggle (hold) | Toggle whether your view zooms when a target is selected. |
| `v_target_unlock` | Unlock current target |  |
| `v_target_unpin_selected` | Unpin Target |  |
| `v_target_unpin_selected_hold` | Unpin Target (Hold) |  |

## target cycling

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_target_cycle_all_back` | Cycle Lock - All - Back | Cycle through all vehicles in range of your scanners. |
| `v_target_cycle_all_fwd` | Cycle Lock - All - Forward | Cycle through all vehicles in range of your scanners. |
| `v_target_cycle_all_reset` | Cycle Lock - All - Closest | Lock onto the closest vehicle to you. |
| `v_target_cycle_attacker_back` | Cycle Lock - Attackers - Back | Cycle locks between all attackers. |
| `v_target_cycle_attacker_fwd` | Cycle Lock - Attackers - Forward | Cycle locks between all attackers. |
| `v_target_cycle_attacker_reset` | Cycle Lock - Attackers - Closest | Lock onto he closest attacker. |
| `v_target_cycle_friendly_back` | Cycle Lock - Friendlies - Back | Cycle through non-hostile targets in the area. |
| `v_target_cycle_friendly_fwd` | Cycle Lock - Friendlies - Forward | Cycle through non-hostile targets in the area. |
| `v_target_cycle_friendly_reset` | Cycle Lock - Friendlies - Closest | Lock onto the closest friendly vehicle. |
| `v_target_cycle_hostile_back` | Cycle Lock - Hostiles - Back | Cycles between hostile (red) ships. |
| `v_target_cycle_hostile_fwd` | Cycle Lock - Hostiles- Forward | Cycles between hostile (red) ships. |
| `v_target_cycle_hostile_reset` | Cycle Lock - Hostiles - Closest | Lock onto the closest hostile vehicle. |
| `v_target_cycle_in_view_back` | Cycle Lock - In View - Back |  |
| `v_target_cycle_in_view_fwd` | Cycle Lock - In View - Forward |  |
| `v_target_cycle_in_view_reset` | Cycle Lock - In View - Under Reticle | 'Cycle Lock - In View - Reset to First' may also be another name for this. Perhaps it cycles between ships under reticle? |
| `v_target_cycle_pinned_back` | Cycle Lock - Pinned - Back | Cycle locks between pinned targets. |
| `v_target_cycle_pinned_fwd` | Cycle Lock - Pinned - Forward | Cycle locks between pinned targets. |
| `v_target_cycle_pinned_reset` | Cycle Lock - Pinned - Reset to First |  |
| `v_target_cycle_subitem_back` | Cycle Lock - Sub-Target - Back | Cycle through the current locked-on target's sub-targets to focus fire on them (e.g. turrets, thrusters) |
| `v_target_cycle_subitem_fwd` | Cycle Lock - Sub-Target - Forward | Cycle through the current locked-on target's sub-targets to focus fire on them (e.g. turrets, thrusters) |
| `v_target_cycle_subitem_reset` | Cycle Lock - Sub-Target - Reset | Reset your sub-targeting to the main target. |
| `v_target_under_reticle` | Lock target under reticle | Have your ship's computer lock onto the ship you're aiming at (not missles, just computer tracking). The locked target will hear a sound alerting them to your lock. |

## radar

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_invoke_ping` | Scan - Activate Ping |  |

## scanning

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_dec_scan_focus_level` | Decrease Scanning Angle |  |
| `v_inc_scan_focus_level` | Increase Scanning Angle |  |
| `v_scanning_trigger_scan` | Activate Scanning | Scans the target under your reticle while held. |

## mining

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_decrease_mining_throttle` | Mining Laser Power - Decreae |  |
| `v_increase_mining_throttle` | Mining Laser Power - Increase |  |
| `v_jettison_volatile_cargo` | Jettison Volatile Cargo | If you have volatile mining cargo, such as Quantanium, and it's about to explode, this action will let you jettison your entire cargo to save you and the ship. |
| `v_mining_throttle` | Mining Laser Power - Throttle |  |
| `v_mining_use_consumable1` | Activate Mining Module - Slot 1 |  |
| `v_mining_use_consumable2` | Activate Mining Module - Slot 2 |  |
| `v_mining_use_consumable3` | Activate Mining Module - Slot 3 |  |
| `v_mining_use_permanent_modifier` | Activate Mining Module - Permanent Modifier | Currently in SC this is labelled as a duplicate of activate slot 1, so it's been named here according to its XML name: 'use permanent modifier' |
| `v_toggle_mining_laser_fire` | Fire Mining Laser |  |
| `v_toggle_mining_laser_type` | Switch Mining Laser |  |

## salvage

| Action | In-Game Label | Description |
| --- | --- | --- |
| `tractor_beam_vehicle_decrease_distance` | Vehicle Tractor Beam - Decrease Distance |  |
| `tractor_beam_vehicle_increase_distance` | Vehicle Tractor Beam - Increase Distance |  |
| `v_salvage_beam_spacing_abs` | Salvage Beam Spacing - Absolute |  |
| `v_salvage_beam_spacing_rel` | Salvage Beam Spacing - Relative |  |
| `v_salvage_cycle_modifiers_focused` | Cycle Focused Salvage Modifiers | Cycle the mode/modifiers for any salvage beam(s) that have focus (e.g. between different scraper models, and/or a tractor beam). |
| `v_salvage_cycle_modifiers_left` | Cylce Left Salvage Modifiers | Cycle the mode/modifiers for the left salvage beam only, regardless of focus. |
| `v_salvage_cycle_modifiers_right` | Cylce Right Salvage Modifiers | Cycle the mode/modifiers for the right salvage beam only, regardless of focus. |
| `v_salvage_cycle_modifiers_structural` | Cycle Structural Salvage Modes |  |
| `v_salvage_decrease_beam_spacing` | Salvage Beam Spacing Decrease | Bring the beams closer to the central point. |
| `v_salvage_focus_all_heads` | Focus all salvage heads | Set focus to all of your salvage head. Controls that rely on focus will now affect all your salvage heads. |
| `v_salvage_focus_disintegrate` | Focus Disintegration Tool | Set focus to the Disintegration Tool. |
| `v_salvage_focus_fracture` | Focus Fracture Tool | Set focus to the Fracture Tool. |
| `v_salvage_focus_left` | Focus Left Salvage Head | Set focus to your left salvage head. Controls that rely on focus will now affect only your left salvage head. |
| `v_salvage_focus_right` | Focus Right Salvage Head | Set focus to your right salvage head. Controls that rely on focus will now affect only your right salvage head. |
| `v_salvage_increase_beam_spacing` | Salvage Beam Spacing Increase | Make the gap between beams bigger. |
| `v_salvage_nudge_down__left` | Nudge Left Salvage Tool: Down | Nudges the aim of the salvage beam a little bit in the stated direction. |
| `v_salvage_nudge_down__right` | Nudge Right Salvage Tool: Down | Nudges the aim of the salvage beam a little bit in the stated direction. |
| `v_salvage_nudge_left__left` | Nudge Left Salvage Tool: Left | Nudges the aim of the salvage beam a little bit in the stated direction. |
| `v_salvage_nudge_left__right` | Nudge Right Salvage Tool: Left | Nudges the aim of the salvage beam a little bit in the stated direction. |
| `v_salvage_nudge_right__left` | Nudge Left Salvage Tool: Right | Nudges the aim of the salvage beam a little bit in the stated direction. |
| `v_salvage_nudge_right__right` | Nudge Right Salvage Tool: Right | Nudges the aim of the salvage beam a little bit in the stated direction. |
| `v_salvage_nudge_up__left` | Nudge Left Salvage Tool: Up | Nudges the aim of the salvage beam a little bit in the stated direction. |
| `v_salvage_nudge_up__right` | Nudge Right Salvage Tool: Up | Nudges the aim of the salvage beam a little bit in the stated direction. |
| `v_salvage_reset_gimbal` | Salvage Mode - Gimbal Reset |  |
| `v_salvage_toggle_beam_spacing_axis` | Salvage Beam Axis - Toggle | Toggles between the two salvage beams being parallel horizontal and being parallel vertical. |
| `v_salvage_toggle_fire_disintegrate` | Fire Disintigrate Beam |  |
| `v_salvage_toggle_fire_focused` | Fire Focused Salvage Beams - Toggle | Other controls can set focus to specific beams, this action will then toggle the focussed beam(s) on or off. |
| `v_salvage_toggle_fire_fracture` | Fire Fracture Beam |  |
| `v_salvage_toggle_fire_left` | Fire Left Salvage Beam | Toggle fire the left salvage beam, regardless of focus |
| `v_salvage_toggle_fire_right` | Fire Right Salvage Beam | Toggle fire the right salvage beam, regardless of focus |
| `v_salvage_toggle_gimbal_mode` | Salvage Mode - Toggle Gimbal |  |

## vehicles - view

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_ads_cycle_tracking` | — |  |
| `v_ads_hold` | Vehicle ADS (Hold) | On foot, CIG call this 'zoom', but in a ship they call it 'ADS'. This is the 'zoom while in a ship' mode. |
| `v_ads_stable_max_zoom_hold` | — |  |
| `v_ads_toggle` | Vehicle ADS (Toggle) | On foot, CIG call this 'zoom', but in a ship they call it 'ADS'. This is the 'zoom while in a ship' mode. |
| `v_view_cycle_fwd` | Cycle camera view |  |
| `v_view_dynamic_zoom_abs` | Dynamic zoom (abs.) |  |
| `v_view_dynamic_zoom_abs_toggle` | Dynamic zoom toggle (abs.) |  |
| `v_view_dynamic_zoom_rel` | Dynamic zoom in and out (rel.) |  |
| `v_view_dynamic_zoom_rel_in` | Dynamic zoom in (rel.) |  |
| `v_view_dynamic_zoom_rel_out` | Dynamic zoom out (rel.) |  |
| `v_view_freelook_mode` | Freelook |  |
| `v_view_mode` | Cycle camera orbit mode |  |
| `v_view_pitch` | Look up/down |  |
| `v_view_pitch_down` | Look down |  |
| `v_view_pitch_mouse` | Look up/down |  |
| `v_view_pitch_up` | Look up |  |
| `v_view_yaw` | Look left/right |  |
| `v_view_yaw_left` | Look left |  |
| `v_view_yaw_mouse` | Look left/right |  |
| `v_view_yaw_right` | Look right |  |
| `v_view_zoom_in` | Zoom in (3rd person view) |  |
| `v_view_zoom_out` | Zoom out (3rd Person view) |  |

## camera - advanced camera controls

| Action | In-Game Label | Description |
| --- | --- | --- |
| `view_enable_camview_mode` | Third Person Cam - Advanced Controls Modifier | Hold this and press the advanced camera controls to change its appearance. |
| `view_fov_in` | Advanced Camera: Increase FoV | Zoom in to a tighter FOV angle |
| `view_fov_out` | Advanced Camera: Decrease FoV | Zoom out to a wider FOV angle |
| `view_fstop_in` | Advanced Camera: Increase DoF | Adjust bokeh effect |
| `view_fstop_out` | Advanced Camera: Decrease DoF | Adjust bokeh effect |
| `view_load_view_1` | Camera: Load View 1 |  |
| `view_load_view_2` | Camera: Load View 2 |  |
| `view_load_view_3` | Camera: Load View 3 |  |
| `view_load_view_4` | Camera: Load View 4 |  |
| `view_load_view_5` | Camera: Load View 5 |  |
| `view_load_view_6` | Camera: Load View 6 |  |
| `view_load_view_7` | Camera: Load View 7 |  |
| `view_load_view_8` | Camera: Load View 8 |  |
| `view_load_view_9` | Camera: Load View 9 |  |
| `view_move_target_X_neg` | Advanced Camera: X Offset Negative | Offset the camera left/right |
| `view_move_target_X_pos` | Advanced Camera: X Offset Positive | Offset the camera left/right |
| `view_move_target_Y_neg` | Advanced Camera: Y Offset NegativeÂ / Spectator Freecam Focal Point Backward | Offset the camera forward/backward |
| `view_move_target_Y_pos` | Advanced Camera: Y Offset Positive / Spectator Freecam Focal Point Forward | Offset the camera forward/backward |
| `view_move_target_Z_neg` | Advanced Camera: Z Offset Negative | Offset the camera vertically |
| `view_move_target_Z_pos` | Advanced Camera: Z Offset Positive | Offset the camera vertically |
| `view_reset_saved` | Camera: Clear Saved View |  |
| `view_restore_defaults` | Reset Current View | Resets cam to default state |
| `view_save_view_1` | Camera: Save View 1 |  |
| `view_save_view_2` | Camera: Save View 2 |  |
| `view_save_view_3` | Camera: Save View 3 |  |
| `view_save_view_4` | Camera: Save View 4 |  |
| `view_save_view_5` | Camera: Save View 5 |  |
| `view_save_view_6` | Camera: Save View 6 |  |
| `view_save_view_7` | Camera: Save View 7 |  |
| `view_save_view_8` | Camera: Save View 8 |  |
| `view_save_view_9` | Camera: Save View 9 |  |
| `view_switch_to_alternative` | Third Person Cam - Freemove | Allows the camera to move without the player moving while held. |

## vehicles - multi function displays (mfds)

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_mfd_interact_cycle_backwards_long` | MFD - Cycle Page - Backwards (Long Press) |  |
| `v_mfd_interact_cycle_backwards_short` | MFD - Cycle Page - Backwards (Short Press) |  |
| `v_mfd_interact_cycle_forwards_long` | MFD - Cycle Page - Forwards (Long Press) |  |
| `v_mfd_interact_cycle_forwards_short` | MFD - Cycle Page - Forwards (Short Press) |  |
| `v_mfd_movement_down_long` | MFD - Movement - Down (Long Press) |  |
| `v_mfd_movement_down_short` | MFD - Movement - Down (Short Press) |  |
| `v_mfd_movement_left_long` | MFD - Movement - Left (Long Press) |  |
| `v_mfd_movement_left_short` | MFD - Movement - Left (Short Press) |  |
| `v_mfd_movement_right_long` | MFD - Movement - Right (Long Press) |  |
| `v_mfd_movement_right_short` | MFD - Movement - Right (Short Press) |  |
| `v_mfd_movement_up_long` | MFD - Movement - Up (Long Press) |  |
| `v_mfd_movement_up_short` | MFD - Movement - Up (Short Press) |  |
| `v_mfd_quick_action_repair_all` | Repair All | Activate self-repair for all destroyed items where available |
| `v_mfd_select_view_comms_long` | MFD - Set Page - Communications (Long Press) |  |
| `v_mfd_select_view_comms_short` | MFD - Set Page - Communications (Short Press) |  |
| `v_mfd_select_view_configuration_long` | MFD - Set Page - Vehicle Configuration (Long Press) |  |
| `v_mfd_select_view_configuration_short` | MFD - Set Page - Vehicle Configuration (Short Press) |  |
| `v_mfd_select_view_diagnostics_long` | MFD - Set Page - Diagnostics (Long Press) |  |
| `v_mfd_select_view_diagnostics_short` | MFD - Set Page - Diagnostics (Short Press) |  |
| `v_mfd_select_view_ifcs_long` | MFD - Set Page - IFCS (Long Press) |  |
| `v_mfd_select_view_ifcs_short` | MFD - Set Page - IFCS (Short Press) |  |
| `v_mfd_select_view_resource_network_long` | MFD - Set Page - Resource Network (Long Press) |  |
| `v_mfd_select_view_resource_network_short` | MFD - Set Page - Resource Network (Short Press) |  |
| `v_mfd_select_view_scanning_long` | MFD - Set Page - Scanning (Long Press) |  |
| `v_mfd_select_view_scanning_short` | MFD - Set Page - Scanning (Short Press) |  |
| `v_mfd_select_view_self_status_long` | MFD - Set Page - Self Status (Long Press) |  |
| `v_mfd_select_view_self_status_short` | MFD - Set Page - Self Status (Short Press) |  |
| `v_mfd_select_view_target_status_long` | MFD - Set Page - Target Status (Long Press) |  |
| `v_mfd_select_view_target_status_short` | MFD - Set Page - Target Status (Short Press) |  |
| `v_mfd_soft_select_cast_left_long` | MFD - Select - Left Cast (Long Press) |  |
| `v_mfd_soft_select_cast_left_short` | MFD - Select - Left Cast (Short Press) |  |
| `v_mfd_soft_select_cast_right_long` | MFD - Select - Right Cast (Long Press) |  |
| `v_mfd_soft_select_cast_right_short` | MFD - Select - Right Cast (Short Press) |  |
| `v_mfd_soft_select_mfd_1_long` | MFD - Select - MFD 1 (Long Press) |  |
| `v_mfd_soft_select_mfd_1_short` | MFD - Select - MFD 1 (Short Press) |  |
| `v_mfd_soft_select_mfd_10_long` | MFD - Select - MDF 10 (Long Press) |  |
| `v_mfd_soft_select_mfd_10_short` | MFD - Select - MFD 10 (Short Press) |  |
| `v_mfd_soft_select_mfd_2_long` | MFD - Select - MFD 2 (Long Press) |  |
| `v_mfd_soft_select_mfd_2_short` | MFD - Select - MFD 2 (Short Press) |  |
| `v_mfd_soft_select_mfd_3_long` | MFD - Select - MFD 3 (Long Press) |  |
| `v_mfd_soft_select_mfd_3_short` | MFD - Select - MFD 3 (Short Press) |  |
| `v_mfd_soft_select_mfd_4_long` | MFD - Select - MFD 4 (Long Press) |  |
| `v_mfd_soft_select_mfd_4_short` | MFD - Select - MFD 4 (Short Press) |  |
| `v_mfd_soft_select_mfd_5_long` | MFD - Select - MFD 5 (Long Press) |  |
| `v_mfd_soft_select_mfd_5_short` | MFD - Select - MFD 5 (Short Press) |  |
| `v_mfd_soft_select_mfd_6_long` | MFD - Select - MFD 6 (Long Press) |  |
| `v_mfd_soft_select_mfd_6_short` | MFD - Select - MFD 6 (Short Press) |  |
| `v_mfd_soft_select_mfd_7_long` | MFD - Select - MFD 7 (Long Press) |  |
| `v_mfd_soft_select_mfd_7_short` | MFD - Select - MFD 7 (Short Press) |  |
| `v_mfd_soft_select_mfd_8_long` | MFD - Select - MFD 8 (Long Press) |  |
| `v_mfd_soft_select_mfd_8_short` | MFD - Select - MFD 8 (Short Press) |  |
| `v_mfd_soft_select_mfd_9_long` | MFD - Select - MFD 9 (Long Press) |  |
| `v_mfd_soft_select_mfd_9_short` | MFD - Select - MFD 9 (Short Press) |  |
| `v_mfd_soft_select_mfd_primary_long` | MFD - Select - Primary (Long Press) |  |
| `v_mfd_soft_select_mfd_primary_short` | MFD - Select - Primary (Short Press) |  |

## lights

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_lights` | Headlights (toggle) |  |
| `v_lights_off` | Headlights Off |  |
| `v_lights_on` | Headlights On |  |

## nightvision

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_light_amplification_off` | LAMP: Light Amplification Off | LAMP (Light AMPlification) - Nightvision for your ship |
| `v_light_amplification_on` | LAMP: Light Amplification On | LAMP (Light AMPlification) - Nightvision for your ship |
| `v_light_amplification_toggle` | LAMP: Light Amplification Toggle | LAMP (Light AMPlification) - Nightvision for your ship |

## fuel

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_set_refuel_mode` | Refuel Mode Set | Switch into refuelling mode |
| `v_toggle_refuel_mode` | Refuel Mode Toggle | Switch into refuelling mode |

## docking

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_dock_toggle_view` | Docking Camera Toggle |  |
| `v_invoke_docking` | — |  |
| `v_toggle_docking_mode` | — |  |

## cockpit

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_close_all_doors` | — | Close all doors/elevators/ramps on your ship. Depending on how CIG have setup the ship, this will often include all the component bays and interior doors. |
| `v_cooler_throttle_down` | Cooler Rate - Decrease |  |
| `v_cooler_throttle_up` | Cooler Rate - Increase |  |
| `v_flightready` | Flight/Systems Ready | Turn on power, engines, and shields with a single action. |
| `v_lock_all_doors` | — | Lock all doors/elevators/ramps on your ship. Locked doors can only be opened by the ship owner and their party members. Unlocked doors can be opened by anyone. |
| `v_lock_all_ports` | — | Lock all of the ship's ports - Ports must be UNLOCKED in order to remove/replace components, weapoons, or utilities with a tractor beam tool. |
| `v_open_all_doors` | — | Open all doors/elevators/ramps on your ship. Depending on how CIG have setup the ship, this will often include all the component bays and interior doors. |
| `v_self_destruct` | — | Destroy your ship from the pilot seat; timer depends on the ship (bigger ships allow more time for evacuation). |
| `v_toggle_all_doorlocks` | Lock/Unlock All Doors | Toggle whether the doors/elevators/ramps on your ship are locked or unlocked. Locked doors can only be opened by the ship owner and their party members. Unlocked doors can be opened by anyone. |
| `v_toggle_all_doors` | Open/Close All Doors | Toggle whether the ship's doors/elevators/ramps are all open or closed. Depending on how CIG have setup the ship, this will often include all the component bays and interior doors. |
| `v_toggle_all_portlocks` | Lock/Unlock All Ports | Toggle whether the lock state of the ship's ports - Ports must be UNLOCKED in order to remove/replace components, weapoons, or utilities with a tractor beam tool. |
| `v_unlock_all_doors` | — | Unlock all doors/elevators/ramps on your ship. Locked doors can only be opened by the ship owner and their party members. Unlocked doors can be opened by anyone. |
| `v_unlock_all_ports` | — | Unlock all of the ship's ports - Ports must be UNLOCKED in order to remove/replace components, weapoons, or utilities with a tractor beam tool. |

## ground vehicle - general

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_horn` | Horn |  |

## ground vehicle - movement

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_boost` | Boost | Make a ground vehicle go faster while driving it. |
| `v_brake` | Brake |  |
| `v_mgv_switch_brake_on_idle` | Switch Brake On Idle |  |
| `v_move` | Drive Forward / Backward |  |
| `v_move_back` | Drive Backward |  |
| `v_move_forward` | Drive Forward |  |

## on foot

| Action | In-Game Label | Description |
| --- | --- | --- |
| `ammoRepool` | Ammo Repool | Combine All Ammo |
| `attack1` | Attack1 / Shoot |  |
| `attackSecondary` | Attack2 |  |
| `consume` | Eat/Drink | Consume the food item held in your hand. |
| `crouch` | — |  |
| `customize` | Customize Weapon | Diegetic UI to add/remove attachments to your held weapon based on what you have on your person. |
| `dismiss_corpse_marker` | Dismiss Corpse Marker | Remove the marker for your corpse from your HUD. |
| `downedRevivalRequest` | Request Medical Rescue (while incapacitated) | Send up a beacon to request medical rescue. |
| `drop` | Drop item |  |
| `eva_boost` | EVA: Boost |  |
| `eva_brake` | EVA: Brake |  |
| `eva_roll` | EVA: Roll Left/Right |  |
| `eva_roll_left` | EVA: Roll Left |  |
| `eva_roll_right` | EVA: Roll Right |  |
| `eva_strafe_back` | EVA: Strafe Backward |  |
| `eva_strafe_down` | EVA: Strafe Down |  |
| `eva_strafe_forward` | EVA: Strafe Forward |  |
| `eva_strafe_lateral` | EVA: Strafe Left/Right |  |
| `eva_strafe_left` | EVA: Strafe Left |  |
| `eva_strafe_longitudinal` | EVA: Strafe Forward/Backward |  |
| `eva_strafe_right` | EVA: Strafe Right |  |
| `eva_strafe_up` | EVA: Strafe Up |  |
| `eva_strafe_vertical` | EVA: Strafe Up/Down |  |
| `eva_toggle_headlook_mode` | EVA: Freelook (Hold) |  |
| `eva_view_pitch` | EVA: View Up/Down |  |
| `eva_view_pitch_down` | EVA: View Down |  |
| `eva_view_pitch_mouse` | EVA: View Up/Down |  |
| `eva_view_pitch_up` | EVA: View Up |  |
| `eva_view_yaw` | EVA: View Left/Right |  |
| `eva_view_yaw_left` | EVA: View Left |  |
| `eva_view_yaw_mouse` | EVA: View Left/Right |  |
| `eva_view_yaw_right` | EVA: View Right |  |
| `fixed_speed_decrement` | Default Movement Speed - Decrease |  |
| `fixed_speed_increment` | Default Movement Speed - Increase |  |
| `force_respawn` | Force Re-spawn (E.V.A. / On Foot) | Perish and respawn at the relevant location |
| `free_thirdperson_camera` | Free View Camera (hold) |  |
| `gp_crouch` | — |  |
| `gp_jump` | — |  |
| `gp_movex` | Move Left / Right |  |
| `gp_movey` | Move Forward / Back |  |
| `gp_rotatepitch` | Look (Pitch) | Look Up/Down |
| `gp_rotateyaw` | Look (Yaw) | Look Left/Right |
| `holster` | Holster Weapon |  |
| `incapacitatedRespawn` | Regen (while Incapacitated) | Perish and respawn at the relevant location |
| `inspect` | Inspect Item |  |
| `interact_with_scope` | Interact with Scope | Will toggle active ability like night vision on compatible scopes and sights |
| `jump` | Jump |  |
| `jump_hold` | Jump |  |
| `jump_release` | — |  |
| `leanleft` | Lean Left |  |
| `leanright` | Lean Right |  |
| `ledgegrab` | Ledge Grab |  |
| `melee_AttackHeavyLeft` | Melee - Attack Heavy - Left (Hold) |  |
| `melee_AttackHeavyRight` | Melee - Attack Heavy - Right (Hold) |  |
| `melee_AttackLightLeft` | Melee - Attack Light - Left |  |
| `melee_AttackLightRight` | Melee - Attack Light - Right |  |
| `melee_AttackSyringeStab` | Medical Pen - Inject Other |  |
| `melee_block` | Melee - Block (Hold) |  |
| `melee_dodgeBack` | Melee - Dodge Backward |  |
| `melee_dodgeLeft` | Melee - Dodge Left |  |
| `melee_dodgeRight` | Melee - Dodge Right |  |
| `moveback` | Move Backward |  |
| `moveforward` | Move Forward |  |
| `moveleft` | Move Left |  |
| `moveright` | Move Right |  |
| `nextweapon` | Next Weapon |  |
| `pl_hud_open_scoreboard` | Scoreboard |  |
| `port_modification_select` | Port Modification Interact |  |
| `prevweapon` | Previous Weapon |  |
| `prone` | — |  |
| `prone_rollleft` | Roll Left (while Prone) |  |
| `prone_rollright` | Roll Right (while Prone) |  |
| `reload` | Reload |  |
| `reloadSecondary` | Reload Secondary |  |
| `select_gadget_pit` | Select Gadget |  |
| `select_meleeweapon_pit` | Select Melee |  |
| `select_primary_pit` | Select Primary Weapon |  |
| `select_secondary_pit` | Select Secondary Weapon |  |
| `select_sidearm_pit` | Select Sidearm |  |
| `selectUnarmedCombat` | Unarmed Combat | 'Equip' your fists |
| `ship_recall` | Recall Last Vehicle | Is this just for Arena Commander? |
| `sprint` | — |  |
| `stabilize` | Hold Breath (ADS) / Steady Scope |  |
| `takedown_nonLethal` | Melee - Non-lethal Takedown | When close behind another character |
| `thirdperson` | Third Person View (toggle) |  |
| `throw_overhand` | Throw - Overarm & Two-Handed | A stronger throw of the item in your hand (incl. grenades) |
| `throw_underhand` | Throw - Underarm | A weaker throw for short range lobs of the item in your hand (incl. grenades) |
| `toggle_flashlight` | Flashlight (toggle) |  |
| `toggle_lowered` | Weapon Stance / Lower Weapon - Toggle | Lower your weapon to appear less aggressive but keep it held and ready. |
| `toggleAttachHelmet` | Toggle Attach Helmet |  |
| `toggleEquipHelmet` | Toggle Equip Helmet |  |
| `toggleHelmetState` | Toggle Helmet State | This is mixed up in the in-game keybind UI because of a bug/error in the gamefiles (it's given the same UI name as increase walk speed by mistake). It's not clear what this action does, if anything. It may depend on the helmet (perhaps there are helmets with retractable visors or something). |
| `tractor_beam_decrease_distance` | Tractor Beam - Decrease Distance | Decreases the target distance for an object controlled with the Tractor Beam. |
| `tractor_beam_increase_distance` | Tractor Beam - Increase Distance | Increases the target distance for an object controlled with the Tractor Beam. |
| `walk` | — |  |
| `weapon_auxiliary_action` | Toggle/Activate Underbarrel Attachment Action |  |
| `weapon_change_firemode` | Change Weapon Fire Mode |  |
| `weapon_change_mining_throttle` | Hand Mining Throttle - Increase/Decrease | Adjust the power output of the hand tool while mining |
| `weapon_melee` | Melee - Weapon Attack |  |
| `weapon_zeroing_decrease` | — |  |
| `weapon_zeroing_increase` | Weapon Zeroing Increase/Auto |  |
| `zgt_detach` | EVA: Detach from Surface |  |
| `zgt_launch` | EVA: Launch from Surface |  |
| `zgt_roll_left` | EVA: Roll Left |  |
| `zgt_roll_right` | EVA: Roll Right |  |
| `zoom` | ADS (Aim Down Sight) | This is the ADS action for sights |
| `zoom_in` | Zoom in |  |
| `zoom_out` | Zoom out |  |

## quick keys, interactions, and inner thought

| Action | In-Game Label | Description |
| --- | --- | --- |
| `pc_camera_orbit` | Camera Orbit |  |
| `pc_focus` | Interaction Mode: Focus | Focus |
| `pc_interaction_mode` | Interaction Mode | Interaction Mode |
| `pc_interaction_select` | Activate Inner Thought | Activate Interaction |
| `pc_personal_back` | Interaction Mode: Exit |  |
| `pc_personal_thought` | Personal Inner Thought (PIT) | Personal Inner Thought |
| `pc_pit_emotes` | Emotes - PIT Category |  |
| `pc_pit_empty_backpack` | Store AllÂ Commodities | Empty your pack / store all |
| `pc_pit_flight_systems` | Flight Systems - PIT Category |  |
| `pc_pit_inventory` | Personal Inventory |  |
| `pc_pit_item_actions` | Item Actions - PIT Category |  |
| `pc_pit_item_drop` | Drop Item |  |
| `pc_pit_looting` | Personal Inventory Loot UI | Default activation is to hold 'i'. |
| `pc_pit_looting_toggle_view` | Loot UI - Change Page | Changes between the main and secondary page of the Loot UI |
| `pc_pit_looting_toggle_weapon_attachments` | Loot UI - Toggle Weapon Attachments |  |
| `pc_pit_miningmode_actions` | Mining Mode Actions - PIT Category |  |
| `pc_pit_mobiglas_actions` | Mobiglas Actions - PIT Category |  |
| `pc_pit_player_actions` | Player Actions - PIT Category |  |
| `pc_pit_remote_turrets` | Remote Turret - PIT Category |  |
| `pc_pit_ship_systems` | Ship Systems - PIT Category |  |
| `pc_pit_vehicle_actions` | Vehicle Actions - PIT Category |  |
| `pc_pit_weapon_selection` | Weapon Selection - PIT Category |  |
| `pc_pit_weapons_systems` | Weapon Systems - PIT Category |  |
| `pc_qs_consumables` | Radial Menu - Consumables |  |
| `pc_qs_grenades` | Radial Menu - Throwables/Grenades |  |
| `pc_qs_weapons_pit_primary` | Radial Menu - Primary Weapon |  |
| `pc_qs_weapons_pit_secondary` | Radial Menu - Secondary Weapon |  |
| `pc_qs_weapons_pit_sidearm` | Radial Menu - Sidearm |  |
| `pc_screen_focus_down` | Interaction Mode: MFD Focus Down |  |
| `pc_screen_focus_left` | Interaction Mode: MFD Focus Left |  |
| `pc_screen_focus_right` | Interaction Mode: MFD Focus Right |  |
| `pc_screen_focus_up` | Interaction Mode: MFD Focus Up |  |
| `pc_select` | Activate Inner Thought | Activate Interaction |
| `pc_zoom_in` | Interaction Mode: Zoom In | Interaction Mode Zoom In |
| `pc_zoom_out` | Interaction Mode: Zoom Out | Interaction Mode Zoom Out |

## social - general

| Action | In-Game Label | Description |
| --- | --- | --- |
| `cycle_chat_lobby` | Cycle Chat Lobby | Press to cycle through subscribed lobbies in chat. |
| `focus_on_chat_textinput` | Chat Window On/Off | Show/Hide the chat window on your HUD. |
| `notification_accept` | Notification - Accept | @{english=; french=; german=; italian=Accetta notifica; spanish=; brazillian=; chinese=æŽ¥å—é€šçŸ¥; japanese=; korean=ì•Œë¦¼ ìˆ˜ë½; ukrainian=Ð¡Ð¿Ð¾Ð²Ñ–Ñ‰ÐµÐ½Ð½Ñ Ð¿Ñ€Ð¸Ð¹Ð½ÑÑ‚Ð¾} |
| `notification_decline` | Notification - Decline | @{english=; french=; german=; italian=Rifiuta notifica; spanish=; brazillian=; chinese=æ‹’ç»é€šçŸ¥; japanese=; korean=ì•Œë¦¼ ê±°ì ˆ; ukrainian=Ð’Ñ–Ð´Ñ…Ð¸Ð»ÐµÐ½Ð½Ñ ÑÐ¿Ð¾Ð²Ñ–Ñ‰ÐµÐ½Ð½Ñ} |
| `pl_exit` | Exit seat |  |
| `respawn` | Re-spawn | This has the 'social general' tag because that's what CIG put it as. This is the AC respawn command or is perhaps redundant. |
| `toggle_chat` | Chat Window (Toggle) |  |
| `toggle_contact` | CommLink App (Toggle) | Opens the global chat in MobiGlas |

## social - emotes

| Action | In-Game Label | Description |
| --- | --- | --- |
| `emote_agree` | Emote: Agree |  |
| `emote_angry` | Emote: Angry |  |
| `emote_atease` | Emote: At Ease |  |
| `emote_attention` | Emote: Attention |  |
| `emote_blah` | Emote: Blah |  |
| `emote_bored` | Emote: Bored |  |
| `emote_bow` | Emote: Bow |  |
| `emote_burp` | Emote: Burp |  |
| `emote_cheer` | Emote: Cheer |  |
| `emote_chicken` | Emote: Chicken |  |
| `emote_clap` | Emote: Clap |  |
| `emote_come` | Emote: Come |  |
| `emote_cry` | Emote: Cry |  |
| `emote_cs_forward` | Emote: Forward |  |
| `emote_cs_left` | Emote: Left |  |
| `emote_cs_no` | Emote: No |  |
| `emote_cs_right` | Emote: Right |  |
| `emote_cs_stop` | Emote: Stop |  |
| `emote_cs_yes` | Emote: Yes |  |
| `emote_dance` | Emote: Dance |  |
| `emote_disagree` | Emote: Disagree |  |
| `emote_failure` | Emote: Failure |  |
| `emote_flex` | Emote: Flex |  |
| `emote_flirt` | Emote: Flirt |  |
| `emote_gasp` | Emote: Gasp |  |
| `emote_gloat` | Emote: Gloat |  |
| `emote_greet` | Emote: Greet |  |
| `emote_laugh` | Emote: Laugh |  |
| `emote_launch` | Emote: Confirm Launch | Confirms the launch of the vehicle |
| `emote_point` | Emote: Point |  |
| `emote_rude` | Emote: Rude |  |
| `emote_salute` | Emote: Salute |  |
| `emote_sit` | Emote: Sit |  |
| `emote_sleep` | Emote: Sleep |  |
| `emote_smell` | Emote: Smell |  |
| `emote_taunt` | Emote: Taunt |  |
| `emote_threaten` | Emote: Threaten |  |
| `emote_wait` | Emote: Wait |  |
| `emote_wave` | Emote: Wave |  |
| `emote_whistle` | Emote: Whistle |  |

## social - invites

| Action | In-Game Label | Description |
| --- | --- | --- |
| `ui_notification_accept` | Accept Invite |  |
| `ui_notification_decline` | Reject Invite |  |
| `ui_notification_ignore` | Ignore Invite (hold) | Ignore Invite |

## comms/social

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_target_hail` | Hail Target | Initiate an in-game video call to the vehicle currently locked on to. |

## voip, foip and head tracking

| Action | In-Game Label | Description |
| --- | --- | --- |
| `foip_cyclechannel` | Cycle through audio channels | Cycle through audio channels |
| `foip_pushtotalk` | VOIP Push To Talk | VOIP Push To Talk |
| `foip_pushtotalk_proximity` | VOIP Push To Talk (Proximity only) | VOIP Push To Talk (Proximity only) |
| `foip_recalibrate` | FOIP Recalibrate | FOIP Recalibrate |
| `foip_viewownplayer` | FOIP Selfie Cam | FOIP Selfie Cam |
| `headtrack_camera_enabled` | Enable / Disable Head Tracking for 3rd Person Camera (Toggle) | Enables or disables head tracking in external cameras. |
| `headtrack_enabled` | Enable Head Tracking (Toggle) | Switches head tracking on / off (Toggle) |
| `headtrack_hold` | Head Tracking (Hold) | Enables head tracking as long as the button is held down |
| `headtrack_recenter_device` | Recenter Head Tracking Device (except TrackIR) | Recenters head tracking device inputs. |

## command module

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_toggle_docking_request` | Docking Request Toggle | Command module docking request. |

## stopwatch

| Action | In-Game Label | Description |
| --- | --- | --- |
| `stopwatch_reset` | Stopwatch Reset (Long Press) |  |
| `stopwatch_trigger` | Stopwatch Start/Pause |  |

## arena commander

| Action | In-Game Label | Description |
| --- | --- | --- |
| `spectate_gen_nextmode` | Spectator Camera Mode (Next) |  |
| `spectate_gen_prevmode` | Spectator Camera Mode (Previous) |  |
| `spectate_next_target` | Spectator Camera Target (Next) |  |
| `spectate_prev_target` | Spectator Camera Target (Previous) |  |
| `spectate_rotatepitch` | Spectator Camera Rotate Pitch |  |
| `spectate_rotatepitch_mouse` | Spectator Camera Rotate Pitch |  |
| `spectate_rotateyaw` | Spectator Camera Rotate Yaw |  |
| `spectate_rotateyaw_mouse` | Spectator Camera Rotate Yaw |  |
| `spectate_toggle_hud` | Spectator Camera HUD (Toggle) |  |
| `spectate_toggle_lock_target` | Spectator Camera Lock Target |  |
| `spectate_zoom` | Spectator Camera Zoom |  |
| `spectate_zoom_in` | Spectator Camera Zoom In |  |
| `spectate_zoom_out` | Spectator Camera Zoom Out |  |

## view

| Action | In-Game Label | Description |
| --- | --- | --- |
| `v_look_ahead_enable` | Look Ahead Toggle | Toggle whether the pilot's view automatically looks toward the forward vector/horizon (intensity and type will depend on your Game Settings) |

## Other

| Action | In-Game Label | Description |
| --- | --- | --- |
| `hmd_lens_display_toggle` | HMD: Lens display toggle | Enables / Disables the Visor |
| `hmd_recenter` | HMD Recenter | Recenters the VR headset |
| `hmd_theater_mode_toggle` | HMD: Theatre mode toggle | Enables / Disables Theater Mode |
| `hmd_toggle` | HMD Toggle | Enables/disables VR gameplay |

## (uncategorised)

| Action | In-Game Label | Description |
| --- | --- | --- |
| `turret_yaw_mouse` | Turret - Yaw |  |


