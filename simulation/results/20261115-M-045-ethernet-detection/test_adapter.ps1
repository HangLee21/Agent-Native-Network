$ErrorActionPreference='Stop'
$path='D:\Multi-Agent Network\.worktrees\production\app\gateway_setup\bootstrap.ps1'
$errors=$null; $tokens=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw $errors[0] }
$function=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-DedicatedEthernetCandidate'},$true)
. ([scriptblock]::Create($function.Extent.Text))
function Adapter($name,$status,$hardware,$virtual,$type,$media,$physical) { [pscustomobject]@{Name=$name;Status=$status;HardwareInterface=$hardware;Virtual=$virtual;InterfaceType=$type;MediaType=$media;PhysicalMediaType=$physical} }
$fixtures=@(
 (Adapter 'USB Ethernet' 'Up' $true $false 6 '802.3' '802.3'),
 (Adapter 'Virtual Ethernet' 'Up' $false $true 6 '802.3' '802.3'),
 (Adapter 'Disconnected Ethernet' 'Disconnected' $true $false 6 '802.3' '802.3'),
 (Adapter 'WiFi' 'Up' $true $false 71 'Native 802.11' 'Native 802.11'),
 (Adapter 'WiFi disguised' 'Up' $true $false 6 '802.3' 'Native 802.11')
)
$chosen=@($fixtures | Where-Object { Test-DedicatedEthernetCandidate $_ })
if ($chosen.Count -ne 1 -or $chosen[0].Name -ne 'USB Ethernet') { throw 'Fixture selection mismatch' }
Write-Output 'PASS fixtures: USB selected; virtual, disconnected and WiFi excluded'
$adapters=@(Get-NetAdapter -Physical)
$real=@($adapters | Where-Object { Test-DedicatedEthernetCandidate $_ })
if (-not @($real | Where-Object { $_.InterfaceIndex -eq 20 }).Count) { throw 'Real Ethernet index 20 not selected' }
if (@($real | Where-Object { $_.InterfaceType -eq 71 -or $_.PhysicalMediaType -match '802.11' }).Count) { throw 'Real WiFi incorrectly selected' }
$real | Select-Object Name,InterfaceIndex,Status,InterfaceType,HardwareInterface,Virtual,MediaType,PhysicalMediaType | ConvertTo-Json -Depth 3
Write-Output 'PASS read-only real adapter enumeration'
