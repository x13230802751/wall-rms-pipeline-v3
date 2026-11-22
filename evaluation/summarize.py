# 按实验条件汇总识别和 RMS 指标，计算置信区间及方法配对差异。
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.stats import beta
from room_walls.artifacts import dump
from .metrics import summarize_wall_rows


def percentile_ci(x):
    a=np.asarray(x);a=a[np.isfinite(a)]
    return None if not len(a) else [float(v) for v in np.percentile(a,[2.5,97.5])]


def summarize_group(records,rng):
    rows=[w for r in records for w in r['walls']];out=summarize_wall_rows(rows)
    out.update(n_rooms=len(records),source=records[0]['source'],mode=records[0]['mode'],condition=records[0]['condition'],
               pipeline_failures=sum(r['status']=='failed' for r in records))
    out['room_joint_success']=float(np.mean([r['instance']['0.5']['fp']==0 and r['instance']['0.5']['fn']==0 and
                                             r['summary']['strict_joint_success']==1 for r in records]))
    k=int(round(out['room_joint_success']*len(records)));n=len(records)
    out['room_joint_success_exact_ci95']=[0. if k==0 else float(beta.ppf(.025,k,n-k+1)),
                                        1. if k==n else float(beta.ppf(.975,k+1,n-k))]
    for threshold in ['0.25','0.5','0.75']:
        s=[r['instance'][threshold] for r in records];tp=sum(x['tp'] for x in s);fp=sum(x['fp'] for x in s);fn=sum(x['fn'] for x in s)
        out['instance_'+threshold]=dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,
            recall=tp/(tp+fn) if tp+fn else None,f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.)
    main=[r['instance']['0.5'] for r in records]
    for field in ['binary_iou','best_iou_mean','split_count','merge_count']:
        values=[s[field] for s in main if s[field] is not None];out[field]=float(np.mean(values)) if values else None
    good=[w for w in rows if w.get('matched')]
    for field in ['precision','recall','visible_grid_coverage','boundary_recall','defect_recall','normal_error_deg','centroid_normal_offset_mm']:
        vals=[w[field] for w in good if w.get(field) is not None];out['mean_'+field]=float(np.mean(vals)) if vals else None
    for field in ['e_noise_mm','e_visibility_mm']:
        vals=[abs(w[field]) for w in good if w.get(field) is not None];out['ma_'+field]=float(np.mean(vals)) if vals else None
    # Room-cluster bootstrap. Every wall in the resampled room travels together.
    aggregates=[]
    for r in records:
        valid=[w for w in r['walls'] if w.get('matched')];err=np.array([w['e_selection_mm'] for w in valid])
        s=r['summary'];inst=r['instance']['0.5']
        aggregates.append([len(r['walls']),len(valid),np.sum(abs(err)),np.sum(err**2),
                           len(r['walls'])*s['success_02'],len(r['walls'])*s['strict_joint_success'],inst['tp'],inst['fp'],inst['fn'],
                           float(inst['fp']==0 and inst['fn']==0 and s['strict_joint_success']==1)])
    a=np.array(aggregates);index=rng.integers(len(a),size=(2000,len(a)));b=a[index].sum(1)
    def div(x,y):return np.divide(x,y,out=np.full_like(x,np.nan),where=y>0)
    out['ci95']={k:percentile_ci(v) for k,v in dict(valid_rate=div(b[:,1],b[:,0]),mae_selection_mm=div(b[:,2],b[:,1]),
        rmse_selection_mm=np.sqrt(div(b[:,3],b[:,1])),success_02=div(b[:,4],b[:,0]),strict_joint_success=div(b[:,5],b[:,0]),
        instance_f1=div(2*b[:,6],2*b[:,6]+b[:,7]+b[:,8]),room_joint_success=b[:,9]/len(records)).items()}
    out['ci_method']='2000 percentile resamples of room seeds; degenerate intervals are descriptive, not proof of certainty'
    return out


def paired(records,rng):
    lookup={(r['seed'],r['condition'],r['source'],r['mode']):r for r in records};groups=defaultdict(list)
    for key,a in lookup.items():
        seed,condition,source,mode=key
        if mode!='expanded':continue
        b=lookup[(seed,condition,source,'paper')];bm={w['truth_wall']:w for w in b['walls']}
        differences=[]
        for w in a['walls']:
            other=bm[w['truth_wall']]
            if w.get('matched') and other.get('matched'):
                differences.append(abs(w['e_selection_mm'])-abs(other['e_selection_mm']))
        groups[(condition,source)].append(dict(seed=seed,n=len(differences),sum=float(np.sum(differences)),
            targets=len(a['walls']),success_delta=a['summary']['success_02']-b['summary']['success_02']))
    output=[]
    for (condition,source),g in groups.items():
        count=sum(x['n'] for x in g);a=np.array([[x['sum'],x['n'],x['success_delta']] for x in g]);b=a[rng.integers(len(g),size=(2000,len(g)))].sum(1)
        values=np.divide(b[:,0],b[:,1],out=np.full(2000,np.nan),where=b[:,1]>0)
        output.append(dict(condition=condition,source=source,common_matched_walls=count,
             not_common_matched_walls=sum(x['targets']-x['n'] for x in g),
             delta_mae_expanded_minus_paper_mm=sum(x['sum'] for x in g)/count if count else None,
             delta_mae_ci95=percentile_ci(values),delta_success_02=float(np.mean([x['success_delta'] for x in g])),
             delta_success_ci95=percentile_ci(b[:,2]/len(g))))
    return output


def affected_targets(records):
    conditions={'occlusion_center','bulge25','bulge60','recess25','near_clutter','mixed','split_wall'}
    groups=defaultdict(list)
    for r in records:
        if r['condition'] in conditions:
            groups[(r['condition'],r['source'],r['mode'])].extend(w for w in r['walls'] if w['truth_wall']==1)
    return [dict(condition=k[0],source=k[1],mode=k[2],scope='Generator-affected wall 1 only; diagnostic subgroup',
                 **summarize_wall_rows(rows)) for k,rows in groups.items()]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('folder');args=ap.parse_args();folder=Path(args.folder)
    records=[json.loads(line) for line in (folder/'records.jsonl').read_text(encoding='utf-8').splitlines()]
    protocol=json.loads((folder/'protocol.json').read_text());expected=len(protocol['seeds'])*(len(protocol['conditions'])+len(set(protocol['conditions'])&set(protocol['oracle_conditions'])))*2
    if len(records)!=expected:raise ValueError(f'Incomplete run: {len(records)}/{expected}')
    unique={(r['seed'],r['condition'],r['source'],r['mode']) for r in records}
    if len(unique)!=len(records):raise ValueError('Duplicate evaluation records')
    groups=defaultdict(list)
    for r in records:groups[(r['condition'],r['source'],r['mode'])].append(r)
    rng=np.random.default_rng(904113);summary=[summarize_group(g,rng) for g in groups.values()]
    dump(folder/'condition_summary.json',summary);dump(folder/'paired_comparison.json',paired(records,rng))
    dump(folder/'affected_wall_summary.json',affected_targets(records))
    fields=['condition','source','mode','n_rooms','n_target_walls','n_valid','pipeline_failures','valid_rate','best_iou_mean',
            'mae_selection_mm','rmse_selection_mm','p95ae_selection_mm','mae_total_mm','success_02','success_05','success_10','strict_joint_success','mean_defect_recall']
    with (folder/'condition_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows({k:r.get(k) for k in fields} for r in summary)
    flat=[]
    for r in records:
        for w in r['walls']:flat.append({k:r[k] for k in ['seed','condition','source','mode']}|w)
    dump(folder/'wall_records.json',flat)
    audit=dict(evaluations=len(records),target_wall_rows=len(flat),groups=len(summary),
         max_oracle_numerical_error_mm=max(w['oracle_numerical_error_mm'] for w in flat),
         zero_or_near_zero_reference_rows=sum(w['r_obs_mm']<.1 for w in flat),
         no_global_accuracy_claim=True,physical_accuracy_validated=False)
    dump(folder/'audit.json',audit);print(json.dumps(audit))


if __name__=='__main__':main()
