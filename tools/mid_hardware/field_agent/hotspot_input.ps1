param(
    [Parameter(Mandatory=$true)][string]$PrivateDirectory,
    [ValidateRange(1,4294967295)][long]$PcId=310031,
    [ValidateRange(1024,65535)][int]$PcPort=8793,
    [ValidateRange(1024,65535)][int]$EntryPort=8792
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Security
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$allowedRoot=[IO.Path]::GetFullPath((Join-Path $taskRoot '.local\mid\H-017'))+[IO.Path]::DirectorySeparatorChar
$privatePath=[IO.Path]::GetFullPath($PrivateDirectory)
if (-not ($privatePath+[IO.Path]::DirectorySeparatorChar).StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase)) {throw 'Private directory must stay inside .local/mid/H-017.'}
$observation=Get-Content -LiteralPath (Join-Path $privatePath 'ap-observation.private.json') -Raw|ConvertFrom-Json
if (-not $observation.pc_ip -or $observation.actual_channel -notin 1..13 -or -not $observation.actual_bssid) {throw 'Actual AP IP/channel/BSSID missing; no usable board input generated.'}
if ($observation.actual_bssid -notmatch '^([0-9a-f]{2}:){5}[0-9a-f]{2}$') {throw 'Invalid actual AP BSSID.'}
$originalBytes=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes((Join-Path $privatePath 'original.dpapi')),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
$original=[Text.Encoding]::UTF8.GetString($originalBytes)|ConvertFrom-Json
# Private provisioning file: owner and SYSTEM only; no inherited broad workspace ACL.
$owner=[Security.Principal.WindowsIdentity]::GetCurrent().User
$security=New-Object Security.AccessControl.DirectorySecurity
$security.SetOwner($owner)
$security.SetAccessRuleProtection($true,$false)
$inherit=[Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
$propagation=[Security.AccessControl.PropagationFlags]::None
$allow=[Security.AccessControl.AccessControlType]::Allow
foreach ($sid in @($owner,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
    $rule=[Security.AccessControl.FileSystemAccessRule]::new($sid,[Security.AccessControl.FileSystemRights]::FullControl,$inherit,$propagation,$allow)
    $security.AddAccessRule($rule)|Out-Null
}
Set-Acl -LiteralPath $privatePath -AclObject $security
$path=Join-Path $privatePath 'board-ip-config.private.json'
if (Test-Path -LiteralPath $path) {throw 'Provisioning input already exists; preserve observed session.'}
$command=[ordered]@{cmd='ip_config';enabled=$true;ssid=$original.ssid;password=$original.password;bssid=$observation.actual_bssid;channel=[int]$observation.actual_channel;pc_ip=$observation.pc_ip;pc_port=$PcPort;listen_port=$EntryPort;pc_id=$PcId}
$document=[ordered]@{schema='H017.private.field.ip.v2.provisioning';observed_utc=[DateTime]::UtcNow.ToString('o');requires_refresh_after_hotspot_restart=$true;board_radio_must_be_stopped=$true;ap_interface=$observation.ap_interface_id;channel_source=$observation.channel_source;bssid_source=$observation.bssid_source;command=$command}
[IO.File]::WriteAllText($path,($document|ConvertTo-Json -Depth 7),[Text.UTF8Encoding]::new($false))
[pscustomobject]@{private_input_created=$true;owner_only_ACL=$true;DPAPI_original=$true;pc_ip=$observation.pc_ip;channel=$observation.actual_channel;pc_id=$PcId;pc_port=$PcPort;entry_port=$EntryPort;SSID_printed=$false;password_printed=$false;bssid_printed=$false;board_commands=0;requires_refresh_after_hotspot_restart=$true}|ConvertTo-Json -Compress
