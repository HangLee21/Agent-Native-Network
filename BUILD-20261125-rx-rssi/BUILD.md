# BUILD 20261125 rx-rssi

- images/mid_edge.bin  sha256 B0E870905E6B6B93CF57058560E0AC3EEC1F70BAEE1E9824C974AEDBEA4FEC51
- 在 fast-switch 基础上：runtime.c 记录并回显收到的 rssi/snr（rx_rssi / rx_snr）
- 目的：为 2.4G LoRa 做链路质量测量（PDR + RSSI），此前固件只有收包计数
- 行为影响：仅新增状态字段，收发逻辑未改
