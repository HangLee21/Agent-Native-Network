$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='04 Pi - eora SSH login'
Set-Location -LiteralPath 'D:\Multi-Agent Network'
Write-Host 'Enter the Linux login password for eora on Pi 04. It will not be displayed.'
$pub=(Get-Content -Raw -LiteralPath (Join-Path $env:USERPROFILE '.ssh\id_ed25519_eora.pub')).Trim().Split(' ')
if ($pub[0] -ne 'ssh-ed25519' -or $pub[1] -notmatch '^[A-Za-z0-9+/=]+$') {throw 'Unexpected public key format'}
$key=$pub[0]+' '+$pub[1]
$remote='set -eu; test "$(hostname)" = eora-air-04; test "$(id -un)" = eora; umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; grep -qF -- '+ "'"+$pub[1]+"'" +' ~/.ssh/authorized_keys || printf ''\n%s\n'' '+ "'"+$key+"'" +' >> ~/.ssh/authorized_keys; hostname; systemctl is-active node_reader'
& ssh -T -o StrictHostKeyChecking=yes -o ("UserKnownHostsFile="+(Join-Path $env:TEMP 'pi_known_hosts')) -o ConnectTimeout=10 -o NumberOfPasswordPrompts=1 -o PreferredAuthentications=password eora@100.101.0.110 $remote
Write-Host ("SSH exit: "+$LASTEXITCODE)
Read-Host 'Press Enter to close'
