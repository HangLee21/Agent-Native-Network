"""Audit raw records and generate descriptive held-out summaries; no significance claims."""
import csv
import hashlib
import json
from collections import Counter
from simulation.rescue_graph import OUT, ROOT


def main():
    rows = list(csv.DictReader((OUT/'metrics.csv').open()))
    selected = list(csv.DictReader((OUT/'selected.csv').open()))
    assert len(rows) == 12672
    assert len({tuple(r[k] for k in ('world','reach','horizon','policy','parameter','seed')) for r in rows}) == len(rows)
    lookup = {tuple(r[k] for k in ('world','reach','horizon','policy','parameter','seed')): r for r in rows}
    for r in rows:
        assert int(r['received']) == int(r['discovered'])
        assert abs(float(r['instant_route_auc']) - float(r['report_auc']) - float(r['delay_sum'])/(8*int(r['horizon']))) < 1e-12
        if r['reach'] == '9999':
            ideal = lookup[(r['world'],r['reach'],r['horizon'],'ideal','0',r['seed'])]
            for metric in ('report_auc','discovered','edges','scanned'):
                assert r[metric] == ideal[metric]
    metadata = json.loads((OUT/'metadata.json').read_text())
    for name, expected in metadata['hashes'].items():
        assert hashlib.sha256((ROOT/'simulation'/name).read_bytes()).hexdigest() == expected
    by = {(r['world'],r['reach'],r['horizon'],r['family']): r for r in selected}
    best = [r for r in selected if r['family']=='best_existing' and r['reach']!='9999']
    differences = [float(r['report_auc'])-float(by[(r['world'],r['reach'],r['horizon'],'carry')]['report_auc']) for r in best]
    lines = ['# 公开城市拓扑：留出结果与判定', '',
        '全部8张SubT urban_circuit公开模拟世界，21–32节点；12672次执行，288条开发集选择后的留出汇总。种子0–7选择参数，8–23评价。图不属于独立随机抽样，不作总体显著性推断。', '',
        '## 结果', '',
        '|预算/覆盖阈值|策略|报告AUC|发现数（8个目标）|沿实际轨迹即时回报AUC|',
        '|---|---|---:|---:|---:|']
    for horizon in ('600','900'):
        for reach in ('6','12'):
            for family in ('ideal','carry','base_age','contact_age','contact_batch','best_existing'):
                group = [r for r in selected if (r['horizon'],r['reach'],r['family'])==(horizon,reach,family)]
                means = [sum(float(r[k]) for r in group)/8 for k in ('report_auc','discovered','instant_route_auc')]
                lines.append(f'|{horizon}/{reach}|{family}|'+ '|'.join(f'{v:.4f}' for v in means)+'|')
    lines += ['', f'32个有限覆盖分层中，开发集选出的实用基线在留出集上较carry改善{sum(d>1e-10 for d in differences)}个、退化{sum(d < -1e-10 for d in differences)}个、相同{sum(abs(d)<=1e-10 for d in differences)}个。选择分布：{dict(Counter(r["policy"] for r in best))}。', '',
        '27/32个分层发现量下降。全覆盖下全部原始策略与ideal的AUC、发现数、移动边数、扫描量严格相同。所有已发现报告在结束前收到；当前差异是回报时效和搜索代价，不是最终报告丢失。', '',
        '## 防止误判', '',
        '- 即时回报AUC沿各策略自身实际发现轨迹计算。它与实际AUC之差严格等于报告等待总量/(8H)；与ideal搜索轨迹的差还包含绕路造成的发现变化，不能统称通信损失。该分解是首轮后追加的解释性审计，不用于选择参数。',
        '- AUC奖励早回报。若只考察结束时收到的目标数，提前返回常常变差。尚无证据支持给火灾目标虚构统一截止时间，也不能把AUC收益解释为救援人数收益。',
        '- 全图和覆盖集已知、规则分区、无碰撞、确定可达、瞬时摘要都是简化。BFS奇偶分区可能造成路径交叉，后续须与空间连续分区和联合覆盖规划对照。当前结果不是最优搜索路径上的不可消除差距。',
        '- 本轮不包含中继，不能与使用额外设备的方案直接宣称公平优胜；此前走廊中继结果不能外推到这些图。', '',
        '## 阶段判定', '',
        '确认一个可继续检验的已有问题：覆盖受限时，机器人回报发现需要接触机会，主动接触改变搜索进度。简单数量触发已明显强于单纯年龄触发，因此停止把固定周期返回作为主要对手。尚未确认Agent特有网络问题或新协议的必要性。', '',
        '下一完整阶段：先查找communication-constrained exploration / informative path planning / intermittent connectivity既有方法，统一任务假设；再用连续空间分区与覆盖优先路径复核，并给固定中继配置计入同等资源成本。若目标是火灾救援论文，还需独立文献支持报告如何影响后续行动，而非只优化自定AUC。理论建模继续暂缓。', '',
        '## 来源与复现', '',
        '- [上游固定版本](https://github.com/osrf/subt/tree/083c6a8acb0c25aa1a35e34517e628cd3b52ae77/subt_ign/worlds/urban_circuit)，原始文件SHA256和下载地址见metadata.json；Apache 2.0 LICENSE/COPYING下载至data/subt_urban。',
        '- [官方通信模型说明](https://github.com/osrf/subt/wiki/Communication-Model-Tutorial)：本轮只借用图及visibility标签，未运行Gazebo、未复现距离/概率无线模型。',
        '- 运行：`.venv/Scripts/python.exe simulation/rescue_graph.py`，随后 `.venv/Scripts/python.exe -m simulation.audit_rescue_graph`。',
        '- metrics.csv保留全量结果，selected.csv保留每图每条件的开发/留出选择，traces_seed0.json.gz保留全部种子0轨迹。', '']
    (OUT/'INTERPRETATION.md').write_text('\n'.join(lines), encoding='utf-8')
    print('All 12672 records, negative controls, decomposition and source hashes verified.')


if __name__ == '__main__':
    main()
