# HeteroMRTA 原策略与作者 Greedy：本机小实例评估

2026-10-23，E1-002。作者提交固定为 `db51e29535e34bcaa8cb75f70be3fd28b0027988`。

已恢复作者权重并完成 CPU 推理；9 机器人、15/20 任务两组各 5 个配对种子。结果采用 `simulation/outputs/E1-002/20261023-02/` 和 `20261023-03/`，每个策略均保留所有尝试。`20261023-01/` 是先行入口检查，保留其代码快照，不重复计入统计。`20261023-04/` 是下述 Greedy 单行修改的失败诊断。

正式归档：[结果与解释](../../simulation/results/2026-10-23-E1-002-heteromrta/INTERPRETATION.md)，含02/03正常运行、04失败诊断及归档哈希清单。独立审查：[C-002](../../coordination/reviews/C-002.md)。

## 实际结果

| 条件 | 策略 | 成功/尝试 | 完成任务比例 | 返回驻地 makespan 均值 | 失败/超时 |
|---|---|---:|---:|---:|---:|
| 9 机器人、15 任务 | 原权重，argmax | 5/5 | 全部 1.0 | 21.408737 | 0/0 |
| 9 机器人、15 任务 | 作者 Greedy | 5/5 | 全部 1.0 | 24.030662 | 0/0 |
| 9 机器人、20 任务 | 原权重，argmax | 5/5 | 全部 1.0 | 25.900583 | 0/0 |
| 9 机器人、20 任务 | 作者 Greedy | 5/5 | 全部 1.0 | 32.299929 | 0/0 |

每次成功运行均有 9/9 机器人返回驻地，仿真结束时间不超过 200。15 任务下策略在 4/5 个实例上更快；20 任务下为 5/5。均值之比对应的降低分别为 10.91% 和 19.81%。这是小样本实现对照，当前差距包含两种作者入口的规则差异和下述 Greedy 实现问题。

两组种子均为 0–4，使用作者随机实例生成器，3 个物种、每物种 3 机器人、5 维能力、decision_dim=30，默认位置、速度、任务需求和作业时长分布。每个种子两策略重新生成同一实例；`initial.json` 的 SHA256 在两策略间完全一致。未使用作者 RALTestSet 的 pickle 测试集，因此不是论文表格数值复现。9/20 接近论文小规模机器人/任务数量，但能力维度遵循公开权重的 5 维接口，而不是把论文中 3 维设置混入比较。

`makespan_return` 仅在全部任务完成且全部返回时取仿真结束时间；另存 `last_task_finish`。例如 15 任务 seed=0，策略最后任务结束于 16.471094，返回驻地结束于 22.391610。所有动作原 mask 为可行，正常运行最大动作数为 50。

## 入口和实现发现

入口为 [`simulation/heteromrta_eval.py`](../../simulation/heteromrta_eval.py)。原策略调用 `Worker.run_episode(False, False, False)`，与作者 `test.py` 的非采样测试一致，使用 `best_model`、argmax、`max_waiting=False`。作者 Greedy 直接调用 `TaskEnv.execute_greedy_action(plot_figure=False)`，其 `max_waiting=True` 会在等待任务过多时增加 mask 限制。两者共享原始全局即时状态可得性，但保留各自原算法的 mask/调度配置。作者推理入口与训练 CFM 分开，不运行训练。

作者 `env/task_env.py:728–738` 将 `dist` 置为无穷，但在发现更近候选后只更新 `action`，未更新 `dist`。因此该版本实际上选择遍历中最后一个未屏蔽的候选，不能把它解释成标准最近任务 Greedy。

为明确这是否只是单行修复问题，04 在内存中只增加 `dist = dist_`，原文件字节不变。seed=0 在仿真时间 0 重复选择驻地，10,000 次动作后达到独立动作预算，完成 0/15。原因是原 mask 允许驻地，初始驻地距离为 0；仅修正距离最小化会留在原地。这一失败保留完整事件和最终状态，标签为 `corrected_nearest` 诊断，不能作为已修好的 baseline。下一步应单立任务规定回站条件、无可行任务时的等待行为，审查后再评价。

原 `worker.py` 的 300 动作计数只在训练分支自增，测试分支无此保护。新入口用每实例 60 秒墙钟限制和 10,000 动作预算约束执行，不改原成功轨迹。失败、仿真超期、墙钟超时和动作预算耗尽分别保留，墙钟超时若没有最终状态则完成比例记为未知。正常 20 次评估均未触发保护。

## 来源、环境与恢复

源码和 38,361,491 字节 checkpoint 来自[作者固定提交](https://github.com/marmotlab/HeteroMRTA/tree/db51e29535e34bcaa8cb75f70be3fd28b0027988)。下载路径、每文件 SHA256 与 Git blob 均在每组 `manifest.json` 中；已有筛查清单的五份文件 SHA256 全部匹配。原始文件保存在忽略目录 `data/heteromrta/upstream/`，不提交权重和环境。

本机 Python 3.11.5；`.venv` 通过 `--system-site-packages` 复用 `C:/environment/python3.11/`，没有安装新包。实测 NumPy 1.26.4、Torch 2.3.1+cu121、SciPy 1.14.1、Matplotlib 3.7.5，实际推理在 CPU，Torch 线程数为 1。模块绝对路径存 manifest，完整 `pip freeze` 存 02 的 `environment_freeze.txt`；最小版本清单见 [`heteromrta_requirements.txt`](../../simulation/heteromrta_requirements.txt)。NumPy 1.26.4 可运行原标量转换，本轮原 baseline 无兼容补丁。

Torch 2.3.1 的 `weights_only=True` 无法读取权重包中的 NumPy scalar 元数据。入口改用仅允许原权重实际包含的六个 globals 的受限 Unpickler，再提取 `best_model` 并严格加载全部 state_dict 键。禁止任意 global 的测试及非空输出目录保护测试均通过，日志在 02 的 `safety_tests.log`。没有使用一般的无限制 pickle 加载。

新 clone 的恢复命令（网络访问需可用）：

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r simulation/heteromrta_requirements.txt
.venv/Scripts/python.exe -X utf8 simulation/heteromrta_eval.py --fetch
.venv/Scripts/python.exe -m unittest simulation.test_heteromrta_eval -v
.venv/Scripts/python.exe -X utf8 simulation/heteromrta_eval.py --output simulation/outputs/E1-002/<new-run-id> --tasks 15 --timeout 60
.venv/Scripts/python.exe -X utf8 simulation/heteromrta_eval.py --output simulation/outputs/E1-002/<another-new-run-id> --tasks 20 --timeout 60
```

`--fetch` 下载固定文件并校验 Git blob 和已有 SHA256；每次运行保存新 manifest、脚本快照、每实例输入与最终状态、动作/mask、stdout/stderr、结果、配对 CSV 和摘要。输出目录必须为空。正式两组及诊断的脚本 SHA256 为 `baaa9c84f2fc8e93f9f2b20fe0441d22259bc1e89f0753d17d1548147663aa14`，运行期间未更改脚本。

执行计时与加载/建网计时分列；15/20 任务下策略平均执行约 0.261/0.317 秒，作者 Greedy 约 0.031/0.043 秒。它们含审计记录和原环境操作，后两组曾并发运行，不用于精确计算效率排名。

## 网络研究下一步

本轮确认任务执行器和原策略可运行，并定位到具体的 Greedy 回站/候选选择问题。通信接口接入时，远端任务剩余能力、组队状态、同伴状态与动作 mask 必须共同由实际送达的信息决定；保留同策略同规模即时信息运行用于归因。网络空口成本、控制开销、有效交付及尾时延在本轮未建模，均为 N/A，不能记为零。扩展性曲线及学习适应性仍需后续实验。
