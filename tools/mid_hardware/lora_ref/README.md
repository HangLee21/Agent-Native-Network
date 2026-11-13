# A 收、B 发的 LoRa 参考通道

本目录属于 H-019。M-034 已授权五板发布：先 A 收、B 发验证真实收报，再给 C/D/E 配置发送。使用同一镜像，只写应用分区，保留现有 Wi-Fi、NVS、OLED 和现场服务。

## 本轮实测交付

五板已运行 `mid-lora-ref-v1-6f62fc56a70718250928d818fadd2a943d965587acb6622d36dd04c4b6d7ce50`，A 为 rx，B–E 为 tx；433MHz、SF7、BW125kHz、CR4/5、标称0dBm、周期10000ms，角色和周期已保存并读回。

- A/B 首收两份128B真实报告，每份含4个Wi-Fi邻居。
- 五板发布后35秒收到四源9份；硬件复位后不重下配置，35秒收到四源14份。
- 单独停掉PC的Wi-Fi遥测入口、保留热点和ESP-NOW，26秒仍收到四源9份，随后恢复8791/8794；最终5入口、20方向均互证。

以上为有限接收窗口，不计算PDR。硬件复位恢复已测，真正拔电源启动未测；[可选断电检查](POWER_ON_CHECK.md)。

[每板实际烧录命令](../../../simulation/outputs/H-019/20261110-20-delivery/FLASH_COMMANDS.md)、[每板版本与角色](../../../simulation/outputs/H-019/20261110-20-delivery/FLEET.json)。每板本次仅写app一次，460800传输，总流程约20.6–21秒；较早的115200记录保留。

首轮链路为 B 的 LR1121 发射 → A 的 LR1121 接收 → A 的 USB 串口 → 笔记本。ESP-NOW 和板内业务保留。A 自己的邻居表若从本机读取，必须标为本地来源，不能计作收到一份 LoRa 空口报告。

帧格式、运行角色和配置命令以 [E1-029](../../../coordination/tasks/E1-029.md) 及 `firmware/mid_baseline/field_agent/lora_ref/` 的正式合同为准。主机复用 E1 的解码器，不维护第二套二进制布局。帧合同或目标驱动未交付时，不把准备文件称为可用的 LoRa 网关。

主机入口 `receive.py` 已接 E1 的 `decoder.py::decode_serial_line`。它检查接收者 A 的身份，保存原帧、PC 时间、重复/序号缺口，保留 Wi-Fi 与 LoRa 两类 RSSI，不写现场图。

离线检查固定样本，不打开串口：

```powershell
python -X utf8 -m tools.mid_hardware.lora_ref.receive --input firmware/mid_baseline/field_agent/lora_ref/samples/serial_rx.json --output simulation/outputs/H-019/20261110-02-decode-check
```

后续射频固件与天线确认、允许实际采集后，有限串口入口为下列形式；`COM10` 须先按 A 的 MAC 重新核实，本阶段不执行：

```powershell
.local/espnow/E1-015/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe -X utf8 -m tools.mid_hardware.lora_ref.receive --port COM10 --duration 30 --output simulation/outputs/H-019/<新的收报目录>
```

串口分支使用现有 H 设备租约，460800/8N1，打开前设 DTR/RTS 为 false，不发送任何设备命令。实际串口事件仍须与设备版本、LR1121 状态和 B 发端记录对照；解析成功本身不证明空口链路已验收。应用串口与 ROM 烧写端口不能同时占用。

## 台架身份

| 用途 | 板 | 已登记 MAC | 本轮只读核对端口 |
|---|---|---|---|
| 笔记本接收外设 | A | 90:da:72:48:a4:f8 | COM10 |
| 邻居表上报 | B | 90:da:72:48:a5:cc | COM7 |

端口已在 H-019/05 中重新核对 MAC、当前版本和保留配置；实际烧写工具仍会再核当前应用身份及 ROM MAC。准备配置为 `.local/mid/H-019/pilot.json`，它不向设备下发命令。

## 收报保留的内容

- 原始串口行、原始帧字节、PC 收报时间和 A 的身份。
- 报告者 MAC、boot、报告序号、板内采样时刻、完整性/截断标志及空表。
- 每个 Wi-Fi 邻居的身份、方向、确认状态、采样时年龄和 Wi-Fi RSSI。
- B→A 的 LoRa RSSI/SNR，单独命名，不放进 Wi-Fi RSSI 字段。
- 同一报告身份的重复与序号缺口；缺口不直接作为无线丢包率分母。

PC 收到旧快照不刷新现有 Wi-Fi 的 9 秒互证。不能跨设备直接相减单调时钟；首轮只比较相同报告者 boot 和可对齐的采样窗口。10 秒是初始建议上报周期，实际 LoRa 频率、SF、BW、CR、功率及帧长尚待 E1 的配置合同与驱动验证。

## 天线与接口资料

[厂商产品页](https://www.ebyte.com/product/2472.html)列出 Sub-GHz 410–493 MHz 与 LoRa 2.4 GHz 2400–2500 MHz。该频段说明不能代替具体射频口、天线或板版次的确认。不要把其他系列的 SMA/IPEX 条目当成本板接口。

后续已取得官方原理图3699与完整手册2472，来源、哈希及裁图保存在 H-019/04。手册组件①为 LoRa 2.4GHz，②为 LoRa Sub-GHz IPEX-1；屏蔽罩朝自己、USB向下时②在左上。用户经M报告五板天线均已连接，具体天线型号尚未目视核实，不重复索取证明。首轮用厂商 EBYTE BSP 的标称0dBm Sub-GHz配置，真实芯片与接收结果由首对板检验。

原理图引脚表为 NSS8、SCK9、MOSI10、MISO11、RESET12、BUSY13、DIO9 IRQ14；GPIO36为与OLED共享的电源控制，不因LoRa off拉低。现有 ESP-NOW 成功不代替 LR1121 检查。

## 后续发布快路径

沿 H-018 的身份、回退包、app-only 和写后启动核对流程执行，不套用示例配置覆盖 NVS。当前程序的应用串口为 460800，保存的 ROM 刷写命令为 115200；这两个速率不是同一用途。

已有 A/D/E 日志中，915056 字节应用写入耗时 50.5/50.7/50.3 秒，总流程 60.409/60.610/60.412 秒。来源见 H-019/01 的 `SAVED_FLASH_TIMES.json`；本轮没有测速或新烧写。若后续本来就需要刷写，只在那次操作中尝试较高可靠速率，失败才针对该次诊断，不做反复测速刷板。

烧写入口已支持 `--task-id H-019 --flash-baud 460800 --preserve-autostart`；旧默认115200不变，ROM核身份仍115200。只在本次必要发布时尝试460800，不增加独立测速或反复刷写。实际执行的完整镜像路径、SHA256和命令会随每板结果保存，不用占位命令冒充已执行。

最小验收为 B 发出一份实际报告、A 空口接收、笔记本使用同一解码器解析并保存；再与 B 同时间窗邻居快照对照。此后才扩展C/D/E，并核持久配置和真正断电后的自主恢复。

## 工作台中的 LoRa 来源（H-020）

正常入口仍为 http://127.0.0.1:8794/ 。组网图选 LoRa 时，浏览器持续读取同源 `/api/v1/lora/topology`；其数据来自 A 的实际串口收报，不载入历史采样。首次接入需等待约10秒报告周期。Wi-Fi 默认入口及业务、位置来源独立保留。A 在这一通道是接收器；其他板报告里的 A 邻居行不等于 A 自己的邻居报告。

Studio 按需启动单个 SDK Python 子进程，持有 `H020-Studio-LoRa` 全局硬件串口租约。串口为460800、DTR/RTS=false，不发设备命令。当前身份绑定为A的USB位置 `1-1.3`，当下端口COM10；重插同位置可按新COM号恢复，换USB口须先重新核身份，程序不会扫描并占用其他板。缺设备或租约忙均在接收器状态中显示，查看期间可自动重连。退出LoRa页约12秒后释放串口；Studio关闭或父进程管道EOF也会结束读取。不要同时另开串口助手读取A。

`reports` 仅保存当前读取会话每个报告者的最新有效快照。`report` 为E1解码原字段，`gateway_boot/rx_seq/received_at_ms` 来自A接收封套，`pc_received_at/pc_receive_age_ms` 是电脑收件时刻与单调钟年龄；它们不能相减推算不同设备的传输时延。重复/倒序序号不续收件年龄，重连清空旧会话。邻居行方向为 `peer_id → observer_id`，行内RSSI为Wi-Fi测量；封套 `lora.rssi_dbm/snr_db` 是 `observer_id → A` 的LoRa接收质量。采样时的双向邻居状态不代表当前9秒实时互证，不证明业务包交付或LoRa业务多跳。

`/api/studio/status` 的 `lora_receiver` 只观察生命周期，不启动读取；`live.serial_opens=0` 指原Wi-Fi/IP观察器，LoRa串口归属以该接收器字段为准。H-020现场证据在 `simulation/outputs/H-020/`，合成时钟/重启隔离测试为 `python -m unittest tools.mobile_gateway.lora_test -v`，后者不打开硬件。
