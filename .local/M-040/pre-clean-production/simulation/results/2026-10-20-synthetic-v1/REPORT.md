# 首轮任务级仿真自动摘要

数据类别：**synthetic**；24 个配对随机种子；336 次运行。所有策略均终局汇总观测。

指标为固定留出位置的光谱预测 RMSE，越小越好；不是矿物识别或找矿成功率。
区间是种子自举的描述性 95% 区间，不表示实地总体置信度。

| 先验 | 条件 | 平均 RMSE | 平均采样数 |
|---|---|---:|---:|
| strong_prior | static | 0.010281 | 35.12 |
| strong_prior | local | 0.010307 | 33.62 |
| strong_prior | ideal | 0.010326 | 34.92 |
| strong_prior | good | 0.010326 | 34.92 |
| strong_prior | intermittent | 0.010324 | 34.71 |
| strong_prior | stress | 0.010310 | 33.75 |
| strong_prior | disconnected | 0.010307 | 33.62 |
| strong_prior | prior_only | 0.009990 | 0.00 |
| coarse_prior | static | 0.027400 | 37.08 |
| coarse_prior | local | 0.027519 | 35.71 |
| coarse_prior | ideal | 0.027554 | 36.42 |
| coarse_prior | good | 0.027554 | 36.42 |
| coarse_prior | intermittent | 0.027494 | 36.29 |
| coarse_prior | stress | 0.027514 | 35.71 |
| coarse_prior | disconnected | 0.027519 | 35.71 |
| coarse_prior | prior_only | 0.026994 | 0.00 |

配对差值按前者减后者；负值表示前者误差较小。

| 先验 | 对照 | 平均差值 | 描述性区间 |
|---|---|---:|---|
| strong_prior | ideal minus static | 0.000046 | [-0.000010, 0.000107] |
| strong_prior | ideal minus local | 0.000019 | [-0.000031, 0.000069] |
| strong_prior | good minus ideal | 0.000000 | [0.000000, 0.000000] |
| strong_prior | intermittent minus ideal | -0.000003 | [-0.000040, 0.000036] |
| strong_prior | stress minus ideal | -0.000016 | [-0.000065, 0.000033] |
| strong_prior | disconnected minus local | 0.000000 | [0.000000, 0.000000] |
| strong_prior | static minus prior_only | 0.000290 | [0.000230, 0.000346] |
| strong_prior | local minus prior_only | 0.000317 | [0.000258, 0.000377] |
| strong_prior | ideal minus prior_only | 0.000336 | [0.000282, 0.000399] |
| coarse_prior | ideal minus static | 0.000154 | [0.000013, 0.000288] |
| coarse_prior | ideal minus local | 0.000035 | [-0.000110, 0.000179] |
| coarse_prior | good minus ideal | 0.000000 | [0.000000, 0.000000] |
| coarse_prior | intermittent minus ideal | -0.000060 | [-0.000138, 0.000009] |
| coarse_prior | stress minus ideal | -0.000041 | [-0.000188, 0.000113] |
| coarse_prior | disconnected minus local | 0.000000 | [0.000000, 0.000000] |
| coarse_prior | static minus prior_only | 0.000406 | [0.000302, 0.000537] |
| coarse_prior | local minus prior_only | 0.000525 | [0.000365, 0.000715] |
| coarse_prior | ideal minus prior_only | 0.000561 | [0.000446, 0.000681] |

尚无应用依据支持实质收益阈值；本轮不作问题存在或算法优越性的判定。
完整参数见 metadata.json；全部运行见 metrics.csv；种子 0 时序见 trace_*.jsonl。
