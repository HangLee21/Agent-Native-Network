# 五板到货前准备

H-001，2026-11-03。当前没有硬件。采用 ESP32-S3 的 ESP-NOW 做单跳承载，上层网络由 E1 实现。LR1121 在本阶段不参与无线传输。这里的板型来自厂商资料，未开箱确认；CH340、COM 口名称或芯片握手均不能证明是400TB。

## 接线与固件准备

先给五板编号 board1–board5，拍下各自型号、版本和USB口对应关系，逐板插入枚举并保存绑定依据。初期使用USB数据线连接主机，避免同时接外部供电与外部UART。厂商列出的UART0为GPIO43 TX、GPIO44 RX、3.3V逻辑；如以后外接转换器，应核对实际板版次、共地并交叉TX/RX，禁止接5V TTL。无需接LR1121、OLED或修改板上跳线来运行ESP-NOW。

板载Wi-Fi天线及USB桥接实际布置、Flash/PSRAM、GPIO复用与原理图版本均待实物核对。产品页链接的说明书/原理图无法由当前网页解析器读取，因此本交付不猜填LoRa/OLED接线。来源及逐字段限制见profile.json。

目标固件目录由E1维护，H不修改。串口合同为coordination/handoffs/M-016-contract.md：115200、8N1、UTF-8逐行JSON，schema=ann.serial.v1；最大命令512字节（H按包含换行的保守上限校验）。IDF日志可混杂。必须核对固件hash/build_id、SDK版本、目标esp32s3和编译日志后才能记“目标编译通过”。本任务不安装SDK、不刷机、不擦除、不装驱动。

依赖：Python 3.11+标准库可做来源清单与测试；pyserial可枚举/访问串口。缺pyserial时Windows使用Win32_SerialPort只读枚举；该fallback不提供完整USB序列号和location，也不能握手。用户之后安装依赖需另有明确执行范围，本工具不会自动安装。检测到的工具状态见本次输出的environment.json。

## 安全默认与绑定

以下命令只枚举一次，不打开任何串口，不改DTR/RTS，不调用刷机工具；输出目录必须不存在，程序不会覆盖历史。

```powershell
python -B -m tools.espnow_hardware.hardware_tool --once --output simulation/outputs/H-001/UNIQUE-CHECK-ID
```

bindings.example.json故意保持空。到货后在新配置中加入每个物理确认的绑定：

```json
{"id":"board1","port":"COM9","vid":6790,"pid":29987,"serial_number":"ACTUAL-USB-SERIAL","node_id":"aa:bb:cc:dd:ee:ff","allow_probe":true,"physically_confirmed":true,"binding_basis":"saved photo and one-at-a-time port mapping evidence path"}
```

上述VID/PID、COM、MAC只是格式示例，不能原样使用。实际每项均从设备/来源记录取得；没有USB序列号时可显式固定location或完整hwid，但这仍是操作员登记，不是防伪认证。配置中填写的所有识别字段必须与当前枚举一致，端口改名后不得自动追踪未知端口。芯片MAC应从可信的逐板初始化记录获得；没有预先绑定的MAC就不能由本工具自动探测未知设备。

```powershell
python -B -m tools.espnow_hardware.hardware_tool --once --probe --bindings hardware/eora_hub_400tb/ACTUAL-bindings.json --output simulation/outputs/H-001/UNIQUE-PROBE-ID
```

只对allow_probe=true、身份一致的绑定设备发送info，验证随机nonce、schema、固件ann-espnow、protocol整数1、chip=esp32s3、预登记MAC、非空boot/build/board与mode=idle。ready仅表示此固件握手通过，board_identity仍为unverified。绑定串口打开前请求DTR/RTS=false；操作系统/USB驱动可能产生瞬时控制电平，本机无板，未验证是否复位。

stats/stop还需--probe --device board1 --command stats（或stop）；没有任意命令透传。仅显式standalone stop恢复路径接受身份与nonce均合格的active info，收到对应stop回应后才记stopped；普通probe、stats及bench仍要求idle。身份/nonce不符不发送stop。逐端口与采集文件关闭异常分别记录，仍继续其余清理并尝试保存check、measurements和manifest；cleanup_failed为失败状态。--log可对一个≤2MiB的既有日志做hash与schema计数，证据类型为unverified_external_log，不导入测量、不自动信任fixture。

## 有限台架入口

bench.example.json默认armed=false。后续先冻结实际绑定集合、run_id、发送者/接收者、帧长、次数和输出路径，再明确armed。程序不从heartbeat自动启动bench。

```powershell
python -B -m tools.espnow_hardware.hardware_tool --bindings hardware/eora_hub_400tb/ACTUAL-bindings.json --bench hardware/eora_hub_400tb/ACTUAL-bench.json --output simulation/outputs/H-001/EXACT-PLAN-RUN-ID
```

一次最多5板、一个发送者、一个目的；count≤1000，ANN头固定112字节，bench字段总长112..250字节，echo为120..250字节。单次捕获≤45秒，整个入口内部预算55秒、合同上限60秒。串口累计≤2MiB。先核所有绑定，再逐一握手；全部通过且时间预算足够，才逐板arm(node_id/run_id/duration_ms)，检查nonce回应，再对接收/中继板start、发送板bench。arm本身不发无线业务；有效期固定为捕获时长加5秒，最长50秒。所有打开的板均采集原始行；一旦尝试arm，结束或异常都会对全体发送nonce stop并记录是否收到回应。停止未确认记失败，板端仍应执行自己的有限运行上限。相同run_id对应唯一新输出目录，不允许覆盖/自动补跑。

当前对齐M明确active_freezes.E1=E1_lifecycle_v4的完整冻结（FREEZE version2、22项）及未变的golden；此前E1_full_v3和公共接口v1保留为历史。verify_host.py只接受代码中列入M授权清单的active版本，核FREEZE.json固定锚点、M完整来源清单及各文件hash，测试前后均核一次；未知版本、漂移、路径越界或清单缺项均拒绝，不回退旧冻结，失败也保存最终manifest。后续E1改版须M同步新冻结并明确授权更新该清单。

host-synthetic芯片身份会被真实硬件握手拒绝。消息身份为(origin_id, origin_boot_id, seq)，node_id+boot_id属于当前记录节点；tx_attempt是该节点本次启动内的提交编号，不是RF重试。原始行保留这些字段、unique_receive及evidence_kind，不重命名为测量。frame_rx不是唯一应用接收。echo_correlation关联request_origin_id/request_boot_id/request_seq；RTT只可由同源同boot的generated与echo_correlation本地t_us相减，不跨板减时钟，当前不接尚未冻结E2分析器，不计算数值。

五板配置不等于五板多跳实验。此入口验证串口控制和单发送者台架采集；多跳/恢复合同另行冻结。原始serial.jsonl包括host_tx/device_rx、主机时间与解析事件；tx_result只属于链路回调，端到端交付要由接收节点唯一消息验证。未定义/未验证的RF重试和airtime保持unknown，不由回调计数推算。

measurements.json初始所有数值均null，status=not_measured、reason=hardware_not_available、source=null，后续不覆盖。主机合成测试只在tools/espnow_hardware/tests的临时根内运行，不进入实测台账。

台架结束后核全体stop、前后stats的boot和event/queue overflow、接收端delivered计数与唯一rx日志、坏JSON/残行，关闭串口和采集文件。先写不可变capture_context.json，记录本run、H-001、采集状态、raw_logs路径/hash、绑定/握手、前后计数与实测host monotonic窗口；窗口包含串口控制/停止/排空延迟，不是PHY计时。分析配置同样独占写入且不再改写，再调用M冻结的analyze_files，绝不把将继续更新的RUN_MANIFEST作为其来源。

分析只在显式bench结束后触发，once/probe不发无线也不分析虚拟测量。成功且完整的hardware_serial采集可按分析器逐指标状态，把有效PDR、协议payload goodput和同源echo成功子集P95追加到measurement_updates.jsonl，source包含analysis与原始日志、上下文、配置、分析器hash；距离/RF重试/airtime无观测仍null。缺源、生成数不足、损坏日志、接收计数不符、停止未确认等均不能导入有效实测。synthetic分析只写synthetic目录，不能升级为hardware_measured。

当前使用M明确授权的E2_analyzer_v2（FREEZE schema/2，release v2-C017-revision），按active_freezes.E2_analyzer核完整四件hash并固定FREEZE锚点。context包含log_sha256对象：每个resolve后日志绝对路径映射原始字节SHA256，同run、同源配置与上下文在分析后也复核未变。未知分析器版本/漂移拒绝，不回退v1。20261103-13保留为被撤回v1的历史检查，不作为最终集成证据。

主机验证入口：python -B -m tools.espnow_hardware.verify_host --output simulation/outputs/H-001/<新run>。它核E1/E2冻结后运行合成安全/控制/来源测试，再核来源未变；不枚举或打开真实串口。额外的verify_c_capture同样要求新H-001输出，用已安装CMake/Ninja在该run内编译冻结的主机C入口、运行有限echo场景，将实际C日志经过真实H Capture和E2分析函数互验。该入口的覆盖计数与一秒归一窗口明确为synthetic fixture，不是UART/RF实测，不创建实测更新；主机编译不代表ESP目标编译。每次≤120秒、编译最多2作业，禁止借此运行旧ns-3或无线实验。

工具支持显式--task-id H-001或H-002，默认H-001；输出必须是本仓库simulation/outputs/<task-id>/<run-id>/的全新目录，manifest的task_id与选择一致，拒绝跨任务根和嵌套run目录。H-002强制--once，只允许枚举或附加--probe进行已绑定设备info握手，拒绝bench、stats/stop、--device及日志导入。后续测量分析接口待M冻结后再集成，当前不猜算数值。

H-002仍须先由调用方读取其主卡：仅ready/running且M-016验收后执行。以下是未来入口示例，本轮没有运行H-002，也没有创建后台进程、计划任务或循环轮询；调度由M统一登记。

```powershell
python -B -m tools.espnow_hardware.hardware_tool --task-id H-002 --once --output simulation/outputs/H-002/UNIQUE-CHECK-ID
```
