# BUILD 20261125 fast-switch

- 镜像: images/mid_edge.bin (972496 字节)
- sha256: 97D1333F5D40C7ADF13E7E132F297BC83D76446E233124B70E0CB6E1896943FB
- 在 BUILD-20261125-lora-band-power 基础上新增：
  - port.c: 抽出 program()；新增 lref_port_switch()（跳过复位/TCXO/全校准）
  - port.c: lref_switch_last_us / lref_apply_last_us 计时
  - runtime.c: 角色不变且射频已活时优先走快速切换，失败回退整机 apply
  - lora_ref_status 回显 switch_us / apply_us
- 默认行为不变：默认仍是 470.5MHz/SF7/BW125/0dBm，且首次启动走整机 apply
- 回滚: BUILD-20261120-lrn1-health/images/mid_edge.bin
- 未验证：快速切换后的射频一致性（频点/带宽/功率是否真正生效）需实测确认