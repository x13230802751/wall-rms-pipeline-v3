# 保存和读取墙面目录及测量结果，并校验点云与索引文件的对应关系。
import csv
import hashlib
import json
import platform
import re
from pathlib import Path
import numpy as np
from . import __version__
from .config import Config
from .vendor.io import read_cloud

ARRAY_KEYS={'paper_indices','expanded_indices','seed_indices'}
MEASURE_ARRAYS={'indices','signed_mm','abs_mm','selected_xyz_m','uv_m'}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,data):
    Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')


def empty_output(path):
    p=Path(path)
    if p.exists() and (not p.is_dir() or any(p.iterdir())):
        raise ValueError('Output must be absent or empty; use a new directory (existing evidence is never overwritten)')
    return p


def absolute_source(source):
    if '::' in source:
        archive,member=source.split('::',1);return str(Path(archive).resolve())+'::'+member
    return str(Path(source).resolve())


def load_metric_cloud(source,unit):
    if unit not in ('m','mm'):raise ValueError('Explicit unit m/mm is required')
    p,sha=read_cloud(source,with_hash=True)
    return p*(1. if unit=='m' else .001),sha


def save_catalog(result,source,sha,unit,points,out,labels_path=None):
    out=empty_output(out);out.mkdir(parents=True,exist_ok=True)
    arrays={};walls=[]
    for w in result['walls']:
        walls.append({k:v for k,v in w.items() if k not in ARRAY_KEYS})
        walls[-1].update(n_paper=len(w['paper_indices']),n_expanded=len(w['expanded_indices']))
        for k in ARRAY_KEYS:arrays[w['id']+'_'+k]=np.asarray(w[k],dtype=np.int64)
    np.savez_compressed(out/'assignments.npz',**arrays)
    catalog={k:v for k,v in result.items() if k!='walls'}
    catalog.update(walls=walls,schema_version=1,software_version=__version__,python_version=platform.python_version(),
                   numpy_version=np.__version__,cloud_source=absolute_source(source),cloud_payload_sha256=sha,
                   source_unit=unit,coordinate_unit='m',assignments_sha256=digest(out/'assignments.npz'),
                   labels_source=None if labels_path is None else str(Path(labels_path).resolve()),
                   labels_sha256=None if labels_path is None else digest(labels_path),
                   id_scope='IDs are local to this input hash, configuration and software; they are not official wall IDs',
                   learning_model='none; geometric discovery' if labels_path is None else 'external labels; provenance supplied by caller')
    dump(out/'catalog.json',catalog)
    with (out/'walls.csv').open('w',newline='',encoding='utf-8-sig') as f:
        keys=['id','dominant','n_paper','n_expanded','width_m','height_m','floor_gap_m','plane_center_m','plane_normal']
        writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader()
        writer.writerows({k:w[k] for k in keys} for w in walls)
    from .visuals import catalog_plots, viewer
    catalog_plots(points,result,out);viewer(points,result,out)
    return catalog


def load_catalog(path,cloud_override=None):
    path=Path(path);c=json.loads(path.read_text(encoding='utf-8-sig'))
    if c.get('schema_version')!=1:raise ValueError('Unsupported catalog schema')
    Config.from_dict(c['config'])
    assignment=path.parent/'assignments.npz'
    if digest(assignment)!=c['assignments_sha256']:raise ValueError('Assignment hash mismatch; rerun discovery')
    p,sha=load_metric_cloud(cloud_override or c['cloud_source'],c['source_unit'])
    if sha!=c['cloud_payload_sha256']:raise ValueError('Point cloud hash mismatch: catalog belongs to a different file')
    if len(p)!=c['n_input']:raise ValueError('Point count differs from catalog')
    seen=set()
    with np.load(assignment,allow_pickle=False) as arrays:
        for w in c['walls']:
            wid=w['id']
            if not re.fullmatch(r'W\d{2,}',wid) or wid in seen:raise ValueError('Invalid or duplicate wall ID')
            seen.add(wid)
            for key in ARRAY_KEYS:
                a=arrays[wid+'_'+key]
                if a.ndim!=1 or not np.issubdtype(a.dtype,np.integer) or len(a)==0 or a.min()<0 or a.max()>=len(p) or len(np.unique(a))!=len(a):
                    raise ValueError('Invalid saved point indices')
                w[key]=a
            if not np.isin(w['paper_indices'],w['expanded_indices']).all():raise ValueError('Paper set must be a subset of expanded set')
            for k in ['plane_center_m','plane_normal','u','v']:
                a=np.asarray(w[k],dtype=float)
                if a.shape!=(3,) or not np.isfinite(a).all():raise ValueError('Invalid saved wall geometry')
    return p,c


def save_measurement(r,points,out,provenance):
    out=empty_output(out);out.mkdir(parents=True,exist_ok=True)
    values=np.c_[r['indices'],r['selected_xyz_m'],r['signed_mm'],r['abs_mm']]
    np.savetxt(out/'distances.csv',values,delimiter=',',comments='',
               header='point_index,x_m,y_m,z_m,signed_distance_mm,abs_distance_mm',fmt=['%d']+['%.17g']*5)
    result={k:v for k,v in r.items() if k not in MEASURE_ARRAYS};result.update(provenance)
    result.update(schema_version=1,software_version=__version__,distances_sha256=digest(out/'distances.csv'),
                  gt_comparison='not_performed_no_matched_reference',engineering_acceptance='not_assessed')
    dump(out/'result.json',result)
    from .visuals import measurement_plots
    measurement_plots(r,out)
    return result
