"""Synthetic checks of the ambient car rules of the game (traffic/ambient.py, drawn by checks/trafficPaths): the road
and lane each lane of a road goes to at an intersection, the path through it, and left-hand traffic. The roads are
straight, 100 m long, with their lanes 3.5 m wide from the centre line, built as the BAI model of the exporter."""
from pathlib import Path
import math
import sys
import unittest

import numpy as np

CORE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE / 'exporters/psdl'))
from traffic.ambient import CAR_FRONT, LEFT, RIGHT, STRAIGHT, IntersectionTraffic  # noqa: E402
from traffic.model import BaiIntersection, BaiRoad, BaiSide, RoadPaths  # noqa: E402

LANE = 3.5


def road(name, a, b, forward, backward, offset=0.0, freeway=False):
    # a straight road from a to b (program coordinates) with forward lanes going from a to b and backward lanes from
    # b to a, each on the right of its direction (right-hand traffic), the inner one offset + LANE / 2 from the centre
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    d = (b - a) / np.linalg.norm(b - a)
    right = np.array((d[2], 0.0, -d[0]))  # left-handed, y up
    centre = [a + (b - a) * t for t in np.linspace(0, 1, 11)]
    half = offset + LANE * max(forward, backward, 1) + 0.5

    def line(off):
        return [tuple(c + right * off) for c in centre]
    lanes = [line(offset + LANE * (i + 0.5)) for i in range(forward)]
    back = [line(-(offset + LANE * (i + 0.5))) for i in range(backward)]
    # the left side of the BAI goes from the start to the end, the right one from the end to the start
    res = BaiRoad(name, [1], RoadPaths(BaiSide(line(-half - 3), line(-half), back), BaiSide(line(half + 3), line(half), lanes)))
    res.freeway = freeway
    return res


def intersection(ends):
    # ends: (road, at its start); the BAI lists them by increasing angle around the centre, as the exporter does
    node = BaiIntersection('X', 1, np.zeros(3))

    def angle(end):
        r, at_start = end
        i = 0 if at_start else -1
        p = np.add(r.paths.right.outer[i], r.paths.left.outer[i]) / 2
        return math.atan2(p[2], p[0])
    node.roads = sorted(ends, key=angle)
    for r, at_start in ends:
        (r.start if at_start else r.end).intersection = node
    return node


def crossing(lanes_ns=2, lanes_ew=2, west=True, **kwargs):
    # a crossing at the origin: S and E end on it, N and W start on it (both orientations of the roads)
    kw = kwargs.get
    roads = {
        'S': road('S', (0, 0, -110), (0, 0, -10), *kw('S', (lanes_ns, lanes_ns)), offset=kw('S_offset', 0.0), freeway=kw('S_freeway', False)),
        'N': road('N', (0, 0, 10), (0, 0, 110), *kw('N', (lanes_ns, lanes_ns)), offset=kw('N_offset', 0.0), freeway=kw('N_freeway', False)),
        'E': road('E', (110, 0, 0), (10, 0, 0), *kw('E', (lanes_ew, lanes_ew))),
    }
    ends = [(roads['S'], False), (roads['N'], True), (roads['E'], False)]
    if west:
        roads['W'] = road('W', (-10, 0, 0), (-110, 0, 0), *kw('W', (lanes_ew, lanes_ew)))
        ends.append((roads['W'], True))
    return intersection(ends), roads


def results(node, drive_on_left=False):
    # {(road, lane): result} of the lanes arriving at the intersection
    return {(r.road.road.name, r.lane): r for r in IntersectionTraffic(node, {}, drive_on_left).lanes()}


def moves(result):
    return [(m.road.road.name, m.turn, m.driven_lane()) for m in result.moves]


def codes(result):
    return [code for code, _ in result.problems]


class Turns(unittest.TestCase):
    def test_two_lanes(self):
        res = results(crossing()[0])
        # the inner lane: the first road on the left, or the next one (straight on), into lane 0
        self.assertEqual(moves(res[('S', 0)]), [('W', LEFT, 0), ('N', STRAIGHT, 0)])
        # the outer lane: the first road on the right, or straight on, into the outer lane
        self.assertEqual(moves(res[('S', 1)]), [('E', RIGHT, 1), ('N', STRAIGHT, 1)])
        # the same for a road ending on the intersection the other way (E goes towards the centre from its start)
        self.assertEqual(moves(res[('E', 0)]), [('S', LEFT, 0), ('W', STRAIGHT, 0)])
        # and for the roads starting on it (their backward lanes arrive)
        self.assertEqual(moves(res[('N', 1)]), [('W', RIGHT, 1), ('S', STRAIGHT, 1)])
        self.assertEqual(moves(res[('W', 0)]), [('N', LEFT, 0), ('E', STRAIGHT, 0)])
        self.assertEqual(len(res), 8)
        self.assertTrue(all(not r.problems for r in res.values()))

    def test_middle_lane(self):
        res = results(crossing(3, 3)[0])
        # 3 other roads let cars leave: straight on, keeping the lane
        self.assertEqual(moves(res[('S', 1)]), [('N', STRAIGHT, 1)])
        # at a T junction, the roads with 3 lanes or more: here only N
        res = results(crossing(3, 2, west=False)[0])
        self.assertEqual(moves(res[('S', 1)]), [('N', STRAIGHT, 1)])

    def test_single_lane(self):
        # any other road at random, into the outer lane of the one on the right, lane 0 of the others
        res = results(crossing(S=(1, 1))[0])
        self.assertEqual(moves(res[('S', 0)]), [('E', RIGHT, 1), ('N', STRAIGHT, 0), ('W', LEFT, 0)])

    def test_lanes_not_aligned(self):
        # the lanes of N start 3 m further from the centre line: 3 m to the right of the inner lane of S, so it can't go
        # straight on; the outer lane still can (3 m to its right is allowed)
        res = results(crossing(N_offset=3.0)[0])
        self.assertEqual(moves(res[('S', 0)]), [('W', LEFT, 0)])
        self.assertEqual(moves(res[('S', 1)]), [('E', RIGHT, 1), ('N', STRAIGHT, 1)])
        # and the other way round: N's inner lane 3 m to the left of S's outer lane is allowed only for the inner one
        res = results(crossing(S_offset=3.0)[0])
        self.assertEqual(moves(res[('S', 0)]), [('W', LEFT, 0), ('N', STRAIGHT, 0)])
        self.assertEqual(moves(res[('S', 1)]), [('E', RIGHT, 1)])

    def test_freeway(self):
        node, _ = crossing(S=(4, 4), N=(2, 2), S_freeway=True, N_freeway=True)
        res = results(node)
        # the lanes other than the outer one take the first freeway road going forwards and keep their lane number
        self.assertEqual(moves(res[('S', 1)]), [('N', STRAIGHT, 1)])
        self.assertEqual(codes(res[('S', 1)]), [])
        self.assertEqual(moves(res[('S', 2)]), [('N', STRAIGHT, 1)])
        self.assertEqual(codes(res[('S', 2)]), ['traffic_lane_unchecked'])
        # the outer lane uses the routine of the outer lanes: straight on would be 7 m to the left (lane 4 of S to the
        # outer lane of N, where its number is clamped), so only the right turn
        self.assertEqual(moves(res[('S', 3)]), [('E', RIGHT, 1)])

    def test_no_road(self):
        res = results(intersection([(road('S', (0, 0, -110), (0, 0, -10), 1, 1), False)]))
        self.assertEqual(moves(res[('S', 0)]), [])
        self.assertEqual(codes(res[('S', 0)]), ['traffic_no_road'])

    def test_one_way(self):
        # no cars leave the intersection on N (its lanes go towards it) and none arrive from W (its lanes go away)
        res = results(crossing(N=(0, 2), W=(2, 0))[0])
        self.assertNotIn(('W', 0), res)
        self.assertEqual(moves(res[('S', 0)]), [('W', LEFT, 0)])
        self.assertEqual(moves(res[('S', 1)]), [('E', RIGHT, 1)])


class Paths(unittest.TestCase):
    def test_straight(self):
        res = results(crossing()[0])
        move = res[('S', 0)].moves[1]
        points = np.array(move.points)
        # along the inner lane (on the right of the centre line, +x going +z), from the lane before the end of S to
        # the lane after the start of N
        self.assertTrue(np.allclose(points[:, 0], LANE / 2))
        self.assertTrue(np.all(np.diff(points[:, 2]) > 0))
        # it leaves the lane the front of the car before its end, and reaches the start of the lane of N
        self.assertTrue(any(np.allclose(p, (LANE / 2, 0, -10 - CAR_FRONT)) for p in points))
        self.assertTrue(np.allclose(points[-2], (LANE / 2, 0, 10)))

    def test_right_turn(self):
        res = results(crossing()[0])
        move = res[('S', 1)].moves[0]
        points = np.array(move.points)
        # from the outer lane of S (x = 5.25) to the outer lane of E leaving the centre (going +x, on its right: -z)
        self.assertTrue(np.allclose(points[0][[0, 2]], (1.5 * LANE, -10 - CAR_FRONT - 5)))
        self.assertTrue(np.allclose(points[-2], (10, 0, -1.5 * LANE)))
        self.assertTrue(np.allclose(points[-1], (15, 0, -1.5 * LANE)))
        # it stays in the corner between them
        self.assertTrue(np.all(points[:, 0] >= 1.5 * LANE - 1e-9) and np.all(points[:, 2] <= -1.5 * LANE + 1e-9))


class LeftHandTraffic(unittest.TestCase):
    def test_mirrored(self):
        res = results(crossing()[0], drive_on_left=True)
        # the lanes are swapped between the two directions: lane 0 is now the kerb lane, on the left (x < 0 going +z),
        # and turns left; the last lane, next to the centre line, turns right
        self.assertEqual(moves(res[('S', 0)]), [('W', LEFT, 0), ('N', STRAIGHT, 0)])
        self.assertEqual(moves(res[('S', 1)]), [('E', RIGHT, 1), ('N', STRAIGHT, 1)])
        straight = np.array(res[('S', 0)].moves[1].points)
        self.assertTrue(np.allclose(straight[:, 0], -1.5 * LANE))
        right = np.array(res[('S', 1)].moves[0].points)
        self.assertTrue(np.allclose(right[0][[0, 2]], (-LANE / 2, -10 - CAR_FRONT - 5)))
        # into E leaving the centre on its left (+z), next to the centre line
        self.assertTrue(np.allclose(right[-2], (10, 0, LANE / 2)))
        self.assertTrue(all(not r.problems for r in res.values()))

    def test_lane_counts(self):
        # a two-way road with different counts both ways gets a warning (once, on its first lane); a one-way road not
        res = results(crossing(S=(2, 3), N=(0, 2))[0], drive_on_left=True)
        self.assertEqual(codes(res[('S', 0)]), ['traffic_left_hand_lanes'])
        self.assertEqual(codes(res[('S', 1)]), [])
        self.assertEqual(codes(results(crossing(S=(2, 0))[0], drive_on_left=True)[('S', 0)]), [])


if __name__ == '__main__':
    unittest.main()
