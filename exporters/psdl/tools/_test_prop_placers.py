"""Bounded synthetic migration and PATHSET checks; optionally audit a builder export JSON preview."""
import contextlib
import copy
import gzip
import importlib.util
import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
import numpy as np

CORE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE / 'exporters/psdl'))
sys.path.insert(0, str(CORE.parents[1] / 'python'))
from prop_placers import export_prop_placer
from bin_export import BINExporter
from scene_input import StandaloneSceneInput
from common.pathset_writer import PATHSETWriter
from MigrationHelper import MigrationHelper

spec = importlib.util.spec_from_file_location('prop_placer_migration', CORE / 'migrations/5.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def read_paths(path):
    with open(path, 'rb') as stream:
        def unpack(fmt): return struct.unpack(fmt, stream.read(struct.calcsize(fmt)))
        assert stream.read(4) == b'PTH1'
        count, _ = unpack('<II')
        paths = []
        for _ in range(count):
            name = stream.read(32).split(b'\0')[0].decode('ascii')
            size, _ = unpack('<II')
            points = []
            for _ in range(size):
                unpack('<I')
                points.append(unpack('<fff'))
            typ, spacing, _ = unpack('<BBH')
            paths.append((name, typ, spacing, points))
        assert stream.read() == b''
        return paths


def write_paths(parts, directory):
    processor = SimpleNamespace(get_objects=lambda: parts)
    target = str(Path(directory) / 'props.psdl')
    with contextlib.redirect_stdout(io.StringIO()):
        binary = str(Path(directory) / 'parts.bin')
        BINExporter(processor, False).export_bin_file(binary)
        PATHSETWriter(StandaloneSceneInput(binary), target).write()
    return read_paths(Path(directory) / 'props/props.pathset')


def line(spacing=5, points=None):
    return dict(id=1, type='propLine', data=dict(name='Native line', fields=dict(state=dict(
        propRule=dict(main=dict(type='line', element=dict(type='line', mesh='geometry/tree.pkg', elemDistance=spacing)))))),
                spline=dict(sections=[dict(center=p) for p in (points or [[0, 2, 0], [0, 4, 30]])]))


def native_positions(points, raw_spacing):
    result = []
    spacing = raw_spacing / 4 if raw_spacing else 5
    for a, b in zip(points, points[1:]):
        a, b = np.asarray(a), np.asarray(b)
        length = np.linalg.norm(b - a)
        if length < 1e-6:
            continue
        for i in range(max(1, int(length / spacing))):
            result.append(a + (b - a) * (i * spacing / length))
    return result


class PropPlacers(unittest.TestCase):
    def test_native_lines_stay_separate_in_actual_binary_writer(self):
        parts = []
        for spacing in (0.25, 5, 10, 63.75):
            export_prop_placer(SimpleNamespace(data={}), line(spacing), parts)
        with tempfile.TemporaryDirectory() as directory:
            paths = write_paths(parts, directory)
        self.assertEqual([p[2] for p in paths], [1, 20, 40, 255])
        self.assertTrue(all(p[1] == 2 and p[0] == 'tree' for p in paths))
        self.assertEqual(paths[0][3], [(0, 2, 0), (0, 4, 30)])

    def test_native_spacing_is_not_silently_truncated(self):
        for value in (-1, 0, 64, 0.3, float('inf'), float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                export_prop_placer(SimpleNamespace(data={}), line(value), [])

    def test_native_line_projects_sampled_heights_and_mirrors_x(self):
        parts = []
        export_prop_placer(SimpleNamespace(data={}), line(points=[[3, 2, 0], [3, 8, 30], [7, 11, 50]]), parts)
        with tempfile.TemporaryDirectory() as directory:
            paths = write_paths(parts, directory)
        self.assertEqual(paths[0][3], [(-3, 2, 0), (-3, 8, 30), (-7, 11, 50)])

    def test_individuals_are_exported_even_with_psdl_container(self):
        prop = dict(meshId=0, position=[3, 7, 11], rotation=[0, 0, 0, 1], scale=[1, 1, 1])
        element = dict(id=2, type='propStrip', data=dict(name='Strip', fields=dict(state=dict(propRule=dict(main=dict(type='psdl')))),
                                                       propLines=[dict(name='main', props=[prop])]))
        parts = []
        export_prop_placer(SimpleNamespace(data=dict(meshDict=[dict(name='geometry/tree.pkg')])), element, parts)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].translation, prop['position'])
        self.assertEqual(parts[0].properties['flags'], '1')
        with tempfile.TemporaryDirectory() as directory:
            paths = write_paths(parts, directory)
        self.assertEqual(paths[0][1], 1)
        self.assertEqual(paths[0][3][0], (-3, 7, 11))

    def test_invalid_polygon_is_reported(self):
        with self.assertRaises(ValueError):
            export_prop_placer(None, dict(validationError='PP_INVALID_POLYGON'), [])

    def test_migration_preserves_shared_points_road_rules_and_ids(self):
        old = dict(id=123, state=dict(type='__propPath'), points=dict(ribbons=[1, 2]))
        road = dict(id=4, state=dict(propRule=dict(left=dict(type='psdl'))))
        survivor = dict(id=9, state=dict(type='roadWithSidewalks', propRule=dict(right=dict(type='psdl'))), points=dict(left=1))
        data = dict(propPaths=[old], customElements=[old, survivor], lowLevelElements=[old, survivor], roads=[road],
                    terrainPoints=[dict(id=1, position=[0, 1, 2]), dict(id=2, position=[3, 4, 5])])
        original = copy.deepcopy(data)
        output = migration.migrate_city(data)
        self.assertEqual(data, original)
        self.assertNotIn('propPaths', output)
        self.assertEqual(output['customElements'], [survivor])
        self.assertEqual(output['lowLevelElements'], [survivor])
        self.assertEqual(output['roads'][0]['state'], road['state'])
        self.assertEqual(output['terrainPoints'], data['terrainPoints'])
        self.assertEqual(migration.migrate_city(output), output)

    def test_migration_backs_up_before_writing_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = dict(coreVersion=4, core='MidtownMadness2')
            (root / 'preferences.json').write_text(json.dumps(preferences))
            presets = dict(presets={'customElement/__propPath': [], 'roadPropRule': [dict(name='Keep')]})
            (root / 'presets.json').write_text(json.dumps(presets))
            with gzip.open(root / 'city.json.gz', 'wt') as stream:
                json.dump(dict(propPaths=[dict(id=1)]), stream)
            original = (root / 'city.json.gz').read_bytes()
            migration.process_folder(MigrationHelper(directory + '/'))
            self.assertEqual((root / 'city.json.gz.v4.bak').read_bytes(), original)
            self.assertEqual(json.loads((root / 'preferences.json').read_text())['coreVersion'], 5)
            self.assertEqual(json.loads((root / 'presets.json').read_text()), dict(presets={'roadPropRule': [dict(name='Keep')]}))
            updated = (root / 'city.json.gz').read_bytes()
            migration.process_folder(MigrationHelper(directory + '/'))
            self.assertEqual((root / 'city.json.gz').read_bytes(), updated)


def audit_preview(path):
    from DecodeExportedJson import DecodeExportedJson
    data = DecodeExportedJson().decode_json(str(path))
    elements = [e for e in data['customElements'] if e['type'] in ('propLine', 'propStrip', 'propPolygon')]
    assert {e['type'] for e in elements} == {'propLine', 'propStrip', 'propPolygon'}
    parts = []
    for element in elements:
        export_prop_placer(SimpleNamespace(data=data), element, parts)
    with tempfile.TemporaryDirectory() as directory:
        paths = write_paths(parts, directory)
    native = [p for p in paths if p[1] == 2]
    lines = [e for e in elements if e['type'] == 'propLine']
    assert len(native) == len(lines)
    for element, (_, _, spacing, points) in zip(lines, native):
        preview = [p['position'] for line in element['data']['propLines'] for p in line['props']]
        positions = native_positions([[-p[0], p[1], p[2]] for p in points], spacing)
        np.testing.assert_allclose(positions, preview, atol=0.001)
    individually_evaluated = sum(len(line['props']) for e in elements if e['type'] != 'propLine' for line in e['data']['propLines'])
    individual_count = sum(len(points) // (2 if typ == 1 else 1) for _, typ, _, points in paths if typ != 2)
    assert individually_evaluated == individual_count
    print('Preview parity:', len(native), 'native lines and', individual_count, 'individual props')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--preview':
        audit_preview(sys.argv[2])
    else:
        unittest.main()
