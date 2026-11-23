# baseline Vue + TypeScript 前端迁移（M-064，第一阶段）

## 已确认方向

2026-11-23 用户确认：**先将 ControlSystem/lh 的新版框架迁入 baseline，以后在 baseline 开发。deploy 暂不迁移，待测试充分后另行同步。** 当前会话获明确授权在独立 worktree 实施，不替代或冒充原独立角色窗口。

本阶段不是将两套 Git 历史整树合并，不是重写固件/采集，也不是声称旧工程 UI 已全部变成 Vue。先建立完整、能独立构建验证的新框架开发源；工程功能按下表逐项移植，验收前保留原默认入口。

## 源码布局与权威源

| 路径 | 定位 |
|---|---|
| [frontend/](../frontend/) | 新前端唯一开发源：完整 Vue/TS/Pinia/Vite 工程，含平台壳、网络模块与独立 Studio |
| [框架来源清单](../frontend/FRAMEWORK_SOURCE.json) | 原 lh 精确提交、349 个导入文件的导出字节 SHA256、排除范围 |
| [scripts/network-studio/](../scripts/network-studio/) | 真实/Mock 分离启动、只读网关桥与自动检查；不启动硬件采集 |
| [START_NETWORK_STUDIO.cmd](../START_NETWORK_STUDIO.cmd) | 新框架真实工作区；默认不连接，操作者选择服务器/本地网关 |
| [START_NETWORK_DEMO.cmd](../START_NETWORK_DEMO.cmd) | 显式、独立的合成演示；只打开 mock-studio 入口 |
| [START_STUDIO.cmd](../START_STUDIO.cmd) | **原工程默认入口，原样保留**；采集、来源选择、SQLite 记录回放仍在原工程服务 |
| [tools/release/sync_frontend.py](../tools/release/sync_frontend.py) | 后续 baseline → ControlSystem/lh 的受控回传工具，默认只检查 |

初次来源为 `haimol/ControlSystem` 的 `lh@bdadc989decf4d383b49dff2def4aa1aa0aa59b5`。使用已提交内容导出，不复制 node_modules、dist、Java 后端、工作机环境文件、现场日志或录制数据库。平台壳保留是为了框架和样式统一，**不意味着 baseline 已有 Java 平台接口，也不把 Python 采集器改作飞控后端**。平台业务需对应 Java 服务；独立网络 Studio 可单独运行。

迁入后在 baseline 修改新框架，lh 是后续集成目标，不再在两边独立改同一前端。旧 vanilla JS 是工程兼容过渡层，不是第二个长期开发源；必要旧界面修复应同时登记向 Vue 移植的对应项。

## 工程功能保留 / 移植矩阵

| 能力 | 现有工程位置/合同 | 本阶段新 Vue 状态 |
|---|---|---|
| NODE、LoRa/ESP-NOW 方向、RF/GPS 新鲜度、三种布局 | 原 Studio + lora.topology.v1 | 已有 Vue 实现；无 GPS 不补点，旧协议保持 unknown |
| 前端选择服务器 / 网关地址 | 新版连接配置 | 已有，真实/Mock 双向拒绝，默认断开 |
| 自动/手动接收源、故障回退 | 原 sources；GET sources / POST sources/select | **原工程保留，尚未接入新 Vue**；地址切换不冒充硬件来源切换 |
| SQLite 持久记录、分段回放 | 原 replay；sessions/session/start/stop | **原工程保留，尚未移植**；新 Mock 的内存演示记录不是它的替代品 |
| 接收器/启动器恢复、fleet/registry 数字身份 | recovery / fleet 与原启动器 | 原工程保留；新界面不臆造自动恢复或注册能力 |
| USB 本机刷写 | FLASH_NODES 与原 flash 适配 | CLI/控制台原样保留，不改成未经验证的网页按钮 |
| 跨网络刷写、做卡、分组、机群 | SITE/FLASH_REMOTE/MK_CARDS 等 | 原样保留，未执行任何设备操作 |
| 网关安装、随包 Python、ARM 解码器兼容 | 原 setup/runtime/decoder | 原样保留，未运行安装/SSH/配置 |
| DJI/机器人平台业务与视频 | 导入的平台前端壳，需 Java 等服务 | 仅保留框架源码，未新增后端或真机联调 |

后续需要将来源管理、真实持久记录/回放、恢复与身份配置逐项做成类型明确的 Vue 工程模块。必须验证行为一致、错误/中断可见、保留旧数据，再决定将原默认 START_STUDIO 切换到新 UI。不能为了换样式丢失工程能力。

## 本地运行

要求 Node 满足 [package.json](../frontend/package.json) 的 engines，并用锁文件安装：

```powershell
# 在 baseline 仓库根目录
cd frontend
npm ci --no-audit --no-fund
npm run network:real
```

或双击新真实入口。默认候选网页端口 5188；如果原 ControlSystem 预览仍运行，应先显式设置空闲端口，**不停止或抢占其他进程**：

```powershell
$env:NETWORK_WEB_PORT = '10518'
node scripts/network-studio/dev.mjs --real
```

新 Studio 地址 `/studio.html`，平台共享模块 `/#/network`。真实模式不会启动 Mock。需要合成演示时另用 DEMO 入口，正常与模拟两个启动器不能抢同一端口。网络配置默认 disabled，刷新不会因保存过地址就自动连接；不访问线上 ECS。

## 回传 lh：仅显式范围，不整树合并

选择导入完整前端而非整个 ControlSystem 仓库：保留新框架所有组件/测试，但避免混入无关后端/历史。选择并行过渡而非立即替换默认入口：暂时多一个入口，换取工程能力不丢失。回传采用精确范围和三方校验，不强制覆盖。

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
