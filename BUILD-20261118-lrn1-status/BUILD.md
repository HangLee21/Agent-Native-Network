# BUILD-20261118-lrn1-status

LRN1 帧扩展：可选状态块（24B）+ 预留 GPS 块（20B），并修掉三处协议不一致。

## 镜像

    images/mid_edge.bin    970736 bytes
    sha256                 532DAF152AF25662B315D6809D8A178774C347D1CE85F10A229C45072A2A5414

## 本版改动

1. 头部 flags 增加 bit3（状态块存在）、bit4（GPS 块存在）：
   len = 44 + 20*rows + (24 if status) + (20 if gps) + 4
2. 状态块 24 字节：复位原因、供电电压、芯片温度、空闲堆、队列、丢帧、路由数、
   发射功率、SF、故障位、Pi 侧标志/温度/负载/内存/信号/串口错误、电量，另留 5 字节。
3. GPS 块 20 字节预留：经纬度(1e-7 度)、高度、速度、航向、卫星数、HDOP/VDOP。
   无定位源时 flags 为 0，前端显示"无定位"。
4. 固件已填真实值：reset_reason（esp_reset_reason）、heap_free_kb。
   电压与芯片温度仍为 0（需要驱动与实机标定，见 docs/LRN1_EXTENSION_DESIGN.md）。
5. 状态块每 5 帧带一次（seq % 5 == 0），其余帧保持邻居行满额。
6. 修复：truncation 标志位（bit0）此前从未设置，而 decoder.py 依赖它判断截断。
7. 修复：decoder.py 把第 35 字节当"必须为 0 的保留位"，导致编号固件的帧在
   legacy 解码路径上全部被拒收。
8. 新增邻居淘汰：静默超过 10 分钟（ND_EVICT_MS）的邻居从表中移除，
   避免永久失联的邻居长期占据发送名额。

## 验证

- 主机测试（两棵树）：PASSED，覆盖块标志、长度、字段往返、容量 8/6/5、CRC。
- C 编码 -> Python 解码交叉验证：字段全部一致。
- C 编码 -> Python 解码 -> Python 编码：152 字节逐字节相同。
- 服务端解析：把 C 生成的帧喂给 topology_server，status/gps 正确解出，bad_frames=0。

## 尚未验证

- 未刷入实机（三台树莓派当时全部离线）。
- 电压与芯片温度未接入（当前恒为 0）。
