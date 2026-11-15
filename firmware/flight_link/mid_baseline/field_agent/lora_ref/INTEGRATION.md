# 集成与H运行入口

基线：E1-028 oled-candidate-02（89d751…），当前正式五板即时邻居版本。原包不改；E1-029隔离候选中只改main/app_main.c、field_runtime.inc、main/CMakeLists.txt：启动lora_ref_init、每轮主任务复制ND/RF并排出至多一个事件、串口lora_ref_config/status、编译本目录runtime/port及三个官方驱动C文件。构建ID须覆盖本目录全部C/H。

串口配置沿原nonce/command_result，无新串口owner；H将以下命令送到已确认身份的板，E1本轮不发送。每次配置仅一次NVS lr_ref/cfg提交。Wi-Fi既有group/channel/IP/agent配置保持，无需清NVS。

```json
{"cmd":"lora_ref_config","nonce":"A-lr-rx","role":"rx","report_period_ms":10000,"jitter_ms":250,"frequency_hz":470000000,"sf":7,"bandwidth_hz":125000,"coding_rate":5,"tx_power_dbm":0,"sync_word":18,"preamble_symbols":8,"start_on_boot":true}
{"cmd":"lora_ref_config","nonce":"B-lr-tx","role":"tx","report_period_ms":10000,"jitter_ms":250,"frequency_hz":470000000,"sf":7,"bandwidth_hz":125000,"coding_rate":5,"tx_power_dbm":0,"sync_word":18,"preamble_symbols":8,"start_on_boot":true}
{"cmd":"lora_ref_config","nonce":"period-only","report_period_ms":20000}
{"cmd":"lora_ref_status","nonce":"lr-status"}
{"cmd":"lora_ref_config","nonce":"lr-off","role":"off"}
```

默认频点已改为 `470000000` Hz：`runtime.c` 的出厂默认与 `tools/mid_hardware/lora_ref/configure.py` 的 `--frequency-hz` 默认同时改动；`samples/` 下的解码夹具仍固定 433 MHz 且已冻结，不改。两个频点都在 LR1121 Sub-GHz 白名单 410..493 MHz 内并由 `valid()` 校验。**433 MHz 是 H-019 实测过的频点，470 MHz 没有任何空口证据**；H 先核 400TB Sub-GHz 口（②号 IPEX-1）及天线是否在 470 上调谐，不把 2.4G 端口接法混入。**已部署板子的 NVS `lr_ref/cfg` 仍是 433 MHz，改默认值不会静默改频**，必须显式下发新的 `lora_ref_config` 才切换。A/B物理身份按现有MAC绑定，C/D/E可用同一tx命令扩展。原配置可部分更新，改period不改角色/PHY；新period还须满足最大208B ToA+100ms+最大负抖动，避免堆积。不支持的功率拒绝，不静默改成另一档。

command_result成功表示配置已保存和排队；等lora_ref_config_applied(ok=true)对应generation，再核status的requested_generation=applied_generation和worker_state(0off/1rx/2tx；-1错误)。初始化/配置/当前TX可能使生效稍后，不把保存当作射频已成功。off保存后断电恢复off；rx/tx默认start_on_boot=true并按保存角色恢复。首次无配置默认off。

主任务每个报告周期取当前完整allowed ND表，空表也发；LoRa工作线程单独操作SPI，队列仅1待发快照、8事件，满/旧配置丢弃计数不阻塞业务。worker可在TX期间独立等待TX_DONE，不占主任务。串口JSON只由原主任务排出，不让两个任务同时printf。LoRa off不关共享GPIO36电源；只停止LoRa。PC Wi-Fi遥测停接不影响这一任务路径。

首轮A收/B发，先验一条真实lora_ref_rx经decoder得到B源序号和表，再与同期Wi-Fi快照比。B发送submitted/tx_done、A收到、PC串口收到分开。角色保存/冷启动与真正断电自启由H记录，不用软件复位冒充断电。只调周期不重编、不反复刷写；五板app-only正式部署沿M最新授权由H操作。
