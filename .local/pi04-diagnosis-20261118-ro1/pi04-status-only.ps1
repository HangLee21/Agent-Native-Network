$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Pi 04 - read-only status'
Write-Host 'Type the Linux password for eora on Pi 04, then press Enter. Input stays hidden.'
$remote='hostname; printf "reader="; systemctl is-active node_reader; ip -4 -o addr show dev wlan0; ip -4 -o addr show dev eth0'
& ssh -T -o StrictHostKeyChecking=yes -o ("UserKnownHostsFile="+(Join-Path $env:TEMP 'pi_known_hosts')) -o ConnectTimeout=10 -o NumberOfPasswordPrompts=1 -o PreferredAuthentications=password eora@100.101.0.110 $remote | Tee-Object -FilePath (Join-Path $PSScriptRoot 'pi04-readonly-status.txt')
Write-Host ("SSH exit: "+$LASTEXITCODE)
Read-Host 'Press Enter to close'
