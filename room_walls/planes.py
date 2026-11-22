# 通过降采样、RANSAC 和连通聚类，从房间点云中提取平面候选。
"""Discovery only: RANSAC support is never silently used as the full surface."""
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from .vendor.geometry import fit_plane


def voxel_indices(points,size):
    cells=np.floor((points-points.min(0))/size).astype(np.int64)
    _,idx=np.unique(cells,axis=0,return_index=True)
    return np.sort(idx)


def largest_dbscan(points, eps, min_points):
    """Exact radius DBSCAN; deterministic border assignment, largest cluster."""
    if len(points)<min_points:return np.empty(0,dtype=int)
    tree=cKDTree(points)
    core=tree.query_ball_point(points,eps,return_length=True)>=min_points
    coreids=np.flatnonzero(core)
    if not len(coreids):return np.empty(0,dtype=int)
    ct=cKDTree(points[coreids]); pairs=ct.query_pairs(eps,output_type='ndarray')
    graph=coo_matrix((np.ones(len(pairs)),(pairs[:,0],pairs[:,1])),shape=(len(coreids),len(coreids)))
    _, groups=connected_components(graph,directed=False)
    labels=np.full(len(points),-1,dtype=int); labels[coreids]=groups
    border=np.flatnonzero(~core)
    if len(border):
        distance,nearest=ct.query(points[border],distance_upper_bound=eps)
        ok=np.isfinite(distance);labels[border[ok]]=groups[nearest[ok]]
    best=np.argmax(np.bincount(labels[labels>=0]))
    return np.flatnonzero(labels==best)


def ransac(points,config,rng):
    sample=points if len(points)<=config.ransac_sample else points[rng.choice(len(points),config.ransac_sample,replace=False)]
    # score batches to bound memory, not an N x all-trials allocation
    best_count=0; best=None
    for start in range(0,config.ransac_trials,32):
        triples=rng.integers(len(sample),size=(min(32,config.ransac_trials-start),3))
        a,b,c=sample[triples[:,0]],sample[triples[:,1]],sample[triples[:,2]]
        normals=np.cross(b-a,c-a);lengths=np.linalg.norm(normals,axis=1)
        valid=lengths>1e-8
        if not valid.any():continue
        normals=normals[valid]/lengths[valid,None];offset=np.einsum('ij,ij->i',normals,a[valid])
        counts=(np.abs(sample@normals.T-offset)<=config.ransac_mm/1000).sum(0)
        j=int(np.argmax(counts))
        if counts[j]>best_count:best_count=int(counts[j]);best=(normals[j],offset[j])
    if best is None:return None
    n,offset=best; ids=np.flatnonzero(np.abs(points@n-offset)<=config.ransac_mm/1000)
    if len(ids)<config.min_plane_points:return None
    for _ in range(2):
        try:c,n,_=fit_plane(points[ids])
        except ValueError:return None
        ids=np.flatnonzero(np.abs((points-c)@n)<=config.ransac_mm/1000)
        if len(ids)<config.min_plane_points:return None
    return ids


def extract_planes(points,config):
    ids=voxel_indices(points,config.voxel_mm/1000)
    q=points[ids]
    counts=cKDTree(q).query_ball_point(q,config.radius_mm/1000,return_length=True)
    ids=ids[counts>=config.radius_min_neighbors]; rng=np.random.default_rng(config.seed)
    planes=[]; exhausted=False
    for _ in range(config.max_planes):
        if len(ids)<config.min_plane_points:break
        support=ransac(points[ids],config,rng)
        if support is None:break
        all_support=ids[support]
        component=largest_dbscan(points[all_support],config.cluster_eps_mm/1000,config.cluster_min_points)
        if len(component)>=config.min_plane_points:
            chosen=all_support[component];c,n,_=fit_plane(points[chosen])
            planes.append({'center':c,'normal':n,'seed_indices':chosen})
        keep=np.ones(len(ids),dtype=bool);keep[support]=False;ids=ids[keep]
    else:exhausted=True
    return planes,exhausted
