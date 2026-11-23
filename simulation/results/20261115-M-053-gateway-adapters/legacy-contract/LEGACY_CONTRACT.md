# 旧 RHF 接收兼容合同（历史实测边界）

- 设备 RHF2S008；2026-11-13 实测 gateway EUI `b827ebfffe32e2c1`，其历史有效 `local_conf.json` 保存 `server_address=192.168.137.10`、`serv_port_up=1680`、`serv_port_down=1680`。它是网关发送的固定目标；若其配置仍未改变，电脑端必须在该地址/网络可达并监听 UDP 1680，才能接到旧网关报文。不能假设被动监听能自动改变包的目的地址。此为历史保存快照，当前设备已取下，现存配置未经重新读取。
- 转发使用 Semtech UDP 协议版本 2：头部 `02 | token[2] | type[1] | EUI[8]`；`PUSH_DATA type=0` 收到后向报文来源回复 `02 | 同token | 01`，`PULL_DATA type=2` 回复 `02 | 同token | 04`。ACK应由相同接收socket返回；不改变token，不能要求网关安装新服务。
- `PUSH_DATA` 后接UTF-8 JSON，其 `rxpk` 数组携带 `data`（base64）、`size`、`stat` 等；LRN1二进制帧的解析/CRC沿用现有decoder，不重定义。历史实收为 `stat=1`、470.5MHz、SF7BW125、4/5；样本见保存JSONL，字段 `b64` 转为 Semtech `data` 用于合成UDP回环，来源需如实标记历史帧重封装，不是当前RF接收。
- 历史配置曾放开CRC转发标志，当前电脑端旧实现仍仅将 `stat=1` 接受为LRN1；这两者不能混同。未知/损坏帧不得变成有效节点或刷新旧数据。
- 旧网关自身无需 HTTP；已部署的 `/api/v1/appliance` / `/api/v1/lora/topology` 和UDP发现属于另一种已有服务模式，仅对实际存在该服务的设备适配。先前本项目新网关初始化尚未完成，不能把候选服务视为旧RHF已部署。
- 默认接收/可视化不自动启用下行；旧下行功能及显式配置不能由适配器隐式扩权。
- 不修改网关、板固件/NVS、LRN1、原Semtech报文或原固定发送目的地；本次只修改电脑端。IP/EUI/连接状况为已保存的历史证据而非本轮在线测量。

来源文件SHA256见 SOURCE.json。本记录不对旧网关当前可达、当前配置或已部署HTTP作断言。
