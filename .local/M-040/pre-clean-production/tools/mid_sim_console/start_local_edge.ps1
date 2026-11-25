param([string]$SerialPort,[string]$NodeId,[int]$Baud=0)
$ErrorActionPreference='Stop'
if (!$SerialPort) { $SerialPort=Read-Host '本机串口（例如 COM12）' }
if (!$NodeId) { $NodeId=Read-Host '本板 MAC' }
if (!$Baud) { $Baud=[int](Read-Host '实际固件波特率（例如460800）') }
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$edgeData=Join-Path $env:LOCALAPPDATA ('MIDEdge/'+$NodeId.Replace(':',''))
New-Item -ItemType Directory -Path $edgeData -Force | Out-Null
$edgeLog=Join-Path $edgeData (([guid]::NewGuid().ToString('N'))+'.jsonl')
Set-Location -LiteralPath $repoRoot
python tools/mid_sim_console/local_edge.py --serial-port $SerialPort --node-id $NodeId --baud $Baud --state (Join-Path $edgeData 'requests.json') --log $edgeLog
