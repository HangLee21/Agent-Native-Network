# BUILD 20261125 link-2c2
- sha256 5E95D133B6C7751662A3A65DE1032734979BB305CBE6A2990DB3E4C743DE05CB
- app_main: lora24 模式下把 lora_ref_link_pop() 收到的帧解码为 mid 包，
  以 input{type=1} 投递到 inputs 队列（与 ESP-NOW 同一入口），邻居/路由代码无需改动
- 仅在 link_mode=lora24 时执行；espnow 路径零影响
- 未上板验证 lora24 端到端（需两块板同时切换）
