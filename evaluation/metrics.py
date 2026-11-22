# 计算独立参考平面、墙实例匹配、选点指标和 RMS 误差统计。
import numpy as np
from scipy.optimize import linear_sum_assignment


def reference_plane(points):
    p=np.asarray(points,dtype=np.float64)
    if p.ndim!=2 or p.shape[1]!=3 or len(p)<3 or not np.isfinite(p).all():
        raise ValueError('Reference requires >=3 finite XYZ points')
    center=p.mean(0);q=p-center;values,vectors=np.linalg.eigh(q.T@q/len(q))
    if values[1]<1e-15:raise ValueError('Reference is collinear or degenerate')
    normal=vectors[:,0];residual=q@normal
    return dict(rms_mm=float(np.sqrt(np.mean(residual**2))*1000),center=center,normal=normal)


def relative_error(pred,ref):
    return None if abs(ref)<1e-12 else float(abs(pred-ref)/abs(ref)*100)


def decompose(pred,obs,visible,full):
    return dict(e_selection_mm=float(pred-obs),e_noise_mm=float(obs-visible),
                e_visibility_mm=float(visible-full),e_total_mm=float(pred-full))


def match_iou(iou,threshold):
    a=np.asarray(iou,dtype=float)
    if a.ndim!=2 or not 0<threshold<=1 or not np.isfinite(a).all():raise ValueError('Invalid IoU matrix/threshold')
    if not a.size:return []
    # A valid extra pair dominates the sum of all possible IoU tie-breakers.
    reward=np.where(a>=threshold,min(a.shape)+1+a,0.)
    rows,cols=linear_sum_assignment(reward,maximize=True)
    return [(int(r),int(c)) for r,c in zip(rows,cols) if a[r,c]>=threshold]


def instance_scores(truth,predictions,threshold=.5):
    truth=np.asarray(truth)
    if truth.ndim!=1 or not np.issubdtype(truth.dtype,np.integer):raise ValueError('Truth must contain integer instance IDs')
    gt_ids=np.unique(truth[truth>0]);sizes=np.array([np.sum(truth==k) for k in gt_ids])
    preds=[]
    for ids in predictions:
        ids=np.asarray(ids)
        if ids.ndim!=1 or not np.issubdtype(ids.dtype,np.integer) or (len(ids) and (ids.min()<0 or ids.max()>=len(truth))):
            raise ValueError('Prediction index out of range/type')
        if len(np.unique(ids))!=len(ids):raise ValueError('Duplicate point IDs within prediction')
        preds.append(ids[truth[ids]>=0])
    intersection=np.zeros((len(gt_ids),len(preds)),dtype=int)
    for r,k in enumerate(gt_ids):
        for c,ids in enumerate(preds):intersection[r,c]=np.sum(truth[ids]==k)
    predsize=np.array([len(p) for p in preds]);union=sizes[:,None]+predsize[None,:]-intersection
    iou=np.divide(intersection,union,out=np.zeros_like(intersection,dtype=float),where=union>0)
    pairs=match_iou(iou,threshold);tp=len(pairs);fp=len(preds)-tp;fn=len(gt_ids)-tp
    pred_union=np.zeros(len(truth),bool)
    for ids in preds:pred_union[ids]=True
    btp=int(np.sum(pred_union&(truth>0)));bfp=int(np.sum(pred_union&(truth==0)));bfn=int(np.sum(~pred_union&(truth>0)))
    return dict(gt_ids=gt_ids.tolist(),pairs=pairs,iou_matrix=iou,intersections=intersection,
                gt_sizes=sizes,pred_sizes=predsize,tp=tp,fp=fp,fn=fn,
                precision=None if tp+fp==0 else tp/(tp+fp),recall=None if tp+fn==0 else tp/(tp+fn),
                f1=0. if 2*tp+fp+fn==0 else 2*tp/(2*tp+fp+fn),
                binary_precision=None if btp+bfp==0 else btp/(btp+bfp),binary_recall=None if btp+bfn==0 else btp/(btp+bfn),
                binary_iou=None if btp+bfp+bfn==0 else btp/(btp+bfp+bfn),
                best_iou_mean=float(np.mean(np.max(iou,axis=1))) if iou.size else 0.,
                split_count=int(np.sum(np.sum(intersection>=np.maximum(1,.1*sizes[:,None]),axis=1)>=2)),
                merge_count=int(np.sum(np.sum(intersection>=np.maximum(1,.1*predsize[None,:]),axis=0)>=2)))


def error_summary(values,prefix):
    a=np.asarray(values,dtype=float)
    if not len(a):return {f'{k}_{prefix}_mm':None for k in ('bias','mae','rmse','medae','p95ae','maxae')}
    return {f'{k}_{prefix}_mm':float(v) for k,v in dict(bias=np.mean(a),mae=np.mean(abs(a)),
            rmse=np.sqrt(np.mean(a*a)),medae=np.median(abs(a)),p95ae=np.percentile(abs(a),95),maxae=np.max(abs(a))).items()}


def summarize_wall_rows(rows):
    n=len(rows);valid=[r for r in rows if r.get('matched') and r.get('e_selection_mm') is not None]
    out=dict(n_target_walls=n,n_valid=len(valid),valid_rate=len(valid)/n if n else None)
    out.update(error_summary([r['e_selection_mm'] for r in valid],'selection'))
    out.update(error_summary([r['e_total_mm'] for r in valid],'total'))
    for threshold,suffix in [(.2,'02'),(.5,'05'),(1.,'10')]:
        out['success_'+suffix]=sum(abs(r['e_selection_mm'])<=threshold for r in valid)/n if n else None
    strict=[r for r in valid if r['iou']>=.75 and r['precision']>=.95 and r['recall']>=.95 and abs(r['e_selection_mm'])<=.2]
    out['strict_joint_success']=len(strict)/n if n else None
    defects=[r for r in rows if r.get('has_defect') or r.get('defect_recall') is not None]
    out['defect_joint_success']=sum(r in strict and (r.get('defect_recall') or 0)>=.95 for r in defects)/len(defects) if defects else None
    return out
