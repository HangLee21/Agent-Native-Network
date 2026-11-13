param(
    [ValidateSet('Start','Inspect','Stop')][string]$Action='Inspect',
    [Parameter(Mandatory=$true)][string]$PrivateDirectory
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
Add-Type -AssemblyName System.Security
$null=[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]
$null=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
$null=[Windows.Foundation.Metadata.ApiInformation,Windows.Foundation,ContentType=WindowsRuntime]
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$allowedRoot=[IO.Path]::GetFullPath((Join-Path $taskRoot '.local\mid\H-017'))+[IO.Path]::DirectorySeparatorChar
$privatePath=[IO.Path]::GetFullPath($PrivateDirectory)
if (-not ($privatePath+[IO.Path]::DirectorySeparatorChar).StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase)) {throw 'Private directory must be inside .local/mid/H-017.'}
[IO.Directory]::CreateDirectory($privatePath)|Out-Null
function Await-Result($operation,[Type]$resultType) {
    $method=[System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'}|Select-Object -First 1
    $task=$method.MakeGenericMethod($resultType).Invoke($null,@($operation))
    if (-not $task.Wait(25000)) {throw 'WinRT operation timed out; inspect and restore hotspot state.'}
    return $task.Result
}
$connection=[Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $connection) {throw 'No active upstream profile; no hotspot change.'}
$manager=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connection)
$current=$manager.GetCurrentAccessPointConfiguration()
$state=$manager.TetheringOperationalState.ToString()
$upstream=[pscustomobject]@{adapter_id=$connection.NetworkAdapter.NetworkAdapterId.ToString();connectivity=$connection.GetNetworkConnectivityLevel().ToString()}
$result=[ordered]@{action=$Action;state_before=$state;upstream=$upstream;configuration_band_before=$current.Band.ToString();credentials_printed=$false;board_access=$false}
if ($Action -eq 'Start') {
    if ($state -ne 'Off') {throw 'Hotspot already active/in transition; existing session preserved, no restart.'}
    $snapshot=Join-Path $privatePath 'original.dpapi'
    if (Test-Path -LiteralPath $snapshot) {throw 'Private snapshot already exists; preserve old session record.'}
    $plain=[pscustomobject]@{ssid=$current.Ssid;password=$current.Passphrase;band=$current.Band.ToString();authentication=$current.AuthenticationKind.ToString();original_state=$state;upstream=$upstream}
    $bytes=[Text.Encoding]::UTF8.GetBytes(($plain|ConvertTo-Json -Depth 5))
    $encrypted=[Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    [IO.File]::WriteAllBytes($snapshot,$encrypted)
    $typeName='Windows.Networking.NetworkOperators.NetworkOperatorTetheringSessionAccessPointConfiguration'
    if (-not [Windows.Foundation.Metadata.ApiInformation]::IsTypePresent($typeName)) {throw 'Per-session hotspot configuration unsupported; persistent settings unchanged.'}
    $null=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringSessionAccessPointConfiguration,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
    $session=New-Object Windows.Networking.NetworkOperators.NetworkOperatorTetheringSessionAccessPointConfiguration
    $session.Ssid=$plain.ssid
    $session.Passphrase=$plain.password
    $session.Band=[Windows.Networking.NetworkOperators.TetheringWiFiBand]::TwoPointFourGigahertz
    $session.AuthenticationKind=$current.AuthenticationKind
    $op=$manager.StartTetheringAsync($session)
    $answer=Await-Result $op ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime])
    $result.operation_status=$answer.Status.ToString()
    if ($answer.Status.ToString() -ne 'Success') {throw ('Hotspot start failed: '+$answer.Status.ToString())}
    $result.requested_session_band='TwoPointFourGigahertz'
    $result.persistent_configuration_changed=$false
    [IO.File]::WriteAllText((Join-Path $privatePath 'session-owned.json'),([pscustomobject]@{owned=$true;started_utc=[DateTime]::UtcNow.ToString('o');original_state='Off';requested_band='TwoPointFourGigahertz'}|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
} elseif ($Action -eq 'Stop') {
    $ownedPath=Join-Path $privatePath 'session-owned.json'
    if (-not (Test-Path -LiteralPath $ownedPath)) {throw 'No owned session record; no hotspot stopped.'}
    $owned=Get-Content -LiteralPath $ownedPath -Raw|ConvertFrom-Json
    if (-not $owned.owned -or $owned.original_state -ne 'Off') {throw 'Session ownership guard failed.'}
    if ($state -ne 'Off') {
        $answer=Await-Result ($manager.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime])
        $result.operation_status=$answer.Status.ToString()
        if ($answer.Status.ToString() -ne 'Success') {throw ('Hotspot stop failed: '+$answer.Status.ToString())}
    }
    $originalBytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $privatePath 'original.dpapi')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
    $original=[Text.Encoding]::UTF8.GetString($originalBytes)|ConvertFrom-Json
    $afterConfiguration=$manager.GetCurrentAccessPointConfiguration()
    $result.configuration_band_after=$afterConfiguration.Band.ToString()
    $result.original_configuration_retained=($afterConfiguration.Ssid -ceq $original.ssid -and $afterConfiguration.Passphrase -ceq $original.password -and $afterConfiguration.Band.ToString() -eq $original.band -and $afterConfiguration.AuthenticationKind.ToString() -eq $original.authentication)
    if (-not $result.original_configuration_retained) {throw 'Persistent configuration unexpectedly changed; retain snapshot for explicit recovery.'}
}
$result.state_after=$manager.TetheringOperationalState.ToString()
$afterConnection=[Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
$result.upstream_after=[pscustomobject]@{adapter_id=$afterConnection.NetworkAdapter.NetworkAdapterId.ToString();connectivity=$afterConnection.GetNetworkConnectivityLevel().ToString()}
$result.upstream_profile_unchanged=($result.upstream.adapter_id -eq $result.upstream_after.adapter_id)
$result|ConvertTo-Json -Depth 5 -Compress
