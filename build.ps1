# Builds Echo (Echo.exe) and installs it to %LOCALAPPDATA%\Programs\Echo (Start Menu shortcut kept).
$ErrorActionPreference = 'Stop'
$src = $PSScriptRoot
$out = Join-Path $env:LOCALAPPDATA 'Programs\Echo'
Add-Type -AssemblyName System.Drawing

# App icon: the gauge glyph (white arc on black rounded square), PNG-in-ICO at 256 px.
$ico = Join-Path $src 'app.ico'
$bmp = New-Object System.Drawing.Bitmap 256, 256
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = 'AntiAlias'
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$r = 56; $path.AddArc(0, 0, $r, $r, 180, 90); $path.AddArc(256 - $r, 0, $r, $r, 270, 90); $path.AddArc(256 - $r, 256 - $r, $r, $r, 0, 90); $path.AddArc(0, 256 - $r, $r, $r, 90, 90); $path.CloseFigure()
$g.FillPath([System.Drawing.Brushes]::Black, $path)
$track = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(70, 255, 255, 255)), 26
$arc = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), 26
$arc.StartCap = 'Round'; $arc.EndCap = 'Round'
$g.DrawEllipse($track, 58, 58, 140, 140)
$g.DrawArc($arc, 58, 58, 140, 140, -90, 245)
$ms = New-Object System.IO.MemoryStream; $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png); $png = $ms.ToArray()
$fs = [System.IO.File]::Create($ico); $w = New-Object System.IO.BinaryWriter $fs
$w.Write([uint16]0); $w.Write([uint16]1); $w.Write([uint16]1)
$w.Write([byte]0); $w.Write([byte]0); $w.Write([byte]0); $w.Write([byte]0); $w.Write([uint16]1); $w.Write([uint16]32)
$w.Write([uint32]$png.Length); $w.Write([uint32]22); $w.Write($png); $w.Close()

# Compile.
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$exe = Join-Path $src 'Echo.exe'
& $csc /nologo /target:winexe /platform:x64 /optimize+ "/out:$exe" "/win32icon:$ico" `
    /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll /r:System.Net.Http.dll /r:System.Security.dll `
    "/r:$src\lib\Microsoft.Web.WebView2.Core.dll" "/r:$src\lib\Microsoft.Web.WebView2.WinForms.dll" `
    "$src\Echo.cs"
if ($LASTEXITCODE) { throw "csc failed ($LASTEXITCODE)" }

# Install (stop the running copy first so files are not locked).
Get-Process Echo, AgentMonitor -ErrorAction SilentlyContinue | Stop-Process -Force
# The old install (AgentMonitor) goes; Echo moves its data folder on first start.
$old = Join-Path $env:LOCALAPPDATA 'Programs\AgentMonitor'
if (Test-Path $old) { Start-Sleep -Milliseconds 500; Remove-Item $old -Recurse -Force }
Remove-Item (Join-Path $src 'AgentMonitor.exe') -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item $exe, "$src\lib\*.dll" $out -Force
if (Test-Path "$out\ui") { Remove-Item "$out\ui" -Recurse -Force }
Copy-Item "$src\ui" "$out\ui" -Recurse
# The Python side ships with Echo, which copies it into the configured scripts folder on start.
New-Item -ItemType Directory -Force "$out\scripts" | Out-Null
Copy-Item "$src\snapshot.py", "$src\send.py", "$src\convs.py" "$out\scripts" -Force
# Portable copy for other machines: unzip anywhere and run Echo.exe (needs the WebView2 runtime).
$zip = Join-Path $src 'dist\Echo-portable.zip'
New-Item -ItemType Directory -Force (Split-Path $zip) | Out-Null
Compress-Archive -Path "$out\*" -DestinationPath $zip -Force
Write-Host "Portable zip: $zip"
Write-Host "Installed to $out"

# Start Menu shortcut, named after the app (Echo); the old "Agent Monitor" one is replaced.
$menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
Remove-Item (Join-Path $menu 'Agent Monitor.lnk') -ErrorAction SilentlyContinue
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $menu 'Echo.lnk'))
$lnk.TargetPath = Join-Path $out 'Echo.exe'; $lnk.WorkingDirectory = $out; $lnk.Save()
