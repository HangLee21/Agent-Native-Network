# MOCHA / AutoCast 原组件核查

2026-10-23。归档自simulation/outputs/D-002/20261023-03，14项原AST函数/类探针全部符合给定输入下的预期。sources.json固定三个仓库版本及86份源码哈希；probe_results.json保留输入、输出、夹具、源行号、脚本与运行库来源；probe_source.py是当次脚本快照。

实测包括MOCHA六字节头部和最新记录筛选，AutoCast收益/大小排序、Beacon乱序覆盖、Data旧帧抛弃与同帧合并。AutoCast原发送循环在两份各60ms对象后停止，累计120ms；其Beacon序列化包含point_cloud_list，固定其他字段时10点653字节、1000点17483字节。这些是原组件在明确输入下的行为，未测完整协议、驾驶任务或无线竞争。

完整入口、依赖及数据可见性分析见 [运行报告](../../../research/agent_native_network/NETWORK_BASELINE_RUNTIME.md)，独立审查见 [C-002](../../../coordination/reviews/C-002.md)。恢复命令：

```powershell
python simulation/network_baseline_probe.py --source-root data/network_baselines --fetch-manifest simulation/results/2026-10-23-D-002-network-components/sources.json --output simulation/outputs/D-002/new-run
```

输出目录必须不存在。源码下载到data，不覆盖已有不匹配文件；ROS2/CARLA完整环境另行恢复。
