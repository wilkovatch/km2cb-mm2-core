"""Synthetic checks of migration 10 (the front-only building lines become polygonal buildings)."""
import copy
import gzip
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

CORE = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE.parents[1] / 'python'))
from MigrationHelper import MigrationHelper

spec = importlib.util.spec_from_file_location('front_only_migration', CORE / 'migrations/10.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def side(name, floors=1):
    return dict(type='psdl', name=name, hasGroundFloor=True, lowUpperFloorsCount=floors)


def building(front):
    return dict(type='psdl', front=True, frontState=front, height=10.0, depth=5.0)


def point(i, x, z, dividing=False):
    return dict(id=i, position=dict(x=x, y=0.0, z=z), dividing=dividing)


def line(i, name, ids, buildings, front_only=True, loop=True, preset=''):
    return dict(id=i, name=name, linePoints=ids, buildings=buildings, sides=[], instanceState=dict(projectToGround=True),
                state=dict(type='psdl', name=preset, frontOnly=front_only, loop=loop, invertDirection=False, height=18.0,
                           roofTex='roof.tex', fixBound=True, hudmapCategory=4))


def city():
    points = [point(0, 0, 0), point(1, 30, 0), point(2, 30, 20, True), point(3, 0, 20),
              point(10, 100, 0), point(11, 130, 0), point(12, 130, 10), point(13, 115, 10), point(14, 115, 25), point(15, 100, 25),
              point(20, 200, 0), point(21, 230, 0),
              point(30, 300, 0), point(31, 330, 0)]
    a, b, c = side('a'), side('b', 2), side('a')
    return dict(
        terrainPoints=points,
        buildingLines=[
            # a square with a dividing point: segments 0 and 1 in the first building, 2 in the second, 3 in the loop one
            line(0, 'Square', [0, 1, 2, 3], [building(a), building(b), building(c)], preset='Old facade'),
            # a concave outline, all the fronts equal
            line(1, 'L shape', [10, 11, 12, 13, 14, 15], [building(side('l')), building(side('l'))]),
            line(2, 'Short', [20, 21], [building(side('s'))]),
            line(3, 'Normal', [30, 31], [building(side('n'))], front_only=False, loop=False)],
        customElements=[dict(id=0, name='Decal', state=dict(type='decal', room=dict(kind='buildingLine', id=3)),
                             source=dict(kind='buildingLine', id=1), points={}, containerId=-1)])


def presets():
    return dict(presets={
        'buildingSide': [dict(type='psdl', name='Default', Name='Default', hasGroundFloor=True)],
        'buildingLine': [dict(type='psdl', name='Default', Name='Default', frontOnly=False, loop=False, height=28.0, roofTex='def.tex', fixBound=False, hudmapCategory=0, uMult=-0.25, vMult=-0.25),
                         dict(type='psdl', name='Old facade', Name='Old facade', frontOnly=True, loop=True, height=12.0, roofTex='old.tex', hudmapCategory=0)]})


class FrontOnlyMigration(unittest.TestCase):
    def migrated(self):
        new_presets, moved = migration.migrate_presets(presets())
        return migration.migrate_city(city(), moved, new_presets['presets'])

    def test_lines_become_polygonal_buildings(self):
        data, converted, short = self.migrated()
        self.assertEqual(converted, ['Square', 'L shape'])
        self.assertEqual(short, ['Short'])
        polygons = data['polygonalBuildings']
        self.assertEqual([p['id'] for p in polygons], [0, 1])
        self.assertEqual(polygons[0]['points'], [0, 1, 2, 3])
        state = polygons[0]['state']
        self.assertEqual((state['type'], state['height'], state['roofTex'], state['fixBound'], state['hudmapCategory']), ('psdl', 18.0, 'roof.tex', True, 4))
        self.assertNotIn('frontOnly', state)
        self.assertEqual(polygons[0]['instanceState'], dict(projectToGround=True))
        self.assertEqual(state['name'], 'Old facade')  # its preset moved too

    def test_walls_get_the_fronts_of_their_segments(self):
        data = self.migrated()[0]
        square = data['polygonalBuildings'][0]
        self.assertTrue(square['state']['individualSides'])
        self.assertEqual([s['name'] for s in square['wallStates']], ['a', 'a', 'b', 'a'])
        self.assertEqual(square['wallStates'][2]['lowUpperFloorsCount'], 2)

    def test_concave_line_keeps_its_outline_and_shared_side(self):
        data = self.migrated()[0]
        shape = data['polygonalBuildings'][1]
        self.assertEqual(shape['points'], [10, 11, 12, 13, 14, 15])
        self.assertFalse(shape['state']['individualSides'])
        self.assertNotIn('wallStates', shape)
        self.assertEqual(shape['state']['sideState']['name'], 'l')
        self.assertEqual(shape['state']['name'], '')

    def test_other_lines_and_references(self):
        data = self.migrated()[0]
        lines = data['buildingLines']
        self.assertEqual([(l['id'], l['name']) for l in lines], [(0, 'Short'), (1, 'Normal')])
        for l in lines:
            for key in ('frontOnly', 'height', 'roofTex'):
                self.assertNotIn(key, l['state'])
        element = data['customElements'][0]
        self.assertEqual(element['state']['room'], dict(kind='buildingLine', id=1))
        self.assertEqual(element['source'], dict(kind='polygonalBuilding', id=1))

    def test_presets(self):
        data, moved = migration.migrate_presets(presets())
        p = data['presets']
        self.assertEqual(moved, {'Old facade'})
        self.assertEqual([x['name'] for x in p['buildingLine']], ['Default'])
        self.assertNotIn('frontOnly', p['buildingLine'][0])
        self.assertNotIn('height', p['buildingLine'][0])
        self.assertEqual([x['name'] for x in p['polygonalBuilding']], ['Default', 'Old facade'])
        default = p['polygonalBuilding'][0]
        self.assertEqual((default['height'], default['roofTex'], default['individualSides']), (28.0, 'def.tex', False))
        self.assertEqual(default['sideState']['name'], '')
        self.assertEqual(p['polygonalBuilding'][1]['height'], 12.0)
        # an existing default is kept
        again = migration.migrate_presets(data)[0]['presets']
        self.assertEqual(again['polygonalBuilding'], p['polygonalBuilding'])

    def test_default_roof_texture(self):
        # a default line preset without a roof texture: the one of the default building
        source = presets()
        source['presets']['buildingLine'][0].pop('roofTex')
        source['presets']['building'] = [dict(type='psdl', name='Default', topTexture='building.tex')]
        p = migration.migrate_presets(source)[0]['presets']
        self.assertEqual(p['polygonalBuilding'][0]['roofTex'], 'building.tex')
        self.assertEqual(p['polygonalBuilding'][1]['roofTex'], 'old.tex')

    def test_folder(self):
        folder = tempfile.mkdtemp()
        try:
            root = pathlib.Path(folder)
            with gzip.open(root / 'city.json.gz', 'wt', encoding='utf-8') as f:
                json.dump(city(), f)
            (root / 'presets.json').write_text(json.dumps(presets()), encoding='utf-8')
            (root / 'preferences.json').write_text(json.dumps(dict(core='MidtownMadness2', coreVersion=9)), encoding='utf-8')
            migration.process_folder(MigrationHelper(folder + '/'))
            prefs = json.loads((root / 'preferences.json').read_text(encoding='utf-8'))
            self.assertEqual(prefs['coreVersion'], 10)
            with gzip.open(root / 'city.json.gz', 'rt', encoding='utf-8') as f:
                self.assertEqual(len(json.load(f)['polygonalBuildings']), 2)
            self.assertTrue((root / 'city.json.gz.v9.bak').exists())
        finally:
            shutil.rmtree(folder)


if __name__ == '__main__':
    unittest.main()
