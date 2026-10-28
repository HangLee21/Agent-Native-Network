# E2-013独立A0核验入口

2026-10-28。准备依据为提交`7f92debd36310a7d5e37ef52d23c019138284cdd`中的旧入口、MODEL_CHAIN、NETWORK_CHAIN、S03和新任务卡；准备期间不读E1活动新代码或输出。验证器只用Python标准库，不导入E1模块、不执行worker、不读权重或环境。

先冻结判据，等M给版本后再运行。`criteria.json`将真实生成、JSON/工具合法性、颜色语义分列；红蓝预期来自预定像素，不从模型答案反推。词汇筛查只是保守初筛，有否定、多色、非finish或非JSON时标人工待核，不用猜测补成功。两输入都通过才可确认有限视觉/工具兼容；失败保留，不计算协作性能或泛化准确率。

M冻结需明确：E1已停写；冻结版本/时间；所有本轮成功失败运行目录；累计worker账本；源码、配置、执行卡、来源锁、输入PNG、spec、process、result、summary、manifest、stdout及失败记录的逐文件SHA-256。不能只给成功run或当前活动路径。准备的冻结描述格式如下（示例占位，不能直接运行）：

```json
{
  "schema": "E2-013-M-freeze/1",
  "frozen_by_role": "M",
  "target_task": "E1-012",
  "frozen_at": "M填写",
  "version_reference": "M冻结记录路径或提交",
  "all_attempts_included": true,
  "files": {"simulation/outputs/E1-012/实际run/manifest.json": "实际SHA256"},
  "runs": ["simulation/outputs/E1-012/实际run"],
  "ledger": "data/agent_native/E1-012/a0_attempt_ledger.jsonl"
}
```

运行形式：`python -B simulation/edge_agent_validation/validate_a0.py --freeze <M冻结JSON> --output simulation/outputs/E2-013/<不存在的新run目录>`。没有M冻结时不运行，不消耗核验次数，也不后台等待。最多两次正式核验；第二次须脚本/判据修订及说明，首轮原字节保留。冻结协议如与E1实际布局有差异，先记录适配再执行，不能靠静默别名绕过缺证据。

验证器先将本轮自身源码、判据、主卡、冻结配置和公共manifest模板快照写入新目录，再逐项核冻结输入。冻结hash不符或输入不全时以不通过/未建立报告，不能用E1 summary替代原始worker。允许读取的E1输入仅限M逐文件列出的新输出、归档、新data目录和必要源码/卡/锁；每文件≤20MiB、合计≤100MiB，防止意外读取模型。结果保留文件哈希，执行前后复核防止观察过程中改动。

脚本覆盖：PNG CRC/IDAT/滤波及实际RGB；spec中context哈希、私有证据/无其他节点图像、prompt无颜色真值泄露；worker身份/revision/实际张量/生成与token；严格JSON/字段与本地引用（独立实现）；process/summary/manifest交叉计数；所有worker启动与ledger/墙时预算。自动报告不能替代对冻结控制器/worker源码的人工检查，特别是实际调用、上下文绑定、离线加载、启动门槛、提示修订和失败保留。

权重身份沿已验收来源锁与取得清单核声明关联，不在本卡重读2GB权重，也不重新检查环境导入。资源门槛依执行时inventory/result及冻结源码核对，不用核验时的空闲资源替代。GPU峰值只解释为worker记录的测量区间。归档待核验完成后按任务卡范围保存，不重写E1原始文件。
