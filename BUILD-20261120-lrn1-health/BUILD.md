# BUILD-20261120-lrn1-health

把状态块里**节点自己能量到的字段全部接上**（此前只接了 2 个）。

## 镜像

    images/mid_edge.bin    971408 bytes
    sha256                 2AA298FC6AE6A320...（见 SHA256SUMS.txt）

## 本次接上的字段

| 字段 | 来源 |
|---|---|
| supply_mv | LR1121 自测 VBAT：Vbat = (5*raw/255 - 1) * Vana，Vana≈1.35 V |
| die_temp_c | LR1121 自测温度：T = (raw/2047*Vana - Vbe25)*1000/VbeSlope + 25 |
| outes | 源路由表里 used 的条数 |
| queue_depth | 发送队列 outer.count |
| 	x_drops | outer.overflows |
| lora_sf | 运行时配置 cfg.sf |
| lora_tx_power_dbm | 运行时配置 cfg.power（本设计只用 0 dBm 标称值） |
| ault_flags | 上电原因=欠压 则置位；邻居表当前已满 则置位 |
| wifi_channel | 节点自身 ESP-NOW 信道 |

原有的 eset_reason / heap_free_kb 保持不变。

## 仍然为空（明确说明）

| 字段 | 原因 |
|---|---|
| pi_*（7 个） | 数据在**树莓派**上，需要新增一条串口命令由 Pi 主动喂给节点；
ode_reader 独占串口，需要在其会话里实现 |
| attery_pct | 这些板子由 USB 供电，**没有电池采样电路** |
| GPS 块全部 | **没有定位模块** |

## 验证

- 主机测试 PASSED（0 failures）
- 固件编译 0 错误

## 未验证

未刷入实机：Tailscale 处于 NoState，树莓派不可达。