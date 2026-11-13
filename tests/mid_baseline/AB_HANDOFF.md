# A/B小包阶段交接

配置入口AB_SMALL_PACKET_PLAN.json：A=90:da:72:48:a4:f8，B=90:da:72:48:a5:cc，来源为H提供的AB库存/标签快照及本文件配套hash。COM7/COM8只是当时端口提示，每次由H重新核MAC/USB。A快照为既有ANN固件；B快照只有ROM身份，不能据此认为已备份/烧录/MID就绪。C–E后置。

建议只占一次有限RF运行：先A→B 5包，再B→A 5包，每源间隔500ms、建议payload16byte，阶段各8秒，全run上限24秒，H剩余预算取较小者。该文件是带MAC的语义计划，enabled=false/native_commands=null；尚未发明或调用未冻结的MID CLI。E1正式包、真实解析接口/事件映射和C设备就绪无阻断之后，H保存独立派生配置及具体命令/时序才能执行。H最终帮助页应来自实际CLI。

Planner输入/输出及其来源必须保存，按既有500ms周期执行；不手写固定下一跳绕过Planner，不屏蔽直达来制造多跳收益。两块板只验证双向源/目的与显示对应，不验证转发或五板结果。

AB_SOCP_INPUT.json给出A/B双向流和显式假设的无量纲mean=.8、variance=.0001、rate=.05/qos=.9模型，兼容已核hash的E1检查点1 Planner输入格式；不是链路标定，也不是QoS达到实测值。E2没有在本阶段求解；E1按最终冻结Planner核格式并保存真实输出/hash，才转换为最终config。用户数据2包/秒与无量纲SOCP rate=.05不能混同。没有设备测量不填造距离/位置/无线模型参数。

必须同时采两端原始事件、boot/build、发起计数、唯一目的RX、重复/失败/控制提交量、overflow/stop及显示快照。源屏即使LINK OK仍显示目的未确认；目的本地收到可显示LOCAL RX，CMD OK只是受理。MID无端到端ACK则RTT保持null；不能新增ACK/重传换取成功显示。捕获缺失/身份冲突/stop未确认保留失败，不能补生成接收日志。原始日志适配器须在E1真实消息合同后冻结，当前归一化提案不能直接冒充native字段。

E2已对H固定C显示模型/渲染及fake平台故障边界做独立检查；这些不是ESP目标对象、像素、I2C电气或射频证据。H显示start成功仅代表worker建立，READY是首帧事务成功；需要H/用户另外确认新版实物。A原OLED确认保留，不能替代新版MID显示确认。
