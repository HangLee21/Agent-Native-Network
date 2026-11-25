# 可选的真正断电自启检查

已验证五板保存角色后，经过 RTS/EN 硬件复位，无需重新下发 LoRa 配置即可恢复 A 接收、B–E 发送。本轮没有拔除全部电源，真正断电启动另按以下步骤检查。

1. 关闭占用板子串口的程序。
2. 断开 A–E 的全部供电，稍候再接上。A 接电脑 USB 数据口；B–E 可继续使用 USB 供电，之后也可接充电宝的 USB 输出。
3. 不发送角色、周期或发包命令。等待约15秒，再只读运行下列入口；A 的 COM 号按实际设备核对。

```powershell
.local/espnow/E1-015/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe -X utf8 -m tools.mid_hardware.lora_ref.receive --port COM10 --duration 35 --output simulation/outputs/H-019/<新的断电收报目录>
```

结果应能见到 B、C、D、E 各自的新 boot 和报告序号，A 的 gateway_boot 也应更新。保存的角色和周期可用 E2 的 `Edge.lora_status()` 读回；只读采集不会向设备发送配置命令。

既有 Wi-Fi 工作台仍使用原热点。LoRa 参考通道的采样状态、RSSI/SNR 与 Wi-Fi 实时互证分别记录，旧 LoRa 快照不续 Wi-Fi 的9秒门槛。
