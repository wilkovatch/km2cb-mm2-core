"""Small synthetic checks for spline decal migration, paired export and legacy writer compatibility."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
import numpy as np

CORE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE / 'exporters/psdl'))
sys.path.insert(0, str(CORE.parents[1] / 'python'))
from writers.decal_writer import DecalWriter
from decal_check import read_pathset, check_path

spec = importlib.util.spec_from_file_location('decal_migration', CORE / 'migrations/3.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class Scene:
    # the parts as the writers read them (see scene.py), from dicts already in the space of the writers
    def __init__(self, objects):
        self.parts = [SimpleNamespace(name=o['name'], type=o['name'].split(',')[-1].split('_')[1],
                                      properties=o['properties'], vertices=[tuple(v) for v in o['vertices']])
                      for o in objects]


def audit_preview(export_json, pathset):
    """Compare evaluated preview edges/UVs with the actual game paths, including the game's 1 cm lift."""
    from DecodeExportedJson import DecodeExportedJson
    data = DecodeExportedJson().decode_json(export_json)
    paths = read_pathset(pathset)
    index = 0
    for element in data.get('customElements') or []:
        if element['type'] != 'decal':
            continue
        mesh = element['data']['mesh']
        vertices = mesh['vertices']
        uvs = mesh['uvs']
        for piece_index,piece in enumerate(element['spline']['pieces']):
            name,points = paths[index]
            assert not check_path(name,points)[1], name
            ends = [points[0],points[1],points[-2],points[-1]]
            for corner in range(4):
                v = np.array(vertices[piece_index*4+corner])
                game = np.array([-v[0],v[1]-0.01,v[2]])
                distances = [np.linalg.norm(game-p) for p in ends]
                actual = int(np.argmin(distances))
                assert distances[actual] < 0.001, (index,corner,distances)
                np.testing.assert_allclose(uvs[piece_index*4+corner][0], actual%2, atol=0.0001)
                width = np.linalg.norm(points[0]-points[1])
                v_game = np.floor(np.linalg.norm(points[-2]-points[0])/width+0.5) if actual>=2 else 0
                np.testing.assert_allclose(uvs[piece_index*4+corner][1],v_game,atol=0.001)
            index += 1
    assert index == len(paths), (index,len(paths))
    print(str(index) + ' preview spans match exported game edges and UVs')


class DecalTests(unittest.TestCase):
    def test_migration_accepts_null_city_collections(self):
        decal = dict(name='Legacy decal',texture='texture/rails.tex',width=2,
                     points=[dict(point=dict(localPosition=p)) for p in ([1,2,3],[4,5,6])])
        for values in ({}, dict(terrainPoints=None), dict(customElements=None), dict(terrainPoints=None,customElements=None)):
            with self.subTest(values=values):
                data = dict(values,cityProperties=dict(decals=[decal]))
                before = copy.deepcopy(data)
                out = migration.migrate_city(data)
                self.assertEqual(data,before)
                self.assertEqual([p['id'] for p in out['terrainPoints']],[0,1])
                self.assertEqual(out['customElements'][0]['id'],0)
                self.assertEqual(out['customElements'][0]['points']['spline'],[0,1])
                self.assertEqual(migration.migrate_city(out),out)

    def test_migration_preserves_data_and_is_idempotent(self):
        data = dict(cityProperties=dict(decals=[dict(name='Zebra', texture='texture/zebra.tex', width=3,
            points=[dict(point=dict(localPosition=dict(x=4,y=2,z=10))), dict(point=dict(localPosition=dict(x=7,y=3,z=15)))]),
            dict(name='Incomplete',points=[])], cableCarRailDecals=True, cableCarRailWidth=2),
            terrainPoints=[dict(id=9,position=dict(x=0,y=0,z=0))], customElements=[dict(id=5,name='Existing',state=dict(type='room'))])
        before = copy.deepcopy(data)
        out = migration.migrate_city(data)
        self.assertEqual(data, before)
        self.assertEqual(out['customElements'][0], before['customElements'][0])
        self.assertEqual([e['id'] for e in out['customElements']], [5,6,7])
        self.assertEqual(out['customElements'][1]['points']['spline'], [10,11])
        self.assertEqual(out['terrainPoints'][1]['position'], dict(x=4,y=2,z=10))
        self.assertEqual(out['customElements'][1]['state']['texture'], 'texture/zebra.tex')
        self.assertEqual(out['cityProperties'], {})
        self.assertEqual(migration.migrate_city(out), out)

    def test_migration_validates_before_mutation(self):
        data = dict(cityProperties=dict(decals=[dict(points=[dict(point=dict(localPosition=dict(x=float('nan'))))])]))
        with self.assertRaises(ValueError): migration.migrate_city(data)
        self.assertIn('decals', data['cityProperties'])

    def test_writer_preserves_pairs_winding_tiles_and_legacy_inputs(self):
        objects = [dict(name='0_DECAL', properties=dict(texture='paired',strip_pairs='1'),
                        vertices=[[-2,0,1],[2,0,1],[-2,20,3],[2,20,3]]),
                   dict(name='0_DECAL', properties=dict(texture='legacy',width='2'),vertices=[[10,0,0],[10,20,0]])]
        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp)/'test.psdl')
            DecalWriter(Scene(objects),target).write()
            path = Path(tmp)/'test/decals.pathset'
            paths = read_pathset(path)
            self.assertEqual({name for name,_ in paths}, {'paired','legacy'})
            for name,points in paths:
                self.assertEqual(check_path(name,points)[1], [])
                if name == 'paired':
                    np.testing.assert_allclose(sorted(p.tolist() for p in points[:2]), [[-2,1,0],[2,1,0]])
                    np.testing.assert_allclose(sorted(p.tolist() for p in points[-2:]), [[-2,3,20],[2,3,20]])
            DecalWriter(Scene([]),target).write()
            self.assertFalse(path.exists())

    def test_invalid_pairs_do_not_write(self):
        objects = [dict(name='0_DECAL',properties=dict(texture='bad',strip_pairs='1'),vertices=[[0,0,0]])]
        with tempfile.TemporaryDirectory() as tmp:
            DecalWriter(Scene(objects),str(Path(tmp)/'test.psdl')).write()
            self.assertFalse((Path(tmp)/'test/decals.pathset').exists())

    def test_single_decal_corners_and_export(self):
        from decals import decal_single_corners, export_single_decal
        corners = decal_single_corners(dict(position=[10, 2, 20], scale=[2, 1, 10]))
        np.testing.assert_allclose(corners, [[9, 2, 15], [11, 2, 15], [9, 2, 25], [11, 2, 25]])
        # yaw 90 turns the length (Z) to X; the size and the winding (seen from above in the editor's left-handed space,
        # the same as the strips of the spline decals) don't change
        for rotation in ([0, 90, 0], [0, 37, 0], [0, 0, 0]):
            c = np.array(decal_single_corners(dict(position=[0, 0, 0], rotation=rotation, scale=[2, 1, 10])))
            self.assertAlmostEqual(np.linalg.norm(c[1] - c[0]), 2)
            self.assertAlmostEqual(np.linalg.norm(c[2] - c[0]), 10)
            self.assertLess(np.cross(c[1] - c[0], c[2] - c[0])[1], 0)
        c = np.array(decal_single_corners(dict(position=[0, 0, 0], rotation=[0, 90, 0], scale=[2, 1, 10])))
        np.testing.assert_allclose(c[2] - c[0], [10, 0, 0], atol=1e-9)
        # pitch 90 lowers the far end (a positive X rotation tips the front down, as in the engine)
        c = np.array(decal_single_corners(dict(position=[0, 0, 0], rotation=[90, 0, 0], scale=[2, 1, 10])))
        np.testing.assert_allclose(c[2] - c[0], [0, -10, 0], atol=1e-9)
        processor = SimpleNamespace(find_block=lambda position: 0, get_tex=lambda tex: tex.split('/')[-1])
        decal = dict(type='decalSingle', data=dict(name='Single', fields=dict(state=dict(texture='texture/zebra.tex'))),
                     points=dict(center=dict(id=0, position=[10, 2, 20], rotation=[0, 0, 0], scale=[2, 1, 10])))
        res = []
        export_single_decal(processor, decal, res)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].name, '0_DECAL')
        self.assertEqual(res[0].properties['texture'], 'zebra')
        self.assertEqual(res[0].properties['strip_pairs'], '1')
        self.assertEqual(len(res[0].vertices), 4)
        res = []
        decal['data']['fields']['state']['texture'] = ''
        export_single_decal(processor, decal, res)
        self.assertEqual(res, [])

    def test_city_import_creates_editable_splines_and_reports_width_loss(self):
        sys.path.insert(0, str(CORE / 'scripts/importCity'))
        from _test_import_city import write_psdl
        from main import prepare
        scene = Scene([dict(name='0_DECAL', properties=dict(texture='zebra',strip_pairs='1'),
                            vertices=[[-1,0,0],[1,0,0],[-2,20,0],[2,20,0]])])
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'city/test.psdl'
            source.parent.mkdir()
            write_psdl(source)
            DecalWriter(scene,str(source)).write()
            city,_ = prepare(dict(psdlFile=str(source),sourceRoot=tmp,importBai=False,importInst=False,
                                  importProps=False,importSettings=False,importPaths=True))
            decals = [e for e in city.elements if e['type']=='decal']
            self.assertEqual(len(decals),1)
            self.assertEqual(decals[0]['state']['curveType'],2)
            self.assertAlmostEqual(decals[0]['state']['width'],3)
            self.assertGreater(len(decals[0]['points']['spline']),1)
            self.assertNotIn('decals',city.properties)
            self.assertTrue(any('variable width' in w['message'] for w in city.warnings))


if __name__ == '__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--preview':
        audit_preview(sys.argv[2],sys.argv[3])
    else:
        unittest.main()
