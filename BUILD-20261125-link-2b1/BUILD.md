# BUILD 20261125 link-2b1
- sha256 5446268469C40E232DBBE79581642DBF04053C1A9DE392C5B6EF15C07D7B7009
- lora_ref: 允许 role=3(link) 并在配置解析中接受 \"link\"（此前只放宽了校验，配置会被拒）
- 新增链路收帧环形缓冲与 lora_ref_link_pop()；worker 增加 role==3 分支
- 状态回显 link_rx_frames / link_rx_dropped
- 仅接收侧骨架：不发送、不改 ESP-NOW、默认 espnow

真机验证（eora-air-01，2.4G link 态）
  频率 2404000000 / BW406000 / 13dBm，link_rx_frames=3，link_rx_dropped=0
