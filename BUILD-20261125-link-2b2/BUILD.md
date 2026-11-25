# BUILD 20261125 link-2b2
- images/mid_edge.bin
- lora_ref: role=3 现在也服务 frames 队列（可在链路态发送），tick 允许 role=3 入队上行帧
- port.c: lref_port_tx 接受 role=3

真机验证（1 号与 2 号同时处于 link 态 @2404MHz/SF7/BW406/+13dBm）
  1 号 link_rx_frames=2，2 号 link_rx_frames=2 —— 双向收到对方的帧
  验证后两台已恢复 470.5MHz/+14dBm/role=tx
