<#
  validate_actionmaps.ps1 - check that every binding in MOZA.xml sits in the actionmap the
  GAME files it under, using the game's own normalized export as the authoritative oracle.

  WHY THIS EXISTS
  ----------------
  The starbinder catalogue (reference/STARBINDER_KEYBINDS_DATABASE_v*.md) groups actions by their
  first "keyword" - that is a CATEGORY, not the SC actionmap. Inferring an actionmap from that
  category is how camera bindings ended up in the wrong map and silently did nothing. The only
  authoritative action -> actionmap source is CIG's defaultProfile.xml (inside Data.p4k), but the
  game also writes a normalized copy of whatever profile is currently loaded to:

     ...\StarCitizen\LIVE\user\client\0\Profiles\default\actionmaps.xml

  Two facts make that file a perfect validator:
    1. The game files each ACCEPTED action under its TRUE actionmap.
    2. The game DROPS any action whose actionmap is wrong (or whose binding it rejects).
  So: load your profile in-game (Options > Keybindings, or pp_rebindkeys MOZA.xml), then run this.
    - MISMATCH      = the action is in the export under a DIFFERENT map -> MOZA.xml is wrong, fix it.
    - NOT-IN-EXPORT = the game did not keep this binding. Either it equals an SC default (benign) or
                      it was DROPPED (wrong map / rejected binding). Verify the ones that matter.
    - OK            = MOZA's actionmap matches the game's filing.

  USAGE (from the project root):
     powershell -ExecutionPolicy Bypass -File .\tools\validate_actionmaps.ps1
     powershell -ExecutionPolicy Bypass -File .\tools\validate_actionmaps.ps1 -Profile "C:\path\to\actionmaps.xml"

  Exit code is non-zero if any MISMATCH is found (handy for a quick gate).
#>

[CmdletBinding()]
param(
  [string]$Mapping,   # MOZA.xml (default: <root>\MOZA.xml)
  [string]$Profile    # game export actionmaps.xml (default: <client0>\Profiles\default\actionmaps.xml)
)

$ErrorActionPreference = 'Stop'

# --- resolve default paths relative to this script (root = ...\controls\mappings) ---
$root = Split-Path $PSScriptRoot                       # ...\controls\mappings
if (-not $Mapping) { $Mapping = Join-Path $root 'MOZA.xml' }
if (-not $Profile) {
  $client0 = Split-Path (Split-Path $root)             # ...\client\0
  $Profile = Join-Path $client0 'Profiles\default\actionmaps.xml'
}

if (-not (Test-Path $Mapping)) { throw "MOZA mapping not found: $Mapping" }
if (-not (Test-Path $Profile)) {
  throw "Game export not found: $Profile`n  Load the profile in-game first (it writes this file), or pass -Profile <path>."
}

[xml]$mx = Get-Content $Mapping -Raw
[xml]$ax = Get-Content $Profile -Raw

# Structure-agnostic: MOZA.xml is ActionMaps>actionmap; the game export is ActionMaps>ActionProfiles>actionmap.
function Get-Maps([xml]$doc) { $doc.SelectNodes('//actionmap') }

# Authoritative lookup: action name -> list of actionmaps it appears in (from the game export).
$auth = @{}
foreach ($m in Get-Maps $ax) {
  foreach ($a in $m.action) {
    if (-not $auth.ContainsKey($a.name)) { $auth[$a.name] = New-Object System.Collections.ArrayList }
    [void]$auth[$a.name].Add($m.name)
  }
}

$ok = 0
$mismatch = @()
$notInExport = @()

foreach ($m in Get-Maps $mx) {
  foreach ($a in $m.action) {
    $mozaMap = $m.name
    if ($auth.ContainsKey($a.name)) {
      if ($auth[$a.name] -contains $mozaMap) { $ok++ }
      else { $mismatch += [pscustomobject]@{ Action = $a.name; Moza = $mozaMap; Auth = ($auth[$a.name] -join ',') } }
    } else {
      $notInExport += [pscustomobject]@{ Action = $a.name; Moza = $mozaMap }
    }
  }
}

Write-Output "Profile (oracle): $Profile"
Write-Output "Mapping:          $Mapping"
Write-Output ""
Write-Output ("OK (map matches game): {0}   MISMATCH: {1}   NOT-IN-EXPORT: {2}" -f $ok, $mismatch.Count, $notInExport.Count)

if ($mismatch.Count) {
  Write-Output ""
  Write-Output "=== MISMATCH (wrong actionmap - FIX THESE) ==="
  $mismatch | ForEach-Object { "  {0}: MOZA=[{1}]  GAME=[{2}]" -f $_.Action, $_.Moza, $_.Auth }
}

if ($notInExport.Count) {
  Write-Output ""
  Write-Output "=== NOT-IN-EXPORT (game default OR dropped - verify the ones that matter) ==="
  $notInExport | ForEach-Object { "  {0}: MOZA=[{1}]" -f $_.Action, $_.Moza }
}

Write-Output ""
if ($mismatch.Count -eq 0) { Write-Output "No actionmap mismatches against the game's filing." }
else { Write-Output ("{0} mismatch(es) - see above." -f $mismatch.Count) }

exit ([int]($mismatch.Count -gt 0))
