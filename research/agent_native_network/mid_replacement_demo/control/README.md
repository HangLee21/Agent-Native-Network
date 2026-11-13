# 五板控制台页面

直接双击index.html可用离线预览。在线服务/启动器由E2-018负责，真实SOCP由E1-018提供，串口由H负责；页面本身不连接串口、不刷写。H的M-019实验优先使用设备。

示例：源A、目的E，选择“恰好指定跳数”4，预览得到无环链；将离线输入图改为“仅A–B–C–D–E邻接”，要求1跳时会报告不可行。手动中继填B,C,D可预览A→B→C→D→E；重复节点会拒绝。MID离线只画明确的假设输入图，标记未运行SOCP，不伪造最优结果。

服务入口是仓库根目录下 `tools/mid_console/START_CONSOLE.cmd`，默认只预览；需要实板时按E2/H交付说明启用，H的实验锁优先。页面由服务同源加载。GET /api/status仅浏览，POST /api/plan仅规划；只有点击“发送到实板”才POST /api/run。必须同时获得服务run_available=true、计划明确可执行且非busy，页面才放开发送。无服务、仅预览或能力未知时禁用。同一计划在本页至多提交一次，出错不自动重试；重新发送需要重新预览。运行期间按需GET本次run进度（有界80秒），可显式停止；停止期间仍禁发。若发送请求超时，应刷新状态核对服务是否已启动运行。

已按E1正式PlanLibrary和E2服务字段适配：请求使用A–E字母，带model_id、明确的双向graph_edges；状态有可用子集时传node_set。显示model来源/单位/适用范围、solver.status、chain或candidate_edges的编码概率。MID的500ms周期保持语义单独说明；假设模型上的真实求解仍不是实时链路测量。图只示意布局，不表示距离或覆盖。

H结果位于run.result：按evidence_kind、packets[].identity（origin/boot/seq/dst）、actual_edges、relays、destination_received和destination_unique_received显示。实际发送边不拼接成未经确认的完整路径；只有目的rx_local确认才显示收到。缺失、部分、失败和超时保留，原始JSON可展开。修改选项后清空上一轮显示，避免旧路线叠在新计划上。

本机验证：JavaScript语法检查通过；实际Chrome离线浏览器19项操作/显示检查通过，最终记录见 `simulation/outputs/D-017/20261107-03-delivery-ui/BROWSER_CHECK.json`，截图为同目录control-desktop.png。其中适配器记录是明确标注的合成显示夹具，仅核对界面字段，不算服务运行或RF证据。本D窗口没有启动服务、打开串口或运行实板发送。E2负责浏览器到真实服务/规划的正常操作，H负责串口验收；实际能力以他们的新记录为准。

H已于2026-11-07交付真实页面到实板验收：在M-019收尾释放设备后，CUA由8766页面实际发送A→E恰好4跳3条（实际A-B-C-D-E，3/3）和B→D MID3条（真实SOCP optimal、假设模型，实际B-D，3/3），每条均有目的rx_local和载荷匹配。证据 `simulation/outputs/H-007/20261107-02-browser-hardware-acceptance/`，原始run由该目录列出。自动结束stop及全体串口关闭有实测记录，手动stop中止未单独实测。H保留给用户的入口为 [本地实板控制台](http://127.0.0.1:8766/)，该服务由H管理；D只读取验收记录，没有重复发送。此项仍待C/M验收，不将6条有限功能结果外推吞吐、覆盖或实时最优链路。

页面数据标签区分离线、假设、预览与实板；原始计划/运行记录可展开。H从M-019交还设备前不得抢串口。回放导航离线指向../index.html，同源服务约定/replay/。

若上次运行是cleanup_unconfirmed，页面会列出停止/清理尚未确认的板号、失败阶段和下一步；这与实验保留、串口占用分别显示。由H确认设备及清理、恢复服务后，点击“刷新服务状态”并重新预览，不能用刷新页面代替恢复证明。尚未预览、计划过期、已提交的禁发原因各自明确；同一计划不自动补发。新增25项隔离浏览器状态检查通过，具体接口兼容和边界见[状态提示交接](STATUS_HANDOFF.md)。D没有为这项提示改动访问8766或设备。
