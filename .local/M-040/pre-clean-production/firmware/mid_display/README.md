# MID 显示模块

H-005 从 H-004 已验证的 OLED 版本提取的独立组件。保留板号/MAC、模式、信道、帮助和 PRG 翻页；增加发送、接收、配置及计数页面。MID 没有端到端 ACK 时，源端显示 `UNCONFIRMED`；目的板在本地合法交付后显示 `DEST RECEIVED`。原 ANN 的确认另显示 `ANN ACKED`。

集成接口见 `INTERFACE.md`，事件含义见 `hardware/mid_baseline/DISPLAY_SEMANTICS.md`，来源及生产文件哈希见 `PROVENANCE.json` 和 `FREEZE.json`。这里的 API 不等于 E1 的 MID CLI。

主机验证：

```powershell
& '.local/espnow/H-004/venv/Scripts/python.exe' -B -X utf8 tools/mid_hardware/check_host.py --output simulation/outputs/H-005/<全新目录名>
```

检查包括禁止 MID 伪确认、晚到回调、目的/中继区分、错误保留、ANN 原确认、计数饱和、帧缓冲边界；fake I²C 检查探测失败、第一帧失败和首帧成功后失败。所有这些都是主机合成检查，不是无线或新屏幕实测。

H-005 未刷入新显示模块。当前 A 板仍运行 H-004 已确认的 ANN OLED 程序。目标对象编译尝试因 Windows DLL relocation 错误未启动编译器；目标对象/最终链接仍未验证，交由 E1 正式集成构建核实。新包烧录和 RF 需要 E1 固定包、E2 配置和 C 无阻断设备就绪审查。
