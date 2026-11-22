# 定义并校验墙面发现、点集恢复和测量诊断使用的配置参数。
from dataclasses import dataclass, asdict, fields
import numpy as np


@dataclass(frozen=True)
class Config:
    up: tuple = (0., 0., 1.)
    voxel_mm: float = 30.
    ransac_mm: float = 12.
    ransac_trials: int = 512
    ransac_sample: int = 12000
    max_planes: int = 28
    min_plane_points: int = 120
    radius_mm: float = 95.
    radius_min_neighbors: int = 4
    cluster_eps_mm: float = 95.
    cluster_min_points: int = 4
    min_wall_width_m: float = .8
    min_wall_height_m: float = 1.2
    min_wall_area_m2: float = 1.0
    floor_touch_mm: float = 250.
    max_wall_tilt_deg: float = 15.
    max_floor_tilt_deg: float = 15.
    recovery_mm: float = 50.
    footprint_mm: float = 100.
    coverage_grid_mm: float = 100.
    seed: int = 7023
    wall_label: int = 2
    floor_label: int = 1
    ceiling_label: int = 0

    def __post_init__(self):
        v=np.asarray(self.up,dtype=float)
        if v.shape!=(3,) or not np.isfinite(v).all() or np.linalg.norm(v)<1e-10:
            raise ValueError('up must be a nonzero finite XYZ vector')
        object.__setattr__(self,'up',tuple((v/np.linalg.norm(v)).tolist()))
        integer={'ransac_trials','ransac_sample','max_planes','min_plane_points',
                 'radius_min_neighbors','cluster_min_points','seed','wall_label','floor_label','ceiling_label'}
        for f in fields(self):
            if f.name=='up':continue
            x=getattr(self,f.name)
            if isinstance(x,bool) or not isinstance(x,(int,float)) or not np.isfinite(x):
                raise ValueError(f'{f.name} must be a finite number')
            if f.name in integer and int(x)!=x:raise ValueError(f'{f.name} must be an integer')
            if f.name in integer:object.__setattr__(self,f.name,int(x))
            if f.name not in {'seed','wall_label','floor_label','ceiling_label'} and x<=0:
                raise ValueError(f'{f.name} must be positive')
        if self.seed<0:raise ValueError('seed must be nonnegative')
        if min(self.min_plane_points,self.ransac_sample)<3:raise ValueError('Need at least 3 plane points')
        if not 0<self.max_wall_tilt_deg<45 or not 0<self.max_floor_tilt_deg<45:
            raise ValueError('Tilt bounds must be between 0 and 45 degrees')
        if self.recovery_mm<self.ransac_mm:raise ValueError('recovery_mm must be >= ransac_mm')
        if len({self.wall_label,self.floor_label,self.ceiling_label})!=3:
            raise ValueError('Wall, floor and ceiling labels must differ')

    def to_dict(self):return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data,dict):raise ValueError('Configuration must be a JSON object')
        unknown=set(data)-{f.name for f in fields(cls)}
        if unknown:raise ValueError(f'Unknown config fields: {sorted(unknown)}')
        return cls(**data)
