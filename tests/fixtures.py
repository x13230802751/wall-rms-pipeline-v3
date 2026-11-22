# 生成测试用房间点云、真实标签和几何算法配置。
import numpy as np


def room(step=.07, roughness_mm=2., bulge=False, clutter=False):
    """Four separated wall interiors, floor, ceiling; no input wall hints."""
    u = np.arange(.04, 3.96, step)
    v = np.arange(.04, 2.96, step)
    h = np.arange(.04, 2.56, step)
    clouds, objects, labels = [], [], []
    for k, (axis, offset, span) in enumerate([(0, 0., v), (0, 4., v),
                                            (1, 0., u), (1, 3., u)]):
        a, z = np.meshgrid(span, h)
        a, z = a.ravel(), z.ravel()
        p = np.zeros((len(a), 3)); p[:, axis] = offset
        p[:, 1-axis] = a; p[:, 2] = z
        if k == 0 and roughness_mm:
            deviation = np.cos(a*4)*np.cos(z*5)
            design = np.c_[np.ones(len(a)), a, z]
            deviation -= design @ np.linalg.lstsq(design, deviation, rcond=None)[0]
            deviation *= roughness_mm / (1000*np.sqrt(np.mean(deviation**2)))
            p[:, axis] += deviation
        if k == 0 and bulge:
            p[(a>.9)&(a<1.6)&(z>.8)&(z<1.4), axis] += .025
        clouds.append(p); objects.extend([k+1]*len(p)); labels.extend([2]*len(p))
    a,b=np.meshgrid(u,v)
    for z, label in [(0.,1),(2.6,0)]:
        p=np.c_[a.ravel(),b.ravel(),np.full(a.size,z)]
        clouds.append(p);objects.extend([0]*len(p));labels.extend([label]*len(p))
    if clutter:
        a,z=np.meshgrid(np.arange(1.,2.,step),np.arange(.6,2.,step))
        p=np.c_[np.full(a.size,2.),a.ravel(),z.ravel()]
        clouds.append(p);objects.extend([-1]*len(p));labels.extend([12]*len(p))
    return np.vstack(clouds), np.array(objects), np.array(labels)


def config(**kwargs):
    from room_walls.config import Config
    return Config(voxel_mm=40, ransac_trials=160, min_plane_points=60,
                  cluster_eps_mm=130, cluster_min_points=3, min_wall_width_m=.6,
                  min_wall_height_m=1., min_wall_area_m2=.6,
                  radius_mm=130, radius_min_neighbors=3, **kwargs)
