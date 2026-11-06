"""Bounded synthetic checks of the parked cars export (the parkedCars props type), no stock data."""
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python')]
from _test_prop_placers import native_positions, read_paths
from json_processor import JsonProcessor
from parked_car_export import export_parked_cars, get_path, get_rows, write_rows, MANIFEST
from prop_placers import export_prop_placer
from writers.pathset_writer import MAX_PATHS


def rotation_towards(forward):
    # the yaw quaternion of a placement whose model Z axis is along the horizontal direction
    half = math.atan2(forward[0], forward[2]) / 2
    return (0.0, math.sin(half), 0.0, math.cos(half))


def line(slots, forward=(0, 0, 1), name='rightParking'):
    return dict(name=name, props=[dict(meshId=-1, position=slot, rotation=rotation_towards(forward), scale=(1, 1, 1)) for slot in slots])


def container():
    return dict(type='parkedCars')


def road(name, slots, forward=(0, 0, 1), **instance):
    return dict(data=dict(name=name, fields=dict(state=dict(propRule=dict(rightParking=container())), instanceState=instance),
                          propLines=[line(slots, forward)]))


def strip(name, slots, owner='', forward=(0, 0, 1)):
    state = dict(type='propLine', propRule=dict(main=container()))
    if owner:
        state['_propertyContainerId'] = owner
    return dict(id=1, type='propLine', data=dict(name=name, fields=dict(state=state), propLines=[line(slots, forward, 'main')]))


def row(slots, forward=(0, 0, 1)):
    return dict(name='row', kind='road', owner='', slots=slots, forwards=[forward] * len(slots))


def single(name='Single parked car', position=(3.0, 7.0, 11.0), forward=(0, 0, 1), owner=''):
    element = strip(name, [position], owner, forward)
    element['type'] = element['data']['fields']['state']['type'] = 'parkedCar'
    element['data']['fields']['state']['propRule']['main']['type'] = 'parkedCar'
    element['data']['propLines'][0]['props'][0]['meshId'] = 0  # the fixed preview must never become a normal prop
    return element


def straight(count=4, step=6.0, x=3.0):
    return [(x, 1.0, i * step) for i in range(count)]


class ParkedCars(unittest.TestCase):
    def test_single_car_uses_one_horizontal_slot_at_its_position_and_heading(self):
        for yaw in (0, 37, 90, 180, 270):
            forward = (math.sin(math.radians(yaw)), 0, math.cos(math.radians(yaw)))
            with self.subTest(yaw=yaw), tempfile.TemporaryDirectory() as directory:
                data = dict(customElements=[single(forward=forward)])
                export_parked_cars(data, directory + '/', 'x')
                paths = read_paths(Path(directory) / 'x_parkedcar.pathset')
                self.assertEqual(len(paths), 1)
                _, typ, raw, points = paths[0]
                self.assertEqual(typ, 2)
                self.assertEqual(len(points), 2)
                self.assertEqual(points[0], (-3, 7, 11))
                self.assertAlmostEqual(points[1][1], 7)
                self.assertAlmostEqual(math.dist(*points), 6, places=5)
                self.assertAlmostEqual(points[1][0] - points[0][0], -6 * forward[0], places=5)
                self.assertAlmostEqual(points[1][2] - points[0][2], 6 * forward[2], places=5)
                self.assertEqual(len(native_positions(points, raw)), 1)

    def test_single_cars_and_rows_share_city_and_race_files(self):
        data = dict(roads=[road('City row', straight(2))], customElements=[single(), single('Race car', (9, 0, 0), owner='A')],
                    cityProperties=dict(circuitRaces=[dict(_elementContainerId='A')]))
        with tempfile.TemporaryDirectory() as directory:
            export_parked_cars(data, directory + '/', 'x')
            self.assertEqual(len(read_paths(Path(directory) / 'x_parkedcar.pathset')), 2)
            paths = read_paths(Path(directory) / 'x_parkedcar_circuit0.pathset')
            self.assertEqual(len(paths), 3)
            self.assertEqual(paths[0][3][0], (-9, 0, 0))

    def test_single_cars_count_towards_the_shared_path_limit(self):
        data = dict(customElements=[single(str(i)) for i in range(MAX_PATHS + 1)])
        with tempfile.TemporaryDirectory() as directory, patch('parked_car_export.report.error') as error:
            export_parked_cars(data, directory + '/', 'x')
            self.assertEqual(len(read_paths(Path(directory) / 'x_parkedcar.pathset')), MAX_PATHS)
            self.assertIn('the last 1', error.call_args.args[0])

    def test_single_car_previews_are_not_exported_as_ordinary_props(self):
        element = single()
        parts = []
        export_prop_placer(SimpleNamespace(data=dict(meshDict=[dict(name='geometry/giz_pcar01_l.pkg')])), element, parts)
        self.assertEqual(parts, [])
        JsonProcessor.get_road_props(SimpleNamespace(data=dict(meshDict=[])), parts, element,
                                     element['data']['fields']['state']['propRule'], 'customElement')
        self.assertEqual(parts, [])

    def test_path_mirrors_x_and_gives_the_last_slot_a_span(self):
        points, raw = get_path(row(straight()))
        self.assertEqual(points, [(-3.0, 1.0, i * 6.0) for i in range(5)])
        self.assertEqual(raw, 23)

    def test_the_slot_direction_sets_the_order_of_the_points(self):
        points, _ = get_path(row(straight(), (0, 0, -1)))
        self.assertEqual(points, [(-3.0, 1.0, z) for z in (18.0, 12.0, 6.0, 0.0, -6.0)])

    def test_a_single_slot_runs_along_its_direction(self):
        points, raw = get_path(row([(3.0, 1.0, 0.0)], (1, 0, 0)))
        self.assertEqual(points, [(-3.0, 1.0, 0.0), (-9.0, 1.0, 0.0)])
        self.assertGreaterEqual(raw, 20)

    def assert_one_car_per_slot(self, slots):
        with patch('parked_car_export.report.warning') as warning:
            points, raw = get_path(row(slots))
        warning.assert_not_called()
        self.assertGreaterEqual(raw, 20)
        cars = native_positions(points, raw)
        self.assertEqual(len(cars), len(slots))
        for car, slot in zip(cars, slots):
            self.assertAlmostEqual(math.dist(car, (-slot[0], slot[1], slot[2])), 0, places=4)

    def test_the_game_places_one_car_at_each_slot_of_a_straight_row(self):
        self.assert_one_car_per_slot(straight())
        self.assert_one_car_per_slot(straight(step=5.25))
        self.assert_one_car_per_slot(straight(3, 100.0))

    def test_the_game_places_one_car_at_each_slot_of_a_curved_row(self):
        slots = [(10 * math.sin(i / 3), 0.0, 6.0 * i) for i in range(12)]
        self.assert_one_car_per_slot(slots)

    def test_the_game_places_each_car_at_the_height_of_its_slot(self):
        # the game doesn't look for the ground, so the heights the editor projected have to be in the path
        slots = [(3.0, 0.3 * math.sin(i), 6.0 * i) for i in range(12)]
        self.assert_one_car_per_slot(slots)

    def test_a_steep_row_is_reported(self):
        with patch('parked_car_export.report.warning') as warning:
            get_path(row([(0.0, 0.2 * i, 6.0 * i) for i in range(3)]))
        warning.assert_not_called()
        with patch('parked_car_export.report.warning') as warning:
            get_path(row([(0.0, 1.5 * i, 6.0 * i) for i in range(3)]))
        self.assertIn('slope', warning.call_args.args[0])

    def test_slots_that_cant_hold_one_car_are_reported(self):
        with patch('parked_car_export.report.warning') as warning:
            get_path(row(straight(step=3.0)))
        self.assertIn('missing or doubled', warning.call_args.args[0])

    def test_too_many_rows_are_an_error_and_the_file_stays_loadable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'x_parkedcar.pathset')
            with patch('parked_car_export.report.error') as error:
                write_rows(path, [row(straight())] * (MAX_PATHS + 3))
            self.assertIn('the last 3 are left out', error.call_args.args[0])
            self.assertEqual(len(read_paths(path)), MAX_PATHS)

    def test_rows_of_every_source_except_the_skipped_ones(self):
        through = dict(data=dict(name='Intersection', fields=dict(state=dict(propRule=dict(right=container()))),
                                 propLines=[line(straight(), name='right')]))
        data = dict(roads=[road('kept', straight()), road('skipped', straight(), doNotExport=True)],
                    intersections=[dict(data=dict(name='Intersection'), roadsThrough=[through])], customElements=[strip('strip', straight())])
        self.assertEqual([r['name'] for r in get_rows(data)], ['kept', 'Intersection', 'strip'])

    def test_a_row_without_slots_is_reported(self):
        empty = road('empty', [])
        with patch('parked_car_export.report.warning') as warning:
            self.assertEqual(get_rows(dict(roads=[empty])), [])
        self.assertIn('no slots', warning.call_args.args[0])

    def test_files_of_the_city_and_of_the_races(self):
        def data(*elements, roads=()):
            races = [dict(_elementContainerId='A'), dict(_elementContainerId='B')]
            return dict(roads=list(roads), customElements=list(elements),
                        cityProperties=dict(circuitRaces=races, blitzRaces=[dict(_elementContainerId='C')]))
        with tempfile.TemporaryDirectory() as directory:
            folder = directory + '/'
            root = Path(directory)
            export_parked_cars(data(strip('race', straight(2, x=7.0), 'B'), strip('blitz', straight(2, x=9.0), 'C'), roads=[road('city', straight(3))]), folder, 'x')
            self.assertEqual(len(read_paths(root / 'x_parkedcar.pathset')), 1)
            self.assertFalse((root / 'x_parkedcar_circuit0.pathset').exists())
            paths = read_paths(root / 'x_parkedcar_circuit1.pathset')
            self.assertEqual([p[3][0][0] for p in paths], [-7.0, -3.0], 'the rows of the race, then those of the city')
            self.assertTrue((root / 'x_parkedcar_blitz0.pathset').exists())

            # stale files, only the ones of a previous export
            mine = root / 'x_parkedcar_circuit1.pathset'
            other = root / 'x_parkedcar_race7.pathset'
            other.write_bytes(b'by hand')
            export_parked_cars(data(strip('blitz', straight(2), 'C')), folder, 'x')
            self.assertFalse(mine.exists())
            self.assertFalse((root / 'x_parkedcar.pathset').exists())
            self.assertTrue((root / 'x_parkedcar_blitz0.pathset').exists())
            self.assertTrue(other.exists())
            self.assertEqual(json.loads((root / MANIFEST).read_text()), ['x_parkedcar_blitz0.pathset'])

    def test_the_manifest_is_not_packed(self):
        self.assertTrue(MANIFEST.startswith('.km2-'))

    def test_the_rows_are_not_exported_as_props(self):
        prop = dict(meshId=0, position=[3, 7, 11], rotation=[0, 0, 0, 1], scale=[1, 1, 1])
        element = strip('strip', straight())
        element['data']['propLines'][0]['props'] = [prop]
        parts = []
        export_prop_placer(SimpleNamespace(data=dict(meshDict=[dict(name='geometry/giz_pcar01_l.pkg')])), element, parts)
        self.assertEqual(parts, [])
        with_props = road('road', straight())
        with_props['data']['propLines'][0]['props'] = [prop]
        res = []
        rule = with_props['data']['fields']['state']['propRule']
        JsonProcessor.get_road_props(SimpleNamespace(data=dict(meshDict=[])), res, with_props, rule, 'road')
        self.assertEqual(res, [])


if __name__ == '__main__':
    unittest.main()
