"""Bounded synthetic checks of the boat, duck and ferry PATHSET export (no stock data, no importer)."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE/'exporters/psdl'), str(CORE.parents[1]/'python')]
from boat_export import get_boat_routes, export_boats, MODELS


def boat(name, model, points, speed=0, **extra):
    return dict(type='movingObject', data=dict(name=name, fields=dict(state=dict(model=model, speed=speed, **extra))),
                points=dict(spline=[dict(id=i, position=p) for i, p in enumerate(points)]))


LOOP = [[0, -2, 0], [10, -2, 0], [10, -2, 10], [0, -2, 10]]


def read_pathset(path):
    # PTH1: count, 0, then per path name32, points, 0, points of (room, x, y, z), type, spacing, 0
    d = Path(path).read_bytes()
    assert d[:4] == b'PTH1'
    n, = struct.unpack_from('<I', d, 4)
    o, paths = 12, []
    for _ in range(n):
        name = d[o:o+32].split(b'\0')[0].decode()
        count, extra = struct.unpack_from('<II', d, o+32)
        o += 40
        pts = [struct.unpack_from('<Ifff', d, o+16*k) for k in range(count)]
        o += 16*count
        typ, spacing, pad = struct.unpack_from('<BBH', d, o)
        o += 4
        paths.append(dict(name=name, points=pts, type=typ, spacing=spacing, extra=extra, pad=pad))
    assert o == len(d)
    return paths


class BoatTests(unittest.TestCase):
    def test_routes_use_controls_and_split_by_pathset(self):
        data = dict(customElements=[boat('a', 0, LOOP), boat('d', 2, LOOP), boat('f', 5, LOOP, speed=9), dict(type='train')])
        routes = get_boat_routes(data)
        self.assertEqual([r[0] for r in routes['sailboat']], [None, 'giz_duck_s'])
        self.assertEqual([r[0] for r in routes['ferry']], ['giz_carferry01_l'])
        self.assertEqual(routes['sailboat'][0][1][1], (-10, -2, 0))  # X mirrored
        self.assertEqual([r[2] for r in routes['sailboat']], [20, 8])  # model default speeds, in quarter metres per second
        self.assertEqual(routes['ferry'][0][2], 20)  # the ferry does not read the speed

    def test_speed_and_model_names(self):
        data = dict(customElements=[boat('s', 1, LOOP, speed=7.3), boat('t', 3, LOOP, speed=1000), boat('w', 4, LOOP, speed=0.01)])
        routes = get_boat_routes(data)['sailboat']
        self.assertEqual([r[0] for r in routes], ['giz_sailboard01_f', 'giz_tug01_l', 'giz_watertaxi01_l'])
        self.assertEqual([r[2] for r in routes], [29, 255, 1])

    def test_invalid_routes_are_skipped(self):
        data = dict(customElements=[boat('two', 0, LOOP[:2]), boat('same', 0, [LOOP[0], LOOP[0], LOOP[1]]),
                                    boat('nan', 0, [LOOP[0], LOOP[1], [float('nan'), 0, 0]]), boat('model', 99, LOOP),
                                    boat('closing', 0, [LOOP[0], LOOP[1], LOOP[0]]), boat('ok', 0, LOOP)])
        routes = get_boat_routes(data)
        self.assertEqual(len(routes['sailboat']), 1)

    def test_file_layout_and_stale_files(self):
        data = dict(customElements=[boat('a', 0, LOOP), boat('d', 2, LOOP[:3], speed=3), boat('f', 5, LOOP)])
        with tempfile.TemporaryDirectory() as folder:
            race = folder + '/'
            export_boats(data, race, 'test')
            sail = read_pathset(race + 'test_sailboat.pathset')
            self.assertEqual([p['name'] for p in sail], ['PATH0', 'giz_duck_s'])
            self.assertEqual([p['type'] for p in sail], [2, 2])
            self.assertEqual([p['spacing'] for p in sail], [20, 12])
            self.assertEqual([p['points'][1] for p in sail][0], (0, -10.0, -2.0, 0.0))
            self.assertEqual(len(sail[1]['points']), 3)
            ferry = read_pathset(race + 'test_ferry.pathset')
            self.assertEqual([p['name'] for p in ferry], ['giz_carferry01_l'])
            export_boats(dict(customElements=[boat('a', 0, LOOP)]), race, 'test')
            self.assertFalse(Path(race + 'test_ferry.pathset').exists())
            export_boats(dict(customElements=[]), race, 'test')
            self.assertFalse(Path(race + 'test_sailboat.pathset').exists())

    def test_models_are_unique_enum_entries(self):
        self.assertEqual(len(MODELS), 6)


if __name__ == '__main__':
    unittest.main()
