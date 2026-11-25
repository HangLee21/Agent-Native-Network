# H-005 硬件和显示交接

当前交付的是独立显示组件和硬件准备结果，状态为交审。没有新 MID 固件烧录、无线台架或五板互通结果。

## 当前设备

2026-11-06 的一次有限检查只枚举到已绑定的 A（COM7，CH340 1A86:7523，location 1-2，无 USB 序列号）；COM3–6 是蓝牙串口，未打开。A 实时返回 MAC `90:da:72:48:a4:f8`，旧固件 `ann-espnow`、新近启动 ID `76f1fa15`、mode=idle，build_id 仍为 `ann-v1-75266b4504be32826e859f2d91b06c4c00f62fb662d5e03c23b6572a30e01013`。仅发送一条 info，没有复位、刷写或无线启动，串口 finally 关闭。

B–E 未连接、未绑定、未烧录，MAC/端口/固件和测量均留 null。完整字段和来源见 `BOARD_INVENTORY.json`。A 的 4MiB Flash 来自 H-004 ROM 读取，不能说本次 info 又测了 Flash。原厂整片备份保持在 H-004 私有目录，未上传，也不在此交付中提供备份链接。

后续连接方式：保持 A 的实物标签；B–E 逐块用 USB 数据线接电脑，并说明对应板号，以实际 USB 关联和读出的 MAC 登记。相同 CH340 无序列号、端口可能复用，不能凭 COM 号分配板号。五板实验需要各板供电，并按 E2 的冻结采集方案保留各板原始日志；不能把同时有五块板等同于已具备五路数据采集。

本机 `bindings.local.json` 保留 A 绑定并更新本次旧固件 info 来源；allow_probe=false，不恢复 H-002 或任何到货自动化。

## 显示交付

- 生产模块：`firmware/mid_display/`；公共头文件、IDF 组件、模型、六页渲染和驱动均在 H 独占范围。
- 接口：`firmware/mid_display/INTERFACE.md`；语义：`DISPLAY_SEMANTICS.md`；生产文件及语义 hash：`firmware/mid_display/FREEZE.json`。
- 旧版本保留：H-004 package-01 的 29 个清单文件全部核验，manifest SHA256=`45e373e019bafebad249d4341c8dd5a7f5bdcc1ff8ac1bf65f12f3b1678280ee`；旧源码和包未改。来源差异在 `firmware/mid_display/PROVENANCE.json`。
- E1 使用只读组件，填写实际 MID CLI 帮助、真实 MAC/标签和事件映射；最终构建的 build_id 必须覆盖冻结生产文件。不能为 OLED 增加 MID ACK、重传或端点等待计时器。

## 已验证与限制

`simulation/outputs/H-005/20261106-06-final-host-checks/`：严格 host GCC 编译、状态语义、36 个标签/页面帧缓冲边界组合、计数饱和、错误保留、晚到回调及三种 fake I²C 故障通过。fake 检查确认模型中发布不调用 I²C，失败后保留共享电源和队列；它不是物理故障注入或 RF 性能证明。

ESP32-S3 对象编译尝试在启动编译器时失败：Windows WinError 623，系统 DLL relocation；没有生成任何目标对象，没有链接新 MID 应用。原始失败记录在 `20261106-04-target-objects/`，按本卡停止该分支，没有循环重试。E1 正式集成须检查 SDK/工具环境并完成真实目标编译、链接和容量检查；H 的 host fake backend 通过不能替代它。

旧 H-004 的用户“显示正常，PRG 能切页”只适用于旧版本。新六页显示、最终 MID 程序、显示开关对业务处理的影响和全部无线性能仍未验证。对应数值留 null。

## 设备动作门槛

H 当前停在准备交审阶段：须有 E1 固定包及 hash、E2 冻结台架配置、C-018 对该包无阻断的设备就绪结论，再按 H-005 预算验证已明确绑定的板。先首板启动/CLI/OLED，后向其他设备推广；每板最多一次候选 app 写入，不改原私有备份，不 erase-all/eFuse/force。

RF 用例由 E2 配置限制，最多六次、每次 60 秒、每源最多 1000 包。H 不根据本显示模块自行添加发包、强制路由、ACK、重传或覆盖收益实验。不足设备则只验实际部分。原始日志、唯一来源/启动/序号、实际下一跳、端点唯一接收与快照要对应留证；无匹配回执时 RTT 留 null。

## 交接状态

H-005 物理检查已结束，句柄全部关闭，无后台进程、等待、轮询或调度器。普通交接已落卡，未跨聊天任意发送消息，未执行 Git 写操作。冻结模块等待 E1 集成及 E2/C 核验；新包、C 放行和 E2 配置是后续硬件步骤的明确依赖。
