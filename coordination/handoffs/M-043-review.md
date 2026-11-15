# M-043 独立评审摘录

来源：C 窗口 coordination/reviews/C-035.md 的 M-043 增量，M 原文归档，其他历史评审仍由 C 维护。


审 `app/start/launcher.py`，当前与E2/11冻结源码SHA-256一致（`cc2696853731dd0bcd79ba134792ae74b2cff92a3f3fcd39f763b20fb3dfc58d`）。新逻辑先等待匹配心跳，再在未观察心跳时确认子进程存活、topology schema及配置EUI，允许启动完整Studio；无心跳时标recovering，不将HTTP就绪当网关在线。后续两秒检查匹配EUI与gateway_observed；gateway.py基于PULL_DATA时间30秒过期，故旧状态超过阈值会转离线，而非永久保留。实际恢复/过期转换本轮没有新增端到端实验。

E2/11保存随包解释器、临时端口的真实gateway/Studio启动证据：无心跳时HTML HTTP 200、含前端资源引用、gateway_observed=false、control.enabled=false、recovery=recovering；浏览器打开调用返回true，但没有视觉截图或确认页面实际渲染，不将HTML响应表述为视觉验收。证据脚本直接调用launch，未验证完整双击入口替换旧实例；旧用户实例应先由用户关闭再重新双击。没有发现当前单候选配置下阻断该修复的源码问题。

注意：当配置多个candidate_hosts时，首个地址的服务一旦HTTP就绪即停止遍历，即便未收到网关PULL_DATA；其他候选地址可能永不尝试。当前fleet仅一个地址，此为多候选配置的后续局部风险，不声称已验证故障切换。C未运行服务、浏览器或触及现场设备；仅只读源码与保存证据，无后台。
