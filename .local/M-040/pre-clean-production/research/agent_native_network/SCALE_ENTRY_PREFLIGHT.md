# 配对规模目录与原策略单步检查

2026-10-26，E2-006。按照[需求驱动研究链条](DEMAND_DRIVEN_RESEARCH_CHAIN.md)的扩展入口，从任务与设备数量生成配对输入。本轮完成10个目录和20次初始策略前向检查，未执行完整任务回合，未加入网络延迟或竞争。

## 配对构造

每个种子5、6分别调用固定作者TaskEnv生成一次9节点、60任务的主目录，保存完整原始initial及用于因果执行的catalog。作者版本为`db51e29535e34bcaa8cb75f70be3fd28b0027988`，能力维度5，3种能力类别各3节点，decision_dim=30；其余采用作者默认生成规则。源码及权重经过既有asset_manifest校验。

在同一个主目录上取任务前缀，并复制完整9节点能力配置：

| 配置 | 固定15总任务 | 固定每节点5/3任务 | Task特征形状 | Agent特征形状 |
|---|---|---|---|---|
| 9节点/15任务 | 共同起点 | 共同起点 | 1×16×15 | 1×9×11 |
| 18节点/15任务 | 是 | — | 1×16×15 | 1×18×11 |
| 36节点/15任务 | 是 | — | 1×16×15 | 1×36×11 |
| 18节点/30任务 | — | 是 | 1×31×15 | 1×18×11 |
| 36节点/60任务 | — | 是 | 1×61×15 | 1×36×11 |

每族6个实例，两种子各自共享9/15起点，因此总计10个独特配置。新增节点ID为9–17、18–35，节点i的能力、species、驻地和速度严格复制主目录i mod 9，原0–8不变。任务ID、位置、需求和服务时长取主目录对应前缀，不重新生成。面积沿用作者坐标范围；所有配置的共同初始catalog仍免费已知。

这是固定能力构成的数量扩展。复制设备不增加新的平台类型，也没有新传感正文或动态能力发现。60任务主目录生成后截取前缀，和直接调用作者生成15任务的随机过程不同，本轮不与旧种子0–4的任务实例混作配对。

## 本机验证

[生成器](../../simulation/heteromrta_scale_catalog.py)逐目录校验任务前缀、原9节点、追加副本及能力总量可行性。然后用旧`LocalView`构造时刻0观测，加载固定原权重，分别调用actor0和最后一个actor。只检查输入/输出形状、数值有限、选中动作未被mask，不推进状态。

- 10/10配置通过，20/20次前向产生合法动作。
- 每个配置单独子进程，墙时上限30秒；实际4.55–15.59秒，含模块导入和权重加载。
- 使用CPU单线程、`net.eval()`与`torch.no_grad()`，没有训练或GPU计算。
- [5项结构测试](../../simulation/test_heteromrta_scale_catalog.py)通过：前缀/保留ID、副本独立、JSON数值ID排序、非法输入拒绝、两族共享原点。终版日志来自实际测试命令，保存在输出目录。
- 全任务表现、超时和规模下的业务量由E1-006独立执行；初始前向通过只证明入口可执行。

固定权重SHA-256：`7cb4ab4fdaea750e52132e65481024b1c123252221a70b0336f839abfe7ccf5a`。36节点/60任务检查通过不证明权重在该规模已达到良好任务性能。

## 复现与交接

原始输出：`simulation/outputs/E2-006/20261026-01/`，共2主目录及10配置。输出只允许创建新的子目录；任何已有目录拒绝覆盖。失败或进程超时也会保留在索引中。本轮没有失败配置，所有子进程已退出。

命令（仓库根目录；重做时必须使用新的run-id）：

```powershell
.venv/Scripts/python.exe -X utf8 simulation/heteromrta_scale_catalog.py --output simulation/outputs/E2-006/<new-run-id> --timeout 30
.venv/Scripts/python.exe -X utf8 -m unittest simulation.test_heteromrta_scale_catalog -v
```

`catalog_index.json`包含`cases`数组，每项提供case_id、seed、agents、tasks、families、catalog_path、文件SHA-256、规范化内容SHA-256、master SHA及probe结果。文件中的绝对路径记录本次运行位置；跨机器恢复时以归档相对目录定位并核对文件hash。E1按目录文件hash复制后使用，不从参数重新生成。

| 交接文件 | SHA-256 |
|---|---|
| catalog_index.json | `dae5db475be0a5c62c810943f71fc743db70cfadd970194cc44ac0604ae54b93` |
| manifest.json | `594041eb46aaa14f8e8275e5eb43b23ac9ebb408fdd73063bd7dc436d36f09b1` |
| heteromrta_scale_catalog.py | `b189bc366f0cb16c04b4e7dc9c49a434c4f73253206ac3eea4d3efd314b0c60d` |
| test_heteromrta_scale_catalog.py | `719a4abd5814d4e8946ab70624c78479a088d71ee34aa9af0facdaa363fbf813` |
| unit_tests.log | `5e89ac0615d22bc89948a1de22f1530e8d9243fb53d152ec23ed28687fde536c` |

manifest在生成与探针前保存作者资产、脚本快照和范围，逐配置补入命令与结果；最终版本已冻结交付E1和C。原始initial保留TaskEnv生成的全部字段，目录只含执行器所需tasks/agents，两者映射可独立重建。

任务规模增长产生的任务事件和维护业务，将在相同执行规则下实际运行后统计。当前没有无线服务结果，也未测出规模边界。
