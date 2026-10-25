# Data profile: simulation/results/2026-10-25-E1-004-causal/figures/source_data.csv

**Shape:** 55 rows × 17 cols

## Columns

| Column | Type | n | missing | summary |
|---|---|---|---|---|
| `tasks` | ordinal | 55 | 0 | 2 levels: 15(40), 20(15); min_group_n=15 |
| `seed` | ordinal | 55 | 0 | 5 levels: 0(11), 1(11), 2(11), 3(11), 4(11); min_group_n=11 |
| `condition` | categorical | 55 | 0 | 6 levels: instant(15), delay0.5(15), delay2(10), fifo2048(5), fifo4096(5) +1 more; min_group_n=5 |
| `task_wait` | ordinal | 55 | 0 | 2 levels: 200.0(45), 20.0(10); min_group_n=10 |
| `success` | boolean | 55 | 0 | 2 levels: 1(44), 0(11); min_group_n=11 |
| `status` | categorical | 55 | 0 | 2 levels: success(44), horizon_incomplete(11); min_group_n=11 |
| `completion_fraction` | boolean | 55 | 0 | 2 levels: 1.0(44), 0.0(11); min_group_n=11 |
| `makespan_return` | continuous | 44 | 11 (20%) | mean=27.2, sd=6.92, range=[15, 50.8], skew=0.78 (moderately skewed); outliers=1 (IQR) |
| `capped_makespan` | continuous | 55 | 0 | mean=61.7, sd=70, range=[15, 200], skew=1.43 (highly skewed); outliers=11 (IQR) |
| `messages` | continuous | 55 | 0 | mean=198, sd=108, range=[27, 433], skew=-0.05 (approximately symmetric) |
| `application_bytes` | continuous | 55 | 0 | mean=6.14e+04, sd=3.38e+04, range=[7.58e+03, 1.35e+05], skew=-0.05 (approximately symmetric) |
| `delivered` | continuous | 55 | 0 | mean=191, sd=101, range=[27, 418], skew=-0.06 (approximately symmetric); outliers=1 (IQR) |
| `pending` | continuous | 55 | 0 | mean=7.2, sd=25.4, range=[0, 137], skew=4.13 (highly skewed); outliers=7 (IQR) |
| `dropped` | boolean | 55 | 0 | 1 levels: 0(55); min_group_n=55 |
| `latency_p95` | continuous | 55 | 0 | mean=1.45, sd=3.26, range=[0, 18.6], skew=3.87 (highly skewed); outliers=3 (IQR) |
| `initial_sha256` | categorical | 55 | 0 | 10 levels: f233e57b9a76975e845c5749520874a882cfb1596d2bcb632a9f08ddc06e262c(8), 471bdf5a5e19d7399eadc13519a3a54e8ef5751f09fabd7df8103355b775c83f(8), 60e9103ba15cd4192e1b7527007fd990bbc82814e26eaca3833e1f734b12febf(8), c4d96d8f4d62e3fbacc695d6c198f4eb03620f7edcb693bf1b297e42141653be(8), 920123a50a06092d79d349336492fc937140b8bdf477c0282920d5ff33dc0ee8(8) +5 more; min_group_n=3 |
| `source_case` | text | 55 | 0 |  |

## Group structure
- Grouped by: `tasks`, `task_wait`, `condition`
- Number of groups: 11
- Group size: min=5, median=5, max=5
- **WARN**: at least one group has n<10 — use box/violin + stripplot rather than mean-only bar chart.

## Correlations (Pearson, sorted by |r|)
- `makespan_return` ↔ `capped_makespan` : r = 1.000 (very strong)
- `messages` ↔ `application_bytes` : r = 1.000 (very strong)
- `pending` ↔ `latency_p95` : r = 0.954 (very strong)
- `application_bytes` ↔ `delivered` : r = 0.933 (very strong)
- `messages` ↔ `delivered` : r = 0.931 (very strong)
- `makespan_return` ↔ `messages` : r = 0.748 (very strong)
- `capped_makespan` ↔ `messages` : r = 0.748 (very strong)
- `makespan_return` ↔ `application_bytes` : r = 0.747 (very strong)
- `capped_makespan` ↔ `application_bytes` : r = 0.747 (very strong)
- `makespan_return` ↔ `delivered` : r = 0.708 (very strong)
- ... +11 more pairs

## Warnings
- 列 'condition' 至少有一个类别 n<10 — 小样本必须展示原始数据点，不要只画均值柱状图。
- 列 'initial_sha256' 至少有一个类别 n<10 — 小样本必须展示原始数据点，不要只画均值柱状图。

## Chart suggestions (preliminary)
- 分类 vs 连续，小样本（每组 n<10）→ **箱线图/小提琴图 + stripplot 叠加原始点**；**避免**只画均值柱状图，会掩盖分布。
- ≥3 个连续变量 → 相关性热力图（['makespan_return', 'capped_makespan', 'messages', 'application_bytes', 'delivered']）或 pairplot 散点矩阵
- 分类维度组合数 = 9600（tasks, seed, condition, task_wait, success, status, completion_fraction, dropped, initial_sha256 全交叉），**一张图塞不下**——建议按某一维拆成多面板，或选择子集。
- capped_makespan 高度偏态（skew=1.43）→ 考虑对数变换或小提琴图代替均值柱图
- pending 高度偏态（skew=4.13）→ 考虑对数变换或小提琴图代替均值柱图
- latency_p95 高度偏态（skew=3.87）→ 考虑对数变换或小提琴图代替均值柱图

> 这是基于数据形态的**初步建议**。最终图型选择必须结合**论证目标**（你想说什么）—— 详见 `references/chart-selection.md`。
