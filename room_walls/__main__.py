# 提供发现墙面、测量指定墙面和批量测量的命令行入口。
import argparse
import json
import sys
import time
import zipfile
from pathlib import Path
import numpy as np
from .config import Config
from .discovery import discover
from .measurement import measure_wall
from .artifacts import (dump,digest,empty_output,load_metric_cloud,save_catalog,load_catalog,save_measurement)


def choose(walls,names):
    if names=='all':return walls
    keys=names.split(',')
    if len(set(keys))!=len(keys):raise ValueError('Duplicate wall IDs')
    lookup={w['id']:w for w in walls}
    missing=set(keys)-set(lookup)
    if missing:raise ValueError(f'Unknown wall IDs {sorted(missing)}; available: {list(lookup)}')
    return [lookup[k] for k in keys]


def measurement(points,wall,out,mode,roi,provenance):
    r=measure_wall(points,wall,roi=roi,mode=mode)
    other_mode='paper' if mode=='expanded' else 'expanded'
    try:
        other=measure_wall(points,wall,roi=roi,mode=other_mode)
        r['comparison']={'other_mode':other['mode'],'other_rms_mm':other['rms_mm'],
                         'other_n_selected':other['n_selected'],'difference_mm':r['rms_mm']-other['rms_mm'],
                         'interpretation':'Selection sensitivity, NOT ground-truth error'}
    except ValueError as e:
        # A valid bulge-only ROI can have zero strict RANSAC inliers.
        r['comparison']={'other_mode':other_mode,'other_rms_mm':None,'difference_mm':None,
                         'unavailable':str(e),'interpretation':'No valid comparison set; primary measurement retained'}
    return save_measurement(r,points,out,provenance)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Whole room -> candidate wall IDs -> selected-wall RMS; no model training claimed')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('discover','run'):
        p=sub.add_parser(name);p.add_argument('--cloud',required=True);p.add_argument('--unit',required=True,choices=['m','mm'])
        p.add_argument('--out',required=True);p.add_argument('--config');p.add_argument('--up',nargs=3,type=float)
        p.add_argument('--labels',help='External semantic NPY integer labels, one per original point; not an installed model')
        if name=='run':p.add_argument('--walls',default='all');p.add_argument('--mode',choices=['expanded','paper'],default='expanded')
    p=sub.add_parser('measure');p.add_argument('--catalog',required=True);p.add_argument('--wall',required=True)
    p.add_argument('--out',required=True);p.add_argument('--cloud',help='Relocated same-hash input cloud')
    p.add_argument('--roi');p.add_argument('--mode',choices=['expanded','paper'],default='expanded')
    args=parser.parse_args(argv);start=time.perf_counter()
    try:
        out=empty_output(args.out)
        if args.command in ('discover','run'):
            config={} if not args.config else json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
            if args.up:config['up']=args.up
            cfg=Config.from_dict(config);points,sha=load_metric_cloud(args.cloud,args.unit)
            labels=None if args.labels is None else np.load(args.labels,allow_pickle=False)
            result=discover(points,cfg,labels=labels)
            selected=choose(result['walls'],args.walls) if args.command=='run' else []
            result['discovery_runtime_seconds']=time.perf_counter()-start
            catalog=save_catalog(result,args.cloud,sha,args.unit,points,out,args.labels)
            measurements=[]
            for w in selected:
                provenance={'cloud_payload_sha256':sha,'catalog_sha256':digest(out/'catalog.json'),
                            'selection_config':cfg.to_dict(),'discovery_mode':result['mode'],'roi':None}
                m=measurement(points,w,out/'measurements'/w['id'],args.mode,None,provenance)
                measurements.append(m)
            if args.command=='run':
                summary=dict(mode=result['mode'],measurements=measurements,runtime_seconds=time.perf_counter()-start,
                             gt_comparison='not_performed_no_matched_reference',warnings=result['warnings'])
                dump(out/'summary.json',summary)
            print(json.dumps({'mode':result['mode'],'walls':[w['id'] for w in result['walls']],
                              'measured':[{k:m[k] for k in ('wall_id','rms_mm','n_selected')} for m in measurements],
                              'out':str(out.resolve()),'runtime_seconds':round(time.perf_counter()-start,3)},ensure_ascii=True))
        else:
            points,catalog=load_catalog(args.catalog,args.cloud);wall=choose(catalog['walls'],args.wall)
            if len(wall)!=1:raise ValueError('measure accepts exactly one wall ID')
            roi=None if not args.roi else json.loads(Path(args.roi).read_text(encoding='utf-8-sig'))
            provenance={'cloud_payload_sha256':catalog['cloud_payload_sha256'],'catalog_sha256':digest(args.catalog),
                        'selection_config':catalog['config'],'discovery_mode':catalog['mode'],'roi':roi}
            m=measurement(points,wall[0],out,args.mode,roi,provenance)
            print(json.dumps({k:m[k] for k in ('wall_id','mode','rms_mm','n_selected')},ensure_ascii=True))
    except (ValueError,OSError,KeyError,TypeError,IndexError,zipfile.BadZipFile,np.linalg.LinAlgError) as e:
        print(f'ERROR: {e}',file=sys.stderr);return 2
    return 0


if __name__=='__main__':sys.exit(main())
