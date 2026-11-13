# ABC设备准备更新：C原程序备份

2026-11-06，D-015。此侧记补充已交审的ABC_ADDENDUM.md，替代其中“C备份正在执行”的状态；不改来源审计、guide-1.0旧副本或已交审操作说明。

H已交C完整备份记录：真实MAC `90:da:72:48:a4:e0`，四段共4,194,304bytes，230400波特率，合并与设备整片MD5均为`4c81d36f5147fc71b2773d56bb7c9ded`，记录SHA256为`e429df1e9651fd44a645f716ebfa71610c02adce670731d72ec433a41feda353`。D核`hardware/mid_baseline/BACKUP_STATUS_20261106_ABC.json`的C字段与H14号summary一致，backup_manifest对应MAC/长度/摘要一致；D未重新读取设备或私有备份原字节。

来源为`simulation/outputs/H-005/20261106-14-C-segmented/`的summary/backup_manifest/RUN_MANIFEST及上述状态侧记。原程序字节仅由H保存在本机私有忽略目录，本页不提供原字节链接；A/B旧备份保留。

H记录设备累计458.360/1500秒，C增量220.017/600秒；Flash/eFuse写0、RF0，全部端口已关闭，成功后一次正常复位，应用身份未验证。此次完成的是备份准备，不能写成新MID已经烧录、OLED正常或三板互通。

E1四组真实配置和package-01仍按前次固定hash使用；离线boot1/seq1编码禁止投设备。后续由H在E2具体native方案及C对应包/场景无阻断齐备后执行，实测结果由H/E2冻结交接，D不轮询或后台等待。
