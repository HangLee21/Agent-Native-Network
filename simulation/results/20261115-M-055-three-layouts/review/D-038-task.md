# D-038 | 三模式拓扑布局
状态 done，负责人D，主卡M055。先读主卡与角色；主卡定义具体要求/范围/验收。独占生产app/services/assets/mobile_gateway/**和README.md、本卡及simulation/outputs/D-038/**。实现清晰布局、手动拖节点并保存/重置、严格GPS布局；不要保留三个名称却共用旧格点。自动布局有界且缓存，手动坐标与GPS隔离，来源隔离。沿用现有静态前端，不后台/硬件/服务/Git。一次完成必要隔离浏览器测试与截图，冻结后回填review、证据、hash及进程状态，交M验收。

## 交审（2026-11-15）

生产起点 `3d9765b689121a0dbbd54f9c09b8fe374e6653ae`；修改 README.md、assets/mobile_gateway/index.html、studio-model.js、view.js。默认清晰布局按实际连接划分簇/孤立点，选择节点将一跳邻居排列在周围；仅成员、连接或选择变化时重算，年龄/状态刷新不重排。手动模式可拖单节点，背景仍可平移；坐标按网页网关及 Wi-Fi/LoRa 来源身份分开保存在浏览器 localStorage，刷新/模式切换保留，可重置，新节点不挪已有位置。GPS模式仅绘制有效坐标并注明未定位数，节点列表仍可查缺坐标成员，不回退拓扑。切换来源时适配视野而不迁移手动坐标；无后台、协议或硬件变动。

最终证据 `simulation/outputs/D-038/20261115-08-final/`：真实无头Chrome与合成回环数据，截图包含5节点、30节点分簇/稀疏/密集及选中邻居、手动拖动和2个有效GPS/28个未定位。实际鼠标在两次缩放和平移后拖动70×35 CSS像素，断言对应SVG坐标误差小于2且其他节点不动；验证周期更新、模式切换与刷新后的保存值、LoRa A/B隔离、手动重置、新节点加入原节点不挪、GPS不改手动数据。RESULT.json、check.py、截图、RUN_MANIFEST.json、PROCESS_END.json同目录；fixture线程退出，无页面异常。01–07为保留的逐次诊断与回归，不作现场数据。

最终 SHA-256：view.js `0c6ebc4b6536bd9d1bc68e76bd0fdf6640e341a1c42f662403ee544a0f723b9b`；studio-model.js `ec8ee28b021c4b8b13093c4663dc15d17339387f2736c7ffe89a01fe144aa8f9`，其他文件见最终清单。node语法和D范围 diff --check 通过。数据与布局表现为本机合成演示，不代表实机网络或RF性能；未操作正式服务、设备或Git。请C-040对冻结版本窄审。

2026-11-15 M验收完成：生产d27bb3e，D038最终08浏览器证据及C040窄审已采纳；仅界面验证。写入范围释放，未操作设备/正式服务。采纳目录simulation/results/20261115-M-055-three-layouts/。
