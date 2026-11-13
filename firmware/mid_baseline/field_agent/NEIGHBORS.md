# M-033 即时邻居查询合同 v1（E1/E2 对接）

新候选保留 field.ip.v2/原业务协议。旧 E1-027 和 E1-028 candidate01 没有此查询；旧30秒/2行 report 运输年龄未知，不能单独支撑9秒互证。五板均为有效 IP 入口时优先每板约2秒查询一次；不提高原广播/report频率、不向无入口板注入新业务。

请求：`{"schema":"field.ip.v2","op":"neighbors","pc_id":310031,"pc_session":<当前PC会话>,"entry_boot":<该板boot>,"query_id":<非零uint32>}`。ID由PC在同一会话中单调递增，按入口维护。要求当前 PC/board boot/有效租约、active&&route_mode。响应 event=neighbors，原 base 字段外带 query_id、ok。无效或过期会话/boot 不产生成功快照。hello 增加 neighbors_api=1。

成功还带 encoding=`nd.rf.v1`、snapshot_at_ms（该板单调钟）、confirm_ms=9000、lost_ms=12000、nd_full（ND表满累计拒绝数）、rows（完整的当前 allowed ND 表，至多8行）。每行恰好8列：

`[peer_mac,peer_boot,state,seen_age_ms,ack_age_ms,rssi_dbm,rf_age_ms,channel]`

state=0失效/1只听到/2互证，直接取同一快照时刻的 nd_state；seen_age 最大裁到12000、ack_age最大裁到9000、rf_age最大裁到12000，因此到达上限只表示“至少这么老”，绝不能标fresh。ack_age在从未互证时为null。RSSI来自真实ESP-NOW回调表最近一帧的 rx_ctrl，缺失/未来时间为null；rf_age是该帧年龄，channel缺有效值为null。RSSI样本并不代表对端发送成功率。ND每行带真实peer_boot，不能用PC注册boot冒充采样epoch；新boot使旧互证失效。ND表完整不等于无限全网盘点，nd_full>0须显示观测容量限制。

隔离：成功查询不会进入保留环，没有event_cursor，poll不会重放它；同一PC session已成功答复的query_id及更早ID拒绝(ok=false,error=old_query)。每板成功快照限速500ms；过快请求ok=false,error=rate_limited，不刷新成功query_id。新PC session重新开始ID，但旧session请求仍被租约校验拒绝。没有新RF发送、NVS写入、发生器暂停或路由表改写。

PC必须在发送前保存(PC本地单调send时刻,entry_id,entry_boot,pc_session,query_id)，仅接受对应未完成请求的一份成功响应；重包、未知ID、超时、旧boot/session一律不能续期。建议请求总往返上限1000ms，丢失后用新ID，下次正常周期重试；不复用已成功/过期ID。不要因收到UDP就给样本盖新时间。

时效上界：在发送前取PC单调时钟，收件后计算RTT。样本在收件时的年龄上界=板内age+完整RTT（保守包含发送/排队/返回）；此后再加PC经过时间，不能跨设备相减。state2只在ack_age上界<9000且seen_age上界<12000、双方当前boot证据一致时可作近期互证；RSSI同样按自身rf_age+RTT独立衰减。两方向分开取样和过期，缺样不判失败。state0是当前表的超时证据，可撤该方向互证；不能由一个方向覆盖另一个方向。板内年龄裁顶、字段未知、超时或没有待定请求时不授予fresh。

H沿M-033独占试点/五板app-only发布；E1只交候选。无入口板继续原发生器/ESP-NOW和限频部分report，PC对它们没有即时快照，保持unknown/独立老化，不假装已被主动查询。具体现场是否出现近期互证由H/E2实测，不保证靠新接口必然全绿。

板内年龄在毫秒差上加1ms后再裁顶，覆盖时间量化误差；PC仍须另加完整RTT及读回后的经过时长。ND接收时间使用ESP-NOW回调时间戳，避免主任务输入排队把旧ACK当新互证；门槛和ND协议不变。
