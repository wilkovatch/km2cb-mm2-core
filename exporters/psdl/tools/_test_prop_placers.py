"""Bounded synthetic migration and PATHSET checks; optionally audit a builder export JSON preview."""
import contextlib
import copy
import csv
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
from unittest.mock import patch
import numpy as np

CORE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE / 'exporters/psdl'))
sys.path.insert(0, str(CORE.parents[1] / 'python'))
from prop_placers import export_prop_placer
from prop_rules_export import PropRulesExporter
from utils import placed_props
from scene import Scene
from writers.pathset_writer import PATHSETWriter, MAX_PATHS
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
    target = str(Path(directory) / 'props.psdl')
    with contextlib.redirect_stdout(io.StringIO()):
        PATHSETWriter(Scene(parts), target).write()
    return read_paths(Path(directory) / 'props/props.pathset')


def line(spacing=5, points=None):
    return dict(id=1, type='propLine', data=dict(name='Native line', fields=dict(state=dict(projectToGround=False,
        propRule=dict(main=dict(type='pathsetStrip', mesh='geometry/tree.pkg', elemDistance=spacing))))),
                spline=dict(sections=[dict(center=p) for p in (points or [[0, 2, 0], [0, 4, 30]])]))


def line_on_ground(spacing, slots, end):
    # as the builder gives it with Project to ground: a placement for each prop, then the end of the path without a model
    props = [dict(meshId=0, position=p, rotation=[0, 0, 0, 1], scale=[1, 1, 1]) for p in slots] + [dict(meshId=-1, position=end, rotation=[0, 0, 0, 1], scale=[1, 1, 1])]
    return dict(id=1, type='propLine', data=dict(name='Line on the ground', propLines=[dict(name='main', props=props)], fields=dict(state=dict(projectToGround=True,
        propRule=dict(main=dict(type='pathsetStrip', mesh='geometry/tree.pkg', elemDistance=spacing))))),
                spline=dict(sections=[dict(center=slots[0]), dict(center=end)]))


def native_positions(points, raw_spacing):
    result = []
    spacing = raw_spacing / 4 if raw_spacing else 5
    for a, b in zip(points, points[1:]):
        a, b = np.asarray(a), np.asarray(b)
        length = np.linalg.norm(b - a)
        count = int(length / spacing)
        for i in range(count):
            result.append(a + (b - a) * (i / count))
    return result


class PropPlacers(unittest.TestCase):
    def test_native_prop_rules_expand_zero_maximum_without_changing_other_counts(self):
        definitions = [dict(name='tree' + str(count), start=0, elemDistance=5, maxNumber=count,
                            minHorizPos=0.5, maxHorizPos=0.5, meshes=['geometry/tree.pkg'])
                       for count in (0, 3, 9999)]
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            PropRulesExporter(None, False).write_prop_rules(definitions, [], str(Path(directory) / 'props.psdl'))
            with open(Path(directory) / 'props/propdefs.csv', newline='') as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual([int(row['maxUse']) for row in rows], [9999, 3, 9999])
        self.assertEqual([definition['maxNumber'] for definition in definitions], [0, 3, 9999])

    def test_native_positions_follow_the_game(self):
        # the step is stretched to fill the span, and a span shorter than the spacing gets no props
        np.testing.assert_allclose(native_positions([[0, 0, 0], [0, 0, 12]], 20), [[0, 0, 0], [0, 0, 6]])
        self.assertEqual(native_positions([[0, 0, 0], [0, 0, 3]], 20), [])
        self.assertEqual(len(native_positions([[0, 0, 0], [0, 0, 3], [0, 0, 8]], 20)), 1)

    def test_native_lines_stay_separate_in_actual_writer(self):
        parts = []
        for spacing in (0.25, 5, 10, 63.75):
            export_prop_placer(SimpleNamespace(data={}), line(spacing), parts)
        with tempfile.TemporaryDirectory() as directory:
            paths = write_paths(parts, directory)
        self.assertEqual([p[2] for p in paths], [1, 20, 40, 255])
        self.assertTrue(all(p[1] == 2 and p[0] == 'tree' for p in paths))
        self.assertEqual(paths[0][3], [(0, 2, 0), (0, 4, 30)])

    def test_a_pathset_stays_within_the_paths_the_game_can_load(self):
        parts = []
        for _ in range(MAX_PATHS + 1):
            export_prop_placer(SimpleNamespace(data={}), line(), parts)
        with tempfile.TemporaryDirectory() as directory, patch('writers.pathset_writer.report.error') as error:
            paths = write_paths(parts, directory)
        self.assertEqual(len(paths), MAX_PATHS)
        self.assertIn('the last 1 are left out', error.call_args.args[0])

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

    def assert_game_places_each_slot(self, element, slots, spacing):
        parts = []
        export_prop_placer(SimpleNamespace(data={}), element, parts)
        with tempfile.TemporaryDirectory() as directory:
            paths = write_paths(parts, directory)
        self.assertEqual(paths[0][1:3], (2, int(spacing * 4)))
        # the points are the single precision values of the file, as the game reads them
        positions = native_positions([[-p[0], p[1], p[2]] for p in paths[0][3]], paths[0][2])
        self.assertEqual(len(positions), len(slots))
        np.testing.assert_allclose(positions, slots, atol=0.25)

    def test_a_line_on_the_ground_has_each_prop_at_its_height(self):
        slots = [[3, 0.3 * i * i, 6 * i] for i in range(8)]
        self.assert_game_places_each_slot(line_on_ground(5, slots, [3, 20, 48]), slots, 5)

    def test_a_line_on_the_ground_keeps_the_spacing_when_it_is_small(self):
        # with a spacing rounded down to fit the rounding of the points, each span would get two props
        for spacing in (0.25, 0.5, 1):
            slots = [[0, 0, spacing * i] for i in range(40)]
            self.assert_game_places_each_slot(line_on_ground(spacing, slots, [0, 0, spacing * 40]), slots, spacing)

    def test_rounding_to_single_precision_doesnt_lose_props(self):
        # far from the origin the spans come out a little shorter than the spacing, in single precision
        for origin in (700.1, 3000.3, -7001.7):
            exact = [[origin + 5 * i, origin, origin] for i in range(200)]
            self.assert_game_places_each_slot(line_on_ground(5, exact, [origin + 1000, origin, origin]), exact, 5)
            diagonal = [[origin + 3 * i, origin, origin + 4 * i] for i in range(200)]
            self.assert_game_places_each_slot(line_on_ground(5, diagonal, [origin + 600, origin, origin + 800]), diagonal, 5)

    def test_a_span_too_long_for_one_prop_is_reported(self):
        parts = []
        with patch('prop_placers.report.warning') as warning:
            export_prop_placer(SimpleNamespace(data={}), line_on_ground(5, [[0, 0, 0], [0, 0, 6]], [0, 20, 12]), parts)
        warning.assert_called_once()
        with patch('prop_placers.report.warning') as warning:
            export_prop_placer(SimpleNamespace(data={}), line_on_ground(5, [[0, 0, 0], [0, 0, 6]], [0, 0, 12]), parts)
        warning.assert_not_called()

    def test_a_line_on_the_ground_without_props_has_no_path(self):
        element = line_on_ground(5, [[0, 0, 0]], [0, 0, 3])
        element['data']['propLines'][0]['props'] = []
        parts = []
        export_prop_placer(SimpleNamespace(data={}), element, parts)
        self.assertEqual(parts, [])

    def test_individuals_are_exported_even_with_psdl_container(self):
        prop = dict(meshId=0, position=[3, 7, 11], rotation=[0, 0, 0, 1], scale=[1, 1, 1])
        element = dict(id=2, type='propLine', data=dict(name='Strip', fields=dict(state=dict(propRule=dict(main=dict(type='psdl')))),
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

    def test_old_strips_become_flat(self):
        old = dict(type='pathsetStrip', elements=[dict(type='pathsetStrip', mesh='geometry/a.pkg', rawSpacing=20)])
        unset = dict(type='pathsetStrip', elements=[dict(type='pathsetStrip', mesh='geometry/a.pkg', rawSpacing=0)])
        output = migration.migrate_city(dict(roads=[dict(id=4, state=dict(propRule=dict(right=old, left=unset)))]))
        rule = output['roads'][0]['state']['propRule']
        self.assertEqual(rule['right'], dict(type='pathsetStrip', mesh='geometry/a.pkg', elemDistance=5))
        self.assertEqual(rule['left']['elemDistance'], 5)
        presets = dict(presets=dict(propContainer=[dict(name='Default', type='pathsetStrip', elements=[dict(type='pathsetStrip', mesh='', rawSpacing=8)])]))
        output, _ = migration.migrate_presets(presets)
        self.assertEqual(output['presets']['props/pathsetStrip'], [dict(name='Default', type='pathsetStrip', mesh='', elemDistance=2)])


class PropsTypesMigration(unittest.TestCase):
    TREE = 'geometry/tree.pkg'

    def migrate(self, city, presets=None):
        new_presets, links = migration.migrate_presets(dict(presets=presets or {}))
        return migration.migrate_city(city, links), new_presets['presets']

    def test_a_container_with_one_element_becomes_flat(self):
        rule = dict(left=dict(type='line', name='cars', element=dict(type='line', mesh=self.TREE, elemDistance=2, name='other')),
                    right=dict(type='parkedCars', element=dict(type='parkedCars', xPos=0.5)),
                    middle=dict(type='pathsetStrip', element=dict(type='pathsetStrip', mesh=self.TREE, elemDistance=5)),
                    # enabled but never edited
                    middleLeft=dict(type='line'))
        output, _ = self.migrate(dict(roads=[dict(id=1, state=dict(type='psdl', propRule=rule))]))
        result = output['roads'][0]['state']['propRule']
        self.assertEqual(result['left'], dict(type='line', mesh=self.TREE, elemDistance=2, name='cars'))
        self.assertEqual(result['right'], dict(type='parkedCars', xPos=0.5))
        self.assertEqual(result['middle'], dict(type='pathsetStrip', mesh=self.TREE, elemDistance=5))
        self.assertEqual(result['middleLeft'], dict(type='line'))
        self.assertEqual(output['roads'][0]['state']['type'], 'psdl')

    def test_only_the_elements_of_a_list_are_renamed(self):
        psdl = dict(type='psdl', meshes=[self.TREE], name='', elemDistance=9)
        custom = dict(type='custom', meshes=[self.TREE], random=True)
        line = dict(type='line', mesh=self.TREE)
        rule = dict(left=dict(type='psdl', elements=[psdl]), right=dict(type='custom', elements=[custom]), middle=dict(type='mixed', elements=[line, custom, psdl]))
        output, _ = self.migrate(dict(roads=[dict(id=1, state=dict(type='psdl', propRule=rule))]))
        state = output['roads'][0]['state']
        self.assertEqual(state['type'], 'psdl')
        self.assertEqual(state['propRule']['left']['type'], 'psdl')
        self.assertEqual(state['propRule']['left']['elements'], [dict(psdl, type='psdlProp')])
        self.assertEqual(state['propRule']['right']['elements'], [dict(custom, type='customProp')])
        self.assertEqual([e['type'] for e in state['propRule']['middle']['elements']], ['line', 'customProp', 'psdlProp'])

    def test_every_prop_rule_is_found_and_a_repeated_run_changes_nothing(self):
        rule = dict(left=dict(type='psdl', elements=[dict(type='psdl', meshes=[self.TREE], name='a')]), right=dict(type='line', element=dict(type='line', mesh=self.TREE)))
        city = dict(roads=[dict(state=dict(type='psdl', propRule=copy.deepcopy(rule)))],
                    intersections=[dict(roadsThrough=[dict(state=dict(type='psdl', propRule=copy.deepcopy(rule)))])],
                    customElements=[dict(id=1, state=dict(type='roadWithSidewalks', propRule=copy.deepcopy(rule)))])
        presets = {'road': [dict(name='r', type='psdl', propRule=copy.deepcopy(rule))], 'roadPropRule': [dict(name='p', type='psdl', **copy.deepcopy(rule))]}
        output, new_presets = self.migrate(city, presets)
        for state in (output['roads'][0]['state'], output['intersections'][0]['roadsThrough'][0]['state'], output['customElements'][0]['state'], new_presets['road'][0]):
            self.assertEqual(state['propRule']['left']['elements'][0]['type'], 'psdlProp')
            self.assertEqual(state['propRule']['right'], dict(type='line', mesh=self.TREE))
        self.assertEqual(new_presets['roadPropRule'][0]['type'], 'psdl')
        self.assertEqual(new_presets['roadPropRule'][0]['right'], dict(type='line', mesh=self.TREE))
        self.assertEqual(migration.migrate_city(output, migration.Links()), output)

    def test_the_presets_move_to_a_category_for_each_type(self):
        presets = dict(
            propElem=[dict(name='Default', type='psdl', meshes=[self.TREE]), dict(name='shared', type='line', mesh=self.TREE, elemDistance=1), dict(name='e', type='custom', meshes=[self.TREE])],
            propContainer=[dict(name='Default', type='psdl', elements=[]), dict(name='shared', type='line', element=dict(type='line', mesh=self.TREE, elemDistance=2)),
                           dict(name='g', type='psdl', elements=[dict(type='psdl', meshes=[self.TREE], name='Default')])])
        city = dict(roads=[dict(state=dict(propRule=dict(left=dict(name='shared', type='line', element=dict(type='line', mesh=self.TREE))))),
                           dict(state=dict(propRule=dict(left=dict(type='line', element=dict(name='shared', type='line', mesh=self.TREE)))))])
        output, new_presets = self.migrate(city, presets)
        self.assertNotIn('propElem', new_presets)
        self.assertNotIn('propContainer', new_presets)
        self.assertEqual([p['name'] for p in new_presets['props/psdlProp']], ['Default'])
        self.assertEqual([p['name'] for p in new_presets['props/psdl']], ['Default', 'g'])
        self.assertEqual(new_presets['props/psdl'][1]['elements'][0]['type'], 'psdlProp')
        self.assertEqual([p['name'] for p in new_presets['props/customProp']], ['Default', 'e'])
        # the container and the element had a preset with the same name, now in the same category: both stay
        self.assertEqual([p['name'] for p in new_presets['props/line']], ['Default', 'shared', 'shared 2'])
        self.assertEqual(new_presets['props/line'][1], dict(name='shared', type='line', mesh=self.TREE, elemDistance=2))
        self.assertEqual(new_presets['props/line'][2], dict(name='shared 2', type='line', mesh=self.TREE, elemDistance=1))
        self.assertEqual(output['roads'][0]['state']['propRule']['left']['name'], 'shared')
        self.assertEqual(output['roads'][1]['state']['propRule']['left']['name'], 'shared 2')

    def test_it_backs_up_and_advances_the_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'preferences.json').write_text(json.dumps(dict(coreVersion=4, core='MidtownMadness2')))
            (root / 'presets.json').write_text(json.dumps(dict(presets=dict(propElem=[dict(name='Default', type='psdl')]))))
            with gzip.open(root / 'city.json.gz', 'wt') as stream:
                json.dump(dict(customElements=[dict(id=1, state=dict(type='room'))]), stream)
            original = (root / 'city.json.gz').read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                migration.process_folder(MigrationHelper(directory + '/'))
            self.assertEqual((root / 'city.json.gz.v4.bak').read_bytes(), original)
            self.assertTrue((root / 'presets.json.v4.bak').exists())
            self.assertEqual(json.loads((root / 'preferences.json').read_text())['coreVersion'], 5)
            self.assertIn('props/psdlProp', json.loads((root / 'presets.json').read_text())['presets'])
            updated = (root / 'city.json.gz').read_bytes()
            migration.process_folder(MigrationHelper(directory + '/'))
            self.assertEqual((root / 'city.json.gz').read_bytes(), updated)


def audit_preview(path):
    from DecodeExportedJson import DecodeExportedJson
    data = DecodeExportedJson().decode_json(str(path))
    elements = [e for e in data['customElements'] if e['type'] in ('propLine', 'propPolygon')]
    assert {e['type'] for e in elements} == {'propLine', 'propPolygon'}
    parts = []
    for element in elements:
        export_prop_placer(SimpleNamespace(data=data), element, parts)
    with tempfile.TemporaryDirectory() as directory:
        paths = write_paths(parts, directory)
    native = [p for p in paths if p[1] == 2]
    def native_line(element):
        return element['type'] == 'propLine' and element['data']['fields']['state']['propRule']['main']['type'] == 'pathsetStrip'
    lines = [e for e in elements if native_line(e)]
    assert len(native) == len(lines)
    for element, (_, _, spacing, points) in zip(lines, native):
        preview = [p['position'] for line in element['data']['propLines'] for p in placed_props(line)]
        positions = native_positions([[-p[0], p[1], p[2]] for p in points], spacing)
        np.testing.assert_allclose(positions, preview, atol=0.001)
    individually_evaluated = sum(len(line['props']) for e in elements if not native_line(e) for line in e['data']['propLines'])
    individual_count = sum(len(points) // (2 if typ == 1 else 1) for _, typ, _, points in paths if typ != 2)
    assert individually_evaluated == individual_count
    print('Preview parity:', len(native), 'native lines and', individual_count, 'individual props')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--preview':
        audit_preview(sys.argv[2])
    else:
        unittest.main()
