# 从这里开始

2026-11-18 M-056 完成做卡工具修复及 04 实卡准备。04 卡已备份并写入，读回确认 NoCloud 实例号一致、主机名 eora-air-04、安装入口唯一，保留了用户、SSH 与原启动参数。04/05/06 编号复用经模拟夹具检查。免网线首启、无线入网及 node_reader active 待上机。

2026-11-18 M-056，04 卡免网线首启与编号复用。主分支 f2e38eb。H-026 负责工具与04实卡准备，C-041只读窄审，M收口。上机测试由用户在通知后进行。

2026-11-15 M-055交付生产d27bb3e：前端明确分为清晰、手动、GPS布局。清晰模式按连接分簇，选节点将一跳邻居展开；手动模式支持缩放/平移后的节点拖动，位置按来源保存在当前浏览器，可重置；GPS只绘制有效坐标，未定位成员仍留列表。D038最终08合成浏览器检查覆盖5/30节点、单节点拖动、更新/刷新/模式切换保存、来源隔离、重置和新节点加入，C040窄审无阻断。证据simulation/results/20261115-M-055-three-layouts/。未操作硬件或重启正式服务，Ctrl+F5更新；这些是界面检查，不是30板RF测量。

2026-11-15 当前M-055：按用户要求改为清晰、手动、GPS三种布局。D038独占生产assets/README实施，C040冻结后窄审；M统一manifest/Git。无后台、硬件或正式服务操作。

2026-11-15 M-054已交付生产3d9765b：20至30节点前端去拥挤。超过30对关系时总览收起连线，点节点显示一跳邻居，可主动显示全部；显示当前/总连接数，隐藏不表示无连接。默认取消边文字，选中查看详情；列表支持编号/标签/MAC搜索、状态筛选和滚动。逻辑节点槽位稳定，真实GPS投影不变；聚焦/稀疏连线避让节点并扩大点击区域。D的5/30节点、435对密集关系、动态/窄屏/搜索/来源/GPS及局部避让浏览器证据已采纳，C039-01已在代表场景关闭。全部为合成主机检查，不代表30板RF；复杂线仍可能交叉/共线，主动展开大量连接使用简单线。未操作硬件、网关、网卡、固件或重启正式服务。证据simulation/results/20261115-M-054-topology-readability/；浏览器Ctrl+F5读取新静态资源。

2026-11-15 当前M-054：20至30节点前端去拥挤，D-037独占assets/README，C-039最终窄审。只改展示与交互，不改协议/来源服务，不操作硬件；用5/30节点隔离浏览器夹具验收。

2026-11-15 M-053已交付生产397cee9并推送：电脑端统一来源管理，兼容旧Semtech UDP/既有HTTP/CH340串口接收；前端按来源ID和selection_epoch切换，不绑定编号1或固定网关格式，支持自动、手动偏好与失效回退。旧网关/原协议decoder/设备NVS/网卡未改；旧UDP载荷与token ACK回环、慢HTTP隔离、串口自动/显式配置worker和浏览器联合检查通过，C038-01已关闭。H最终移除本机临时USB绑定，原START入口自动识别节点1并实收2/3/4/5四源；手动选择后恢复auto通过。正式launcher15924/Studio3364留用户，唯一锁域production/data/node-serial-lease，未来操作须先核实际owner。旧RHF本轮未接入，固定目标192.168.137.10:1680必须仍可达，旧控制全链及实物换网关/拔电恢复未复测。证据simulation/results/20261115-M-053-gateway-adapters/。

2026-11-15 当前M-053：旧网关不可修改，电脑端兼容旧UDP/既有HTTP/串口并与前端解耦。E2-039适配/来源管理，D-036前端，H-025旧协议与现场交接，C-038窄审；不SSH/安装/网卡改动/烧录。主卡coordination/tasks/M-053.md。

2026-11-15 M-052已交付生产93a203d并推送：显式node_serial节点1临时LoRa接收，拓扑节点显示在线/超时未见/观测中断/从未观测与报告年龄，过期Wi-Fi邻居边和LoRa上行边灰化，报告详情默认折叠。10秒上报按35秒超时处理；入口丢失与单节点超时区分。D无头合成场景、E2五项离线检查、C软件窄审完成；H实际25秒收到2/3/4/5共11帧，正式8794已确认节点1身份并接入四源近期报告。未刷板、未做实际拔电恢复或PDR测量。原共享锁访问失败后在确认无owner下迁移生产data/node-serial-lease，当前launcher13796/Studio13272留给用户，今后现场工具用同一锁域。证据simulation/results/20261115-M-052-node-gateway/。

2026-11-15 当前 M-052：节点1临时LoRa网关与明确失联显示；D-035前端、E2-038接收模式、H-024现场单串口、C-037窄审。RHF初始化暂停，不烧录。见 coordination/tasks/M-052.md。


M-051认证交互修复已交付生产d83f9dd：明确账户与最多三次手动重输；原认证失败原因未知，未代用户登录。完整安装仍待用户运行原入口。

M-050已交付生产0b7f0b1：按用户专用直连授权保留网关默认路由并继续配置；私有运行时检查已在本轮实机通过，完整服务安装尚待重试。见M-050主卡。

M-049修复已交付生产4f1ee7f：暂存预算按包计算、自动选/tmp或/var/tmp、SSH正常关闭顺序修正。目标安装仍待用户重开原入口，详见M-049主卡。

M-048完整离线候选已交付生产1816020：随包Python/dnsmasq、单连接一次密码、传输失败有界恢复。目标安装尚待用户运行SETUP_GATEWAY.cmd，见M-048主卡及simulation/results/20261115-M-048-offline-deployment/。

M-048认证/预检修复已交付生产f81dbf6；依赖补齐待用户运行新版后的目标环境记录，网关安装仍未完成。见主卡coordination/tasks/M-048.md。

M-047本轮已完成：生产816958f已推送；实际短探测网关TCP22可达，已恢复DHCP。先前超时原因未确定，真实初始化待用户重开SETUP_GATEWAY。证据见simulation/results/20261115-M-047-gateway-connection/。

2026-11-15 [M-044](coordination/tasks/M-044.md) 脚本离线交付已验收，生产 05d4ca6 已推送。首次用 SETUP_GATEWAY.cmd，日常用 START_STUDIO.cmd；真实网关与换电脑尚待现场验证。

2026-11-15 当前 [M-044](coordination/tasks/M-044.md)：网关 DHCP/本地接收服务＋PC主动连接，E2-037/H-023/D-034/C-036 分工；脚本先完成，现场网络只读，不烧板。主卡路径以主仓 coordination/tasks/M-044.md 为准。

当前追加M-039生产分支/一键部署：主卡coordination/tasks/M-039.md，独立worktree .worktrees/production。用户明天才接串口，今天仅离线软件/算法；不继续探测设备。研发主目录保留，生产代码冻结后同步。

最新用户优先级为coordination/tasks/M-038.md：五板稳定业务和LoRa控制接收、无人机地面联调。各角色按新卡执行，停止自己的旧大矩阵，保留结果；H恢复台架并遵循P0先D后其余板。

当前M-037：先读coordination/tasks/M-037.md及各角色新卡，优先30节点动态无人机通信，基于成熟路由算法复现并允许新帧/跳限；旧阶段不自动扩跑。

2026-11-14 当前：[M-036 高速 30 节点仿真](coordination/tasks/M-036.md)。先读 docs/HANDOFF_TO_CODEX_20261114.md、docs/PROJECT_STATUS.md 和自身新任务卡；用户要求设备未到场先用模拟器推进，八通道网关已在场。本阶段不恢复台架、不烧录，旧硬件流程不自动激活。

[M-035 组网图增加 LoRa 上报来源](coordination/tasks/M-035.md)。

[M-034 LoRa 参考通道](coordination/tasks/M-034.md) 开始准备两板试点。

[M-033 现场邻居边与逐包交付状态](coordination/tasks/M-033.md)，H-018、D-029、E2-031。

[M-032 实际 AD-HOC 拓扑与持续业务前端](coordination/tasks/M-032.md)。H/D 收口现有现场入口，E1-028、E2-030 定位原生遥测。

[M-031 充电宝供电的独立 AD-HOC 节点](coordination/tasks/M-031.md)，E1-027、H-017、C-030。树莓派与现场网关继续沿用 M-030。

[M-030 移动节点、校园地图和笔记本观测网关](coordination/tasks/M-030.md)。E1-026、E2-028、H-016、D-027、C-029 由各自既有窗口接续。

[M-029 板上确定性按需多跳与分机部署](coordination/tasks/M-029.md) 已启动。

[M-028 随机上电与邻居发现回放](coordination/tasks/M-028.md)。

[M-027 Ubuntu 即插即用与无线邻居发现](coordination/tasks/M-027.md)，E1-024、E2-025、H-014、D-024、C-027。

2026-11-08 [M-026 可视化消息发送器与实测仿真首页](coordination/tasks/M-026.md)，接续 M-025 分机与 OLED，D-023、E2-024、H-013、C-026。

2026-11-08 [M-025 分机部署的真实收发及可选 OLED](coordination/tasks/M-025.md)，E1-023、H-012、E2-023、D-022、C-025。

2026-11-08 [M-024 五板实测拓扑统一工作台](coordination/tasks/M-024.md)，H-011、E1-022、E2-022、D-021、C-024。

2026-11-07 [M-023 指定跳数与自适应改道](coordination/tasks/M-023.md)：8767 软件仿真，由 H-010 / E1-021 / E2-021 / D-020 / C-023 分工。8766 仍为独立实板控制台。

当前：[M-022可编辑链路仿真控制台](coordination/tasks/M-022.md)，双击可用入口由现有窗口实施。

2026-11-07 当前：[M-021五节点动态链路仿真与回放](coordination/tasks/M-021.md)。已有五板实测及可视化控制台保留供使用。

2026-11-07 最新：[五板中继替换实验与可视化](coordination/tasks/M-019.md)。旧五板数据已覆盖12场景和120条端点交付，新阶段比较中继退出后的持续业务表现。

2026-11-07 当前执行：用户已连接全部五板并授权全部烧录测试，见[M-018五板阶段](coordination/handoffs/M-018-five-board.md)。原三板成果已验收，五板按原角色继续，新增DE绑定/备份、统一固件、20方向及受控四跳实测。不要继续沿用旧的没有新实验安排。

2026-11-07 最新：M已依据E2/C独立结果验收[M-018](coordination/tasks/M-018.md)三板有限功能阶段：双向24/24交付、经B受控两跳6/6；C标签与PRG用户确认完成。执行成果已交，Git归档尚未完成；当前没有新增实验安排。下列早期待审/待实测描述保留为历史，以CURRENT顶部为准。

2026-11-06 当前：[M-018 MID五板论文复现与OLED集成](coordination/tasks/M-018.md)。按[共同合同](coordination/handoffs/M-018-contract.md)由既有E1/E2/D/C/H独立窗口执行，先核作者代码再做必要适配。H已交付首板OLED并获用户显示/PRG确认，保留该版本；五板MID互通尚未验证。M派发后按需决策，不轮询。以下旧阶段记录保留，具体状态以最新任务卡为准。

最新验收：M-016 到货前协议/固件、采集分析工具及主机验证已通过 C-017 整体独立终审，M 验收六卡 done。源码、文档、当前结果及修复前证据已归档；无无线实测。H-002 后续自动检测取消，h-eora 已删除，等用户通知到货。M 按需决策，不持续监控。

以下保留此前任务登记与阶段记录。

最新协作要求：M 派发后不持续监控；执行者自主推进，需审批、指导或阶段验收时再联系 M。到货检测定时任务已删除，硬件测试等用户通知到货。详见 [M职责](coordination/roles/M.md)。

当前推进：[M-016](coordination/tasks/M-016.md)：五块EoRa-HUB-400TB到货前协议/固件、主机验证和硬件检测准备；原E1/E2/D/C加既有H执行。

最近完成：[M-015网络主线框架](coordination/tasks/M-015.md)：以已发表成熟网络论文为依据，固定计算条件，聚焦动态多跳网络服务与扩展成本；已通过C-016独立终审并由M验收，本轮只做框架与实验设计。

Agent-Native Network；主目录：`D:\Multi-Agent Network`。

每次接手先读[协作规则](AGENTS.md)、[本角色说明](coordination/README.md)、[当前摘要](coordination/CURRENT.md)和[任务索引](coordination/TASKS.md)中分配的主任务卡；再按卡读取指定资料。先核实分支、提交和Git状态，保留已有修改。

最近完成：[M-014真实模型A0执行阶段](coordination/tasks/M-014.md)，已通过E2核验、C-015独立终审并由M验收；[阶段报告](research/agent_native_network/A0_EXECUTION_20261028.md)。累计4次worker、3次真实生成，加载已跑通，严格JSON工具协议未通过；A0尚未整体通过，协议与输出适配属于后续真实业务链；固定业务的网络实验可独立推进。

实验进度总览：[完整实验框架与当前位置](research/agent_native_network/EXPERIMENT_FRAMEWORK.md)。按研究阶段查看输入、实现入口、完成证据和下一步；[M-013](coordination/tasks/M-013.md)已通过C-014独立核对并由M验收；后续每阶段完成后更新总览对应行。

历史阶段[M-012前置实现与有限兼容验证](coordination/tasks/M-012.md)：[阶段报告](research/agent_native_network/PREPARATION_20261028.md)已通过C-013独立终审并由M验收。模型资产与隔离环境已取得，该阶段真实模型前向为0（其后M-014已完成3次生成）；原生ns-3已完成两次动态两跳微场景。研究主线保持M-011修订。

最近完成[M-011方向纠偏](coordination/tasks/M-011.md)，完整要求见[用户任务](coordination/handoffs/M-011-user-request.md)。文献、架构模型与实验规划已通过C-012独立终审并由M验收；后续执行按新任务卡启动，旧计划不自动驱动执行。

最近完成[M-010详细研究报告](coordination/tasks/M-010.md)：D撰写、E2核对数据、C独立终审，M已验收。阅读[详细报告](research/agent_native_network/RESEARCH_PROGRESS_AND_PROBLEM_STATEMENT.md)；本轮没有运行新实验。

最近完成[ORG-003](coordination/tasks/ORG-003.md)独立窗口接管及文档修正，已通过C-010终审并由M验收。实际五窗口及本轮任务见[窗口登记](coordination/WINDOWS.md)。用户已授权向既有四角色窗口发送任务；实际进度只以主卡和交付物为准。

当前框架：[已发表论文支撑的网络研究框架](research/agent_native_network/NETWORK_RESEARCH_FRAMEWORK.md)（M-015整合，C-016终审通过，M已验收）。方向沿革：[动态可扩展具身边缘智能网络修订](research/agent_native_network/RESEARCH_REORIENTATION_20261027.md)（M-011整合，C-012终审通过，M已验收）。此前[需求驱动研究链条](research/agent_native_network/DEMAND_DRIVEN_RESEARCH_CHAIN.md)保留为历史探索。最近保存实验：[009无线阶段](research/agent_native_network/WIRELESS_EXECUTION_STAGE.md)。更早阶段沿研究文件和当前摘要的历史链接查阅。

管理规范：[目录与流程](coordination/README.md)、[组织决定](coordination/DECISIONS.md)、[任务卡模板](coordination/templates/TASK.md)、[实验来源模板](coordination/templates/RUN_MANIFEST.json)。角色说明：[M](coordination/roles/M.md)、[E1](coordination/roles/E1.md)、[E2](coordination/roles/E2.md)、[C](coordination/roles/C.md)、[D](coordination/roles/D.md)、[H](coordination/roles/H.md)。

独立worktree仍读取主目录coordination中的实时任务卡。`simulation/AGENT_COLLAB_PROTOCOL.md`是科研仿真说明，不是窗口协作规则。
