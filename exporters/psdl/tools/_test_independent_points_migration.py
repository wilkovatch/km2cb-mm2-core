"""Synthetic checks for independent point values and the core-owned version-6 migration."""
import gzip
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

CORE = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE.parents[1] / 'python'))
from MigrationHelper import MigrationHelper

spec = importlib.util.spec_from_file_location('independent_points_migration', CORE / 'migrations/6.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def city():
    return dict(terrainPoints=[dict(id=7, position=dict(x=1, y=12, z=3), rotation=dict(x=0, y=45, z=0),
                                   scale=dict(x=2, y=1, z=6), linkType=2, elementType=1, elementId=10, anchorIndex=3)],
                terrainPatches=[dict(perimeterPointsIds=[7])],
                customElements=[dict(id=i, state=dict(type=kind), points=dict(center=7))
                                for i, kind in enumerate(('parkedCar', 'decalSingle', 'mapLabel'))]
                + [dict(id=4, state=dict(type='decal'), points=dict(spline=[7]))])


class IndependentPointsMigration(unittest.TestCase):
    def test_values_and_other_references(self):
        source = city()
        result = migration.migrate_city(source)
        self.assertEqual(source, city())
        for element in result['customElements'][:3]:
            value = element['points']['center']
            self.assertEqual(value['position'], dict(x=1, y=12, z=3))
            self.assertNotIn('linkType', value)
        self.assertEqual(result['customElements'][0]['points']['center']['rotation'], dict(x=0, y=45, z=0))
        self.assertEqual(result['customElements'][1]['points']['center']['scale'], dict(x=2, y=1, z=6))
        self.assertEqual(set(result['customElements'][2]['points']['center']), {'position'})
        for key in ('terrainPoints', 'terrainPatches'):
            self.assertEqual(result[key], source[key])
        self.assertEqual(result['customElements'][3], source['customElements'][3])

    def test_idempotent_and_independent(self):
        result = migration.migrate_city(city())
        self.assertEqual(migration.migrate_city(result), result)
        result['customElements'][0]['points']['center']['position']['x'] = 99
        self.assertEqual(result['customElements'][1]['points']['center']['position']['x'], 1)
        self.assertEqual(result['terrainPoints'][0]['position']['x'], 1)

    def test_missing_optional_transforms(self):
        source = city()
        source['terrainPoints'][0].pop('rotation')
        source['terrainPoints'][0]['scale'] = None
        self.assertEqual(migration.migrate_city(source)['customElements'][1]['points']['center'], {'position': dict(x=1, y=12, z=3)})

    def test_missing_reference(self):
        source = city()
        source['terrainPoints'] = []
        with self.assertRaisesRegex(ValueError, 'Missing terrain point 7'):
            migration.migrate_city(source)

    def test_bad_transform(self):
        for bad in (None, dict(x=1, y=float('nan'), z=3), dict(x=True, y=2, z=3), [1, 2, 3]):
            source = city()
            source['terrainPoints'][0]['position'] = bad
            with self.assertRaises(ValueError):
                migration.migrate_city(source)

    def test_empty_and_null_collections(self):
        for source in ({}, dict(terrainPoints=None, customElements=None)):
            self.assertEqual(migration.migrate_city(source), source)

    def prepare_folder(self, root, source=None):
        with gzip.open(root / 'city.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump(city() if source is None else source, stream)
        (root / 'preferences.json').write_text(json.dumps(dict(core='MidtownMadness2', coreVersion=5)), encoding='utf-8')
        return MigrationHelper(str(root) + '/')

    def test_folder_backups_and_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            helper = self.prepare_folder(root)
            originals = {p.name: p.read_bytes() for p in root.iterdir()}
            migration.process_folder(helper)
            with gzip.open(root / 'city.json.gz', 'rt', encoding='utf-8') as stream:
                self.assertEqual(json.load(stream), migration.migrate_city(city()))
            self.assertEqual(json.loads((root / 'preferences.json').read_text())['coreVersion'], 6)
            for name, original in originals.items():
                self.assertEqual((root / (name + '.v5.bak')).read_bytes(), original)
            saved = {p.name: p.read_bytes() for p in root.iterdir()}
            migration.process_folder(MigrationHelper(folder + '/'))
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, saved)

    def test_validation_failure_leaves_original_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            source = city(); source['terrainPoints'] = []
            helper = self.prepare_folder(root, source)
            originals = {p.name: p.read_bytes() for p in root.iterdir()}
            with self.assertRaises(ValueError):
                migration.process_folder(helper)
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, originals)

    def test_write_failure_does_not_publish_version(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            helper = self.prepare_folder(root)
            with patch.object(helper, 'save', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    migration.process_folder(helper)
            self.assertEqual(json.loads((root / 'preferences.json').read_text())['coreVersion'], 5)
            self.assertTrue((root / 'city.json.gz.v5.bak').exists())

    def test_versions_and_templates(self):
        settings = json.loads((CORE / 'settings.json').read_text())
        self.assertEqual((settings['coreVersion'], settings['programVersion'], settings['featureVersion']), (7, 5, 1))
        self.assertEqual(json.loads((CORE / 'templates/_common/preferences.json').read_text())['coreVersion'], 7)
        for kind in migration.POINT_TYPES:
            self.assertFalse(json.loads((CORE / ('elements/customElements/' + kind + '/settings.json')).read_text())['point']['anchorable'])

    def test_program_compatibility_and_migration_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            helper = self.prepare_folder(pathlib.Path(folder))
            self.assertEqual([pathlib.Path(p).name for p in helper.get_migrations_todo(5, 1)], ['6.py', '7.py'])
            for program, feature in ((4, 99), (5, 0)):
                with self.assertRaisesRegex(Exception, 'CORE_IS_FOR_NEWER_PROGRAM'):
                    helper.get_migrations_todo(program, feature)
            with self.assertRaisesRegex(Exception, 'CORE_IS_FOR_OLDER_PROGRAM'):
                helper.get_migrations_todo(6, 1)


if __name__ == '__main__':
    unittest.main()
