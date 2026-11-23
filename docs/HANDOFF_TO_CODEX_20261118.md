# 交给 Codex 的对接提示

把下面整段复制给 Codex 即可。

---

```
仓库：D:\Multi-Agent Network
分支：codex/baseline-reproduction-20261023（只在这里改）

硬性约束
1. 绝对不要修改 codex/production-deployment（deploy）分支，它是只读基线，仍应停在 d27bb3e。
2. 不要用 git add -A（仓库里有 .local/、仿真产物等大量未跟踪内容）。按路径显式 git add。
3. 提交前用 `git grep -l '<密钥>'` 确认没有把 WiFi 口令或 Tailscale auth key 写进版本库。

先读这三个文件，再动手
- docs/SESSION_SUMMARY_20261118.md   ← 本阶段做了什么、哪些已验证、哪些没验证
- docs/OPERATING_GUIDE.md            ← 日常操作（网络三模式 / 前端 / 刷写 / 排查）
- docs/LRN1_FRAME.md                 ← LoRa 帧结构（含第 35 字节的节点编号）

当前可用（不要弄坏）
- START_STUDIO.cmd    自动切 lab 模式、起 topology_server(8780)+Studio(8794)、开浏览器
- FLASH_NODES.cmd     一键刷全部节点，自带依赖自愈、build_id 校验、失败回滚
- FLEET_STATUS.cmd    机群状态
- 网关 Ebyte E870-L 已配置为静态 192.168.137.11，转发到 192.168.137.10:1680
- 三块节点已刷到 BUILD-20261118-lrn1-nodenumber，编号 1/2/3 从帧里解出

第一个任务：把 LRN1 状态块刷进三块板并验证
背景：docs/LRN1_EXTENSION_DESIGN.md 已实现并提交（9c006a4），主机测试与 C/Python
      交叉验证全部通过，镜像在 BUILD-20261118-lrn1-status/。但三台树莓派当时离线，
      没有刷入实机。
要求：FLASH_NODES.cmd 刷三块板，然后看网关收到的帧里 status 块是否出现
      （每 5 帧一次），核对 reset_reason 与 heap_free_kb 是真实值而不是 0。
      电压与芯片温度当前恒为 0，属已知未接入项，不要当成 bug。
成功标准：三台节点 report.status 有值，且 reset_reason 与 Pi 侧重启记录一致。

（PI4 做卡已由另一窗口用 4b19a97 解决，eora-air-04 已入网，不要重复：那条路的
  根因是 cmdline.txt 的 i= 种子参数优先于 meta-data 的 instance-id。）

验收标准（重要，之前吃过亏）
- 不允许只验证"页面能显示"。必须验证状态转换：
  节点在线→失效（30 秒阈值内）、失效→恢复、双方互证/单侧/失效三种连线都能出现。
- 任何失败必须打印真实原因。禁止用 -ErrorAction SilentlyContinue 加兜底摘要假装成功。
- 声称"已验证"之前，先确认你跑过的是真实路径，而不是合成数据。

已知未解决问题（不要当成已完成）
- 本机 Tailscale 会间歇性 NoState，需要管理员 Restart-Service Tailscale。
- 网关转发器会偶发静默，重启可恢复（恢复需 90 秒以上）。
```
