# deploy 仓库里的位置（做卡与刷板）

本仓库是**打包形态**，目录结构与开发仓库不同。下面是新增内容的实际位置，
以及和开发仓库的对应关系。

---

## 一、目录对照

| 内容 | 本仓库（deploy） | 开发仓库 |
|---|---|---|
| 做卡工具 | `app/services/tools/gateway_probe/mkcard.py` | `tools/mid_baseline/gateway_probe/mkcard.py` |
| Pi 侧 helper | `app/services/tools/gateway_probe/{node_reader,node_update,pi_node_probe,set_group}.py` | 同上对应 |
| 机群工具 | `app/services/tools/fleet/{fleet,flash_nodes,refresh_labels}.py` | `tools/mid_baseline/fleet/` |
| 现场配置写入 | `app/services/tools/fleet/write_site_env.py` | 同上 |
| 老卡开密码 | `app/services/tools/fleet/enable_ssh_password.py` | 同上 |
| 生产包生成 | `app/services/tools/fleet/make_production_kit.py` | 同上 |
| 一键脚本 | 仓库根 `SETUP_SITE.cmd`、`MK_CARDS.cmd`、`SITE_STATUS.cmd`、`SITE_FLASH.cmd`、`SITE_GROUP.cmd` | 仓库根 |
| 文档 | `docs/` | `docs/` |

---

## 二、五个一键脚本在三种布局下都能用

它们自己探测路径，不需要改：

```
fleet/            ← 生产做卡包
tools/mid_baseline/fleet/   ← 开发仓库
app/services/tools/fleet/   ← 本仓库
```

`site.env` 会被向上最多 4 层自动查找，所以放在仓库根即可。

---

## 三、这里的工具**没有被现有启动器引用**

本仓库原有的 `START_STUDIO.cmd`、`FLASH_NODES.cmd`、`SETUP_GATEWAY.cmd`
（`app/flash/`、`app/gateway_setup/`、`app/start/`）**一字未改**。

新增的做题与刷板工具是**并列的一套**，面向"给现场同事做卡 + 跨网络刷板"，
与原有的"本机 USB 刷写台 / 网关部署"互不影响。

> 注意：`FLASH_NODES.cmd` 在本仓库指的是**本机 USB 刷写台**；
> 跨网络刷板请用新增的 `SITE_FLASH.cmd`。

---

## 四、做卡（现场形态）

```powershell
# 生成生产做卡包（给没有私钥的现场同事）
python app\services\tools\fleet\make_production_kit.py --out D:\handoff\card-kit --with-flash
```

生成物是一个自包含目录，放到任意位置双击 `SETUP_SITE.cmd` 即可。

---

## 五、文档索引

| 文档 | 内容 |
|---|---|
| [SITE_OPERATOR_RUNBOOK.md](SITE_OPERATOR_RUNBOOK.md) | 现场同事的双击式操作单 |
| [OPERATOR_HANDBOOK.md](OPERATOR_HANDBOOK.md) | 两人分工、env 字段、命令速查、故障表 |
| [CARD_CONTENTS.md](CARD_CONTENTS.md) | 卡上写了什么（逐项） |
| [CARD_PROVISIONING_MODES.md](CARD_PROVISIONING_MODES.md) | WiFi 两种认证、Tailscale 三种模式 |
| [DEV_PROD_SPLIT.md](DEV_PROD_SPLIT.md) | 开发/生产解耦 |
| [FLEET_GROUPS.md](FLEET_GROUPS.md) | 两个 group 的隔离与信道 |
| [BATCH_CARD_CHECKLIST.md](BATCH_CARD_CHECKLIST.md) | 批量做卡准备清单 |
| [PORT_TO_DEPLOY_PLAN.md](PORT_TO_DEPLOY_PLAN.md) | 本次移植的清单与风险 |

文档里出现的 `tools\mid_baseline\...` 属于**开发仓库**路径；
在本仓库请对照第一节的表格。

---

## 六、改代码的正确流程（**只改 baseline**）

本仓库的代码一律由 baseline 迁移而来，**不要直接改这里**。
直接改会产生两处分叉，下次迁移就互相覆盖（`/health` 与 LRN1 解码器就这样被发现过）。

### 1. 在 baseline 改

```powershell
cd "D:\Multi-Agent Network"
# ... 修改 tools/、research/、firmware/ 下的源码 ...
```

### 2. 迁移到本仓库

```powershell
python tools\release\sync_to_deploy.py --deploy .local\wt-deploy --check   # 先看差哪些
python tools\release\sync_to_deploy.py --deploy .local\wt-deploy           # 同步
```

对应关系写死在脚本里的 `PAIRS`，共 38 个文件：

| baseline | 本仓库 |
|---|---|
| `tools/mid_baseline/gateway_probe/*` | `app/services/tools/gateway_probe/*` |
| `tools/mid_baseline/gateway_probe/{topology_server,start_frontend}.py`、`netmode.ps1` | `tools/mid_baseline/gateway_probe/` |
| `tools/mid_baseline/fleet/*` | `app/services/tools/fleet/*` |
| `research/agent_native_network/mobile_gateway/*` | `app/services/assets/mobile_gateway/*` |
| `tools/mobile_gateway/*` | `app/services/tools/mobile_gateway/*` |
| `tools/flight_link/{gateway,codec,archive}.py` | `app/services/tools/flight_link/*` |
| `firmware/mid_baseline/field_agent/lora_ref/decoder.py` | `app/services/firmware/mid_baseline/field_agent/lora_ref/decoder.py` |
| `tools/release/{refresh_release_manifest,verify_release}.py` | `tools/release/*` |

### 3. 在本仓库重算发布清单

```powershell
cd .local\wt-deploy
runtime\python\python.exe -X utf8 tools\release\refresh_release_manifest.py
runtime\python\python.exe -X utf8 tools\release\verify_release.py
runtime\python\python.exe -X utf8 app\start\launcher.py --dry-run
```

`--dry-run` 必须输出 `"release_ready": true`。

### 4. 只有这几种情况才允许在本仓库单独存在

| 文件 | 为什么不同步 |
|---|---|
| `app/start/launcher.py`、`app/flash/`、`app/gateway_setup/` | 打包/硬件适配层，baseline 没有 |
| `app/services/tools/flight_link/compat_decoder.py` | 网关 ARM 运行时的 Python 3.4 副本，由解码器语义生成 |
| `firmware/manifest.json` | 发布清单，由脚本生成（不手改） |
| `config/fleet.default.json` | 现场默认配置（含节点表与网关） |
| `*.cmd` 启动脚本、`docs/` 子集 | 交付形态的入口与文档 |

### 5. 验证两边一致

```powershell
python tools\release\sync_to_deploy.py --deploy .local\wt-deploy --check
# 输出“两边一致。”才算迁移完成
```

---

## 七、本轮迁移记录

| 从 baseline 迁入 | 修了什么 |
|---|---|
| `server.py` | `/health` 用 `session`（原先 `state.instance` 抛 AttributeError） |
| `studio.py` | 前端资源与 fleet 配置在打包布局下的回退 |
| `decoder.py` | 旧帧与新帧（编号/状态块/GPS 块）同时解码 |
| `gateway.py` | 状态块与 GPS 块的新鲜度（`status_age_ms` 等） |
| `tools/mobile_gateway/*` | 全部同步 |

迁移后实测（真实 E870-L 网关）：

```
frames=21  bad=0  reports=5
编号 1/2/3/4/5，邻居各 4 个，status_age_ms 21–33 s
```

---

## 八、密码登录策略（有意为之的取舍）

现有 5 块板与以后新做的卡，**密码登录全局可用**（覆盖了 1 号原有的加固策略）。
这是明确的选择，不是遗漏。

### 历史情况

1 号上有一个更早的加固文件：

```ini
# /etc/ssh/sshd_config.d/10-eora.conf
PubkeyAuthentication yes
PasswordAuthentication no           # 全局禁止密码
Match Address 169.254.0.0/16
    PasswordAuthentication yes      # 仅网线直连时允许
```

含义：密码只能在“人蹲在设备旁边插网线”时用，必须物理接触。

### 现在的做法

`00-eora-password.conf` 写入 `PasswordAuthentication yes`。
sshd 对同名指令取**首个生效值**，目录按文件名字典序 Include，`00-` 永远最先，
因此覆盖了 `10-eora.conf` 的 `no`。

### 影响

| | 之前 | 现在 |
|---|---|---|
| 密码登录来源 | 仅网线直连（169.254） | **任何来源**（tailnet / WiFi / 公网若可达） |
| 拿到密码的人 | 需物理接触设备 | 远程即可登录 |
| 私钥登录 | 仍需（未改动） | 仍需 |

**原因**：第二位运维走 Tailscale（100.x.x.x），不属于 169.254/16，
在旧策略下会被拒绝（`Permission denied (publickey)` 就是这么来的）。

### 如需收紧

改用只允许 tailnet 与直连网线：

```ini
# /etc/ssh/sshd_config.d/00-eora-password.conf
PasswordAuthentication no
KbdInteractiveAuthentication no
Match Address 100.64.0.0/10,169.254.0.0/16
    PasswordAuthentication yes
    KbdInteractiveAuthentication yes
```

验证方式：`sshd -T -C addr=100.64.0.1 | grep -i passwordauthentication` 应为 yes，
`sshd -T -C addr=8.8.8.8` 应为 no。

### 回退到最初状态

删除 `00-eora-password.conf` 并 `systemctl reload ssh` 即可，`10-eora.conf` 一直未被修改。

### 相关实现

- `app/services/tools/fleet/enable_ssh_password.py`（对已有设备打开）
- `app/services/tools/gateway_probe/mkcard.py` 的安装器逻辑（新卡首启自动写入）

两者都写 `00-` 前缀，并清理历史遗留的 `20-eora-password.conf`。

---

## 九、网关候选地址与失败切换

`config/fleet.default.json` 的 `gateway.candidate_hosts` 是**有序列表**，
`RemoteGateway` 按列表顺序尝试：

1. 先集中在当前首选上试，连续失败 `retries`（默认 3）次后，切到列表中的下一个；
2. 切换时同一次轮询内会再给新候选一次机会，不必多等一整轮；
3. 一旦某个候选成功，就把它固定为首选并清零失败计数；
4. `receiver`/`info` 里会回报当前使用的 `host`，便于判断连的是哪台。

现场换网关只需改 `candidate_hosts`（可写多个）。`mode` 说明：

| mode | 含义 | 适用 |
|---|---|---|
| `remote` | 网关**自身**提供 HTTP 拓扑接口（8780） | RHF2S008 一类带 Web 服务的网关 |
| `legacy_local` | 网关只发 UDP，由本机接收器解析 | E870-L 一类纯透传网关 |

`legacy_local` 下启动器会自己拉起接收器，不需要额外脚本。

---

## 十、启动脚本：两棵树里逐字节相同

仓库根的启动脚本**不再是两套实现**。同一个文件靠运行时自检决定走哪条路，
所以两棵树里内容完全一致，不存在“改了这边忘了那边”的问题。

| 脚本 | 在两棵树里做什么 |
|---|---|
| `START_STUDIO.cmd` | 有 `app\start\launcher.py` 就走打包启动器（`runtime\python`）；否则走开发前端 `start_frontend.py` |
| `FLASH_NODES.cmd` | **只做本机 USB 刷写**（`app\flash`）。开发树没有这套，会明确提示改用 `FLASH_REMOTE.cmd` |
| `FLASH_REMOTE.cmd` | **远程机群刷板**，自动在 `fleet\`、`tools\mid_baseline\fleet\`、`app\services\tools\fleet\` 中找 `flash_nodes.py` |
| `SITE_FLASH.cmd` | 菜单 → 转调 `FLASH_REMOTE.cmd`（同一实现） |

### 自检开关

每个脚本都支持 `--which`，只打印“会走哪条路”然后退出，不会真的启动或刷写：

```powershell
START_STUDIO.cmd --which
FLASH_NODES.cmd  --which
FLASH_REMOTE.cmd --which
```

输出示例（交付包）：

```
mode=packaged  target=app\start\launcher.py   found=yes
python=<包内 runtime 路径>
kind=local-usb target=app\flash\flash_nodes.py found=yes
kind=remote    fleetdir=<包内 app\services\tools\fleet>
```

开发树里 `FLASH_NODES.cmd --which` 会显示 `found=no`，这就是它给出提示的原因。

### 为什么这样能避免遗忘

- 四个文件在 `git` 里是**同一份内容**，改一边必然改两边（否则一次提交就看得见）。
- 行为差异由**检测到的事实**决定（有没有 `runtime\python`、有没有 `app\flash`），
  而不是靠人记住“这个仓库里 FLASH_NODES 是远程”。
- `--which` 让任何人都能在十秒内确认现场走的是哪条路。
