<#
    refresh_keybinds_db.ps1
    ------------------------------------------------------------------
    Re-downloads the Star Citizen keybind master database that powers
    https://starbinder.space/ and regenerates the grouped Markdown
    reference STARBINDER_KEYBINDS_DATABASE_v<version>.md in this folder.

    The game version is auto-detected from the starbinder homepage
    ("UPDATED FOR x.y") and baked into the output file name. Any older
    STARBINDER_KEYBINDS_DATABASE_v*.md is removed so only the latest
    snapshot remains.

    Usage (from this folder):
        powershell -ExecutionPolicy Bypass -File .\refresh_keybinds_db.ps1

    Data sources (all relative to https://starbinder.space/):
        keybinds.json      -> action_name => { label, description, keywords[] }
        localisation.json  -> resolves "@ui_..." description references
        (actionmaps.xml 404s here; it is uploaded by the user in-browser)
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$base = 'https://starbinder.space/'

# 1) Detect SC version from the homepage banner ("UPDATED FOR 4.8")
$html = (Invoke-WebRequest -Uri $base -UseBasicParsing).Content
$m    = [regex]::Match($html, '(?i)UPDATED\s+FOR\s+([0-9]+\.[0-9]+(\.[0-9]+)?)')
$ver  = if ($m.Success) { $m.Groups[1].Value } else { 'unknown' }
Write-Host "Detected Star Citizen version: $ver"

# 2) Download the master data files
$kb  = (Invoke-WebRequest -Uri ($base + 'keybinds.json')     -UseBasicParsing).Content | ConvertFrom-Json
$loc = (Invoke-WebRequest -Uri ($base + 'localisation.json') -UseBasicParsing).Content | ConvertFrom-Json
$locNames = @{}; foreach ($p in $loc.PSObject.Properties) { $locNames[$p.Name] = $p.Value }
Write-Host "Downloaded $($kb.PSObject.Properties.Name.Count) actions."

# 3) Helpers
function Resolve-Desc($d) {
    if ([string]::IsNullOrWhiteSpace($d)) { return '' }
    if ($d.StartsWith('@')) {
        $k = $d.Substring(1)
        if ($locNames.ContainsKey($k)) { return [string]$locNames[$k] } else { return '' }
    }
    return [string]$d
}
function Clean($s) { if ($null -eq $s) { return '' }; ($s -replace '\r?\n',' ' -replace '\|','\|' -replace '\s{2,}',' ').Trim() }
function Slug($s)  { ($s.ToLower() -replace '[^a-z0-9 -]','' -replace ' ','-' -replace '-{2,}','-').Trim('-') }

# 4) Group actions by their first keyword (category)
$byCat = @{}
foreach ($p in $kb.PSObject.Properties) {
    $v = $p.Value
    $cat = if ($v.keywords -and $v.keywords.Count -gt 0) { [string]$v.keywords[0] } else { '(uncategorised)' }
    if (-not $byCat.ContainsKey($cat)) { $byCat[$cat] = [System.Collections.Generic.List[object]]::new() }
    $byCat[$cat].Add([pscustomobject]@{ action=$p.Name; label=[string]$v.label; desc=(Resolve-Desc $v.description) })
}

# Curated category order (flight first, social/on-foot last); anything new appended
$order = @('flight - movement','flight - power','flight - HUD','quantum travel','vehicle',
    'vehicles - seats and operator modes','operator modes','vehicles - weapons','vehicles - missiles',
    'vehicles - shields and countermeasures','targeting','target cycling','radar','scanning','mining','salvage',
    'vehicles - view','camera - advanced camera controls','vehicles - multi function displays (mfds)','lights',
    'nightvision','fuel','docking','cockpit','ground vehicle - general','ground vehicle - movement','on foot',
    'quick keys, interactions, and inner thought','social - general','social - emotes','social - invites',
    'comms/social','voip, foip and head tracking','command module','stopwatch','arena commander','view','Other','(uncategorised)')
foreach ($k in $byCat.Keys) { if ($order -notcontains $k) { $order += $k } }

# 5) Build Markdown
$today = (Get-Date).ToString('yyyy-MM-dd')
$sb = [System.Text.StringBuilder]::new()
[void]$sb.AppendLine('# Star Citizen - Master Keybinding Reference (all available bindings)')
[void]$sb.AppendLine('')
[void]$sb.AppendLine('> Complete catalogue of every bindable Star Citizen action and what it does.')
[void]$sb.AppendLine('> **Source:** the master keybind database behind <https://starbinder.space/> (`keybinds.json` + `localisation.json`).')
[void]$sb.AppendLine("> **Game version:** Star Citizen Alpha **$ver** (starbinder homepage reads ""UPDATED FOR $ver"").")
[void]$sb.AppendLine("> **Actions:** $($kb.PSObject.Properties.Name.Count) across $($byCat.Keys.Count) categories.  **Snapshot:** $today.")
[void]$sb.AppendLine('>')
[void]$sb.AppendLine('> The `Action` column is the internal action name you put inside `<action name="...">` in your `.xml` profile. The `In-Game Label` is what appears in the Keybindings menu. This is a *reference of what exists* - see `CLAUDE.md` for what is actually bound on the MOZA rig. Regenerate with `refresh_keybinds_db.ps1`.')
[void]$sb.AppendLine('')
[void]$sb.AppendLine('## Contents')
[void]$sb.AppendLine('')
foreach ($cat in $order) { if ($byCat.ContainsKey($cat)) { [void]$sb.AppendLine("- [$cat](#$(Slug $cat)) ($($byCat[$cat].Count))") } }
[void]$sb.AppendLine('')
foreach ($cat in $order) {
    if (-not $byCat.ContainsKey($cat)) { continue }
    [void]$sb.AppendLine("## $cat")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| Action | In-Game Label | Description |')
    [void]$sb.AppendLine('| --- | --- | --- |')
    foreach ($r in ($byCat[$cat] | Sort-Object action)) {
        $lbl = Clean $r.label; if ($lbl -eq '') { $lbl = '-' }
        $dsc = Clean $r.desc
        [void]$sb.AppendLine("| ``$($r.action)`` | $lbl | $dsc |")
    }
    [void]$sb.AppendLine('')
}

# 6) Write versioned file and prune older snapshots
$target = Join-Path $here ("STARBINDER_KEYBINDS_DATABASE_v$ver.md")
$sb.ToString() | Out-File -FilePath $target -Encoding utf8
Get-ChildItem $here -Filter 'STARBINDER_KEYBINDS_DATABASE_v*.md' |
    Where-Object { $_.FullName -ne $target } |
    ForEach-Object { Write-Host "Removing old snapshot: $($_.Name)"; Remove-Item $_.FullName -Force }
Write-Host "Wrote $target ($((Get-Item $target).Length) bytes)"
Write-Host "Remember to update the version referenced in CLAUDE.md if it changed."
