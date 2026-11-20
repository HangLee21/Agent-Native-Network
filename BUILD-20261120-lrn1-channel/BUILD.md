# BUILD-20261120-lrn1-channel

新增节点自身 WiFi 信道上报（状态块第 19 字节）。

## 镜像

    images/mid_edge.bin    970752 bytes
    sha256                 0C2FDCA00DC635173BD5C9A9644D0D7EBE2599AC8631C14FF41E134AAF82B5EA

## 改动

- \lrn1_status\ 增加 \wifi_channel\（写完状态块第 19 字节，原为保留）
- 固件在 \lrn1_platform_status\ 里填入 ESP-NOW 实际使用的信道
- 解码器与接收服务解析该字段，暴露为 \eport.status.wifi_channel\

## 为什么报"节点自己的信道"而不是"邻居的信道"

邻居行里本来就有 \channel\（第 19 字节），但它来自 \info->rx_ctrl->channel\。
实测在这套 IDF 上 ESP-NOW 收包该字段无效，所以那一列**一直是空的**。
而"本节点工作在哪个信道"才是解释"为什么互相收不到"的关键量，且可以可靠获得。

## 验证

- 主机测试：\wifi_channel round-trips\ 通过，PASSED (0 failures)
- C 编码 -> Python 解码：\wifi_channel: 6\，且编解码往返逐字节一致
- 固件编译 0 错误

## 尚未验证

未刷入实机（按用户要求本轮不做上机测试）。