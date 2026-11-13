# 控制台计划库

只规划，不开端口、不启动服务、不写实板、不改固件。E2负责同源HTTP/重复点击和运行状态，D负责UI，H独占串口；M-019实验占用时必须返回busy，不抢端口。

```python
from tools.mid_baseline.planner.console.plans import PlanLibrary
library = PlanLibrary()  # __file__定位仓库，不依赖服务的当前目录
catalog = library.list_models()
preview = library.plan({"src":"B", "dst":"E", "mode":"hops", "hops":3, "count":2})
```

返回`ok:false,error:{code,message}`或`ok:true`的可序列化计划。模型ID仅白名单`assumed-five-v1`，路径来自代码，客户端不能传文件路径。它是原五板实际求解过的假设模型（mean.8/variance.0001），不能冒充实时测量/当前邻接。`source_path/source_sha256/verified_scope/unit`随每个计划返回。M-019的有效测量模型尚未接入此目录，不能自动把不完整窗口当新模型。

请求必需src/dst为不同A..E、mode为mid/hops/manual；count1..10（默认1）。`node_set`可选2..5个节点，`graph_edges`可选有向正边子集。未给node_set时，若H传available_nodes且包含端点则使用该可用子集，否则全模型离线预览。graph_edges只表示操作者选定的逻辑输入图，不证明物理不可达；未包含的边不能出现在受控链中。

- hops：hops整数1..4，枚举恰好k条边的可行简单路径，取字母序首条。`chain/exact_hops`明确显示选择规则，生成每执行节点仅一个下一跳、weight1的控制表。TTL仍是上限，未用于假造固定跳数。
- manual：via为0..3个有序中继，不允许重复节点/端点/缺边；同样生成单链表。
- mid：懒加载原Planner与CVXPY，以本模型单流rate.05/qos.9求SOCP最大公共裕量，返回真实权重。node_set改变时取对应矩阵，操作者禁边时mean0/variance1显式逻辑惩罚；若求解后仍有禁边则拒绝，不事后修改概率。`chain/exact_hops=null`，不能把概率表标为唯一最优链。candidate_edges保留每行raw_weight、归一化概率和u16编码后概率。每500ms选一次下一跳并保持，不是逐包独立分流。可能有环/TTL到期；每包真实路线要靠日志，中继收/发与唯一目的rx_local关联。

H服务实时状态示例：

```python
live = {"busy": False, "ready_nodes": ["B","C","D","E"],
        "publisher": "B", "publisher_boot": 123, "run_available": True}
result = library.plan({"src":"B","dst":"E","mode":"mid","count":1},
                      available_nodes=["B","C","D","E"], live_status=live)
```

123只是文档占位，不能部署。缺少live、设备未就绪、忙碌、无有效publisher绑定均`availability.runnable=false`，仍可显示预览；状态不是从旧文件推断。required_nodes为受控链或MID源可达支持图涉及节点。publisher还必须在node_set和实时ready集合。H运行前再次核实际boot/build/baud和占用，原子获取独占租约，调用原bridge.pack生成新seq配置；模型预览不生成带假boot的可执行命令。新state改变后E2应重新核计划可执行性，不把旧runnable当永久许可。

E2生成服务端唯一plan_id，保存不可变计划；`plan_fingerprint`只是规范化内容指纹，不是认证、租约或一次运行ID。重复点击、1..10包上限、60s超时/停止排空、Host/Origin保护均由E2/H按M-020实现，库本身不触发任何业务。不得把本库的预期链/概率/solver optimal当成已发送或交付。

原始network_update兼容现有MID bridge，单流、N<=5，源/目的MAC绑定随结果返回。服务可用标准库解释器做hops/manual；mid使用现有`.local/mid/E1-016/venv/Scripts/python.exe`，不安装全局依赖。首次CVXPY导入约数秒，建议E2在线程/子进程执行plan而不是阻塞UI/串口调度。求解异常由服务返回明确错误，不能默默改成手工链并仍称MID。
