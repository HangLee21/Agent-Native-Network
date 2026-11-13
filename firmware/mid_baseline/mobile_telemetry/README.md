# 移动遥测固件

新入口 mobile_telemetry/idf/ 与旧自主路由固件并存，原MID1/SR01/ND01帧及160字节业务不改，OLED API2不改。路由操作见BASE_ROUTING.md；新增线格式与接收方向、年龄、空缺规则见TELEMETRY.md；接口主卡E1-026。UART460800/8N1。

Pi 持有本机唯一串口，依现有route_config(group/channel/autostart)启动本板后注入位置：

```json
{"cmd":"position_set","nonce":"gps-1","position_boot":7,"position_seq":1,"source":"simulated","fix":true,"age_ms":500,"lat":31.2345678,"lon":121.2345678,"accuracy_m":null}
{"cmd":"telemetry","nonce":"snapshot-1"}
{"cmd":"telemetry_config","nonce":"silence-1","enabled":false,"period_ms":10000}
```

示例坐标只说明格式，是模拟输入。真实提供器用source=gnss；该标签是Pi声明，不代表板独立验证GPS硬件。每次提供器重启换非零position_boot，同epoch position_seq严格递增，拒绝旧序号/近期旧epoch。fix=false时lat/lon/accuracy_m全null；source=unavailable不能fix=true。年龄由Pi测量后报入的age_ms再加板内elapsed，不用Pi/板/对端的单调时钟直接相减。坐标WGS84范围，空精度null。超过30秒不继续输出有效坐标；板复位丢失位置，等待Pi重注入。

position_set仅回位置状态，telemetry_config仅回运行设置，telemetry才给完整有界快照，减少GPS更新时串口开销。快照position为null或lat/lon/source/age_ms/accuracy_m，额外position_boot/seq/age_ms未知为null；fix/stale/position_source明确区分无定位和过期。rf_neighbors是本板物理接收摘要（peer→receiver），仅纳未被link_filter过滤的帧，RSSI取rx_ctrl真实值，不推算距离/端到端链路。rf_rx逐帧给实际MAC、RSSI/信道或null、callback时刻/队列年龄、frame_kind/bytes/filtered；不把relay原始源当上一跳。旧采样均值另给aggregate_last_valid_age_ms。

peer_positions是最近一跳MT01通告及其本地递增年龄；位置包不更新ND01互证状态、不创建实测拓扑边。新通告无RSSI字段。缺rx_ctrl输出unavailable；实际数值0不会改成缺项。模拟GPS不改变rf_source：真板RF+假GPS必须分别标记。

MT01是52B独立一跳无ACK/无转发通告，默认仅active动态共享组模式每10s一帧，idle/静态MID无附加帧；telemetry_config.enabled=false无通告。运行期period可10..60s，不持久，复位默认开启10s。没有新位置也通告明确无定位状态。业务、HELLO、路由队列和在途回调优先，忙时推迟，无追赶突发。每节点默认约0.1帧/秒、5.2应用B/s，不是含802.11封装/硬件重试的空口开销。telemetry_generated/submitted/link_ok/link_fail/deferred分记；查询/注入不额外发位置帧。

本机主机检查命令：python -X utf8 -B tools/mid_baseline/mobile_profiles/validate.py --run <新run名>；validate_json.py同样指定新run。示例文件：python -X utf8 -B tools/mid_baseline/mobile_profiles/examples.py --run <新run名>。这些命令不打开串口。实际注入、RF样本、混合GPS与业务160B兼容由H按独占lease验收；E1不刷写或假报硬件成功。高业务/高串口负载会增加队列年龄，逐帧日志与快照开销需H测量，队列溢出沿原保护停止，不承诺所有负载下无损。

停止/回退：stop等radio=false，按实际此前模式清route/discovery配置和过滤后，由H app-only恢复此前记录的正式包；包中给1969静态/MID与c761自主版本候选，H以刷前实际build选择。位置/遥测设置均不写NVS，不擦NVS分区或eFuse。
