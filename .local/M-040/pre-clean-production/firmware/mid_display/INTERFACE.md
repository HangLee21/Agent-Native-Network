# H-005 显示快照接口 v1

本目录由 H 唯一维护。E1 只读引用冻结版本，不修改 H 模块。它只显示本地已观察到的事件，不发送无线报文，不解析或新增 MID 串口协议，不决定路由、ACK、重试或超时。业务事件到显示事件的映射由 E1 负责，并由 E2/C 核对。

## 接入方式

在 E1 的 IDF 工程中将本目录加入 `EXTRA_COMPONENT_DIRS`，主组件声明 `REQUIRES mid_display`。生产入口包含 `mid_display.h`。需要 ESP-IDF v5.5.1、ESP32-S3、EoRa-HUB-400TB 板型。

1. 使用实读 MAC、实际信道、模式 MID/ANN 初始化 `mid_display_identity`。未登记的设备标签必须为 `?`；`mid_display_registered_label()` 只认识已确认的 A MAC。B–E 须等 H 实物登记后，由 E1 配置表提供实际标签，不能按 MAC 取模分配。
2. 在一个普通任务中调用 `mid_display_model_init(&snapshot, &identity)`。此模型由同一个任务维护。不要在 Wi-Fi ISR/回调中直接更新显示；回调事件先进入执行者自己的队列。
3. E1 用 `mid_display_set_help()` 提供与冻结 MID CLI 完全一致的五行帮助，每行最多 21 个可打印 ASCII 字符。默认 MID 帮助明确写着尚未冻结，不能当成真实 MID 指令。ANN 默认沿用原有命令提示。
4. 调用 `mid_display_start(&snapshot)`。返回 0 仅表示创建了显示任务，不表示首帧或像素已经验证。启动失败应只记显示告警，不要因显示失败停止无线或重启板子。
5. 执行者将实际事件映射成 `mid_display_event`，调用 `mid_display_model_apply()`，随后 `(void)mid_display_publish(&snapshot)`。`publish` 只覆盖一个队列槽，不做 I²C。建议限频到每 250ms 一次，重要事件可即时发布。所有统计先在模型中累计，快照被覆盖不会丢累计计数。
6. `mid_display_hardware_state()` 返回 OFF/STARTING/READY/FAILED。READY 在第一次完整帧 I²C 传输成功后设置；它不是实物像素观察。FAILED 后不自动重新初始化显示，业务继续运行。更新者和启动者必须为同一个任务。

快照是同一进程内的 C 结构，不是串口或无线格式。不要将结构体直接序列化，不要依赖 host/ESP 的 `sizeof` 相同。E1 的新 JSON/无线 schema 仍由 E1 唯一拥有。

## 事件身份和关联

数据引用 `mid_display_ref` 包含 origin MAC、boot、seq、flow，以及 ORIGIN/BOOT/SEQ/FLOW 存在位。数值 0 可以是有效值，未知值通过存在位表达。数据事件至少须有真实 ORIGIN/SEQ；ANN 原确认还必须有 BOOT。转发 TX 的 origin 保留最初源节点，不改写成中继。

同一引用的目的 MAC 必须一致。后到的旧报文 MAC 回调可以增加观测计数或错误记录，但不改变较新 TX 的状态。相同 ANN 引用已确认后，迟到的链路结果不把它降级成链路状态。源端 ANN 确认必须来自自己的源引用。MID 拒绝 ANN_CONFIRMED，即便调用者误传该事件。

TX 的 `dst` 是最终目的，`next_hop` 是本次实际选择的下一跳；未知下一跳填全零。模型不从邻居、Planner 意图或旧路径推断当前下一跳。TX 统计包括本机实际执行的源发送和转发尝试，不能当成唯一业务包数。

控制配置使用 `cfg_origin/cfg_seq/cfg_valid`。RECEIVED/APPLIED/STALE 必须有原发送者及序号；REJECTED 可没有可解析来源/序号，此时显示 `--`，不把接收帧的上一跳冒充配置原发送者。APPLIED 只在实际执行配置时产生，收到或排队不算应用。

详细来源和禁用推断见 `hardware/mid_baseline/DISPLAY_SEMANTICS.md`。模型不实现数据去重或接收认证：RX_DEST 必须由 E1 在其合法性、目的匹配和唯一交付判断之后产生；重复目的接收使用 RX_DUPLICATE。中继接收使用 RX_RELAY。

## 页面与计数

PRG 按下稳定 40ms 后只切页：状态 → TX → RX → 配置 → 计数 → 帮助 → 状态。没有无线/命令动作。不要在启动/复位时按住 PRG；RST 仍是硬件复位。

状态页同时保留 TX、目的未知、RX 及 CMD 独立状态。TX 页显示最终目的/实际下一跳和引用；RX 页区分中继与目的接收；配置页显示原发送者/序号/状态；计数页显示排队、提交、MAC 成败、目的接收、原 ANN 确认、超时、本地失败、邻居和路由。CMD OK 只表示命令受理。

数据 seq、flow 和配置 seq 使用 8 位十六进制显示；`--------` 表示缺失。计数超过 99999 显示 `>99999`，完整 uint32 计数保留在快照，累计到 UINT32_MAX 饱和。`!` 表示本次模型生命周期曾出现 TX 错误、配置拒绝、命令错误或非法显示事件；后续成功不清除。TX 页仍保留最后一次发送故障类型，状态页保留故障次数。重置模型才重置这些本地显示统计。

## 驱动约束和来源

驱动沿用已由用户确认显示/PRG正常的 H-004 OLED 初始化序列、字体基础、供电和引脚：SDA18/SCL17/RES21，GPIO36 置高使能共享外设电源，PRG0。400kHz I²C、0x3c/0x3d 探测，每个事务 50ms，约 500ms 刷新。任务优先级 1，栈 6144 字节，快照队列长度 1。显示任务阻塞不占用调用者；E1 应让协议处理任务具有合适优先级，并由后续实板测量确认处理影响，不能把主机检查当成性能结论。

显示故障不关闭 GPIO36 电源，不改变路由/无线，不删除仍可能由生产者访问的快照队列。失败后发布返回 -1。组件只依赖 gpio/i2c/timer/FreeRTOS/log。

`FREEZE.json` 固定生产源码、接口和语义文档 hash。E1 的最终包及 build_id 必须覆盖这些生产文件，不能继续使用 H-004 的 ANN build_id。H 的主机检查、ESP 对象编译尝试、E1 最终链接、设备就绪审查和新实物显示是不同证据。
