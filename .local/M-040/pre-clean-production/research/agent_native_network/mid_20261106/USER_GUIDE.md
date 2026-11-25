# MID 使用指南

当前操作版本为 [package-01 A/B完整操作指南](USER_GUIDE_PACKAGE01.md)，D-015 guide-1.0.1，2026-11-06。已按E1检查点2的精确包、真实CLI和事件核对；52件包文件、13件源码及H生产6件hash匹配。D未操作设备，指南不代替C设备就绪结论或H实板结果。

正式包manifest SHA256：`d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683`。新MID配置先从A入口注入，A/B都绑定本次A boot；双方实际采用配置后再按E2冻结计划收发，结束确认radio=false且stopping=false。详细命令、镜像偏移、OLED含义、失败处理与证据边界均在完整指南。

来源见 [SOURCE_AUDIT.md](SOURCE_AUDIT.md)，工程计划见 [REPRODUCTION_PLAN.md](REPRODUCTION_PLAN.md)，交接版本见 [STAGE2_HANDOFF.md](STAGE2_HANDOFF.md)。原guide-0.1和0.2分别在D-015的01/02号证据目录保留，不再作为当前操作入口。正式A/B实测结果尚待定向交付，不能把目标编译、事件样例或旧ANN互通当成MID成功。

勘误：按C的D-doc-02将输入队列溢出事件名写为`input_queue_overflow`；guide-1.0固定副本仍在03号证据目录。此修改不改变操作流程，不新增功能重测。
