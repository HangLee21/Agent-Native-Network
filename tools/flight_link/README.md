# 网关控制候选（H独占现场服务）

合同为 `firmware/flight_link/CONTRACT.md` 的 LRC2/LRA2 v1，当前仅无害 echo/status；设置周期尚未实现。本入口不创建 LoRaWAN 网络服务，不支持飞控。明日由 H 在确认网关及源固件后，先检查 UDP 1680 现有所有者，串行停换和恢复；不得与其他转发接收器并开。

1. 复制 `tx-config.example.json` 到 H 的新运行目录。频率、rfch、功率必须按网关当前可用配置确认；示例功率 null 故意不可启动。SF7BW125/CR4/5、标准IQ与CRC开启按E1合同；目标实际上行频率不符会拒绝下发。
2. `python -m tools.flight_link.gateway --udp-host 0.0.0.0 --udp-port 1680 --http-port 8780 --gateway-ip 192.168.137.200 --gateway-eui b827ebfffe32e2c1 --tx-config <已确认配置.json>`。进程不使用SO_REUSEADDR；端口已占用时直接失败。HTTP只监听127.0.0.1。
3. `python -m tools.flight_link.client --port 8780 status` 读取目标当前MAC、observer_boot、report_seq和独立pc_receive_age_ms。最新有效报告超过30s时接收器状态显示stale；这不是RF年龄上界。
4. `python -m tools.flight_link.client --port 8780 send --target <MAC> --boot <boot> --report-seq <seq> --operation echo --value 305419896 --ttl-ms 30000`。status命令不带value。目标boot/锚点须匹配最新有效LRN1；节点以自己上报发送时刻检查TTL，不依赖两机对钟。网关本地收件年龄只能提前排除已过期，不能证明节点端TTL仍有效。
5. 再调用status并保存结果：gateway_sent是发给转发器；gateway_accepted是TX_ACK NONE，只说明网关调度；只有匹配目标、boot、report_seq、操作和echo值的有效LRA2才是executed。网关拒绝、发送错误、过期和execution_unknown_timeout均不应当作目标执行或丢包。迟到的匹配LRA2可升级确认。每目标一个在途、全网关间隔至少1秒，单命令最多3次。未知结果不要自动用新ID重发。

服务命令历史只保存在当前进程内，重启会丢失在途状态；H采集前后status和原始网关/板端日志，保留cmd_id。LRC2/LRA2 v1没有认证或主动伪造防护，仅用于受控地面echo/status，不能控制飞行动作。

`20261114-06-process-final` 是隔离进程/临时本地端口+E1实际主机C核心的合成闭环；`20261114-07-final-fixtures` 七项通过。并非实网关PULL_RESP/TX_ACK、板端收件或空口验证。
# 2026-11-14 有界调度与恢复

命令日志同时保存 SHA-256 校验副本；每次下发之前主文件与副本均完成写入。主文件缺失或损坏时，仅在副本校验和结构检查通过时恢复；损坏原件另存证据。恢复的未确认下发仍为执行未知，不自动重发。主文件和副本均不可验证时拒绝启动，不能清空未知执行记录。此保护不等于已验证物理介质断电行为。

服务可通过 `--state-file <稳定可写文件>` 启用命令日志；生产启动器对 `tools.flight_link.gateway` 指定 `production/local/command-journal.json`。启动前应保留此文件及备份；缺省不指定时仍是进程内状态，重启后无法恢复。日志保存请求、相同 cmd_id、下发尝试和回执；每次 UDP 下发前先落盘意图，落盘失败停止发送。重启时，曾尝试下发但没有目标回执的命令标为 `execution_unknown_restart`，未尝试的标为 `restart_not_sent`；两者均不自动重发，匹配的迟到 LRA2 仍可更新结果。日志路径须由一个服务实例独占；损坏或网关 EUI 不符时拒绝启动，需保留原文件并由维护人员处理。

调度先选择尝试次数最少的到期前命令，次数相同时按入队顺序；这样 30 个同时等待的目标先各得一次机会，再轮到重试。每次最短间隔、最多三次与 TTL 约束不变。此顺序不是无线时隙预约，不能保证半双工接收窗口或按期交付。

内存及双副本保留最多 256 条近期记录；需要空间时，已结束和执行未知的记录先事务提交至同目录 `<state-file>.archive.sqlite3`，再从近期记录移除。归档按原 cmd_id 建索引，不删除历史；重复 ID 仍校验原请求，归档记录可通过 `GET /api/v1/commands/<16位cmd_id>` 查询，匹配的迟到目标回执可更新。`/api/v1/lora/topology` 中 `commands` 只显示近期记录。中断后自动对账，同一命令不会因归档重新发送。归档数据库与 `<state-file>.archive-required` 标记都属于完整记录；缺失归档、磁盘故障或损坏会阻止安全运行，不能自动清空。数据库占用会随历史增长，须为审计保留足够磁盘；无 `--state-file` 时归档仅在内存中，重启不保留。此方案未验证真实断电和存储介质故障。

