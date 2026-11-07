"""Synthetic checks for the version-8 migration: the files of the old converters (low LOD textures, bridge models) become flags."""
import gzip
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

CORE = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE.parents[1] / 'python')]

import MigrationHelper

spec = importlib.util.spec_from_file_location('generated_migration', CORE / 'migrations/8.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

LOD = 'texture/r2_lod_0a1b2c.tex'
MODEL = 'geometry/bridge_0a1b2c3d.pkg'


def bridge(**state):
    return {'state': dict({'type': 'bridge', 'paired': True}, **state), 'points': {}}


class Migration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = pathlib.Path(self.tmp.name)
        for path in (LOD, LOD.replace('.tex', '_fa.tex'), 'texture/old_lod_ffffff.tex', 'texture/mine.tex', MODEL,
                     'bound/bridge_0a1b2c3d_BOUND.bnd', 'tune/banger/bridge_0a1b2c3d.dgBangerData',
                     'geometry/bridge_99999999.pkg', 'bound/bridge_99999999_BOUND.bnd', 'geometry/bridge_11111111.pkg'):
            (self.folder / path).parent.mkdir(parents=True, exist_ok=True)
            (self.folder / path).write_bytes(b'x')

    def write(self, city, presets=None):
        with gzip.open(self.folder / 'city.json.gz', 'wt', encoding='utf-8') as f:
            json.dump(city, f)
        (self.folder / 'preferences.json').write_text(json.dumps({'core': 'MidtownMadness2', 'coreVersion': 7}))
        if presets is not None:
            (self.folder / 'presets.json').write_text(json.dumps(presets))

    def run_migration(self):
        migration.process_folder(MigrationHelper.MigrationHelper(str(self.folder) + '/'))
        with gzip.open(self.folder / 'city.json.gz', 'rt', encoding='utf-8') as f:
            city = json.load(f)
        presets = json.loads((self.folder / 'presets.json').read_text()) if (self.folder / 'presets.json').exists() else None
        return city, presets, json.loads((self.folder / 'preferences.json').read_text())

    def test_the_flags(self):
        self.write({'roads': [{'state': {'textureLOD': LOD}}, {'state': {'textureLOD': 'texture/mine.tex'}}],
                    'customElements': [bridge(mesh=MODEL, generatedMesh=MODEL, generatedLength=40.0),
                                       bridge(mesh='geometry/bridge_11111111.pkg', generatedMesh=MODEL, generatedLength=40.0)]},
                   {'presets': {'road': [{'textureLOD': 'texture/old_lod_ffffff.tex'}, {'textureLOD': 'texture/gone_lod_eeeeee.tex'}],
                                'customElement/bridge': [{'mesh': MODEL, 'generatedMesh': MODEL}]}})
        city, presets, preferences = self.run_migration()
        roads = [r['state'] for r in city['roads']]
        self.assertEqual(roads[0], {'textureLOD': '', 'generateLodTexture': True})
        self.assertEqual(roads[1], {'textureLOD': 'texture/mine.tex'}, 'a texture chosen by hand')
        bridges = [b['state'] for b in city['customElements']]
        self.assertEqual(bridges[0], {'type': 'bridge', 'paired': True, 'mesh': '', 'generateMesh': True})
        self.assertEqual(bridges[1], {'type': 'bridge', 'paired': True, 'mesh': 'geometry/bridge_11111111.pkg'}, 'another model chosen by hand')
        self.assertEqual(presets['presets']['road'][0], {'textureLOD': '', 'generateLodTexture': True})
        self.assertEqual(presets['presets']['road'][1], {'textureLOD': 'texture/gone_lod_eeeeee.tex'}, 'its file is missing: kept as it was')
        self.assertEqual(presets['presets']['customElement/bridge'][0], {'mesh': '', 'generateMesh': True})
        self.assertEqual(preferences['coreVersion'], 8)
        self.assertTrue((self.folder / 'city.json.gz.v7.bak').exists())

    def test_the_files_no_longer_used(self):
        self.write({'roads': [{'state': {'textureLOD': LOD}}],
                    'customElements': [bridge(mesh=MODEL, generatedMesh=MODEL), bridge(mesh='geometry/bridge_11111111.pkg')]})
        self.run_migration()
        backup = self.folder / migration.BACKUP
        moved = sorted(str(p.relative_to(backup)).replace('\\', '/') for p in backup.rglob('*') if p.is_file())
        self.assertEqual(moved, ['bound/bridge_0a1b2c3d_BOUND.bnd', 'bound/bridge_99999999_BOUND.bnd', 'geometry/bridge_0a1b2c3d.pkg',
                                 'geometry/bridge_99999999.pkg', 'texture/old_lod_ffffff.tex', 'texture/r2_lod_0a1b2c.tex',
                                 'texture/r2_lod_0a1b2c_fa.tex', 'tune/banger/bridge_0a1b2c3d.dgBangerData'])
        self.assertTrue((self.folder / 'geometry/bridge_11111111.pkg').exists(), 'still used')
        self.assertTrue((self.folder / 'texture/mine.tex').exists(), 'not a generated name')

    def test_once(self):
        self.write({'roads': [{'state': {'textureLOD': LOD}}]})
        self.run_migration()
        (self.folder / LOD).parent.mkdir(exist_ok=True)
        (self.folder / LOD).write_bytes(b'x')
        self.run_migration()
        self.assertTrue((self.folder / LOD).exists(), 'the version is 8: nothing to do')


if __name__ == '__main__':
    unittest.main()
