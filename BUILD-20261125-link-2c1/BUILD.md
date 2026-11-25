# BUILD 20261125 link-2c1
- sha256 B4F8DDFA4A44E16516D898F8D1CF306F8DD94E1808C9B2798414F72DBE026B00
- lora_ref: 新增 lora_ref_link_send()，主任务可经 frames 队列投递链路帧（SPI 仍由 worker 独占）
- app_main: 新增 LINK_LORA24 后端；lora24 模式下 radio_start 不启动 Wi-Fi/ESP-NOW
- 尚未接线：链路接收未投递到 input 队列，因此 lora24 模式下邻居表不会更新（下一步）
