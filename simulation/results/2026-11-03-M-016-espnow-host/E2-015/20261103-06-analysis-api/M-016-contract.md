# M-016 跨窗口接口合同 v1

2026-11-03。用户要求立即实现到货前代码；沿原窗口加既有H，不创建副本。协议是ESP-NOW上层对等网络，不是原生IP/802.11s。五板静态测量优先，尚无硬件数值。

## 路径与依赖

E1独占firmware/agent_native；H独占hardware/eora_hub_400tb和tools/espnow_hardware；E2独占tests/espnow；D独占research/agent_native_network/espnow_20261103及两份既有导航。C冻结后审。H不改firmware，E1不改H工具；M传递公共接口冻结。

## 最小串口接口（E1与H共同遵守，修改须M同步）

UART console 115200、8N1，UTF-8逐行JSON；启动/IDF日志可混杂，主机只解析有schema=ann.serial.v1的JSON对象。命令最大512 byte，错误返回明确error，不执行未知命令。info无射频发送副作用；上电idle不发业务。

请求 {"cmd":"info","nonce":"probe123"}
响应 {"schema":"ann.serial.v1","event":"info","nonce":"probe123","firmware":"ann-espnow","protocol":1,"node_id":"aa:bb:cc:dd:ee:ff","boot_id":"...","build_id":"...","chip":"esp32s3","board":"unverified","mode":"idle"}

info只证明固件/chip身份，不能自动证明400TB板型；绑定依据另存。其他基础命令stats/stop；bench用于显式人工或armed台架运行，参数run_id/dst/count/interval_ms/frame_bytes/echo；frame_bytes是ESP-NOW字段总长度（包括协议头），v1上限250。bench请求对应日志至少event=generated/tx_submit/tx_result/rx/echo/stats，含run_id、node_id、boot_id、origin_id、seq、t_us、frame_bytes、payload_bytes及适用状态，未知字段允许null，firmware定义精确语义并交M冻结。所有控制命令应给nonce关联回应；finite bench最大60秒、count≤1000，低负载先测，stop可取消；未经绑定与armed不发送bench。E1可选择串口测试功能先实现，网络模式后以同固件扩展；禁止只交空函数。

## 测量与自动检测

需要真实硬件的range_m/pdr/goodput_bps/rtt_p95_ms等初始为null、status=not_measured，reason=hardware_not_available，source=null。fixture测量永远evidence_kind=synthetic且独立目录。端到端交付以接收节点唯一消息为准，回调成功只属于link callback；无法取得RF重试/airtime时保持unknown或显式估计。

用户已授权到货自动检测。默认一次OS串口枚举，不打开串口，不猜板型，不下载/安装/刷写。仅配置中已绑定设备且标记允许probe才握手；验证nonce与协议后才能登记ready。主动台架run另需armed合同，设备集合/参数/次数/输出目录冻结；当前无硬件不运行。为后续H-002每小时检查准备--once入口，单次≤60秒，无永久进程、无未知设备写入。新证据追加，不改历史；尚无板时只记录waiting_hardware，不能填测量。

## 已核官方入口

- https://www.ebyte.com/product/2472.html
- https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/network/esp_now.html
- https://github.com/espressif/esp-idf/tree/v5.5.1/examples/wifi/espnow

目标为初步可运行代码，不要求当前承诺百节点能力、真实PHY测量或未安装工具链编译。开发完成后的可验证问题必须修复，不能把代码/接口问题推给硬件到货。

## 公共接口检查点 v1（M已核hash）

E1-014公共头include/ann.h、include/ann_console.h及firmware/agent_native/INTERFACE.md已冻结，hash见M-016-verification.json的E1_public_interface_v1。H/E2可读取这三文件对齐，核心src和适配实现仍活动，不得据此声称测试已通过。增加显式arm(node_id/run_id/duration_ms)；start/bench依赖arm；host chip为host-synthetic。初版固定112 byte上层头，bench总长112..250，echo总长120..250；主机工具须使用此范围。该报文格式是五板功能原型，规模研究后续评估头开销。其余串口事件精确身份和时间字段需实现后再冻结。
