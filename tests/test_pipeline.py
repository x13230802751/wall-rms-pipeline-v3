# 测试自动找墙、四点局部测量、缺陷保留及杂物处理的完整流程。
import importlib.util
import unittest
import numpy as np
from fixtures import room, config


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('room_walls'), 'Pipeline package is not implemented')

    def test_four_walls_and_independent_rms(self):
        from room_walls.discovery import discover
        from room_walls.measurement import measure_wall
        p, truth, _=room()
        result=discover(p, config())
        self.assertEqual(len(result['walls']),4)
        seen=[]
        for wall in result['walls']:
            ids=wall['expanded_indices']; counts=np.bincount(truth[ids],minlength=5)
            obj=int(np.argmax(counts));seen.append(obj)
            self.assertGreater(counts[obj]/len(ids),.99)
            self.assertGreater(counts[obj]/np.sum(truth==obj),.95)
            r=measure_wall(p,wall)
            centered=p[r['indices']]-p[r['indices']].mean(0)
            independent=np.sqrt(max(0,np.linalg.eigvalsh(centered.T@centered/len(centered))[0]))*1000
            self.assertAlmostEqual(r['rms_mm'],independent,places=6)
            if obj==1:self.assertAlmostEqual(r['rms_mm'],2.,delta=.1)
        self.assertEqual(sorted(seen),[1,2,3,4])

    def test_bulge_recovered_beyond_ransac_threshold(self):
        from room_walls.discovery import discover
        from room_walls.measurement import measure_wall
        p,truth,_=room(roughness_mm=0,bulge=True)
        result=discover(p,config())
        wall=max(result['walls'],key=lambda w:np.sum(truth[w['expanded_indices']]==1))
        bulge=(truth==1)&(p[:,0]>.02)
        self.assertGreater(np.mean(np.isin(np.flatnonzero(bulge),wall['expanded_indices'])),.95)
        expanded=measure_wall(p,wall); strict=measure_wall(p,wall,mode='paper')
        self.assertGreater(expanded['rms_mm'],strict['rms_mm']+2)

    def test_semantics_and_floor_contact_reject_board(self):
        from room_walls.discovery import discover
        p,truth,labels=room(clutter=True)
        r=discover(p,config(),labels=labels)
        self.assertEqual(len(r['walls']),4)
        self.assertEqual(r['mode'],'external_semantics')
        self.assertTrue(all(np.all(labels[w['expanded_indices']]==2) for w in r['walls']))
        geometric=discover(p,config())
        self.assertEqual(len(geometric['walls']),4)

    def test_rotation_and_original_indices(self):
        from room_walls.discovery import discover
        p,truth,_=room(roughness_mm=0)
        a=.6;b=.3
        rz=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
        rx=np.array([[1,0,0],[0,np.cos(b),-np.sin(b)],[0,np.sin(b),np.cos(b)]])
        rotation=rz@rx
        transformed=p@rotation.T+[12,-3,8]
        transformed=np.vstack([[np.nan,0,0],transformed])
        r=discover(transformed,config(up=tuple(rotation[:,2])))
        self.assertEqual(len(r['walls']),4)
        self.assertEqual(r['n_invalid'],1)
        self.assertTrue(all(w['expanded_indices'].min()>=1 for w in r['walls']))

    def test_four_points_limit_selected_wall(self):
        from room_walls.discovery import discover
        from room_walls.measurement import measure_wall
        p,truth,_=room()
        r=discover(p,config())
        w=max(r['walls'],key=lambda w:np.sum(truth[w['expanded_indices']]==1))
        roi={'unit':'m','corners':[[0,.5,.4],[0,2.5,.4],[0,2.5,2.2],[0,.5,2.2]]}
        m=measure_wall(p,w,roi=roi)
        self.assertTrue(np.all(truth[m['indices']]==1))
        self.assertTrue(np.all((p[m['indices'],1]>=.5)&(p[m['indices'],1]<=2.5)))
        self.assertLess(len(m['indices']),len(w['expanded_indices']))

    def test_bad_inputs_fail_instead_of_zero(self):
        from room_walls.discovery import discover
        from room_walls.config import Config
        with self.assertRaises(ValueError):Config(up=(0,0,0))
        with self.assertRaises(ValueError):Config(ransac_mm=-1)
        with self.assertRaises(ValueError):Config(ransac_trials=True)
        with self.assertRaises(ValueError):discover(np.zeros((20,3)),config())
        p,_,labels=room()
        with self.assertRaises(ValueError):discover(p,config(),labels=labels[:-1])

    def test_missing_floor_rejected_and_all_wall_points_disjoint(self):
        from room_walls.discovery import discover
        p,truth,labels=room()
        with self.assertRaises(ValueError):discover(p[labels!=1],config())
        result=discover(p,config())
        ids=np.concatenate([w['expanded_indices'] for w in result['walls']])
        self.assertEqual(len(ids),len(np.unique(ids)))

    def test_integral_json_numbers_are_normalized(self):
        from room_walls.config import Config
        cfg=Config(ransac_trials=160.0,max_planes=20.0)
        self.assertIsInstance(cfg.ransac_trials,int)
        self.assertIsInstance(cfg.max_planes,int)

    def test_geometric_clutter_failure_is_measured_and_semantic_mask_removes_it(self):
        from room_walls.discovery import discover
        from room_walls.measurement import measure_wall
        p,truth,labels=room(roughness_mm=0)
        a,z=np.meshgrid(np.arange(.7,1.2,.04),np.arange(1.,1.5,.04))
        clutter=np.c_[np.full(a.size,.03),a.ravel(),z.ravel()]
        p=np.vstack([p,clutter]);truth=np.r_[truth,np.full(len(clutter),-1)];labels=np.r_[labels,np.full(len(clutter),12)]
        geometry=discover(p,config());semantic=discover(p,config(),labels=labels)
        gw=max(geometry['walls'],key=lambda w:np.sum(truth[w['expanded_indices']]==1))
        sw=max(semantic['walls'],key=lambda w:np.sum(truth[w['expanded_indices']]==1))
        self.assertGreater(measure_wall(p,gw)['rms_mm'],2.)
        self.assertLess(measure_wall(p,sw)['rms_mm'],1e-6)
        self.assertIn('NO_SEMANTIC_MODEL_CLUTTER_POSSIBLE',gw['warnings'])

    def test_local_bulge_roi_succeeds_when_paper_comparison_is_empty(self):
        import tempfile
        from pathlib import Path
        from room_walls.discovery import discover
        from room_walls.__main__ import measurement
        p,truth,_=room(roughness_mm=0,bulge=True)
        result=discover(p,config())
        wall=max(result['walls'],key=lambda w:np.sum(truth[w['expanded_indices']]==1))
        roi={'unit':'m','corners':[[.025,1.,.9],[.025,1.5,.9],[.025,1.5,1.3],[.025,1.,1.3]],'min_points':3}
        with tempfile.TemporaryDirectory() as temp:
            r=measurement(p,wall,Path(temp)/'measure','expanded',roi,{})
            self.assertGreater(r['n_selected'],3)
            self.assertIsNone(r['comparison']['other_rms_mm'])
            self.assertIn('unavailable',r['comparison'])


if __name__=='__main__':unittest.main()
