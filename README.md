# Agent-Native Network

**Scalable and Adaptive Networking for Distributed Embodied Edge Intelligence**

面向分布式具身边缘智能的动态可扩展无线网络。更新：2026-10-27。

本机多窗口协作从[START_HERE](START_HERE.md)进入；实际执行范围与验收以[CURRENT](coordination/CURRENT.md)和主任务卡为准。

## 新前端开发源：Vue + TypeScript（2026-11-23）

ControlSystem/lh 的新版完整前端已迁入 [frontend](frontend/)，以后在 baseline 开发。**2026-11-24 用户确认：默认双击 [START_STUDIO.cmd](START_STUDIO.cmd)，打开新版 Vue 真实工作区（10518）；旧启动器原字节保留为 [START_STUDIO_LEGACY.cmd](START_STUDIO_LEGACY.cmd)，不再默认。** 默认入口复用原采集/Studio后台但不打开旧界面、不改网卡；已有同根真实预览会安全复用。只启前端仍可用 [START_NETWORK_STUDIO.cmd](START_NETWORK_STUDIO.cmd)，[START_NETWORK_DEMO.cmd](START_NETWORK_DEMO.cmd) 是独立模拟入口。来源、运行、功能缺口与回传 lh 规则见 [迁移说明](docs/BASELINE_FRONTEND_MIGRATION.md)。**deploy 冻结，旧工程工具仍保留；切换默认 UI 不表示旧工程 UI 全量迁完或生产已验收。**

2026-11-24 追加：原 Sources/epoch、fleet/recovery、SQLite分页录放、Agent/原字节实收证据与独立Wi-Fi/IP图层已接入；默认清晰布局、红色超时/琥珀未观测、粗方向箭头和入出向表。473 Vue/27 Node/25原后端/22构建浏览器检查通过，均为软件与隔离合同验证，未复测现场3/4号问题；[本轮证据/边界](simulation/results/20261124-M064-core-observability/REPORT.md)。本机可用构建静态服务，无需Vite；不是公网部署鉴权完成。

## 工程线：固件与自组网

| 内容 | 文档 |
|---|---|
| **目标与完成度（单一事实来源）** | [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) |
| 文档索引 | [docs/README.md](docs/README.md) |
| 固件版本沿革、build_id 与回滚 | [CHANGELOG.md](CHANGELOG.md) |
| 三平面算法总纲（协议逻辑入口） | [ALGORITHM.md](firmware/mid_baseline/field_agent/ALGORITHM.md) |
| 规模扩展与高速移动规划 | [SCALABILITY_MOBILITY_PLAN.md](docs/SCALABILITY_MOBILITY_PLAN.md) |
| 实现状态（板/编/仿/未） | [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) |

## 当前研究方向

研究具备独立端侧推理能力的设备，如何通过移动、多跳、局部连接和间歇连接无线网络持续协作。模型根据收到的证据产生、追加、改选或终止信息请求；网络发现、路由、竞争排队和分区重构影响证据服务，反过来改变后续推理需求。研究主体是网络系统，核心评价是同资源下的服务连续性、有效goodput、控制成本与达标运行域。

当前以[研究方向修订总报告](research/agent_native_network/RESEARCH_REORIENTATION_20261027.md)为研究总入口。同步/版本恢复保留为控制面模块，HeteroMRTA保留为传统业务和功能回归；近期同时准备真实模型负载与成熟动态无线验证，再选择具体机制。接口和双图用于表达与执行，贡献由可实现机制及同条件结果建立。

## 当前阅读入口

| 内容 | 文档 |
|---|---|
| 偏差根因、五个问题、完整框架、三个候选及近期优先级 | [方向修订总报告](research/agent_native_network/RESEARCH_REORIENTATION_20261027.md) |
| 12篇核心资料：部署、动态性、规模、控制深度及强机制 | [近期文献核查](research/agent_native_network/reorientation_20261027/LITERATURE_REVIEW.md) |
| 动态图、请求接口、队列/干扰与跨层控制权限 | [架构与模型](research/agent_native_network/reorientation_20261027/ARCHITECTURE_AND_MODEL.md) |
| A真实模型、B动态无线、C机制归因的有限实验方案 | [验证计划](research/agent_native_network/reorientation_20261027/VALIDATION_PLAN.md) |
| 唯一当前推进顺序与历史计划定位 | [NEXT_STEPS](research/agent_native_network/NEXT_STEPS.md) |
| 研究文档和历史证据目录 | [研究目录](research/agent_native_network/README.md) |

## 证据状态与历史成果

本次交付为文献、模型与实验规划；新的真实模型、动态多跳和跨层控制实验待后续任务执行。P1多实体本地模型、P2共享硬件独立上下文、P3远端API、P4单模型切分分别记录。规划中的B2扩到64个无线节点时仍固定4个模型端点，其余为中继；模型数量扩展另行验证。

旧成果保留原数据与结论，五类定位见[总报告§8](research/agent_native_network/RESEARCH_REORIENTATION_20261027.md)。主要入口如下：

| 历史证据 | 适用范围 |
|---|---|
| [前期调研与问题报告](research/agent_native_network/RESEARCH_PROGRESS_AND_PROBLEM_STATEMENT.md) | 纠偏前状态维护与任务执行研究快照，正文保留；其中推进顺序已由新路线接续 |
| [009无线执行](research/agent_native_network/WIRELESS_EXECUTION_STAGE.md) | 60次固定业务回放、18任务回合；简化单竞争域，平均busy低于0.3%，没有容量饱和证据 |
| [008需求执行](research/agent_native_network/DEMAND_EXECUTION_STAGE.md)、[需求账本](research/agent_native_network/DEMAND_CENSUS.md) | 因果任务业务与9/18/36任务规模；不替代动态多跳网络扩展 |
| [HeteroMRTA复现](research/agent_native_network/HETEROMRTA_REPRODUCTION.md)、[MOCHA原协议运行](research/agent_native_network/MOCHA_RUNTIME_ENTRY.md) | 原方法运行与协议语义，沿原条件解释 |
| [来源导航](research/agent_native_network/RESEARCH_PROVENANCE_INDEX.md)、[simulation](simulation/README.md) | 历史源码、原结果与证据等级；文档中的旧待办不自动激活 |

[旧需求驱动链条](research/agent_native_network/DEMAND_DRIVEN_RESEARCH_CHAIN.md)、[此前扩展分析](research/agent_native_network/SCALABILITY_COMPREHENSIVE_ANALYSIS.md)及[首版实验链条](research/agent_native_network/RESEARCH_EXPERIMENT_CHAIN.md)作为阶段资料保留。当前路线和执行顺序以上述新入口为准。

## 日常操作（三条命令）

```powershell
FLASH_UPDATE.cmd              # 更新算法/固件：先归一化链路状态，再刷机，最后逐台读回校验
SWITCH_LINK.cmd lora24        # 启用 2.4 GHz LoRa 链路层
SWITCH_LINK.cmd espnow        # 切回 ESP-NOW
```

补充：

```powershell
SWITCH_LINK.cmd status              # 只读，看当前链路配置
SWITCH_LINK.cmd toggle              # 在两个链路层之间来回切，不必记当前是哪个
SWITCH_LINK.cmd lora24 eora-air-01  # 只操作指定设备
FLASH_UPDATE.cmd --skip-normalize   # 只刷机，保留当前 NVS 链路配置
FLASH_UPDATE.cmd path\to\image.bin  # 指定镜像（回滚用）
```

### FLASH_UPDATE 与 FLASH_NODES 的关系

| 能力 | FLASH_NODES.cmd | FLASH_UPDATE.cmd |
| --- | --- | --- |
| 刷写固件 | 是 | 是（内部调用 FLASH_NODES） |
| 刷前归一化链路状态 | 否 | 是 |
| 刷后读回配置校验 | 只校验 build id | 追加参数读回 |
| 单台定向刷写 | 是（`--only`） | 否，需直接用 FLASH_NODES |
| 列出可用镜像 | 是（`--list`） | 否 |

所以两者不是重复：`FLASH_UPDATE` 是**带安全护栏的默认入口**，
`FLASH_NODES` 是**底层原语**（批量刷写、单台定向、列镜像时使用）。

为什么必须归一化：esptool 只写 app 分区，NVS 保留 `link_mode` 与射频角色。
节点若停在 `lora24` 且未设 `role=link`，重烧后会既无 Wi-Fi 也无 2.4G 链路，
只能拆下来接 USB。`FLASH_UPDATE` 默认先写回 `espnow` 规避这一点。