# M-067 V2 数据实物审计

数据源：Mendeley DOI `10.17632/bn6n2639xh.2`，V2，2025-04-30 发布；[官方页面](https://data.mendeley.com/datasets/bn6n2639xh/2)。压缩包从官方V2端点下载，长度1,077,596,067字节；四个MAT及V2手册解包后文件ID、长度和SHA-256均与官方公共API一致，详见 `simulation/outputs/E2-044/20261124-01-v2-audit/file-integrity.json` 及 `v2-official-files.json`。原始文件及float64内存映射副本位于 `data/field_feasibility_v2/`，不入Git；`data_ready.json` 保存每文件哈希和查询约定。

四个MAT变量分别为 `rem2m600s`、`rem25m600s`、`rem50m600s`、`rem80m600s`，均为MATLAB double、shape `(250,250,600)`；所有1.5亿个值有限，NaN/Inf均为0。手册称覆盖1.25 km × 1.25 km，间距5 m，每秒更新，共600帧；维度依次表示两个空间网格和时间。手册未给出可唯一校准的地理原点、轴方向及像素中心/角点关系，因此接口使用明确的抽象局部坐标：axis0=x、axis1=y、格点坐标0..1245 m，每5 m一个；最近格点、平局向上，不宣称地理映射。`t_s=0..599` 整数相对秒，对应手册标号1..600秒，不做时间或高度插值，其他高度/越界抛错。每个高度4个派生数组坐标已与原MAT逐值对比；负/越界/非整数时间测试通过。数值保持float64，不填补或裁剪。

特别限制：各高度全体最小值/计数见数组清单：2 m为 `-240.96910013008056 dBm`，出现6,070,773/37,500,000；25 m同值912,964次；50 m同值16,943次；80 m最小为-90.9554，出现1次。2 m另有3个正值（最大14.367 dBm）。手册没有定义极小重复值的语义，暂不能断言是无信号、数值地板、建筑物内部还是缺失；默认查询原样返回，后续评价必须报告是否排除此值及统计分母，并对原始值与显式预定义掩码作敏感性分析，不可默认为实测或静默删去。四层的准确极值和抽样百分位见 `array-audit.json`。

真实场随时间变化：空间5格抽样、连续秒绝对变化均值依高度依次为2.819、1.540、1.147、1.058 dB；各高度全图均值的时间跨度分别约9.08、3.72、2.06、1.74 dB（均含上述重复极小值）。此为所给射线追踪仿真数据的描述，不是无人机间通信链路测量。

手册列出静态2/10/20/30/40/50/80 m，实际V2压缩包/官方目录仅见静态10/20/30/40/50 m五文件；动态四高度齐全。静态对照可使用明确冻结的V2动态时间片，不能自行补称缺失静态文件。时间与高度对照图 `simulation/outputs/E2-044/20261124-01-v2-audit/v2-spatiotemporal-grid.png` 的色标限制为[-120,-40] dBm仅用于显示；原始数据未裁剪。手册渲染 `manual-page-1.png`、`manual-page-2.png` 同目录。

接口示例：`from simulation.field_feasibility.data_v2 import FieldV2; f=FieldV2("data/field_feasibility_v2"); f.query(0,0,2,0)` 返回 -86.754 dBm。真值整体数组仅供数据准备/离线评分，不提供给无人机策略或用来推断未来场；接口本身不是安全隔离机制。

## 在另一台电脑准备 V2 数据

仓库提供 `simulation/field_feasibility/baseline_prepare_v2.py`，依赖 Python、NumPy 与 SciPy；无需本机的 `.local` 或 `simulation/outputs`。先从[官方 V2 页面](https://data.mendeley.com/datasets/bn6n2639xh/2)取得 ZIP，然后在仓库根目录执行：

```powershell
python -X utf8 simulation/field_feasibility/baseline_prepare_v2.py --zip "D:\下载\Mendeley-V2.zip" --target data/field_feasibility_v2
```

如果本机已有四个原始 MAT、`guidemanual.pdf` 和可选派生 NPY，可改为：

```powershell
python -X utf8 simulation/field_feasibility/baseline_prepare_v2.py --source-dir "D:\已有V2缓存" --target data/field_feasibility_v2
```

也可同时提供 `--source-dir` 和 `--zip`，优先校验复用目标及源目录，缺失原始文件再从ZIP提取；单独只有NPY而没有四个原始MAT和手册（或ZIP）时不会伪称已核验原始文件。入口读取仓库已验收 `simulation/results/20261124-M067-v2-data-audit/data_ready.json` 的文件名、发布SHA256和派生数组SHA256；逐高度加载和转换，不同时加载四层。每个原始文件和派生数组都需与验收哈希一致，目录内已有文件不同、已有ready记录与验收不一致、或已有ready但资产缺失时均失败，不覆盖旧文件。转换生成的NPY也要求与已验收NPY字节哈希一致；若其他NumPy版本/平台生成格式有差异，入口会明确报错而非降低校验标准。输出目录需要与其内部暂存目录处于同一文件系统，文件发布不覆盖已有路径；失败后不会生成新的ready标记，但极端并发冲突可能留下已经成功发布且校验通过的个别新文件。

确认接口：`python -c "from simulation.field_feasibility.data_v2 import FieldV2; print(FieldV2('data/field_feasibility_v2').query(0,0,2,0))"`，预期约 `-86.754`。这是审计数据的查询示例，不是实时测量。下载、原始与派生文件均保留在任务目录，约需2.3 GB以上；首次准备还需临时空间，请根据输入和目标是否同盘预留余量。
