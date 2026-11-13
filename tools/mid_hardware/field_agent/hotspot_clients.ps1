param([Parameter(Mandatory=$true)][string]$FlashResult)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]
$null=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
$known=Get-Content -LiteralPath $FlashResult -Raw|ConvertFrom-Json
$ids=@($known.boards|ForEach-Object {$_.result.mac})
$profile=[Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
$manager=[Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
$clients=@($manager.GetTetheringClients())
$macs=@($clients|ForEach-Object {($_.MacAddress.ToLower() -replace '[^0-9a-f]','') -replace '(.{2})(?=.)','$1:'})
$rows=@($known.boards|ForEach-Object {[pscustomobject]@{label=$_.label;node_id=$_.result.mac;associated=($macs -contains $_.result.mac)}})
[pscustomobject]@{checked_utc=[DateTime]::UtcNow.ToString('o');source='Windows NetworkOperatorTetheringManager.GetTetheringClients';hotspot_state=$manager.TetheringOperationalState.ToString();project_boards=$rows;unrelated_client_details_omitted=$true;SSID_logged=$false;password_logged=$false}|ConvertTo-Json -Depth 5 -Compress
