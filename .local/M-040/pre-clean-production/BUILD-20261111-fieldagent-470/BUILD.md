# 构建归档：field_agent + 470 MHz + 主动路由（2026-11-11）

**这是什么**：一次固件目标编译的产物与证据归档，不是实验运行、不是任务卡、也不是验收结论。
仓库 `coordination/` 的命名空间由 M 维护，本目录**没有占用任何角色任务 ID**；
如果要并入正式任务，请 M 分配 ID 后整体移动。

## 结论一句话

源码改动**编译通过**（0 warning / 0 error）、路由重路由逻辑**主机单测 15/15 通过**、
470 MHz 默认值**确认进入镜像**；但**未烧录、未上电、无空口与移动性实测**。

## 内容

| 文件 | 说明 |
|---|---|
| `images/mid_edge.bin` | app 镜像，偏移 `0x10000`，951,712 B |
| `images/bootloader.bin` | bootloader，偏移 `0x0` |
| `images/partition-table.bin` | 分区表，偏移 `0x8000` |
| `mid_edge.elf` / `mid_edge.map` | 带符号 ELF 与链接映射（用于核对新符号与体积） |
| `sdkconfig` | 本次实际生效的配置 |
| `flash_args` / `flasher_args.json` / `project_description.json` | 构建系统生成的烧录参数与工程描述 |
| `build.log` | idf.py 完整日志（229,944 B，warnings=0 errors=0） |
| `changed-sources.sha256` | 本次改动/新增的 10 个源文件哈希 |
| `SHA256SUMS.txt` | 归档内每个文件的哈希 |
| `unit-test/sr_retry_check.c` / `.exe` / `run.log` | 路由重路由主机单测源码、二进制与运行记录 |

## 关键标识

- 新 `build_id`（已嵌在镜像里）：`mid-lora-ref-v1-158bf1db1c611f9d024537bda6c51117068d66d0b97db67c64aff734934a948f`
- 已部署旧镜像：`mid-lora-ref-v1-6f62fc56a70718250928d818fadd2a943d965587acb6622d36dd04c4b6d7ce50`
- 镜像大小 951,712 B（0xE85A0），1 MiB app 分区余 **0x17A60（9%）**
- 工具链：ESP-IDF `v5.5.1-dirty`，esptool `4.13.0`，`environment.json` SHA256 `24c6a7a18c9315417c163cdee5fe7cd766ca503a034c481c0277f463ec0d1cc1`
- 代码基线：`b7f16ea94c1f4e07045784d06f87362ebc3e84c3`（分支 `codex/baseline-reproduction-20261023`）。
  **注意**：该提交之上本工作区已有大量他人未提交改动，本归档只对本目录 `dirty_files_sha256` 列出的 10 个文件负责。

## 本次改了什么

1. **主动路由预热** `field_warm_tick()`（`idf/main/field_runtime.inc`）：开机后按 `agent.cfg.roster`
   与 PC 逻辑地址主动发起既有有界 RREQ，不再等业务包触发；路由剩余有效期 >4 s 时跳过，
   每 500 ms 至多一条查询。
2. **470 MHz 默认频点**（`lora_ref/runtime.c`、`tools/mid_hardware/lora_ref/configure.py`）：
   出厂默认 433 → 470 MHz，新增 `--frequency-hz`（白名单 410–493 MHz）。
3. **失效下一跳即时探测** `neighbor_demand()`（`idf/main/app_main.c`）：路由发送回调失败时
   立刻单播 `ND01` HELLO，不再等 2–3 s 周期或 9 s ACK 窗口。
4. **单次本地重路由**（`source_route.c` 的 `failed()`）：本地 DATA 首跳失败时重新发现一次，
   每个包身份只重试一次（`retried[]` 环 + `retries` 计数）。
5. **有界射频自愈** `radio_heal()`：发送回调 1 s 未到不再永久锁死；3 s 隔离窗、每 boot 最多 3 次。
6. **LoRa 网关可替换**：`receive.py` 增加 `--gateway-mac` / `--any-gateway` / `--task-id`；
   `lora_ref_status` 增加 `lora_ref_rx_frames`、`lora_ref_last_rx_ms`。

设计、常量、限制与验收清单见
[`firmware/mid_baseline/field_agent/PROACTIVE_ROUTING.md`](../../firmware/mid_baseline/field_agent/PROACTIVE_ROUTING.md)
与 [`tools/mid_hardware/lora_ref/GATEWAY_SWAP.md`](../../tools/mid_hardware/lora_ref/GATEWAY_SWAP.md)。

## 已验证 / 未验证

已验证（本机、本次）：

- `idf.py build` 退出码 0，`warnings=0 errors=0`；
- 新符号确在 ELF：`field_warm_tick` 0x4200e688、`neighbor_demand` 0x42010f64、`radio_heal` 0x42010880、
  `retried_take` 0x42016a24、`warm_build` 0x4200e59c、`warm_remaining` 0x4200d9bc；
- `images/mid_edge.bin` 中 `470000000`（`80 A1 03 1C`）出现 1 次、`433000000`（`40 0E CF 19`）0 次；
- 主机 gcc 编译真实 `mid.c` + `source_route.c`，15 项断言全过（见 `unit-test/run.log`）。

**未验证（不得当作通过）**：

- 没有烧录、没有上电、没有任何 ESP-NOW 或 LoRa 空口数据；
- 主动预热、即时探测、单次重路由、射频自愈的**行为**只有代码与主机单测支撑；
- 470 MHz 的**天线匹配**没有任何证据，五板天线型号仍未目视核实；发射前须确认 ②号 Sub-GHz IPEX 口；
- 移动性（移动/移走中间节点）恢复时间未测。

## 复现

```powershell
# 1) 载入保留工具链环境（把 R: 换成真实路径，本机会话无法建立盘符映射）
$root='D:\Multi-Agent Network\.local\espnow\E1-015'
$j = Get-Content "$root\environment.json" -Raw | ConvertFrom-Json
foreach ($p in $j.PSObject.Properties) {
  $v = ([string]$p.Value) -replace 'R:\\', ($root + '\') -replace 'R:/', (($root -replace '\\','/') + '/')
  Set-Item -Path ("env:" + $p.Name) -Value $v
}
Remove-Item env:PYTHONHOME,env:PYTHONPATH,env:VIRTUAL_ENV -ErrorAction SilentlyContinue

# 2) 构建（源码只读；build 目录与 sdkconfig 放在仓库外，避免污染工作树）
& "$root\tools\python_env\idf5.5_py3.11_env\Scripts\python.exe" `
  "$root\sdk\esp-idf-v5.5.1\tools\idf.py" `
  -B <构建目录> -D "SDKCONFIG=<sdkconfig路径>" `
  -D "SDKCONFIG_DEFAULTS=D:\Multi-Agent Network\firmware\mid_baseline\field_agent\idf\sdkconfig.defaults" `
  -D MID_HEADLESS=OFF build
```

`field_agent` 的 `build_id` 由 `idf/main/CMakeLists.txt` 按源码哈希计算，
所以**任何源码改动都会改变 `build_id`**，烧录守卫与 `flash.py --current-build/--target-build` 需同步更新。

## 本次遇到的环境问题（重要，影响后续复现）

1. **盘符映射不可用**：`subst R:` 在本会话被拒绝（`Access denied`），因此改用真实路径加载
   `environment.json`；IDF 正常工作。
2. **命名管道受限**：受限模式下 `idf.py` 用命名管道捕获 cmake 输出会被拒绝（`WinError 5`），
   必须对这条构建命令放宽一次访问权限才能完成编译。这是环境边界，不是代码问题。
3. **`.local/` 不可写**：该目录属主是另一个账户 `HLI\CodexSandboxOffline`，当前用户没有
   修改其权限的资格，权限修复脚本按策略**拒绝**并未做任何修改。因此本归档只能放在仓库根目录。
4. **`simulation/` 与其它子目录不可写**：即使把授权补给了当前用户，写入仍被沙箱的
   完整性/能力标签挡住（标签只在工作区根生效），需要重启会话让 DSH 重新下发才能恢复。
   因此本归档没有写进 `simulation/outputs/`。

建议：等有权限的账户或管理员把 `.local/mid/` 修好后，将本目录整体移入
`.local/mid/BUILD-20261111-fieldagent-470/`，或按 M 分配的任务 ID 落到 `simulation/outputs/<任务ID>/<run-id>/`。

## 权限改动的撤销

本次只做过一次意图性权限修改（工作区根），脚本自带备份：

```powershell
pwsh -NoProfile -File 'D:\dsh-acl-recovery\acl-backup-c1b713855fff4398a5763a879812c5ce.json.ps1' -Path 'D:\Multi-Agent Network' -AllowRoot 'D:\Multi-Agent Network' -Restore 'D:\dsh-acl-recovery\acl-backup-c1b713855fff4398a5763a879812c5ce.json'
```

`simulation/` 也补过一次授权（备份 `acl-backup-fdcd6d32eeb8420f818eb63701e50b08`），
但实测未解决写入问题：

```powershell
pwsh -NoProfile -File 'D:\dsh-acl-recovery\acl-backup-fdcd6d32eeb8420f818eb63701e50b08.json.ps1' -Path 'D:\Multi-Agent Network\simulation' -AllowRoot 'D:\Multi-Agent Network' -Restore 'D:\dsh-acl-recovery\acl-backup-fdcd6d32eeb8420f818eb63701e50b08.json'
```
