# 测试墙面发现与测量命令行、输出文件及来源一致性校验。
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from fixtures import room,config

ROOT=Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.p,_,cls.labels=room(step=.10)
        cls.cloud=cls.root/'room.csv'
        np.savetxt(cls.cloud,cls.p,delimiter=',',header='x,y,z',comments='')
        cls.cfg=cls.root/'config.json';cls.cfg.write_text(json.dumps(config().to_dict()))

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def runcli(self,*args,code=0):
        env=os.environ.copy();env['MPLCONFIGDIR']=str(self.root/'mpl')
        p=subprocess.run([sys.executable,'-m','room_walls',*map(str,args)],cwd=ROOT,
                         env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(p.returncode,code,p.stdout+'\n'+p.stderr)
        return p

    def test_discover_then_select_and_reject_changed_source(self):
        out=self.root/'discover'
        self.runcli('discover','--cloud',self.cloud,'--unit','m','--config',self.cfg,'--out',out)
        cat=json.loads((out/'catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(len(cat['walls']),4)
        self.assertTrue((out/'index.html').exists());self.assertTrue((out/'overview.png').exists())
        selected=self.root/'selected'
        self.runcli('measure','--catalog',out/'catalog.json','--wall','W01','--out',selected)
        r=json.loads((selected/'result.json').read_text())
        self.assertEqual(r['wall_id'],'W01');self.assertGreater(r['n_selected'],20)
        distances=np.genfromtxt(selected/'distances.csv',delimiter=',',names=True)
        self.assertAlmostEqual(np.sqrt(np.mean(distances['signed_distance_mm']**2)),r['rms_mm'],places=9)
        self.runcli('measure','--catalog',out/'catalog.json','--wall','W99','--out',self.root/'bad',code=2)
        self.runcli('measure','--catalog',out/'catalog.json','--wall','W01','--out',selected,code=2)
        changed=self.root/'changed.csv';changed.write_bytes(self.cloud.read_bytes()+b'\n')
        self.runcli('measure','--catalog',out/'catalog.json','--cloud',changed,'--wall','W01','--out',self.root/'changed',code=2)
        # Any changed array file is rejected before measurement.
        with (out/'assignments.npz').open('ab') as f:f.write(b'changed')
        self.runcli('measure','--catalog',out/'catalog.json','--wall','W01','--out',self.root/'corrupt',code=2)

    def test_mm_semantic_run_all_and_requested_ids(self):
        mm=self.root/'mm.csv';np.savetxt(mm,self.p*1000,delimiter=',',header='x,y,z',comments='')
        labels=self.root/'labels.npy';np.save(labels,self.labels)
        out=self.root/'all'
        self.runcli('run','--cloud',mm,'--unit','mm','--labels',labels,'--config',self.cfg,'--walls','all','--out',out)
        data=json.loads((out/'summary.json').read_text())
        self.assertEqual(len(data['measurements']),4)
        self.assertEqual(data['mode'],'external_semantics')
        self.assertEqual(data['gt_comparison'],'not_performed_no_matched_reference')
        self.assertTrue(all((out/'measurements'/m['wall_id']/'deviation.png').exists() for m in data['measurements']))
        self.runcli('run','--cloud',self.cloud,'--unit','m','--config',self.cfg,'--walls','W01,W03','--out',self.root/'two')
        selected=json.loads((self.root/'two'/'summary.json').read_text())
        self.assertEqual([m['wall_id'] for m in selected['measurements']],['W01','W03'])


if __name__=='__main__':unittest.main()
