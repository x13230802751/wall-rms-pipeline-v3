# 从整房间点云中识别地面和墙面候选，并恢复各墙的原始点集合。
"""Whole-room geometric candidates, with optional externally supplied semantics."""
import numpy as np
from scipy.spatial import cKDTree, ConvexHull
from .config import Config
from .planes import extract_planes
from .vendor.geometry import inside_polygon


def wall_frame(normal,up):
    u=np.cross(up,normal);u/=np.linalg.norm(u)
    v=np.cross(normal,u);v/=np.linalg.norm(v)
    if v@up<0:v=-v
    return u,v


def discover(points,config=None,labels=None):
    cfg=config or Config(); p=np.asarray(points,dtype=np.float64)
    if p.ndim!=2 or p.shape[1]!=3:raise ValueError('points must be N x 3, in meters')
    finite=np.isfinite(p).all(1);original=np.flatnonzero(finite);q=p[finite]
    if len(q)<cfg.min_plane_points:raise ValueError('Insufficient finite points for discovery')
    if np.ptp(q@np.asarray(cfg.up))<cfg.min_wall_height_m:raise ValueError('Cloud has insufficient height; check unit/up')
    if labels is not None:
        labels=np.asarray(labels)
        if labels.shape!=(len(p),) or not np.issubdtype(labels.dtype,np.integer):
            raise ValueError('Semantic labels must be a one-dimensional integer array, one per ORIGINAL point')
        ll=labels[finite];planes=[];limited=False
        for label in (cfg.wall_label,cfg.floor_label,cfg.ceiling_label):
            subset=np.flatnonzero(ll==label)
            if len(subset)<cfg.min_plane_points:continue
            found,limit=extract_planes(q[subset],cfg);limited |= limit
            for plane in found:
                plane['seed_indices']=subset[plane['seed_indices']];plane['semantic_class']=int(label)
            planes.extend(found)
    else:
        planes,limited=extract_planes(q,cfg)
    up=np.asarray(cfg.up);heights=q@up;bottom,top=np.quantile(heights,[.01,.99])
    horizontal=[x for x in planes if abs(x['normal']@up)>=np.cos(np.deg2rad(cfg.max_floor_tilt_deg))]
    floors=[x for x in horizontal if x['center']@up<=bottom+.2*(top-bottom)
            and (labels is None or x.get('semantic_class')==cfg.floor_label)]
    if not floors:raise ValueError('No reliable low horizontal floor found; check unit, up, floor visibility or labels')
    floor=max(floors,key=lambda x:len(x['seed_indices']))
    fn=floor['normal'].copy()
    if fn@up<0:fn=-fn
    fc=floor['center']; candidates=[];rejected=[]
    roomcenter=np.median(q,axis=0)
    for index,x in enumerate(planes):
        n=x['normal'].copy();c=x['center'];support=q[x['seed_indices']]
        if abs(n@up)>np.sin(np.deg2rad(cfg.max_wall_tilt_deg)):continue
        if labels is not None and x.get('semantic_class')!=cfg.wall_label:continue
        if n@(roomcenter-c)<0:n=-n
        u,v=wall_frame(n,up);uv=np.c_[(support-c)@u,(support-c)@v]
        lo,hi=uv.min(0),uv.max(0);width,height=hi-lo
        touch=float(np.quantile((support-fc)@fn,.01))
        reasons=[]
        if width<cfg.min_wall_width_m:reasons.append('TOO_NARROW')
        if height<cfg.min_wall_height_m:reasons.append('TOO_SHORT')
        if width*height<cfg.min_wall_area_m2:reasons.append('TOO_SMALL')
        if abs(touch)>cfg.floor_touch_mm/1000:reasons.append('NOT_FLOOR_CONNECTED')
        if reasons:
            rejected.append({'candidate':index,'center_m':c.tolist(),'reasons':reasons});continue
        corners=c+np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]])@np.stack([u,v])
        candidates.append(dict(center=c,normal=n,u=u,v=v,seed_indices=x['seed_indices'],
            uv_seed=uv,width_m=float(width),height_m=float(height),floor_gap_m=touch,
            corners_m=corners.tolist(),discovery_support_count=len(support)))
    if not candidates:raise ValueError('No wall candidates passed size/orientation/floor-contact checks')
    candidates.sort(key=lambda w:tuple(np.round(w['center'],5)))
    # Compete against other wall/floor/ceiling planes to avoid double-assigned corner points.
    reference=candidates+horizontal
    nearest_distance=np.full(len(q),np.inf);nearest=np.full(len(q),-1,dtype=int)
    for i,w in enumerate(reference):
        distance=np.abs((q-w['center'])@w['normal']);closer=distance<nearest_distance
        nearest_distance[closer]=distance[closer];nearest[closer]=i
    walls=[]
    for j,w in enumerate(candidates):
        preliminary=(nearest==j)&(nearest_distance<=cfg.recovery_mm/1000)
        if labels is not None:preliminary &= ll==cfg.wall_label
        ix=np.flatnonzero(preliminary);uv=np.c_[(q[ix]-w['center'])@w['u'],(q[ix]-w['center'])@w['v']]
        # Include the interior even where RANSAC removed a real bump. This selects
        # existing observations only; it does not invent points in window holes.
        hull=w['uv_seed'][ConvexHull(w['uv_seed']).vertices]
        dist,_=cKDTree(w['uv_seed']).query(uv,distance_upper_bound=cfg.footprint_mm/1000)
        ix=ix[inside_polygon(uv,hull)|np.isfinite(dist)]
        strict=ix[np.abs((q[ix]-w['center'])@w['normal'])<=cfg.ransac_mm/1000]
        if len(strict)<3 or len(ix)<3:continue
        item={k:w[k] for k in ('width_m','height_m','floor_gap_m','corners_m','discovery_support_count')}
        item.update(id=f'W{len(walls)+1:02d}',plane_center_m=w['center'].tolist(),plane_normal=w['normal'].tolist(),
                    u=w['u'].tolist(),v=w['v'].tolist(),paper_indices=original[strict],
                    expanded_indices=original[ix],seed_indices=original[w['seed_indices']],
                    recovery_mm=cfg.recovery_mm,coverage_grid_mm=cfg.coverage_grid_mm,
                    mode='external_semantics' if labels is not None else 'geometry',
                    warnings=['CANDIDATE_REQUIRES_REVIEW','FINITE_RECOVERY_BAND','HULL_MAY_INCLUDE_OPENING_CONTENTS'])
        if labels is None:item['warnings'].append('NO_SEMANTIC_MODEL_CLUTTER_POSSIBLE')
        near=float(np.mean(np.abs((q[ix]-w['center'])@w['normal'])>.9*cfg.recovery_mm/1000))
        item['recovery_edge_fraction']=near
        if near>.01:item['warnings'].append('POINTS_NEAR_RECOVERY_LIMIT')
        walls.append(item)
    if not walls:raise ValueError('No wall candidates retained enough original points')
    dominant={w['id'] for w in sorted(walls,key=lambda w:w['discovery_support_count'],reverse=True)[:4]}
    for w in walls:w['dominant']=w['id'] in dominant
    warnings=['GEOMETRIC_CANDIDATES_NOT_VERIFIED_WALL_IDENTITIES'] if labels is None else ['EXTERNAL_LABELS_NOT_INDEPENDENTLY_VERIFIED']
    if len(walls)!=4:warnings.append('WALL_COUNT_DIFFERS_FROM_PAPER_FOUR')
    if limited:warnings.append('PLANE_SEARCH_LIMIT_REACHED')
    return dict(walls=walls,config=cfg.to_dict(),mode='external_semantics' if labels is not None else 'geometry',
                n_input=len(p),n_invalid=int((~finite).sum()),n_planes=len(planes),
                floor={'center_m':fc.tolist(),'normal':fn.tolist()},warnings=warnings,rejected_candidates=rejected)
