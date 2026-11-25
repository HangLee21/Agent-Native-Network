# baseline Vue + TypeScript 前端迁移（M-064）

## 已确认方向

2026-11-23 用户确认：**先将 ControlSystem/lh 的新版框架迁入 baseline，以后在 baseline 开发。deploy 暂不迁移，待测试充分后另行同步。** 当前会话获明确授权在独立 worktree 实施，不替代或冒充原独立角色窗口。

本阶段不是将两套 Git 历史整树合并，不是重写固件/采集，也不是声称旧工程 UI 已全部变成 Vue。先建立完整、能独立构建验证的新框架开发源；工程功能按下表逐项移植。**2026-11-24 真实网关接入验证后，用户明确选择新 Vue 为默认启动 UI；原启动器保留为 [START_STUDIO_LEGACY.cmd](../START_STUDIO_LEGACY.cmd)，不再默认。** 这一入口选择覆盖最初的暂缓切换决定，但不关闭功能缺口或授权生产发布。

## 源码布局与权威源

| 路径 | 定位 |
|---|---|
| [frontend/](../frontend/) | 新前端唯一开发源：完整 Vue/TS/Pinia/Vite 工程，含平台壳、网络模块与独立 Studio |
| [框架来源清单](../frontend/FRAMEWORK_SOURCE.json) | 原 lh 精确提交、349 个导入文件的导出字节 SHA256、排除范围 |
| [scripts/network-studio/](../scripts/network-studio/) | 真实/Mock 分离启动、只读网关桥与自动检查；不启动硬件采集 |
| [START_NETWORK_STUDIO.cmd](../START_NETWORK_STUDIO.cmd) | 新框架真实工作区；默认不连接，操作者选择服务器/本地网关 |
| [START_NETWORK_DEMO.cmd](../START_NETWORK_DEMO.cmd) | 显式、独立的合成演示；只打开 mock-studio 入口 |
| [START_STUDIO.cmd](../START_STUDIO.cmd) | **默认新版真实 Vue UI**；10518，复用同根真实预览；原后台保留，无旧浏览器/网卡变更 |
| [START_STUDIO_LEGACY.cmd](../START_STUDIO_LEGACY.cmd) | 原默认启动器的逐字节副本；仅显式运行时打开旧工程 UI，保留原采集/来源/SQLite工程能力 |
| [默认入口适配](../tools/release/start_vue_studio.py) | 识别预览根目录与真实/Mock隔离；后台缺失时复用原启动逻辑的无浏览器/skip-lab模式 |
| [tools/release/sync_frontend.py](../tools/release/sync_frontend.py) | 后续 baseline → ControlSystem/lh 的受控回传工具，默认只检查 |

初次来源为 `haimol/ControlSystem` 的 `lh@bdadc989decf4d383b49dff2def4aa1aa0aa59b5`。使用已提交内容导出，不复制 node_modules、dist、Java 后端、工作机环境文件、现场日志或录制数据库。平台壳保留是为了框架和样式统一，**不意味着 baseline 已有 Java 平台接口，也不把 Python 采集器改作飞控后端**。平台业务需对应 Java 服务；独立网络 Studio 可单独运行。

迁入后在 baseline 修改新框架，lh 是后续集成目标，不再在两边独立改同一前端。旧 vanilla JS 是工程兼容过渡层，不是第二个长期开发源；必要旧界面修复应同时登记向 Vue 移植的对应项。

## 工程功能保留 / 移植矩阵

| 能力 | 现有工程位置/合同 | 本阶段新 Vue 状态 |
|---|---|---|
| NODE、LoRa/ESP-NOW 方向、RF/GPS 新鲜度、三种布局 | 原 Studio + lora.topology.v1 | 已有 Vue 实现；无 GPS 不补点，旧协议保持 unknown |
| 前端选择服务器 / 网关地址 | 新版连接配置 | 已有，真实/Mock 双向拒绝，默认断开 |
| 自动/手动接收源、故障回退 | 原 sources；GET sources / POST sources/select | **已接原合同**；显示偏好与实际源/epoch，未验证来源禁选，换源清理旧观测 |
| SQLite 持久记录、分段回放 | 原 replay；sessions/session/start/stop | **已接原持久库**；刷新后恢复录制状态、正确处理 stop 返回已关闭ID；25帧分页/全局定位/原时间轴，不套用当前清单 |
| 接收器/启动器恢复、fleet/registry 数字身份 | recovery / fleet 与原启动器 | **已接只读状态与合并清单**；登记缺报/历史标签/直接报告分开，恢复未知或过期不报成功；不提供注册/设备配置写入 |
| Agent/逐包/原始载荷与覆盖缺口 | 原 State/timeline 与旧证据模型 | **已接独立证据区**；显式启动只读取证，完整身份+目的自报+原字节才计实收，冲突保留，计数/提交/选路不冒充交付 |
| Wi-Fi/IP 即时方向 | 原 State 的样本时间/boot失效/互证 | **已接独立图层**；双向新鲜证据共同限制互证有效期，LoRa邻居历史样本仍不标成即时互通 |
| 构建产物同源接入 | 旧服务无 CORS；本机受限 Node 服务 | **已提供本机静态服务**；不依赖Vite，独立只读桥与限动作工程桥，不是公网鉴权/生产部署方案 |
| USB 本机刷写 | FLASH_NODES 与原 flash 适配 | CLI/控制台原样保留，不改成未经验证的网页按钮 |
| 跨网络刷写、做卡、分组、机群 | SITE/FLASH_REMOTE/MK_CARDS 等 | 原样保留，未执行任何设备操作 |
| 网关安装、随包 Python、ARM 解码器兼容 | 原 setup/runtime/decoder | 原样保留，未运行安装/SSH/配置 |
| DJI/机器人平台业务与视频 | 导入的平台前端壳，需 Java 等服务 | 仅保留框架源码，未新增后端或真机联调 |

2026-11-24 追加迁移已覆盖上表的核心只读观测与本地录放合同，并修复 [旧自检入口](../tools/mobile_gateway/check_studio.py)。来源/SQLite操作只走独立 [工程桥](../scripts/network-studio/engineering-relay.mjs)；原 [GET-only桥](../scripts/network-studio/gateway-relay.mjs) 权限不扩大。旧工程入口继续保留，注册配置、刷写、机群等未做成新网页控制功能。**原协议全部继续标 unknown；清单缺席不是确认掉电，LoRa历史邻居不是即时Wi-Fi互通，SQLite只录LoRa、不含IP/Agent时间线。** 详情与验证见 [本轮报告](../simulation/results/20261124-M064-core-observability/REPORT.md)。

图形默认清晰布局，红色超时与琥珀色未观测单独告警；加粗箭头/选中邻接/入出向关系表与样本年龄保留证据区别。板内证据需要显式点击开始，页面初次连接不隐式读取原生状态；初始/追赶最多请求最近512个时间线cursor，缺口显式提示，不将缺收件当作未交付。

## 本地运行

要求 Node 满足 [package.json](../frontend/package.json) 的 engines，并用锁文件安装：

```powershell
# 在 baseline 仓库根目录
cd frontend
npm ci --no-audit --no-fund
npm run network:real
```

**推荐双击 [默认 START_STUDIO.cmd](../START_STUDIO.cmd)**：默认10518，打开新Vue真实页。已有同根、real-only预览则复用；陌生、其他checkout或Mock预览占用则停止并说明，不杀进程。缺失的后台通过原启动逻辑以 `--no-browser --skip-lab` 启动，不打开旧UI、不改网卡/触发UAC；原后台已在时不重启。`--which`仅查看分派，`--no-browser`不打开浏览器，`--web-port`或 `NETWORK_WEB_PORT` 可指定端口。旧交付包的自带Python/app分支仍保持，不意味着deploy已迁移。

只需要前端时，也可显式双击 [START_NETWORK_STUDIO.cmd](../START_NETWORK_STUDIO.cmd)；该原有低层入口保持5188默认值，不负责后台或端口复用。若原ControlSystem预览仍运行，应显式选择空闲端口，**不停止或抢占其他进程**：

```powershell
$env:NETWORK_WEB_PORT = '10518'
node scripts/network-studio/dev.mjs --real
```

新 Studio 地址 `/studio.html`，平台共享模块 `/#/network`。真实模式不会启动 Mock。需要合成演示时另用 DEMO 入口，正常与模拟两个启动器不能抢同一端口。网络配置默认 disabled，刷新不会因保存过地址就自动连接；不访问线上 ECS。冷启动新版时请保留启动窗口，关闭窗口会结束该前端开发进程；复用已有预览时不改变其生命周期。

### 构建后的本机服务（不启动后端/Mock/硬件）

```powershell
cd frontend
npm run build
npm run network:serve
# http://127.0.0.1:10518/studio.html
# 自定义端口：npm run network:serve -- --port 10519
```

[静态服务](../scripts/network-studio/serve.mjs) 只绑定loopback，同源提供构建产物与两条受限桥；默认入口能识别同根服务并复用。构建模式没有源码HMR，改前端后需重新构建并刷新；服务端模块修改需重启自有服务。仅复制dist到任意Web服务器仍不等于接入成功，更不是公网鉴权/生产发布方案。不要将本机工程桥直接暴露到外网。

完整工程功能选择本机 Studio 地址 `http://127.0.0.1:8794` 和旧网关协议；8780直连接收器仍只有拓扑。默认CMD可按既有逻辑启动缺失后台；仅运行前端服务不会代开采集器。原生Wi-Fi/IP或逐包证据的显式读取可能使原后台发起只读状态查询，不是启动Agent或发送业务。

[原始来源清单](../frontend/FRAMEWORK_SOURCE.json) 是首次349文件导入凭据，**不是后续授权开发后的当前源码哈希声明**；本轮源码/构建与证据校验另存报告目录。外部Java/Network-v1/飞控/视频服务未迁入；平台壳原有localhost:8080轮询与网络工程接口不是同一能力，回归中明确阻断并记录这些请求。

## 回传 lh：仅显式范围，不整树合并

选择导入完整前端而非整个 ControlSystem 仓库：保留新框架所有组件/测试，但避免混入无关后端/历史。初期选择并行过渡；2026-11-24按用户要求切换默认UI，但保留显式旧入口，确保未迁移工程能力不丢失。回传采用精确范围和三方校验，不强制覆盖。

先在 baseline 提交并验证新前端，再：

```powershell
python -B tools/release/sync_frontend.py --target D:\ControlSystem --check
# 仔细检查 JSON；确认没有冲突后才在后续明确授权的同步任务中执行：
python -B tools/release/sync_frontend.py --target D:\ControlSystem --apply
```

- 只从 baseline 的**已提交** frontend、network-studio 工具及两个新入口导出，不复制 backend/固件/研究/现场配置。
- 目标必须是平台布局的 Git 根、分支必须为 lh。deploy 不接受；不自动提交、合并、切分支或推送。
- 首次以精确原 lh 提交作为基准，后续以同步凭据中的每文件校验值作为基准。处理 Windows CRLF 差异；二进制不归一化。
- 默认 `--check` 不写目标；`--apply` 要求目标前端无未提交/未跟踪修改。发生分叉、目标删除、来源删除或未知同名文件即冲突，不自动删文件。
- 成功同步会写入目标前端的 `.baseline-sync.json` 凭据；需连同 reviewed diff 一起提交。目标源码在 Git 中有前版本，失败应检查实际 diff，不自动 reset/clean/回滚覆盖用户工作。
- 退出 0：一致或安全应用成功；2：只读检查发现待同步；3：冲突，未应用；1：配置/执行错误。apply 不是全目录事务，I/O 失败时检查 diff 后处理。

本轮仅验证工具与只读计划，**不反写 ControlSystem，不改 deploy，不自行部署服务器**。未来新增公网端口/环境变量先由用户配置。

## 验证与状态

本阶段验证记录在主任务卡和独立证据目录；旧 lh 的 450/18/21 历史数字不能自动当作 baseline 本机通过。需要在新位置重跑完整 Vue 测试、类型/构建、Node Mock/只读桥测试、合成浏览器和静态产物检查，并验证旧工程受保护文件无改动。

### 本轮实际结果（2026-11-23）

| 验证 | 结果 |
|---|---|
| Vue/Vitest 完整回归 | 59 文件、450 测试通过 |
| vue-tsc / Vite 三入口构建 | 通过；仍有既有 Vue 测试注入警告和大块提示，不是生产优化已完成 |
| Node Mock / 只读网关桥 | 18 测试通过 |
| 同步工具离线保护 | 13 测试通过 |
| Edge 合成浏览器 + 静态产物 | 21 项通过，0 页面异常、0 意外请求；48 次 real-mode 请求均被夹具拦截，非现场数据 |
| lh 回传检查 | 只读计划：新增 1、更新 2、一致 347、冲突 0；退出 2 表示有待回传，不是检查失败；未实际写回 |
| 原工程受保护路径 / deploy refs | 本轮提交无改动；ControlSystem 仍为原提交且工作树干净 |

完整证据见 [本轮验证记录](../simulation/results/20261123-M064-vue-ts-framework/README.md)。原 lh 来源文件仅有两处迁入适配：浏览器检查增加任务输出目录和安全控制台编码；一个测试文件移除上游 EOF 空白行（已补跑该文件 5 测试），不改 UI/测试逻辑。均列在来源清单。

**这些是框架导入与软件自测，不是 C 独立审计、无线/设备验收、完整工程 UI 移植或生产发布许可。** 验证用 Mock/静态服务器已经结束；本地 real-only 预览使用 10518，默认断开，不启动 Mock，不主动连接原采集器。

19:47 已 fast-forward 集成到原 baseline 分支；主目录重新独立安装依赖并再次通过完整 450 测试、类型与构建。主目录预览 `/studio.html` 已在新 Edge 上下文验证零后端读取；后续编辑 `D:\Multi-Agent Network\frontend` 与该预览是同一份源码，不再使用隔离 worktree 的预览。集成瞬间 17 份未提交文件原字节保持，后续只更新本轮授权的协调材料，其余 16 份工程卡仍保持原字节。补充证据见 [主目录集成复核](../simulation/results/20261123-M064-vue-ts-framework/integration/README.md)。
