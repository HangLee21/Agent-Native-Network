# 8767 同页工作台接口

GET `/api/workbench` 返回 `{ok,settings,snapshot,catalog,algorithms,execution_semantics}`。snapshot保留H的全部来源、采集时间、样本数与20方向字段；settings是独立草稿初值。GET `/api/snapshot`（别名`/api/measured-defaults`）返回H快照；POST `/api/reset {}`返回相同初值，不改原始测量或物理状态。H未交付时503明确提示。

仿真沿POST `/api/plan {settings,time_s}`、`/api/run {settings,algorithm}`、GET `/api/runs/<id>`。algorithm为fixed或latency_aware；旧MID设置则fixed或adaptive。两臂均实际计算，selected_algorithm表示选看哪一臂，execution_semantics固定paired_run_selected_arm_display。不能把选看说成只跑该算法。新运行目录E2-022，旧job/result地址保留。

正式实测schema为mid.measured.settings.v1，H measured.py编译的场景直接交E1 runner/workbench.py。fixed/latency_aware选择分别记录在job，实际调用compare_latency，不经旧编译器重建。实测schema也可选mid（或compare_mid），只支持A→B、反向开启、不限跳数；先验证，不支持则400说明，支持则实际执行原MID，execution_semantics为actual_arms_executed。run配置/选项分别冻结settings.json/options.json。

实板同源接口：GET `/api/hardware/status`，POST `/api/hardware/plan`，POST `/api/hardware/run {plan_id,confirm:true}`，GET `/api/hardware/runs/<24hex>`，POST `/api/hardware/runs/<id>/stop {}`。保持8766原响应和错误状态。无任意URL、恢复、文件或底层命令接口。run只接受预览的plan_id及显式confirm，不接settings。

plan可直接接8766原src/dst/mode/hops/via/count/model_id/node_set/graph_edges，仍由8766规划模型核验；也可接`{settings,mode,count}`，mode为hops或mid：从草稿提取连接/节点屏蔽为路由约束，参数修改或时间窗故障拒绝执行。原MID+hops不兼容时明确拒绝；时延感知动态改道只有仿真。所有实板规划都受原assumed-five-v1模型限制，不能把H测量成功率当成该SOCP的真实校准输入。边屏蔽不改变物理邻接，复位只恢复草稿。

8767加载、复位、预览不发包；8766保留ready/lease/boot/cleanup检查和发送上限。验收仅status/plan/read，不为验收额外run/stop。
