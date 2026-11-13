# MID 论文与作者候选源码核查

版本：D-015 source-freeze-01，2026-11-06。供 E1/E2/C 先行复核；D 未运行作者工程、求解器、Linux 路由命令或设备。本文的代码行为结论来自固定提交的静态阅读。实施选择仍由 M-018 合同和 E1 接口冻结记录确定。

## 1. 来源、版本与许可

| 来源 | 本次取得的版本 | 能确认的内容 | 尚未确认 |
|---|---|---|---|
| 本地 `T-RO24_MID.pdf` | 3,961,285 bytes；SHA-256 `dd1c42d21e816e8337e0ac5071c8fed7f43af5d6a4fa2705314b40741f3e2d08` | 全文16页及附录已读；原页3、4、13、15已渲染核图/公式 | 本地文件与出版商最终PDF、arXiv各版本的逐字对应尚未比对 |
| [论文作者提交页](https://arxiv.org/abs/2306.08737v2) | arXiv:2306.08737；v1 2023-06-14，v2 2024-09-16 | 标题与8位作者对应；可区分预印本版本 | 页面没有建立下述具体提交与三组仿真、三组实机实验的对应关系 |
| [miod 固定提交](https://github.com/danmox/miod/tree/d4ba825cb2068301f7811e522c4cc44092796e1e) | `d4ba825cb2068301f7811e522c4cc44092796e1e`；2021-12-17 17:52:22Z；tree `45f36b1bd5ccfe72453f09d6f77c02c8c5294dcd` | 提交API作者名 Daniel Mox；包含 SOCP、连接规划、ROS、Linux 路由脚本 | 不能称“TRO24最终实验源码” |
| [mid 固定提交](https://github.com/danmox/mid/tree/653f5b35a8e54402ef70f50c152292a0d830260b) | `653f5b35a8e54402ef70f50c152292a0d830260b`；2024-05-14 09:17:46Z；tree `4e644281bbab250836e2f4ea6212836bac26520d` | 提交作者名 Daniel Mox；README明确已不维护；模块含 robust_routing、connectivity_planner、or_protocol | 更新日期接近论文并不能证明论文使用此提交；也不是旧UDP/Linux脚本的直接替代版本 |

M-018 记录论文 DOI 为 [10.1109/TRO.2024.3463493](https://doi.org/10.1109/TRO.2024.3463493)。本次 DOI 网页读取失败，出版商条目未独立复核，不能把该次网页失败写成 DOI 不存在。

取得方式：固定提交 codeload zip + GitHub commit/repo API；单请求上限60秒，单项上限32MiB，本地解包限制96MiB/仓库，检查归档路径后解包。首轮受沙箱网络限制失败，获准后下载成功；未使用 Git checkout/pull。作者代码只保存在忽略目录 `.local/mid/D-015/source-01/`，本文及清单不复制整份作者源码。

| 本地归档 | bytes | SHA-256 |
|---|---:|---|
| `miod.zip` | 2,346,883 | `502461b85893c065fd6a0bdd923dc0d9a66d80b3619cd0ed3bc427f35161213f` |
| `mid.zip` | 15,924,591 | `bf575eadf786d5986788a54442d2b678a3cc02dede3b39bcc9dddbf87b8852d8` |

归档、API元数据及辅助来源的下载URL、字节数和hash见同目录 `DOWNLOADS.json`、`AUX_DOWNLOADS.json`；选定源码的路径、行数、hash见本目录 [SOURCE_FILES.json](SOURCE_FILES.json)。固定提交中的行号均按原始文件计数。

许可核查：两仓库解包树均未找到文件名以 LICENSE/COPYING 开头的许可文件；GitHub repo API `license` 均为 null。miod `socp/package.xml:7` 声明 BSD，但 `network_planner/package.xml:10`、`routing_protocol/package.xml:8`、`routing_msgs/package.xml:7` 为 TODO；mid 的 robust_routing、connectivity_planner、or_protocol 的 package.xml 均为 TODO。只能记录这些包级声明，无法据此给整个仓库补授 BSD 许可。公开重发作者代码或直接复制许可未明的模块前，需解决对应模块授权；本次不联系作者，不阻塞按已记录公式和行为撰写适配说明。

## 2. 原论文每组实验对应什么

页码为本地PDF印刷页码。数值是原文报告，本次没有复现这些结果。

| 场景 | 原始节点/需求 | 比较与测量 | 对五板工作的边界 |
|---|---|---|---|
| §IV-A，Fig.7，p8，仿真范围 | 2 task + 2 network；50×50m方波路径；双向 `(m,ε)=(0.2,0.7)` | 固定位置和可移动基础设施都用优化路由；模型QoS，范围约20→40m | 四板静态路由功能不等于此移动范围实验 |
| §IV-B，Fig.8，p8–9，仿真巡逻 | 3 task + 2 network；四叶形轨迹；循环业务 `(0.2,0.9)` | 固定位置与移动；模型QoS失配时间28.19%→0%；另测不同规模规划耗时 | 五节点数匹配也仍缺轨迹和SDP移动执行 |
| §IV-C，Fig.9，p9–10，仿真替换 | 外圈4 task，内圈4 network及1替补；2→4、3→1，`(0.2,0.7)` | 替换期间位置与路由变化；静态参考15–27s出现12sQoS中断；约2.85Hz重规划 | 五板无法原样重建此9设备场景 |
| §V-A，Fig.10–11，p11，实机范围 | 2 task + 1 network；固定中继距静止源20m，另一task直线远离 | 固定与移动；iperf3吞吐；约2.5Mbps支撑160→220m；25m移动平均 | 原天线/场地/飞行条件不可照搬到ESP-NOW |
| §V-B，Fig.12–13，p12，实机巡逻 | **3 task + 3 network，共6台**；task逆时针直径40m圆 | 实机平均速率/时延；1s采样、20s移动平均；60s后约5Mbps、低于115ms | 五板3+2属于缩减适配，不是六节点原配置；本段未给实机静态对照曲线 |
| §V-C，Fig.14–15，p13，实机替换 | 2 task固定约30m；2 network + 1替补，共5台 | t≈13s退出并替换；瞬时吞吐骤降，20s移动平均约>4.5Mbps，稳定后约8Mbps | 固定五板切路可验证路由/配置执行，不能替代自主位置补偿 |

原文还存在节点编号冲突：p13首段说 `.3` 退出，下一段及Fig.15 caption说 `.4` 退出。图14标识已视觉核查；本次不自行择一修正文意。原文没有说明退出/加入是断电、停路由、改变成员表、停止位置发布或飞离；也没有提供故障检测、规划输入删节点及替补激活的操作序列。

三组仿真用ROS/Gazebo和式(1)–(2)模型；实机在Montevideo郊外低干扰场地，用NUC/Ubuntu18.04、ROS multi-master、Intel AX200 2.4GHz ad-hoc/IP、定向天线、PX4/GPS/LIDAR。后两组实机将天线由腿移到机臂，刻意降低水平面增益。模型Fig.3参数 `L0=-53,n=2.52,N0=-70,a=.2,b=.6` 不等同于每组实机场地拟合参数；p11–12明确承认场地模型过于保守。

## 3. miod 从位置输入到无线转播和路由执行

以下所有作者文件均固定在 miod `d4ba825...`。

| 步骤 | 源码依据与固定链接 | 静态确认 |
|---|---|---|
| 位置/ID | [network_planner.py L45–121](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/network_planner/src/network_planner/network_planner.py#L45-L121) | task/comm IDs合并，ID映射`10.42.0.id`；用`#`展开pose topic，订阅`PoseStamped`，收到位置标记为True |
| SOCP与发布 | [同文件 L251–302](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/network_planner/src/network_planner/network_planner.py#L251-L302) | 只接受optimal和正确变量数；按F序还原`N×N×K`；过滤`α<=0.01`；输出`node,src,dest,gateways`到`network_update`；未归一化 |
| ROS订阅 | [launch_sub.launch L3–8](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/launch/launch_sub.launch#L3-L8)、[rt_update_sub.py L7–31](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/rt_update_sub.py#L7-L31) | `rt_upd`重映射到`/network_update`；回调将ROS消息打印为嵌套列表 |
| 服务器转换 | [main_srv.py L88–119](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/main_srv.py#L88-L119) | pexpect启动上述roslaunch，读stdout并作JSON转换；存成`update[node][src]=[[dest,gw...],[weights...]]` |
| 周期广播 | [main_srv.py L29–49](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/main_srv.py#L29-L49)、[L196–205](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/main_srv.py#L196-L205) | 默认每1s广播`[HOST,seq,全表]`到`10.42.0.255:54545`；每次发送seq加1，即使内容未变 |
| 去重和转播 | [main_cli.py L304–341](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/main_cli.py#L304-L341) | 用payload原始source而非UDP前一跳`cur_src`作为序号表key；首见或严格更大seq接受；仅`source==SERVER`更新自己的表；原字节再次广播，保留原发送者与序号 |
| 本地路由执行 | [main_cli.py L264–302](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/main_cli.py#L264-L302)、[main_srv.py L163–194](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_protocol/src/main_srv.py#L163-L194) | 按源IP创建policy rule/table，对目的route先del后add，累计权重抽样；一轮命令后sleep(.5)，不是精确硬实时2Hz |

因此，候选旧工程确实含应用层多跳配置扩散。广播没有端到端确认、原子提交或双版本切换；周期发送不能当成每个节点都已安装成功。该逻辑也不能被解读成ESP-NOW本身自带多跳路由。

默认客户端SERVER是`10.42.0.13`；`--srv`可以覆盖（main_cli L30–44、L385–402）。这必须与实际Planner/服务器身份对应。序号从0开始、去重表仅存内存，未含boot/epoch；服务器重启后的低序号会被仍运行的客户端拒收，直到超过旧值或客户端状态重置。接收buffer4096字节；当前代码未见分片重组。以上边界需在适配中记录，不擅自新增可靠控制协议。

## 4. 复现必须明确处理的差异

### A. 论文Bernoulli与源码累计抽样

论文p7 §III-B写每0.5s对各`i,j,k`掷Bernoulli(α)。源码每个本地源/目的条目只取一个`coin∈[0,Σw]`，比较累计权重。若只执行首次命中，则第j项概率为`w_j/Σw`；这是条件归一化的单一下一跳选择。单网关分支无论权重多小都尝试使用；`Σw<1`的剩余闲置比例并未按α保留。过滤0.01还会改变可选集合。不能宣称该执行器实现了式(9)的原始时间份额调度或其QoS保证。

### B. 缺少break，不能推断“最后下一跳胜出”

main_cli L282–293 / main_srv L177–186首次命中后没有break，后续更大累计阈值也会命中，并记录日志、打印及尝试`ip route add`。`subprocess.run`的返回码被忽略，stdout/stderr丢弃；日志在确认成功前写入。

系统命令依据：[iproute2 v4.15.0 iproute.c L1936–1947](https://github.com/iproute2/iproute2/blob/v4.15.0/ip/iproute.c#L1936-L1947)，`add`使用`NLM_F_CREATE|NLM_F_EXCL`，`replace`才用REPLACE。**有条件推断**：若本轮del成功且首次命中网关有效、路由插入成功，后续同table/目的/优先级的add通常因已存在失败，实际保留第一次成功项，日志却可能出现多项。若前项网关无效则可能由后项首次成功；若del失败或全部add失败，结果另当别论。本次没有在作者Ubuntu镜像/内核中执行命令，不能称已测得具体路由表。E1/E2应将单次选择、命令成功与日志一致性分别验证，并记录最小修复。

### C. 流索引被压缩

ROS消息自身包含`node,src,dest`（[PRTableEntry.msg L1–12](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/routing_msgs/msg/PRTableEntry.msg#L1-L12)）；SOCP保留K维；但main_srv L115–118只存`[node][src]`，所以同节点、同源不同目的会后写覆盖。问题发生在分发转换层，不能笼统说SOCP不支持多流。单源单目的/不同源流未因此冲突；同源多目的必须保留完整流身份或显式拒绝，并作为适配差异验证。

### D. 方差、标准差和附录系数

论文p3式(2)称`R̃=a·d/(b+d)`为方差；p4式(5)用它累加流方差。候选源码 [channel_model.py L49–55、L70–74](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/socp/src/socp/channel_model.py#L49-L74) 返回`var=(a·d/(b+d))²`，所以代码中未平方的量实际承担标准差含义。SOCP [rr_socp.py L116–148](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/socp/src/socp/rr_socp.py#L116-L148) 取`sqrt(rate_var)`，并 [L50–65](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/socp/src/socp/rr_socp.py#L50-L65) 用`norm(diag(std)·α) <= (mean-m-s)/Φ⁻¹(ε)`；在ε>.5时对应正文(9)的结构，但输入方差数值不同。

论文p15 Algorithm2直接把R̃放进c，并写`C=diag(c)/Φ⁻¹(ε)`；这与正文(16)–(17)所需的`Φ⁻¹(ε)·diag(sqrt(R̃))`不同。已视觉核原页，不能当OCR错误略过。另p4/p15公式写“∀i,k”，而源码明确跳过目的节点：rr_socp L123–124。流守恒中目的为吸收节点；若所有节点均要求非负净流且s>0，会有求和矛盾。适配以哪套约束/方差为准必须在冻结记录写明，不能拼出“论文和代码完全一致”。

### E. 默认值、入口及工程完整性

`PathLossModel.__init__`默认b=6.0（channel_model L22），`RRSOCPServer`可读ROS参数覆盖（rr_socp_server L13–24）。`intel_aero_experiments/launch/net_patrol.launch` L30–33是task `[1,2,5]`、network `[10,11]`；L45–49显式`N0=-70,n=2.52,L0=-48,a=.2,b=.6`，L21最小更新率2Hz。不能用类默认值宣称原实机用了b=6，也不能把这个五节点入口称论文六节点巡逻。

另有六节点候选 [3t3n_circle.launch L9–18](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/intel_aero_demos/launch/3t3n_circle.launch#L9-L18)；其yaml为task `[1,2,3]`、network `[4,5,6]`、L0=-48、b=.6，每源多目的（[配置L1–26](https://github.com/danmox/miod/blob/d4ba825cb2068301f7811e522c4cc44092796e1e/intel_aero_demos/config/3t3n_circle_patrol.yaml#L1-L26)）。然而该yaml用`qos/margin/confidence`结构，入口`intel_aero_demos/scripts/network_planner_node` L15–24读`/comm_reqs`和`rate/qos`；Python planner L48还要求step_size。Python planner L5导入`ChannelModel`，该提交channel_model.py没有同名定义/别名；rr_socp_server则正确显式别名PathLossModel。net_patrol.launch L71–85引用`network_planner_net_patrol_node`，同包CMake只声明outdoor_test/outdoor_action_test，解包树未找到该命名入口。这些是静态阻断证据，尚未做构建测试。已有3t3n配置也不足以确认完整可运行，更不足以证明TRO24实机使用它。

### F. 节点退出、加入与失联

已查范围：miod planner、intel_aero_experiments、intel_aero_demos的入口/配置及routing脚本。Python planner在构造时固定agent_ids，仅等待所有位置各到达一次（L85–121、L215–217），之后继续使用所存位置；没有在该路径看到基于新鲜度删节点。客户端2000ms邻居inactive筛选属于无线状态统计；不能代替Planner成员变更。退出/加入机制仍未定位到与Fig.14对应的可运行入口。最小后续是取得实验版本说明或由M明确成员/位置输入变化方式，再单独记录“本项目适配”；不发邮件、不无限检索。

### G. availability轴与历史CVXPY

miod rr_socp.py L56–60，以及mid robust_routing/src/robust_routing/socp.py L37–41，将K维先加总为二维`N×N`，却调用`cp.sum(matrix,2)`和`cp.sum(matrix,1)`。E1-016检查点1已保存CVXPY1.7.4下axis2越界的失败；D未复跑。论文p4集合A要求每接收节点`Σ(i,k)α_ij^k<=1`、每发送节点`Σ(j,k)α_ij^k<=1`，所以**正文对应的二维实现应分别求axis=0列和axis=1行的和**，再逐项约束<=1。E1独立实现该两轴有正文依据，应记录为纠正候选实现缺陷，不能写成原源码原样运行通过。

本次还查看[CVXPY v1.0.31 AxisAtom源码](https://github.com/cvxpy/cvxpy/blob/v1.0.31/cvxpy/atoms/axis_atom.py)：其早期axis校验与当前不同，不能仅凭现代异常反推作者环境当年一定出现同一异常；历史sum图生成及实际依赖版本未完整核验，是否静默产生另一种约束仍未知。无须据此阻塞正文两轴的显式适配，原始版本一致性保留未验证。

## 5. 较新 mid 模块的使用边界

[robust_routing/scripts/robust_routing_socp.py](https://github.com/danmox/mid/blob/653f5b35a8e54402ef70f50c152292a0d830260b/robust_routing/scripts/robust_routing_socp.py#L24-L31)输入RateGraph，输出RobustRoutes，通信需求经service设置；不再直接沿用旧`network_update`链。L68–89会把非正边方差改成1（原注释称bps，量纲仍需审查）；L109–137跳过接收端、过滤phantom relays并按每relay归一化gateway权重。

[robust_routing/src/robust_routing/socp.py L84–125](https://github.com/danmox/mid/blob/653f5b35a8e54402ef70f50c152292a0d830260b/robust_routing/src/robust_routing/socp.py#L84-L125)禁止流回源、跳过目的约束并取方差平方根；[connectivity_planner/channel_model.py L23–57](https://github.com/danmox/mid/blob/653f5b35a8e54402ef70f50c152292a0d830260b/connectivity_planner/src/connectivity_planner/channel_model.py#L23-L57)仍把sigmoid平方作为方差，默认b=6。新模块可以作公式实现交叉参照；不能把其中RateGraph、opportunistic routing等模块与旧UDP/Linux路径混成一个已证实的TRO24系统。本轮未运行该工程。

## 6. 已冻结与未决

已冻结：本地论文hash；两作者候选提交/归档hash；旧配置多跳转播确实存在；0.5s执行器与1s广播不同；累计抽样/缺break/返回码忽略；同源多目的覆盖；方差和附录差异；默认与明确入口值；候选入口不完整；三组仿真与三组实机的节点数和测量边界。

未决：TRO24最终实验commit/分支、完整launch和原始日志；出版商PDF与本地版对应；实机各场地模型与需求参数；退出/加入控制机制；作者环境中route命令实际结果；模块级可再分发许可。查过的来源就是本地全文、两个固定源树、其README/package.xml/API及论文提交页；没有足够证据的项保留未知。它们不阻塞对已确定SOCP与转播逻辑作显式适配，但限制“原实验复现”表述。

工程操作页另见 [REPRODUCTION_PLAN.md](REPRODUCTION_PLAN.md) 与 [USER_GUIDE.md](USER_GUIDE.md)。来源检查点先交审；真实命令须等E1/H冻结后补齐，不据候选作者入口编写可执行的五板命令。
