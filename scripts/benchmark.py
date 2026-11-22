# 运行基础合成房间基准，评价墙面识别和 RMS 测量并记录失败。
"""Independent synthetic instance/measurement evaluation; failures are recorded."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from fixtures import room,config
from room_walls.discovery import discover
from room_walls.measurement import measure_wall
from room_walls.artifacts import empty_output,dump


def independent_rms(p):
    q=p-p.mean(0)
    _,vectors=np.linalg.eigh(q.T@q/len(q))
    # Evaluate residuals with the independently obtained normal. Taking sqrt of
    # a nearly-zero covariance eigenvalue loses precision for rotated flat walls.
    return float(np.sqrt(np.mean((q@vectors[:,0])**2))*1000)


def cases():
    for rms in (0.,.5,1.8,5.):
        p,t,l=room(roughness_mm=rms);yield f'clean_{rms}mm',p,t,l,False,None
    p,t,l=room(roughness_mm=0,bulge=True);yield 'bulge_25mm',p,t,l,False,None
    for sigma in (.5,2.):
        p,t,l=room();p=p+np.random.default_rng(13).normal(0,sigma/1000,p.shape)
        yield f'noise_{sigma}mm',p,t,l,False,None
    for fraction in (.5,.2):
        p,t,l=room();keep=np.random.default_rng(31).random(len(p))<fraction
        yield f'sparse_{fraction}',p[keep],t[keep],l[keep],False,None
    p,t,l=room();keep=~((t==1)&(p[:,1]>.8)&(p[:,1]<1.8)&(p[:,2]>.8)&(p[:,2]<1.8))
    yield 'occluded_patch',p[keep],t[keep],l[keep],False,None
    p,t,l=room(clutter=True);yield 'floating_board',p,t,l,False,None
    p,t,l=room(roughness_mm=0)
    a,z=np.meshgrid(np.arange(.7,1.2,.04),np.arange(1.,1.5,.04));clutter=np.c_[np.full(a.size,.03),a.ravel(),z.ravel()]
    p=np.vstack([p,clutter]);t=np.r_[t,np.full(len(clutter),-1)];l=np.r_[l,np.full(len(clutter),12)]
    yield 'near_clutter_geometry',p,t,l,False,None
    yield 'near_clutter_semantics',p,t,l,True,None
    p,t,l=room();theta=.47;r=np.array([[1,0,0],[0,np.cos(theta),-np.sin(theta)],[0,np.sin(theta),np.cos(theta)]])
    yield 'rotated_gravity',p@r.T+[2,3,8],t,l,False,tuple(r[:,2])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='outputs/synthetic_benchmark');args=parser.parse_args()
    out=empty_output(args.out);out.mkdir(parents=True,exist_ok=True);records=[]
    for name,p,truth,labels,semantic,up in cases():
        cfg=config(**({} if up is None else {'up':up}));start=time.perf_counter()
        record=dict(case=name,input_points=len(p),input_sha256=hashlib.sha256(p.tobytes()).hexdigest(),
                    mode='external_semantics' if semantic else 'geometry',config=cfg.to_dict(),walls=[])
        try:
            r=discover(p,cfg,labels=labels if semantic else None)
            overlaps=np.array([[np.sum(truth[w['expanded_indices']]==k) for w in r['walls']] for k in range(1,5)])
            rows,cols=linear_sum_assignment(-overlaps)
            matched=set()
            for row,col in zip(rows,cols):
                k=int(row+1);w=r['walls'][col];ids=w['expanded_indices'];tp=int(overlaps[row,col]);nt=int(np.sum(truth==k))
                if tp==0:continue
                matched.add(k);m=measure_wall(p,w);paper=measure_wall(p,w,mode='paper')
                reference=independent_rms(p[truth==k]);same_set=independent_rms(p[ids])
                record['walls'].append(dict(truth_wall=k,predicted_wall=w['id'],precision=tp/len(ids),recall=tp/nt,
                    iou=tp/(nt+len(ids)-tp),rms_mm=m['rms_mm'],paper_rms_mm=paper['rms_mm'],
                    reference_observed_wall_rms_mm=reference,absolute_error_mm=abs(m['rms_mm']-reference),
                    independent_same_set_difference_mm=abs(m['rms_mm']-same_set)))
            record.update(status='completed',predicted_walls=len(r['walls']),missed_truth_walls=sorted(set(range(1,5))-matched),
                          extra_candidates=len(r['walls'])-len(matched),warnings=r['warnings'])
        except ValueError as e:record.update(status='failed',error=str(e),missed_truth_walls=[1,2,3,4])
        record['runtime_seconds']=time.perf_counter()-start;records.append(record)
        print(name,record['status'],record.get('predicted_walls'),flush=True)
    metric_rows=[w for r in records for w in r['walls']]
    summary=dict(cases=len(records),completed_cases=sum(r['status']=='completed' for r in records),
                 matched_walls=len(metric_rows),max_independent_same_set_difference_mm=max(w['independent_same_set_difference_mm'] for w in metric_rows),
                 max_selection_error_mm=max(w['absolute_error_mm'] for w in metric_rows),
                 reference_definition='Independent covariance-eigenvector fit and residual RMS of all observed true wall points; noise included, not physical scanner-free truth',
                 labels_provenance='Synthetic oracle labels, not predictions from a trained model',
                 failure_policy='All scenarios retained; no tuning to official RMS references')
    dump(out/'records.json',records);dump(out/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=True))


if __name__=='__main__':main()
