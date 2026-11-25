# 移动模型与链路寿命预测（LET）

对应实现：`firmware/mid_baseline/field_agent/mobility.{c,h}`，主机测试 `test_mobility.c`。

## 1 移动状态定义

```c
typedef struct {
    uint32_t valid;        // bit0 位置, bit1 速度, bit2 精度
    int32_t  lat_e7, lon_e7;   // 1e-7 度
    int32_t  alt_mm;           // 毫米
    int32_t  ve_mm_s, vn_mm_s, vu_mm_s;  // 毫米/秒（东-北-天）
    uint32_t accuracy_mm, velocity_accuracy_mm_s;
    uint32_t sample_ms;        // 源侧采样时刻（单调）
    uint8_t  fix, source, flight_mode;
} mob_state;
```

原则：

- **`valid` 位图而非魔数**：速度为 0 与速度未知必须可区分（`valid&2 == 0` 时禁止用 0 当静止）。
- **`source`** ∈ {unavailable, gnss, injected, replay}：**注入与回放必须与真实 GNSS 区分**，
  不得把模拟数据写成实测。
- **`sample_ms` 是源侧时钟**，接收方只做同机单调差，不跨设备相减。
- 三维：高度使用 `alt_mm`，相对运动在三维求解；仅 2D 时 `vu=0` 且 `valid&4` 标记精度为 2D。

## 2 相对运动

设本机 `i`、邻居 `j`：

```
r = p_j − p_i          （东-北-天，毫米）
u = v_j − v_i          （毫米/秒）
d = |r|,  s = |u|
接近速度（正为靠近）：c = −(r·u)/d
```

**关键**：只有 `u`（相对速度）决定链路寿命；**单节点绝对速度不能用来判断链路是否将断**。
两机同速同向（`u=0`）即使各自 30 m/s，链路几何也不变化。

经纬度到局部切平面的换算（毫秒级精度足够）：

```
north_mm = Δlat_deg × 111320000
east_mm  = Δlon_deg × 111320000 × cos(平均纬度)
up_mm    = Δalt_mm
```

## 3 LET 求解

求解 `|r + u·t| = R`：

```
a = |u|²
b = 2(r·u)
c = |r|² − R²
t_exit = (−b + √(b²−4ac)) / (2a)
```

分支：

| 条件 | LET |
|---|---|
| `d ≥ R`（已在范围外） | **0** |
| `valid&2 == 0` 或 `s < 1 mm/s`（无相对运动） | **无穷**（不预测） |
| `b²−4ac < 0` | **无穷**（最近接近点仍在范围内） |
| `t_exit ≤ 0` | **无穷** |
| `t_exit > 3600 s` | **无穷**（视为稳定） |
| 其他 | `t_exit × 1000` ms |

### 3.1 一个必须记住的几何下界

从范围边界向内运动时：

```
LET ≥ 2R / |u|      （穿出对侧边界的最短时间）
```

因此 **绝对阈值在小速度下不可达**：R=120 m、|u|=60 m/s 时最短 LET ≈ 4.0 s，
此时「3 s 内 AT_RISK」永远不触发。**阈值必须由 R 与机群速度导出**，故
`mob_init()` 取默认值、`mob_limits()` 允许按编队速度重设：

```
degrade_ms  ≈ 2R / v_typ
critical_ms ≈ R / v_typ
```

## 4 不确定性与置信度

一阶误差传播（保守，取 2σ）：

```
σ_r = √(acc_i² + acc_j²)
σ_v = √(vacc_i² + vacc_j²)
σ_t = σ_r/s + (LET/1000)·(σ_v/s)        （秒）
band = 2·σ_t·1000                        （毫秒）
let_low  = max(0, LET − band)
let_high = min(CAP, LET + band)
confidence = 1000·(1 − band/LET)         （0..1000）
```

**风险判定使用 `let_low`（保守界）**，不允许用乐观估计掩盖即将断裂的链路。

## 5 链路风险状态与滞回

| 状态 | 条件（基于 `let_low`） |
|---|---|
| `GOOD` | 无穷，或 > `degrade_ms` |
| `DEGRADING` | ≤ `degrade_ms` 且 > `critical_ms` |
| `AT_RISK` | ≤ `critical_ms` |

**滞回规则（非对称）**：

- 升级（恶化）**立即生效** —— 安全优先，宁可早报。
- 降级（恢复）必须持续 `MOB_HYSTERESIS_MS`（2 s）才生效，防止单样本抖动。

`risk` 与 ND 三态**相互独立**：ND 表示"现在能不能通"，`risk` 表示"几何上还能通多久"。
禁止用 `risk` 覆盖 `LOST/HEARD/BIDIRECTIONAL`。

## 6 为什么 LET 不能等同于真实链路寿命

必须同时满足才可影响路由（P3 门槛）：

1. LET 只是**几何预测**，不包含遮挡、多径、天线姿态、干扰；
2. `R`（`range_mm`）当前是**默认几何值**，必须由实测覆盖（PDR 对距离的实测曲线）；
3. 需与 `PDR/ETX/RSSI/SNR` 联合，任何一项为「未知」时 `confidence` 必须下降；
4. 需评估预测误差（见 `EXPERIMENT_PLAN.md` 的 `Link Prediction Error`）。

## 7 Shadow Mode（本阶段唯一允许的用法）

```
现有 ND/SR 正常运行（不受影响）
   └─ 同步计算 LET / risk
        └─ 每个邻居一条 mob_shadow 记录（含 let_low/high、confidence、age、PDR/ETX）
             └─ 与 ND 实际失效事件对照，统计精确率/召回率/预警提前量
```

**只有评估达标后**才允许进入 P3 的路由影响阶段。

## 8 移动场景定义（合成，非实测）

| 场景 | 参数 | 观测量 |
|---|---|---|
| S1 稳定编队 | 同速同向，间距 40–80 m，速度 10–20 m/s | 邻居变化率≈0；LET 应多为无穷 |
| S2 双向交汇 | 两列相向，相对速度 30–50 m/s | 链路持续时间短；LET 应快速下降后归零 |
| S3 编队分裂 | 一组转向离队，相对速度 10–20 m/s | 直径突增；分区概率上升 |
| S4 重新汇合 | 分裂后反向 | 邻居恢复次序、路由重建时延 |
| S5 移动中继 | 单节点在两个分区之间往复 | 中继切换次数、修复时延 |
| S6 突然退出 | 节点在 t0 停止发送（断电） | 检测时延 vs LET 预报（应无预兆 → 用于检验误报） |
| S7 速度/航向突变 | 5 s 内 15 m/s → 25 m/s、航向 90° | 预测误差、滞回是否抑制抖动 |

所有场景由 `tools/mid_baseline/mobility/` 的脚本生成可复现轨迹（固定种子），
输出 JSONL 供 `mobility.c` 回放与评估工具消费。**这些是合成数据，不得标注为实测。**
