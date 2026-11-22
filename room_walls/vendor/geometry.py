# 提供复用的四点区域校验、点集筛选、平面拟合和 RMS 计算。
"""Metric geometry. No smoothing or residual-based rejection of wall points."""
import numpy as np

DEFAULTS = dict(slab_half_thickness_mm=50., max_corner_deviation_mm=10.,
                min_points=30, coverage_grid_mm=50.)

def validate_config(config):
    allowed=set(DEFAULTS)|{'unit','corners','room_id','roi_id','description'}
    if set(config)-allowed: raise ValueError(f'Unknown ROI fields: {sorted(set(config)-allowed)}')
    if config.get('unit') not in ('m','mm'):raise ValueError('unit must explicitly be m or mm for BOTH cloud and corners')
    cfg={**DEFAULTS,**config}
    for k in DEFAULTS:
        v=cfg[k]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not np.isfinite(v) or v<=0:raise ValueError(f'{k} must be a finite positive number')
    if cfg['min_points']<3 or int(cfg['min_points'])!=cfg['min_points']:raise ValueError('min_points must be an integer >= 3')
    for k in ('room_id','roi_id','description'):
        if k in cfg and not isinstance(cfg[k],str):raise ValueError(f'{k} must be a string')
    return cfg

def fit_plane(points):
    center=points.mean(axis=0)
    _,s,vt=np.linalg.svd(points-center,full_matrices=False)
    if len(s)<3 or s[1] <= max(s[0]*1e-6,1e-10):raise ValueError('Points have insufficient two-dimensional extent (coincident or collinear)')
    return center,vt[-1],s

def inside_polygon(uv,polygon):
    edges=np.roll(polygon,-1,axis=0)-polygon
    delta=uv[:,None,:]-polygon[None,:,:]
    cross=edges[None,:,0]*delta[:,:,1]-edges[None,:,1]*delta[:,:,0]
    tol=1e-10*np.linalg.norm(edges,axis=1)
    return np.all(cross>=-tol,axis=1)|np.all(cross<=tol,axis=1)

def roi_frame(corners,max_deviation_m):
    if corners.shape!=(4,3) or not np.isfinite(corners).all():raise ValueError('corners must contain exactly four finite XYZ triplets')
    if np.min([np.linalg.norm(corners[i]-corners[j]) for i in range(4) for j in range(i)])<1e-8:raise ValueError('Repeated corners')
    c,n,_=fit_plane(corners)
    deviation=np.max(np.abs((corners-c)@n))
    if deviation>max_deviation_m:raise ValueError(f'Corners are not coplanar within tolerance: {deviation*1000:.3f} mm')
    edge=corners[1]-corners[0];u=edge-n*np.dot(edge,n)
    if np.linalg.norm(u)<1e-8:raise ValueError('Invalid first edge')
    u/=np.linalg.norm(u);v=np.cross(n,u)
    poly=np.c_[(corners-c)@u,(corners-c)@v]
    edges=np.roll(poly,-1,axis=0)-poly;nxt=np.roll(edges,-1,axis=0)
    turns=edges[:,0]*nxt[:,1]-edges[:,1]*nxt[:,0]
    if not (np.all(turns>1e-10) or np.all(turns < -1e-10)):raise ValueError('Corners must form a non-crossing, strictly convex boundary in cyclic order')
    return c,n,u,v,poly,float(deviation*1000)

def coverage(uv,poly,grid):
    lo=poly.min(0);hi=poly.max(0)
    shape=np.maximum(np.ceil((hi-lo)/grid).astype(int),1)
    if np.prod(shape)>2_000_000:raise ValueError('Coverage grid too fine for ROI; increase coverage_grid_mm')
    x=lo[0]+(np.arange(shape[0])+.5)*grid;y=lo[1]+(np.arange(shape[1])+.5)*grid
    xx,yy=np.meshgrid(x,y,indexing='ij');centers=np.c_[xx.ravel(),yy.ravel()]
    valid=inside_polygon(centers,poly)
    ids=np.floor((uv-lo)/grid).astype(int);ids=np.clip(ids,0,shape-1)
    occupied=np.zeros(int(np.prod(shape)),dtype=bool);occupied[ids[:,0]*shape[1]+ids[:,1]]=True
    return float(np.sum(occupied & valid)/np.sum(valid)) if valid.any() else None

def measure(points,config):
    cfg=validate_config(config);scale=1 if cfg['unit']=='m' else .001
    p=np.asarray(points,dtype=np.float64)*scale
    if p.ndim!=2 or p.shape[1]!=3:raise ValueError('Point cloud must have shape N x 3')
    corners=np.asarray(cfg.get('corners'),dtype=np.float64)*scale
    c0,n0,u,v,poly,corner_dev=roi_frame(corners,cfg['max_corner_deviation_mm']/1000)
    valid=np.isfinite(p).all(1);ids=np.flatnonzero(valid);q=p[valid]-c0
    uv=np.c_[q@u,q@v];h=q@n0;in_poly=inside_polygon(uv,poly)
    half=cfg['slab_half_thickness_mm']/1000
    selected=in_poly & (np.abs(h)<=half+1e-12);idx=ids[selected];s=p[idx]
    if len(s)<cfg['min_points']:raise ValueError(f'Only {len(s)} points selected; min_points={cfg["min_points"]}')
    center,n,sv=fit_plane(s)
    if np.dot(n,n0)<0:n=-n
    signed=(s-center)@n*1000;distance=np.abs(signed)
    cov=coverage(uv[selected],poly,cfg['coverage_grid_mm']/1000)
    warnings=[]
    if cov is None:warnings.append('COVERAGE_GRID_TOO_COARSE')
    elif cov<.5:warnings.append('LOW_COVERAGE')
    edge_fraction=float(np.mean(np.abs(h[selected])>.9*half))
    if edge_fraction>.01:warnings.append('NEAR_SLAB_BOUNDARY')
    rms=float(np.sqrt(np.mean(signed**2)))
    if sv[-1]/sv[1]>.1:warnings.append('NON_PLANAR_OR_CONTAMINATED_SELECTION')
    return dict(status='warning' if warnings else 'ok',rms_mm=rms,n_input=len(p),
                n_invalid=int((~valid).sum()),n_projected=int(in_poly.sum()),n_selected=len(s),
                n_slab_excluded=int((in_poly&~selected).sum()),coverage_fraction=cov,
                slab_edge_fraction=edge_fraction,corner_max_deviation_mm=corner_dev,
                p95_abs_mm=float(np.percentile(distance,95)),max_abs_mm=float(distance.max()),
                plane_center_m=center.tolist(),plane_normal=n.tolist(),warnings=warnings,
                config=cfg,indices=idx,selected_xyz_m=s,signed_mm=signed,abs_mm=distance,
                uv_m=uv[selected],polygon_uv_m=poly,corners_m=corners,roi_center_m=c0)
