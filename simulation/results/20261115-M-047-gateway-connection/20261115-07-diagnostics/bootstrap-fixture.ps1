$Elevated=$true; $Rollback=$false
$ErrorActionPreference = 'Stop'
$root=$global:fakeRoot
if (-not $Elevated) {
    $script = '"' + $PSCommandPath + '"'
    $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$script,'-Elevated')
    if ($Rollback) { $arguments += '-Rollback' }
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -PassThru -Wait -ArgumentList $arguments
    exit $proc.ExitCode
}
$stateDir = Join-Path $root 'data/gateway-setup'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$statePath = Join-Path $stateDir 'temporary-ip.json'
$logPath = Join-Path $stateDir ('run-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N') + '.jsonl')
$phase = 'start'
function Write-SetupEvent {
    param([string]$Stage,[string]$Status,$Code=$null,[string]$ErrorType='')
    $event = [ordered]@{ time=(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'); component='bootstrap'; stage=$Stage; status=$Status }
    if ($null -ne $Code) { $event.exit_code=$Code }
    if ($ErrorType) { $event.error_type=$ErrorType }
    try { Add-Content -LiteralPath $logPath -Value ($event | ConvertTo-Json -Compress) -Encoding UTF8 } catch { Write-Warning '无法写入诊断日志。' }
}
Write-SetupEvent 'start' 'started'

function Restore-TemporaryAddress {
    param($State)
    $adapter = Get-NetAdapter -InterfaceIndex $State.interface_index -ErrorAction Stop
    if ($adapter.InterfaceGuid.ToString() -ne $State.interface_guid) { throw '原网卡身份发生变化；保留恢复记录，请勿继续。' }
    $existing = Get-NetIPAddress -InterfaceIndex $State.interface_index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -eq $State.temporary_ip }
    if ($existing) { $existing | Remove-NetIPAddress -Confirm:$false -ErrorAction Stop }
    if ($State.original_dhcp -eq 'Enabled') {
        Set-NetIPInterface -InterfaceIndex $State.interface_index -AddressFamily IPv4 -Dhcp Enabled -ErrorAction Stop
    }
    $archive = Join-Path $stateDir ('restored-' + [guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $statePath -Destination $archive
}

function Test-ApplianceIdentity { param([string]$ExpectedEui) return $true }

function Test-DedicatedEthernetCandidate {
    param($Adapter)
    $interfaceType = $Adapter.InterfaceType
    if ($null -eq $interfaceType) { $interfaceType = $Adapter.ifType }
    return ($Adapter.Status -eq 'Up' -and $Adapter.HardwareInterface -eq $true -and
        $Adapter.Virtual -eq $false -and $interfaceType -eq 6 -and
        $Adapter.MediaType -eq '802.3' -and
        $Adapter.PhysicalMediaType -in @('802.3','Unspecified'))
}

try {
    $phase = 'previous_recovery'
    if (Test-Path -LiteralPath $statePath) {
        Write-Host '正在恢复上一次中断的网卡设置……'
        Restore-TemporaryAddress (Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json)
    }
    $phase = 'local_preflight'
    $config = Join-Path $root 'data/fleet.json'
    if (-not (Test-Path -LiteralPath $config)) { $config = Join-Path $root 'config/fleet.default.json' }
    $fleet = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
    $eui = [string]$fleet.gateway.eui
    if ($eui -notmatch '^[0-9a-f]{16}$') { throw '网关标识无效。' }
    $python = Join-Path $root 'runtime/python/python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw '交付包缺少运行环境。' }
    $adapters = @(Get-NetAdapter -Physical)
    $choices = @($adapters | Where-Object { (Test-DedicatedEthernetCandidate $_) -and -not (Get-NetRoute -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue) })
    if ($choices.Count -eq 0) {
        Write-Host '未找到符合条件的已连接物理有线网口。检测到的物理网卡：'
        foreach ($adapter in $adapters) { Write-Host ('  {0}：{1}，介质 {2}' -f $adapter.Name,$adapter.Status,$adapter.PhysicalMediaType) }
        throw '请检查网线、网卡状态或驱动，然后重试。'
    }
    if ($choices.Count -eq 1) { $selected = $choices[0] } else {
        Write-Host '检测到多个有线网口，请选择网线连接网关的网口：'
        for ($i=0; $i -lt $choices.Count; $i++) { Write-Host ('{0}. {1}' -f ($i+1),$choices[$i].Name) }
        $choice = Read-Host '输入序号'
        $number = 0
        if (-not [int]::TryParse($choice,[ref]$number) -or $number -lt 1 -or $number -gt $choices.Count) { throw '没有选择有效网口。' }
        $selected = $choices[$number-1]
    }
    if (Get-NetRoute -InterfaceIndex $selected.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue) { throw '该网口有默认路由，不能作为专用直连网口。' }
    $actionName = if ($Rollback) { 'rollback' } else { 'install' }
    $actionLabel = if ($Rollback) { '回滚' } else { '初始化' }
    Write-Host ('电脑网口：{0}；准备{1}网关。' -f $selected.Name,$actionLabel)
    $confirm = Read-Host '请确认网线直连网关、没有接入共享网络。按回车开始，输入 N 取消'
    if ($null -eq $confirm -or $confirm -ne '') { throw '已取消操作。' }
    Write-SetupEvent 'confirmation' 'completed'
    if ($actionName -eq 'install') {
        $phase = 'package_check'
        $global:LASTEXITCODE=0
        $code=$LASTEXITCODE; $status=if($code -eq 0){'completed'}else{'failed'}
        Write-SetupEvent $phase $status $code
        if ($LASTEXITCODE -ne 0) { throw '交付包尚未准备完成，未修改网卡。' }
    }
    $ipState = Get-NetIPInterface -InterfaceIndex $selected.ifIndex -AddressFamily IPv4
    $state = [ordered]@{ interface_index=$selected.ifIndex;interface_guid=$selected.InterfaceGuid.ToString();original_dhcp=$ipState.Dhcp.ToString();temporary_ip='192.168.137.250' }
    $addresses = @(Get-NetIPAddress -InterfaceIndex $selected.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    $already = @($addresses | Where-Object { $_.IPAddress -match '^192\.168\.137\.' }).Count -gt 0
    $result=1
    try {
        $phase = 'temporary_address'
        if (-not $already) {
        if (Get-NetIPAddress -IPAddress $state.temporary_ip -ErrorAction SilentlyContinue) { throw '临时地址已被本机占用，未修改网卡。' }
        $tmp = $statePath+'.tmp'
            $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($state | ConvertTo-Json))
            $file = [IO.File]::Open($tmp,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try { $file.Write($bytes,0,$bytes.Length); $file.Flush($true) } finally { $file.Dispose() }
        Move-Item -LiteralPath $tmp -Destination $statePath
        New-NetIPAddress -InterfaceIndex $selected.ifIndex -IPAddress $state.temporary_ip -PrefixLength 24 -ErrorAction Stop | Out-Null
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        do {
            $temporary = Get-NetIPAddress -InterfaceIndex $selected.ifIndex -IPAddress $state.temporary_ip -ErrorAction Stop
            if ($temporary.AddressState -eq 'Preferred') { break }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $deadline)
        if ($temporary.AddressState -ne 'Preferred') { throw '电脑临时地址未就绪，请检查网卡后重试。' }
        }
        Write-SetupEvent $phase 'completed'
        $phase = 'remote_setup'
        Write-SetupEvent $phase 'started'
        $global:LASTEXITCODE=$global:fakeExit
        $result=$LASTEXITCODE
        $status=if($result -eq 0){'completed'}else{'failed'}
        Write-SetupEvent $phase $status $result
    } finally {
        if (Test-Path -LiteralPath $statePath) {
            $phase = 'local_restore'
            try { Restore-TemporaryAddress (Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json); Write-SetupEvent $phase 'completed' }
            catch { Write-SetupEvent $phase 'failed' $null $_.Exception.GetType().Name; throw }
        } else { Write-SetupEvent 'local_restore' 'not_needed' }
        if ($actionName -eq 'install' -and $result -eq 0 -and $state.original_dhcp -eq 'Enabled') {
            $phase = 'dhcp_renew'
            $global:renewed=$true; $global:LASTEXITCODE=0
            $code=$LASTEXITCODE; $status=if($code -eq 0){'completed'}else{'failed'}
            Write-SetupEvent $phase $status $code
            if ($LASTEXITCODE -ne 0) { throw '电脑网口已还原为自动获取地址，但续租未成功；可重新插拔网线后重试。' }
        }
        if ($actionName -eq 'install' -and $result -eq 0) {
            $phase = 'connection_verify'
            $newAddresses = @(Get-NetIPAddress -InterfaceIndex $selected.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object { $_.IPAddress -match '^192\.168\.137\.' -and $_.IPAddress -ne '192.168.137.200' })
            if ($newAddresses.Count -eq 0) { throw '网关初始化已执行，但电脑网口尚未取得同网段地址；请重新插拔网线后重试。' }
            $connection = Test-NetConnection -ComputerName '192.168.137.200' -Port 22 -InformationLevel Detailed -WarningAction SilentlyContinue
            if (-not $connection.TcpTestSucceeded -or $connection.InterfaceAlias -ne $selected.Name) { throw '网关初始化已执行，但专用网口尚不能连接网关；请检查网线并重试。' }
            try { $identityOk = Test-ApplianceIdentity $eui } catch { $identityOk = $false }
            if (-not $identityOk) { throw '网关初始化已执行，但接收服务身份或就绪状态未通过核验；请检查网关后重试。' }
        }
    }
    if ($result -ne 0) { $phase='remote_setup'; throw '网关操作未完成，请查看上方提示后重试。' }
    Write-SetupEvent 'finish' 'completed' 0
    Write-Host '处理完成。'
} catch {
    Write-SetupEvent $phase 'failed' $null $_.Exception.GetType().Name
    Write-Host ('未完成：' + $_.Exception.Message)
    Write-Host ('诊断日志：' + $logPath)
    $result=1
} finally {
    Write-Host '按任意键关闭。'
    $null=$null
}
$global:bootstrapResult=$result
