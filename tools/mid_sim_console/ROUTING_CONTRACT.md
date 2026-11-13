# M-023 routing接入（E2）

8767单服务兼容两种schema：mid.routing.settings.v1走H routing/E1新简单路径执行器；mid.console.settings.v1继续原MID runner，不改算法含义或旧job。GET /api/catalog默认新routing，?mode=mid取旧MID；/api/defaults与/presets同规则，响应含settings。root catalog附legacy_catalog供界面模式切换。

POST /api/plan {settings,time_s:0}：H routing.preview的候选链/代价/available/message/settings_sha256原样返回，标注scenario_preview_only，非策略观测/非实际交付。time_s允许0..duration显式查看假设图；运行时仍只按E1已到达观测控制，不借预览先知。POST /api/validate支持两schema。

POST /api/run {settings}沿原结构，冻结完整配置，新目录simulation/outputs/E2-021/<新id>/；旧E2-020 job、registry和/results/<id>/地址保持。新worker按schema固定选择执行器模块，无HTTP可指定命令/文件/模块。GET /api/runs/<id>、/result、cancel与旧接口一致。

新result提供routing_policy/strategy_labels/candidates（假设预览）以及逐臂packets，每包含packet_id/src/dst、generated_s/received_s、actual_path（仅实际接收节点）、hop_events（模拟时刻）、delivery_status；计划链单独planned_path，不用它补实际路径。旧MID结果不改名为时延感知，历史页面照旧。

E1实际run_pair模块交付后薄适配，优先消费INDEX与每臂context/events/summary；无新raw时不编实际路径/收益。候选成本是单向传播+32B序列化，不是原MID SOCP目标。D按生产者字段适配；本卡仅8767软件，禁操作8766。
