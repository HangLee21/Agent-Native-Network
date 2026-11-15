param([switch]$Elevated)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not $Elevated) {
    $script = '"' + $PSCommandPath + '"'
    $proc = Start-Process -FilePath 'powershell.exe' -Verb RunAs -PassThru -Wait -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$script,'-Elevated')
    exit $proc.ExitCode
}
$stateDir = Join-Path $root 'data/gateway-setup'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$statePath = Join-Path $stateDir 'temporary-ip.json'

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

function Test-ApplianceIdentity {
    param([string]$ExpectedEui)
    $request = [Net.WebRequest]::Create('http://192.168.137.200:8780/api/v1/appliance')
    $request.Proxy = $null
    $request.Timeout = 5000
    $response = $request.GetResponse()
    try {
        $reader = [IO.StreamReader]::new($response.GetResponseStream())
        try { $identity = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        return ($identity.schema -eq 'ann.gateway.appliance.v1' -and $identity.gateway_eui -eq $ExpectedEui -and $identity.api_version -eq 1 -and $identity.ready -eq $true)
    } finally { $response.Dispose() }
}

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
    if (Test-Path -LiteralPath $statePath) {
        Write-Host '正在恢复上一次中断的网卡设置……'
        Restore-TemporaryAddress (Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json)
    }
    $config = Join-Path $root 'data/fleet.json'
    if (-not (Test-Path -LiteralPath $config)) { $config = Join-Path $root 'config/fleet.default.json' }
    $fleet = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
    $eui = [string]$fleet.gateway.eui
    if ($eui -notmatch '^[0-9a-f]{16}$') { throw '网关标识无效。' }
    $python = Join-Path $root 'runtime/python/python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw '交付包缺少运行环境。' }
    $adapters = @(Get-NetAdapter -Physical)
    $choices = @($adapters | Where-Object { Test-DedicatedEthernetCandidate $_ })
    if ($choices.Count -eq 0) {
        Write-Host '未找到符合条件的已连接物理有线网口。检测到的物理网卡：'
        foreach ($adapter in $adapters) { Write-Host ('  {0}：{1}，介质 {2}' -f $adapter.Name,$adapter.Status,$adapter.PhysicalMediaType) }
        throw '请检查网线、网卡状态或驱动，然后重试。'
    }
    Write-Host '请选择只连接网关、不接入共享网络的电脑有线网口：'
    for ($i=0; $i -lt $choices.Count; $i++) { Write-Host ('{0}. {1}' -f ($i+1),$choices[$i].Name) }
    $choice = Read-Host '输入序号'
    $number = 0
    if (-not [int]::TryParse($choice,[ref]$number) -or $number -lt 1 -or $number -gt $choices.Count) { throw '没有选择有效网口。' }
    $selected = $choices[$number-1]
    if (Get-NetRoute -InterfaceIndex $selected.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue) { throw '该网口有默认路由，不能作为专用直连网口。' }
    if ((Read-Host '确认网口仅连接网关、没有接入共享网络？输入 YES 继续') -cne 'YES') { throw '未确认专用网口。' }
    $action = Read-Host '输入 1 初始化网关；输入 2 回滚初始化'
    if ($action -eq '1') { $actionName='install' } elseif ($action -eq '2') { $actionName='rollback' } else { throw '未选择有效操作。' }
    if ($actionName -eq 'install') {
        & $python -B (Join-Path $PSScriptRoot 'setup_gateway.py') --plan
        if ($LASTEXITCODE -ne 0) { throw '交付包尚未准备完成，未修改网卡。' }
    }
    $ipState = Get-NetIPInterface -InterfaceIndex $selected.ifIndex -AddressFamily IPv4
    $state = [ordered]@{ interface_index=$selected.ifIndex;interface_guid=$selected.InterfaceGuid.ToString();original_dhcp=$ipState.Dhcp.ToString();temporary_ip='192.168.137.250' }
    $addresses = @(Get-NetIPAddress -InterfaceIndex $selected.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue)
    $already = @($addresses | Where-Object { $_.IPAddress -match '^192\.168\.137\.' }).Count -gt 0
    $result=1
    try {
        if (-not $already) {
        if (Get-NetIPAddress -IPAddress $state.temporary_ip -ErrorAction SilentlyContinue) { throw '临时地址已被本机占用，未修改网卡。' }
        $tmp = $statePath+'.tmp'
            $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($state | ConvertTo-Json))
            $file = [IO.File]::Open($tmp,[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try { $file.Write($bytes,0,$bytes.Length); $file.Flush($true) } finally { $file.Dispose() }
        Move-Item -LiteralPath $tmp -Destination $statePath
        New-NetIPAddress -InterfaceIndex $selected.ifIndex -IPAddress $state.temporary_ip -PrefixLength 24 -ErrorAction Stop | Out-Null
        }
        & $python -B (Join-Path $PSScriptRoot 'setup_gateway.py') --action $actionName --gateway-eui $eui
        $result=$LASTEXITCODE
    } finally {
        if (Test-Path -LiteralPath $statePath) { Restore-TemporaryAddress (Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json) }
        if ($actionName -eq 'install' -and $result -eq 0 -and $state.original_dhcp -eq 'Enabled') {
            & ipconfig.exe /renew $selected.Name | Out-Null
            if ($LASTEXITCODE -ne 0) { throw '电脑网口已还原为自动获取地址，但续租未成功；可重新插拔网线后重试。' }
        }
        if ($actionName -eq 'install' -and $result -eq 0) {
            $newAddresses = @(Get-NetIPAddress -InterfaceIndex $selected.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                Where-Object { $_.IPAddress -match '^192\.168\.137\.' -and $_.IPAddress -ne '192.168.137.200' })
            if ($newAddresses.Count -eq 0) { throw '网关初始化已执行，但电脑网口尚未取得同网段地址；请重新插拔网线后重试。' }
            $connection = Test-NetConnection -ComputerName '192.168.137.200' -Port 22 -InformationLevel Detailed -WarningAction SilentlyContinue
            if (-not $connection.TcpTestSucceeded -or $connection.InterfaceAlias -ne $selected.Name) { throw '网关初始化已执行，但专用网口尚不能连接网关；请检查网线并重试。' }
            try { $identityOk = Test-ApplianceIdentity $eui } catch { $identityOk = $false }
            if (-not $identityOk) { throw '网关初始化已执行，但接收服务身份或就绪状态未通过核验；请检查网关后重试。' }
        }
    }
    if ($result -ne 0) { throw '网关操作未完成，请查看上方提示后重试。' }
    Write-Host '处理完成。'
} catch {
    Write-Host ('未完成：' + $_.Exception.Message)
    $result=1
} finally {
    Write-Host '按任意键关闭。'
    $null=$Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
}
exit $result
