$ErrorActionPreference='Stop'
$global:fakeRoot=Join-Path $PSScriptRoot 'mock-pc'
New-Item -ItemType Directory -Force (Join-Path $fakeRoot 'data'),(Join-Path $fakeRoot 'runtime/python') | Out-Null
[IO.File]::WriteAllText((Join-Path $fakeRoot 'data/fleet.json'),'{"gateway":{"eui":"b827ebfffe32e2c1"}}'.Replace('{','{').Replace('}','}'))
[IO.File]::WriteAllText((Join-Path $fakeRoot 'runtime/python/python.exe'),'fixture')
function Get-NetAdapter { param([switch]$Physical,$InterfaceIndex) if($InterfaceIndex) {return $global:adapters | Where-Object ifIndex -eq $InterfaceIndex};return $global:adapters }
function Get-NetRoute { param($InterfaceIndex,$AddressFamily,$DestinationPrefix) }
function Get-NetIPInterface { param($InterfaceIndex,$AddressFamily) [pscustomobject]@{Dhcp='Enabled'} }
function Get-NetIPAddress { param($InterfaceIndex,$AddressFamily,$IPAddress) if($IPAddress){if($global:added){[pscustomobject]@{IPAddress='192.168.137.250';AddressState='Preferred'}}}elseif($global:added){[pscustomobject]@{IPAddress='192.168.137.250';AddressState='Preferred'}}elseif($global:renewed){[pscustomobject]@{IPAddress='192.168.137.21'}}else{[pscustomobject]@{IPAddress='169.254.1.2'}} }
function New-NetIPAddress { param($InterfaceIndex,$IPAddress,$PrefixLength) $global:added=$true;$global:mutations++ }
function Remove-NetIPAddress { [CmdletBinding()]param([Parameter(ValueFromPipeline=$true)]$InputObject,[switch]$Confirm) process{$global:added=$false} }
function Set-NetIPInterface { param($InterfaceIndex,$AddressFamily,$Dhcp) }
function Test-NetConnection { param($ComputerName,$Port,$InformationLevel,$WarningAction) [pscustomobject]@{TcpTestSucceeded=$true;InterfaceAlias=$global:expectedName} }
function Read-Host { param($Prompt) if($global:answers.Count -eq 0){throw 'unexpected prompt'};$answer=$global:answers[0];$global:answers=@($global:answers | Select-Object -Skip 1);return ,$answer }
function MakeAdapter($index,$name) {[pscustomobject]@{Name=$name;Status='Up';ifIndex=$index;InterfaceGuid=[guid]'af80aace-132a-41b9-9a21-e907ad26de0c';HardwareInterface=$true;Virtual=$false;InterfaceType=6;MediaType='802.3';PhysicalMediaType='802.3'}}
foreach($mode in @('single','multiple','cancel','no_input','remote_failure')) {
 $global:adapters=@((MakeAdapter 9 'LAN 1')); if($mode -eq 'multiple'){$global:adapters+=MakeAdapter 10 'LAN 2'}
 $global:expectedName=if($mode -eq 'multiple'){'LAN 2'}else{'LAN 1'}
 if($mode -eq 'multiple'){$global:answers=@('2','')}elseif($mode -eq 'cancel'){$global:answers=@('N')}elseif($mode -eq 'no_input'){$global:answers=@($null)}else{$global:answers=@('')}
 $global:added=$false;$global:renewed=$false;$global:mutations=0;$global:fakeExit=if($mode -eq 'remote_failure'){255}else{0}
 . (Join-Path $PSScriptRoot 'bootstrap-fixture.ps1')
 if($mode -eq 'cancel' -or $mode -eq 'no_input'){if($global:bootstrapResult -ne 1 -or $global:mutations -ne 0){throw 'cancel failed'}} elseif($mode -eq 'remote_failure'){if($global:bootstrapResult -ne 1 -or $global:added){throw 'remote failure restore failed'}}
 elseif($global:bootstrapResult -ne 0 -or $global:mutations -ne 1 -or $global:answers.Count -ne 0){throw "selection failed $mode"}
 $log=Get-Content -LiteralPath $logPath -Encoding UTF8 | ForEach-Object { $_ | ConvertFrom-Json }
 if($mode -eq 'remote_failure' -and (-not @($log | Where-Object { $_.stage -eq 'remote_setup' -and $_.exit_code -eq 255 -and $_.status -eq 'failed' }).Count -or -not @($log | Where-Object { $_.stage -eq 'local_restore' -and $_.status -eq 'completed' }).Count)){throw 'diagnostic record missing'} 
 Write-Output "PASS $mode"
}
