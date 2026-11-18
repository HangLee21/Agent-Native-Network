# 阶段总结 2026-11-18 · 网关接入 / 前端合并 / 刷写自动化

分支：`codex/baseline-reproduction-20261023`
**`codex/production-deployment`（deploy）全程只读，未做任何修改**（仍停在 `d27bb3e`）。

---

## 1. 这一阶段解决了什么

| 事项 | 结果 | 证据 |
|---|---|---|
| 换新网关（亿佰特 E870-L） | ✅ 打通 | frames 持续增长，三台节点编号 1/2/3 正确 |
| 旧网关（RHF2S008）兼容 | ✅ 保留 | `KNOWN_GATEWAYS` 仍映射为 RHF2S008 |
| 两条前端线合并 | ✅ 完成 | 部署源解耦 + 布局 + 编号同时可用 |
| 节点编号进帧 | ✅ 已上板 | 帧头第 35 字节，空口验证 |
| 远程刷写 | ✅ 一键 | 三台 `OK VERIFIED`，缺依赖自愈 |
| 网络模式管理 | ✅ 三模式 | `netmode.ps1` |
| 批量做卡 | ❌ **未验证通过** | 三次尝试，卡上零日志 |

---

## 2. 网关（亿佰特 E870-L470LG11-S）

### 设备事实

```
型号      E870-L470LG11-S    固件 FW-9252-0-10
MAC       a4:f0:0f:e5:7b:83  SN S5203996S
射频      radio0 470.6 MHz / radio1 471.4 MHz
          → 8 信道 470.3/470.5/470.7/470.9 + 471.1/471.3/471.5/471.7
          实际使用 ch1 = 470.5 MHz（与三块节点一致）
默认账号  admin / admin（登录框 placeholder 就写着）
```

### 管理 API（逆向自其 Web 前端）

```
GET  /login.js                      → RAND_KEY（每次开机随机）
POST /loginsubmit.json              body = HMAC-SHA1(key=密码, msg=用户名+RAND_KEY) 的 hex
                                    → 返回 token
后续请求必须带 ?token=<t>&date=<毫秒>  （缺 date 会退回登录页）
GET  /basic.json                    读配置
POST /basic.json                    写配置（JSON body）
POST /DeviceContrl  body="parameter send completed"   提交配置（不提交会回滚！）
POST /DeviceContrl  body="web set device reboot"       重启
```

### 改过的配置

| 字段 | 原值 | 现值 |
|---|---|---|
| `server_address` | `192.168.1.1` | `192.168.137.10` |
| `serv_port_up` | `1700` | `1680` |
| `gateway_ID` | `FFFFFFFFFFFFFFFF` | `a4f00fe57b830000` |
| `eth_dhcp_mode` | `0`(DHCP) | `1`(静态)，`192.168.137.11/24` |

**两个坑**：
1. 只写 `basic.json` 不提交 `parameter send completed` 会**回滚**。
2. `web set device reboot` **是有效的**，但**恢复转发需要 90 秒以上**；
   只等 90 秒会误判为"指令无效"。

### 静默故障

转发器会停止发送（连 PULL_DATA 心跳都没有），配置却完全正常。
用 `DeviceContrl` 重启可恢复。**目前没有根因，只有恢复手段。**

---

## 3. 前端

### 合并内容

采用 deploy 分支的前端与工具作为基线（它们已包含更早的网关顶点与数据源白名单改动），
再把本分支的修复叠加：

| 来源 | 能力 |
|---|---|
| deploy | 网关源解耦、遗留 UDP 兼容、节点超时、稠密拓扑、手动/GPS 布局、串口接收节点 |
| 本分支 | 网关身份从 PUSH_DATA 头学习、数字标签、端口独占保护、Ebyte 适配 |

新增文件：`fleet-model.js`、`sources.py`、`node_serial.py`、`remote.py`、
`serial_discovery.py`、`fleet_registry.py`，以及被依赖的 `tools/flight_link/`。

### 修掉的三个显示缺陷（都是"看起来正常"型）

| 缺陷 | 症状 | 根因 |
|---|---|---|
| 节点年龄用全局时间 | 停机节点永远显示最新 | `pc_receive_age_ms = now - self.last_rx`，last_rx 是全局的 |
| `state` 字段类型不匹配 | **"双方互证/失效"从未出现过** | 解码器约定字符串 `lost/heard/bidirectional`，我输出数字 |
| 手写标签冒充设备 | 在线的板子被标成"D" | `labels.json` 里有从未被设备验证的映射 |

修复后实测：绿色「双方互证」出现 4 次、红色「采样时已失效」出现 5 次、
未上电的板子状态为「采样已失效」。

---

## 4. 固件：LRN1 携带节点编号

帧头第 35 字节写入设备编号（1–255，0=未分配，越界写 0 不截断）。
完整帧结构见 `docs/LRN1_FRAME.md`。

镜像：`BUILD-20261118-lrn1-nodenumber/`
```
mid_edge.bin 970032 B  sha256 02C17B12...EDC4F60
build_id mid-lora-ref-v1-bb52a9c1...1287e7a306
```

空口验证（不加载任何名单文件）：
```
a4:f8 → 1    a5:cc → 2    a4:e0 → 3    网关 → E870L-470
```

---

## 5. 工具

仓库根目录四个双击入口：

| 文件 | 作用 |
|---|---|
| `START_STUDIO.cmd` | 自动切 lab（缺地址时提权切换）→ 起服务 → 开浏览器 |
| `FLASH_NODES.cmd` | 刷全部节点：预检 → 自动补工具/装 esptool → 刷 → 校验 → 回滚 |
| `FLEET_STATUS.cmd` | 机群状态 |
| `MK_CARD.cmd` | 做卡（**尚未验证通过**） |

配套脚本：`netmode.ps1`、`start_frontend.py`、`flash_nodes.py`、`refresh_labels.py`、
`mkcard.py`、`shortcut_*.ps1`。

### 平台细节（踩过才知道）

- `netmode.ps1` 必须是 **UTF-8 BOM + CRLF**，否则 Windows PowerShell 5.1 解析失败。
- 非提权运行时改网卡会 `Access is denied`；早期版本用 `SilentlyContinue` 吞掉错误，
  **打印了成功摘要却什么都没做**，已改为逐条报错。
- `fleet.py update` 曾只取含 `FAILED` 的那一行，**真正的 esptool 报错被丢弃**。

---

## 6. 未解决 / 未验证

### 6.1 批量做卡（主要遗留）

三次尝试，**每次卡上都是零日志**：

| 机制 | 结果 |
|---|---|
| `systemd.run`（缺 `kernel-command-line.target`） | 不执行 |
| `systemd.run`（参数补齐） | 不执行 |
| cloud-init `runcmd` + 新 instance-id + 正确 802.1X | 不执行 |

结论：**这张镜像上的首启自动化没有跑起来**，机制未查明。
日志已改写到 FAT boot 分区（`eora-firstboot.log` / `eora-status.txt`），
下一次尝试可以直接从卡上取证。

### 6.2 其它

- 本机 Tailscale 会间歇性进入 `NoState`，需手工 `Restart-Service Tailscale`。
  工具已能识别并给出该命令，但不能自动修复（需要管理员）。
- esptool 自动安装路径未在"真的缺失"状态下验证（卸载被 PEP 668 拦住）。
- `LRN1` 帧里 `wifi_group` 与 `total_rows` 存在字节重叠（group 实际 24 位），
  属既有行为，已在文档记录但未改动。

---

## 7. 教训（写下来避免重犯）

1. **"能显示"不等于"正确"**。验收必须包含状态转换：在线→失效、失效→恢复、
   双方互证/单侧/失效三种连线都要能出现。
2. **不要用配置冒充事实**。手写的映射表、预声明的名单，最后都会变成假数据。
3. **失败必须报出来**。`SilentlyContinue` + 兜底摘要 = 假装成功。
4. **观察窗口要够长**。90 秒的观察让我把"慢"误判成"无效"。
5. **换机制前先取证**。应该在第二次失败时就停下来读日志，而不是换第三个方案再赌。
