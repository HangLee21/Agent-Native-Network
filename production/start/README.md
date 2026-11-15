# Studio 启动入口

在 Windows 的生产工作副本中双击根目录 `START_STUDIO.cmd`。程序优先读取 `production/local/fleet.json`，否则读取 `production/config/fleet.example.json`。当前示例发布清单尚未冻结，启动会打开明确的离线页面；页面不冒充实时数据或回放。此入口和示例配置尚未经过现场设备验收。

可用参数：`START_STUDIO.cmd --dry-run` 只检查配置和发布文件，不探测硬件或占用端口；`START_STUDIO.cmd --self-test` 使用临时目录、模拟服务和本机临时端口；`--config <配置路径>` 指定配置，`--release <清单路径或发布目录>` 指定发布包。需要 Python 3 和 Windows（实例锁使用 `msvcrt`）。

正常启动时先检查实例锁及配置中的 UDP、TCP 端口；占用时不会停止其他程序。已安装有效发布包但网关未连接时，先显示离线页并自动重试，无需重新配置。仅对配置列出的网关地址逐个尝试，每个候选最多等待约 8 秒，只有服务收到匹配地址及 EUI 的 Semtech PULL_DATA 才认为观察到网关。启动后读取本机拓扑服务的 `receiver.gateway_observed`，变化时在启动窗口输出 `gateway_disconnected` 或 `gateway_observed`；节点上报和网关调度回执不等于目标执行回执。不更改网关或热点配置。按 Ctrl+C 停止本启动器及其子进程；日志位于 `production/local/logs/studio-*`。离线页使用配置的 Studio 端口，端口也被占用时会报错。

## 发布包对接要求

当前 `production/release/manifest.example.json` 是未冻结示例，并不具备下列启动字段；需要由发布负责人在实际发布清单中明确提供。启动器额外要求：

- `schema_version: 1`，`status` 为 `candidate` 或 `validated`，非空 `release_id` 和完整小写十六进制 `source_commit`。
- `services.gateway_module`、`services.studio_module` 为发布目录内 Python 模块名；`services.gateway_args`、`services.studio_args` 为参数字符串数组。可用占位符为 `{udp_port}`、`{topology_port}`、`{studio_port}`、`{gateway_ip}`、`{gateway_eui}`、`{run_dir}`、`{release_dir}`。绝对文件路径使用发布目录或运行日志目录占位符。
- `service_files_sha256` 将发布目录中的运行时 `.py`、`.json`、`.html`、`.js`、`.css` 文件相对路径映射到其小写 SHA-256；清单自身除外。入口模块和依赖均须包含并通过校验。

服务以隔离 Python 环境运行，导入路径只显式加入所选发布目录，不读取未冻结研发工作区。发布包必须带齐实际运行依赖，包括网关服务所用的解码模块。网关参数须明确指定由现场负责人核实的发射配置；示例中的功率为 null，不能当作实测值。对于 `tools.mobile_gateway.studio`，启动器传入所选 fleet、拓扑端口及生产输出许可；发布参数仍需提供 `--output {run_dir}/studio` 和 `--port {studio_port}`。同源 `/api/v1/fleet` 使用相同配置，仅返回 schema 与节点编号/MAC。对于 `tools.flight_link.gateway`，启动器另外传入稳定的 `production/local/command-journal.json`；重启后的未知结果不自动重发。服务文件及这些适配仍须由 M 冻结进实际发布包；离线测试不代表现场启动成功。

节点编号同时读取启动器选定的 fleet 和 `production/local/registry.json`。registry 缺失时使用 fleet；每次请求都会重新校验并合并两者。同一 MAC 和编号跨文件相同可合并，文件内重复、跨文件冲突或格式错误时接口返回错误，前端可在修复后重新读取。registry 由烧录工具独占写入；其中的预留编号不表示设备已完成烧录或在线，设备状态仍以读回和遥测为准。

运行中再次双击会验证并打开已有实例；残留锁由系统释放，启动器不会按 PID 清理其他程序。自身子服务退出后自动重启，退避为 1、2、4、8、15 秒并保持 15 秒上限；服务持续运行 60 秒后重置退避。网关断开时继续观察并等待重连，不更改设备配置。启动器的 Windows 作业对象在进程终止时关闭其管理的子进程。外部程序占端口时只等待，不结束该程序。

正常启动保存所选 fleet 的校验副本；相同路径的原配置损坏或缺失时，从通过 SHA-256 和配置规则校验的副本加载，原文件保留。此恢复不改写 H 的 registry，也不把配置副本当作设备状态。无可验证副本时不猜测身份或无线配置。

同源 `GET /api/v1/recovery` 返回 `schema: studio.recovery.v1`、`state`、`reason` 和 Unix 秒 `updated_at`。状态为 `connecting`、`recovering`、`online`、`recovered`、`unavailable`；正常页面中的状态超过 10 秒未刷新时返回 503/`unknown`。`online`/`recovered` 仅表示服务启动且观察到匹配网关 PULL_DATA，并不证明节点上线、命令执行或射频链路正常；网关失联显示 `recovering`，后续匹配 PULL_DATA 才显示 `recovered`。这是 D 前端的恢复状态对接接口，具体展示由 D 完成。
