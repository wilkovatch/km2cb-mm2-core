"""Short checks of the opponent route check (traffic/opponents.py): synthetic networks with each kind of problem.

With KM2_MM2_STOCK_CITY set to the city folder of the extracted stock files, a fixed sample of the stock OPP files of
sf and london (in the race folder next to it) is checked against the stock PSDL rooms, facade bounds and BAI: no stock
opponent may have a waypoint out of the rooms or off the intersections. Straight legs through facades do occur in the
stock files (e.g. sf race7-p-3, waypoints 4-5 and 7-8, diagonally through built blocks): they are listed (KM2_VERBOSE=1),
not failed."""
import os
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest

import numpy as np

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE / 'exporters/psdl/tools'), str(CORE.parents[1] / 'python')]
from traffic.model import BaiNetwork, BaiRoad, BaiIntersection, RoadPaths, BaiSide
from traffic.opponents import OpponentMap, ROAD, STRAIGHT, BLOCKED

STOCK_SAMPLE = 6  # OPP files per city


def straight_road(name, a, b, room, pts=None):
    # a road from the intersection a to b (a straight line of 3 sections, unless pts gives its centre line)
    if pts is None:
        pts = [a.centre + (b.centre - a.centre) * t for t in (0.0, 0.5, 1.0)]
    else:
        pts = [np.array(q, dtype=float) for q in pts]
    side = BaiSide(pts, pts, [pts])
    road = BaiRoad(name, [room], RoadPaths(side, side))
    road.start.intersection, road.end.intersection = a, b
    a.roads.append((road, True))
    b.roads.append((road, False))
    return road


def grid_city():
    # 3 intersections in a row (rooms 1, 3, 5, 100 m apart), joined by roads (rooms 2, 4), a park (room 6) north of
    # them and a building block (room 7, with a facade) north of the park; everything else is out of the city
    net = BaiNetwork()
    nodes = [net.add_intersection(BaiIntersection('I' + str(k), 1 + 2 * k, np.array([100.0 * k, 0.0, 0.0]))) for k in range(3)]
    for k in range(2):
        net.add_road(straight_road('R' + str(k), nodes[k], nodes[k + 1], 2 + 2 * k))

    def room_of(p):
        x, z = float(p[0]), float(p[2])
        if -10 <= z <= 10 and -10 <= x <= 210:
            k = int(round(x / 50.0))
            return 1 + k if abs(x - 50 * k) <= 40 or k % 2 == 1 else 0
        if 10 < z <= 100 and -10 <= x <= 210:
            return 6
        if 100 < z <= 200 and -10 <= x <= 210:
            return 7
        return 0
    facades = [((-10.0, 150.0), (210.0, 150.0), 0.0, 20.0)]
    return OpponentMap(room_of, net, facades), nodes


TURN = 'opponent_turn_too_sharp'


def turns_city():
    # I1 (100, 0) reached from I0 (0, 0), with roads on to I2 (a quarter turn), I3 (back by 153 degrees) and I4 (a
    # quarter turn, but its end on I1 is 30 m behind a car coming from I0, as on a road without geometry)
    net = BaiNetwork()
    centres = ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (20.0, 40.0), (100.0, -100.0))
    nodes = [net.add_intersection(BaiIntersection('I' + str(k), 1 + 2 * k, np.array([x, 0.0, z])))
             for k, (x, z) in enumerate(centres)]
    for k, (a, b) in enumerate(((0, 1), (1, 2), (1, 3))):
        net.add_road(straight_road('R' + str(k), nodes[a], nodes[b], 2 + 2 * k))
    net.add_road(straight_road('R3', nodes[1], nodes[4], 8, pts=((70.0, 0.0, -30.0), (90.0, 0.0, -60.0), (100.0, 0.0, -100.0))))

    def room_of(p):
        for node in nodes:
            if np.hypot(p[0] - node.centre[0], p[2] - node.centre[2]) < 10.0:
                return node.room
        return 2
    return OpponentMap(room_of, net), [tuple(n.centre) for n in nodes]


class OpponentRouteTest(unittest.TestCase):
    def test_sharp_turns(self):
        city, c = turns_city()
        res = city.check(c[0], [c[0], c[1], c[2], c[2]])
        self.assertEqual(res.issues, [])
        # back by 153 degrees at the waypoint 2
        res = city.check(c[0], [c[0], c[1], c[3], c[3]])
        self.assertEqual([(i.code, tuple(i.position)) for i in res.issues], [(TURN, c[1])])
        self.assertIn('turns back by 153 degrees onto R2', res.issues[0].message)
        self.assertIs(res.issues[0].leg.road, city.network.roads[2])
        self.assertFalse(res.ok())
        # a quarter turn onto a road starting behind the car
        res = city.check(c[0], [c[0], c[1], c[4], c[4]])
        self.assertEqual([i.code for i in res.issues], [TURN])
        self.assertIn('R3 starts behind the opponent (135 degrees', res.issues[0].message)
        # a U-turn, and on a closed circuit the U-turn at the last waypoint into the next lap too
        res = city.check(c[0], [c[0], c[1], c[0], c[0]], laps=1)
        self.assertEqual([(i.code, tuple(i.position)) for i in res.issues], [(TURN, c[1])])
        res = city.check(c[0], [c[0], c[1], c[0], c[0]], laps=2)
        self.assertEqual([(i.code, tuple(i.position)) for i in res.issues], [(TURN, c[1]), (TURN, c[0])])

    def test_road_legs(self):
        city, nodes = grid_city()
        res = city.check((0.0, 0.0, -0.0), [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (200.0, 0.0, 0.0), (195.0, 0.0, 0.0)])
        self.assertTrue(res.ok())
        self.assertEqual([i.code for i in res.issues], [])
        self.assertEqual([leg.kind for leg in res.legs], [ROAD, ROAD, ROAD, ROAD])
        self.assertIs(res.legs[1].road, city.network.roads[0])

    def test_skipped_intersection_is_straight(self):
        # 0 -> 200 skips the middle intersection: no road joins them, the straight line follows the roads here
        city, nodes = grid_city()
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (200.0, 0.0, 0.0), (200.0, 0.0, 0.0)])
        self.assertEqual([leg.kind for leg in res.legs], [ROAD, STRAIGHT, ROAD])
        self.assertEqual([i.code for i in res.issues], ['opponent_leg_straight'])
        self.assertTrue(res.ok())

    def test_waypoint_on_road(self):
        city, nodes = grid_city()
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (50.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 0.0)])
        self.assertIn('opponent_waypoint_not_intersection', [i.code for i in res.issues])
        self.assertIn('R0', [i.message for i in res.issues if i.code == 'opponent_waypoint_not_intersection'][0])
        self.assertFalse(res.ok())

    def test_point_out_of_the_city(self):
        city, nodes = grid_city()
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (500.0, 0.0, 500.0)])
        self.assertEqual([i.code for i in res.issues if i.level == 'error'], ['opponent_point_no_room', 'opponent_leg_blocked'])

    def test_blocked_by_facade(self):
        # to a finish behind the facade: straight from the last waypoint, through it
        city, nodes = grid_city()
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 180.0)])
        blocked = [leg for leg in res.legs if leg.kind == BLOCKED]
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0].facades, 1)
        self.assertAlmostEqual(float(blocked[0].first_problem[2]), 150.0, places=3)
        self.assertFalse(res.ok())

    def test_facade_above_the_car(self):
        city, nodes = grid_city()
        city.facade_bottom[:] = 5.0  # e.g. a bridge: the car passes under it
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 180.0)])
        self.assertEqual([leg.kind for leg in res.legs], [ROAD, ROAD, STRAIGHT])

    def test_repeated_waypoint_and_too_few(self):
        city, nodes = grid_city()
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 0.0)])
        self.assertEqual([i.code for i in res.issues], ['opponent_waypoint_repeated'])
        res = city.check((0.0, 0.0, 0.0), [(100.0, 0.0, 0.0)])
        self.assertEqual([i.code for i in res.issues], ['opponent_no_waypoints'])

    def test_circuit_goes_on_to_the_second_waypoint(self):
        city, nodes = grid_city()
        # last waypoint = the first one: nothing more to check (but the turns, U-turns on this row of intersections,
        # see test_sharp_turns)
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)], laps=2)
        self.assertEqual([leg.kind for leg in res.legs], [ROAD, ROAD, ROAD, ROAD])
        self.assertEqual([i.code for i in res.issues if i.code != TURN], [])
        # last waypoint elsewhere: the next lap goes from it to the second waypoint (here along a road), drawn, but the
        # open loop is an error (the opponent circles at the last waypoint in game)
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (200.0, 0.0, 0.0), (200.0, 0.0, 0.0)], laps=2)
        self.assertEqual(len(res.legs), 5)
        self.assertEqual(res.legs[3].kind, ROAD)
        self.assertEqual((res.legs[3].start, res.legs[3].end), ('waypoint 3', 'waypoint 2'))
        self.assertEqual([(i.level, i.code) for i in res.issues], [('error', 'opponent_circuit_open')])
        self.assertIs(res.issues[0].leg, res.legs[3])
        # without a road to the second waypoint either: the same error, not a straight leg as well
        res = city.check((0.0, 0.0, 0.0), [(100.0, 0.0, 0.0), (200.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)], laps=2)
        self.assertEqual([i.code for i in res.issues if i.code != TURN and (i.code != 'opponent_leg_straight' or i.leg.lap)],
                         ['opponent_circuit_open'])
        self.assertTrue(any(leg.lap and leg.kind == STRAIGHT for leg in res.legs))
        # a single lap never goes back
        res = city.check((0.0, 0.0, 0.0), [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (200.0, 0.0, 0.0), (200.0, 0.0, 0.0)], laps=1)
        self.assertEqual(len(res.legs), 4)
        self.assertNotIn(('waypoint 3', 'waypoint 2'), [(leg.start, leg.end) for leg in res.legs])


def stock_map(city_folder, name):
    from bai_check import read_bai
    import psdl_check
    vertices, rooms, attributes, _ = psdl_check.read_psdl(str(city_folder / (name + '.psdl')))
    heights = read_psdl_heights(city_folder / (name + '.psdl'))
    polys, room_y, bounds = [], [], []
    for perimeter in rooms:
        vs = psdl_check.distinct_vertices(perimeter)
        poly = [(vertices[v][0], vertices[v][2]) for v in vs]
        polys.append(poly)
        room_y.append(float(np.mean([vertices[v][1] for v in vs])) if vs else 0.0)
        arr = np.array(poly) if poly else np.zeros((1, 2))
        bounds.append((arr.min(axis=0), arr.max(axis=0)))
    lo = np.array([b[0] for b in bounds])
    hi = np.array([b[1] for b in bounds])

    def room_of(p):
        x, z = float(p[0]), float(p[2])
        best, dist = 0, None
        for i in np.nonzero((x >= lo[:, 0]) & (x <= hi[:, 0]) & (z >= lo[:, 1]) & (z <= hi[:, 1]))[0]:
            if psdl_check.inside(polys[i], (x, z)):
                d = abs(float(p[1]) - room_y[i])
                if dist is None or d < dist:
                    best, dist = int(i) + 1, d
        return best
    facades = []
    for words in attributes:
        for (v0, v1, h, bottom) in facade_bounds(words):
            a, b = vertices[v0], vertices[v1]
            y0 = min(a[1], b[1])
            facades.append(((a[0], a[2]), (b[0], b[2]), y0, y0 + heights[h] if h < len(heights) else y0 + 10.0))
    roads, ints = read_bai(str(city_folder / (name + '.bai')))
    net = BaiNetwork()
    nodes = {}
    for it in ints:
        nodes[it['id']] = net.add_intersection(BaiIntersection(str(it['id']), it['room'], np.array(it['centre'])))
    for rd in roads:
        side = BaiSide(rd['centre'], rd['centre'], [])
        road = net.add_road(BaiRoad('road ' + str(rd['id']), list(rd['rooms']), RoadPaths(side, side)))
        a, b = nodes.get(rd['start']['intersection']), nodes.get(rd['end']['intersection'])
        road.start.intersection, road.end.intersection = a, b
    # the road lists of the intersections in the order of the file
    road_by_id = {rd['id']: net.roads[i] for i, rd in enumerate(roads)}
    for it in ints:
        node = nodes[it['id']]
        for rid in it['roads']:
            road = road_by_id.get(rid)
            if road is not None:
                node.roads.append((road, road.start.intersection is node))
    return OpponentMap(room_of, net, facades)


def read_psdl_heights(path):
    import struct
    b = path.read_bytes()
    n_vertices = struct.unpack_from('<I', b, 8)[0]
    o = 12 + 12 * n_vertices
    n_heights = struct.unpack_from('<I', b, o)[0]
    return list(struct.unpack_from('<' + str(n_heights) + 'f', b, o + 4))


def facade_bounds(words):
    # the facade bound attributes of a room: (vertex 0, vertex 1, height index, 0) (type 7: sun angle, height, v0, v1)
    res = []
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        typ, subtype = (word >> 3) & 15, word & 7
        if typ == 10:
            i += 1
        elif typ in (0, 1, 2, 4, 5, 6, 8, 9, 12):
            n = subtype
            if subtype == 0:
                n = words[i]
                i += 1
            i += {0: 4 * n, 1: 2 * n, 2: 2 * n, 5: n + 2, 6: n + 2, 8: 2 + 6 * n, 12: n + 2}.get(typ, n)
        elif typ == 7:
            res.append((words[i + 2], words[i + 3], words[i + 1], 0))
            i += 4
        elif typ == 3:
            i += 4
        elif typ == 11:
            i += 6
        else:
            break
        if word & 0x80:
            break
    return res


def read_opp(path):
    rows = []
    for line in path.read_text().splitlines()[1:]:
        if line.strip():
            rows.append(np.array([float(v) for v in line.split(',')[:3]]))
    return rows


@unittest.skipUnless(os.environ.get('KM2_MM2_STOCK_CITY'), 'KM2_MM2_STOCK_CITY not set')
class StockOpponentsTest(unittest.TestCase):
    def test_stock_opponents(self):
        city_folder = Path(os.environ['KM2_MM2_STOCK_CITY'])
        verbose = bool(os.environ.get('KM2_VERBOSE'))
        for name in ('sf', 'london'):
            city = stock_map(city_folder, name)
            files = sorted((city_folder.parent / 'race' / name).glob('*.opp'))
            random.Random(1).shuffle(files)
            for path in files[:STOCK_SAMPLE]:
                rows = read_opp(path)
                # the stock circuits have several laps
                res = city.check(rows[0], rows[1:], laps=2 if path.name.startswith('circuit') else 1)
                kinds = ''.join({ROAD: 'r', STRAIGHT: 's', BLOCKED: 'B'}[leg.kind] for leg in res.legs)
                if verbose:
                    print(name, path.name, kinds, [(i.code, i.message) for i in res.issues if i.level == 'error'])
                with self.subTest(city=name, opp=path.name):
                    self.assertEqual([i.message for i in res.issues if i.level == 'error' and i.code != 'opponent_leg_blocked'], [])


if __name__ == '__main__':
    unittest.main()
