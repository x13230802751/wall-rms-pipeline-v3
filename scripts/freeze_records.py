# 整理可纳入 Git 的紧凑实验记录，不复制真实点云坐标。
"""Copy compact measurements into Git-safe records; never copy real point coordinates."""
import csv
import json
import hashlib
import shutil
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from room_walls.config import Config
from room_walls.artifacts import dump


def main():
    results=ROOT/'results';results.mkdir(exist_ok=True)
    configs=ROOT/'configs';configs.mkdir(exist_ok=True);dump(configs/'default.json',Config().to_dict())
    for filename in ['records.json','summary.json']:
        shutil.copyfile(ROOT/'outputs/synthetic_benchmark_v2'/filename,results/('synthetic_'+filename))
    shutil.copyfile(ROOT/'outputs/official_verification.json',results/'official_verification.json')
    rows=[]
    for room in ['M26','M04']:
        summary=json.loads((ROOT/'outputs'/f'{room}_v1'/'summary.json').read_text(encoding='utf-8'))
        for r in summary['measurements']:
            rows.append(dict(room=room,wall=r['wall_id'],n=r['n_selected'],expanded_rms_mm=r['rms_mm'],
                             paper_rms_mm=r['comparison']['other_rms_mm'],difference_mm=r['comparison']['difference_mm'],
                             matched_official_gt=False,source_sha256=r['cloud_payload_sha256']))
    with (results/'official_measurements.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    dump(results/'official_measurements.json',rows)
    provenance={'source_repository':'https://github.com/x13230802751/civl7023-wall-flatness',
                'source_commit':'56407caf4d1ec3c2234c890936cbf0677f6cda51','files':{}}
    for name in ['io.py','geometry.py']:
        data=(ROOT/'room_walls/vendor'/name).read_bytes()
        provenance['files'][name]={'sha256_raw_copy':hashlib.sha256(data).hexdigest(),
                                  'sha256_lf_normalized':hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()}
    dump(ROOT/'vendor_provenance.json',provenance)
    text='''# 复用来源

复用用户原有私有项目 `civl7023-wall-flatness` 的固定提交
`56407caf4d1ec3c2234c890936cbf0677f6cda51` 中：

- `code/wall_flatness/io.py` → `room_walls/vendor/io.py`：点云读取和内容哈希。
- `code/wall_flatness/geometry.py` → `room_walls/vendor/geometry.py`：SVD、四点合法性和选区。

这是源码快照，不依赖相邻旧项目的可变代码。当前来源归属和使用权限沿用用户自己的原项目；没有引入外部未核实授权的算法源码。SHA256 详见 `vendor_provenance.json`，跨系统核对时使用 LF 归一化值。

新编写部分包括自动平面发现、DBSCAN、地面/墙面筛选、原始点恢复、目录索引和验证、命令行、预览页及整房间评测。论文提供方法参考，没有复制其模型代码或训练权重。
'''
    (ROOT/'PROVENANCE.md').write_text(text,encoding='utf-8')
    print('Saved compact records and vendor provenance')


if __name__=='__main__':main()
