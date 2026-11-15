$ErrorActionPreference='Stop'
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Administrator rights required; no changes made.' }

$idx=20;$ip='192.168.137.250';$target='192.168.137.200';$guid='{F839B1C1-B38F-4912-8748-9247E0C8BA58}'
$statePath='D:\Multi-Agent Network\.worktrees\production\data\gateway-setup\temporary-ip.json'
$adapter=Get-NetAdapter -InterfaceIndex $idx
if($adapter.InterfaceGuid.ToString() -ne $guid -or $adapter.Status -ne 'Up' -or -not $adapter.HardwareInterface -or $adapter.Virtual){throw '网卡身份或状态不符，未执行诊断'}
if((Get-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4).Dhcp -ne 'Enabled'){throw '网卡原状态不符，未执行诊断'}
if(Get-NetRoute -InterfaceIndex $idx -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue){throw '网口有默认路由，未执行诊断'}
if(Test-Path -LiteralPath $statePath){throw '存在待恢复记录，未执行诊断'}
if(Get-NetIPAddress -IPAddress $ip -ErrorAction SilentlyContinue){throw '临时地址已被使用，未执行诊断'}
if(Get-Process ssh,scp -ErrorAction SilentlyContinue){throw 'SSH/SCP正在运行，未执行诊断'}
$state=[ordered]@{interface_index=$idx;interface_guid=$guid;original_dhcp='Enabled';temporary_ip=$ip}
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($state|ConvertTo-Json));$temp=$statePath+'.tmp';$file=[IO.File]::Open($temp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$file.Write($bytes,0,$bytes.Length);$file.Flush($true)}finally{$file.Dispose()};Move-Item -LiteralPath $temp -Destination $statePath
try{
 New-NetIPAddress -InterfaceIndex $idx -IPAddress $ip -PrefixLength 24 -ErrorAction Stop | Out-Null
 $deadline=[DateTime]::UtcNow.AddSeconds(10)
 do {$entry=Get-NetIPAddress -InterfaceIndex $idx -IPAddress $ip -ErrorAction Stop;if($entry.AddressState -eq 'Preferred'){break};Start-Sleep -Milliseconds 250}while([DateTime]::UtcNow -lt $deadline)
 if($entry.AddressState -ne 'Preferred'){throw '临时地址未就绪'}
 $route=Find-NetRoute -RemoteIPAddress $target -ErrorAction Stop | Where-Object { $_.DestinationPrefix } | Select-Object -First 1 InterfaceIndex,DestinationPrefix,NextHop
 Write-Output ('ROUTE '+($route|ConvertTo-Json -Compress))
 if($route.InterfaceIndex -ne $idx){throw '目标选路未经过专用网口'}
 $ping=[Net.NetworkInformation.Ping]::new();try{$reply=$ping.Send($target,1500);Write-Output ('ICMP '+$reply.Status)}finally{$ping.Dispose()}
 $client=[Net.Sockets.TcpClient]::new();try{$async=$client.BeginConnect($target,22,$null,$null);if($async.AsyncWaitHandle.WaitOne(2000)){try{$client.EndConnect($async);Write-Output 'TCP22 connected'}catch{Write-Output ('TCP22 failed '+$_.Exception.GetType().Name)}}else{Write-Output 'TCP22 timeout'}}finally{$client.Close()}
 $neighbor=Get-NetNeighbor -InterfaceIndex $idx -IPAddress $target -ErrorAction SilentlyContinue | Select-Object IPAddress,LinkLayerAddress,State;Write-Output ('NEIGHBOR '+($neighbor|ConvertTo-Json -Compress))
}finally{
 $a=Get-NetAdapter -InterfaceIndex $idx;if($a.InterfaceGuid.ToString() -ne $guid){throw '网卡身份变化，恢复记录保留'}
 $entry=Get-NetIPAddress -InterfaceIndex $idx -IPAddress $ip -ErrorAction SilentlyContinue;if($entry){$entry|Remove-NetIPAddress -Confirm:$false -ErrorAction Stop}
 Set-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4 -Dhcp Enabled -ErrorAction Stop
 if((Get-NetIPInterface -InterfaceIndex $idx -AddressFamily IPv4).Dhcp -ne 'Enabled'){throw 'DHCP未恢复，记录保留'}
 if(Get-NetIPAddress -InterfaceIndex $idx -IPAddress $ip -ErrorAction SilentlyContinue){throw '临时地址仍存在，记录保留'}
 Move-Item -LiteralPath $statePath -Destination (Join-Path (Split-Path $statePath) ('restored-'+[guid]::NewGuid().ToString('N')+'.json'))
 Write-Output 'RESTORE DHCP Enabled; temporary address removed'
}
