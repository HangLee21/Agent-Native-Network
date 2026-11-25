# E2-015独立协议与分析验证

2026-11-03。当前结果分为四组，均失败/错误/跳过0，不合并样本数：

| 运行 | 当前证据 | 项数 | 本轮编译实际E1 C |
|---|---|---:|---|
| 13：生命周期v4 | 独立主机C/console测试，含100条连续事务 | 20 | 是 |
| 15：分析器v2 | 三项C退修后的分析器回归 | 44 | 否，分析器测试 |
| 16：v4日志互验 | 复用第13轮实际C日志，与H外层格式及不可变context互验 | 1 | 否，复用已有C输出 |
| 17：H_capture_v5独立集成 | 实际Capture分段读取→实际分析桥→v2分析器及关键负例 | 6 | 否，复用第13轮C输出 |

这些是主机协议功能和分析器证据，ESP目标编译、SDK调用、实板及RF测量仍未验证。第16轮只核H格式；第17轮已调用最终冻结H的实际Capture与分析桥，没有调用主动台架main或物理串口。C三项退修仍待独立复核；M已登记E2_analyzer_v2并交H/C。本窗口没有打开物理串口、安装工具、运行模型或旧ns-3。

旧检查点中“actual_E1_core_compiled始终false”只适用于第01–06轮准备阶段。第07/08/12/13轮实际编译M冻结的E1 C并记录true；其余日志/API轮的false表示该轮未重新编译，不能解释为从未编译或没有实际C日志。旧输出、失败和卡快照原字节保留。

E2只写tests/espnow、simulation/outputs/E2-015与自身卡，保留其他窗口与全部旧运行；不Git写、不子代理、不跨聊天发送。基准d8325a230ce41943f43528c6a0c9552949e07abe，实际角色窗口执行。每次运行带公共manifest、卡/合同/源码快照；[RUN_INDEX.json](RUN_INDEX.json)记录17次运行及逐manifest hash，没有覆盖历史。

## 当前源码、编译和结果

M冻结E1生命周期v4（FREEZE.json version2），SHA256 `3b028fb77103ad011a92e0fdb7f34d4065a940806240ad570f7f30e21c2d908f`；21项文件逐hash匹配后复制到E2 run的E1-frozen-source。实际链接ann.c、ann_console.c、ann_log.c，分别编译E2独立驱动和E1 host/console程序。编译器为已有`C:/Strawberry/c/bin/gcc.EXE`，GCC13.2.0 MinGW-W64 x86_64；不安装环境，不把主机编译说成ESP-IDF编译。

最终执行：

```powershell
python -B -X utf8 tests/espnow/run_validation.py --pattern test_core.py --output simulation/outputs/E2-015/20261103-13-final-core-contract
```

[最终result](../../simulation/outputs/E2-015/20261103-13-final-core-contract/result.json)：20项、失败/错误/跳过0，actual_E1_core_compiled=true；[core_build](../../simulation/outputs/E2-015/20261103-13-final-core-contract/core_build.json)保存完整命令、编译器版本、21项输入和二进制hash。E2驱动binary SHA256 a1bc4b84d41eb63b41402f76d0bfa6530c409976a6fcbdbfe379bf64b7deab91，E1 host binary 8083a9e6af63b3f6a48a4203c726afdefec498eed9a83dff3b835f84e9f820a8。测试通过以实际C执行为依据，不是Python协议替身。

| 独立用例 | 已核边界 |
|---|---|
| 正常多跳/分区 | 五节点链按实际出队帧/物理测试邻接传递；成功经过4段数据转发，无路径时不伪造端点交付，pending有界终结 |
| 替代路径 | 四节点菱形，先发现实际路由，再切断已选源第一跳，核心通过ERROR/重发现走另一可达路径；没有给核心拓扑真值 |
| ACK丢失/重复 | 丢ACK触发DATA重试，端点只交付一次；重放DATA和已完成的ACK不造成二次交付/确认 |
| 取消 | 发现前取消、本地已排队DATA取消均不再交付；已送达效果不会被取消回滚，随后迟ACK不恢复源完成 |
| 截止 | 排队到期、未tick之前直接到来的晚RREP与晚ACK均不能下溢寿命或确认过期源事务 |
| 重启 | 源相同seq在新boot为新身份；中继初始化后仍可转发，旧/新boot不混同；不承诺接收重启后永久exactly-once |
| 有界存储 | pending8满明确拒绝；重复风暴填满out32/event32而不越界，queue/event overflow显式可见，stop清队列 |
| 状态更新 | 同origin/boot/key新seq覆盖旧值，重放旧DATA不覆盖，寿命后状态过期 |
| 连续100条 | 并发1、100ms签发间隔、60000ms寿命的100条事务全部一次交付/确认；第17及100条后重放第一份仍live旧DATA不重交付，覆盖16槽压力与64序号窗口外旧包拒绝。约10秒为调用者虚拟时钟，不是无线吞吐 |
| wire独立交叉 | Python按公开112-byte little-endian/CRC32格式独立生成，C编码逐byte相同，单byte损坏均被C拒绝；参考工具自身测试不替代该C交叉测试 |
| console | host-synthetic身份、idle/info无业务、未arm拒绝、nonce/重复键/过长行恢复、count1001拒绝、正向arm/bench/stop及arm过期回idle；只通过stdin/stdout，无串口 |

C驱动所有邻接/丢帧/时间推进均是测试传输，不模拟真实MAC竞争、距离、RF吞吐或能耗。不推五板硬件可达性或扩展容量；协议无分片/加密/跨重启永久去重，C核心非线程安全，约束以冻结INTERFACE为准。

## 当前分析器v2冻结与H接入

[ANALYZER_FREEZE.json](ANALYZER_FREEZE.json)记录M授权退修后的v2冻结，三个文件从此停改：

- analyze_logs.py SHA256 acb8ba503597d4943c3f7d340dfec9508b4a86126389dc67bfc362a83c1025cd。
- ANALYZER_API.md SHA256 53a4b65d298fd85d16de21f0249d1663b082d7886eb34c28555fc9655c34c8ec。
- README.md SHA256 ce4efa3c06ff4c7c1fb22fafbf102d692abeaad32d0955397b591568c3e67379。

只依赖Python标准库；可调用函数/CLI与ann.analysis.v1字段见[API合同](ANALYZER_API.md)。第15轮44项通过、失败/错误/跳过0，发布输入/结果hash在冻结文件。第11轮36项属于旧v1历史证据，已被C发现的三项退修扩展覆盖；具体修复与第16轮v4互验见文末。

按最终E1 telemetry区分logger node+boot与事务origin+origin_boot+seq；原请求分母排除反向echo新事务。tx_submit status0只是调用前公告，不能当driver已接受，缺独立API接受日志时driver_accepted=null。tx_result数字1/0仅link回调，按node+boot+tx_attempt关联去重复，不作PDR。frame_rx不作应用交付，rx/echo unique_receive才作为端点接收；RTT只由echo_correlation的原请求身份配对同源boot时钟，毫秒乘1000不是微秒RF精度。

[第16轮互验](../../simulation/outputs/E2-015/20261103-16-v2-v4-capture-context/result.json)使用新版v2分析器、第13轮已完成实际C v4日志和H已读取的device_rx外层格式，1项通过。保存不可变CAPTURE_CONTEXT.json，把C源manifest/build、raw/H封装log hash绑定；函数运行后上下文文件字节不变。输出[原行分析](../../simulation/outputs/E2-015/20261103-16-v2-v4-capture-context/actual-C-v4-analysis.json)与[H格式分析](../../simulation/outputs/E2-015/20261103-16-v2-v4-capture-context/H-envelope-v4-analysis.json)的PDR/goodput/RTT一致，均evidence_kind=synthetic。合成1秒窗口/主机虚拟RTT只检查计算，不写硬件测量；range/单向时延/RF重试/airtime均null。每项null有metric_status理由，生成/接收/echo有文件行号与源manifest/config/log/analyzer SHA。第14轮是旧v1分析器的历史对照，记录保留。

H以后应按M派发接口在真实捕获后保存不再变的捕获上下文，再计算并追加有效实测量；当前E2没有写H工具或实际执行该自动接线。当前固件bench可靠事务，raw_no_retry分析标签不证明raw台架已实现。接收日志完整性、实测窗口、板卡绑定仍由H验证；synthetic内外标记不得升级成hardware_measured。

## H分段验证与保留的失败

H v2的8文件与当时M冻结匹配后，E2独立执行8项检查：实际profile保持unverified/未到货/默认不开口，bindings空、bench未armed；measurement_ledger六项value/source默认null；host-synthetic不能登记实板，USB桥名不能代替物理绑定，错误OS身份/错误任务根先拒绝，默认入口在mock枚举下不打开端口、不填测量。全部临时输出仅E2目录，实际OS枚举和H-002未执行。第05轮准备+H+日志工具共48项通过，不把H原14项写成E2重跑。

之后H进入C发现问题的修复，旧v2/v3源码哈希变动时停止依赖，不读活动实现。C两反例（active stop/close异常）由H/C处理，E2不冒称自己复核了最终修复或覆盖完整工具。旧H v3模块测试因当时未取得稳定快照而显式skip；这段只描述历史范围。第16轮以前只核H格式。M提供最终H_capture_v5冻结后，第17轮已建立12件原字节快照，独立运行实际Capture和分析桥（见下节）；不等于重跑H完整工具套件或物理台架。

| 记录 | 解释 |
|---|---|
| 01/02 | 37/38项准备工具通过；不是C/无线测试 |
| 03 | 前置旧ann.h hash变化导致冻结文件未建立后，我仍启动套件，setup FileNotFoundError；记录保留，非H代码失败 |
| 04/05 | 修正为H专属冻结后46/48项通过 |
| 06 | API32项通过，H活动时只运行分析文件套件 |
| 07 | v3实际C12项通过，包括100事务；当时未含后补三反例 |
| 08 | 稳定v3归档18项中4失败：C晚RREP/晚ACK/取消排队DATA三反例及分析器时间排序过严一项。前者交E1修，后者由E2修；全部保留 |
| 09 | 修正分析顺序后，旧实际C正向日志/H封装互验通过 |
| 10 | H源码再偏离旧v3时前置复制未执行，却继续启动缺快照测试导致1失败；保留。后改为明确跳过缺少授权快照的H类测试，不掩盖为成功 |
| 11 | 旧v1分析器36项发布检查通过，后经C发现三项退修 |
| 12 | E1生命周期v4，18项独立C检查通过，旧三反例全部关闭 |
| 13/14 | 增加正向arm/bench/stop与arm过期后20项C通过；再核不可变捕获上下文和v4日志/H格式 |
| 15/16 | C三项退修后的v2分析器44项通过，再核v4 C日志/H格式1项通过；待C独立复核 |
| 17 | 最终H_capture_v5实际Capture/分析桥独立互验6项通过，物理串口/无线0 |

07/08/12的父manifest曾沿用准备阶段limitations模板文字，**不改历史原字节**；各自result的actual_E1_core_compiled=true、core_build、命令/二进制与原字节源码是实际主机C编译证据，RUN_INDEX给出补充映射。13起父manifest已按实际C执行更新该限制，ESP/RF始终未验证。14的compiled=false只表示本轮没有重新编译，日志来自有hash的13轮，不表示日志是Python伪造。

## 预算与交审

截至第17轮受控子进程累计约30.811秒/600秒，单命令≤120秒；输出约5.53MB/100MiB，无超时/资源保护停止。本次只新增有界H集成6项，没有重复20项C或44项分析器完整套件。所有失败、补充映射和原run保留。没有把断言数/packet数当实验样本，也未将skip当通过。

本窗口命令均已结束，无模型、无线、实际串口或后台进程；E2交review停写。保持M已登记的E2_analyzer_v2四件hash不变；其余源码清单见E2_FINAL_FREEZE.json。M已提供H_capture_v5最终freeze，第17轮有限集成完成；本窗口交回review，等待C独立审查新测试及M验收，不自动续跑。若分析器接口确需变更，先M协调新冻结。硬件到货与ESP目标编译/刷写/真实RF证据仍属未验证，本任务不自动续跑。

## C-017分析器v2退修及重新冻结

M解除v1冻结后，依据C报告E2-01/02/03最小修订，函数签名和schema保持。第15轮44项分析器测试通过，失败/错误/跳过0；第16轮使用已完成第13轮的实际v4 C日志与H封装互验，1项通过。这里只复用日志，没有重新编译核心、运行活动H实现或增加硬件证据。

- E2-01：rx/echo字段存在时严格要求bool。0/1、字符串、null均记issue并排除，PDR/goodput未知；只有synthetic缺字段rx/旧echo允许legacy兼容。显式false echo不能成为旧RTT。
- E2-02：重复generated身份保留首行与冲突来源，不采用覆盖后的时间；即便重复内容相同也保守标歧义。该键echo全部排除有效RTT，计入invalid_echoes/generated_without_echo，并报告歧义键数量；混合输入可保留其他无歧义成功子集。回归覆盖不同时间、不同正文、相同重复和混合正常身份。
- E2-03：硬件上下文须H-001、hardware_capture_unanalyzed、同run；相互冲突/缺run拒绝。log_sha256以每个输入日志resolve后的绝对路径绑定原字节hash，缺映射/错hash/后改日志拒绝。其他来源manifest可补充，不能为本run硬件标签背书。正向门控测试使用明确的假设硬件标签，仅验证逻辑，未写真实测量台账。

API、README和analyze_logs.py已按ANALYZER_FREEZE.json v2重新冻结；H须据新API准备不可变context后再接入。旧v1由M原字节归档，C旧失败未改写。当前结果是E2修复自测通过，三项C问题是否关闭仍由C/M独立验收。

## 最终H_capture_v5独立集成（第17轮）

M明确H已completed/review停写后，先核freeze锚点`2e7ada3487c8e202c764680bc93b7ae6e3e4c5a420b5d2aff88643d7a7838d56`，12件源码逐hash匹配，复制到E2本轮H-frozen-source原字节快照。实际Capture和analysis_bridge由该快照导入，分析桥按M登记加载未改动的E2_analyzer_v2四件。读取入口后没有运行H作者verify_host/verify_c_capture或主动main，独立测试只写E2本轮目录。

[第17轮结果](../../simulation/outputs/E2-015/20261103-17-final-H-capture-independent/result.json)：6项、失败/错误/跳过0。[integration_inputs](../../simulation/outputs/E2-015/20261103-17-final-H-capture-independent/integration_inputs.json)绑定H12件/API四件、原C源manifest/build和trace hash。复用第13轮已完成实际v4 C日志；当前run实际编译=false，只表示本轮没有重新编译。

| 用例 | 独立核对结果 |
|---|---|
| 正向实际Capture | 原C日志以≤37byte的内存分片经过实际poll/record并close，再实际finalize_capture；source原请求分母1、目的唯一接收1、同源boot有效RTT1，source log/context hash和行号保留；未明确SDK接受仍null |
| 覆盖完整性 | JSON损坏、未完行、logger boot改变、目的计数不符、event overflow共五个子例均令覆盖未确认，PDR/goodput为null |
| 缺窗口 | PDR仍可算；goodput保持null，不用签发间隔代替实测窗口 |
| stop未确认 | 保存context，停止分析，没有analysis或measurement update |
| synthetic伪升级 | 实际C synthetic内标记即使装进hardware_serial外层仍拒绝，未生成测量update |
| 来源错误 | 实际Capture context的错run/错log hash分别被同run和原字节映射门控拒绝 |

全部基线measurements.json保留null/source=null且字节不被改写；不存在measurement_updates.jsonl。正向分析在synthetic子目录，虚拟1秒窗口/主机RTT不是硬件性能；source端反向echo是新事务，不进入原请求分母。串口枚举与open_bound入口设禁止保护，输入只是内存字节缓冲，未执行真实OS枚举、开口、bench、无线或模型。没有用H18轮作者35项或H17轮集成代替E2这6项。

当前E2局部API冻结四件hash保持。6项是独立Capture/桥接功能证据；不代表完整H主动控制路径、端口驱动/硬件或ESP目标通过。C尚未审阅本次新增测试/结果，由M提供最终冻结后验收；原失败与旧manifest不改。
