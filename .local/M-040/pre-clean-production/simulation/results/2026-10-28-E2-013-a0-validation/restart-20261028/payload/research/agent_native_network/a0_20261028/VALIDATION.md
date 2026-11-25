# E2-013：A0独立核验最新结果

2026-10-28，用户批准恢复后的第二次核验。**新证据一致性核验通过；真实模型加载、图像张量与3次生成已有实证；严格JSON工具协议全部失败，A0整体验收仍未通过。** E2累计正式核验2/2次，无模型、下载、训练或仿真调用，交review停写。

## 当前冻结与旧快照

主卡记录M已通过read_thread核实用户在E1窗口直接“批准启动”，资源改善后允许人工恢复和一次额外资源检查，不增加worker/token/时间预算。[新冻结清单](../../../coordination/reviews/M-014-restart-freeze.json)SHA256 `2247e4f9200cd94cf3c2c2396ad430a87310a9e054e9d199ce443b673369b7b5`，994项执行前后hash全部匹配，覆盖15个run及两阶段归档。HEAD仍为`7f92debd36310a7d5e37ef52d23c019138284cdd`。

旧核验的“worker1、生成0、loading保护停止”是首次冻结时事实，原[首轮输出](../../../simulation/outputs/E2-013/20261028-01-frozen-a0/validation.json)、旧E1/E2归档及报告快照完整保留；本次新增证据使当前结论更新，不改写旧记录。原E2根归档manifest SHA256仍为`70327fecbd2e1f1bfb7f61555d1d06a74fb755babeaf02ea1bf82ee7474c2b07`。

第二次核验命令：

```powershell
python -B -X utf8 simulation/edge_agent_validation/validate_restart.py --freeze coordination/reviews/M-014-restart-freeze.json --output simulation/outputs/E2-013/20261028-02-user-approved-restart
```

目标目录运行前不存在，退出0。[公共manifest](../../../simulation/outputs/E2-013/20261028-02-user-approved-restart/manifest.json)保存源码/判据/卡/冻结输入快照；[自动结果](../../../simulation/outputs/E2-013/20261028-02-user-approved-restart/validation.json)1519项记录一致性检查通过、失败0。该数不是模型样本或实验性能。[适配依据](../../../simulation/edge_agent_validation/RESTART_ADAPTATION.md)、[独立判据](../../../simulation/edge_agent_validation/criteria_restart.json)和[源码人工复核](../../../simulation/edge_agent_validation/SOURCE_REVIEW_RESTART.md)另存；不导入E1模块、未重跑其37项工程检查。

## 三次生成：语义与严格工具协议分列

| worker / 私有输入 / 提示 | 原始输出（含前导空格） | 原定颜色词主评分 | JSON / 引用 | 加载段 / 生成 / worker墙时（秒） |
|---|---|---|---|---|
| 01，红图，v0，旧保护停止 | 无输出 | 未测 | 未测 | 未完成 / 0 / 33.203 |
| 02，红图，v0 | ` The dominant color is red.` | 正确 | 失败 / 无合法工具引用 | 3.688 / 1.859 / 29.672 |
| 03，红图，v1 | ` #FF0000` | 不通过：缺red/blue颜色词 | 失败 / 无合法工具引用 | 3.312 / 0.922 / 25.328 |
| 04，蓝图，v1，固定输入诊断 | ` blue` | 正确 | 失败 / 无合法工具引用 | 3.500 / 0.844 / 25.765 |

独立人工复核确认red/blue语义与像素相符；#FF0000的RGB含义是红色，但只作辅助解释，不事后提高预设主评分。所有输出严格解析失败，未修成JSON、未以宽松解析替代工具协议。两提示、红输入重复、蓝输入单次的结果不能写成泛化准确率，也不是独立协作回合。两输入实际执行不等于同时通过视觉+格式+引用的A0门槛。

## 预算、来源与测量口径

| 核对点 | 结论 |
|---|---|
| 累计预算 | 4次worker启动（含旧保护停止）、3次生成started且completed、113.96800000000803秒；每次≤256新token/180秒，累计≤720秒。启动名额已满，不再恢复 |
| 授权/预检/提示 | 唯一user_restart_authorized有M核实的用户来源及执行卡快照；累计3预检=原2+明确授权1。12新检查RAM5083320320 byte、VRAM7164MiB通过；14仅复用12记录。提示修订1次，旧保护事件保留 |
| 旧账本与归档 | 当前ledger以旧归档ledger原字节为完整前缀。旧E1归档296项payload不变；新208项增量归档与其当前来源/副本逐项一致。原E2归档17项payload不变；不强求已获批修改的当前报告/源码等于旧快照 |
| 来源/版本 | 固定revision、来源锁和13项身份记录一致；E2不重读2GB权重或导入模型env。12↔11、14↔13测试源码逐文件匹配。37项仅为保存的工程回归，未在本轮重跑 |
| 实际运行时 | 三次worker记录torch2.3.1+cu121、Transformers4.51.3、Pillow10.4.0、tokenizers0.21.1、hub0.30.2、safetensors0.5.3；不是控制器的旧包库存。Accelerate未单列本次版本，不猜填 |
| 输入/私有上下文 | 两PNG实解码红蓝64×64；每次只送一图，prompt无期望red/blue，context hash一致。实际pixel_values=[1,1,3,512,512]、mask=[1,1,512,512]、input_ids=[1,118]；不能写成64×64张量推理成本 |
| GPU放置 | 三次hf_device_map={'':'cuda:0'}、全参数cuda:0/FP16、参数体积1014964608 byte；真实加载已建立 |
| GPU峰值 | 加载期PyTorch已分配峰值1022361088 byte；生成已分配峰值1145682944 byte，保留峰值1166016512 byte。加载前和加载/预处理后分别重置；生成峰值含常驻模型+生成分配、排除加载瞬态，不是整卡占用 |
| RAM及回收 | 02/03/04最低系统可用RAM为2562977792/2756612096/2392031232 byte，最大采样间隔0.266/0.281/0.266秒；无新保护，均有wait回收和历史PID检查。系统可用量不是worker峰值或固定容量成功保证，E2未重新枚举全机 |
| 时延 | 上表加载段为worker记录的processor/模型加载段；总墙时另含解释器、导入、预处理和退出。三者不混用，不据3次兼容尝试作正式性能统计 |

旧03缺config_sha256、05/09/10辅助manifest后补及未知字段仍保留，不猜填、不覆写。核验范围含所有成功与失败、原始输出/采样及授权链。未发现需E1修复的证据矛盾；下一步研究问题是受约束工具JSON兼容，修复/换模型/运行时须另立明确预算，不能直接进入A1/A2或网络/协作性能评价。

## 交接与新增归档

第二次自动结果SHA256 `6616befc38fa75a634951e26d560de44043e553262b0eb739f82d91c0c22ec88`；执行manifest SHA256 `e8a6d2517c6087a2b0503c357d43ba78b383070aa821134da15ff0848d2da491`。新记录存于`simulation/results/2026-10-28-E2-013-a0-validation/restart-20261028/`，仅含E2第二次输出、脚本/判据/人工复核及本报告；旧根映射和payload不变，无模型/env副本。

本卡两次正式核验额度用完，所有E2命令已退出，无本窗口模型/下载/研究后台进程，无跨聊天发送、Git写操作或子代理。等待M冻结，再由D整合、C-015独立审查与M验收。
