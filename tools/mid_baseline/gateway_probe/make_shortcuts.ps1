<#
    在桌面生成两个快捷方式。仓库迁移或换电脑后重跑一次即可。

    快捷方式本身不进版本库（它在桌面），但生成它的脚本要进，
    否则换个机器就没人记得参数长什么样。
#>
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$gp = Join-Path $root 'tools\mid_baseline\gateway_probe'
$desktop = [Environment]::GetFolderPath('Desktop')
$ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$defs = @(
    @{ Name = '切回校园网.lnk';     Script = 'shortcut_campus.ps1'; Icon = 17; Desc = '把有线网口切回 DHCP，恢复正常上网' },
    @{ Name = '启动 LoRa 前端.lnk'; Script = 'shortcut_studio.ps1'; Icon = 13; Desc = '切换到 lab 模式并启动 LoRa 拓扑前端' }
)

$ws = New-Object -ComObject WScript.Shell
foreach ($d in $defs) {
    $script = Join-Path $gp $d.Script
    if (-not (Test-Path -LiteralPath $script)) {
        Write-Host ("缺少包装脚本: " + $script) -ForegroundColor Red
        continue
    }
    $target = Join-Path $desktop $d.Name
    $sc = $ws.CreateShortcut($target)
    $sc.TargetPath = $ps
    $sc.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $script + '"'
    $sc.WorkingDirectory = $root
    $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,$($d.Icon)"
    $sc.Description = $d.Desc
    $sc.WindowStyle = 1
    $sc.Save()
    Write-Host ("已创建: " + $target) -ForegroundColor Green
}

Write-Host ''
Write-Host '两个快捷方式都会请求管理员权限（改网卡地址必须提权）。'
Write-Host '「启动 LoRa 前端」在提权后会用 explorer 以普通用户身份拉起前端，'
Write-Host '这样输出目录不会归 administrator 所有。'
