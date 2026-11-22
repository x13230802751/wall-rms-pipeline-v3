# 改变随机种子和恢复厚度，检查官方点云测量结果的稳定性。
"""Official scans: repeatability and sensitivity only, not GT accuracy."""
import argparse
from dataclasses import replace
from pathlib import Path
import time
import numpy as np
from room_walls.artifacts import load_metric_cloud,dump,empty_output
from room_walls.config import Config
from room_walls.discovery import discover
from room_walls.measurement import measure_wall
from .metrics import instance_scores


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    out=empty_output(args.out);out.mkdir(parents=True,exist_ok=True);records=[]
    for room in ['M26','M04']:
        points,sha=load_metric_cloud(str(Path(args.archive).resolve())+'::'+room+'.pcd','m')
        baseline=discover(points,Config());truth=np.zeros(len(points),int)
        base_rms={}
        for i,w in enumerate(baseline['walls'],1):
            truth[w['expanded_indices']]=i;base_rms[i]=measure_wall(points,w)['rms_mm']
        settings=[(f'seed_{s}',Config(seed=s)) for s in [7023,11,29,47,101]]
        settings += [(f'recovery_{r}mm',Config(recovery_mm=r)) for r in [20.,100.]]
        for name,cfg in settings:
            t=time.perf_counter();result=discover(points,cfg)
            match=instance_scores(truth,[w['expanded_indices'] for w in result['walls']],.5)
            pairs={r:c for r,c in match['pairs']};rows=[]
            for row,k in enumerate(match['gt_ids']):
                rec=dict(baseline_wall=baseline['walls'][row]['id'],matched=row in pairs,baseline_rms_mm=base_rms[k])
                if row in pairs:
                    col=pairs[row];w=result['walls'][col];m=measure_wall(points,w)
                    rec.update(predicted_wall=w['id'],point_iou_to_baseline=float(match['iou_matrix'][row,col]),
                               rms_mm=m['rms_mm'],change_mm=m['rms_mm']-base_rms[k],n_selected=m['n_selected'])
                rows.append(rec)
            records.append(dict(room=room,setting=name,config=cfg.to_dict(),source_sha256=sha,
                                candidate_count=len(result['walls']),rows=rows,runtime_seconds=time.perf_counter()-t))
            print(room,name,[round(r.get('change_mm',0),4) for r in rows],flush=True)
            dump(out/'records.json',records)
    dump(out/'protocol.json',dict(reference='Default automatic candidate masks; NOT manual ground truth',
        interpretation='Changes measure algorithm repeatability and recovery-band sensitivity, not accuracy',
        independent_physical_rooms=2,settings_per_room=7,threshold=.5))


if __name__=='__main__':main()
