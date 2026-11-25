# BUILD 20261125 link-2a

- images/mid_edge.bin  sha256 363D79FFEA9A3AE1876BE174C0EED72BBD593680339166FA94882EDB6867D028
- 阶段 2a：加入 link_backend 抽象（link->send），espnow 为唯一实现
- 三处发送（route_pump/telemetry_pump/pump）统一走 link->send；ensure_peer 收进后端
- 新增计数 link_tx_ok / link_tx_fail / link_tx_oversize，info 回显 link_backend
- 预期行为与上一版完全一致（默认 espnow，协议层未改）
