# D-021 同页正式接入

index.html=workbench.html，行为workbench.js；旧template/catalog保留。按E2 WORKBENCH_CONTRACT：GET /api/snapshot取H settings/snapshot，POST /api/reset {}复位；/api/plan、/api/run {settings,algorithm}、/api/runs/id同页。fixed/latency_aware实际配对两臂，selected_algorithm供选看；mid实际原MID单臂，只支持A↔B双向/不限，UI有反向开关与限制提示。非法组合由服务拒绝。

物理走同源硬件status、plan{settings,mode,count}、run{plan_id,confirm:true}、runs/id及/stop。只有明确发送按钮run；草稿/算法/包数变更使plan失效禁发。模型干预被拒，屏蔽仅路由约束；H快照不校准原实板SOCP假设系数。

20方向单独保存，默认单向编辑。采集开始范围/样本/实测服务与模型字段分列，完整snapshot原始来源可展开。蓝箭头为当前草稿候选，橙箭头为保存包实际记录，不能相互替代。节点和边可点，策略/选包/物理预览同页，无主流程跳转。

正常入口验收见simulation/outputs/D-021/20261108-01-browser-acceptance/；新job20261108-134033-0cc5c195bc44，1次新软件模拟，物理只status/plan。待C/M独立验收。

## D-023 路线图增量（2026-11-08）

route-view.js负责图层和保存记录回放，不持有发送plan、不调用run/send/stop。源/目的/跳数/算法/参与节点/模型修改后300ms合并预览；请求和响应绑定完整草稿、模式、算法、node_set和图版本。旧成功或失败均不能覆盖新图。实板预览与主发送均传node_set（默认ABC），count1；预览plan_id不流入发送。没有恰好k跳路径时清图并说明，禁止改成其他跳数。

图中路线显式分为当前草稿规划、保存仿真实际包、保存实板实际包。蓝色规划箭头有方向/节点圈/跳序；模型时刻可选开始/窗口/恢复。时延枚举候选不能冒充原MID/SOCP结果，也不预言运行中的观测与配置传播。原MID缺逐包结果时清除其他臂的链。

实板保存记录只GET /api/hardware/runs/<24hex>；使用该run的bindings、原identity、actual_edges（tx_submit）、relays（rx_relay）和destination_received。完整链还须内部节点均有中继接收、目的收件匹配；缺段只画已有段，不拼接plan.chain。它不是当前链路测量。分机没有集中沿途证据时明确说明，不画猜测链。

仿真只用保存run的actual_path和原生成/接收时刻；算法与结果策略双向同步，包下拉、位置条、播放共用同一包。播放每400ms推进一条保存记录，到末尾停止；编辑/换模式/恢复/失败停止。当前草稿不重算历史包。旧history请求及在途任务反馈不能恢复已被新选择清除的橙链。无新RF/仿真验收证据见D-023/20261108-06-route-highlighting。
