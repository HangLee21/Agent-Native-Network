# M-034 双板 LoRa 参考上报合同 LRN1

状态：主机合同/样本准备；不是已发布或已实测的射频固件。A LR1121 常收并经 USB UART0 460800/8N1 输出 JSONL，B 单跳发原始 LoRa 点对点帧；Wi-Fi/ESP-NOW 业务继续。相同镜像按运行配置选择 off/rx/tx，默认off。A自己的邻居表须标为local，不伪装成LoRa收件；五移动板都需空口发送时另需第六只接收器。

LRN1使用小端整数，不直接发送C结构体。header44B、row20B、CRC32/IEEE4B，帧长=48+20*n，空表48B、8行全表208B。CRC为zlib.crc32(header+rows)，末尾uint32LE；PHY另启用CRC。最多8行，身份去重键(observer_id,observer_boot,report_seq)。无ACK/重传/LoRa转发，不参与Wi-Fi选路。

| 偏移 | 长度 | 内容 |
|---:|---:|---|
|0|4|ASCII LRN1|
|4|1|header_len=44|
|5|1|row_len=20|
|6|1|flags：bit0截断、bit1 ND表曾满、bit2 tx_delay有效；其余0|
|7|1|实际行数n，0..8|
|8|6|observer MAC|
|14|4|observer boot，非0|
|18|4|报告序号，非0，每源boot单调递增，耗尽后停止发而不回卷|
|22|8|snapshot_at_ms，来源板本地单调钟|
|30|4|Wi-Fi group，非0|
|34|1|本次采样可见allowed ND行总数，0..8|
|35|1|保留0|
|36|4|report_period_ms|
|40|4|tx_delay_ms：采样到提交LoRa发送前的本板延迟；无效时0|
|44|20*n|邻居行|
|44+20*n|4|CRC32LE|

每行：peer MAC[6]、peer boot u32、state u8(0失效/1听到/2互证)、valid_flags u8、seen_age_ms u16、ack_age_ms u16、Wi-Fi RSSI i8、rf_age_ms u16、Wi-Fi channel u8。valid bit0=ack有效，bit1=RSSI有效，bit2=RF样本年龄有效，bit3=channel有效；其他0，无效字段字节为0。缺测输出null。seen/ack/rf年龄采用同NEIGHBORS.md的向上1ms及12000/9000/12000ms裁顶语义，到顶只可视为至少这么老。RF RSSI来自该观察者的ESP-NOW接收回调，非LoRa RSSI。peer→observer为方向；互证只表示采样当时ND状态，不给当前9秒互证续期。

截断标志必须与n<total_rows一致；无邻居也发带新报告序号的空表。ND表满标志不代表已知道遗漏节点数。采样与业务在主任务同一份ND/RF状态中复制，LoRa工作任务只读取不可变副本。USB/LoRa队列有界，满时丢报告并计数，不阻塞业务或逐包写Flash。

## A → 笔记本串口事件

每行schema=lora.ref.v1。接收事件event=lora_ref_rx，必含gateway_id/gateway_boot/rx_seq/received_at_ms、frame_hex、lora对象。lora含frequency_hz/sf/bandwidth_hz/coding_rate/preamble_symbols/sync_word，以及实际packet status的rssi_dbm/snr_db(无测量null)。received_at_ms是A本地收报时间，PC另附本机收件时刻，不能与B的snapshot跨机相减。主机统一由decoder.py解出report，避免固件与主机维护两套JSON邻居定义。

decoder.py的decode_frame(bytes)返回report；decode_serial_line(str)验证A事件并添入解出的report。H可直接导入，不占任何串口。samples/serial_rx.json是固定synthetic样本，对应samples/frame.hex。PHY参数示例只用于解码字段，不是已配置硬件。

发送侧另输出lora_ref_tx：observer_id/observer_boot/report_seq/frame_bytes/snapshot_at_ms、tx_started_ms、tx_done_ms(未知null)、result=submitted|tx_done|timeout|driver_error、累计attempted/submitted/tx_done/skipped。每个尝试都保留原seq；不能用submitted或TX IRQ代替A实际收件。接收率分母须在同一窗口取得B实际发送计数，以唯一身份计算；只有A收件时只能报序号缺口。

## 无需重编译的配置合同

`lora_ref_config`：role=off|rx|tx、report_period_ms(1000..3600000，首轮建议10000)、jitter_ms(0..min(1000,period/4)，建议250)、frequency_hz、sf、bandwidth_hz、coding_rate、tx_power_dbm、sync_word、preamble_symbols、start_on_boot。显式配置才写lr_ref命名空间；只改周期/角色不改变Wi-Fi配置或要求刷写。lora_ref_status返回已应用值、来源版本、帧/空口长度与计数/故障。PHY变更由LoRa工作任务串行生效，不能在另一任务的SPI传输中修改。角色off只关LoRa，不关GPIO36共享电源或OLED/ESP-NOW。

10秒为起始建议，不承诺任何SF/帧长下都合适；驱动按所选参数算ToA并拒绝period不足以完成本帧的配置，不追赶积压。按源MAC/boot分散初相位，每次重抽小抖动。实际频点、功率、端口与天线须由H按400TB资料确认，未验证前不启动发送。首轮仅A收/B发，不测试距离矩阵。
