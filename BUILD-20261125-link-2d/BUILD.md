# BUILD 20261125 link-2d
- images/mid_edge.bin sha256 15E0420D80A7558453365A2372C8701FF15560966DCBCB14769C41E25D7EB3CF
- runtime.c：role==3 加入时序切换。发送上行帧前 lref_port_switch(470.5MHz/SF7/BW125)，
  发送完成后再 lref_port_switch 回链路频段（2.4G）并恢复监听
- 上行频段当前由 LREF_UPLINK_HZ 常量固定为 470.5MHz（后续应做成配置项）

真机验证（eora-air-03，1 号为其邻居）
  role=link 2404000000，neighbors=1（节点1，bidirectional，age 975ms）
  同时网关仍收到：节点1 -35dBm/3.9s、节点3 -52dBm/4.3s
  → 2.4G 链路与 470M 上行并行工作，盲区仅为发送窗口
