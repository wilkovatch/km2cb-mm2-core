"""Synthetic checks of the instance state part of migration 5 (spline values, warp and line projection moved to the instance state)."""
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

spec = importlib.util.spec_from_file_location('spline_state_migration', CORE / 'migrations/5.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def road_state():
    return dict(type='psdl', Name='Main', roadWidth=5.0, project=False, projectAll=True, curveType=1, segments=7, segmentsPer100m=True, lpf=2,
                adjustLowPolyWidth=True, makeCoplanar=False, hermiteTension=0.25, subdivideEqually=True, warp=True, startCrosswalkSize=2.0)


def city():
    return dict(
        roads=[dict(id=0, state=road_state(), instanceState=dict(intersectionMove=3.0)),
               dict(id=1, state=dict(type='psdl', segments=4), instanceState=None),
               dict(id=2, state=dict(type='psdl'), instanceState={}, ghost=True)],
        intersections=[dict(id=0, state=dict(type='psdl', warp=True, sizeIncrease=1.0), instanceState=dict(seamless=True))],
        buildingLines=[dict(id=0, state=dict(type='psdl', projectToGround=True, height=8.0), instanceState={})],
        terrainPatches=[dict(id=0, state=dict(type='psdl', warp=True, projectToGround=True))],
        customElements=[dict(id=0, state=dict(type='decal', curveType=2, segments=9), points={})])


def presets():
    return dict(presets={
        'road': [road_state()],
        'intersection': [dict(type='psdl', Name='Default', warp=False, sizeIncrease=1.0)],
        'buildingLine': [dict(type='psdl', Name='Default', projectToGround=False, height=8.0)],
        'customElement/decal': [dict(type='decal', Name='Default', width=2.0, curveType=0, segments=50, segmentsPer100m=True, hermiteTension=0.5)],
        'lowLevel/train': [dict(type='train', Name='Default', curveType=3, speed=1.0)],
        'customElement/room': [dict(type='room', Name='Default', segments=3)],
        'roadPropRule': [dict(type='psdl', Name='Default', segments=3)]})


class SplineStateMigration(unittest.TestCase):
    def test_road_values_move_to_the_instance_state(self):
        data = migration.migrate_city(city())
        road = data['roads'][0]
        self.assertEqual(road['state'], dict(type='psdl', Name='Main', roadWidth=5.0, startCrosswalkSize=2.0))
        self.assertEqual(road['instanceState'], dict(intersectionMove=3.0, project=False, projectAll=True, curveType=1, segments=7, segmentsPer100m=True, lpf=2,
                                                     adjustLowPolyWidth=True, makeCoplanar=False, hermiteTension=0.25, subdivideEqually=True, warp=True))

    def test_missing_values_stay_missing(self):
        data = migration.migrate_city(city())
        self.assertEqual(data['roads'][1]['instanceState'], dict(segments=4))
        self.assertEqual(data['roads'][2]['instanceState'], {})
        self.assertTrue(data['roads'][2]['ghost'])

    def test_other_elements(self):
        data = migration.migrate_city(city())
        self.assertEqual(data['intersections'][0]['state'], dict(type='psdl', sizeIncrease=1.0))
        self.assertEqual(data['intersections'][0]['instanceState'], dict(seamless=True, warp=True))
        self.assertEqual(data['buildingLines'][0]['state'], dict(type='psdl', height=8.0))
        self.assertEqual(data['buildingLines'][0]['instanceState'], dict(projectToGround=True))
        # terrain patches have no presets, and custom elements have a single state
        self.assertEqual(data['terrainPatches'], city()['terrainPatches'])
        self.assertEqual(data['customElements'], city()['customElements'])

    def test_presets(self):
        data = migration.migrate_presets(presets())[0]['presets']
        self.assertEqual(data['road'][0], dict(type='psdl', Name='Main', roadWidth=5.0, startCrosswalkSize=2.0))
        self.assertEqual(data['intersection'][0], dict(type='psdl', Name='Default', sizeIncrease=1.0))
        self.assertEqual(data['buildingLine'][0], dict(type='psdl', Name='Default', height=8.0))
        self.assertEqual(data['customElement/decal'][0], dict(type='decal', Name='Default', width=2.0))
        self.assertEqual(data['lowLevel/train'][0], dict(type='train', Name='Default', speed=1.0))

    def test_same_names_of_other_types_are_kept(self):
        data = migration.migrate_presets(presets())[0]['presets']
        self.assertEqual(data['customElement/room'][0]['segments'], 3)
        self.assertEqual(data['roadPropRule'][0]['segments'], 3)

    def test_migrating_twice_changes_nothing(self):
        once = migration.migrate_city(city())
        self.assertEqual(migration.migrate_city(once), once)
        once = migration.migrate_presets(presets())[0]
        self.assertEqual(migration.migrate_presets(once)[0], once)

    def test_spline_types_match_the_core(self):
        types = {path.parent.name for path in (CORE / 'elements/customElements').glob('*/settings.json') if 'spline' in json.loads(path.read_text(encoding='utf-8'))}
        self.assertEqual(types, set(migration.SPLINE_TYPES))

    def test_templates_are_migrated(self):
        for path in (CORE / 'templates').glob('*/presets.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(migration.migrate_presets(data)[0], data, path)

    def test_folder(self):
        folder = tempfile.mkdtemp()
        try:
            root = pathlib.Path(folder)
            with gzip.open(root / 'city.json.gz', 'wt', encoding='utf-8') as f:
                json.dump(city(), f)
            (root / 'presets.json').write_text(json.dumps(presets()), encoding='utf-8')
            (root / 'preferences.json').write_text(json.dumps(dict(core='MidtownMadness2', coreVersion=4)), encoding='utf-8')
            migration.process_folder(MigrationHelper(folder + '/'))
            with gzip.open(root / 'city.json.gz', 'rt', encoding='utf-8') as f:
                self.assertEqual(json.load(f), migration.migrate_city(city()))
            self.assertEqual(json.loads((root / 'presets.json').read_text(encoding='utf-8')), migration.migrate_presets(presets())[0])
            self.assertEqual(json.loads((root / 'preferences.json').read_text(encoding='utf-8'))['coreVersion'], 5)
            for name in ('city.json.gz.v4.bak', 'presets.json.v4.bak', 'preferences.json.v4.bak'):
                self.assertTrue((root / name).exists(), name)
        finally:
            shutil.rmtree(folder)


if __name__ == '__main__':
    unittest.main()
