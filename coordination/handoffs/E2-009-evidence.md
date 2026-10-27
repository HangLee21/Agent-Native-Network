# E2-009 前期实验数字与证据口径核对

2026-10-27，Asia/Shanghai。实际执行窗口：E2 | Validation & Ablation；聊天ID `01a16824-3f4e-7e61-8a83-08d2dd8c82f6`。本证据表供D-008编制详细报告，C-011独立审查，M验收。

## 1. 本轮核对结论与边界

已从归档的小型CSV、summary、选定manifest核对下列数字；本轮新实验0、测试0、研究脚本运行0。主要数值与现有报告相符，尚无改变主要结论的数据矛盾。机器可读结果见同目录 [E2-009-evidence.json](E2-009-evidence.json)，保留未四舍五入数据、分组、单位、来源ID和逐文件SHA-256。

本轮“实算”只指读取保存记录后重新计数、求和、均值或比值；“保存标记”是检查文件中历史passed/success字段；“报告引用”未进一步检查原始事件。它们均不表示本窗口重演实验或重新证明源码行为。未重做全量账本、权重验证、环境验证或外部文献核验。M-002至M-009原执行来自M聊天子代理，不能写为本独立E2窗口完成的历史实验。

实测工作目录 `D:\Multi-Agent Network`；分支 `codex/baseline-reproduction-20261023`，HEAD `514382a5ac68c613f219899f1cd6a34cecf42b45`。接手时START_HERE、CURRENT、DECISIONS、TASKS、WINDOWS存在M管理修改，C-011/D-008/E2-009/M-010主卡未跟踪；全部保留。主卡“开始时干净”是M建卡基准快照，不是本窗口接手时状态。

## 2. 计数总表：不同证据不能相加成独立样本

| 阶段 | 保存数量及分母 | 本轮核对方式 | 报告可采用的含义 |
|---|---|---|---|
| 原入口评估 | 10配对目录×2策略=20次；15/20任务各5种子 | 配对CSV与summary均值核对 | 原权重和作者Greedy的小实例实现对照 |
| S1影子接口 | 10原轨迹；每档384决策机会；3延迟档 | summary字段及manifest读取 | 信息接口等价/敏感性，不新增网络任务回合 |
| MOCHA/AutoCast | 14组件探针；另一次成功MOCHA运行18项检查 | 逐项保存passed标记计数 | 组件/隔离协议路径可运行，不是32次系统性能实验 |
| 因果阶段 | 58任务回合=45主比较+1pilot+10等待诊断+2极小延迟；另6固定回放 | 5份任务summary及服务summary重计 | 全部58中45成功、13到H未完成；主45中35成功、10到H未完成 |
| 需求账本 | 复算上述45主回合；原生部分10目录/175任务，其余35配对诊断 | summary、逐任务CSV核对 | 分析复用，不新增45个任务样本 |
| 008执行 | 30=10旧条件回归+10共同恢复+10规模闭环 | 30行CSV分组 | 28成功、2到H未完成；规模仅两任务种子 |
| 009无线 | 60固定回放；18闭环=6目录×3规则 | 回放60行及任务18行CSV核对 | 回放MACseed0/1/2；闭环仅MACseed0，不是78个独立任务样本 |

## 3. HeteroMRTA原评估

来源：[S01](#s01)、[S02](#s02)、[S03](#s03)、[S04](#s04)、[S05](#s05)、[S06](#s06)；入口语义限制见[S31](#s31)。每格成功要求全部任务完成并返回驻地；时间仍是原模型单位。

| 机器人/任务 | 策略成功/尝试 | Greedy成功/尝试 | 策略返回时间均值 | Greedy均值 | 策略更快配对数 | 均值比降幅 |
|---|---|---|---|---|---|---|
| 9/15 | 5/5 | 5/5 | 21.408737 | 24.030662 | 4/5 | 10.9107% |
| 9/20 | 5/5 | 5/5 | 25.900583 | 32.299929 | 5/5 | 19.8123% |

降幅=1−策略均值/Greedy均值，并非逐实例百分比的均值。两个策略同一seed重新生成配对任务；5维能力接口、9机器人、种子0–4。使用作者生成器而非论文测试集，因此不是论文表格复现。作者Greedy距离更新问题及mask/调度规则差异保留；不能据10.91%/19.81%声称战胜标准最近邻算法。单行corrected_nearest失败属于额外诊断，未计入20次正常评估。

## 4. S1影子：384机会与138/215

来源：[S07](#s07)、[S08](#s08)；具体实验语义见[S32](#s32)。10/10原回合完成，零延迟10/10等价。

| 远端延迟（模型单位） | 机会数 | 观测不同 | mask不同 | 分支不同 | 动作/跳过不同 |
|---|---|---|---|---|---|
| 0.0 | 384 | 0 | 0 | 0 | 0 |
| 0.5 | 384 | 298 | 136 | 13 | 138 |
| 2.0 | 384 | 370 | 230 | 20 | 215 |

138/384=35.9375%，215/384≈55.9896%，只是同10条固定轨迹内机会级描述。包含推理与跳过分支变化，不是错误率。正延迟影子动作未反写环境，不能赋予新的完成率、makespan或网络收益。原报告另记373条实际命令、88636应用字节及7条回溯出发命令；本轮这三项仅引用[S32](#s32)，未逐条重算。

## 5. MOCHA/AutoCast组件与最小协议

来源：[S09](#s09)、[S10](#s10)；范围及适配器见[S33](#s33)、[S34](#s34)。保存文件中14/14组件检查和18/18协议检查标记成立；本轮只是重新计数这些标记。

| MOCHA成功交换阶段 | 请求数量 | 请求应用包字节 | 回复应用包字节 | 合计 |
|---|---|---|---|---|
| reverse_sync | 3 | 46 | 48 | 94 |
| initial_sync | 4 | 63 | 65 | 128 |
| no_change_sync | 2 | 29 | 27 | 56 |
| updated_sync | 3 | 46 | 47 | 93 |
| 合计 | 12 | 184 | 187 | 371 |

371字节含每次6字节请求ID，只计服务端收到并回复的12次成功交换；退出后的11字节GHEAD提交不含在内（11字节来自报告引用），没有ZMTP/TCP/IP/ACK/重传或无线开销。MOCHA使用原同步状态机/ZeroMQ双进程回环与显式ROS适配器；AutoCast为原函数组件探针。完整ROS/DDS、CARLA、MQTT任务场景、无线和任务收益均未完成端到端验证。

## 6. 因果任务：58、45与6的区别

来源：[S11](#s11)–[S17](#s17)，主条件与失败解释见[S35](#s35)。

| 保存运行 | 用途 | 任务回合 | 成功 | 到H未完成 |
|---|---|---|---|---|
| 20261025-01-pilot | pilot | 1 | 1 | 0 |
| 20261025-02-delay | main_delay | 30 | 26 | 4 |
| 20261025-03-fifo | main_fifo | 15 | 9 | 6 |
| 20261025-04-wait20 | wait_sensitivity | 10 | 9 | 1 |
| 20261025-05-epsilon | epsilon_diagnostic | 2 | 0 | 2 |
| 全部 | 含pilot和诊断 | 58 | 45 | 13 |
| 其中主矩阵 | delay+FIFO | 45 | 35 | 10 |

主矩阵各行均为固定9机器人、同任务数seeds0–4，共5回合。全部完成并回站才成功。H=200；H截断均值对未完成回合记200，不能解释为实际完成时间。

| 任务数 | 条件 | 成功/5 | 平均完成比例 | 成功回合返回时间均值 | 全5回合H截断均值 |
|---|---|---|---|---|---|
| 15 | delay0.5 | 3/5 | 0.60 | 24.8872 | 94.9323 |
| 15 | delay2.0 | 3/5 | 0.60 | 24.7170 | 94.8302 |
| 15 | fifo2048 | 3/5 | 0.60 | 34.0975 | 100.4585 |
| 15 | fifo4096 | 3/5 | 0.60 | 26.4202 | 95.8521 |
| 15 | fifo8192 | 3/5 | 0.60 | 24.0207 | 94.4124 |
| 15 | instant | 5/5 | 1.00 | 21.5319 | 21.5319 |
| 20 | delay0.5 | 5/5 | 1.00 | 30.7852 | 30.7852 |
| 20 | delay2.0 | 5/5 | 1.00 | 34.0856 | 34.0856 |
| 20 | instant | 5/5 | 1.00 | 25.5840 | 25.5840 |

FIFO 2048/4096/8192的单位为应用字节/原模型时间，容量65536应用字节；这一阶段不能换写为bit/s或测得无线容量。15任务正延迟/FIFO两个失败种子均零完成，但这不是带宽阈值证据；极小延迟与等待诊断指向并发分派、恢复规则。

| 固定业务回放条件 | 接受消息 | 已交付 | 截至窗口仍未交付 | 已交付时延p95（模型单位） |
|---|---|---|---|---|
| instant | 141 | 141 | 0 | 0.000000 |
| fixed05 | 141 | 139 | 2 | 0.500000 |
| fixed2 | 141 | 138 | 3 | 2.000000 |
| fifo2048 | 141 | 139 | 2 | 3.255519 |
| fifo4096 | 141 | 139 | 2 | 0.563094 |
| fifo8192 | 141 | 140 | 1 | 0.223462 |

6回放共享1条pilot轨迹（141消息、42674应用字节；正文总量采用保存instant行的serviced_bytes），不执行新任务策略。窗口末尾pending按截尾保留，不当作无线丢包或任务失败。pilot的42674字节与正式seed0即时轨迹43583字节属于不同保存运行，不能混用。55行绘图源数据仅覆盖45主回合+10等待回合（报告引用），不包括pilot和epsilon。

## 7. 需求账本：175任务、36项至少多人

来源：[S18](#s18)、[S19](#s19)、[S20](#s20)；定义见[S36](#s36)。逐任务CSV共750行，筛选native_instant后175行，来自10任务目录。

| 量 | 数值 | 分母/定义 |
|---|---|---|
| 静态最少1人 | 139 | 175项任务；能力可行性，不考虑路程忙闲 |
| 静态最少2人 | 34 | 同上 |
| 静态最少3人 | 2 | 同上 |
| 静态至少多人 | 36 | (34+2)/175≈20.5714% |
| 实际多人共同开工 | 85 | 85/175≈48.5714%；不是静态必需组队数 |
| 广播发布 | 1738 | 10个instant回合；每次源发布计一次 |
| 应用字节 | 538419 | 实际UTF-8正文；不含MAC/PHY |
| 接收副本 | 13904 | 1738×8；不是13904次广播 |
| 改变缓存的副本 | 13676 | applied=true |
| 在决策中被引用的网络副本 | 5668 | 至少一次读取，非收益标签 |
| 引用总次数 | 23342 | 同一版本可被多个决策重复读取 |
| 决策记录/实际策略调用 | 1166 / 369 | 跳过分支仍有决策记录 |

静态36与实际85分别从逐任务min_members和actual_workers计数，均与summary一致。只读账本复用了因果主矩阵45回合，其余35个延迟/FIFO回合不是另外35个独立任务样本。未改变缓存或截至结束未被引用的副本不能直接标为“无用消息”；引用本身也不能证明改变动作或提高收益。15/20任务集合不保证嵌套，节点始终9，不能据此推断节点扩展效果。

## 8. 008共同恢复与规模入口

来源：[S21](#s21)、[S22](#s22)、[S23](#s23)、[S24](#s24)；解释见[S37](#s37)。

| 组 | 回合 | 成功 | 到H未完成 | 广播条数 | 应用字节 |
|---|---|---|---|---|---|
| legacy | 10 | 8 | 2 | 1472 | 454382 |
| recovery | 10 | 10 | 0 | 1897 | 596379 |
| scale | 10 | 10 | 0 | 3091 | 977998 |

旧条件10回合=instant5+delay0.5五回合；共同恢复10回合同样分配。恢复使旧delay0.5的3/5提升到5/5，但错相启动、冷却、取消作为组合变更，不能归功于其中一个部件或网络算法。规模构造检查覆盖10配置、两主目录、每族6个成员，两个9/15起点重叠，所以不是12个规模任务。20单步前向检查来自报告引用，不算完整任务回合。

| seed | 节点/任务 | 返回时间（模型） | 广播条数 | 应用字节 | 接收副本 |
|---|---|---|---|---|---|
| 5 | 9/15 | 21.677936 | 143 | 44942 | 1144 |
| 5 | 18/15 | 15.236260 | 171 | 54181 | 2907 |
| 5 | 36/15 | 14.142383 | 197 | 62820 | 6895 |
| 5 | 18/30 | 22.755988 | 328 | 103646 | 5576 |
| 5 | 36/60 | 23.536341 | 650 | 206054 | 22750 |
| 6 | 9/15 | 25.073225 | 174 | 54500 | 1392 |
| 6 | 18/15 | 17.212456 | 196 | 61903 | 3332 |
| 6 | 36/15 | 14.506401 | 211 | 67089 | 7385 |
| 6 | 18/30 | 24.620522 | 344 | 108594 | 5848 |
| 6 | 36/60 | 23.410813 | 677 | 214269 | 23695 |

| seed | 固定总任务：9→36返回时间降幅 | 固定总任务：字节增幅 | 固定每节点任务：9/15→36/60字节倍数 |
|---|---|---|---|
| 5 | 34.761% | 39.780% | 4.58489 |
| 6 | 42.144% | 23.099% | 3.93154 |

规模回合10/10成功。固定面积、能力组复制、静态免费目录与两种子限定结论。接收副本=广播条数×(节点数−1)，用于接收/缓存负担，不可直接乘成单域广播空口。此处应用字节仍不含无线成本。

## 9. 009无线：固定回放与任务闭环分别报告

来源：[S25](#s25)、[S26](#s26)、[S27](#s27)、[S28](#s28)、[S29](#s29)、[S30](#s30)；物理条件及边界见[S38](#s38)、[S39](#s39)。20MHz、6Mbps、每节点65536字节队列、简化单竞争域；无隐藏终端、衰落、多跳及完整802.11状态机。1模型时间=20秒、长度1单位=100米为统一实例化，未用设备日志标定。

### 固定输入60回放

| 队列 | 回放 | 原始消息 | 应用字节 | 已发帧 | 替换 | 碰撞帧 | 发射时长和（秒） | busy并集（秒） |
|---|---|---|---|---|---|---|---|---|
| fifo | 30 | 9273 | 2933994 | 9273 | 0 | 416 | 4.938036 | 4.827840 |
| latest_state | 30 | 9273 | 2933994 | 6981 | 2292 | 225 | 3.679032 | 3.619920 |

两队列各30次=10轨迹×3 MACseed。发射时长降幅 = 1−3679032/4938036 = **25.496047%**。碰撞率以实际已发帧为分母，FIFO 416/9273≈4.4861%，latest 225/6981≈3.2230%；2292条替换不是碰撞丢包。两组dropped均0，排空统计与原窗口统计分开；最大额外排空约0.733425毫秒。回放不生成任务收益。

### 18闭环回合

| 规则 | 成功/回合 | 完成任务合计 | 应用字节 | 发射时长和（秒） | 合计每完成任务空口（毫秒） | 实例busy比例范围 |
|---|---|---|---|---|---|---|
| event_fifo | 6/6 | 210 | 743789 | 1.248936 | 5.947314 | 0.0179%–0.0744% |
| event_latest | 6/6 | 210 | 737724 | 0.908528 | 4.326324 | 0.0129%–0.0554% |
| refresh_latest | 6/6 | 210 | 2982716 | 4.763208 | 22.681943 | 0.0667%–0.2853% |

刷新/event_latest的合计空口成本比 = 4763208/908528 = **5.242775倍**。这是同6目录、每组完成210任务的成本比，不是时间收益。表中每任务指标为总空口/总完成数，是任务数加权合计值，不是六实例等权均值。闭环生成业务随实际行动改变，不能把全部成本差归为队列替换本身。

| seed | 节点/任务 | instant | event_fifo | event_latest | refresh_latest |
|---|---|---|---|---|---|
| 5 | 9/15 | 21.677936 | 21.677936 | 21.677936 | 21.677936 |
| 5 | 18/30 | 22.755988 | 23.420980 | 24.658627 | 22.755988 |
| 5 | 36/60 | 23.536341 | 24.481250 | 22.589843 | 25.288956 |
| 6 | 9/15 | 25.073225 | 25.079932 | 25.073225 | 27.218194 |
| 6 | 18/30 | 24.620522 | 25.676650 | 25.676650 | 24.449070 |
| 6 | 36/60 | 23.410813 | 24.001142 | 24.001142 | 24.001142 |

上述时间仍为模型单位，乘20得到物理秒；instant直接复用008相同目录的归档。刷新相对latest在两实例更快、两实例更慢、两实例相同；instant不保证是此固定策略的最优完成路径。任务只含seed5/6×三规模、MACseed0；三种方法不是18个独立目录。全部实例平均busy低于0.3%，当前没有容量饱和证据。

刷新组247915份接收副本中44383改变缓存、203532未改变缓存；不能把203532直接算为可删除的无用通信。事实年龄从原正文生成算，重发排队时延从本次入队算；副本级p95、成功帧级p95和跨实例范围应分别标明，不可互换。

## 10. 供D采用的问题评估与探索边界

可支持的问题定义：在已知任务目录和固定协作策略下，实际竞争交付如何影响决策所需状态的可得性；怎样以更少维护成本保留协作收益。当前数据能识别突发碰撞、状态缺失与行动变化，尚不能给出总体无线容量上限。

可形成下一任务卡的验证方向：预先冻结合理周期/同步恢复对照和调参预算；增加独立任务种子并对每目录增加MAC重复；分离合并、恢复触发和调度顺序；计入请求/确认/摘要/订阅全部费用；用同决策前缀的受控交付干预检验具体消息的因果作用。观测正文和扩区域需要来源、生产者、消费者及消费动作，不能为制造容量失效而临时压低速率。以上为方案建议，本轮未执行。

当前统计不能给新算法泛化显著性结论。按规模先做同目录配对差值，再把MAC重复作为目录内波动；失败保留在总分母，成功时间和全回合H分数分列。具体样本量、非劣阈值和主比较应由M另卡冻结。

## 11. 来源与受检哈希

下列路径相对仓库根目录；每个ID在JSON中同时保存存储SHA-256和解压正文SHA-256。gzip的两个hash不同是正常现象，正文hash用于原始文件对齐。本轮未修改任何归档或历史manifest。

<a id="s01"></a>
- **S01** [simulation/results/2026-10-23-E1-002-heteromrta/20261023-02/paired.csv](../../simulation/results/2026-10-23-E1-002-heteromrta/20261023-02/paired.csv)  
  存储SHA-256：`5bdffa95b5448e3226d531916648b318bb2c8bf8e348816e2fc483f9cacf0963`。

<a id="s02"></a>
- **S02** [simulation/results/2026-10-23-E1-002-heteromrta/20261023-02/summary.json](../../simulation/results/2026-10-23-E1-002-heteromrta/20261023-02/summary.json)  
  存储SHA-256：`7766e437696948bb93ebf17218d70a1fc3b023a333ec9f9ef28f01e424c0e08c`。

<a id="s03"></a>
- **S03** [simulation/results/2026-10-23-E1-002-heteromrta/20261023-02/manifest.json](../../simulation/results/2026-10-23-E1-002-heteromrta/20261023-02/manifest.json)  
  存储SHA-256：`c46613f19a474b604bd7bd678cc65bac22890004bc8b417a8815ef92004fa86b`。

<a id="s04"></a>
- **S04** [simulation/results/2026-10-23-E1-002-heteromrta/20261023-03/paired.csv](../../simulation/results/2026-10-23-E1-002-heteromrta/20261023-03/paired.csv)  
  存储SHA-256：`6e036f38227007ec2c2d35b3e957cac6bb4c16098d6d3ff6cb41b36908608570`。

<a id="s05"></a>
- **S05** [simulation/results/2026-10-23-E1-002-heteromrta/20261023-03/summary.json](../../simulation/results/2026-10-23-E1-002-heteromrta/20261023-03/summary.json)  
  存储SHA-256：`65010c297cc885602e5411e7af2e7c7fcbe31662d9dbc8e4a0720f93e0682480`。

<a id="s06"></a>
- **S06** [simulation/results/2026-10-23-E1-002-heteromrta/20261023-03/manifest.json](../../simulation/results/2026-10-23-E1-002-heteromrta/20261023-03/manifest.json)  
  存储SHA-256：`1b812f21e80e595c27d8c32f50c3871f28024a8ddf7beab96117010affa37a81`。

<a id="s07"></a>
- **S07** [simulation/results/2026-10-25-E1-003-interface/20261025-03/summary.json](../../simulation/results/2026-10-25-E1-003-interface/20261025-03/summary.json)  
  存储SHA-256：`0ac52e4b45ac6b0e58f14b033e22e317d67eaa9106e67e0b6eb69d726431b0fd`。

<a id="s08"></a>
- **S08** [simulation/results/2026-10-25-E1-003-interface/20261025-03/manifest.json](../../simulation/results/2026-10-25-E1-003-interface/20261025-03/manifest.json)  
  存储SHA-256：`bf2e86960e80ec9a669ac97a313afb9eca3393c4436b3fa6973113bcf9650e81`。

<a id="s09"></a>
- **S09** [simulation/results/2026-10-23-D-002-network-components/probe_results.json](../../simulation/results/2026-10-23-D-002-network-components/probe_results.json)  
  存储SHA-256：`0b68aec4bd0ccdee5a08b519eed020ca08f457c1edafa60ba91d48854beff901`。

<a id="s10"></a>
- **S10** [simulation/results/2026-10-25-D-004-protocol/20261025-02/result.json](../../simulation/results/2026-10-25-D-004-protocol/20261025-02/result.json)  
  存储SHA-256：`878ba2cc53279b1f047f3419a017edb66a855d339bd9320e84f0a15dd76758c3`。

<a id="s11"></a>
- **S11** [simulation/results/2026-10-25-E1-004-causal/20261025-01-pilot/summary.json](../../simulation/results/2026-10-25-E1-004-causal/20261025-01-pilot/summary.json)  
  存储SHA-256：`a1357ffd00ef531a51e85bc58b72ba6b5cfb60358138d4242a2ec78a33695e97`。

<a id="s12"></a>
- **S12** [simulation/results/2026-10-25-E1-004-causal/20261025-02-delay/summary.json.gz](../../simulation/results/2026-10-25-E1-004-causal/20261025-02-delay/summary.json.gz)  
  存储SHA-256：`7353f41eecd3a415932a44f3d408e12e015e19d7279d82154746cc4f46113f5f`；正文SHA-256：`f686fcdf07d505c656bf0031cdc49aa7bb92aa4fa8dd8fffbbe77713ee0ffac2`

<a id="s13"></a>
- **S13** [simulation/results/2026-10-25-E1-004-causal/20261025-03-fifo/summary.json.gz](../../simulation/results/2026-10-25-E1-004-causal/20261025-03-fifo/summary.json.gz)  
  存储SHA-256：`3b34fc562227e9f237b6757fec6222bf126baf0851d0ecf5b90995d691d40dec`；正文SHA-256：`d03f1131520dbe6eb07a0263b93b6c10e69378f4ef7b24b12e3b3d23f2bb7cc3`

<a id="s14"></a>
- **S14** [simulation/results/2026-10-25-E1-004-causal/20261025-04-wait20/summary.json.gz](../../simulation/results/2026-10-25-E1-004-causal/20261025-04-wait20/summary.json.gz)  
  存储SHA-256：`ee412542ad5d6aac40ecd20b92f7543a0eaaeb02ccd0e975ed7f784d184b819d`；正文SHA-256：`847497111e2dee0fe1deadb2f4441e4a38b38b28fc3b32fe143d198032ae0c4b`

<a id="s15"></a>
- **S15** [simulation/results/2026-10-25-E1-004-causal/20261025-05-epsilon/summary.json.gz](../../simulation/results/2026-10-25-E1-004-causal/20261025-05-epsilon/summary.json.gz)  
  存储SHA-256：`fc4841e313f58d2c32ff4b0d7bc381b83d75cbb8bee0c0dd3c1de814c8187271`；正文SHA-256：`6276264cde39d8fc3d013a71c0e8a6651116d01c4d31595745644b32d158a3f3`

<a id="s16"></a>
- **S16** [simulation/results/2026-10-25-E1-004-causal/20261025-02-delay/manifest.json.gz](../../simulation/results/2026-10-25-E1-004-causal/20261025-02-delay/manifest.json.gz)  
  存储SHA-256：`689f0ccc948a55dcaf46bb551f643ea65f98765068f79446e1465d663a829316`；正文SHA-256：`3fdeef3392a741aac6ec53a095af0c08c61cdcf58a091460c48f088dc9bf0924`

<a id="s17"></a>
- **S17** [simulation/results/2026-10-25-E2-005-service/20261025-02-frozen-pilot/summary.json](../../simulation/results/2026-10-25-E2-005-service/20261025-02-frozen-pilot/summary.json)  
  存储SHA-256：`3b2ee01954e260471796edeb59f0f30ea680c55546fd3a05c884265657341df1`。

<a id="s18"></a>
- **S18** [simulation/results/2026-10-26-E1-005-demand/20261026-01-census/summary.json](../../simulation/results/2026-10-26-E1-005-demand/20261026-01-census/summary.json)  
  存储SHA-256：`089703e4f9a9c9fac966d0cc9297eb187119ac34cd02c5b845112166f5cca68e`。

<a id="s19"></a>
- **S19** [simulation/results/2026-10-26-E1-005-demand/20261026-01-census/task_coalitions.csv](../../simulation/results/2026-10-26-E1-005-demand/20261026-01-census/task_coalitions.csv)  
  存储SHA-256：`e962bccb5170d47d450aabdf5e5b76b542df7d3e168db1c9902f1232e9d8b258`。

<a id="s20"></a>
- **S20** [simulation/results/2026-10-26-E1-005-demand/20261026-01-census/cases.csv](../../simulation/results/2026-10-26-E1-005-demand/20261026-01-census/cases.csv)  
  存储SHA-256：`79fedf8ab00ef5d2d6c2a81a0d1ed7bf2eb24403a72a5fc949de55112f55fe17`。

<a id="s21"></a>
- **S21** [simulation/results/2026-10-26-E1-006-execution/20261026-04-analysis/cases.csv](../../simulation/results/2026-10-26-E1-006-execution/20261026-04-analysis/cases.csv)  
  存储SHA-256：`8b7a0e6eac589953d691ff392af7caac0e8a4299cb86ec71e2cc975b6fd36ba6`。

<a id="s22"></a>
- **S22** [simulation/results/2026-10-26-E1-006-execution/20261026-04-analysis/summary.json](../../simulation/results/2026-10-26-E1-006-execution/20261026-04-analysis/summary.json)  
  存储SHA-256：`665eb3cd502cff1c1be69231aa6b54ba4608683f397f1d600859a616641e158a`。

<a id="s23"></a>
- **S23** [simulation/results/2026-10-26-E2-006-scale/20261026-01/summary.json](../../simulation/results/2026-10-26-E2-006-scale/20261026-01/summary.json)  
  存储SHA-256：`2c0d7012bc74802227cc5e86924fef7d574e80a80af38e3e8945c6821199db96`。

<a id="s24"></a>
- **S24** [simulation/results/2026-10-26-E1-006-execution/20261026-03-scale/manifest.json](../../simulation/results/2026-10-26-E1-006-execution/20261026-03-scale/manifest.json)  
  存储SHA-256：`9510781a7405052cac7fb0e52ba1f35aab7c9080f70d8657fdf0a36f8cf68939`。

<a id="s25"></a>
- **S25** [simulation/results/2026-10-26-E2-007-wireless/20261026-03-analysis/cases.csv](../../simulation/results/2026-10-26-E2-007-wireless/20261026-03-analysis/cases.csv)  
  存储SHA-256：`3758a5249bb27bc901792c0a43091f41c70ab0fab4fbcb35ed215b445392a6cc`。

<a id="s26"></a>
- **S26** [simulation/results/2026-10-26-E2-007-wireless/20261026-03-analysis/descriptive_summary.json](../../simulation/results/2026-10-26-E2-007-wireless/20261026-03-analysis/descriptive_summary.json)  
  存储SHA-256：`041678ad4260b929dfde7995027c0ee745119df3d4911aac75b331d0f3df6905`。

<a id="s27"></a>
- **S27** [simulation/results/2026-10-26-E2-007-wireless/20261026-01-replay/cases.csv](../../simulation/results/2026-10-26-E2-007-wireless/20261026-01-replay/cases.csv)  
  存储SHA-256：`68d43a94717c696a336f7c7809410bc9e92cadc0f24f9a45bbd91106f964e8d0`。

<a id="s28"></a>
- **S28** [simulation/results/2026-10-26-E2-007-wireless/20261026-01-replay/summary.json](../../simulation/results/2026-10-26-E2-007-wireless/20261026-01-replay/summary.json)  
  存储SHA-256：`18239f725387ba1ec68bac6530d85906fea23b3447f6eeaa5f1c6c53e273d22a`。

<a id="s29"></a>
- **S29** [simulation/results/2026-10-26-E2-007-wireless/20261026-02-task/summary.json.gz](../../simulation/results/2026-10-26-E2-007-wireless/20261026-02-task/summary.json.gz)  
  存储SHA-256：`6bd66cfb2f0dc4fdaea429172e2e057c24a48762bcc06d43d64f80f91d751c34`；正文SHA-256：`f7371034cb2bb3edf02dc4ea46b8b1754ae87d080b9f71a9c372b613d12131b6`

<a id="s30"></a>
- **S30** [simulation/results/2026-10-26-E2-007-wireless/20261026-02-task/manifest.json](../../simulation/results/2026-10-26-E2-007-wireless/20261026-02-task/manifest.json)  
  存储SHA-256：`703ac15caad88ec07475ceebf27cd99f59a55d0d974bf078b02b70d600e3a8e7`。

<a id="s31"></a>
- **S31** [research/agent_native_network/HETEROMRTA_REPRODUCTION.md](../../research/agent_native_network/HETEROMRTA_REPRODUCTION.md)  
  存储SHA-256：`3f72979b9b647ffd5bdf1316fdaa03cc31e27a609611e8db69bfebc3ef332178`。

<a id="s32"></a>
- **S32** [research/agent_native_network/HETEROMRTA_NETWORK_INTERFACE.md](../../research/agent_native_network/HETEROMRTA_NETWORK_INTERFACE.md)  
  存储SHA-256：`fa357dd7360df4c070432ef3882683c866c430a4be58e55fa2486f37e9a4ecc8`。

<a id="s33"></a>
- **S33** [research/agent_native_network/NETWORK_BASELINE_RUNTIME.md](../../research/agent_native_network/NETWORK_BASELINE_RUNTIME.md)  
  存储SHA-256：`35b166142c025b7527ec86e20524ca97608ec3e485ab70fde18b5cdb01ed0d9f`。

<a id="s34"></a>
- **S34** [research/agent_native_network/MOCHA_RUNTIME_ENTRY.md](../../research/agent_native_network/MOCHA_RUNTIME_ENTRY.md)  
  存储SHA-256：`6364aac9106c91eadf17afa2af5d0a5a95e624681e134469067659ee7cf397fc`。

<a id="s35"></a>
- **S35** [research/agent_native_network/CAUSAL_SERVICE_STAGE.md](../../research/agent_native_network/CAUSAL_SERVICE_STAGE.md)  
  存储SHA-256：`06fcf85fee182018c85ff116f0d15c254b8d33357c6118e59c62b7b8b8cf3e3a`。

<a id="s36"></a>
- **S36** [research/agent_native_network/DEMAND_CENSUS.md](../../research/agent_native_network/DEMAND_CENSUS.md)  
  存储SHA-256：`d8bf0dc39377008a03062fdca26d854a51cb95f488666b193f5017d8f754d3af`。

<a id="s37"></a>
- **S37** [research/agent_native_network/DEMAND_EXECUTION_STAGE.md](../../research/agent_native_network/DEMAND_EXECUTION_STAGE.md)  
  存储SHA-256：`d9dfcb808179b306621aa78ab30ecbe7b9d433e3c4a63f937ebe4477c9c76526`。

<a id="s38"></a>
- **S38** [research/agent_native_network/WIRELESS_EXECUTION_STAGE.md](../../research/agent_native_network/WIRELESS_EXECUTION_STAGE.md)  
  存储SHA-256：`309a886a9133f5e2c1dbf29e0083cf082e5fdecba6c4a5b5a5fcdb588818e943`。

<a id="s39"></a>
- **S39** [research/agent_native_network/WIRELESS_SERVICE_CONTRACT.md](../../research/agent_native_network/WIRELESS_SERVICE_CONTRACT.md)  
  存储SHA-256：`28ad9fcc776edec8456ed4a0ade206a77035e4fe13cd1c27f309c05cc0ce3e41`。

## 12. 完成状态

本轮18项保存数值一致性检查均相符；它们是小型计数/算术核对，不是研究测试。历史测试通过仍以原记录为证。本窗口只读与汇总命令均已退出，无本窗口研究或后台进程；未检查其他窗口进程。无交付依赖阻塞。D可按本表引用，C-011独立核对后由M验收。本卡转review后停写，后续实验和修订等新任务授权。输出hash记录于E2-009主卡，避免输出间循环hash。

