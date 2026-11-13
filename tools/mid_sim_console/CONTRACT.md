# M-022同源接口（E2）

服务127.0.0.1:8767，静态首页优先research/agent_native_network/mid_sim_console/index.html。默认/校验唯一来源为H custom.catalog/get_defaults/normalize_settings/compile_scenario，不复制范围或单位。

- GET /api/status：ok,busy,active_run_id,runs（id/state/url），mode=software_simulation。
- GET /api/presets：H catalog原样，附ok=true；GET /api/defaults?preset=normal返回ok/settings/catalog（或省catalog），亦支持GET /api/presets/<preset>。
- POST /api/validate {settings}：返回ok/settings/summary/settings_sha256/scenario。只预览不运行。
- POST /api/run {settings}：冻结normalize后的完整设置及场景，返回202 {ok,run_id,state,status,url,result_url}。每次唯一新目录，不复用旧曲线，不执行来自客户端的命令或文件名。每次只一个真实paired运行，busy409。
- GET /api/runs/<id>：ok/run_id/state/status/settings/summary/result/error/urls。状态queued/running/completed/failed/cancelled。
- POST /api/runs/<id>/cancel {}（亦兼容stop）：停止该计算子进程，不改别的run，重复取消幂等。结束已有run不重跑。
- GET /api/runs/<id>/result：本次真实runner结果；/results/<id>/...只读该已分配结果根下HTML/JS/CSS/JSON/SVG/PNG/CSV/JSONL，禁止路径穿越。首页到此同源结果/回放。

E1建议CLI（以生产者交付为准薄适配）：现有E1-016 venv Python调用simulation/mid_link_console/runner/run.py --settings <E2冻结settings.json> --output <E2新run/experiment>。输出只使用此新空目录，结果result.json/summary.json/replay.json/index.html若有按真实字段透传。E2保留stdout/stderr、settings/scenario、RUN_MANIFEST、子进程返回码；120秒墙时，CPU库最多2线程。无串口/硬件/既有M021运行调用。

实际已接E1 `runner/pair.py:run_pair`，固定worker.py导入pair（非run），cancel.flag传可调用取消检查；两秒未收尾则结束子进程。INDEX.status必须complete才可完成，failed/cancelled不会由进程0误报成功。E2对真实destination_rx/源payload核对应后生成view.json/index.html：result.arms、seconds、events、模拟端到端时延、冻结settings具备；/results/<id>/为实际事件回放/曲线。GET /api/catalog为/presets别名，附H生成preset_settings，方便D共用默认。

页面打开、改草稿、validate/default/reset不产生run；仅显式点击运行。取消不能重发；旧run设置冻结展示，当前草稿不修改旧结果。H边参数窗口半开，双向是两个显式有向行。高级单向/多边均传H同一结构。
