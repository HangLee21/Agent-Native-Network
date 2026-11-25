# 正式package-01的A/B原生执行配置

本检查点可直接交C审查包与配置，H在C无阻断且身份/备份满足后执行。正式manifest=d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683，build=mid-v1-99e77eba7e472bd687ea18321d6ac566e9e8b21d764431e1b42ec7fee945c2f3。52件全部长度/hash已核；E2没有重编ESP目标，构建记录是E1来源。无MID实物结果。

## H实际步骤

1. 按MAC/USB重新核A/B，端口已变化，不用旧COM提示。核原4MiB备份和剩余预算。按C适用范围先A后B写指定包，启动后逐板`{"cmd":"info","nonce":"e2-identify-A"}`（B用独立nonce）。保存解析出的完整command_result为info-A.json/info-B.json，同时保留原始串口。必须是本build、mid-espnow、对应MAC、非零boot、idle、radio/stopping/locked均false。
2. 在仓库cwd，用现有Python运行只读离线物化（不打开串口）：

```powershell
python -B tools/mid_baseline/validation/native.py materialize --info-a <H已保存的info-A.json> --info-b <H已保存的info-B.json> --run-id <H唯一run-id> --output simulation/outputs/H-005/<新run>/AB-native-plan.json
```

入口会再次验52件及E1实际求解的network_update（db11092bb00a3b80ef76dbf30eea15cb9d5755836a7bd58b52e8d8d2944e79c2），以本次A boot生成3份真实config frame_hex，seq1/2/3。该命令配置是运行时具体命令，不预填历史boot。物化成功不表示允许忽略C就绪结论或直接开RF。

3. H用自身同一套已绑定串口句柄按actions顺序发送JSON `command`（115200、逐命令等待相同nonce的command_result/ok），不要再启动另一个publish.py抢串口。两板start绑定同一publisher=A和A当次boot；A在0/1/2秒发布新seq配置。两端必须观察config_applied seq>=3及A flow0→B、B flow1→A的route_selected，5秒未满足则stop退出，不发业务。
4. 按actions取两端e2-base-xx stats；A→B 5包，再B→A 5包，每包16byte（payload里方向/编号）、间隔500ms，各阶段drain≤1.5秒。每条send要ok，不失败重发。不增加ACK/强制路由。源屏LINK OK仍目的未确认；目的rx_local本地收到。总run≤24秒，算H最多6次/6分钟中的一次，不重置RF账本。
5. finally对两端stop；两秒内用只读stats确认radio=false、stopping=false、locked_until_reset=false，保存e2-final-xx stats。任何身份/包/采集异常、超时/锁定、stop未确认均停止该分支并留证，不自动复位/重试/追加run。像素/PRG由H另行实物核对，不把READY当像素证明。

H捕获原始host_tx/device_rx，标明硬件来源hardware_serial，device_rx外层event保留mid.serial.v1原对象（也支持direction=rx,line=原JSON）。每条原事件不要补造run_id/generated/ACK；source队列接纳为原tx_queued，MAC回调另计，目的rx_local含payload_hex。保存两端build/boot、实际时窗与覆盖证据，不以count×interval推窗口。

## 原生分析入口

```powershell
python -B tools/mid_baseline/validation/native.py audit --plan <实际AB-native-plan.json> --log <原生采集JSONL> --context <不可变H-context.json> --output simulation/outputs/H-005/<新run>/native-analysis.json
```

context须task_id=H-005、run_id与plan一致、status=capture_complete、evidence_kind=hardware_measured、package_manifest_sha256等于上列manifest；log_sha256对象把所有原输入绝对路径映射至SHA256；coverage按A/B实际MAC给bool；measurement_duration_us配duration_clock=host_monotonic_controlled_window，来自实际host窗口。只在两端boot/build一致、无input overflow/callback timeout等fatal、实际base/final stats计数与源接纳/目的唯一记录相符、stop完成且每源5接纳时计算PDR/goodput。缺项保留null，输出逐消息原文件行号。RTT、RF重传/空口时长始终未知；控制费用目前仅API提交次数，未提供字节长度则null。该分析器不回写硬件台账。

无context的host native探针只输出synthetic_or_unverified及观察计数，PDR/goodput为空，不能升级RF。旧归一化提案不是native接口；本入口直接消费正式原生字段origin/origin_boot/seq/dst/flow。

## 独立验证边界

E2主机编译实际冻结app_main+mid.c+H模型+原SDK cJSON，SDK/RTOS/无线/显示publish为明确fake。4项通过：真实命令解析/重复键拒绝、5份真实源编码帧送入真实目的回调后rx_local、B源发送、缺回调锁至复位且start拒绝。首次编译因E2 shim遗漏stdbool.h失败已保留；固件未改。另3项物化/身份拒绝/原生审计检查通过。不是ESP运行、像素或无线证明，C仍须审该精确增量。

## ABC增量：A/B先行，不等待五板

H ABC标签hash f16af2085ce37993a0a69c45d2af7091f3412390cf7165557ceda4c6b25cd264，库存hash a3498aa190939d98b6992ddda9801056ccc792ec4ee601ee29a2ad1fd1477fe7；C=90:da:72:48:a4:e0，当前端口只是提示，仍按实物重新核对。E1真实MAC资产cases/INDEX.json hash 37d879827f6e50bd940737dccdee6ca82a79d410b4ac2957a06dc39826ff1f57；工具逐项校验input/solution/update/offline-bin四类hash。H不得部署其中boot1/seq1示例bin。

取得本package的C info（label允许?，MAC/build/boot/idle仍须匹配）后，在上面的materialize命令增加`--case AC --info-c <H实际info-C.json>`即可生成三板命令；`--case BC`与`--case AC_controlled_two_hop`同理。每case独立run/context；依次AB→AC→BC→受控AC，分别双向5/2/2/3包，至多24/15/15/20秒，均算入H既有RF最多6次/6分钟，不新增RF预算。原生协议最多两流，每case分别start/config/stop，不能同时下发六流。控制seq段分别1..3/101..103/201..203/301..303，不复用旧示例boot；任何板重启后重新info并重新物化，不复用配置。

AC/BC会启动三板并校对实际route_selected属于其SOCP配置候选，不擅自改下一跳。受控AC工具独立确认四条路由恰为A→B→C及C→B→A；输入A-C模型禁边是逻辑零容量/惩罚条件，不是实测直连断开。中继B只属于这个case角色，其他case节点仍可源发/目的接收。审计输出relay_evidence逐消息原文件行号；只有完整硬件coverage及源/中继rx_relay+tx_submit（下一跳为终点）/目的rx_local身份均对应，controlled_forwarding_verified才可为true。native日志不提供TTL观测，不据日志声称实测TTL改变。A/C转发能力本次没有直接测量，不由B一次转发外推。

ABC继续使用同一package-01，C字母?+完整MAC符合授权；先完成C完整备份、相同包/配置的C就绪范围再部署。若H剩余RF次数不足则停在已有结果，不能为补齐计划重置账本。E2未操作设备，完整物化工具4项最终检查通过，未执行物化输出的命令。
