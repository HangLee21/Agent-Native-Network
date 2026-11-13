# D-020 接入点

首页默认新routing模式，可选src/dst/hops(null或1–4)/both_directions。模式选择保留原MID及旧运行，不改原算法标签。H routing.catalog/get_defaults生成routing-catalog.json的精确预设与范围，旧catalog.json只供MID模式。

按E2 ROUTING_CONTRACT：GET presets/defaults带mode=routing或mid；POST /api/plan {settings,time_s}查看0/干预中/恢复时的假设候选；POST /api/run按schema分派。候选只描述假设图，不用于实际路径。实际表从result.packets（数组或逐臂字典）或arms[].packets取packet_id/generated_s/received_s/actual_path/delivery_status；原MID无这些字段仍可看旧回放。每臂单列干预前接收链及干预后首个不同目的接收链，原始冻结JSON保留hop_events时刻。

当前服务未宣告routing catalog时，新模式禁发并提示升级后重载；原MID仍能用。D不启动/升级服务，不碰8766。后续浏览器验收消费新服务和已有实际输出，原阶段结果不重复运行。

已兼容arm=fixed/latency_aware，曲线按result.seconds实际非fixed键绘制，不再假定adaptive。首页展示每臂接收包平均模拟耗时；逐包表显示生成秒、收到秒、模拟耗时ms、实际接收链和交付状态，干预前/首次不同实际接收链及源config_install生效时刻另列。reset恢复新routing整套默认（不启动），MID模式和旧历史仍可选。

8767升级已确认，前述服务未接入阻塞已解除。D已从正常入口完成断链和升时延两场：20261107-220941-5b3809dffc02、20261107-221214-8701b0ab9ba1；实际结果和默认复位证据见D-020任务卡及02-browser-acceptance。新UI JS语法检查通过，未启动额外矩阵/硬件。已保存交接，待C/M独立审查。

D-020收尾：默认/切预设优先选已连接的干预边（两跳BC、三跳BE），无干预选AB，方向选项同步；结果链接及逐包策略/状态改为中文，原始ID保留在raw。只读浏览器复位与保存结果核对通过，新增仿真0，历史集合不变。证据simulation/outputs/D-020/20261107-03-ui-finish/；先前两场实跑证据保留。
