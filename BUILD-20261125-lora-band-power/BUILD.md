# BUILD 20261125 lora-band-power

- 源码提交: 756bb16460d054e54499657718aac109c93f31ae
- 镜像: images/mid_edge.bin  (972192 字节)
- sha256: 57958F49E83DDE1F2373E65106FB343A997B9739C21879A67E4283C91C2759E0
- 构建: ESP-IDF v5.5.1, target esp32s3, 项目 firmware/flight_link/mid_baseline/field_agent/idf
- 变更: lora_ref/port.c、lora_ref/runtime.c（功率可配置 + 2.4G 频段）
- 默认行为: 470MHz / SF7 / BW125 / CR4-5 / preamble8 / sync18 / 0 dBm（与上一版一致，
  由主机可执行测试逐字段验证）
- 回滚镜像: BUILD-20261120-lrn1-health/images/mid_edge.bin
  sha256 2AA298FC6AE6A3208415BBA086343A6A8512895822F6F4AB4FF04F1A9DD735CC
- 验证: 仅编译通过并做主机级等价测试；2.4G 收发、+14/+22dBm 供电与发热、法规限值均未验证