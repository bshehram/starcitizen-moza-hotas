<#
  regen_cards.ps1 - the MOZA button-reference cards (split-diagram, print layout).

  Produces the TWO reference cards, sized to fill a US-Letter sheet in LANDSCAPE
  (11 x 8.5 in, aspect 1.294) for printing in hand:

      cards/MOZA_MHG_AB6_ref.png / .svg   (js1: MHG grip 1-29 + AB6 base 49-62)
      cards/MOZA_MTQ_ref.png     / .svg   (js2: MTQ throttle 1-65 + axes)

  LAYOUT (60 / 40)
    The manufacturer diagrams are COMPOSITES - several views packed into one image
    (MTQ = throttle panel + Right Module + Left Module; MHG = side profile + front
    grip head; AB6 = base). Each composite is SPLIT into its sub-views (cropped from
    the source PNG, see the crop rectangles below) and laid out in the LEFT ~60% of
    the sheet as two stacked bands: the two small sub-views side by side on top, the
    one big sub-view below. The button# -> function table fills the RIGHT ~40% in two
    columns (labels are abbreviated to fit the narrow columns).

  PRINTING
    Print "Fit to page" / 100%, landscape. Each card is already the page aspect, so
    it fills the sheet edge to edge. Output is 2x (~330 DPI per card).

  EDITING
    The $AB6 / $MHG_* / $MTQ_* data arrays below are the lookup tables - a hand-kept
    VIEW of the bindings; source of truth is MOZA.xml. When a binding changes, edit
    the matching row here (and MOZA.xml / CLAUDE.md), then re-run. Labels here are
    deliberately terser than MOZA.xml to fit the 40% columns.

  CROP RECTANGLES (x0,y0,x1,y1 in source-PNG pixels) - re-verify if MOZA ships new
  device art (sources: AB6 890x691, MHG 1037x822, MTQ 1049x820):
    MTQ main   60, 90,612,818     MTQ right 615, 72,1045,486   MTQ left 620,488,1045,818
    MHG front 515, 90,985,575     MHG side  100,168, 460,770   AB6 base 250,110, 785,650

  REQUIREMENTS: Windows PowerShell + .NET System.Drawing, and Chrome or Edge.
  RUN (from the project root):
      powershell -ExecutionPolicy Bypass -File .\tools\regen_cards.ps1
#>

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$repo    = Split-Path -Parent $root
$diagDir = Join-Path $repo 'diagrams'
$cardDir = Join-Path $repo 'cards'

$chrome = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { throw "regen_cards: no Chrome/Edge found to render SVG -> PNG." }

$MID = [char]0x00B7

# ---- palette ----
$C_TITLE='#0f1720'; $C_SUB='#5b6b7a'; $C_PRIM='#16202b'; $C_VARTXT='#5b6b7a'; $C_HINT='#8a96a2'
$C_BADGE='#1f2933'; $C_BADGE_UNB='#cdd5dd'
$C_RULE='#d7dee5'; $C_ROWALT='#f4f7fa'
$C_MINE='#9a6a00'; $C_SALV='#0f6e6e'; $C_NOTE='#6b7681'

function Esc($s){ if($null -eq $s){return ''}; ([string]$s) -replace '&','&amp;' -replace '<','&lt;' -replace '>','&gt;' }
function V($tag,$text,$color){ @{ Tag=$tag; Text=$text; Color=$color } }
function R2($n){ [math]::Round($n,1) }

# Recolor a manufacturer diagram (or a sub-rect of one) to white-bg line art.
#   grayscale+invert+levels:  out = -k*lum + k*(1-black),  k = 1/(white-black)
function Get-Diagram($file,$black,$white,$cropTop,$cropL,$cropR,$cropBottom){
  $src = [System.Drawing.Bitmap]::FromFile((Join-Path $diagDir $file))
  $nw = $src.Width - $cropL - $cropR
  $nh = $src.Height - $cropTop - $cropBottom
  $dst = New-Object System.Drawing.Bitmap($nw,$nh,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($dst)
  $g.Clear([System.Drawing.Color]::White)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $k = 1.0/($white-$black); $tr = $k*(1.0-$black)
  $cm = New-Object System.Drawing.Imaging.ColorMatrix
  $cm.Matrix00 = -$k*0.299; $cm.Matrix01 = -$k*0.299; $cm.Matrix02 = -$k*0.299
  $cm.Matrix10 = -$k*0.587; $cm.Matrix11 = -$k*0.587; $cm.Matrix12 = -$k*0.587
  $cm.Matrix20 = -$k*0.114; $cm.Matrix21 = -$k*0.114; $cm.Matrix22 = -$k*0.114
  $cm.Matrix33 = 1.0
  $cm.Matrix40 = $tr; $cm.Matrix41 = $tr; $cm.Matrix42 = $tr; $cm.Matrix44 = 1.0
  $ia = New-Object System.Drawing.Imaging.ImageAttributes
  $ia.SetColorMatrix($cm)
  $g.DrawImage($src, (New-Object System.Drawing.Rectangle(0,0,$nw,$nh)), $cropL,$cropTop,$nw,$nh, [System.Drawing.GraphicsUnit]::Pixel, $ia)
  $ms = New-Object System.IO.MemoryStream
  $dst.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
  $b64 = [Convert]::ToBase64String($ms.ToArray())
  $ms.Dispose(); $g.Dispose(); $src.Dispose(); $dst.Dispose()
  return @{ B64=$b64; W=$nw; H=$nh }
}

# Crop a sub-rectangle [x0,y0,x1,y1] out of a source diagram and recolor it.
function Get-SubDiagram($file,$sw,$sh,$x0,$y0,$x1,$y1){
  Get-Diagram $file 0.45 0.85 $y0 $x0 ($sw-$x1) ($sh-$y1)
}

# Lay recolored sub-views into the left half of the card as a stack of fixed-height
# BANDS (quadrants). Each band spans the zone width and gets height ~ $HFrac (equal
# by default). A band holds one or more images placed side by side: each image owns
# a cell = $Frac of the zone width (cells centred within the band), is fit
# (aspect-preserved) in its cell, and is aligned vertically by $VA ('t'op / 'c'entre
# (default) / 'b'ottom) - used to STAGGER a side-by-side pair (one high, one low) so
# they use the band's whitespace. An optional caption sits under each image.
#   $rows = @( @{ HFrac=<opt>; Imgs=@( @{D=<diag>; Frac=<0..1>; VA=<opt>; Caption=<opt>}, ... ) }, ... )
# Used here as: band 1 = the two small views side by side (staggered); band 2 = the big view.
function Add-DiagramStack($sb,$rows,$zx,$zy,$zw,$zh,$rowGap,$F){
  $capH = [math]::Round(20*$F)
  $cellPad = [math]::Round(12*$F)
  $n = $rows.Count
  $avail = $zh - ($n-1)*$rowGap
  $sumHF = 0.0
  foreach($row in $rows){ $sumHF += $(if($row.HFrac){[double]$row.HFrac}else{1.0}) }
  $y = $zy
  foreach($row in $rows){
    $hf = $(if($row.HFrac){[double]$row.HFrac}else{1.0})
    $bandH = $avail * ($hf/$sumHF)
    $sumFrac = 0.0; foreach($im in $row.Imgs){ $sumFrac += [double]$im.Frac }
    $x = $zx + ($zw - $zw*$sumFrac)/2
    foreach($im in $row.Imgs){
      $cellW = $zw*[double]$im.Frac
      $hasCap = [bool]$im.Caption
      $areaH = if($hasCap){ $bandH - $capH } else { $bandH }
      $d = $im.D
      $scale = [math]::Min(($cellW-$cellPad)/$d.W, $areaH/$d.H)
      $dw = $d.W*$scale; $dh = $d.H*$scale
      $ix = $x + ($cellW-$dw)/2
      $va = if($im.VA){[string]$im.VA}else{'c'}
      $iy = switch($va){ 't' {$y} 'b' {$y + ($areaH-$dh)} default {$y + ($areaH-$dh)/2} }
      [void]$sb.Append("<image xlink:href='data:image/png;base64,$($d.B64)' x='$(R2 $ix)' y='$(R2 $iy)' width='$(R2 $dw)' height='$(R2 $dh)'/>")
      if($hasCap){
        $cy = $iy + $dh + [math]::Round(17*$F)
        [void]$sb.Append("<text x='$(R2 ($x+$cellW/2))' y='$(R2 $cy)' font-size='$([math]::Round(11*$F))' font-weight='600' text-anchor='middle' fill='$C_SUB' letter-spacing='0.4'>$(Esc $im.Caption)</text>")
      }
      $x += $cellW
    }
    $y += $bandH + $rowGap
  }
}

# Append one table row at (x,y). $F = font/size scale. Returns the height consumed.
function Add-Row($sb,$x,$y,$colW,$row,$idx,$F){
  $label = [string]$row.Label
  $unb = [bool]$row.Unbound
  $hasVar = ($null -ne $row.Variants -and $row.Variants.Count -gt 0)
  $rowH = [math]::Round(27*$F); if($hasVar){ $rowH = [math]::Round(44*$F) }
  $pad = [math]::Round(6*$F)
  if($idx % 2 -eq 1){ [void]$sb.Append("<rect x='$($x-$pad)' y='$y' width='$colW' height='$rowH' fill='$C_ROWALT'/>") }
  $badgeH = [math]::Round(20*$F)
  $badgeW = [math]::Round(30*$F); if($label.Length -gt 2){ $badgeW = [math]::Round((14+$label.Length*7.5)*$F) }
  $by = $y + [math]::Round(4*$F)
  $bfill = if($unb){$C_BADGE_UNB}else{$C_BADGE}
  $btxt  = if($unb){'#5b6671'}else{'#ffffff'}
  $bfont = [math]::Round(12*$F)
  [void]$sb.Append("<rect x='$x' y='$by' width='$badgeW' height='$badgeH' rx='$([math]::Round(4*$F))' fill='$bfill'/>")
  [void]$sb.Append("<text x='$(R2 ($x+$badgeW/2))' y='$(R2 ($by+$badgeH*0.72))' font-size='$bfont' font-weight='700' text-anchor='middle' fill='$btxt'>$(Esc $label)</text>")
  $tx = $x + $badgeW + [math]::Round(11*$F)
  $ptxtcol = if($unb){$C_HINT}else{$C_PRIM}
  $pweight = if($unb){'400'}else{'600'}
  $pfont = [math]::Round(13*$F)
  $hfont = [math]::Round(11.5*$F)
  [void]$sb.Append("<text x='$(R2 $tx)' y='$($y+[math]::Round(18*$F))' font-size='$pfont'><tspan font-weight='$pweight' fill='$ptxtcol'>$(Esc $row.Primary)</tspan>")
  if($row.Hint){ [void]$sb.Append("<tspan font-weight='400' font-size='$hfont' fill='$C_HINT'>  ($(Esc $row.Hint))</tspan>") }
  [void]$sb.Append("</text>")
  if($hasVar){
    $vfont = [math]::Round(10.5*$F)
    [void]$sb.Append("<text x='$(R2 $tx)' y='$($y+[math]::Round(35*$F))' font-size='$vfont'>")
    $first=$true
    foreach($v in $row.Variants){
      if(-not $first){ [void]$sb.Append("<tspan fill='#b6c0ca'>     </tspan>") }
      [void]$sb.Append("<tspan fill='$($v.Color)' font-weight='700'>$(Esc $v.Tag) </tspan><tspan fill='$C_VARTXT'>$(Esc $v.Text)</tspan>")
      $first=$false
    }
    [void]$sb.Append("</text>")
  }
  return $rowH
}

# Build one card SVG + render to PNG (2x). $cfg.F = font scale; $cfg.Stack = images.
function New-Card($cfg){
  $sb = New-Object System.Text.StringBuilder
  $CW=$cfg.CanvasW; $CH=$cfg.CanvasH; $F=$cfg.F; $M=34
  [void]$sb.Append("<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' width='$CW' height='$CH' viewBox='0 0 $CW $CH' font-family='Segoe UI, Arial, sans-serif'>")
  [void]$sb.Append("<rect width='$CW' height='$CH' fill='#ffffff'/>")
  $titleFont=[math]::Round(19*$F); $titleY=[math]::Round(30*$F)
  $subFont=[math]::Round(10.5*$F); $subY=[math]::Round(49*$F)
  $ruleY=[math]::Round(60*$F)
  [void]$sb.Append("<text x='$M' y='$titleY' font-size='$titleFont' font-weight='700' fill='$C_TITLE'>$(Esc $cfg.Title)</text>")
  [void]$sb.Append("<text x='$M' y='$subY' font-size='$subFont' fill='$C_SUB'>$(Esc $cfg.Sub)</text>")
  [void]$sb.Append("<line x1='$M' y1='$ruleY' x2='$($CW-$M)' y2='$ruleY' stroke='$C_RULE' stroke-width='1.5'/>")
  $top = $ruleY + [math]::Round(18*$F)
  if($cfg.Stack){
    $st = $cfg.Stack
    $zy = if($st.Y){ $st.Y } else { $top }
    $zh = if($st.H){ $st.H } else { $CH - $zy - [math]::Round(46*$F) }
    Add-DiagramStack $sb $st.Rows $st.X $zy $st.W $zh $st.Gap $F
  }
  foreach($col in $cfg.Cols){
    $cy = if($col.Y){$col.Y}else{$top}; $i = 0
    foreach($r in $col.Rows){
      if($r.Header){
        [void]$sb.Append("<text x='$($col.X)' y='$($cy+[math]::Round(14*$F))' font-size='$([math]::Round(12*$F))' font-weight='700' fill='$C_SUB' letter-spacing='0.6'>$(Esc $r.Header)</text>")
        [void]$sb.Append("<line x1='$($col.X)' y1='$($cy+[math]::Round(21*$F))' x2='$($col.X+$col.W-12)' y2='$($cy+[math]::Round(21*$F))' stroke='$C_RULE' stroke-width='1'/>")
        $cy += [math]::Round(31*$F); $i=0; continue
      }
      $rh = Add-Row $sb $col.X $cy $col.W $r $i $F
      $cy += $rh; $i++
    }
  }
  if($cfg.Legend){ [void]$sb.Append("<text x='$M' y='$($CH-[math]::Round(14*$F))' font-size='$([math]::Round(9*$F))' fill='$C_NOTE'>$(Esc $cfg.Legend)</text>") }
  [void]$sb.Append("</svg>")
  $svgPath = Join-Path $cardDir ($cfg.Name + ".svg")
  [IO.File]::WriteAllText($svgPath, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
  $pngPath = Join-Path $cardDir ($cfg.Name + ".png")
  # Render to a SPACE-FREE temp path, then move into cards/. Chrome's --screenshot=
  # and the file:// URL must not contain literal spaces: Start-Process (PS 5.1)
  # doesn't quote array args, so "...\Program Files\..." splits and Chrome reports
  # "Multiple targets are not supported in headless mode". %20-encode the URL via
  # [Uri].AbsoluteUri; keep the screenshot + --user-data-dir under $env:TEMP (no
  # spaces). The isolated user-data-dir also avoids colliding with a running Chrome.
  $uri = ([Uri]$svgPath).AbsoluteUri
  $tmpPng = Join-Path $env:TEMP ($cfg.Name + ".png")
  $udd = Join-Path $env:TEMP ("cardrender_" + $cfg.Name)
  if(Test-Path $tmpPng){ Remove-Item $tmpPng -Force }
  $argv = @('--headless=new','--disable-gpu','--no-sandbox','--hide-scrollbars',
            "--user-data-dir=$udd","--screenshot=$tmpPng","--window-size=$CW,$CH",
            '--force-device-scale-factor=2',$uri)
  $errF = [IO.Path]::GetTempFileName(); $outF = [IO.Path]::GetTempFileName()
  Start-Process -FilePath $chrome -ArgumentList $argv -Wait -NoNewWindow -RedirectStandardError $errF -RedirectStandardOutput $outF | Out-Null
  try { [IO.File]::Delete($errF); [IO.File]::Delete($outF) } catch {}
  try { Remove-Item $udd -Recurse -Force -ErrorAction SilentlyContinue } catch {}
  if(Test-Path $tmpPng){
    Move-Item $tmpPng $pngPath -Force
    $o=[System.Drawing.Image]::FromFile($pngPath); Write-Host ("  {0,-26} {1}x{2}" -f ($cfg.Name+'.png'), $o.Width, $o.Height); $o.Dispose()
  } else { throw "regen_cards: render failed for $($cfg.Name)." }
}

# ================================================================ split + recolor sub-views
Write-Host "Cropping + recoloring diagram sub-views..."
$SUB_MTQ_MAIN  = Get-SubDiagram 'MOZA_MTQ.png' 1049 820  60  90 612 818
$SUB_MTQ_RIGHT = Get-SubDiagram 'MOZA_MTQ.png' 1049 820 615  72 1045 486
$SUB_MTQ_LEFT  = Get-SubDiagram 'MOZA_MTQ.png' 1049 820 620 488 1045 818
$SUB_MHG_FRONT = Get-SubDiagram 'MOZA_MHG.png' 1037 822 515  90 985 575
$SUB_MHG_SIDE  = Get-SubDiagram 'MOZA_MHG.png' 1037 822 100 168 460 770
$SUB_AB6_BASE  = Get-SubDiagram 'MOZA_AB6.png'  890 691 250 110 785 650

# ================================================================ AB6 (js1 49-62)
# NOTE: variant/primary labels here are deliberately terse (vs MOZA.xml / CLAUDE.md)
# so they fit the narrow 40%-width legend columns - same bindings, shorter wording.
$AB6 = @(
  @{Header='AB6 BASE 49-62'},
  @{Label='49';Primary='Target: cycle in-view fwd';Variants=@((V 'Mine:' 'module 1' $C_MINE),(V 'Salv:' 'focus all' $C_SALV))},
  @{Label='50';Primary='Target: cycle in-view back';Variants=@((V 'Mine:' 'module 2' $C_MINE),(V 'Salv:' 'focus left' $C_SALV))},
  @{Label='51';Primary='Target: lock closest (any)';Variants=@((V 'Mine:' 'module 3' $C_MINE),(V 'Salv:' 'focus right' $C_SALV))},
  @{Label='52';Primary='Target: lock closest attacker';Variants=@((V 'Mine:' 'jettison cargo' $C_MINE),(V 'Salv:' 'beam axis H/V' $C_SALV))},
  @{Label='53';Primary='Target: cycle friendly fwd';Variants=@((V 'Salv:' 'fire left beam' $C_SALV))},
  @{Label='54';Primary='Target: cycle friendly back';Variants=@((V 'Salv:' 'fire right beam' $C_SALV))},
  @{Label='55';Primary='Target: cycle pinned back';Variants=@((V 'Salv:' 'reset gimbal' $C_SALV))},
  @{Label='56';Primary='Target: reset sub-target';Variants=@((V 'Salv:' 'structural modes' $C_SALV))},
  @{Label='57-59';Primary='Left "Slider" lever';Hint='unbound - reserved';Unbound=$true},
  @{Label='60-62';Primary='Right "Dial" lever';Hint='unbound - reserved';Unbound=$true}
)

# ================================================================ MHG (js1 1-29)
$MHG_L = @(
  @{Header='GRIP 1-15'},
  @{Label='1';Primary='Fire Guns - Group 1';Variants=@((V 'Mine:' 'fire laser' $C_MINE),(V 'Salv:' 'focused beam' $C_SALV))},
  @{Label='2';Primary='Launch missiles'},
  @{Label='3';Primary='Look behind (hold)'},
  @{Label='4';Primary='Missile-mode toggle';Variants=@((V 'Mine:' 'switch laser' $C_MINE))},
  @{Label='5';Primary='Lock target under reticle'},
  @{Label='6';Primary='Fire Guns - Group 2';Variants=@((V 'Salv:' 'salvage gimbal' $C_SALV))},
  @{Label='7';Primary='Countermeasure: decoy (flares)'},
  @{Label='8';Primary='Cycle hostiles forward';Variants=@((V 'Salv:' 'fracture beam' $C_SALV))},
  @{Label='9';Primary='Countermeasure: noise (chaff)'},
  @{Label='10';Primary='Cycle hostiles back';Variants=@((V 'Salv:' 'disintegrate' $C_SALV))},
  @{Label='11';Primary='Lock selected target';Variants=@((V 'Salv:' 'cycle modifiers' $C_SALV))},
  @{Label='12';Primary='Cycle sub-target forward'},
  @{Label='13';Primary='Cycle attackers forward'},
  @{Label='14';Primary='Cycle sub-target back'},
  @{Label='15';Primary='Cycle attackers back'}
)
$MHG_R = @(
  @{Header='GRIP 16-29'},
  @{Label='16';Primary='Gimbal lock toggle'},
  @{Label='17';Primary='Scan angle - narrow'},
  @{Label='18';Primary='Activate scanning (hold)'},
  @{Label='19';Primary='Scan angle - widen'},
  @{Label='20';Primary='Radar ping'},
  @{Label='21';Primary='ADS / cockpit zoom toggle'},
  @{Label='22';Primary='Weapon preset - next';Variants=@((V 'Msl:' 'type +' $C_NOTE),(V 'Mine:' 'pwr +' $C_MINE),(V 'Salv:' 'gap +' $C_SALV))},
  @{Label='23';Primary='Weapon preset - prev';Variants=@((V 'Msl:' 'type -' $C_NOTE),(V 'Mine:' 'pwr -' $C_MINE),(V 'Salv:' 'gap -' $C_SALV))},
  @{Label='24';Primary='Weapon aim-type cycle'},
  @{Label='25';Primary='Cycle all contacts forward'},
  @{Label='26';Primary='Snap-lock closest hostile'},
  @{Label='27';Primary='Cycle all contacts back'},
  @{Label='28';Primary='Cycle pinned forward'},
  @{Label='29';Primary='Pin target'}
)

# ================================================================ MTQ (js2 1-65 + axes)
$MTQ_L = @(
  @{Header='PANEL BUTTONS 1-30'},
  @{Label='1';Primary='Weapons power toggle';Hint='keypad A1'},
  @{Label='2';Primary='Thruster power toggle';Hint='A2'},
  @{Label='3';Primary='Shield power toggle';Hint='A3'},
  @{Label='4';Primary='LAMP night-vision toggle';Hint='A4'},
  @{Label='5';Primary='Master mode SCM / NAV';Hint='NAV key'},
  @{Label='6';Primary='Starmap';Hint='HDG key'},
  @{Label='7';Primary='Engage quantum drive';Hint='SPD key'},
  @{Label='8';Primary='Request landing / ATC';Hint='ALT key'},
  @{Label='9';Primary='Jump - inter-system';Hint='FD key'},
  @{Label='10';Primary='Autoland';Hint='AP key'},
  @{Label='11';Primary='Speed limiter -';Hint='upper enc CCW'},
  @{Label='12';Primary='Speed limiter +';Hint='upper enc CW'},
  @{Label='13';Primary='Speed limiter on / off';Hint='upper enc press'},
  @{Label='14';Primary='Accel / G limiter -';Hint='lower enc CCW'},
  @{Label='15';Primary='Accel / G limiter +';Hint='lower enc CW'},
  @{Label='16';Primary='G-force safety toggle';Hint='lower enc press'},
  @{Label='17';Primary='Guns mode';Hint='knob detent 1'},
  @{Label='18';Primary='Missile mode';Hint='knob detent 2'},
  @{Label='19';Primary='Scan mode';Hint='knob detent 3'},
  @{Label='20';Primary='Mining mode';Hint='knob detent 4'},
  @{Label='21';Primary='Salvage mode';Hint='knob detent 5'},
  @{Label='22';Primary='Rocker centre';Hint='rest';Unbound=$true},
  @{Label='23';Primary='Master power OFF';Hint='rocker left'},
  @{Label='24';Primary='Flight ready / power ON';Hint='rocker right'},
  @{Label='25';Primary='Unlock + open all doors';Hint='toggle A up'},
  @{Label='26';Primary='Lock + close all doors';Hint='toggle A down'},
  @{Label='27';Primary='Lights on';Hint='toggle B up'},
  @{Label='28';Primary='Lights off';Hint='toggle B down'},
  @{Label='29';Primary='Landing gear retract';Hint='gear lever up'},
  @{Label='30';Primary='Landing gear deploy';Hint='gear lever down'}
)
$MTQ_R = @(
  @{Header='BUTTONS 34-65'},
  @{Label='34';Primary='Throttle reverse / decrease';Hint='rear detent'},
  @{Label='31-43';Primary='unbound (analog axes)';Unbound=$true},
  @{Label='49';Primary='VTOL off';Hint='3-pos switch rest'},
  @{Label='50';Primary='VTOL on';Hint='3-pos switch fwd-latch'},
  @{Label='51';Primary='Space brake';Hint='3-pos switch back'},
  @{Label='56';Primary='Power to weapons';Hint='WPN hat up'},
  @{Label='55';Primary='Power to shields';Hint='WPN hat down'},
  @{Label='54';Primary='Power to engines';Hint='WPN hat left'},
  @{Label='53';Primary='Power allocation reset';Hint='WPN hat right'},
  @{Label='52';Primary='Power to shields MAX';Hint='WPN hat hold'},
  @{Label='61';Primary='Strafe up';Hint='COM hat up'},
  @{Label='60';Primary='Strafe down';Hint='COM hat down'},
  @{Label='59';Primary='Strafe left';Hint='COM hat left'},
  @{Label='58';Primary='Strafe right';Hint='COM hat right'},
  @{Label='57';Primary='Decoupled mode toggle';Hint='COM hat press'},
  @{Label='62';Primary='Cycle camera view';Hint='mini-stick press'},
  @{Label='63';Primary='Zoom in - cockpit';Hint='throttle dial fwd'},
  @{Label='64';Primary='Zoom out - cockpit';Hint='throttle dial back'},
  @{Label='65';Primary='Boost / afterburner';Hint='L-Module button'},
  @{Header='AXES'},
  @{Label='RY';Primary='Main throttle - forward';Hint='throttle lever'},
  @{Label='Slider';Primary='Mining laser power';Hint='FLAPS, Mining'},
  @{Label='Dial';Primary='Salvage beam spacing';Hint='S-brake, Salvage'},
  @{Label='X / Y';Primary='Camera look (yaw / pitch)';Hint='mini-stick'},
  @{Label='RX';Primary='Throttle twin';Hint='unbound';Unbound=$true}
)

# ================================================================ render
# Layout: LEFT ~60% of the sheet = images (two stacked quadrant bands - the two
# small views side by side on top, the one big view below); RIGHT ~40% = the
# lookup table in two columns. CanvasW:CanvasH = 11:8.5 (1.294) fills a Letter
# sheet in landscape. $F is dialled down so the narrow 40% table still fits.
# Geometry: image zone x=24..1064 (W=1040); table columns start at x=1090.
Write-Host "Rendering print cards (2x via $([IO.Path]::GetFileName($chrome)))..."

# --- Card 1: MHG grip + AB6 base (js1), combined ---
# Top band: the two grip views side by side (larger). Bottom band: the AB6 base
# (smaller - far fewer buttons). Base Frac kept below the grips' so it reads smaller.
$MHG_AB6_COL2 = $MHG_R + $AB6
New-Card @{ Name='MOZA_MHG_AB6_ref'; F=1.18; CanvasW=1860; CanvasH=1437;
  Title='MOZA MHG Grip + AB6 Base  -  Button Reference  (js1)';
  Sub="MHG grip 1-29 mounted on the AB6 base 49-62  $MID  trigger / hats / rocker / wings reused per operator mode";
  Stack=@{ X=24; W=1040; Gap=22; Rows=@(
    @{ HFrac=1.12; Imgs=@(
        @{D=$SUB_MHG_FRONT; Frac=0.56; VA='t'; Caption='MHG grip - front (hats & buttons)'},
        @{D=$SUB_MHG_SIDE;  Frac=0.44; VA='b'; Caption='MHG grip - side'}
    )},
    @{ HFrac=1.00; Imgs=@(
        @{D=$SUB_AB6_BASE;  Frac=0.53; VA='b'; Caption='AB6 base - wings & levers'}
    )}
  )};
  Cols=@( @{X=1090; W=370; Rows=$MHG_L}, @{X=1475; W=365; Rows=$MHG_AB6_COL2} );
  Legend="Combat (default)  $MID  Msl: Missile  $MID  Mine: Mining  $MID  Salv: Salvage.  One control = a different job per operator mode (set on the MTQ knob); AB6 wings 49-56 are targeting in combat, module/salvage banks in those modes." }

# --- Card 2: MTQ throttle (js2) ---
# Top band: the two module views side by side. Bottom band: the throttle panel
# (the big, button-dense view) below them.
New-Card @{ Name='MOZA_MTQ_ref'; F=1.15; CanvasW=1860; CanvasH=1437;
  Title='MOZA MTQ Throttle Panel  -  Button Reference  (js2)';
  Sub="throttle 1-65 + axes  $MID  buttons 44-48 are absent on the device";
  Stack=@{ X=24; W=1040; Gap=22; Rows=@(
    @{ HFrac=0.95; Imgs=@(
        @{D=$SUB_MTQ_RIGHT; Frac=0.52; VA='t'},
        @{D=$SUB_MTQ_LEFT;  Frac=0.52; VA='b'}
    )},
    @{ HFrac=1.30; Imgs=@(
        @{D=$SUB_MTQ_MAIN;  Frac=0.74; Caption='Throttle panel'}
    )}
  )};
  Cols=@( @{X=1090; W=370; Rows=$MTQ_L}, @{X=1475; W=365; Rows=$MTQ_R} );
  Legend="Throttle forward = axis (RY); reverse = rear-detent button 34.  FLAPS & Speedbrake levers drive analog axes (Slider / Dial) in Mining / Salvage modes; their click detents (31-43) are unbound." }

Write-Host "Done -> MOZA_MHG_AB6_ref, MOZA_MTQ_ref (.png + .svg) in $cardDir"
