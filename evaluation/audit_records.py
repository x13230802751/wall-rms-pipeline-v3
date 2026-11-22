# 核对实验样本、误差统计、源码哈希和合成数据复现结果。
"""Independently check saved denominators, formulas, hashes and provenance."""
import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
import numpy as np
from .scenes import generate


def main():
    ap=argparse.ArgumentParser();ap.add_argument('folder');args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];folder=Path(args.folder)
    protocol=json.loads((folder/'protocol.json').read_text())
    for field,paths in [('source_hashes',None),('evaluation_hashes',{'evaluation/metrics.py','evaluation/scenes.py','evaluation/runner.py'})]:
        for name,sha in protocol[field].items():
            if paths is not None and name not in paths:continue
            current=hashlib.sha256((root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            assert current==sha,('Changed experiment source',name)
    records=[json.loads(line) for line in (folder/'records.jsonl').read_text(encoding='utf-8').splitlines()]
    expected={(seed,c,source,mode) for seed in protocol['seeds'] for c in protocol['conditions']
              for source in ['geometry']+(['oracle_semantics'] if c in protocol['oracle_conditions'] else [])
              for mode in ['expanded','paper']}
    observed={(r['seed'],r['condition'],r['source'],r['mode']) for r in records}
    assert expected==observed and len(records)==len(expected),'Missing or duplicate evaluation'
    groups=defaultdict(list);max_identity=0.
    for r in records:
        groups[(r['condition'],r['source'],r['mode'])].append(r)
        assert len(r['walls'])==(6 if r['condition']=='l_room' else 4)
        assert r['instance']['0.5']['tp']==sum(w['matched'] for w in r['walls'])
        for w in r['walls']:
            if not w['matched']:
                assert w['e_selection_mm'] is None and w['e_total_mm'] is None
                continue
            assert math.isclose(w['e_selection_mm'],w['r_pred_mm']-w['r_obs_mm'],abs_tol=1e-12)
            residual=abs(w['e_total_mm']-sum(w[k] for k in ['e_selection_mm','e_noise_mm','e_visibility_mm']))
            max_identity=max(max_identity,residual);assert residual<1e-9
    summaries=json.loads((folder/'condition_summary.json').read_text())
    assert len(summaries)==len(groups)
    for s in summaries:
        rows=groups[(s['condition'],s['source'],s['mode'])];walls=[w for r in rows for w in r['walls']]
        valid=[w for w in walls if w['matched']];errors=np.array([w['e_selection_mm'] for w in valid])
        assert s['n_rooms']==len(rows) and s['n_target_walls']==len(walls) and s['n_valid']==len(valid)
        for name,k in [('success_02',.2),('success_05',.5),('success_10',1.)]:
            assert math.isclose(s[name],sum(abs(errors)<=k)/len(walls),abs_tol=1e-12)
        for key,value in [('mae_selection_mm',float(np.mean(abs(errors))) if len(errors) else None),
                          ('rmse_selection_mm',float(np.sqrt(np.mean(errors**2))) if len(errors) else None)]:
            assert s[key] is None if value is None else math.isclose(s[key],value,abs_tol=1e-12)
        for threshold in ['0.25','0.5','0.75']:
            for k in ['tp','fp','fn']:assert s['instance_'+threshold][k]==sum(r['instance'][threshold][k] for r in rows)
        room_pass=[]
        for r in rows:
            room_pass.append(r['instance']['0.5']['fp']==0 and r['instance']['0.5']['fn']==0 and
                             all(w['matched'] and w['iou']>=.75 and w['precision']>=.95 and w['recall']>=.95
                                 and abs(w['e_selection_mm'])<=.2 for w in r['walls']))
        assert math.isclose(s['room_joint_success'],sum(room_pass)/len(rows),abs_tol=1e-12)
    regenerated=[]
    cases=[(protocol['seeds'][0],'clean'),(protocol['seeds'][len(protocol['seeds'])//2],'near_clutter'),(protocol['seeds'][-1],'l_room')]
    for seed,condition in cases:
        if condition not in protocol['conditions']:continue
        scene=generate(seed,condition);record=next(r for r in records if r['seed']==seed and r['condition']==condition)
        for k in ['input_sha256','truth_sha256']:assert scene[k]==record[k]
        regenerated.append([seed,condition])
    result=dict(status='passed',evaluations=len(records),wall_rows=sum(len(r['walls']) for r in records),
                condition_groups=len(summaries),max_error_identity_residual_mm=max_identity,
                source_hashes_verified=True,regenerated_hash_cases=regenerated,
                checks=['missing/duplicate cases','failure denominators','wall counts','error decomposition',
                        'conditional MAE/RMSE','unconditional error success','instance counts','whole-room success','source and data hashes'],
                physical_ground_truth_verified=False)
    (folder/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
