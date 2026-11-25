# BUILD 20261125 link-mode

- images/mid_edge.bin  sha256 964E2E53E0EE38BBB2F69BFC2FA87E8011039B53103FD2E700DDE43F00771224
- 新增 link_mode 配置（NVS 命名空间 link / key mode）：espnow | lora24
- 命令 link_mode：读（不带 mode）或写（{"mode":"lora24"}），持久化到 NVS
- info/stats 回显 link_mode、link_mode_active、link_mode_pending
- 注意：本版本只实现 espnow 后端；设成 lora24 会被记住并标记 pending，
  实际仍以 espnow 运行，直到 lora24 后端完成。默认 espnow，行为与上一版一致。
