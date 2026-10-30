"""Bounded synthetic train migration, import and native-control PATHSET checks."""
import copy
import gzip
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE/'exporters/psdl'), str(CORE.parents[1]/'python'), str(CORE/'scripts/importCity')]
from train_export import get_train_lines, export_trains
from _formats import read_pathset
from MigrationHelper import MigrationHelper
spec = importlib.util.spec_from_file_location('train_migration', CORE/'migrations/4.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class TrainTests(unittest.TestCase):
    def test_migration_accepts_null_city_collections(self):
        line = dict(name='Legacy train', points=[dict(point=dict(localPosition=p)) for p in ([1,-13,2],[3,-14,4],[5,-15,6])])
        for values in ({}, dict(terrainPoints=None), dict(customElements=None), dict(terrainPoints=None,customElements=None)):
            with self.subTest(values=values):
                data = dict(values, cityProperties=dict(trainLines=[line],cityName='Keep'))
                before = copy.deepcopy(data)
                out = migration.migrate_city(data)
                self.assertEqual(data,before)
                self.assertEqual([p['id'] for p in out['terrainPoints']],[0,1,2])
                self.assertEqual(out['customElements'][0]['id'],0)
                self.assertEqual(out['customElements'][0]['points']['spline'],[0,1,2])
                self.assertEqual(out['cityProperties'],dict(cityName='Keep'))
                self.assertEqual(migration.migrate_city(out),out)

    def test_folder_migration_backs_up_and_publishes_version_last(self):
        data=dict(terrainPoints=None,customElements=None,cityProperties=dict(trainLines=[dict(name='Old',points=[])]))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with gzip.open(root/'city.json.gz','wt') as f:json.dump(data,f)
            (root/'preferences.json').write_text(json.dumps(dict(coreVersion=3,other='keep')))
            original=(root/'city.json.gz').read_bytes()
            migration.process_folder(MigrationHelper(folder+'/'))
            self.assertEqual((root/'city.json.gz.v3.bak').read_bytes(),original)
            self.assertEqual(json.loads((root/'preferences.json.v3.bak').read_text())['coreVersion'],3)
            self.assertEqual(json.loads((root/'preferences.json').read_text()),dict(coreVersion=4,other='keep'))
            converted=(root/'city.json.gz').read_bytes()
            migration.process_folder(MigrationHelper(folder+'/'))
            self.assertEqual((root/'city.json.gz').read_bytes(),converted)

    def test_migration_preserves_ids_and_incomplete_routes(self):
        data = dict(terrainPoints=[dict(id=7,position=[1,2,3])],customElements=[dict(id=9,state=dict(type='room'))],
                    cityProperties=dict(cityName='Keep', trainLines=[dict(name='Line',points=[dict(point=dict(localPosition=dict(x=4,y=-13,z=6)))]),dict(name='Empty')]))
        before = copy.deepcopy(data)
        out = migration.migrate_city(data)
        self.assertEqual(data,before)
        self.assertEqual(out['terrainPoints'][0],before['terrainPoints'][0])
        self.assertEqual(out['customElements'][0],before['customElements'][0])
        self.assertEqual(out['customElements'][1]['points']['spline'],[8])
        self.assertEqual(out['customElements'][2]['name'],'Empty')
        self.assertEqual(out['customElements'][2]['points']['spline'],[])
        self.assertEqual(out['cityProperties'],dict(cityName='Keep'))
        self.assertEqual(migration.migrate_city(out),out)

    def test_invalid_migration_does_not_mutate_input(self):
        data=dict(cityProperties=dict(trainLines=[dict(points=[dict(point=dict(localPosition=[1,float('nan'),3]))])]))
        with self.assertRaises(ValueError): migration.migrate_city(data)
        self.assertIn('trainLines',data['cityProperties'])

    def test_export_uses_controls_not_preview_and_roundtrips(self):
        controls=[[2,-13,4],[12,-14,24],[32,-15,54]]
        element=dict(type='train',data=dict(name='London defaults'),points=dict(spline=[dict(id=i,position=p) for i,p in enumerate(controls)]),
                     spline=dict(sections=[dict(center=[999,999,999])]))
        data=dict(customElements=[element])
        with tempfile.TemporaryDirectory() as folder:
            export_trains(data,folder+'/', 'test')
            paths=read_pathset(Path(folder)/'test_train.pathset')
        self.assertEqual(len(paths),1)
        self.assertEqual(paths[0]['type'],2)
        self.assertEqual(paths[0]['spacing'],20)
        self.assertEqual(paths[0]['points'],[[-p[0],p[1],p[2]] for p in controls])
        element['spline']['sections'] *= 50
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'test_train.pathset'
            target.write_bytes(b'old exported trains')
            export_trains(dict(customElements=[]),folder+'/', 'test')
            self.assertFalse(target.exists())
        self.assertEqual(get_train_lines(data),[[(-p[0],p[1],p[2]) for p in controls]])

    def test_incomplete_and_invalid_routes_warn_and_skip(self):
        for controls in ([],[[0,0,0]],[[0,0,0],[1,0,0]],[[0,0,0],[0,0,0],[1,0,0]],[[0,0,0],[math.inf,0,0],[1,0,0]]):
            with self.subTest(controls=controls):
                data=dict(customElements=[dict(type='train',points=dict(spline=[dict(position=p) for p in controls]))])
                self.assertEqual(get_train_lines(data),[])

    def test_import_creates_native_train_elements(self):
        from _test_import_city import write_psdl
        from main import prepare
        controls=[[1,-13,10],[30,-14,20],[80,-13,90]]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'city').mkdir()
            (root/'race/test').mkdir(parents=True)
            write_psdl(root/'city/test.psdl')
            data=dict(customElements=[dict(type='train',points=dict(spline=[dict(position=p) for p in controls]))])
            export_trains(data,str(root/'race/test')+'/', 'test')
            city,_=prepare(dict(psdlFile=str(root/'city/test.psdl'),importBai=False,importInst=False,importProps=False,importSettings=False,importPaths=True))
            train=next(e for e in city.elements if e['type']=='train')
            points={p['id']:p['position'] for p in city.points}
            self.assertEqual(train['state']['curveType'],3)
            self.assertEqual([points[i] for i in train['points']['spline']],controls)
            self.assertNotIn('trainLines',city.properties)


if __name__ == '__main__': unittest.main()
