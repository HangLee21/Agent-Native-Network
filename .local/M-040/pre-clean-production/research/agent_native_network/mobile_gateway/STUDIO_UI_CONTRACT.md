# 动态观测入口对接

D是本目录唯一写入者；H负责studio控制器与真实无线观测，不运行主机实板业务发生器。默认现场模式不启动软件模型。旧独立8790网关仍能直接打开本页面；没有studio API时控制按钮不可用。

H实际studio控制接口（2026-11-09已按实际代码绑定）：

- `GET /api/studio/status`：`mode: live|demo`，`demo: {running:boolean,elapsed_s,duration_s,exit_code,...}`，来源/进程说明。
- `POST /api/studio/mode {mode: live|demo}`：仅切数据源，不隐式启动演示。
- `POST /api/studio/demo {action:start|stop|restart}`：明确按钮才启动/停止/新跑软件演示。每次新跑使用独立输出目录。
- `POST /api/studio/gps {enabled:boolean}`只改变显示位置层。
- 同源`/api/v1/state`和`timeline?after=`：沿用H的State合同；切模式/新跑须独立`gateway_instance`，状态和时间线必须来自同一实例，不混入另一模式数据。

节点仍按任意MAC/label报告，非预设五板。`position:null`正常；fake GPS仅`position.source=fake_gps|simulated`时明确模拟。`neighbors`/`edges`必须来自实际报告，IP入口注册不推成RF边。无GPS仅按报告关系布局，并显示“非地理位置、无距离含义”。

agent可选报告`agent:{running:boolean,source:string,tx_count:number,rx_count:number,...}`，或status独立`agents:[{node_id,running,source,...}]`。缺失则显示“未报告运行状态”，不能从发送记录推断仍在运行。演示启动E2独立agent进程的状态及来源应由控制器明确返回，不由前端假造。

包仍用`origin/origin_boot/seq/dst/payload_hex`和原观察者。`route_selected.path`只作选路向量，虚线显示。`tx_submit.next_hop`和`rx_relay|rx_local.previous_hop`单独列实际观察段；不将路径向量补成沿途接收。`sequence_scope=route_request`不和业务seq混合。只有目的观察者和原身份/字节齐全的`rx_local`可标目的本地收到。原始HEX与严格UTF8文本都可看，控制帧不算业务动画。

现场agent/record封装若不同，请H在其卡给实际样本；D按实际字段对接，不猜字段。软件演示始终标host_model传输、模拟RF/GPS；不是实板或真实GPS测量。

M-033增补：前端读取网关`state.edges`作为唯一方向清单，不自行从partial节点清单补边。原始`sample_age_lower_bound_ms`仅显示下界；`sample_freshness=fresh|stale|unknown`和observer_boot来自E2归一化。没有完整年龄时不显示当前新鲜互证，实际RSSI与时间新鲜度分开。字段缺失时留未知。

逐包状态新增源端排队、已提交/中继待收件、目的实收、本轮无路、源端拒绝、最终未知和字节冲突；TX失败不当全程永久失败。持有原包身份的异步目的原字节能升级同一记录；来源重启按origin_boot分开。RAM覆盖/抽样与时间线截断只说明观察可能不完整，不转换成丢包状态。

当前连接时效以E2 `direct_evidence`为独立来源：`direct_freshness`、`direct_confirmed`、`mutual_confirmed`/`mutual_basis`和proof中的双方boot、epoch_verified、valid、confirmed、seen/confirmation_age_upper_bound_ms、12s/9s限制。精确sample_age_ms可为null，旧sample_stale属于旧RSSI样本，不否决新的合法即时证据。界限随浏览器经过时间增加；9s确认过期先取消互证，12s听到过期取消该向fresh。RSSI旧值/旧年龄独立，不借即时query刷新。前端不发neighbors/IP查询，不从UART诊断刷绿。

最终nd.rf.v1归一化可能以sample_kind=rf_frame保存RF年龄，连接fresh以direct_evidence为准，不能被旧RF sample_freshness/stale否决。另消费mutual_valid_for_ms逐浏览器经过时间扣除；同时核seen/confirmation上界与9/12秒门槛。rssi_sample_age_upper_bound_ms/rssi_sample_freshness独立，previous_rf_observation留原partial来源。前端的独立可见到期计时只重画时效，不发HTTP/无线包；HTTP失败不续绿。

M-035 / D-030：邻居来源select只切图、地图节点栏和逐方向详情，默认Wi-Fi；原state/timeline、agent、业务与定位来源保持。LoRa只读同源GET /api/v1/lora/topology，按H-020的schema=lora.topology.v1/source=lora_received_snapshot。labels是MAC→label；reports为E1 report原对象加gateway_id/boot、rx_seq、received_at_ms（网关本地钟）、lora、pc_received_at UTC、pc_receive_age_ms、reader_session；receiver state逐项显示。空报/忙/离线/读取失败不从Wi-Fi补邻居；重连新返回全量替换旧会话报告。只在LoRa选中且页面可见、正在观测时随原2秒刷新读取；切回Wi-Fi即停止LoRa GET，H约12秒无请求自行释放读取器。
LoRa每个邻居方向peer→observer，保留采样当时heard/bidirectional/lost和seen/ACK/RF年龄；绝不变成当前9秒mutual绿线，双方最近快照也是紫色虚线。LoRa RSSI/SNR方向observer→gateway单列，不能当板间Wi-Fi质量。两板本地钟不相减；浏览器只增加PC收报年龄。报告boot/seq、接收器boot/rx_seq、截断/ND满可见。LoRa成员按实收报告/邻居行建立，label沿实际映射；已有Wi-Fi定位可用于显示并标来源，缺定位（即便手选GPS）回退非地理拓扑。LoRa图不产生GPS或agent状态。两种来源各保留视图，切回来恢复原图缩放/布局。
