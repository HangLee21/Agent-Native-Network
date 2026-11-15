$ErrorActionPreference='Stop'
$log=Join-Path $PSScriptRoot 'probe-result.txt'
try {
  & (Join-Path $PSScriptRoot 'probe.ps1') *>&1 | Out-File -LiteralPath $log -Encoding UTF8
  Add-Content -LiteralPath $log -Encoding UTF8 -Value 'PROBE_PROCESS completed'
  exit 0
} catch {
  Add-Content -LiteralPath $log -Encoding UTF8 -Value ('PROBE_PROCESS failed: '+$_.Exception.Message)
  exit 1
}
