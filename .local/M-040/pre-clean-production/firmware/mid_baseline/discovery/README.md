# 一跳自主邻居模式

独立ESP32-S3入口`idf/`，保留原`edge/`静态部署包与MID核心。OLED API2；UART460800/8N1，控制台仍是`mid.serial.v1` JSONL。每车只接本机一块板，不需要网页或跨主机IP。第一次给各板相同组与信道即可，配置不含对方MAC、节点标签或转发表。

初次配置（先`info`核实际板身份、`stop`核radio=false；如果有静态profile，先`deployment_clear`）：

```json
{"cmd":"discover_config","nonce":"setup-1","group":27,"channel":6,"autostart":true}
{"cmd":"neighbors","nonce":"list-1"}
{"cmd":"neighbor","nonce":"watch-1","node_id":"<从列表实际读出的MAC>"}
{"cmd":"send","nonce":"send-1","dst":"<列表中双向确认的MAC>","payload_hex":"00ffe4bda0e5a5bd"}
```

`discover_config`只在inactive/无在途发送且无静态profile时写NVS `mid_neighbor/cfg`。group为非0 uint32，channel输入1..13（实际可用范围受SDK区域/硬件限制，失败返回saved_but_start_failed；台架用6），autostart必须是bool。配置成功且autostart=true会启动；以后复位读取本板配置自启，无需主机重新下发。`discover_start`显式恢复。`stop`停止射频、清未发队列，等待在途回调后radio=false，保留NVS，因此复位仍按autostart启动。`discover_clear`只能在已停止时删该键并恢复原MID默认信道6；不擦NVS分区或旧数据。若NVS配置损坏或与静态profile并存，启动失败保持idle，显式清相应模式后再选，不能静默覆盖。

`neighbors`返回最多8个本次运行实际见过的MAC（含lost行），`neighbor(node_id)`只查本板状态，未知返回unknown；均不发无线探针。每行包括当前boot_id、state=heard/bidirectional/lost、last_seen_ms、age_ms、last_confirmed_ms。这些都是本板开机单调时间，不是对方时钟；USB在线不能证明无线邻居在线。9秒没有新回显证明则降为heard且不能发业务，12秒没有有效新HELLO或新证明则lost。状态按查询时刻计算，无须逐邻居主动探测。最多8个不同MAC，本次运行不自动驱逐lost行；表满记录neighbor_table_full，可停止/重启发现模式重新建表。

`neighbor_probe(node_id)`对已见MAC排一次HELLO复核，无同步在线保证；全局1秒最多一次，返回后再读neighbor。周期HELLO继续，探针不重置衰老计时。应用应等待两边均bidirectional再发首包；单边已收到HELLO不表示对方已经确认自己。没有新增订阅传输；应用可本地读列表/关注指定MAC。

控制格式：复用MID1帧头，但kind1/ttl1的17字节body为`ND01`、group u32LE、type u8（1 HELLO、2 echo ACK）、目标boot u32LE、回显HELLO seq u32LE；合计41字节应用帧。周期广播HELLO启动抖动0–500ms，之后2–3秒；同组接收方只在物理来源MAC等于origin时响应，新序号才回复ACK，单源回复最小500ms。ACK必须回显本板当前boot及最近4个HELLO序号，且每邻居同挑战只更新一次证明；ACK不再引发ACK。收到新boot即清旧确认，运行内记最近4个旧boot拒绝迟到旧控制帧。无认证、加密或跨掉电持久抗重放；group用于隔离，不是密码。不同组不能互证。

健康稳定N个互听节点，每节点每2–3秒产生1个广播HELLO，且每轮最多为其余N-1个HELLO各回1个单播ACK，即常态全网约N²/(2..3)帧/秒，非空口时间。每个提交帧41字节，不含802.11/ESP-NOW封装、竞争与硬件重试。手动探针和其回复另计。`stats`有control_hello/ack_generated/received、control_submitted/link_ok/link_fail、control_rejected和neighbor_table_full；generated是进入生成路径，不等于已发，submitted是esp_now_send接纳，link_ok不是目的业务确认。可用实际统计差值计算控制应用字节=41×control_submitted差值。软件没有给每个邻居另设高频轮询；无线回调队列丢失/超时仍沿旧入口保护停止。

发现模式业务沿原MID1 kind2，源MAC/当前boot/seq和0–160字节原始载荷保持，目的MAC来自实际列表。发送只准当前bidirectional邻居；接收还要求实际来源=origin、当前邻居boot匹配、目的为本板。只一跳，不转发、不求MID路由、不自动重发；64项本机易失去重。`send`回执packet_seq/origin_boot是本地接纳，目的`rx_local.payload_hex`是本机接收证据，源没有端点ACK。互证超时后拒绝新发送；已提交或已排队帧不能当作被物理撤回。重新进入发现模式会清邻居/去重缓存，但本板boot与业务seq不变，真正复位才换boot。

切回原MID：stop并等radio=false，discover_clear，再沿原start(publisher,publisher_boot)/config或静态deploy。新模式配置不写对方MAC；A/B/C字母只作旧OLED标签，不用于邻居身份。Ubuntu服务/串口多客户端归E2；真实RF晚加入、停止、重启及Ubuntu物理拔插归H，本机C检查不代替这些证据。
