# 核对保存结果的来源、选中点、逐点距离和独立复算的 RMS。
"""Verify source identity, saved coordinates, selected-point RMS and membership."""
import argparse
from pathlib import Path
import sys
import json
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from room_walls.artifacts import load_catalog,digest,dump


def verify(folder):
    folder=Path(folder);p,cat=load_catalog(folder/'catalog.json')
    allids=np.concatenate([w['expanded_indices'] for w in cat['walls']])
    if len(allids)!=len(np.unique(allids)):raise AssertionError('Wall assignments overlap')
    records=[]
    for file in sorted((folder/'measurements').glob('*/result.json')):
        r=json.loads(file.read_text(encoding='utf-8'));csv=file.parent/'distances.csv'
        if digest(csv)!=r['distances_sha256']:raise AssertionError('Distance file hash mismatch')
        if r['cloud_payload_sha256']!=cat['cloud_payload_sha256']:raise AssertionError('Source hash mismatch')
        if r['catalog_sha256']!=digest(folder/'catalog.json'):raise AssertionError('Catalog hash mismatch')
        a=np.genfromtxt(csv,delimiter=',',names=True,ndmin=1);ids=a['point_index'].astype(int)
        xyz=np.c_[a['x_m'],a['y_m'],a['z_m']]
        if not np.array_equal(xyz,p[ids]):raise AssertionError('Saved coordinates do not match original points')
        w=next(w for w in cat['walls'] if w['id']==r['wall_id'])
        if not np.array_equal(ids,w[r['mode']+'_indices']):raise AssertionError('Selected wall IDs differ')
        centered=xyz-xyz.mean(0);eigen=float(np.sqrt(max(0,np.linalg.eigvalsh(centered.T@centered/len(xyz))[0]))*1000)
        saved=float(np.sqrt(np.mean(a['signed_distance_mm']**2)))
        residual=(xyz-np.array(r['plane_center_m']))@np.array(r['plane_normal'])*1000
        error=max(abs(eigen-r['rms_mm']),abs(saved-r['rms_mm']),float(np.max(np.abs(residual-a['signed_distance_mm']))))
        if error>1e-5:raise AssertionError(f'Independent numeric disagreement: {error}')
        records.append(dict(wall=r['wall_id'],n=len(ids),rms_mm=r['rms_mm'],independent_eigen_rms_mm=eigen,max_difference_mm=error))
    if not records:raise AssertionError('No measurement records to verify')
    return dict(source=folder.name,input_points=len(p),wall_count=len(cat['walls']),source_hash=cat['cloud_payload_sha256'],
                nonoverlap=True,records=records,gt_validation=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('folders',nargs='+');parser.add_argument('--out',required=True);args=parser.parse_args()
    result=[verify(p) for p in args.folders];dump(args.out,result)
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
