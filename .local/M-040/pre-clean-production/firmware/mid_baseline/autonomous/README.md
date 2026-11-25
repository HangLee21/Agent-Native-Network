# 板端按需多跳

入口 idf/，UART460800/8N1，OLED API2。主机只给最终目的MAC和0..160原始字节，ND01互证邻居和SR01寻路都在板上执行。旧MID/edge/discovery入口及包保留。帧、时限、容量和失败语义见 INTERFACE.md / source_route.h。

初次各板核MAC，stop到radio=false；若已有静态profile先deployment_clear，若已有一跳配置先discover_clear。分别给相同组/信道，无远端路径：

```json
{"cmd":"route_config","nonce":"setup","group":29,"channel":6,"autostart":true}
{"cmd":"neighbors","nonce":"peers"}
{"cmd":"send","nonce":"business-1","dst":"<最终目的实际MAC>","payload_hex":"00ffe4bda0e5a5bd"}
{"cmd":"routes","nonce":"routes-1"}
{"cmd":"stats","nonce":"stats-1"}
```

route_config写本机mid_route/cfg，autostart=true立即启动并复位自启；route_start显式恢复，stop停止并取消未提交业务但保留配置，route_clear停止后清配置回信道6。原discover_start/clear在本包兼容为当前动态模式启动/清除。信道输入1..13受SDK区域限制，台架用6。ND01 HELLO2–3s抖动，确认9s有效、12s未见lost；等邻居互证后发首包。目标可不是本地邻居，服务名到最终MAC映射由应用提供。

send成功含origin/origin_boot/packet_seq，是本地接纳；tx_queued在自主模式表示已接纳到有界待发/出队路径，不表示已有路或射频成功。route_accepted/waiting/request/candidate/selected/no_route/invalidated/delivery_unknown/drop含源身份、request和path；rx_relay、tx_submit/link和目的rx_local保持同一源MAC/boot/seq，rx_local.payload_hex是原字节。route_selected.seq是请求序号，不能当业务身份。无端点ACK，不重发未知交付包；用后续新包验证恢复。

窗口200ms，绝对截止1500ms，窗口外回复不改已绑定路径。按最少跳、完整MAC字节序比较实际候选。真实板D的a5:20比B的a5:cc小，因此A-B-C/A-D-C同长平局通常先D；host合成MAC的B较小，不能拿字母预测真实板顺序。缓存10s、首跳boot绑定；下游匹配ERROR撤路，错误丢失由缓存过期恢复。同目的合并一轮，8条待发/4目的轮次，满表明确拒绝或drop。

可选台架局部过滤：link_filter {nonce,allow:[本地允许邻居MAC]}，空allow隔离；link_filter {nonce,clear:true}恢复。接收对所有ND01/SR01/MID按物理来源过滤，单播出口也过滤；广播仍在空口广播，应各板对称设置接收关系。过滤运行期、非持久、复位丢失，不提供目的路径/下一跳；这是逻辑拓扑而非自然RF隔离。改变后等HELLO状态更新，已提交帧不能撤回。

routes只读本板缓存。stats分离ND01/SR01计数：route_control/data_frames/bytes是核心出队给适配器的应用帧，不是空口字节/硬件重试；route_submitted/link_ok/link_fail是本地提交/回调，不是端点确认。SR01控制RREQ/RREP60B、ERROR61B、DATA60+载荷，ND0141B另计。route_core_bytes为目标ABI静态核心大小；pending/out/candidate_high为表/队列高水位；free_heap/minimum_free_heap是整个固件。route_process_total/max_us仅含core tick/receive，不含JSON/日志/编码/完整业务墙时。未有实板记录时这些是接口，不能当已测值。

退回：stop核radio=false、route_clear、link_filter(clear:true)，H按实际MAC/lease执行app-only0x10000恢复旧OLED1969并核info/idle。不擦NVS分区/eFuse。Ubuntu服务由E2接续；实际空表多跳、撤中继、新路径及最终各板状态由H记录，host不代替RF或独立Ubuntu部署。
