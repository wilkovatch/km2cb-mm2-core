"""Bounded synthetic checks of the CPVS writer (writers/cpvs_writer.py): the lists, the file layout and the occlusion.

With KM2_MM2_STOCK_CITY set to the city folder of the extracted stock files, the stock london.cpvs lists are also
decoded and encoded again."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE/'exporters/psdl'), str(CORE.parents[1]/'python')]
from psdl_parts import ExportedCityElement
from scene import Scene
from writers.cpvs_writer import (CPVSGenerator, CPVSWriter, FAST, ACCURATE, OCCLUDER_GROUND, OCCLUDER_CLOSED,
                                 encode_list, decode_list, list_values, write_cpvs, read_cpvs, shared_vertex_neighbours)


def quad(x0, x1, y0, y1, z):
    a, b, c, d = (x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)
    return [[a, b, c], [a, c, d]]


def wall(x, y0, y1, z0, z1):
    a, b, c, d = (x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)
    return [[a, b, c], [a, c, d]]


def box_top(x0, x1, y0, y1, z):
    return quad(x0, x1, y0, y1, z)


def generate(rooms, occluders=(), closed=(), extra_targets=None, parameters=FAST):
    # rooms: the floor triangles of each room (also its targets); occluders: ground/wall triangles, closed: roofs
    floors = [np.array(r, dtype=float) for r in rooms]
    targets = [np.array(r, dtype=float) for r in rooms]
    for room, tris in (extra_targets or {}).items():
        targets[room] = np.concatenate([targets[room], np.array(tris, dtype=float)])
    occ = [t for r in rooms for t in r] + list(occluders) + list(closed)
    kinds = [OCCLUDER_GROUND] * (sum(len(r) for r in rooms) + len(occluders)) + [OCCLUDER_CLOSED] * len(closed)
    neighbours = shared_vertex_neighbours([f.reshape(-1, 3) for f in floors])
    return CPVSGenerator(floors, targets, np.array(occ, dtype=float), kinds, neighbours, parameters).generate()


class Lists(unittest.TestCase):
    def test_round_trip(self):
        rng = np.random.default_rng(7)
        for n in (1, 2, 3, 4, 5, 17, 300, 1341):
            for density in (0.0, 0.05, 0.5, 1.0):
                visible = rng.random(n) < density
                visible[0] = False
                data = decode_list(encode_list(visible))
                self.assertEqual(len(data), (n + 3) // 4)
                values = list_values(data, n)
                self.assertTrue(np.array_equal(values == 3, visible))
                self.assertTrue(np.all((values == 0) | (values == 3)))

    def test_repeat_counts_are_not_offset(self):
        # as in the stock files: a repeat header n gives n bytes (a copy header n gives n + 1)
        self.assertEqual(decode_list(bytes([0x03, 0x00])), b'\0\0\0')
        self.assertEqual(decode_list(bytes([0x81, 0xcc, 0x0f, 0x03, 0x00])), bytes([0xcc, 0x0f, 0, 0, 0]))
        encoded = encode_list(np.zeros(4 * 300, dtype=bool))
        self.assertEqual(encoded, bytes([127, 0, 127, 0, 46, 0]))

    def test_bits(self):
        visible = np.zeros(17, dtype=bool)
        visible[[1, 3, 4, 5, 16]] = True  # PSDL rooms 1, 3, 4, 5 and 16 (pair 0 is reserved)
        data = decode_list(encode_list(visible))
        self.assertEqual(data, bytes([0b11001100, 0b00001111, 0, 0, 0b00000011]))

    @unittest.skipUnless(os.environ.get('KM2_MM2_STOCK_CITY'), 'KM2_MM2_STOCK_CITY not set')
    def test_stock_lists(self):
        path = Path(os.environ['KM2_MM2_STOCK_CITY']) / 'london.cpvs'
        n_rooms, lists = read_cpvs(path)
        rng = np.random.default_rng(1)
        for i in rng.choice(n_rooms, 10, replace=False):
            self.assertLessEqual(len(lists[i]), (n_rooms + 4) // 4)
            values = list_values(lists[i], n_rooms + 1)
            self.assertEqual(values[0], 0)
            again = list_values(decode_list(encode_list(values == 3)), n_rooms + 1)
            self.assertTrue(np.array_equal(values, again))


class File(unittest.TestCase):
    def test_layout(self):
        rng = np.random.default_rng(3)
        for n in (0, 1, 300):
            sets = [rng.random(n) < 0.1 for _ in range(n)]
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'x.cpvs'
                write_cpvs(path, sets)
                b = path.read_bytes()
                self.assertEqual(b[:4], b'PVS0')
                self.assertEqual(int.from_bytes(b[4:8], 'little'), n + 2)
                n_rooms, lists = read_cpvs(path)
                self.assertEqual(n_rooms, n)
                for s, data in zip(sets, lists):
                    self.assertTrue(np.array_equal(list_values(data, n + 1)[1:] == 3, s))


class Occlusion(unittest.TestCase):
    # rooms along x: A [0, 20], B [20, 40] (sharing an edge with A), C [60, 80], all 20 m wide in y
    A = quad(0, 20, 0, 20, 0)
    B = quad(20, 40, 0, 20, 0)
    C = quad(60, 80, 0, 20, 0)

    def test_open_ground(self):
        for parameters in (FAST, ACCURATE):
            sets = generate([self.A, self.B, self.C], parameters=parameters)
            self.assertTrue(all(np.all(s) for s in sets))

    def test_tall_wall_hides(self):
        sets = generate([self.A, self.B, self.C], occluders=wall(50, -200, 220, 0, 30))
        self.assertTrue(sets[0][1] and not sets[0][2], sets[0])
        self.assertFalse(sets[2][0])
        low = generate([self.A, self.B, self.C], occluders=wall(50, -200, 220, 0, 1))
        self.assertTrue(low[0][2])

    def test_neighbours_always_visible(self):
        # a wall between A and B: B is still visible from A (they share an edge), C is not
        sets = generate([self.A, self.B, self.C], occluders=wall(20.5, -200, 220, 0, 60))
        self.assertTrue(sets[0][1] and sets[1][0])
        self.assertFalse(sets[0][2])

    def test_tall_object_behind_wall(self):
        tower = box_top(65, 75, 5, 15, 100)
        sets = generate([self.A, self.B, self.C], occluders=wall(50, -200, 220, 0, 30), extra_targets={2: tower})
        self.assertTrue(sets[0][2])

    def test_roof_over_floor(self):
        # a building over C (closed roof at 30 m, with its walls): it hides what is behind it, and a viewpoint inside it
        # is raised above the roof
        D = quad(120, 140, 0, 20, 0)
        walls = wall(60, 0, 20, 0, 30) + wall(80, 0, 20, 0, 30)
        sets = generate([self.A, self.C, D], occluders=walls, closed=quad(60, 80, -100, 120, 30))
        self.assertFalse(sets[0][2])
        self.assertTrue(sets[1][0] and sets[1][2])

    def test_bridge_is_a_passage(self):
        # a deck at 8 m over a road (the floor of E under it): it doesn't hide what is under and beyond it
        E = quad(-60, 0, 0, 20, 0)
        deck = quad(-40, -20, -200, 220, 8)
        F = quad(-100, -80, 0, 20, 0)
        sets = generate([self.A, E, F, deck])
        self.assertTrue(sets[0][2])
        # the same deck as a solid block (no road under it) hides F
        hill = generate([self.A, F, deck])
        self.assertFalse(hill[0][1])


class SceneAdapter(unittest.TestCase):
    def element(self, name, vertices=(), indices=(), **properties):
        e = ExportedCityElement()
        e.name = name
        e.vertices = list(vertices)
        e.indices = list(indices)
        e.properties = properties
        e.mat = 'ground'
        return e

    def ground(self, block, x0, x1):
        # program space (y up)
        v = [(x0, 0, 0), (x0, 0, 20), (x1, 0, 20), (x1, 0, 0)]
        return self.element(str(block) + '_BLOCK', v, [0, 1, 2, 0, 2, 3])

    def test_rooms_and_objects(self):
        wall_part = self.element('3_FACB', [(50, 0, -200), (50, 0, 220), (50, 30, -200), (50, 30, 220)], [0, 2, 1, 1, 2, 3])
        tower = self.element('3,5_INST', bounds='-5,0,-5,5,100,5', object='tower')
        tower.translation = (70, 0, 10)
        tower.vertices = [(0, 0, 0)]  # the placeholder cube of the exporter, not used
        parts = [self.ground(1, 0, 20), self.ground(3, 20, 40), self.ground(5, 60, 80), wall_part, tower]
        scene = Scene(parts)
        self.assertEqual(len(scene.blocks), 3)
        writer = CPVSWriter(scene, 'x.psdl', False)
        floors, targets, occluders, kinds, neighbours = writer.inputs()
        self.assertAlmostEqual(float(targets[2][:, :, 2].max()), 100.0, places=3)
        self.assertEqual(neighbours[0], {1})
        with tempfile.TemporaryDirectory() as directory:
            writer.path = str(Path(directory) / 'x.cpvs')
            writer.write()
            n_rooms, lists = read_cpvs(writer.path)
            self.assertEqual(n_rooms, 3)
            # the tower over the wall makes the room 5 visible from the room 1
            self.assertEqual(list(list_values(lists[0], 4)), [0, 3, 3, 3])
            tower.properties['bounds'] = '-5,0,-5,5,10,5'
            writer2 = CPVSWriter(Scene(parts), str(Path(directory) / 'y.psdl'), False)
            writer2.write()
            n_rooms, lists = read_cpvs(writer2.path)
            self.assertEqual(list(list_values(lists[0], 4)), [0, 3, 3, 0])


if __name__ == '__main__':
    unittest.main()
