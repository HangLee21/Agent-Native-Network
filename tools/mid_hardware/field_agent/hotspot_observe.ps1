param([Parameter(Mandatory=$true)][string]$PrivateDirectory)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$allowedRoot=[IO.Path]::GetFullPath((Join-Path $taskRoot '.local\mid\H-017'))+[IO.Path]::DirectorySeparatorChar
$privatePath=[IO.Path]::GetFullPath($PrivateDirectory)
if (-not ($privatePath+[IO.Path]::DirectorySeparatorChar).StartsWith($allowedRoot,[StringComparison]::OrdinalIgnoreCase)) {throw 'Private directory must be inside .local/mid/H-017.'}
[IO.Directory]::CreateDirectory($privatePath)|Out-Null
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class H017Wlan {
    [DllImport("wlanapi.dll")] static extern uint WlanOpenHandle(uint version,IntPtr reserved,out uint negotiated,out IntPtr client);
    [DllImport("wlanapi.dll")] static extern uint WlanCloseHandle(IntPtr client,IntPtr reserved);
    [DllImport("wlanapi.dll")] static extern uint WlanQueryInterface(IntPtr client,ref Guid id,uint opcode,IntPtr reserved,out uint size,out IntPtr data,out uint kind);
    [DllImport("wlanapi.dll")] static extern uint WlanHostedNetworkQueryStatus(IntPtr client,out IntPtr data,IntPtr reserved);
    [DllImport("wlanapi.dll")] static extern void WlanFreeMemory(IntPtr data);
    public class Query {
        public uint open_error,channel_error,connection_error,hosted_error;
        public uint channel;
        public string connection_bssid;
        public uint hosted_state,hosted_frequency_khz;
        public string hosted_bssid,hosted_device;
    }
    static string Mac(IntPtr p,int offset) {
        byte[] b=new byte[6]; Marshal.Copy(IntPtr.Add(p,offset),b,0,6);
        return BitConverter.ToString(b).ToLowerInvariant().Replace('-',':');
    }
    public static Query Read(Guid id) {
        Query r=new Query();IntPtr handle;uint ver;
        r.open_error=WlanOpenHandle(2,IntPtr.Zero,out ver,out handle);
        if(r.open_error!=0)return r;
        try {
            IntPtr data;uint size,kind;
            r.channel_error=WlanQueryInterface(handle,ref id,8,IntPtr.Zero,out size,out data,out kind);
            if(r.channel_error==0){try{if(size>=4)r.channel=(uint)Marshal.ReadInt32(data);}finally{WlanFreeMemory(data);}}
            r.connection_error=WlanQueryInterface(handle,ref id,7,IntPtr.Zero,out size,out data,out kind);
            if(r.connection_error==0){try{if(size>=566)r.connection_bssid=Mac(data,560);}finally{WlanFreeMemory(data);}}
            r.hosted_error=WlanHostedNetworkQueryStatus(handle,out data,IntPtr.Zero);
            if(r.hosted_error==0){try{
                r.hosted_state=(uint)Marshal.ReadInt32(data,0);
                r.hosted_device=((Guid)Marshal.PtrToStructure(IntPtr.Add(data,4),typeof(Guid))).ToString();
                r.hosted_bssid=Mac(data,20);
                r.hosted_frequency_khz=(uint)Marshal.ReadInt32(data,32);
            }finally{WlanFreeMemory(data);}}
        }finally{WlanCloseHandle(handle,IntPtr.Zero);}
        return r;
    }
}
'@
$rows=@()
foreach ($adapter in [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
    if ($adapter.Description -notmatch 'Wi-Fi Direct|Realtek.*Wireless') {continue}
    $ips=@($adapter.GetIPProperties().UnicastAddresses|Where-Object {$_.Address.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork}|ForEach-Object {$_.Address.ToString()})
    $guid=[guid]$adapter.Id
    $mac=$adapter.GetPhysicalAddress().ToString().ToLower() -replace '(.{2})(?=.)','$1:'
    $query=[H017Wlan]::Read($guid)
    $rows+= [pscustomobject]@{id=$adapter.Id;description=$adapter.Description;status=$adapter.OperationalStatus.ToString();is_wifi_direct=($adapter.Description -match 'Wi-Fi Direct');ipv4=$ips;adapter_mac=$mac;native=$query}
}
$candidates=@($rows|Where-Object {$_.is_wifi_direct -and $_.status -eq 'Up' -and $_.ipv4.Count -gt 0})
$result=[ordered]@{wifi_direct_candidates=$candidates.Count;adapter_rows=$rows;pc_ip=$null;actual_channel=$null;actual_bssid=$null;channel_source=$null;bssid_source=$null;board_access=$false;credentials_read=$false}
if ($candidates.Count -eq 1) {
    $ap=$candidates[0]
    $result.ap_interface_id=$ap.id
    $result.pc_ip=$ap.ipv4[0]
    if ($ap.native.channel_error -eq 0 -and $ap.native.channel -ge 1 -and $ap.native.channel -le 14) {
        $result.actual_channel=$ap.native.channel
        $result.channel_source='WlanQueryInterface(channel_number) on unique active Wi-Fi Direct AP interface GUID'
    }
    if ($ap.native.connection_error -eq 0 -and $ap.native.connection_bssid -and $ap.native.connection_bssid -notin @('00:00:00:00:00:00','ff:ff:ff:ff:ff:ff')) {
        $result.actual_bssid=$ap.native.connection_bssid
        $result.bssid_source='WlanQueryInterface(current_connection) on AP interface GUID'
    }
    if ($ap.native.hosted_error -eq 0 -and $ap.native.hosted_state -eq 2 -and [guid]$ap.native.hosted_device -eq [guid]$ap.id) {
        $result.actual_bssid=$ap.native.hosted_bssid
        $result.bssid_source='active WlanHostedNetworkQueryStatus matched AP interface GUID'
        $khz=$ap.native.hosted_frequency_khz
        if ($khz -ge 2412000 -and $khz -le 2472000) {
            $result.actual_channel=[int](($khz-2407000)/5000)
            $result.channel_source='active hosted-network driver-reported frequency_khz'
        }
    }
    $result.adapter_MAC_is_only_candidate=$ap.adapter_mac
}
[IO.File]::WriteAllText((Join-Path $privatePath 'ap-observation.private.json'),($result|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
[pscustomobject]@{wifi_direct_candidates=$result.wifi_direct_candidates;pc_ip=$result.pc_ip;actual_channel=$result.actual_channel;channel_source=$result.channel_source;bssid_obtained=($null -ne $result.actual_bssid);bssid_source=$result.bssid_source;native_results=@($rows|ForEach-Object {[pscustomobject]@{is_wifi_direct=$_.is_wifi_direct;status=$_.status;channel_error=$_.native.channel_error;channel=$_.native.channel;connection_error=$_.native.connection_error;hosted_error=$_.native.hosted_error;hosted_state=$_.native.hosted_state}});board_access=$false;private_evidence='ap-observation.private.json'}|ConvertTo-Json -Depth 6 -Compress
