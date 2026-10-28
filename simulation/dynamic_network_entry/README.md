# E2-011：ns-3.46 动态两跳 B0

该目录提供原生 ns-3.46 `AdhocWifiMac`、802.11a、AODV 的有界工程入口。它不运行历史项目仿真，不含模型推理，也不以直接时延队列替代无线栈。实际执行状态见[本轮报告](../../research/agent_native_network/preparation_20261028/NETWORK_ENTRY.md)及[主卡](../../coordination/tasks/E2-011.md)。

配置：3个节点；源0、转发1、目的2。动态场景端点间200米，单跳最大125米，初始两段各100米。中继在19–21秒从(100,0)移动至(100,400)，39–41秒返回。传播使用ns-3 Friis加Range截止；截止用于微场景连通性断言，并非实测无线覆盖半径。真实DCF、ACK/重试、传播时延、PHY误包和AODV共同决定交付，不向协议注入路由或图真值。

从5.0到59.5秒每0.5秒生成512字节UDP探测，共110条，SeqTs头包含在512字节中。该业务明确为合成工程探测，不冒称真实Agent需求。每条签发、socket结果、目的端收到/未收到都保留，末尾未收到不是自动判定丢包；2秒截止另外标记迟到。B0尚未实现请求修订、消费、应用ACK/重试、租约、DTN和模型反馈。

## 命令与边界

在仓库根目录运行，Python使用现有解释器，所有输出须是新路径。Linux也可用相同Python入口；Windows只用现有工具链，不安装WSL、MSYS2或依赖包。

```powershell
python -B simulation/dynamic_network_entry/network_entry.py preflight --output simulation/outputs/E2-011/<new-env-id>
python -B simulation/dynamic_network_entry/network_entry.py acquire --output simulation/outputs/E2-011/<new-source-id>
python -B simulation/dynamic_network_entry/network_entry.py build --output simulation/outputs/E2-011/<new-build-id>
python -B simulation/dynamic_network_entry/network_entry.py check --output simulation/outputs/E2-011/<new-check-id>
python -B simulation/dynamic_network_entry/network_entry.py run --mode smoke --seed 0 --output simulation/outputs/E2-011/<new-smoke-id>
python -B simulation/dynamic_network_entry/network_entry.py run --mode dynamic --seed 0 --output simulation/outputs/E2-011/<new-dynamic0-id>
python -B simulation/dynamic_network_entry/network_entry.py run --mode dynamic --seed 1 --output simulation/outputs/E2-011/<new-dynamic1-id>
```

这些命令说明恢复入口，不扩大本卡预算。若已有源码归档或工作树，`acquire`拒绝覆盖；不要把整段命令再次执行。初次Windows解压因两条文档symlink失败时，`extract`可从已保存归档继续；它仅跳过两个已列名的文档链接，不改源码或归档。`build`会保留此前本卡staging副本；仅复制本目录B0源到独占上游树的scratch文件，禁止指定其他checkout。

- 源码下载仅官方固定3.46归档，≤100MiB；保存URL、大小与实际SHA-256。没有独立发布方checksum时如实说明，不能把自算hash说成外部校验通过。
- 构建在`data/agent_native/E2-011/ns-3.46`，最多累计900秒，4个编译作业；不安装或全局修改PATH。关闭自动ccache，TMP/TEMP和可选ccache目录均在本卡data目录；CMake显式使用当前Python。
- Windows GCC13.2的标准头兼容参数为`-include algorithm`：解决上游`src/core/model/test.cc`缺少显式标准头引入的编译错误，不改上游文件，不改网络模型。实际构建日志保存完整参数。
- 子进程PATH优先放本卡build/lib与现有GCC目录，避免其他软件自带的GCC运行时先被加载；不改全局PATH。直接以argv启动已构建exe，并传相对输出路径：固定3.46的`CommandLineHelper::UserItemParse<std::string>`使用流提取，绝对工作区名中的空格会截断参数，单纯加引号不能解决。
- 模拟总预算：smoke seed0一次；dynamic seed0/1各一次，每次60秒虚拟时间，120秒墙时。启动即在`.reservations/`保留本次名额，失败也计数；新输出目录不能绕过名额。编译与日志fixture测试不计为模拟。不要删除reservation“补跑”。
- 本卡M后续明确追加两次原动态种子的启动修复检查，总尝试上限5。追加运行须显式加`--M-supplement`，另记`dynamic-0-M-supplement`和`dynamic-1-M-supplement`保留项；不增加单跳名额。五个名额当前均已使用，前三次前置启动失败、后两次动态运行通过。该例外来自主卡，不能推断以后自动补跑。
- 每个run沿公共manifest记录当前Git/dirty文件hash、解释器、配置、源码、命令、退出及产物hash。Python checker通过只说明日志约束检查成功，不能单独证明ns-3构建或无线实验成功。

## 观察与独立核对

`raw/events.jsonl`记录应用签发/socket接受/接收、IPv4实际转发和目的端TTL、PHY每次发射及TX状态时长、中继位置和观察标记。`raw/wifi-*.pcap`是旁路核查材料，不被路由协议读取。`verification.json`从已存日志检查：

1. 110个源序号/尺寸/发布时间与socket结果一一对应；收到的消息必须存在且被接受，无重复/未来因果。
2. 全部签发=socket拒绝+唯一收到+接受但窗末未收到；后者保留完整序号和截止，不藏失败。
3. 动态场景每份成功交付TTL反映两跳，且有中继1的实际`UnicastForward`记录；不凭离线距离声称已走多跳。
4. 中继远离的安全检查窗[22,38]不得有目的端收到；恢复后从42秒起至少三份新生成探测实际收到。观察标记不触发路由重置。
5. PHY `PhyTxBegin`与同节点同开始时刻的TX状态一一配对；802.11a无聚合/MU，分类累计实际AODV、应用、ARP、MAC控制等每次发射费用。重试重复计费，PHY空口不是用固定bitrate估算。

这是一份UDP端到端收支和路径/控制费用核验，不是所有内部IP/MAC队列逐项重建或稳态容量证明。尚未收到的队列/丢失去向不强行猜填；更细Drop/队列追踪可另卡扩展。成功PHY发射尝试也不自动等于下一跳完整交付，成功应用路径由接收和IPv4记录确认。

`test_network_entry.py`中的合成日志只检查核验器会拒绝分区穿透、缺少转发、未恢复、虚假结束、漏记发送或时长等错误。这些fixture不属于B0无线运行，也不提供任何网络性能数据。
