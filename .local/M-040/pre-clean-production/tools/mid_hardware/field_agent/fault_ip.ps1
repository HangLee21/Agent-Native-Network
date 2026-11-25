param(
    [ValidateSet('Inspect','Apply','Restore')][string]$Action = 'Inspect',
    [string]$RemoteIP,
    [ValidateRange(1024,65535)][int]$PcPort = 8793,
    [ValidateRange(1024,65535)][int]$EntryPort = 8792,
    [string]$Record
)
$ErrorActionPreference = 'Stop'
# Narrow PC-side UDP fault. It never disconnects WLAN or commands an ESP32 radio.
if ($Action -eq 'Inspect') {
    [pscustomobject]@{ action='Inspect'; rules_created=0; rules_removed=0; admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator); pc_port=$PcPort; entry_port=$EntryPort } | ConvertTo-Json -Compress
    exit 0
}
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$recordRoot = [IO.Path]::GetFullPath((Join-Path $taskRoot '.local\mid\H-017')) + [IO.Path]::DirectorySeparatorChar
if (-not $Record) { throw 'Explicit new private record path required.' }
$recordPath = [IO.Path]::GetFullPath($Record)
if (-not $recordPath.StartsWith($recordRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Record must remain inside .local/mid/H-017.' }
if ($Action -eq 'Restore') {
    $saved = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    if ($saved.schema -ne 'H017.pc_udp_fault.v1' -or $saved.group -notmatch '^H017-[0-9a-f]{32}$') { throw 'Not an owned H017 fault record.' }
    foreach ($ruleName in $saved.rules) {
        if ($ruleName -notmatch ('^' + [regex]::Escape($saved.group) + '-(in|out)$')) { throw 'Invalid owned rule name.' }
        $existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
        if ($existing) {
            if ($existing.Group -ne $saved.group) { throw 'Firewall rule ownership changed; no delete.' }
            Remove-NetFirewallRule -Name $ruleName
        }
    }
    [pscustomobject]@{action='Restore';group=$saved.group;rules_removed=$saved.rules.Count;WLAN_changed=$false;board_commands=0} | ConvertTo-Json -Compress
    exit 0
}
if (Test-Path -LiteralPath $recordPath) { throw 'Fault record already exists; preserve it.' }
$entryAddress = $null
if (-not [Net.IPAddress]::TryParse($RemoteIP,[ref]$entryAddress) -or $entryAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or [Net.IPAddress]::IsLoopback($entryAddress) -or $RemoteIP -in @('0.0.0.0','255.255.255.255')) { throw 'One actual remote entry IPv4 address required.' }
$faultGroup = 'H017-' + [guid]::NewGuid().ToString('N')
$names = @("${faultGroup}-in", "${faultGroup}-out")
$data = [pscustomobject]@{schema='H017.pc_udp_fault.v1';group=$faultGroup;rules=$names;remote_ip=$RemoteIP;pc_port=$PcPort;entry_port=$EntryPort;started_utc=[DateTime]::UtcNow.ToString('o');WLAN_changed=$false;board_commands=0}
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($recordPath)) | Out-Null
# Persist exact cleanup ownership before mutating the firewall, even if rule two fails.
[IO.File]::WriteAllText($recordPath,($data | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
try {
    New-NetFirewallRule -Name $names[0] -DisplayName $names[0] -Group $faultGroup -Direction Inbound -Action Block -Protocol UDP -LocalPort $PcPort -RemotePort $EntryPort -RemoteAddress $RemoteIP -Profile Any | Out-Null
    New-NetFirewallRule -Name $names[1] -DisplayName $names[1] -Group $faultGroup -Direction Outbound -Action Block -Protocol UDP -LocalPort $PcPort -RemotePort $EntryPort -RemoteAddress $RemoteIP -Profile Any | Out-Null
} catch {
    foreach ($ruleName in $names) { Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue }
    throw
}
[pscustomobject]@{action='Apply';group=$faultGroup;remote_ip=$RemoteIP;rules_created=2;WLAN_changed=$false;board_commands=0;restore_record=$recordPath} | ConvertTo-Json -Compress
