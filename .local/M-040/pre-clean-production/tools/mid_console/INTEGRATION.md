# M-020服务集成约定（E2）

实际接口已对齐生产者。请求src/dst=A..E、mode=mid|hops|manual、count=1..10，对应hops=1..4或有序via；可选node_set、graph_edges和白名单model_id=assumed-five-v1。HTTP不允许客户端指定模块、路径或命令。

E1：固定worker用现有E1-016虚拟环境调用`PlanLibrary(ROOT).plan(request, available_nodes=..., live_status=...)`，最多30秒。服务保存完整JSON计划，加唯一plan_id、顶层run_available/busy/preview=true。preview=true表示尚未执行，不是演示求解。MID保留真实solver、权重和多路径语义；hops/manual保留确定单链、选择规则和逻辑输入图；模型来源及SHA原样返回。

H：`adapter.status(publisher=<本计划src>)`无开口，仅USB和最近已核info；`execute(plan, output, stop_event, on_event=emit, timeout=60)`只在显式POST run后的独占worker内调用。输出在simulation/outputs/H-007/<时间>-console-<唯一ID>/，由H创建与写入；E2不复制串口代码。默认preview模式强制run_available=false，启动参数--hardware允许消费H实际状态。H在Windows进程锁内再次核当前MAC/boot/build/baud/idle，实验保留优先。服务不调用reserve/release。

GET status返回ok/service/mode/busy/run_available/reason/hardware/active_run_id/models/limits。hardware含H原始ready_nodes/publisher/publisher_boot/state_basis/live_info_recheck_required；缺适配器/依赖给原因。无设备可预览。

POST run只接受{plan_id}，返回202及ok/run_id/plan_id/state/events/result；同plan_id幂等返回原运行，不再次执行。其他计划busy时409。GET /api/runs/<id>同结构；POST /api/runs/<id>/stop只接受{}，设置同一Event；60秒也设Event。worker返回前不释放busy。H未确认各已读取设备停止/端口关闭时保留cleanup_unconfirmed占用，须H处理，不自动放行。退出设stop，非daemon执行线程等待H返回。

原始H结果保留result，顶层evidence_kind来自H。顶层packets兼容D：identity拆origin/origin_boot/seq/dst，delivered只映射destination_received，actual_edges/relays保留。只有同身份源TX、全部中继RX/TX、目的RX齐备且下一跳无歧义时生成actual_path；缺项为null，不借plan.chain补齐。summary.accepted为源成功命令数、received来自destination_unique_received、unconfirmed保留未确认。MAC回调不当交付。当前H占用，未做RF验收。

D：/同源服务D页面，/replay/为既有回放；无D时E2备用页。页面载入/刷新/plan不调用execute。POST要求与当前Host精确相同的Origin，不接受跨源写；静态导航允许正常进入。
