# M-037：MANET/FANET 原文到实现映射

2026-11-14，D-032，供 E1/E2 实现和 C 审查。目标为 30 节点移动自组网；适配 ESP-NOW 的可移植实现不等于原 IP 线协议互通。本文件是来源与设计映射，不报告新协议实验。原始资料、代码许可和证据的可取得状态逐项标明；任何缺少对应机制的实现均标子集。

## 优先可实现的比较

1. 统一环境先提供 `tick(now)`、接收帧、发送完成、提交业务和弹出有界帧/事件；E1 的 [唯一接口合同](../simulation/manet_core/CONTRACT.md)以其最终版本为准，本文件不代写合同。传入仅本节点信息及实际收到的帧；环境真图只用于传播和结果评价。路由、peer、队列满/过期都必须回传可归因原因。
2. 同载荷、相同到达、链路模型、peer/内存上限、随机种子与端点确认规则，分别跑原源路由、AODV 逐跳、OLSR hop、OLSR ETX、P-OLSR；逐项先做可解释的小规模协议语义场景，再按合同扩大。先保留原算法特征，不把 MPR 加在源路由上称完整 OLSR。
3. 每种算法调 `HELLO`/持有期/发现超时/跳限与队列都公开扫描范围及选择规则。原论文参数是对照起点，不是当前 ESP-NOW 最优值；同一目标期限、offered 负载和公平资源下报告所有源包、同身份唯一端点交付、deadline、P95/P99、失败、分区、控制及 MAC airtime、队列/peer 拒绝。可达条件分母和持续窗口单列。不要用增加等待/缓存或减少 offered 替代改进。

## AODV：按需、逐跳、目的序列号

来源：[Perkins/Royer 1999 原论文全文](https://www.eecs.ucf.edu/~turgut/COURSES/ClassReviewPapers/Perkins99_AODV.pdf) §2–3；[RFC 3561](https://datatracker.ietf.org/doc/html/rfc3561) §5–10，Experimental。1999 论文与 2003 RFC 不是完全相同版本；以 RFC 字段/状态为规范目标时应标 RFC 适配。1999 原文实验包括 50/100 节点模拟，曾指出仅对成功发现的时延统计会漏掉失败，不能把论文结果当当前板端性能。没有取得该论文作者实现及许可证；不能假设第三方仓库是原始代码。

**最小状态**：节点序列号、RREQ ID；每目的路由（下一跳、跳数、目的 seq 及 valid 标志、有效/失效、到期、前驱集合）；(origin,RREQ ID) 去重及有效期；有界业务等待；邻居失效记录。适配增加 boot epoch，明确定义重启旧报文与 sequence 的关系，不能重启后直接把 seq=0 当更新。严格实现 RFC §6.1 的 32 位序列号串行比较及未知 seq 标志；相差半个序列空间的歧义应定义处理并测环路。前驱集合是 RERR 的实际通知对象，不能省略后仍称完整。

**操作映射**：无路由时源增加 request ID、产生 RREQ(origin, origin seq, request id, dst, dst seq/unknown, hop/TTL)；节点依据源序列号/跳数建立反向路由并按来源与 ID 去重，再按 TTL、限速转发。目的端或满足 RFC 新鲜度及标志条件的中继产生 RREP，沿反向下一跳单播；每跳按目的 seq 更大、或 seq 相等且更短等 RFC 条件更新前向路由。数据包逐跳查 next-hop，**不携带完整源路径**。链路失败使受影响路由无效、更新序号并对前驱发 RERR；local repair、gratuitous RREP、HELLO 均按是否实现与控制帧付费单列，缺失则明确子集。ACK 回调只代表本跳；端点 delivery 另计。

RFC §10 起始参数：ACTIVE_ROUTE_TIMEOUT 3000 ms、HELLO 1000 ms、ALLOWED_HELLO_LOSS 2、NODE_TRAVERSAL_TIME 40 ms、NET_DIAMETER 35、RREQ_RETRIES 2、RREQ_RATELIMIT/RERR_RATELIMIT 各 10/s，扩环 TTL_START 1、INCREMENT 2、THRESHOLD 7。若启用 HELLO，RFC 注明 TTL_START 至少设 2；均非对该硬件或 1 秒业务期限的保证。TTL 上限及扩环等待/失败应单独分解。

验证顺序：链 A-B-C 的 reverse/forward 建立和中继转发；重复 RREQ 和旧 seq 不覆盖新路由；seq 回绕、boot 更新、RREP 丢失与重复；断 B-C 后 RERR/前驱和过期；出站满、peer 满、分区合并；可配置 8/16/32 跳限及明确数据负载上限。所有 RREQ、HELLO、RREP、RERR、MAC 重试及端点 ACK 单独记帧长/airtime。

## OLSR：HELLO、两跳、MPR 与 TC

来源：[RFC 3626 全文](https://datatracker.ietf.org/doc/html/rfc3626) §4–12、§18，Experimental；[INRIA 作者协议规格全文](https://inria.hal.science/inria-00471712v1/document)。Jacquet 等 2001 INMIC 原论文已定位为 DOI 10.1109/INMIC.2001.995315，对应 INRIA `inria-00471622` 文件本次未能打开，**未将其列为完整已读**。RFC 协议而非该原论文的实验结果是本节实现依据。[olsrd 主仓](https://github.com/OLSR/olsrd)是现有 OLSR 实现入口，尚未核到 Rosati 论文特定版本和许可证，不能直接把当前仓内容认成作者 P-OLSR 代码。

HELLO 为一跳消息，携带链路/邻居状态与被选 MPR；节点维护对称一跳邻居、从 HELLO 获得的严格两跳集合、willingness、MPR set 与 MPR selector set。MPR 的目标是通过所选对称一跳节点覆盖已知严格两跳邻居；依 RFC §8.3 处理 WILL_ALWAYS、独占可达两跳项与贪心选择，缺失时标简化算法。HELLO 本身不转发。

TC 周期公布 MPR selector 等拓扑，消息带 originator、message sequence、TTL、hop、有效期和 ANSN；只经符合规则的 MPR 选择者方向泛洪，duplicate set 防重复/控制重发，拓扑组按 ANSN 和 hold time 淘汰；基于本地可用一跳、二跳与 TC 图重算逐跳路由。邻居/selector/拓扑老化、TC 选择/转发、重算必须存在才能称 OLSR 子集基线。非对称链路不能直接拿来当对称边；不从环境真图填两跳或 TC。首次启动与丢 HELLO 时可以无路由。

RFC 建议 HELLO_INTERVAL=2 s、TC_INTERVAL=5 s、NEIGHB_HOLD_TIME=3×HELLO、TOP_HOLD_TIME=3×TC、MPR_COVERAGE=1、TC_REDUNDANCY=0、MAXJITTER=HELLO/4；具体配置、碰撞和包分片均应落事件。单接口、不实现 MID/HNA 等可作为明确声明的子集。对于双向确认邻居超过 SDK 20 peer 的情况，MPR 并不自动解决真实单播 peer 管理。

## ETX：双方向接收率与探针费用

[De Couto 等 MobiCom 2003 原文](https://courses.csail.mit.edu/6.885/spring06/papers/DecoutoABM.pdf) §3、§4：每链路 ETX=1/(d_f·d_r)，路径代价为各链路求和；任一比率为 0 或未知时不得产生可用的有限代价。原作者实现每节点以均值 1 s、±10% jitter 广播探针，统计最近 10 s 到达数 / 预计数；每个探针携带各邻居的接收计数以使对端计算另一方向。论文 §4 的探针是 134 B 802.11b payload；广播不由该 MAC 确认/重传。它的实验是 29 台静止 Linux/802.11b 台架，不是 UAV 实飞或 ESP-NOW。本任务应付费广播探针（或明确以 HELLO 复用并计额外字段），真实单播 retry/ACK 机制与探针大小偏差另做敏感性；ETX 值非端点交付概率。

该原论文实现比较 DSDV/DSR 的 ETX，并非 RFC 3626 自带 ETX。采用 OLSRd 的 HELLO LQ 扩展、指数平均，属于另一实现口径，不可默认为 De Couto 原本的滑动窗口；应提供 hop、滑窗 ETX、LQ EWMA 的配置与对照标签。作者 [MIT Grid 项目论文入口](https://pdos.csail.mit.edu/archive/grid/pubs.html) 可定位论文；具体可用代码版本和许可证本次未验证，不直接复制。

## P-OLSR：相对径向速度加权 ETX

Rosati 等发表版为 IEEE Transactions on Vehicular Technology 65(3), 1690–1700 (2016), DOI [10.1109/TVT.2015.2414819](https://doi.org/10.1109/TVT.2015.2414819)。本次实际读取 [作者公开稿全文](https://arxiv.org/html/1406.4399) §II–VI；**未获取出版排版全文**，不能声称已逐字比对两个版本。文中称 fork OLSRd，论文 [19] 指向 `http://smavnet.epfl.ch`；本次该网站不可访问，作者特定源代码、提交及许可证均未核实。现行 OLSRd 仓不等于已取得作者 fork。

按照作者稿公式 (2)、(4)–(6)：每次预期 HELLO 得 h∈{0,1}，`phi_l = alpha*h_l + (1-alpha)*phi_(l-1)`，双向质量来自本地和对方携带的统计；仅在收到的两次 HELLO 上，以对应本地接收时刻与位置计算距离差分 `v_tilde=(d_l-d_(l-1))/(t_l-t_(l-1))`，再 `v_l=gamma*v_tilde+(1-gamma)*v_(l-1)`；链路代价 `exp(beta*v_l)/(phi*rho)`，路径求和。靠近为负，远离为正。实际得失需要把坐标测量时间/坐标失真、消息延迟、丢包和过期/重启可见化；不能读取未来轨迹。极端值、零分母、近零时间、重启、数值饱和要明确处理，任何截断都记为适配。

**原文内部矛盾**：按公式 α 越大，当前 h 权重越大、响应越快；§II-A 文字却说大 α 平均更久、低 α 更快。γ 的公式同样赋新速度 γ 权重。不能把这段话悄悄改为“已确认作者代码”。实验应分别保存参数定义，按公式实现并对 α=0/1 阶跃进行测试；再把相反记号 `alpha_old=1-alpha_new` 列为参数约定敏感性，待找回作者版本核对。原文位置与速度扩展通过 HELLO/TC 传播，不是零成本全局数据。§III 称 HELLO 头由 8 增至 16 B、每邻居块保留 8 B（其中两个保留字节承载速度），TC 的改变另按实际实现和帧编码逐字节计算；其 IPv4/802.11 包布局不能直接搬到 MAC 6 字节的 ESP-NOW。

文中固定翼平台约 12 m/s，实际飞行实验和 19 节点 MAC 模拟分开；论文的 α/β/γ 和其射频模型不能当本板的最优参数或实测结果。P-OLSR 成本权重允许小于 1；如果用不适用于该权重的启发式或截断，需证明求路正确且标偏差。

## 广播风暴：避免把抑制当成无代价

已读取 [Ni/Tseng/Chen/Sheu MobiCom 1999 作者机构全文](https://people.cs.nycu.edu.tw/~yctseng/papers.pub/mobile6-storm-mobicom99.pdf) §2–4 与 [Tseng 等 Wireless Networks 2002 作者机构存档](https://ir.lib.nycu.edu.tw/bitstream/11536/29078/1/000174218000005.pdf) §2–4；两个版本分别引用，不当作同一发表物。原文讨论冗余转发、竞争和碰撞，设同一消息可按源/序号去重。

- 概率法：首次接收后按 p 决定是否重播；必须保留 p=1 的泛洪对照，p 降低可能降低可达性。
- 计数法：首次接收初始化计数，在随机延迟以及等待实际发射期间观察相同消息，每收到一次更新；达到阈值 C 则取消尚未发射的重播。需要取消已排队而未开始发射的机制、消息 ID、有限计数与超时；不能以仿真器知道全网已覆盖来抑制。原论文给 C=3 或 4 的建议仅针对其环境，不是本系统默认最优。
- 距离法维护此前同一消息发射者的最小距离，低于 D 时抑制；位置法计算额外覆盖面积低于阈值时抑制；这些方法假定获得位置/距离，必须显式包含测量误差、携带开销以及未知信息时策略，不能读取真图。簇方法还需要构簇和网关维护成本。

论文报告 10,000 次广播请求的仿真，结果受密度与阈值影响；不要把论文节约比例迁移为此 30 节点结果。诊断应逐消息记录首次接收、重复、转发、排队取消、碰撞、接收覆盖及断连分母，并测试隐藏终端、稀疏割点、非对称和同步突发；计数多并不必然意味着足够覆盖，误抑制需要可见。

## 资源、帧与可审查的增量机会

按 [目标预算](UAV_RESOURCE_BUDGET.md)：ND 表32、SDK peer总上限20，历史 2267bc60 目标 `router` 27,144 B、`agent` 28,144 B 是该版整个静态对象，不代表新协议增量或当前可用 RAM。30 个节点、29 个对端的邻居行：仅示例编码中 MAC6 + 状态1 + 有效期2 = 9 B/行，29 行已 261 B，尚未含头部、位置、质量、序列号或校验；因此必须按 E1 实际 PHY/协议 MTU 检查，并明确是否截断、有界分片及重组丢失/过期，不可悄然丢邻居还宣称完整 MPR 覆盖。总队列和所有分片都计内存及实际发射字节。30×30 的 32 位行位图占 120 B 仅作邻接**位**示例，不包含拓扑年龄、序列、代价、身份映射/对齐及队列开销；节点映射必须通过真实控制消息学习，真图不可直接注入。

实现资源报告包括目标 ABI sizeof/静态对象、各表容量/满表拒绝、PSRAM=0 假设、目标 Flash 与运行期堆/栈水位、每事件最坏扫描与耗时；不能用 host Python 大小或 wall time 冒充板测。ETX 探针的单播与广播质量差异、位置信息时间偏差、协议选择器的不完整邻居覆盖都是候选机制可研究的限制；本地拥塞或信息年龄触发更新、受限 peer 的替换策略可在同一基线下逐项消融，必须付信息/计算成本并检查稳定性。MPR、ETX 或现有广播阈值本身不是新算法。成熟协议若在工程约束中足够有效，可直接采用。

当前审计边界：M-036 的 512 项已有期限自检，另 30 项未做该项审计；三次 6 h 是同一 crossing/50 m/s/compact 的不同种子，不能称跨场景覆盖。原始结果保持不改。本说明没有运行新测试或实机，E1/E2 的实现是否符合上述条件仍待独立审查。
