<#
.SYNOPSIS
    Switch the single Ethernet port between its three real uses.

.DESCRIPTION
    One port, three jobs: the campus network, the LoRa gateway, and a fresh Raspberry Pi.
    Leaving static addresses on it is what broke the machine's proxy: a 10.0.0.0/24 route
    sitting on a dead link outranked the real uplink. This script only ever leaves one of the
    three states behind, and the lab state deliberately has no default route and no DNS, so
    it cannot steal traffic from the Wi-Fi uplink no matter what is plugged in.

    campus  DHCP, normal internet use. Default; use this unless you are doing bench work.
    lab     The LoRa gateway. 192.168.137.10/24, no gateway, no DNS.
    pi      A fresh Raspberry Pi. Pure link-local on both ends; nothing to configure.
    status  Show what the port currently looks like.

.EXAMPLE
    .\netmode.ps1 campus
    .\netmode.ps1 lab
    .\netmode.ps1 status
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('campus', 'lab', 'pi', 'status')]
    [string]$Mode,
    [string]$Interface = '以太网',
    [string]$LabAddress = '192.168.137.10',
    [int]$LabPrefix = 24
)

$ErrorActionPreference = 'Stop'

function Show-State {
    Write-Host ''
    Write-Host "== $Interface" -ForegroundColor Cyan
    $adapter = Get-NetAdapter -Name $Interface -ErrorAction SilentlyContinue
    if (-not $adapter) { Write-Host "   adapter not found" -ForegroundColor Red; return }
    Write-Host ("   link     : {0} / {1}" -f $adapter.Status, $adapter.LinkSpeed)

    $addrs = @(Get-NetIPAddress -InterfaceAlias $Interface -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    if ($addrs.Count -eq 0) { Write-Host '   addresses: (none)' }
    foreach ($a in $addrs) {
        Write-Host ("   address  : {0}/{1}  ({2})" -f $a.IPAddress, $a.PrefixLength, $a.PrefixOrigin)
    }

    $dns = @(Get-DnsClientServerAddress -InterfaceAlias $Interface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
             Select-Object -ExpandProperty ServerAddresses -ErrorAction SilentlyContinue)
    Write-Host ("   dns      : {0}" -f ($(if ($dns.Count) { $dns -join ', ' } else { '(none)' })))

    $def = @(Get-NetRoute -InterfaceAlias $Interface -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue)
    if ($def.Count) { foreach ($r in $def) { Write-Host ("   default  : {0} metric {1}" -f $r.NextHop, $r.RouteMetric) } }
    else { Write-Host '   default  : (none)  <- correct for lab/pi' }
    Write-Host ''
}

function Clear-Static {
    # Remove every non-DHCP IPv4 address. The port must never keep a leftover from the
    # previous mode: that is exactly how the 10.0.0.0/24 route broke the proxy.
    Get-NetIPAddress -InterfaceAlias $Interface -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.PrefixOrigin -ne 'Dhcp' } |
        ForEach-Object {
            Write-Host ("   removing {0}/{1}" -f $_.IPAddress, $_.PrefixLength)
            Remove-NetIPAddress -InterfaceAlias $Interface -IPAddress $_.IPAddress -Confirm:$false -ErrorAction SilentlyContinue
        }
    Get-NetRoute -InterfaceAlias $Interface -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host ("   removing default route via {0}" -f $_.NextHop)
            Remove-NetRoute -InterfaceAlias $Interface -DestinationPrefix '0.0.0.0/0' -Confirm:$false -ErrorAction SilentlyContinue
        }
}

switch ($Mode) {
    'status' {
        Show-State
        break
    }

    'campus' {
        Write-Host '== campus: DHCP, share the Wi-Fi uplink normally' -ForegroundColor Cyan
        Clear-Static
        Set-NetIPInterface -InterfaceAlias $Interface -Dhcp Enabled -ErrorAction SilentlyContinue
        Set-DnsClientServerAddress -InterfaceAlias $Interface -ResetServerAddresses -ErrorAction SilentlyContinue
        ipconfig /renew "$Interface" | Out-Null
        Show-State
        break
    }

    'lab' {
        Write-Host '== lab: LoRa gateway, isolated from the uplink' -ForegroundColor Cyan
        Clear-Static
        Set-NetIPInterface -InterfaceAlias $Interface -Dhcp Disabled -ErrorAction SilentlyContinue
        Set-DnsClientServerAddress -InterfaceAlias $Interface -ResetServerAddresses -ErrorAction SilentlyContinue
        # No -DefaultGateway and no DNS on purpose: the gateway link must never be able to
        # take over the machine's internet access.
        New-NetIPAddress -InterfaceAlias $Interface -IPAddress $LabAddress -PrefixLength $LabPrefix |
            Out-Null
        Write-Host ("   added {0}/{1} (no gateway, no dns)" -f $LabAddress, $LabPrefix)
        Show-State
        break
    }

    'pi' {
        Write-Host '== pi: fresh Raspberry Pi over link-local' -ForegroundColor Cyan
        Clear-Static
        Set-NetIPInterface -InterfaceAlias $Interface -Dhcp Disabled -ErrorAction SilentlyContinue
        Set-DnsClientServerAddress -InterfaceAlias $Interface -ResetServerAddresses -ErrorAction SilentlyContinue
        Write-Host '   no address configured; Windows will use 169.254.x.x automatically'
        Write-Host '   the Pi does the same, so ssh eora@169.254.x.x works once both settle'
        Start-Sleep -Seconds 3
        Show-State
        break
    }
}

Write-Host 'Tip: after switching, restart any proxy/VPN client if it pins an interface.' -ForegroundColor DarkGray
Write-Host '     Run "netmode.ps1 status" any time to see the real state.' -ForegroundColor DarkGray
