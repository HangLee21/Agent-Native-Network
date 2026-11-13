# 五板自主收发与现场记录

五板正式多入口程序已刷入并配置完成。用户目前没有充电宝，先保留USB供电，关闭串口与主机业务发生器，业务由板子每轮自行产生。已验证主机业务端进程停止约20秒时的8条板间新消息源/目的原字节匹配；证据在H-017/20261109-31-PC-absent-USB-power。充电宝、零USB和配置后的实际断电自启待有条件时验证。

现在直接保持五板供电和电脑热点开启即可。8791是无线收件/观测端，没有主机定时发业务；8790是现场地图；8767是独立软件模拟器。测试用逐帧链路过滤和入口故障已清除，五板发生器正常运行。不要用模拟器图上的历史路径判断当前板间RF拓扑。

1. 用 OLED 的设备字母与实际 MAC 对照确认五板，按测点记电源和天线高度。板上发生器设置每轮2–3秒、定长测段；原始字节导出前保持供电。默认没有 GPS，距离由现场测量。
2. 笔记本临时使用2.4GHz热点，所有板的 ESP-NOW 信道与实际热点信道一致。SSID/口令只保存在本机私有配置。USB供电阶段关闭串口；以后检验零USB时，再将各板从电脑移接独立电源。
3. 在PC状态页确认至少两个有效入口，记录每个入口的MAC/boot/地址/租约。正常发包不手选入口。记录PC→远板原字节/目的回执、远板主动→PC实际收件，标明IP直达、ESP-NOW单跳或多跳。
4. 读取当时每方向实际使用的入口。应用租约不续期与正式suspend导致普通Wi-Fi/IP离开分别记录；两种操作均保留板间ESP-NOW。之后另发新事务，在上下两个方向核另一个入口及最终原字节。方向使用不同入口时分别撤除实际入口，不把某一方向原本已用备用入口算成切换。交付未知的旧消息不自动重发。
5. 撤全部PC连接的短时窗口内，各板继续自主业务；恢复PC后立即导出各板仍在RAM的原始记录，并核原身份/字节。环溢出和截断如实保留。掉电前摘要只有计数，不代替逐包字节。
6. 恢复本轮创建的定向故障规则和热点原设置；记录每板最终 build、发生器状态、无线状态、电源和入口状态。现场网关继续显示实际上报，缺失或过期数据留未知。

| 测段必记字段 | 内容 |
| --- | --- |
| 时间与测点 | segment、开始/结束时刻、人工距离m、遮挡、朝向、天线高度m |
| 设备 | label、MAC、boot、build、信道、供电方式、是否零USB |
| 业务 | PC逻辑事务号、原origin/boot/seq/dst、实际入口、源接纳、目的原字节、PC实际收件 |
| 故障 | 撤入口或全PC连接的实际起止、板间链路是否仍有证据、后续新包的入口和接收份数 |
| 限制 | UART/IP日志缺口、RAM环覆盖、摘要掉电窗口、未测物理条件 |

可执行采集：`python -m tools.mid_hardware.field_agent.capture_ip --port 8791 --duration 60 --output <新H-017目录>`。只读，使用实际 E2 Client，不创建模拟端点。

故障工具：`fault_ip.ps1 -Action Inspect` 先检查；Apply 只创建本轮记录的两个精确UDP阻断规则，Restore 只删除这两个已核归属的规则。须在管理权限和实际入口端口确认后使用。当前只执行过Inspect，未创建规则。

零USB、两有效入口、自然覆盖外远端和充电宝接线需实际现场条件，不能用源码或本机HTTP夹具代替。Windows Wi-Fi承载普通IP，ESP-NOW由板运行；同信道要求依据[Espressif ESP-NOW FAQ](https://docs.espressif.com/projects/esp-faq/en/latest/application-solution/esp-now.html)。热点配置接口依据[Microsoft WinRT说明](https://learn.microsoft.com/en-us/uwp/api/windows.networking.networkoperators.networkoperatortetheringmanager.configureaccesspointasync)。
