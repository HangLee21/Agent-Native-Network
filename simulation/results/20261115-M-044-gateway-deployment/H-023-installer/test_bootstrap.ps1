$ErrorActionPreference='Stop'
$fixture=Join-Path $PSScriptRoot 'bootstrap-fixture.ps1'
$global:fakeRoot=Join-Path $PSScriptRoot 'mock-pc'
New-Item -ItemType Directory -Force (Join-Path $global:fakeRoot 'data'),(Join-Path $global:fakeRoot 'runtime/python') | Out-Null
[IO.File]::WriteAllText((Join-Path $global:fakeRoot 'data/fleet.json'),'{"gateway":{"eui":"b827ebfffe32e2c1"}}')
[IO.File]::WriteAllText((Join-Path $global:fakeRoot 'runtime/python/python.exe'),'fixture')
function Get-NetAdapter { param([switch]$Physical,$InterfaceIndex) [pscustomobject]@{Status='Up';ifType=6;ifIndex=9;InterfaceGuid=[guid]'af80aace-132a-41b9-9a21-e907ad26de0c';Name='Fake Ethernet'} }
function Get-NetRoute { param($InterfaceIndex,$AddressFamily,$DestinationPrefix) }
function Get-NetIPInterface { param($InterfaceIndex,$AddressFamily) [pscustomobject]@{Dhcp='Enabled'} }
function Get-NetIPAddress { param($InterfaceIndex,$AddressFamily,$IPAddress) if($IPAddress){if($global:added){[pscustomobject]@{IPAddress='192.168.137.250'}}}elseif($global:added){[pscustomobject]@{IPAddress='192.168.137.250'}}elseif($global:renewed){[pscustomobject]@{IPAddress='192.168.137.21'}}else{[pscustomobject]@{IPAddress='169.254.1.2'}} }
function New-NetIPAddress { param($InterfaceIndex,$IPAddress,$PrefixLength) $global:added=$true; if($global:failAdd){throw 'synthetic add failure'} }
function Remove-NetIPAddress { [CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject,[switch]$Confirm) process{$global:added=$false} }
function Set-NetIPInterface { param($InterfaceIndex,$AddressFamily,$Dhcp) $global:restored=$true }
function Test-NetConnection { param($ComputerName,$Port,$InformationLevel,$WarningAction) [pscustomobject]@{TcpTestSucceeded=$true;InterfaceAlias='Fake Ethernet'} }
function Read-Host { param($Prompt) $answer=$global:answers[0];$global:answers=@($global:answers | Select-Object -Skip 1);return $answer }
foreach($mode in @('success','remote_failure','address_failure','identity_failure')){
 $global:identityValid=($mode -ne 'identity_failure');$global:answers=@('1','YES','1');$global:added=$false;$global:restored=$false;$global:renewed=$false;$global:failAdd=($mode -eq 'address_failure');$global:fakeExit=if($mode -eq 'remote_failure'){1}else{0}
 . $fixture
 if($global:added -or -not $global:restored){throw "DHCP recovery failed: $mode"}
 if($mode -eq 'success' -and (-not $global:renewed -or $global:bootstrapResult -ne 0)){throw 'success/renew failed'}
 if($mode -ne 'success' -and $global:bootstrapResult -ne 1){throw "failure result wrong: $mode"}
 if(Test-Path -LiteralPath (Join-Path $global:fakeRoot 'data/gateway-setup/temporary-ip.json')){throw 'temporary state remained'}
 Write-Output "PASS $mode"
}
