$ErrorActionPreference = 'Stop'
# Read only. SSID/passphrase are deliberately not accessed or printed.
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
$connection = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
if ($null -eq $connection) {
    [pscustomobject]@{active_profile=$false;hotspot_changed=$false;credentials_read=$false;status='no_active_profile'} | ConvertTo-Json -Compress
    exit 1
}
$capability = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::GetTetheringCapabilityFromConnectionProfile($connection)
$manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($connection)
$configuration = $manager.GetCurrentAccessPointConfiguration()
[pscustomobject]@{active_profile=$true;capability=$capability.ToString();operational_state=$manager.TetheringOperationalState.ToString();configured_band=$configuration.Band.ToString();hotspot_changed=$false;credentials_read=$false;actual_AP_channel=$null;actual_BSSID=$null;note='Configuration band is not an RF measurement of channel/BSSID.'} | ConvertTo-Json -Compress
