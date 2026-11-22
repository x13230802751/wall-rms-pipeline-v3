# 对指定墙面或其局部区域拟合平面，计算 RMS、逐点距离和覆盖率。
import numpy as np
from .vendor.geometry import fit_plane, measure


def measure_wall(points,wall,roi=None,mode='expanded'):
    if mode not in ('expanded','paper'):raise ValueError('Measurement mode must be expanded or paper')
    p=np.asarray(points,dtype=float);ids=np.asarray(wall[mode+'_indices'],dtype=np.int64)
    if ids.ndim!=1 or len(ids)<3 or ids.min()<0 or ids.max()>=len(p) or len(np.unique(ids))!=len(ids):
        raise ValueError('Invalid or insufficient original wall indices')
    xyz=p[ids]
    if not np.isfinite(xyz).all():raise ValueError('Selected wall contains nonfinite XYZ')
    if roi is not None:
        # ROI coordinates may be mm; already loaded cloud is meters.
        rc=dict(roi)
        if rc.get('unit') not in ('m','mm'):raise ValueError('ROI unit must be m or mm')
        if rc['unit']=='mm':rc['corners']=(np.asarray(rc['corners'],dtype=float)*.001).tolist()
        rc['unit']='m'
        rr=measure(xyz,rc);ids=ids[rr['indices']];xyz=p[ids]
    c,n,_=fit_plane(xyz)
    if n@np.asarray(wall['plane_normal'])<0:n=-n
    signed=(xyz-c)@n*1000;absolute=np.abs(signed)
    u,v=np.asarray(wall['u']),np.asarray(wall['v']);origin=np.asarray(wall['plane_center_m'])
    uv=np.c_[(xyz-origin)@u,(xyz-origin)@v]
    # Occupancy of the measured bounding rectangle; not an estimate of unseen physical surface.
    cell=wall['coverage_grid_mm']/1000;lo=uv.min(0);hi=uv.max(0)
    dims=np.maximum(np.ceil((hi-lo)/cell).astype(int),1)
    grid=np.minimum(np.floor((uv-lo)/cell).astype(int),dims-1)
    coverage=float(len(np.unique(grid,axis=0))/np.prod(dims))
    warnings=list(wall['warnings'])
    if mode=='paper':warnings.append('RANSAC_INLIER_RMS_CAN_EXCLUDE_REAL_DEFECTS')
    if coverage<.5:warnings.append('LOW_RECTANGLE_COVERAGE')
    return dict(wall_id=wall['id'],mode=mode,rms_mm=float(np.sqrt(np.mean(signed**2))),
                n_selected=len(ids),plane_center_m=c.tolist(),plane_normal=n.tolist(),
                p95_abs_mm=float(np.percentile(absolute,95)),max_abs_mm=float(absolute.max()),
                rectangle_coverage_fraction=coverage,warnings=warnings,indices=ids,
                signed_mm=signed,abs_mm=absolute,selected_xyz_m=xyz,uv_m=uv,
                measurement_definition='Point-weighted RMS of selected original input points to their SVD best-fit plane; no final residual trimming',
                sign_convention='Normal oriented toward median room point at discovery; interior direction is heuristic')
