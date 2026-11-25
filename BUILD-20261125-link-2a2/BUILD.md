# BUILD 20261125 link-2a2

- images/mid_edge.bin sha256 F4657EDD2315BDF512A7034539B6DB114F819BE045758241FA91444D18FCD2F4
- 修正 2a 的状态字段：link_mode_pending 曾被误替换为 link_tx_ok；
  发送计数改名为 link_send_ok / link_send_fail / link_send_oversize，避免歧义
- 超长守卫改为 len>208（与 lora_ref frame_job 缓冲一致），超长计入 link_send_oversize
- info 回显 link_backend 与三个发送计数
