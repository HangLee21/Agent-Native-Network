# M-034 / E1-029 LoRa参考通道

H可立即使用的入口：[帧及串口事件合同](CONTRACT.md)、[host decoder](decoder.py)、[固定串口样本](samples/serial_rx.json)。样本中的MAC用于标识A/B，boot/时刻/信号值均为synthetic，非实测。

```powershell
python -B firmware/mid_baseline/field_agent/lora_ref/decoder.py --serial-file firmware/mid_baseline/field_agent/lora_ref/samples/serial_rx.json
```

复用函数：`from firmware.mid_baseline.field_agent.lora_ref.decoder import decode_frame, decode_serial_line`。函数不打开串口、不下载依赖。H的唯一串口owner逐行取得JSON后调用decode_serial_line，另加PC本地收件时间。LoRa packet RSSI/SNR在lora对象，Wi-Fi每邻居RSSI在report.neighbors中，不混用。

当前只做准备；未刷板、未运行A/B射频。codec检查见simulation/outputs/E1-029/20261110-01-frame-contract/。板级驱动与引脚证据、候选构建状态在本任务卡续填，不把此host入口当作完整硬件固件。
