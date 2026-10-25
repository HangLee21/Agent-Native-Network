# E1-004 因果任务执行归档

阶段于2026-10-25开始，2026-10-26收尾；目录日期沿用任务启动日期。M在输出冻结后归档672份原始证据，原始约165 MB，压缩后约8.27 MB；原输出全部保留。逐文件原始/存储hash和压缩方式见[ARCHIVE_MANIFEST](ARCHIVE_MANIFEST.json)，排除的仅为可再生成Python字节码。

| 运行 | 回合 | 用途 |
|---|---:|---|
| `20261025-01-pilot` | 1 | 首个即时信息适配pilot，供E2固定业务回放 |
| `20261025-02-delay` | 30 | 9机器人、15/20任务各5种子，instant/0.5/2延迟主矩阵 |
| `20261025-03-fifo` | 15 | 15任务5种子，FIFO 2048/4096/8192字节/模拟时间 |
| `20261025-04-wait20` | 10 | 发现失败后，15任务全5种子instant/0.5延迟共同等待20的探索性诊断 |
| `20261025-05-epsilon` | 2 | seed2/3的极小正延迟定位；另存跨运行机制分析脚本与派生记录 |

58回合均正常退出，其中45成功、13到H=200未完成；所有初态与原复现归档一致。主45回合、后加敏感性、pilot及定点诊断分别解释，不能混算为独立泛化样本。报告见[执行器与实验结果](../../../research/agent_native_network/HETEROMRTA_CAUSAL_EXECUTOR.md)，阶段判断见[因果闭环与共享服务](../../../research/agent_native_network/CAUSAL_SERVICE_STAGE.md)。

每个run保存冻结源码、来源/权重hash、命令、环境和逐回合完整事件。大JSON以gzip存储，解压恢复原始字节；两次单测日志明确记录其来源。`.gitattributes`禁用本归档换行转换。

[结果图](figures/figure.png)、[矢量PDF](figures/figure.pdf)、[55回合图表数据](figures/source_data.csv)为归档后由M产生的派生分析，不属于原运行manifest；来源hash、数据剖析、图注及预览检查放在figures目录。绘图脚本见[复算入口](../../../coordination/reviews/M-006-plot.py)。
