# M-053 网关适配与前端解耦

2026-11-15 M-053已交付生产397cee9并推送：电脑端统一来源管理，兼容旧Semtech UDP/既有HTTP/CH340串口接收；前端按来源ID和selection_epoch切换，不绑定编号1或固定网关格式，支持自动、手动偏好与失效回退。旧网关/原协议decoder/设备NVS/网卡未改；旧UDP载荷与token ACK回环、慢HTTP隔离、串口自动/显式配置worker和浏览器联合检查通过，C038-01已关闭。H最终移除本机临时USB绑定，原START入口自动识别节点1并实收2/3/4/5四源；手动选择后恢复auto通过。正式launcher15924/Studio3364留用户，唯一锁域production/data/node-serial-lease，未来操作须先核实际owner。旧RHF本轮未接入，固定目标192.168.137.10:1680必须仍可达，旧控制全链及实物换网关/拔电恢复未复测。证据simulation/results/20261115-M-053-gateway-adapters/。

日常仍运行START_STUDIO.cmd，页面http://127.0.0.1:8794/；在LoRa视图的接收来源中使用自动选择或手动选择已验证接收器。自动发现仅查询身份与RX能力，不修改板角色。旧网关保持原有网络连接/固定发送目标；无需再次安装或升级旧网关。

证据按SOURCE.json逐文件保留来源与SHA-256；first-live-candidate为显式配置修复前现场，final-auto-live为本轮最终部署，不能混用。
