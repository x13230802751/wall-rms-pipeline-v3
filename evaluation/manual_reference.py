# 使用独立审定的人工墙面标签，评价墙面识别和扫描点云 RMS 误差。
"""Evaluate against independently supplied, adjudicated instance annotations."""
import argparse
import json
from pathlib import Path
import numpy as np
from room_walls.artifacts import load_catalog,empty_output,dump,digest
from room_walls.measurement import measure_wall
from .metrics import instance_scores,reference_plane


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--catalog',required=True);ap.add_argument('--labels',required=True)
    ap.add_argument('--metadata',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    out=empty_output(args.out);points,catalog=load_catalog(args.catalog)
    meta=json.loads(Path(args.metadata).read_text(encoding='utf-8-sig'))
    required=['cloud_payload_sha256','reviewers','adjudicated','blind_to_predictions','boundary_policy','unit']
    if any(k not in meta for k in required):raise ValueError('Annotation provenance metadata incomplete')
    if meta['cloud_payload_sha256']!=catalog['cloud_payload_sha256']:raise ValueError('Annotation/cloud hash mismatch')
    if meta['unit']!='m':raise ValueError('Reference coordinates and measurement unit must be explicitly meters')
    if meta['adjudicated'] is not True or meta['blind_to_predictions'] is not True:
        raise ValueError('Independent, adjudicated reference required; candidate-generated labels are not ground truth')
    if not isinstance(meta['reviewers'],list) or len(set(meta['reviewers']))<2:
        raise ValueError('Provide two distinct reviewers and an adjudicated annotation')
    truth=np.load(args.labels,allow_pickle=False)
    if truth.shape!=(len(points),) or not np.issubdtype(truth.dtype,np.integer) or np.any(truth < -1):
        raise ValueError('Labels: N original-order integers; -1 ignore, 0 background, positive wall IDs')
    if not np.any(truth>0):raise ValueError('No reference wall instances')
    if np.any((truth>=0)&~np.isfinite(points).all(1)):raise ValueError('Mark nonfinite source points as -1 ignore')
    output=[]
    for mode in ['expanded','paper']:
        walls=[];ignored=[]
        for w in catalog['walls']:
            ids=w[mode+'_indices'];ids=ids[truth[ids]>=0]
            if not len(ids):ignored.append(w['id']);continue
            w=dict(w);w[mode+'_indices']=ids;walls.append(w)
        score=instance_scores(truth,[w[mode+'_indices'] for w in walls],.5);pairs={r:c for r,c in score['pairs']};rows=[]
        for row,k in enumerate(score['gt_ids']):
            ref=reference_plane(points[truth==k]);rec=dict(reference_wall=k,reference_scan_rms_mm=ref['rms_mm'],matched=row in pairs)
            if row in pairs:
                col=pairs[row];m=measure_wall(points,walls[col],mode=mode)
                rec.update(predicted_wall=walls[col]['id'],rms_mm=m['rms_mm'],error_mm=m['rms_mm']-ref['rms_mm'],
                           iou=float(score['iou_matrix'][row,col]),n_selected=m['n_selected'])
            rows.append(rec)
        output.append(dict(mode=mode,tp=score['tp'],fp=score['fp'],fn=score['fn'],rows=rows,ignored_predictions=ignored))
    out.mkdir(parents=True,exist_ok=True)
    dump(out/'manual_reference_evaluation.json',dict(results=output,metadata=meta,label_sha256=digest(args.labels),
         ignored_point_fraction=float(np.mean(truth==-1)),reference_level='B: annotated observed scan; not independent physical metrology',
         provenance_verified_by='Caller declarations; software checks structure/hashes, not human reviewer identity',
         comparison_domain='Nonignored original points; predictions entirely in ignored regions are excluded'))


if __name__=='__main__':main()
