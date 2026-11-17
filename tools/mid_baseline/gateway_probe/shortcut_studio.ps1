<#
    桌面快捷方式用的包装脚本：接网关并打开 LoRa 前端。

    两步：
      1. 提权切到 lab 模式（网口拿 192.168.137.10，无默认网关）
      2. 用 explorer 以普通用户身份启动 START_STUDIO.cmd

    第 2 步必须降权：提权后直接启动会把 Studio 也变成管理员进程，
    它的输出目录会归 administrator 所有，以后普通权限改不动。
    explorer.exe 始终以当前登录用户运行，由它拉起就成了普通进程。
#>
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$studio = Join-Path $root 'START_STUDIO.cmd'

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    )
    exit
}

Write-Host '1/2 切换到 lab 模式（接网关）...' -ForegroundColor Cyan
try {
    & (Join-Path $PSScriptRoot 'netmode.ps1') -Mode lab
} catch {
    Write-Host ('切换失败: ' + $_.Exception.Message) -ForegroundColor Red
}

if (-not (Test-Path $studio)) {
    Write-Host ('找不到启动脚本: ' + $studio) -ForegroundColor Red
    Write-Host '按回车关闭...'
    [void][Console]::ReadLine()
    exit 1
}

Write-Host ''
Write-Host '2/2 启动前端（以当前用户身份）...' -ForegroundColor Cyan
# explorer 转发给 shell，子进程继承的是宿主用户的令牌而不是管理员的。
Start-Process -FilePath 'explorer.exe' -ArgumentList "`"$studio`""

Write-Host ''
Write-Host '前端窗口会自己弹出，浏览器稍后自动打开 http://127.0.0.1:8794/' -ForegroundColor Green
Write-Host '用完记得双击「切回校园网」。' -ForegroundColor Yellow
Start-Sleep -Seconds 4
