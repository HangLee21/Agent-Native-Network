# E2-015独立协议与分析验证

2026-11-03。**生命周期v4的20项独立主机C/串口测试通过；分析器36项发布检查及修订C日志/H封装互验通过。** 这些是确定性主机协议功能证据，不是ESP目标编译、SDK调用或RF实测。没有打开物理串口、安装工具、模型或旧ns-3运行。

E2只写tests/espnow、simulation/outputs/E2-015与自身卡，保留其他窗口与全部旧运行；不Git写、不子代理、不跨聊天发送。基准d8325a230ce41943f43528c6a0c9552949e07abe，实际角色窗口执行。每次运行带公共manifest、卡/合同/源码快照；[RUN_INDEX.json](RUN_INDEX.json)记录14次运行及逐manifest hash，没有覆盖历史。

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

## 分析器局部冻结与H接入

[ANALYZER_FREEZE.json](ANALYZER_FREEZE.json)固定以下三个文件并已承诺停改：

- analyze_logs.py SHA256 e317f4eeed40ba299641ec61d37f531b5fcbcad4f154c87d2623936be3c14818。
- ANALYZER_API.md SHA256 d5b94dc4adfbb1a8659eb180a39e8ec5e35eeccbc1d7d977f75d494ad021fb52。
- README.md SHA256 3ec0a9e1bd11020b6711fa5929de79ba33dde5142810b6f6a88d27f492e2f183。

只依赖Python标准库；可调用函数/CLI与ann.analysis.v1字段见[API合同](ANALYZER_API.md)。第11轮36项通过、失败/错误/跳过0，发布输入/结果hash在冻结文件；此后只改C测试/验证报告，三个文件hash仍匹配。

按最终E1 telemetry区分logger node+boot与事务origin+origin_boot+seq；原请求分母排除反向echo新事务。tx_submit status0只是调用前公告，不能当driver已接受，缺独立API接受日志时driver_accepted=null。tx_result数字1/0仅link回调，按node+boot+tx_attempt关联去重复，不作PDR。frame_rx不作应用交付，rx/echo unique_receive才作为端点接收；RTT只由echo_correlation的原请求身份配对同源boot时钟，毫秒乘1000不是微秒RF精度。

[第14轮互验](../../simulation/outputs/E2-015/20261103-14-immutable-capture-context/result.json)使用第13轮已完成实际C v4日志和H已读取的device_rx外层格式，1项通过。保存不可变CAPTURE_CONTEXT.json，把C源manifest/build、raw/H封装log hash绑定；函数运行后上下文文件字节不变。输出[原行分析](../../simulation/outputs/E2-015/20261103-14-immutable-capture-context/actual-C-v4-analysis.json)与[H格式分析](../../simulation/outputs/E2-015/20261103-14-immutable-capture-context/H-envelope-v4-analysis.json)的PDR/goodput/RTT一致，均evidence_kind=synthetic。合成1秒窗口/主机虚拟RTT只检查计算，不写硬件测量；range/单向时延/RF重试/airtime均null。每项null有metric_status理由，生成/接收/echo有文件行号与源manifest/config/log/analyzer SHA。

H以后应按M派发接口在真实捕获后保存不再变的捕获上下文，再计算并追加有效实测量；当前E2没有写H工具或实际执行该自动接线。当前固件bench可靠事务，raw_no_retry分析标签不证明raw台架已实现。接收日志完整性、实测窗口、板卡绑定仍由H验证；synthetic内外标记不得升级成hardware_measured。

## H分段验证与保留的失败

H v2的8文件与当时M冻结匹配后，E2独立执行8项检查：实际profile保持unverified/未到货/默认不开口，bindings空、bench未armed；measurement_ledger六项value/source默认null；host-synthetic不能登记实板，USB桥名不能代替物理绑定，错误OS身份/错误任务根先拒绝，默认入口在mock枚举下不打开端口、不填测量。全部临时输出仅E2目录，实际OS枚举和H-002未执行。第05轮准备+H+日志工具共48项通过，不把H原14项写成E2重跑。

之后H进入C发现问题的修复，旧v2/v3源码哈希变动时停止依赖，不读活动实现。C两反例（active stop/close异常）由H/C处理，E2不冒称自己复核了最终修复或覆盖完整工具。当前H源码单测显式暂停/skip；实际Capture类快照未建立，不冒称已测试该类的新版本。H格式互验使用已读外层合同，而不是运行活动H源码。

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
| 11 | 最终分析器36项发布检查通过，局部冻结 |
| 12 | E1生命周期v4，18项独立C检查通过，旧三反例全部关闭 |
| 13/14 | 增加正向arm/bench/stop与arm过期后20项C通过；再核不可变捕获上下文和v4日志/H格式 |

07/08/12的父manifest曾沿用准备阶段limitations模板文字，**不改历史原字节**；各自result的actual_E1_core_compiled=true、core_build、命令/二进制与原字节源码是实际主机C编译证据，RUN_INDEX给出补充映射。13起父manifest已按实际C执行更新该限制，ESP/RF始终未验证。14的compiled=false只表示本轮没有重新编译，日志来自有hash的13轮，不表示日志是Python伪造。

## 预算与交审

截至第14轮受控子进程累计约27.093秒/600秒，单命令≤120秒；输出约3.36MB/100MiB，无超时/资源保护停止。所有失败、补充映射和原run保留。没有把断言数/packet数当实验样本，也未将skip当通过。

本窗口命令均已结束，无模型、无线、实际串口或后台进程；E2交review停写。后续由M向H传递已冻结分析器、C审查和M验收；若分析器接口确需变更，先M协调新冻结，不能静默改交H版本。硬件到货与ESP目标编译/刷写/真实RF证据仍属未验证，本任务不自动续跑。
