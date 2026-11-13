# E2-019当前可消费入口

最终入口：`simulation/outputs/E2-019/20261107-07-final-explained/FINAL_DATASET.json`。正式30场/15配对/7200源身份、3600方向秒窗与所有实际模拟路径/安装/求解/版本表均可消费；仅E1/02+03，排除E1/01和E2/04。REPORT.md/scenario-summary.json给每场景每种子差值，seconds-detail.json给flow_seconds及每场唯一global_control_seconds，event-decomposition.json/selection-invalidation-audit.json给逐包原因与模型更新窗口证据。05首对缓存复用到06，07只补解释不重算核心统计。

各策略各1200计划：渐弱846→963，中继退出850→1116，完全分区775→775；保留无优势场景。每秒空窗0、晚收分列、独立目的身份/payload；控制不能双向重复加总，不称PHY。首次三窗恢复可能再跌，务必展示或说明recovery_interpretation，不把它标成永久恢复。181/10条无下一跳有实际install后清除选择至下个tick的事件证据，不一概归旧路由。全部软件仿真，不拼入M019/020或实板表现；C/M待验收。

以下为过程交接，当前以FINAL_DATASET为准。

最新正式首对：simulation/outputs/E2-019/20261107-05-formal-first-pair/DATASET.json。仅对应E1/02-first-pair，已核gradual_link/seed11，fixed166/240对adaptive192/240，目的唯一事件/payload、因果输入与控制安装审计无问题。D可直接取每场packets/seconds/annotations/topology_truth/directions/tables及实际receive路径。E1/01与E2/04为检查版，不合并、不用于正式回放。正式整批E1/02+03已交，E2接续其余28场并复用05结果，最终入口到达后覆盖本说明的优先级。

最小合同CONTRACT.md，标准化核心analyze.analyze(context,events,truth_callable)及paired(runs)，评价图真值truth.Truth(scenario_id)。原始E1字段未交前不猜事件字段或结果；收到第一对后只做有来源的薄映射，每份原始数据分析一次。

已交给D可立即消费的环境数据：simulation/outputs/E2-019/20261107-03-topology-interface/topology.json。三场景各121个半秒快照、原H场景JSON/来源hash、节点示意坐标、方向路径见证、评价锚点具备。它是实际H场景API生成的环境真值，尚未包含逐包模拟轨迹或任何交付结果，不作策略先知输入，不当真实RF。

已完成10项synthetic针对检查：延后渐弱不会在丢失前提前宣告恢复、分区从40秒重连计恢复同时保留总经历时间、删失/unknown/no_interruption、方向可达、目的身份去重/零窗、晚收分列、发送尝试不当目的交付、配对输入门控与差值。不等于E1已完成30场；当前实验结果消费0。

E1-019仍负责实际执行和首对/整批原始manifest交付；E2不代跑仿真、不复跑M019/020、不占硬件、不后台轮询。第一对到达后输出可直接绘图的packets/seconds/annotations/topology_truth/directions与pairs、DATASET索引；后续全批复用首对分析，不覆盖历史。本轮分析命令退出，状态为入口已就绪、等生产者主动交接。
