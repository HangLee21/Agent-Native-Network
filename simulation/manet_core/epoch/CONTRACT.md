# v3 实验分支覆盖说明

本分支将线协议版本改为 3 并提供 `ma_set_boot`；不得与下文 v2 帧互通。boot epoch 的严格假设和未覆盖项见同目录 README.md，下文其余 ABI 仍适用。

# M-037 共享节点与实验接口 v0.1

范围：实验适配 ABI，不是 RFC 3561 IP/UDP 线协议，也不兼容旧 v1 帧。30 节点起测，可扩展至 40；环境只能把本地收到的帧及链路发送回调交给节点，不能把真实邻接图或未来轨迹交给协议。

## C 主机适配 ABI

`host_new(unsigned id,int policy)` -> opaque node；`host_free(node)`；单调时间单位 ms。`host_submit(node,dst,seq,payload,len,t)` 返回 0 成功，其余拒绝；`host_receive(node,previous_hop,frame,len,t)` 返回状态；`host_service_flags(node,t)` 推进定时器并返回 bit0 有事件、bit1 有待发帧。`host_next(node,t,buf,&next,&type)` 弹一个帧并记录单个在途帧，返回长度；next=-1 为广播，type=3 为业务，其他为控制；节点一次只允许一个在途帧。环境最终调用 `host_result(node,success,t)`；广播 success 表示本地提交完毕，不代表接收。`host_event(node,uint32[8],payload)` 弹事件，分别为 type、reason、origin、boot、sequence、destination、request、payload_length；type 6 为目的端收到。event 队列溢出使统计无效。

兼容冻结 engine_v2 所需 `host_hello/host_nd/host_sync_unlimited/host_sync_changed/host_peer_access/host_stats`；无邻居协议者 hello 返回 0，必须作为公平性差异报告。peer_access 模拟 20 项（含广播）有界 LRU，添加/删除时间与失败仍属未经测量的模型假设。`host_stats` 为旧事件队列/核心溢出等字段，具体在核心说明中报告。

## 帧与事件

本轮 Wi-Fi wire version 2，仅新实验使用；显式魔数、版本、类型、总长度、TTL、源/目的节点、源 boot、业务序号、RREQ id、路由序号/跳数。帧由核心序列化，避免依赖 C 结构体布局或本机端序；未知版本、长度错误、节点越界、超 250 B 和 TTL 用尽拒绝。每个协议按自己实际序列化长度计入 airtime，不允许隐藏免费控制帧。业务身份为 `(origin_id,origin_boot_id,seq)`；仅目的节点真实收包记录 `destination_received`，MAC callback 不是端点确认。依现有 engine_v2 的 `offered` / `admitted` / `destination_received` / `deadline_outcome` JSONL；原因标签是观测事件，不自动构成互斥的逐包丢失归因。

基线先使用有限数组、有限发现与重试；不同协议相同 offered、轨迹、无线和 peer 假设；控制广播、邻居发现、probe 和端点 ACK 的所有字节及 airtime 均计费。冻结源码和模型完整哈希；公平性、时间参数、版本细节与未实现功能必须在各方案说明中公开。几何图只用于模型和评价，不作协议决策；时间未到截止的业务右截尾。

本合同为 v0.1；首个原型完成前可能需记录兼容性修订，不能静默改变。
