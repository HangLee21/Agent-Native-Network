# 五板当前实际结果

2026-11-07：120条端点消息/20条完整四跳链及五板中继角色覆盖已由E2独立核对，见[FIVE_REAL_RESULTS.md](FIVE_REAL_RESULTS.md)。下面三板/准备阶段保持历史，不覆盖或混合统计样本。

# 当前实际结果

2026-11-06：H四次真实RF日志已由E2独立核24条端点消息与6条完整受控两跳链，payload一致。详见[REAL_RESULTS.md](REAL_RESULTS.md)。下列各检查点是执行前历史，不再以“无实测”描述当前总进度。尚未验证的完整OLED像素/PRG、RTT和PHY指标仍未知。

# E2-016独立验证与当前native交接

当前检查点3：正式包52件核验、实际native host4项和最终原生物化/审计4项通过；AB及ABC具体命令由H新info物化，见NATIVE_AB_HANDOFF。尚无E2实板/RF结果。下文准备阶段保留为历史。

2026-11-06。已完成独立验收计划、六组禁用台架草案、归一化事件提案、可运行只读分析API和候选作者代码探针。最终13项检查通过，失败/错误/跳过0；不是适配固件、目标构建、OLED实物或无线验收。这段是准备阶段历史；当前已消费H显示/D来源冻结并核E1检查点固定核心，更新见文末阶段2。

- [验收计划](VALIDATION_PLAN.md)：目的约束/方差/入口参数、周期抽样、控制去重、源目的范围、OLED来源和显示影响的接受标准。
- [场景草案](SCENARIOS.json)：最多6次，与H剩余预算取较小值；enabled=false、MAC绑定/信道/输入freeze未填，不可直接执行。全20对只是能力检查，不是原论文场景复现。
- [事件提案](EVENT_CONTRACT.md)及RESULT_SCHEMA.json：明确只接受分析侧归一化事件，E1/H真实日志适配器待冻结后做，不把提案当生产者已有字段。
- 分析入口tools/mid_baseline/validation/analyze.py：analyze_files只读函数；CLI只写E2-016新文件，未调用共享ANN分析器。PDR/goodput按每流身份、计划计数、两端覆盖和实际窗口门控；RTT无baseline回执保持null，RF retries/airtime不推断；OLED精确引用本机事件而不以CMD/MAC回调冒称交付。
- [候选作者核对](AUTHOR_FINDINGS.md)：七份指定提交原字节留.local，hash与URL见其SOURCES.json；只提取指定函数AST，用fake OS/socket/ROS子进程检查实际控制流。没有执行作者顶层main、ip route、UDP、ROS或CVXPY。

## 实际检查

第01轮10项通过；加入20对分析身份隔离、硬件错误来源和严格JSON等回归后，第02轮13项通过，不合并样本数。第02轮测试与原始作者探针观察在[运行目录](../../simulation/outputs/E2-016/20261106-02-preparation-regression/)。每轮使用新RUN_MANIFEST、入口/合同/卡/源码快照；失败和旧记录不改。

作者探针核实：0.5/0.5权重、coin=0.25触发g1/g2两次添加尝试，coin=0.75只尝试g2；fake命令返回2不被处理。实际Linux哪个路由生效未测。node/src转换将d1覆盖为d2；不同中继重复控制输入4/4/3/5只转播原源4/5。它们是候选作者行为，不是为适配实现写镜像测试；修复/格式扩展应由E1披露。

静态定位rr_socp目的节点continue、方差sqrt、PathLossModel默认b=6.0与launch显式0.6及Planner参数传递。论文全文/附录差异、TRO版本对应、实际求解/数值残差、ESP-NOW native接口、H显示渲染和实际台架均未验证。13项中的OLED检查是提案级语义检查，不能替代冻结H模块和用户屏幕确认。

## 交接与限制

E1：请提供冻结INTERFACE/FREEZE、Planner样例和实际native日志，明确作者缺break/错误处理、node/src覆盖的必要修复和范围；参数覆盖链与500ms周期实际执行要可追溯。H：提供冻结显示快照/事件映射及真实采集合同；按来源重建端点RX和覆盖，不通过新增ACK让MID源显示送达。D：确认七文件候选提交与TRO实验版/许可的关系；本报告已分开静态源码、探针和未核论文。C/M：当前只交准备阶段，不自行done或认定固件/硬件通过。

首次网页取件cache miss、沙盒直连WinError10013，随后受审查的公共只读取件成功；该取件没有执行作者代码。基准b7f16ea94c1f4e07045784d06f87362ebc3e84c3，保留所有其他角色dirty/untracked，无Git写/子代理/跨聊天发送/物理串口/刷写/训练/规模仿真/定时任务。准备阶段前两轮测试累计约0.844秒/1200秒（当前累计见阶段2）、每命令≤120秒，CPU1；准备在60分钟内。当前所有命令结束、无串口与后台进程。后续需要E1/H冻结输入再由M协调交接，本窗口不后台等待。

## 阶段2：固定显示独立检查与A/B准备

按M-018-stage2继续原任务，不重置预算。H显示freeze锚点2d72ee784757d881a6b77108bf886e5e6e0591934c94693d5baee0330e4da9aa，27件逐hash一致并复制到03输出；D检查点四份固定副本逐hash一致，已消费SOURCE_AUDIT，未把D读论文写成本窗口亲自核原页。

| 独立运行 | 结果 | 能支持与不能支持的范围 |
|---|---|---|
| 02 preparation-regression | 13项，失败/错误/跳过0 | 准备工具与作者AST，不重跑 |
| 03 H-display-independent | 5项，失败/错误/跳过0 | 实际H固定C模型/renderer/IDF backend在host fake平台编译运行；四个模型场景及五个故障子例，无ESP目标对象/链接/实物像素结论 |
| 04 candidate-core-independent | 4项，失败/错误/跳过0 | E1检查点1 mid.c/mid.h原hash实际C99编译运行；当前INTERFACE变更，不读活动文档，非最终native/无线集成 |

03独立驱动没有执行H作者测试：CMD OK不改变TX，MID链路成功仍UNCONFIRMED，错误的ANN确认拒绝，目的/中继/重复RX分列；旧回调只影响计数/故障，不覆盖新事务，ANN已确认不会被晚链路结果降级；不匹配目的、倒退时刻拒绝。零值存在位、未知下一跳/配置源、错误标记与计数饱和均核对。渲染12页调用没有改写快照，1024byte帧前后guard保持。该检查只证明渲染纯函数不改协议输入，未证明真实渲染时延或并发调度无影响。

03后端独立fake分别制造队列分配失败、task创建失败、两OLED地址probe失败、首帧失败、首帧成功后失败。publish本身没有I2C/GPIO，50ms事务上限保留，READY只在首帧后，故障不关闭共享电源，活跃publisher队列不删除，FAILED后不自动重启。它是实际backend调用fake声明/API的控制路径证据，不是FreeRTOS真实调度或电气故障测量。

04只消费原FREEZE d99ef0bd18d2e80fb8fad1050139e749fe8cf800dda4f02753dfcb530edbce41中两个仍匹配的核心文件。20有向端点组合、同源双目的（使用源全局不同seq）、u16权重16383/16384边界与499/500ms保持、控制4/4/3/5、publisher boot拒绝和frame长度/保留字节均通过。没有运行真实控制转播适配器、Planner求解、native串口或RF。候选核心有界去重/协议限制以E1说明为准，不扩展声称无限exactly-once。

D来源支持M阶段2明确取舍：按候选代码目的约束跳过/sqrt(var)，availability用正文两轴，累计周期抽样首次命中和全(src,dst)键是披露的修复；不把它说成原文Bernoulli精确等价。TRO最终实验commit/许可、Linux实际路由结果仍未知，不阻塞明确的工程适配。

A/B交接见[AB_HANDOFF.md](AB_HANDOFF.md)、[小包语义计划](AB_SMALL_PACKET_PLAN.json)与[SOCP输入](AB_SOCP_INPUT.json)：真实标签来源留hash，仅双向各5包、至多24秒一次run，无新增ACK/强制跳数，C–E后置。SOCP是显式假设的无量纲模型，不是无线标定；E1必须实际求解并保存结果/hash。当前未取得最终包/native解析合同/C设备就绪结论，enabled=false且native_commands=null；正式包后只补相关核验与可执行配置，不等待五板。H每次重核物理身份，E2不接触串口。

03/04 result、manifest、编译命令、原字节快照、binary hash和独立驱动均在对应新run，四轮索引与旧manifest原字节保持。测试累计约10.907/1200秒，单命令≤120秒、CPU1；准备/实现沿原60分钟，不重置，未启动规模仿真/训练。所有命令已结束，串口0/RF0、无后台等待。当前交checkpoint2 review；按阶段2向E1/C/H一次定向通知可消费hash及缺最终包，不仅落卡。

勘误：准备阶段主卡RESULT_SCHEMA文件名曾因文本占位符替换误带result hash，现纠正为RESULT_SCHEMA.json；旧运行/冻结原字节保留，不改测试结论。

## 检查点3：正式包native核验与AB/ABC实际配置

正式package-01 manifest d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683的52件长度/hash全部核对；正式E1 freeze95e7499f8e5c1469af4a36b29b52e5522a44bf9e19a17497df559dd58d686f40的13份源码一致，H6生产文件未改，AB实际solution/update hash一致。只读消费E1目标构建/镜像校验证据，E2没有重跑ESP目标构建，也没有把包核验当设备验收。

05保存唯一新失败：E2假SDK头遗漏stdbool.h，使host编译失败、0测试/1 setup error；修正E2头后06实际app_main/cJSON/core/H模型host互验4项通过。未改固件、未关严格警告。实际source编码五份帧输入实际destination回调/主循环后五个rx_local，B可源发，命令重复键/未启动拒绝，缺回调锁定至复位；全部SDK/RTOS/无线/display publish为fake，不是RF。原始stdout/真实包源码/cJSON hash/编译命令全部保留。

07/08工具3项通过；ABC实际资产到位后09最终4项通过。native.py materialize校验正式包和实际绑定解，以H新info的A boot构造真实命令，AB各5包；ABC AC/BC各2包、受控AC各3包，每case最多两流、不同控制seq段。不是部署boot1样例。native audit直接读mid.serial.v1并保存源行号，不依赖旧归一化提案：tx_queued仅源接纳、tx_link_ok只是MAC回调、rx_local才目的观察。硬件PDR/goodput需同包/run的H不可变hash context、明确coverage/实际时窗、两端base/final stats计数及stop/boot/build一致；host stdout缺context时数值保持null，RTT/PHY费用未知。控制只报API提交次数，缺长度不猜字节。

H ABC库存/标签已按固定hash消费，E1真实三节点INDEX 37d879827f6e50bd940737dccdee6ca82a79d410b4ac2957a06dc39826ff1f57及各case资产逐hash核对；controlled链四条路由独立匹配A-B-C/C-B-A。原SOCP求解由E1实际完成，E2没有重解或把假设mean/variance说成标定。工具对原生转发证据按origin/origin_boot/seq/dst同时核源、B中继接收/提交及目的唯一RX；没有真实日志时不宣称多跳通过。

具体可执行入口/命令序列/采集context/AB先行与ABC顺序见[NATIVE_AB_HANDOFF.md](NATIVE_AB_HANDOFF.md)，代码tools/mid_baseline/validation/native.py。C需补审具体增量给就绪结论，H按自己剩余预算和备份/身份执行；E2配置通知本身不是刷机放行。H旧AB库存hash没有改写。ABC_INCREMENTAL_ORDER是早期等待资产的历史草案，当前以本native入口/上述固定INDEX为准。

当前10轮受控测试累计21.189/1200秒（仍低于原20分钟；ABC新增5分钟未据此重置），新增准备按M-018-ABC的15分钟范围，不扩展算法或功能。旧13/5/4与本轮4native/4tool各组分列，不相加样本。进程全退出、物理串口0/Flash0/RF0，无后台等待或轮询。按授权一次交C/H/D与E1，等待实测证据后验收，不自行done。

最终10轮对ABC所有参与者的coverage/base-final stats/stop状态统一门控后，4项工具回归通过，失败/错误/跳过0；未改E1/H或扩展RF预算。
