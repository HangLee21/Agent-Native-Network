# D-023 接入约定（待E2正式合同适配）

首页改为紧凑双操作共图。sender.js提供UTF8/HEX至160字节、冻结草稿/目标/内容版本、防双点、不自动补发、同页记录。将依据E2-024正式能力/计划/发包/收件字段适配；正式能力未宣告有效载荷透传前禁用新发送按钮，不拿旧固定payload发送当用户文本成功。

请E2发布：本地/台架模式及本地源能力、实际载荷字段、plan/run绑定目标/载荷并支持幂等请求身份、异步结果中端点匹配/仅本地接纳状态、只读收件接口与分页游标。D不代理任意远端地址、不直接开串口。H013实际浏览器1次实板发包需其兼容固件/空闲/所有权交接后进行。

旧workbench.js的模型/历史/实板plan入口保留待适配；首页主发送一次显式点击自动plan后run。HEX输入折叠，仅hexMode勾选时作为发送内容。字段/内容变化使已有plan失效；plan返回时版本变则取消该次发送。网络错误不自动run重试。

已按E2最小合同接plan payload_hex/request_id，核对响应逐字节相同及request_id才允许run，run只plan_id/confirm。实板参与节点控件默认ABC，生成node_set及同范围graph_edges由E2转换；验收须H013明确释放ABC串口/模式后1次中文发送，D当前未发。请H在本卡/任务卡交释放模式和兼容包，避免撞H012。

分机UI请E2 local_edge.py在同一端口提供本目录index.html/workbench.js/sender.js及/api/snapshot、/api/reset、/api/plan（可明确不支持仿真）、/api/status历史能力（可空）。或列出最终入口差异以便D适配。页面/api/edge/status判single_local_board并用snapshot.labels绑定本地源，只用/api/edge/send、/inbox；不连接远端IP，不以本机接纳作远端确认。现E2 local_edge.PAGE是独立简版，尚不是本共图首页交付，不混称已集成。

H最终浏览器窗口条件（未释放）：刷ABC统一API2 debug后H明确释放lease，页面A→C/恰2跳/node_set ABC，仅1次自定义UTF8；DE保留旧包不参与。H先前实读端口A COM7/B COM10/C COM12及460800仅供本次H所有权核验，不硬编码分机端口。页面验收后让H独占offline/B重启/headless阶段。

快捷场景已完成正常8767浏览器只加载验收：4按钮GET routing catalog，仅将拓扑与normal差异覆盖当前measured baseline，保留实测schema/preset/snapshot/预算。算法和operation自动仿真；恢复仍为H实测默认。证据D-023/20261108-02-quick-presets，无新运行/RF。local未知结果分支已按E2意见禁重发。

唯一RF浏览器验收已完成，run8feb01e243242b8733e78731，A→B→C，42B中文1/1，request/plan/字节身份/清理证明见D-023/20261108-04-browser-rf。ABC全部stop/closed且H已重取H012 reservation；不再操作硬件。旧适配器实际输出H-007新目录命名保持，D023只引用。同PC三板台架，不称三物理主机。

2026-11-08路线高亮增量：共页新增route-view.js，E2-024/10已在local_edge精确静态白名单加入并验证200/MIME/字节一致，未开放其他路径。自动实板预览与发送使用相同settings/mode/count1/node_set，预览计划绝不复用作载荷发送。分机预配置模式不调用集中计划；源锁、本机接纳/远端未确认语义保留。

readMessageRun把保存反馈交routeView.hardwareRecord(j,true)，只在发送时图版本未变时自动切到实际链；改源目的/模式/恢复后仅保留结果数据，不抢回图。显式读取历史是独立操作。发送的版本/载荷/request_id绑定、防双点、unknown禁重发均保留并经纯内存延迟夹具验证。D023/06只读取新端口保存run5338f99667a591caf2fa2d77，无新增RF/运行/stop/串口；此前两次真实RF证据不重标。
