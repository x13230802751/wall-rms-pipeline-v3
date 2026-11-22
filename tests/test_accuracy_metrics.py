# 测试墙实例匹配、失败计分、误差分解和人工标注评测接口。
import importlib.util
import unittest
import numpy as np


class AccuracyMetricTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('evaluation'), 'Evaluation package missing')

    def test_matching_maximizes_valid_pair_count_before_iou(self):
        from evaluation.metrics import match_iou
        self.assertEqual(match_iou(np.array([[.51,.90],[.49,.51]]),.5),[(0,0),(1,1)])

    def test_low_overlap_is_not_a_true_positive(self):
        from evaluation.metrics import instance_scores
        truth=np.array([1]*4+[2]*4+[0]*2)
        r=instance_scores(truth,[np.array([0]),np.array([4,5,6,8])],.5)
        self.assertEqual((r['tp'],r['fp'],r['fn']),(1,1,1))
        self.assertAlmostEqual(r['iou_matrix'][1,1],.6)
        self.assertAlmostEqual(r['binary_precision'],4/5)
        self.assertAlmostEqual(r['binary_recall'],4/8)

    def test_missing_predictions_stay_in_denominator(self):
        from evaluation.metrics import instance_scores, summarize_wall_rows
        r=instance_scores(np.array([1]*5+[2]*5),[],.5)
        self.assertEqual(r['fn'],2);self.assertEqual(r['recall'],0)
        summary=summarize_wall_rows([{'matched':False},{'matched':True,'e_selection_mm':.1,'e_total_mm':.2,
                                     'precision':1.,'recall':1.,'iou':1.,'defect_recall':None}])
        self.assertEqual(summary['valid_rate'],.5)
        self.assertEqual(summary['success_02'],.5)
        self.assertAlmostEqual(summary['mae_selection_mm'],.1)

    def test_merge_and_split_not_counted_as_two_correct_walls(self):
        from evaluation.metrics import instance_scores
        truth=np.array([1]*5+[2]*5)
        r=instance_scores(truth,[np.arange(10)],.5)
        self.assertEqual(r['tp'],1);self.assertEqual(r['fn'],1)
        r=instance_scores(np.ones(10,int),[np.arange(5),np.arange(5,10)],.5)
        self.assertEqual((r['tp'],r['fp']),(1,1))

    def test_reference_rms_and_error_decomposition(self):
        from evaluation.metrics import reference_plane, decompose
        u,v=np.meshgrid(np.linspace(-2,2,30),np.linspace(-1,1,20));p=np.c_[u.ravel(),v.ravel(),np.zeros(u.size)]
        theta=.73;rot=np.array([[np.cos(theta),0,np.sin(theta)],[0,1,0],[-np.sin(theta),0,np.cos(theta)]])
        r=reference_plane(p@rot.T+[8,9,10])
        self.assertLess(r['rms_mm'],1e-8)
        d=decompose(5.,3.,2.,1.)
        self.assertEqual(d['e_total_mm'],4.)
        self.assertEqual(d['e_selection_mm']+d['e_noise_mm']+d['e_visibility_mm'],d['e_total_mm'])

    def test_zero_reference_relative_error_undefined(self):
        from evaluation.metrics import relative_error
        self.assertIsNone(relative_error(.2,0))
        self.assertAlmostEqual(relative_error(1.1,1),10)

    def test_generator_truth_precedes_observation_and_is_reproducible(self):
        from evaluation.scenes import generate
        a=generate(2001,'bulge60');b=generate(2001,'bulge60')
        self.assertTrue(np.array_equal(a['points'],b['points']))
        self.assertEqual(len(a['full_refs']),4)
        self.assertGreater(a['defect'].sum(),0)
        for k in a['full_refs']:
            self.assertTrue(np.all(a['labels'][a['instances']==k]==2))
        l=generate(2001,'l_room');self.assertEqual(len(l['full_refs']),6)

    def test_room_success_penalizes_extra_wall_and_uses_room_count_for_ci(self):
        from evaluation.metrics import instance_scores, summarize_wall_rows
        from evaluation.summarize import summarize_group
        row=dict(matched=True,e_selection_mm=.0,e_total_mm=.0,iou=1.,precision=1.,recall=1.,defect_recall=None)
        def record(extra):
            score=instance_scores(np.array([1,1,1,0]),[np.arange(3)]+([np.array([3])] if extra else []))
            return dict(source='test',mode='expanded',condition='test',status='completed',walls=[row],
                        summary=summarize_wall_rows([row]),instance={t:score for t in ['0.25','0.5','0.75']})
        bad=summarize_group([record(True) for _ in range(20)],np.random.default_rng(1))
        self.assertEqual(bad['strict_joint_success'],1.)
        self.assertEqual(bad['room_joint_success'],0.)
        self.assertAlmostEqual(bad['room_joint_success_exact_ci95'][1],1-.025**(1/20))
        good=summarize_group([record(False) for _ in range(20)],np.random.default_rng(1))
        self.assertEqual(good['room_joint_success'],1.)
        self.assertAlmostEqual(good['room_joint_success_exact_ci95'][0],.025**(1/20))

    def test_manual_reference_interface_measures_ignored_domain_and_rejects_unreviewed(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from evaluation.manual_reference import main
        u,v=np.meshgrid(np.arange(5.),np.arange(4.));points=np.c_[u.ravel(),v.ravel(),np.zeros(u.size)]
        truth=np.ones(len(points),dtype=int);truth[-1]=-1
        wall=dict(id='W01',paper_indices=np.arange(len(points)),expanded_indices=np.arange(len(points)),
                  plane_center_m=[2,1.5,0],plane_normal=[0,0,1],u=[1,0,0],v=[0,1,0],
                  coverage_grid_mm=100,warnings=[])
        catalog=dict(cloud_payload_sha256='fixture-hash',walls=[wall])
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);np.save(folder/'labels.npy',truth)
            meta=dict(cloud_payload_sha256='fixture-hash',reviewers=['fixture-a','fixture-b'],
                      adjudicated=True,blind_to_predictions=True,boundary_policy='Test fixture',unit='m')
            path=folder/'metadata.json';path.write_text(json.dumps(meta),encoding='utf-8')
            argv=['manual_reference','--catalog','unused','--labels',str(folder/'labels.npy'),
                  '--metadata',str(path),'--out',str(folder/'result')]
            with patch('sys.argv',argv),patch('evaluation.manual_reference.load_catalog',return_value=(points,catalog)):
                main()
            result=json.loads((folder/'result/manual_reference_evaluation.json').read_text())
            for mode in result['results']:
                self.assertEqual((mode['tp'],mode['fp'],mode['fn']),(1,0,0))
                self.assertEqual(mode['rows'][0]['n_selected'],len(points)-1)
                self.assertAlmostEqual(mode['rows'][0]['error_mm'],0)
            self.assertAlmostEqual(result['ignored_point_fraction'],1/len(points))
            self.assertIn('not independent physical',result['reference_level'])
            meta['adjudicated']=False;path.write_text(json.dumps(meta),encoding='utf-8');argv[-1]=str(folder/'rejected')
            with patch('sys.argv',argv),patch('evaluation.manual_reference.load_catalog',return_value=(points,catalog)):
                with self.assertRaisesRegex(ValueError,'adjudicated'):main()


if __name__=='__main__':unittest.main()
