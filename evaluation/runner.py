# 运行固定配置的合成房间评测，记录各墙结果、误差和失败情况。
"""Frozen-config simulation evaluation with every target wall in the denominator."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from room_walls.config import Config
from room_walls.discovery import discover
from room_walls.measurement import measure_wall
from room_walls.vendor.geometry import fit_plane
from room_walls.artifacts import dump,empty_output
from .scenes import generate,CONDITIONS
from .metrics import instance_scores,reference_plane,decompose,relative_error,summarize_wall_rows

ROOT=Path(__file__).resolve().parents[1]


def hashes(folder):
    return {str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for p in sorted(folder.rglob('*.py'))}


def reference_data(scene):
    refs={}
    for k,full in scene['full_refs'].items():
        ids=np.flatnonzero(scene['instances']==k);p=scene['points'][ids]
        obs=reference_plane(p);visible=reference_plane(scene['clean'][ids])
        c,n,_=fit_plane(p);oracle=float(np.sqrt(np.mean(((p-c)@n)**2))*1000)
        refs[k]=dict(ids=ids,obs=obs,visible=visible['rms_mm'],full=full,
                     oracle_numerical_error_mm=abs(oracle-obs['rms_mm']))
    return refs


def evaluate(scene,result,refs,mode,status,error=None):
    predictions=[] if result is None else [w[mode+'_indices'] for w in result['walls']]
    scores={str(t):instance_scores(scene['instances'],predictions,t) for t in (.25,.5,.75)}
    primary=scores['0.5'];pairs={r:c for r,c in primary['pairs']};rows=[]
    for row,k in enumerate(primary['gt_ids']):
        ref=refs[k];base=dict(truth_wall=k,matched=row in pairs,r_full_mm=ref['full'],
            r_visible_mm=ref['visible'],r_obs_mm=ref['obs']['rms_mm'],
            oracle_numerical_error_mm=ref['oracle_numerical_error_mm'],
            has_defect=bool(np.any(scene['defect'][ref['ids']])),defect_recall=None)
        if row not in pairs:
            base.update(e_selection_mm=None,e_total_mm=None,iou=0.,precision=0.,recall=0.,
                        failure_reason=error or 'No one-to-one instance match at IoU >= 0.5')
            rows.append(base);continue
        col=pairs[row];w=result['walls'][col];ids=predictions[col]
        measured=measure_wall(scene['points'],w,mode=mode);tp=int(primary['intersections'][row,col])
        trueids=ref['ids'];retained=np.intersect1d(ids,trueids,assume_unique=True)
        cell_gt=np.unique(np.floor(scene['uv'][trueids]/.1).astype(int),axis=0)
        cell_pred=np.unique(np.floor(scene['uv'][retained]/.1).astype(int),axis=0)
        boundary=trueids[scene['boundary'][trueids]];defect=trueids[scene['defect'][trueids]]
        normal=np.asarray(measured['plane_normal']);dot=float(np.clip(abs(normal@ref['obs']['normal']),0,1))
        base.update(predicted_wall=w['id'],n_selected=len(ids),precision=tp/len(ids),recall=tp/len(trueids),
            iou=float(primary['iou_matrix'][row,col]),visible_grid_coverage=len(cell_pred)/len(cell_gt),
            boundary_recall=float(np.mean(np.isin(boundary,ids))) if len(boundary) else None,
            defect_recall=float(np.mean(np.isin(defect,ids))) if len(defect) else None,
            r_pred_mm=measured['rms_mm'],normal_error_deg=float(np.rad2deg(np.arccos(dot))),
            centroid_normal_offset_mm=float(abs((ref['obs']['center']-measured['plane_center_m'])@normal)*1000),
            relative_selection_error_pct=relative_error(measured['rms_mm'],ref['obs']['rms_mm']))
        base.update(decompose(measured['rms_mm'],ref['obs']['rms_mm'],ref['visible'],ref['full']))
        if abs(base['e_selection_mm']+base['e_noise_mm']+base['e_visibility_mm']-base['e_total_mm'])>1e-9:
            raise AssertionError('Error decomposition identity failed')
        rows.append(base)
    serial={}
    for threshold,s in scores.items():
        serial[threshold]={k:v for k,v in s.items() if k not in ['gt_ids','pairs','iou_matrix','intersections','gt_sizes','pred_sizes']}
    return dict(mode=mode,status=status,error=error,instance=serial,
                matching_iou_matrix=primary['iou_matrix'].tolist(),walls=rows,summary=summarize_wall_rows(rows))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--count',type=int,default=20)
    ap.add_argument('--conditions',default=','.join(CONDITIONS));ap.add_argument('--start-seed',type=int,default=2001)
    args=ap.parse_args();out=empty_output(args.out);out.mkdir(parents=True,exist_ok=True)
    conditions=args.conditions.split(',')
    if args.count<1 or any(c not in CONDITIONS for c in conditions):raise ValueError('Invalid count/conditions')
    prod_hashes=hashes(ROOT/'room_walls')
    protocol=dict(schema_version=1,source_commit=None,revision_date='2026-11-22',source_snapshot='Standalone publication; exact tested working files identified by source_hashes and evaluation_hashes',source_hashes=prod_hashes,
        evaluation_hashes=hashes(ROOT/'evaluation'),config=Config().to_dict(),seeds=list(range(args.start_seed,args.start_seed+args.count)),
        conditions=conditions,oracle_conditions=['near_clutter','cabinet_floor','mixed'],matching_thresholds=[.25,.5,.75],
        error_thresholds_mm=[.2,.5,1.],grid_mm=100,bootstrap_unit='synthetic_room_seed',bootstrap_replicates=2000,
        note='Synthetic random rooms, not independent physical buildings; external semantics are oracle labels, not learned predictions')
    dump(out/'protocol.json',protocol);start=time.perf_counter();count=0
    with (out/'records.jsonl').open('w',encoding='utf-8') as f:
        for seed in protocol['seeds']:
            for condition in conditions:
                scene=generate(seed,condition);refs=reference_data(scene);cfg=Config(up=scene['up'])
                sources=['geometry']+(['oracle_semantics'] if condition in protocol['oracle_conditions'] else [])
                for source in sources:
                    before=time.perf_counter();result=None;error=None;status='completed'
                    try:result=discover(scene['points'],cfg,labels=scene['labels'] if source=='oracle_semantics' else None)
                    except ValueError as e:status='failed';error=str(e)
                    discover_seconds=time.perf_counter()-before
                    for mode in ('expanded','paper'):
                        rec=evaluate(scene,result,refs,mode,status,error)
                        rec.update(seed=seed,condition=condition,source=source,input_points=len(scene['points']),
                            input_sha256=scene['input_sha256'],truth_sha256=scene['truth_sha256'],
                            discovery_seconds=discover_seconds,noise_sigma_mm=scene['noise_sigma_mm'])
                        f.write(json.dumps(rec,ensure_ascii=False,allow_nan=False)+'\n');f.flush();count+=1
                print(f'{seed} {condition}: {status} | {count} evaluations | {time.perf_counter()-start:.1f}s',flush=True)
    if hashes(ROOT/'room_walls')!=prod_hashes:raise AssertionError('Production code changed during evaluation')
    dump(out/'execution.json',dict(evaluations=count,runtime_seconds=time.perf_counter()-start,production_code_unchanged=True))


if __name__=='__main__':main()
