# 动态具身网络执行入口准备

2026-10-28。阶段整合：模型文件及隔离环境已取得并校验，模型API可导入；真实A0在加载前因空闲RAM低于既定门槛停止，实际前向0。动态无线入口已完成两个60秒两跳微场景。以下采用两卡最终冻结报告及成功/失败归档，独立审查和验收进度以[主任务卡](../../coordination/tasks/M-012.md)为准。

研究定位沿[方向修订总报告](RESEARCH_REORIENTATION_20261027.md)，本阶段只记录实际入口、成功/失败、运行条件及下一步输入。工程检查通过与模型行为、动态网络服务、跨层收益分别评价。

## 1. 现在已有的证据

| 项目 | 初稿采用的事实 | 还需补齐 |
|---|---|---|
| 模型来源与取得 | [SOURCE_LOCK](preparation_20261028/SOURCE_LOCK.json)固定SmolVLM revision、13文件白名单与许可；E1已实际取得13文件，权重内容SHA和普通Git身份校验记录齐全 | 取得和身份匹配不等于模型加载；来源两文件保持原字节 |
| P2工程入口 | E1已实现独立上下文、私有输入/收件箱、完整到达后可见、显式消费、预算和失败保存；离线16项检查及双节点fixture已有冻结记录 | 模型自主生成交互、多端物理部署及完整网络接口 |
| 来源身份修复 | C初审提出的普通Git tokenizer文件身份问题已由E1修复；新增6项针对性检查通过，归档保留 | 执行者自检与独立验收分别记录，进度见任务卡 |
| A0续行 | 12资源预检通过，13完成取得/隔离安装/API导入；14加载前RAM回落到1,996,738,560 byte，退出1，真实前向0 | 这是资源门槛停止，不是模型不兼容结果；完整加载/视觉输出仍需A0 |
| 动态网络入口 | E2原生构建完成814.531秒；前三次启动失败后，经M明确追加两次原动态种子，各完成60秒并通过日志核验；134文件归档已冻结 | 仅受控两跳B0，未做模型消费、规模或跨层性能验证；独立验收进度见任务卡 |

E1冻结归档的[ARCHIVE_MANIFEST](../../simulation/results/2026-10-28-E1-010-model-entry/ARCHIVE_MANIFEST.json)包含11个run、204份原始记录和15份修复后的入口文件，共219项。D本次逐项核对归档内文件大小和SHA-256，219项均与清单一致；未重新运行这些检查，也未读取活动输出或将模型/环境加入归档。

12–15续行另存[增量归档清单](../../simulation/results/2026-10-28-E1-010-model-entry/continuation-20261028-A0/ARCHIVE_MANIFEST.json)，共106项，D逐项大小/hash核对一致；父清单hash仍指原219文件清单。权重和环境仅留E1的data目录，不装入结果归档。D没有重新读取2GB权重，而是核对取得时的流式身份记录与归档完整性。

E2冻结归档见[网络归档清单](../../simulation/results/2026-10-28-E2-011-network-entry/ARCHIVE_MANIFEST.json)，D逐项核对134份归档文件的大小与存储hash均相符；这属于归档一致性核对，不代替C对原始事件、pcap和检查器的独立审查。

## 2. P2代码实际做到哪里

离线阶段代码见[entry-source](../../simulation/results/2026-10-28-E1-010-model-entry/entry-source/README.md)，最终续行源码见[增量entry-source](../../simulation/results/2026-10-28-E1-010-model-entry/continuation-20261028-A0/entry-source/)。工作目录为`simulation/edge_agent_entry/`；后续运行以明确冻结版本和任务卡为准。

| 模块 | 已有实现 | 当前边界 |
|---|---|---|
| runtime / cli / fixture配置 | 单节点可见context；生成、发送、完整到达、消费、结束；JSON工具/证据引用与调用/字节/墙时限制；保存非法原输出 | fixture是预写动作，0.25秒交付是工程假定，不代表无线或模型自主行为 |
| common / event_schema | 新输出目录拒绝覆盖，公共manifest、源码/配置快照、逻辑与墙时时钟、事件父引用 | details仍为扩展字典；未覆盖完整逐工具JSON Schema，未把backend当安全沙箱 |
| model_backend / model_worker | 局部图像和上下文转提示，本地文件加载、禁远端代码；子进程失败/超时留证，不回退为fixture；隔离模型API已成功导入 | 最终A0仍在worker启动前停止，未完成真实模型加载或输出可靠性验证 |
| preflight / a0 | 来源锁、资源门槛、逐文件身份和任务内累计attempt账本；首次失败停止 | 有来源hash不等于执行授权；来源修复使用可信Git blob身份，不只相信文件自报SHA |
| acquire | 固定PyPI增量解析、隔离安装、固定白名单取得、字节/墙时预算与逐文件核验 | 实际取得通过；不自动重下模型、ONNX或torch，不把API导入当模型加载 |

[08冻结fixture结果](../../simulation/results/2026-10-28-E1-010-model-entry/runs/20261028-08-freeze-fixture/result.json)：两节点、5次脚本调用、2条报文、2次完整到达、1次消费，序列化payload合计411 byte，真实模型前向0。各自输入为64×64合成PNG；文本引用图像不会把PNG算作已发送数据。该数不含无线头部、逐跳重传与空口时间，不能作真实通信效率结论。

16项离线检查覆盖私有上下文隔离、到达前不可响应/消费、父事件与重复消费、非法远端引用、原输出保存、调用/字节/墙时预算、UTF-8长度、过期、finish前消费、拒绝覆盖和模型失败/超时不回退。模型子进程边界使用mock。[11身份修复结果](../../simulation/results/2026-10-28-E1-010-model-entry/runs/20261028-11-source-identity-fix/result.json)另有6项通过，包含同大小篡改并同步改自报SHA仍被拒绝；它们是针对性工程检查，不能与模型样本数相加。

## 3. 硬件、资源预检及恢复状态

以下是E1冻结报告、[09库存](../../simulation/results/2026-10-28-E1-010-model-entry/runs/20261028-09-A0-preflight/inventory.json)及12–15续行中的历史测量，不是本稿重新测得的当前空闲值。

| 项目 | 已保存测量/配置 |
|---|---|
| CPU/RAM | AMD64 Family 25 Model 116 Stepping 1，16逻辑CPU；物理RAM 16,342,147,072 byte。营销型号/物理核心数未由受限CIM取得 |
| GPU | RTX 4060 Laptop GPU，总显存8188 MiB，驱动576.02 |
| 原有Python环境 | Python3.11.5；包元数据torch2.3.1+cu121、transformers4.42.3、Pillow10.4.0、hub0.23.4、safetensors0.4.3，另查accelerate/torchvision；安装记录不等于模型兼容 |
| 09正式预检 | 空闲RAM 1,960,558,592 byte，低于2GiB门槛；空闲VRAM 6,207,569,920 byte，通过2.5GiB门槛；退出2，未下载/未推理 |
| 12续行预检 | 空闲RAM 2,560,176,128 byte、VRAM 6,393,167,872 byte，通过原门槛；此时尚未取得文件或执行前向 |
| 14加载前 | 空闲RAM回落到1,996,738,560 byte，低于2,147,483,648 byte门槛，入口在worker前停止；无实际加载/生成 |
| 隔离覆盖环境 | `data/agent_native/E1-010/env`，transformers4.51.3、tokenizers0.21.1、hub0.30.2、safetensors0.5.3、num2words0.5.14、docopt0.6.2；只读复用原torch/torchvision，实际模型API导入通过 |

[09预检](../../simulation/results/2026-10-28-E1-010-model-entry/runs/20261028-09-A0-preflight/preflight.json)明确门槛是保守执行条件，不是实测模型峰值。E1未为过门槛结束无关进程或修改共享`.venv`。续行已完成官方PyPI解析、六包隔离覆盖安装和模型API导入；模块路径记录显示torch来自原环境、覆盖包来自新环境，pip未卸载环境外旧包。一次预检通过后RAM再次下降的现象说明后续应在加载前确认资源并保存状态，不能据此推断RAM下降的具体原因或模型本身不兼容。

13模型文件实际取得2,034,856,030 byte，依赖包和官方PyPI元数据13,950,751 byte，合计**2,048,806,781 byte**，低于2,500,000,000 byte限额，余451,193,219 byte。准备墙时**556.766秒**，低于600秒。权重本地流式SHA与固定发布值一致，五项普通Git tokenizer文件另核冻结blob身份；[13文件核验记录](../../simulation/results/2026-10-28-E1-010-model-entry/continuation-20261028-A0/runs/20261028-13-acquisition/model_files_verified.json)保存全部本地SHA。API导入成功之后，14仍在加载前停止，实际前向0；未创建worker或attempt账本。

A0原卡最多4次前向、每次128输出token/180秒、累计720秒。0前向不自动授予下一次运行；后续使用现有本地文件/环境，依新检查点生成新资源与配置快照，不重复下载、不改旧执行快照，也不自行降低门槛。本稿不发起A0。

E2冻结环境是Windows、MinGW-w64 GCC13.2.0、CMake4.0.0-rc2、Ninja1.12.0、Python3.11.5；在本卡data目录构建ns-3.46，未安装系统工具或改全局PATH。官方源码包42,684,110 byte，本地SHA-256为`73353e5bc45b3ada8ee079d6122afd76340cc4e2f08068c7d4a6c7c463a60fc8`，未与独立发布方checksum比对；本地VERSION和构建宏与固定来源记录相符。精确环境、失败构建、`-include algorithm`标准头兼容参数和关闭ccache的说明见[NETWORK_ENTRY](preparation_20261028/NETWORK_ENTRY.md)，不改写上游网络语义。

## 4. 成功与失败分别保存

| 证据 | 已知状态及解释 |
|---|---|
| E1 01–04、07–08 | 离线检查/fixture各版本记录；同一脚本入口的重复运行不作多个独立模型场景 |
| E1 05 | 临时构造负例命令误用GBK读取UTF-8配置，未进入runtime；失败保留，不算正式CLI通过 |
| E1 06 | 故意引用未到达信息，保护规则按预期拒绝，退出1；保留失败原文，不改成正常任务成功 |
| E1 09 | 授权后的真实资源预检未达门槛，退出2；下载/推理0是这一冻结记录的事实 |
| E1 10–11 | 最终静态核对及身份校验修复；[10 verification](../../simulation/results/2026-10-28-E1-010-model-entry/runs/20261028-10-final-static/verification.json)和原manifest保留 |
| E1 12–13 | 唯一续行预检通过后，固定13文件取得/身份核验、六包隔离覆盖与模型API导入通过；2,048,806,781 byte、556.766秒 |
| E1 14 | `blocked_before_forward`、退出1，加载前RAM低于2GiB门槛；未创建worker/attempt账本，累计真实前向0；[failure](../../simulation/results/2026-10-28-E1-010-model-entry/continuation-20261028-A0/runs/20261028-14-A0-local-model/failure.json)原样保存 |
| E1 15 | 核对取得/预算、隔离包与原torch路径和旧归档；[verification](../../simulation/results/2026-10-28-E1-010-model-entry/continuation-20261028-A0/runs/20261028-15-continuation-verification/verification.json)不代表再次资源测量或模型加载 |
| E2原生构建 | 已冻结：原生目标完成，814.531秒，在900秒构建预算内；来源、环境、前序失败及成功日志均纳入归档 |
| E2前三次启动 | DLL问题1次、固定CommandLine空格路径问题2次，均未进入Simulator::Run；原失败和尝试计数保留，不能作为无线模拟成功 |
| E2修复后验证 | 已冻结：13/14两个补充run均退出0，各60秒；每次110生成/110接受、68唯一及时收到、42窗末未收到；成功交付均有两跳与实际中继记录，分区窗0收到、42秒后36条新探测收到；C审查进行中 |

### 4.1 E2实际动态两跳结果

冻结配置为3个仿真无线节点、`AdhocWifiMac`、802.11a DCF、6Mbps数据/控制模式、20MHz信道36、16dBm和AODV。源/目的相距200米，中继初始在中点，19–21秒移至远端、39–41秒返回；Friis加125米Range硬截止形成受控分区。这个截止是工程连通性约束，不是实测覆盖。业务为5.0–59.5秒每0.5秒产生一个512字节UDP探测，含12字节SeqTs头；没有应用层可靠重传或模型推理。

| 每次60秒动态运行 | seed0 | seed1 |
|---|---:|---:|
| 生成 / socket接受 / 拒绝 | 110 / 110 / 0 | 110 / 110 / 0 |
| 唯一完整且按2秒截止及时收到 | 68 | 68 |
| 窗末未收到，保留在分母 | 42 | 42 |
| 成功收到有两跳TTL及中继1转发记录 | 68 | 68 |
| 分区安全窗22≤t≤38秒收到 | 0 | 0 |
| t≥42秒新生成且收到 | 36 | 36 |
| 42秒检查点后首份新探测到达时刻 | 42.001712668秒 | 42.001712668秒 |

原始记录入口：[seed0核验](../../simulation/results/2026-10-28-E2-011-network-entry/runs/20261028-13-dynamic0-supplement/verification.json)、[seed1核验](../../simulation/results/2026-10-28-E2-011-network-entry/runs/20261028-14-dynamic1-supplement/verification.json)。两份事件hash与随机流配置分别保存；相同计数是同一受控场景两个种子的结果，不作一般场景统计。42条窗末未收到没有从分母删除，也未猜填内部队列/丢失位置。上述42.0017秒是固定检查点后的新探测到达时刻，不是从实际链路恢复瞬间测得的完整重构时延，更不等于持续服务恢复指标已经验证。

每次实际PHY尝试分类：AODV 193次/0.026336秒，应用143次/0.113256秒，ARP 8次/0.000896秒，MAC控制145次/0.006380秒；合计489次、MPDU尝试101160字节、发射空口时长之和0.146868秒。逐跳和重试付费，ACK计入MAC控制；这些是发射尝试和发射时长，分别区别于成功goodput、接收CCA busy及容量边界。

三次原启动失败（DLL一次、CommandLine空格路径两次）及占用的名额仍保存。M因已定位的启动故障明确追加两次原动态种子，后者用`--M-supplement`记账，总启动5次、实际无线场景2次；单跳没有通过，未进行第6次运行。12项检查器fixture和6项静态检查不是无线场景数。[FINAL_CHECK](../../simulation/results/2026-10-28-E2-011-network-entry/FINAL_CHECK.json)记录六份pcap结构解析和归档核对；独立审查与验收见[C-013](../../coordination/tasks/C-013.md)及M主卡，执行者核验与最终验收分别记录。

## 5. 可复现入口与待恢复条件

E1冻结README给出的工程命令如下，每次必须使用新目录；这里只提供复现入口，不在本稿运行，也不自动占用当前卡的新预算。

```powershell
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.test_runtime --output simulation/outputs/E1-010/<new-check-run>
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.cli --output simulation/outputs/E1-010/<new-fixture-run>
.\.venv\Scripts\python.exe -B -m simulation.edge_agent_entry.test_source_identity --output simulation/outputs/E1-010/<new-source-check>
```

真实A0入口为`python -B -m simulation.edge_agent_entry.a0 --config <task-local-config> --output <new-output>`，需来源锁、M检查点、task-local解释器与模型路径、逐文件身份、资源和累计预算账本齐备。该入口不自动下载。本轮已实际建立隔离解释器、模型目录及`data/agent_native/E1-010/a0_config.json`，13/14各保存执行当时的配置/主卡快照；主卡随后回填变化不回写旧快照。恢复前需新资源与主卡快照，不能原样重跑已存在输出或把旧hash强当当前状态。

E2已完成的启动修复是：子进程PATH优先本卡build/lib和已有GCC目录，直接以argv调用原生exe，向固定CommandLine传无空格相对输出路径。源码证据显示其字符串参数按流提取，绝对工作区名中的空格会截断；单纯加引号不能解决。未改全局PATH。精确入口见[归档启动器说明](../../simulation/results/2026-10-28-E2-011-network-entry/code/README.md)，以下为命令形态：

```powershell
python -B simulation/dynamic_network_entry/network_entry.py run --mode dynamic --seed 0 --M-supplement --output simulation/outputs/E2-011/<new-dynamic0-id>
```

此命令只说明已采用的入口；当前5个启动名额全部用完，不能再次执行或删除reservation补跑。后续需新卡明确预算；已有源码和构建不必重新下载/覆盖，本稿不启动模拟。

## 6. 接下来的三个有限检查点

1. **稳定资源下完成本地A0。** 输入为已取得的13模型文件/核验表、现有隔离解释器和六包版本、来源锁、14资源失败、合成PNG与提示词hash。新任务明确资源复查次数、加载前门槛、调用/时限和失败停止；复用现有文件，不重新下载、不开无界轮询、不关闭无关程序。真实加载后保存峰值内存、输入张量、生成原文、解析及失败，回答能否完成视觉/格式兼容；不能把2GiB保守门槛当实测峰值，不能因0前向隐式重置或扩大预算。
2. **A0通过后做真实场景A1小样本。** 固定两个私有视角/独立上下文、一个可客观评分根问题、合法数据来源与图像hash、相同提示/模型/处理器预算；比较正常证据与缺失或延迟证据，保存模型实际生成的请求、到达、消费、追加/终止及任务答案。新卡明确小样本、调用、图像/token和墙时上限，不自动展开436前向规划。数据许可未落实时仍停留兼容fixture，不能以脚本或合成纯色图声称真实自主负载。
3. **把取得的A轨迹接入已验证动态多跳入口。** 输入为A1请求/正文/计算时延与证据ID、冻结ns-3.46 C++/配置/检查器及Windows运行方案、B0两种子的原始事件/失败、两跳/分区/恢复判据。先在同请求回放下核实际字节、生成—完整到达—消费、截止和未完成请求，再决定可靠正文/请求语义与Drop/队列追踪的最小增量。模型闭环与固定回放分开，新卡定有限次数；不重用本卡5个启动名额，不直接扩64节点或跨层大矩阵。

本阶段来源、取得、导入和受控无线执行各有证据，模型实际加载/自主需求尚缺。因此近期优先顺序为**稳定资源A0→真实场景A1→接动态多跳入口**。更大的[验证方案](reorientation_20261027/VALIDATION_PLAN.md)保留为后续设计，具体机制由实测损失决定。

## 7. 初稿采用的冻结版本

| 输入 | SHA-256 / 读取边界 |
|---|---|
| SOURCE_LOCK.json | 139330b3c5ba0468b06999e0b238a999c21cd6d10f1f106fe03b21d2601503c1；保持原字节 |
| SOURCES_AND_LICENSES.md | 6c2a598a30f60976047f9aca4ea765271d7bb223f1deaca58af50a361350e8c7；保持原字节 |
| E1最终MODEL_ENTRY.md | 998824b1e28d2821a8ddfb8fc9b1194923cac055d48411c1bf4f105d9d459f56；最终交付读取前匹配，替代工程阶段报告输入 |
| 219文件ARCHIVE_MANIFEST.json | 89c819d5b24537561e2fefdc4236abc7d6b06e47e251d5160089dd8cf4107c18；D实际核对219项归档大小/hash相符 |
| E1续行106文件ARCHIVE_MANIFEST.json | 2aae3a4ae64505b794d1f9c8405d491f47454d2bad1bbd971087e4246947cab2；D逐项大小/hash相符，父清单保持原值，不含权重/环境 |
| E1续行verification | a338cb58ab9ff947af945cc1315511eab71f2709ad9151e25b364c7fccd3422d；记录下载预算、来源与blocked_before_forward，不作为实际前向 |
| E2 NETWORK_ENTRY.md | ee5e4577b1130d97ea800e381b75f328167bdab8ee45524d142a3e1844220ac9；M明确交付，读取前匹配 |
| E2 134文件ARCHIVE_MANIFEST.json | c94a2e787d04ddc409f083c02b615074b513e414a2307db73e254c283c76a095；D逐项核对归档大小/存储hash，无差异 |
| E2配置 / 最终verification | config.json为d92013779548f396fa77b780d4383a257c5c39d5bb6410668c65a92a6cee4277；最终核验为f8bc22b5513b437ac91ae24cb6d1604570b777df1268772f4c267320c033f630 |
| 主卡与验收 | [E1-010](../../coordination/tasks/E1-010.md)、[E2-011](../../coordination/tasks/E2-011.md)、[D-010](../../coordination/tasks/D-010.md)、[C-013](../../coordination/tasks/C-013.md)、[M-012](../../coordination/tasks/M-012.md)；本稿记录冻结执行事实，最新审查/验收状态从主卡读取 |

D本次只完成文档整合和归档静态核对，没有运行模型、测试、下载或网络仿真；E1有文件/环境取得与API导入，E2有实际无线运行，按各自原记录解释。历史失败、原manifest与来源两文件保持原字节；独立审查和最终验收按主卡记录。
