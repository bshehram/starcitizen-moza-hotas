<#
  regen_cards.ps1 - Regenerates the MOZA button-reference cards.

  This script lives in tools/. It reads the manufacturer diagrams from
  ../diagrams/ and writes the cards to ../cards/. Produces three landscape PNG
  "cheat sheet" cards (and their self-contained SVG sources), one per device:

      cards/MOZA_AB6_ref.png / .svg   (js1 base buttons 49-62)
      cards/MOZA_MHG_ref.png / .svg   (js1 grip buttons 1-29)
      cards/MOZA_MTQ_ref.png / .svg   (js2 throttle buttons 1-65 + axes)

  Each card = the manufacturer button-number diagram (recolored to a white
  background) on the left, plus a number -> function lookup table on the right.

  HOW IT WORKS
    1. The numbered diagram comes straight from the manufacturer PNGs
       (diagrams/MOZA_AB6.png / MOZA_MHG.png / MOZA_MTQ.png). Those already have every
       button numbered with a leader line pointing at the physical control, so
       the numbers are always placed correctly - we never hand-place them.
       Recolor = grayscale + invert + a levels stretch (dark navy bg -> white,
       faint light line-art -> crisp dark). A top strip is cropped to drop the
       "Button Number" header.
    2. The lookup table is the $AB6 / $MHG / $MTQ data arrays below. This is the
       ONLY thing you edit when a binding changes - see "UPDATING" and CLAUDE.md.
    3. Each card is emitted as an SVG (white bg, embedded recolored diagram as a
       base64 PNG, table drawn as text/rects) and rendered to PNG at 2x with
       headless Chrome/Edge.

  UPDATING AFTER A BINDING CHANGE
    Change MOZA.xml, then edit the matching row in the $AB6 / $MHG / $MTQ array
    here (Primary = function, Hint = where the control is, Variants = the
    mining/salvage/missile alternates for the same physical button) and re-run
    (from the project root):

        powershell -ExecutionPolicy Bypass -File .\tools\regen_cards.ps1

    You only touch the manufacturer PNGs / crop values if MOZA ships a new device
    diagram. Button numbers and leader lines need no edits - they ride along in
    the diagram.

  REQUIREMENTS: Windows PowerShell + .NET System.Drawing, and Chrome or Edge.
#>

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$repo    = Split-Path -Parent $root     # the mappings/ project root (this script lives in tools/)
$diagDir = Join-Path $repo 'diagrams'   # manufacturer source PNGs (input)
$cardDir = Join-Path $repo 'cards'      # generated reference cards (output)

# Locate a Chromium browser to rasterize the SVGs.
$chrome = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { throw "regen_cards: no Chrome/Edge found to render SVG -> PNG." }

$MID = [char]0x00B7   # middle dot, by code-point so this .ps1 stays pure ASCII

# ---- palette ----
$C_TITLE='#0f1720'; $C_SUB='#5b6b7a'; $C_PRIM='#16202b'; $C_VARTXT='#5b6b7a'; $C_HINT='#8a96a2'
$C_BADGE='#1f2933'; $C_BADGE_UNB='#cdd5dd'
$C_RULE='#d7dee5'; $C_ROWALT='#f4f7fa'
$C_MINE='#9a6a00'; $C_SALV='#0f6e6e'; $C_NOTE='#6b7681'

function Esc($s){ if($null -eq $s){return ''}; ([string]$s) -replace '&','&amp;' -replace '<','&lt;' -replace '>','&gt;' }
function V($tag,$text,$color){ @{ Tag=$tag; Text=$text; Color=$color } }

# Recolor a manufacturer diagram to white-bg line art + crop, return @{B64;W;H}.
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

# Append one table row at (x,y). Returns the height it consumed.
function Add-Row($sb,$x,$y,$colW,$row,$idx){
  $label = [string]$row.Label
  $unb = [bool]$row.Unbound
  $hasVar = ($null -ne $row.Variants -and $row.Variants.Count -gt 0)
  $rowH = 27; if($hasVar){ $rowH += 16 }
  if($idx % 2 -eq 1){ [void]$sb.Append("<rect x='$($x-6)' y='$y' width='$colW' height='$rowH' fill='$C_ROWALT'/>") }
  $badgeW = 30; if($label.Length -gt 2){ $badgeW = 14 + $label.Length*7.5 }
  $by = $y + 4
  $bfill = if($unb){$C_BADGE_UNB}else{$C_BADGE}
  $btxt  = if($unb){'#5b6671'}else{'#ffffff'}
  [void]$sb.Append("<rect x='$x' y='$by' width='$([math]::Round($badgeW,1))' height='20' rx='4' fill='$bfill'/>")
  [void]$sb.Append("<text x='$([math]::Round($x+$badgeW/2,1))' y='$($by+14.5)' font-size='12' font-weight='700' text-anchor='middle' fill='$btxt'>$(Esc $label)</text>")
  $tx = $x + $badgeW + 11
  $ptxtcol = if($unb){$C_HINT}else{$C_PRIM}
  $pweight = if($unb){'400'}else{'600'}
  [void]$sb.Append("<text x='$([math]::Round($tx,1))' y='$($y+18)' font-size='13'><tspan font-weight='$pweight' fill='$ptxtcol'>$(Esc $row.Primary)</tspan>")
  if($row.Hint){ [void]$sb.Append("<tspan font-weight='400' font-size='11.5' fill='$C_HINT'>  ($(Esc $row.Hint))</tspan>") }
  [void]$sb.Append("</text>")
  if($hasVar){
    [void]$sb.Append("<text x='$([math]::Round($tx,1))' y='$($y+34)' font-size='10.5'>")
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

# Build one card SVG + render to PNG (2x).
function New-Card($cfg){
  $sb = New-Object System.Text.StringBuilder
  $CW=$cfg.CanvasW; $CH=$cfg.CanvasH
  [void]$sb.Append("<svg xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink' width='$CW' height='$CH' viewBox='0 0 $CW $CH' font-family='Segoe UI, Arial, sans-serif'>")
  [void]$sb.Append("<rect width='$CW' height='$CH' fill='#ffffff'/>")
  [void]$sb.Append("<text x='34' y='46' font-size='29' font-weight='700' fill='$C_TITLE'>$(Esc $cfg.Title)</text>")
  [void]$sb.Append("<text x='34' y='70' font-size='14' fill='$C_SUB'>$(Esc $cfg.Sub)</text>")
  [void]$sb.Append("<line x1='34' y1='84' x2='$($CW-34)' y2='84' stroke='$C_RULE' stroke-width='1.5'/>")
  $d = $cfg.Diagram
  $dw = $cfg.DiagW; $dh = [int]($d.H * ($dw / $d.W))
  [void]$sb.Append("<image xlink:href='data:image/png;base64,$($d.B64)' x='$($cfg.DiagX)' y='$($cfg.DiagY)' width='$dw' height='$dh'/>")
  foreach($col in $cfg.Cols){
    $cy = $col.Y; $i = 0
    foreach($r in $col.Rows){
      if($r.Header){
        [void]$sb.Append("<text x='$($col.X)' y='$($cy+14)' font-size='12' font-weight='700' fill='$C_SUB' letter-spacing='0.6'>$(Esc $r.Header)</text>")
        [void]$sb.Append("<line x1='$($col.X)' y1='$($cy+21)' x2='$($col.X+$col.W-12)' y2='$($cy+21)' stroke='$C_RULE' stroke-width='1'/>")
        $cy += 30; $i=0; continue
      }
      $rh = Add-Row $sb $col.X $cy $col.W $r $i
      $cy += $rh; $i++
    }
  }
  if($cfg.Legend){ [void]$sb.Append("<text x='34' y='$($CH-18)' font-size='11.5' fill='$C_NOTE'>$(Esc $cfg.Legend)</text>") }
  [void]$sb.Append("</svg>")
  $svgPath = Join-Path $cardDir ($cfg.Name + ".svg")
  [IO.File]::WriteAllText($svgPath, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
  $pngPath = Join-Path $cardDir ($cfg.Name + ".png")
  $uri = "file:///" + ($svgPath -replace '\\','/')
  # Start-Process (not the call operator) so Chrome's stderr "NNN bytes written"
  # message doesn't get escalated to a terminating NativeCommandError on PS 5.1.
  $argv = @('--headless=new','--disable-gpu','--no-sandbox','--hide-scrollbars',
            "--screenshot=$pngPath","--window-size=$CW,$CH",'--force-device-scale-factor=2',$uri)
  $errF = [IO.Path]::GetTempFileName(); $outF = [IO.Path]::GetTempFileName()
  Start-Process -FilePath $chrome -ArgumentList $argv -Wait -NoNewWindow -RedirectStandardError $errF -RedirectStandardOutput $outF | Out-Null
  try { [IO.File]::Delete($errF); [IO.File]::Delete($outF) } catch {}
  if(Test-Path $pngPath){ $o=[System.Drawing.Image]::FromFile($pngPath); Write-Host ("  {0,-16} {1}x{2}" -f ($cfg.Name+'.png'), $o.Width, $o.Height); $o.Dispose() }
  else { throw "regen_cards: render failed for $($cfg.Name)." }
}

# ================================================================ recolor diagrams
# levels: black=0.45 white=0.85 (tuned for the MOZA navy diagrams).
# crop:  top strip removes the "Button Number" header; 8px off the bottom.
Write-Host "Recoloring manufacturer diagrams..."
$DIAG_AB6 = Get-Diagram 'MOZA_AB6.png' 0.45 0.85 72 0 0 8
$DIAG_MHG = Get-Diagram 'MOZA_MHG.png' 0.45 0.85 52 0 0 8
$DIAG_MTQ = Get-Diagram 'MOZA_MTQ.png' 0.45 0.85 64 0 0 8

# ================================================================ AB6 (js1 49-62)
$AB6 = @(
  @{Header='BASE BUTTONS  -  role changes with operator mode'},
  @{Label='49';Primary='Target: cycle in-view forward';Variants=@((V 'Mine:' 'mining module 1' $C_MINE),(V 'Salv:' 'focus all heads' $C_SALV))},
  @{Label='50';Primary='Target: cycle in-view back';Variants=@((V 'Mine:' 'mining module 2' $C_MINE),(V 'Salv:' 'focus left head' $C_SALV))},
  @{Label='51';Primary='Target: lock closest (any)';Variants=@((V 'Mine:' 'mining module 3' $C_MINE),(V 'Salv:' 'focus right head' $C_SALV))},
  @{Label='52';Primary='Target: lock closest attacker';Variants=@((V 'Mine:' 'jettison volatile cargo' $C_MINE),(V 'Salv:' 'toggle beam axis H/V' $C_SALV))},
  @{Label='53';Primary='Target: cycle friendly forward';Variants=@((V 'Salv:' 'toggle-fire left beam' $C_SALV))},
  @{Label='54';Primary='Target: cycle friendly back';Variants=@((V 'Salv:' 'toggle-fire right beam' $C_SALV))},
  @{Label='55';Primary='Target: cycle pinned back';Variants=@((V 'Salv:' 'reset salvage gimbal' $C_SALV))},
  @{Label='56';Primary='Target: reset sub-target';Variants=@((V 'Salv:' 'cycle structural modes' $C_SALV))},
  @{Label='57-59';Primary='Left "Slider" lever';Hint='unbound - analog, reserved';Unbound=$true},
  @{Label='60-62';Primary='Right "Dial" lever';Hint='unbound - analog, reserved';Unbound=$true}
)

# ================================================================ MHG (js1 1-29)
$MHG_L = @(
  @{Header='GRIP BUTTONS 1-15'},
  @{Label='1';Primary='Fire Guns - Group 1';Variants=@((V 'Mine:' 'fire mining laser' $C_MINE),(V 'Salv:' 'fire focused beam' $C_SALV))},
  @{Label='2';Primary='Launch missiles'},
  @{Label='3';Primary='Freelook (hold)'},
  @{Label='4';Primary='Missile-mode toggle';Variants=@((V 'Mine:' 'switch mining laser' $C_MINE))},
  @{Label='5';Primary='Lock target under reticle'},
  @{Label='6';Primary='Fire Guns - Group 2';Variants=@((V 'Salv:' 'toggle salvage gimbal' $C_SALV))},
  @{Label='7';Primary='Countermeasure: decoy (flares)'},
  @{Label='8';Primary='Cycle hostiles forward';Variants=@((V 'Salv:' 'fire fracture beam' $C_SALV))},
  @{Label='9';Primary='Countermeasure: noise (chaff)'},
  @{Label='10';Primary='Cycle hostiles back';Variants=@((V 'Salv:' 'fire disintegrate beam' $C_SALV))},
  @{Label='11';Primary='Lock selected target';Variants=@((V 'Salv:' 'cycle focused modifiers' $C_SALV))},
  @{Label='12';Primary='Cycle sub-target forward'},
  @{Label='13';Primary='Cycle attackers forward'},
  @{Label='14';Primary='Cycle sub-target back'},
  @{Label='15';Primary='Cycle attackers back'}
)
$MHG_R = @(
  @{Header='GRIP BUTTONS 16-29'},
  @{Label='16';Primary='Gimbal lock toggle'},
  @{Label='17';Primary='Scan angle - narrow'},
  @{Label='18';Primary='Activate scanning (hold)'},
  @{Label='19';Primary='Scan angle - widen'},
  @{Label='20';Primary='Radar ping'},
  @{Label='21';Primary='ADS / cockpit zoom toggle'},
  @{Label='22';Primary='Weapon preset - next';Variants=@((V 'Msl:' 'type next' $C_NOTE),(V 'Mine:' 'power +' $C_MINE),(V 'Salv:' 'spacing +' $C_SALV))},
  @{Label='23';Primary='Weapon preset - prev';Variants=@((V 'Msl:' 'type prev' $C_NOTE),(V 'Mine:' 'power -' $C_MINE),(V 'Salv:' 'spacing -' $C_SALV))},
  @{Label='24';Primary='Weapon aim-type cycle'},
  @{Label='25';Primary='Cycle all contacts forward'},
  @{Label='26';Primary='Snap-lock closest hostile'},
  @{Label='27';Primary='Cycle all contacts back'},
  @{Label='28';Primary='Cycle pinned forward'},
  @{Label='29';Primary='Pin target'}
)

# ================================================================ MTQ (js2 1-65 + axes)
$MTQ_L = @(
  @{Header='KEYPAD  /  ENCODERS  /  MODE KNOB  /  ROCKER  /  TOGGLES'},
  @{Label='1';Primary='Weapons power toggle';Hint='keypad A1'},
  @{Label='2';Primary='Thruster power toggle';Hint='A2'},
  @{Label='3';Primary='Shield power toggle';Hint='A3'},
  @{Label='4';Primary='LAMP night-vision toggle';Hint='A4'},
  @{Label='5';Primary='Master mode cycle SCM / NAV';Hint='NAV key'},
  @{Label='6';Primary='Starmap';Hint='HDG key'},
  @{Label='7';Primary='Engage quantum drive';Hint='SPD key'},
  @{Label='8';Primary='Autoland';Hint='ALT key'},
  @{Label='9';Primary='Jump - inter-system';Hint='FD key'},
  @{Label='10';Primary='Request landing / ATC';Hint='AP key'},
  @{Label='11';Primary='Speed limiter -';Hint='upper encoder CCW'},
  @{Label='12';Primary='Speed limiter +';Hint='upper encoder CW'},
  @{Label='13';Primary='Speed limiter on / off';Hint='upper encoder press'},
  @{Label='14';Primary='Accel / G limiter -';Hint='lower encoder CCW'},
  @{Label='15';Primary='Accel / G limiter +';Hint='lower encoder CW'},
  @{Label='16';Primary='G-force safety toggle';Hint='lower encoder press'},
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
  @{Header='THROTTLE  /  FLIGHT  /  POWER  /  VIEW'},
  @{Label='34';Primary='Throttle reverse / decrease';Hint='rear detent'},
  @{Label='31-43';Primary='FLAPS / Speedbrake / throttle detents';Hint='unbound - analog axes used instead';Unbound=$true},
  @{Label='49';Primary='VTOL off';Hint='3-pos switch rest'},
  @{Label='50';Primary='VTOL on';Hint='3-pos switch fwd-latch'},
  @{Label='51';Primary='Space brake';Hint='3-pos switch back'},
  @{Label='56';Primary='Power to weapons';Hint='WPN hat up'},
  @{Label='55';Primary='Power to shields';Hint='WPN hat down'},
  @{Label='54';Primary='Power to engines';Hint='WPN hat left'},
  @{Label='53';Primary='Power allocation reset';Hint='WPN hat right'},
  @{Label='52';Primary='Power to shields MAX (hold)';Hint='WPN hat press'},
  @{Label='61';Primary='Strafe up';Hint='COM hat up'},
  @{Label='60';Primary='Strafe down';Hint='COM hat down'},
  @{Label='59';Primary='Strafe left';Hint='COM hat left'},
  @{Label='58';Primary='Strafe right';Hint='COM hat right'},
  @{Label='57';Primary='Decoupled mode toggle';Hint='COM hat press'},
  @{Label='62';Primary='Cycle camera view';Hint='mini-stick press'},
  @{Label='63';Primary='Zoom in - cockpit';Hint='throttle dial fwd'},
  @{Label='64';Primary='Zoom out - cockpit';Hint='throttle dial back'},
  @{Label='65';Primary='Boost / afterburner';Hint='Left Module button'},
  @{Header='AXES'},
  @{Label='RY';Primary='Main throttle - forward';Hint='throttle lever'},
  @{Label='Slider';Primary='Mining laser power';Hint='FLAPS lever, Mining mode'},
  @{Label='Dial';Primary='Salvage beam spacing';Hint='Speedbrake lever, Salvage mode'},
  @{Label='X / Y';Primary='Camera look (yaw / pitch)';Hint='mini-stick'},
  @{Label='RX';Primary='Throttle twin';Hint='unbound - unused';Unbound=$true}
)

# ================================================================ render
Write-Host "Rendering cards (2x via $([IO.Path]::GetFileName($chrome)))..."
New-Card @{ Name='MOZA_AB6_ref'; Title='MOZA AB6 FFB Base  -  Button Reference';
  Sub="js1 base, buttons 49-62  $MID  left wing 49-52, right wing 53-56  $MID  the same 8 buttons change job with the operator mode";
  Diagram=$DIAG_AB6; DiagW=840; DiagX=30; DiagY=104; CanvasW=1500; CanvasH=740;
  Cols=@( @{X=905; Y=120; W=560; Rows=$AB6} );
  Legend="Combat = targeting bank   $MID   Mine: = Mining mode   $MID   Salv: = Salvage mode.  Operator mode is selected on the MTQ rotary knob.  The two levers also drive analog axes (mining laser power / salvage beam spacing) reported on the throttle device." }

New-Card @{ Name='MOZA_MHG_ref'; Title='MOZA MHG Grip  -  Button Reference';
  Sub="js1 grip, buttons 1-29  $MID  mounted on the AB6 base  $MID  trigger / hats / rocker reused per operator mode";
  Diagram=$DIAG_MHG; DiagW=900; DiagX=26; DiagY=102; CanvasW=1960; CanvasH=812;
  Cols=@( @{X=965; Y=118; W=470; Rows=$MHG_L}, @{X=1465; Y=118; W=470; Rows=$MHG_R} );
  Legend="Combat (default)   $MID   Msl: = Missile mode   $MID   Mine: = Mining mode   $MID   Salv: = Salvage mode.  One physical control does a different job per operator mode (set on the MTQ knob); only one is ever live at a time." }

New-Card @{ Name='MOZA_MTQ_ref'; Title='MOZA MTQ Throttle Panel  -  Button Reference';
  Sub="js2 throttle, buttons 1-65 + axes  $MID  buttons 44-48 are absent on the device";
  Diagram=$DIAG_MTQ; DiagW=950; DiagX=26; DiagY=100; CanvasW=2000; CanvasH=1000;
  Cols=@( @{X=1010; Y=112; W=445; Rows=$MTQ_L}, @{X=1470; Y=112; W=505; Rows=$MTQ_R} );
  Legend="Throttle forward = axis (RY); reverse = rear-detent button 34.  The FLAPS & Speedbrake levers drive analog axes (Slider / Dial) in Mining / Salvage modes - their click detents (31-43) are left unbound." }

Write-Host "Done -> MOZA_AB6_ref, MOZA_MHG_ref, MOZA_MTQ_ref (.png + .svg) in $cardDir"
