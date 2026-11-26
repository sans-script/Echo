# Screenshots of the demo site into docs/img, at 2x for crisp text. Rebuilds the demo first so its times are fresh.
python "$PSScriptRoot\make_demo.py"
$edge = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
$site = "file:///" + ((Resolve-Path "$PSScriptRoot\site\index.html").Path -replace '\\', '/')
$img = (New-Item -ItemType Directory -Force "$PSScriptRoot\..\img").FullName
$monitor = Get-CimInstance Win32_VideoController | Select-Object -First 1
$dpi = (Get-ItemProperty 'HKCU:\Control Panel\Desktop' -Name LogPixels -ErrorAction SilentlyContinue).LogPixels
$scale = if ($dpi -and $dpi -ge 96) { [math]::Round($dpi / 96, 3) } else { 1 }
$screenWidth = $monitor.CurrentHorizontalResolution
$screenHeight = $monitor.CurrentVerticalResolution
$viewportWidth = [math]::Round($screenWidth / $scale)
$viewportHeight = [math]::Round($screenHeight / $scale)
$shots = [ordered]@{ overview = ''; agent = 'agent:Aaron'; usage = 'agent:Cypher'; group = 'room'; settings = 'settings'; chats = 'chats:Aaron' }
foreach ($k in $shots.Keys) {
  $out = Join-Path $img "$k.png"
  # A fresh profile each time: a running or lingering Edge would take the command and exit without a screenshot.
  $profile = Join-Path $env:TEMP "echo-shot-$k"
  # Chromium uses CSS pixels while Windows scales the monitor. Match its logical
  # viewport and device scale so content fills the captured monitor just as it does in Echo.
  Start-Process $edge -Wait -ArgumentList '--headless=new', '--disable-gpu', "--user-data-dir=$profile", '--allow-file-access-from-files',
    "--force-device-scale-factor=$scale", "--window-size=$viewportWidth,$viewportHeight", '--virtual-time-budget=3000', "--screenshot=$out", "$site`?view=$($shots[$k])"
  Write-Output "$k $(if (Test-Path $out) { (Get-Item $out).Length } else { 'missing' })"
}
