<#
    桌面快捷方式用的包装脚本：切回校园网。

    需要一个"以管理员身份运行"的入口，因为改网卡地址必须要提权。
    WScript 的 CreateShortcut 无法设置 run-as-admin，所以这里自己提权一次。
#>
$ErrorActionPreference = 'Stop'

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    )
    exit
}

Write-Host '切回校园网模式...' -ForegroundColor Cyan
try {
    & (Join-Path $PSScriptRoot 'netmode.ps1') -Mode campus
} catch {
    Write-Host ('失败: ' + $_.Exception.Message) -ForegroundColor Red
}

Write-Host ''
Write-Host '如果代理软件还连不上，请重启它（托盘退出后重开）。' -ForegroundColor Yellow
Write-Host '按回车关闭...'
[void][Console]::ReadLine()
