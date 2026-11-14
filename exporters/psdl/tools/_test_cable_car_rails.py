"""Synthetic checks of the cable car rules of the game (traffic/rails.py): the next road and the curve through an
intersection."""
from pathlib import Path
import sys
import unittest

import numpy as np

CORE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE / 'exporters/psdl'))
from traffic.rails import CABLE_CAR_HALF_LENGTH, curve_start, next_tram_road, transition_curve


class NextRoad(unittest.TestCase):
    def test_counts(self):
        # the end of a line: the same road
        self.assertEqual(next_tram_road([False, True, False], 1), 1)
        # two: the other one, whatever is between them
        self.assertEqual(next_tram_road([True, False, True], 0), 2)
        self.assertEqual(next_tram_road([True, False, True], 2), 0)
        # four: the second one after its own, in the order of the intersection (the opposite one of a crossing)
        flags = [True, True, False, True, True]
        self.assertEqual([next_tram_road(flags, k) for k in (0, 1, 3, 4)], [3, 4, 0, 1])
        # three or more than four: none
        self.assertIsNone(next_tram_road([True, True, True], 0))
        self.assertIsNone(next_tram_road([True] * 5, 0))


class Curve(unittest.TestCase):
    def test_start(self):
        # half the car before the end of the rail, measured on the centre line
        start = curve_start([[0, 0, 0], [0, 0, 10]], 10.0)
        self.assertTrue(np.allclose(start, [0, 0, 10 - CABLE_CAR_HALF_LENGTH]))
        # a rail on the outside of a curve is longer than the centre line: the same fraction of it
        start = curve_start([[0, 0, 0], [0, 0, 20]], 10.0)
        self.assertTrue(np.allclose(start, [0, 0, 20 - 2 * CABLE_CAR_HALF_LENGTH]))

    def test_straight(self):
        curve = transition_curve([0, 1, 0], [0, 0, 1], [0, 3, 20], [0, 0, 1])
        self.assertTrue(np.allclose(curve[0], [0, 1, 0]) and np.allclose(curve[-1], [0, 3, 20]))
        self.assertTrue(all(abs(p[0]) < 1e-9 for p in curve))
        self.assertTrue(all(abs(b[2] - a[2]) <= 2.0 + 1e-9 for a, b in zip(curve, curve[1:])))
        # the height is linear
        self.assertTrue(np.allclose([p[1] for p in curve], np.linspace(1, 3, len(curve))))

    def test_turn(self):
        # a 90 degree turn from +z to +x: the tangents are scaled by |dx| + |dz| = 20, not by the chord (14.1)
        curve = transition_curve([0, 0, 0], [0, 0, 1], [10, 0, 10], [1, 0, 0], 0.5)
        t0, t1, p1 = np.array([0, 0, 20.0]), np.array([20.0, 0, 0]), np.array([10.0, 0, 10])
        n = len(curve) - 1
        for k, p in enumerate(curve):
            t = k / n
            expected = p1 * (-2*t**3 + 3*t**2) + t0 * (t**3 - 2*t**2 + t) + t1 * (t**3 - t**2)
            self.assertTrue(np.allclose(p, expected), (k, p, expected))
        # at t = 0.5 the curve is at (2.5, 7.5), wider than the quarter circle of radius 10 (its middle is at (2.93, 7.07))
        self.assertTrue(np.allclose(p1 * 0.5 + t0 * 0.125 - t1 * 0.125, [2.5, 0, 7.5]))


if __name__ == '__main__':
    unittest.main()
