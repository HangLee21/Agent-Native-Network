# 每机离线部署配置

固件入口：`firmware/mid_baseline/edge/idf/`。沿用已实测的 c422 UART 驱动入口（460800、8N1），新增本地持久配置；旧 `firmware/mid_baseline/idf/` 和已发布包保持原样。

生成实际 A→B→C 及反向 C→B→A 的共同配置：

```powershell
python -B tools/mid_baseline/edge_profiles/make_profile.py --path A B C --reverse --profile-id abc-two-way-v1 --output simulation/outputs/E1-023/20261108-03-abc-profile
```

该目录已生成，重复演示请换新目录。`deploy.json` 是单条 JSON 命令，可供 E2 `tools.mid_edge` 的 `--profile` 使用；`deploy.jsonl` 是可直接写到本地串口的一行命令。每台设备分别部署相同文件，无需共同主机、跨主机 IP、8766/8767 服务或远端 boot。A/B/C 的实际 MAC 写在 `profile.json`，不是 COM 端口绑定；操作前由 H 核实际身份。

本机串口协议新增：

| 命令 | 参数与行为 |
|---|---|
| `deploy` | `nonce`、`profile_id`（1–64 ASCII）、`table_hex`（MID 表体，不含无线帧头）、布尔 `autostart`。仅 inactive、射频已关且无在途 TX 时接受；校验本机 MAC、确定性无环路径及目的可达后写本机 NVS `mid_deploy/profile`。`autostart:true` 保存后立即启动。 |
| `local_start` | `nonce`。从已保存的本机表启动；无需 publisher_boot。保存失败/缺失/损坏时拒绝。 |
| `stop` | 停止业务、清未发队列，等待在途回调后关射频；保留 NVS。`stopping:true` 时等 `info` 显示 `radio:false`、`stopping:false` 再配置。 |
| `deployment_clear` | `nonce`。仅 inactive 且无在途 TX 时删除本机 profile；不会擦除 NVS 分区或其他命名空间。 |
| `send` | 原 `dst`/`payload_hex`（0–160 字节）；成功回执追加 `origin`、`origin_boot`、`packet_seq`、`dst`。这表示本机接纳，目的端 `rx_local` 才是接收证据。 |
| `info`/`stats` | 追加 `deployment_mode`（`offline_table`/`mid`）、`deployment_saved`、`deployment_fault`、`profile_id`/`autostart`（有配置时）、`display_enabled`；`info.display_api=2`。计数、事件、`rx_local.payload_hex` 在两种构建中一致。 |

所有命令继续要求唯一 `nonce`。收到 `saved_but_start_failed` 时配置已落盘，但当前射频启动失败；检查 `info` 并修复原因后显式 `local_start`，不要把失败回执当作未写入。电源中断时 NVS 事务完整性由 ESP-IDF NVS 提供；本机软件测试不冒称实际掉电测试。

上电读取本机配置；`autostart:true` 时直接安装本地路径表并启动射频，中继单独重启也如此。`autostart:false` 只保存，直到 `local_start`；显式 `stop` 不会修改已保存 autostart，因此重新上电会按保存值启动。损坏/未知版本配置报 `deployment_load_failed` 并保持 idle，不静默改回原 MID 模式。可在 inactive 时重新 `deploy` 或 `deployment_clear` 恢复。

此部署模式只接受每行至多一个权重 65535 的确定性路径；每条有配置的路径必须终止于目的端，拒绝环、悬空出口、多下一跳概率表以及不存在本机身份的表。路径由人或离线应用在部署前指定，无在线测量或动态优化。原 MID `start(publisher,publisher_boot)`/`config(frame_hex)` 仍用于论文概率表：需要运行时发布者身份和当前 boot，由主机 planner 求解并发布。两者显式分开；有本地 profile 时拒绝原 `start`/`config` 和无线配置覆盖，先 stop、clear 后才可回原模式。

板间继续使用原 MID 数据帧和相同 ESP-NOW 信道 6，原始 source MAC/boot/seq/payload 保持，中继只递减 TTL。没有新增端到端 ACK、持久接收邮箱、可靠重发、加密或协议版本协商。源重启生成新 boot；中继重启不改变源包身份，去重缓存是本机易失内存，重启后可能再次收到旧副本。应用应在发包前连接目的端接收，并按源 MAC/boot/seq 处理幂等。无线可达性、三物理边缘机部署、屏幕像素和真实 NVS 重启效果由 H 的设备证据另列。

OLED 构建链接 H 的 API 2 显示模块。无屏构建仅链接同一纯 C 事件计数模型和 E1 的空后端，不链接显示 renderer、IDF 显示线程或 I²C 组件，也不初始化显示 GPIO/电源；`display_enabled:false`、`display_hw=0`。两个构建采用同一网络/串口/部署代码，以不同 build_id 区分。

主机检查：`python -B tools/mid_baseline/edge_profiles/validate.py --run <新目录名>`。目标构建：`python -B tools/mid_baseline/edge_profiles/build.py --candidate <新候选名> --variant oled --run <新目录名>`，再以同一 candidate、`--variant headless` 和另一新 run 构建无屏包。候选首次创建时快照源文件，后续不会覆盖；代码变化须新 candidate。工具链复用 `.local/espnow/E1-015/`，临时 R: 映射不替换已有其他映射。构建不打开串口，不下载依赖。
