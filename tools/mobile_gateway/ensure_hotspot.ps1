param([Parameter(Mandatory=$true)][string]$Provisioning,[Parameter(Mandatory=$true)][string]$PrivateDirectory)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$privateRoot=[IO.Path]::GetFullPath((Join-Path $root '.local\mid\H-017'))+[IO.Path]::DirectorySeparatorChar
$inputPath=[IO.Path]::GetFullPath($Provisioning)
$sessionPath=[IO.Path]::GetFullPath($PrivateDirectory)
foreach ($path in @($inputPath,$sessionPath)) {if (-not $path.StartsWith($privateRoot,[StringComparison]::OrdinalIgnoreCase)) {throw 'Hotspot paths must stay in private H-017 storage.'}}
$expected=(Get-Content -LiteralPath $inputPath -Raw|ConvertFrom-Json).command
if ($expected.cmd -ne 'ip_config' -or $expected.pc_id -ne 310031) {throw 'Existing private board configuration required.'}
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]
$null=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
$profile=[Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $profile) {throw 'No shareable upstream connection; hotspot not changed.'}
$manager=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
$configuration=$manager.GetCurrentAccessPointConfiguration()
if ($configuration.Ssid -cne $expected.ssid -or $configuration.Passphrase -cne $expected.password) {throw 'Hotspot credentials differ from provisioned boards; credentials and boards were preserved.'}
$before=$manager.TetheringOperationalState.ToString()
$helper=Join-Path $root 'tools\mid_hardware\field_agent'
$started=$false
if ($before -eq 'Off') {
    $answer=& (Join-Path $helper 'hotspot_session.ps1') -Action Start -PrivateDirectory $sessionPath | ConvertFrom-Json
    if ($answer.state_after -ne 'On') {throw 'Hotspot did not become active.'}
    $started=$true
} elseif ($before -ne 'On') {throw 'Hotspot already transitioning; existing session preserved. Try again once ready.'}
$deadline=[DateTime]::UtcNow.AddSeconds(15)
do {
    $public=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $helper 'hotspot_observe.ps1') -PrivateDirectory $sessionPath
    if ($LASTEXITCODE -ne 0) {throw 'Actual hotspot inspection failed.'}
    $observation=Get-Content -LiteralPath (Join-Path $sessionPath 'ap-observation.private.json') -Raw|ConvertFrom-Json
    if ($observation.pc_ip -and $observation.actual_channel -and $observation.actual_bssid) {break}
    Start-Sleep -Milliseconds 300
} while ([DateTime]::UtcNow -lt $deadline)
if ($observation.pc_ip -ne $expected.pc_ip -or $observation.actual_channel -ne $expected.channel -or $observation.actual_bssid -cne $expected.bssid) {throw 'Actual hotspot channel/BSSID/IP differ from provisioned boards; no board settings were changed.'}
[pscustomobject]@{ready=$true;state='On';started_by_launcher=$started;actual_channel=$observation.actual_channel;board_configuration_matches=$true;credentials_logged=$false;board_commands=0}|ConvertTo-Json -Compress
