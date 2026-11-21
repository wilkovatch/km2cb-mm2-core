"""Bounded synthetic checks of the neighbours of the PSDL perimeter points (PSDLWriter.assign_neighbours), no stock data.

As in the stock cities, a point is written once for each other room that only touches it, then once with the room across
the edge to the next point (0 for none): the game takes the last one as the neighbour of that edge."""
from pathlib import Path
import sys
import unittest

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python')]
from writers.psdl_writer import PSDLWriter, PerimeterVert


def neighbours(vertices, rooms):
    # vertices: (x, y) positions (z up, at 0); rooms: their perimeters as vertex indices (from 1, counterclockwise);
    # the room numbers written with each point of each room
    writer = PSDLWriter(None, 'x.psdl', False, False)
    writer.initialize_variables()
    writer.vertices = [(x, y, 0.0) for x, y in vertices]
    perimeters = [[PerimeterVert(v, []) for v in room] for room in rooms]
    writer.assign_neighbours(perimeters)
    return [[pv.neighbours for pv in perimeter] for perimeter in perimeters]


class Neighbours(unittest.TestCase):
    def test_four_rooms_at_a_corner(self):
        # 2 x 2 rooms: 1 bottom left, 2 bottom right, 3 top left, 4 top right, all meeting at vertex 5 (1, 1)
        grid = [(x, y) for y in range(3) for x in range(3)]
        rooms = [[1, 2, 5, 4], [2, 3, 6, 5], [4, 5, 8, 7], [5, 6, 9, 8]]
        res = neighbours(grid, rooms)
        # room 1: out of the city to 2, room 2 to 5, then room 4 only touches 5 (its corner) and room 3 is across 5-4
        self.assertEqual(res[0], [[0], [2], [4, 3], [0]])
        # room 4: 5 is a corner of room 1 (room 2 is across the edge to 5, room 3 across the edge from 5)
        self.assertEqual(res[3], [[1, 2], [0], [0], [3]])

    def test_the_edge_from_the_previous_point_is_not_repeated(self):
        # room 1 shares its whole right side (2-3) with room 2, then goes out of the city from 3
        rooms = [[1, 2, 3, 4], [2, 5, 6, 3]]
        res = neighbours([(0, 0), (1, 0), (1, 1), (0, 1), (2, 0), (2, 1)], rooms)
        self.assertEqual(res[0], [[0], [2], [0], [0]])

    def test_vertex_in_the_middle_of_an_edge(self):
        # room 1 is two metres long, rooms 2 and 3 above it meet at (1, 1), which is not a vertex of room 1
        vertices = [(0, 0), (2, 0), (2, 1), (0, 1), (1, 1), (0, 2), (1, 2), (2, 2)]
        rooms = [[1, 2, 3, 4], [4, 5, 7, 6], [5, 3, 8, 7]]
        res = neighbours(vertices, rooms)
        self.assertEqual(res[0][2], [3, 2])  # across 3-4 both rooms, as long: the first one is the neighbour
        self.assertEqual(res[1][0], [1])
        self.assertEqual(res[2][0], [1])

    def test_corners_a_few_cm_apart(self):
        # the corners of the two rooms are 6 cm apart, farther than the vertices merged when deduplicating
        vertices = [(0, 0), (1, 0), (1, 1), (0, 1), (1.06, 0), (2, 0), (2, 1), (1.06, 1)]
        res = neighbours(vertices, [[1, 2, 3, 4], [5, 6, 7, 8]])
        self.assertEqual(res[0][1], [2])
        self.assertEqual(res[1][3], [1])

    def test_crack_thinner_than_the_spikes(self):
        # room 3 goes along the ends of rooms 1 and 2, with a 9 cm crack between them that leads to no room: it is
        # given to the room of its start, so that a car crossing it isn't lost
        vertices = [(0, 0), (1, 0), (1, 1), (0, 1), (1.09, 0), (2, 0), (2, 1), (1.09, 1), (0, -1), (2, -1)]
        res = neighbours(vertices, [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 6, 5, 2, 1]])
        self.assertEqual(res[2][3], [2])  # 5 to 2, the crack
        self.assertEqual(res[2][2], [2])  # 6 to 5, along room 2
        self.assertEqual(res[2][4], [1])  # 2 to 1, along room 1
        self.assertEqual(res[2][0], [0])  # 9 to 10, out of the city

    def test_long_edge_out_of_the_city(self):
        # an edge longer than the cracks whose start touches another room still leads out of the city
        rooms = [[1, 2, 5, 4], [2, 3, 6, 5]]
        res = neighbours([(x, y) for y in range(2) for x in range(3)], rooms)
        self.assertEqual(res[0][2], [0])  # 5 to 4 (5 is a vertex of room 2)
        self.assertEqual(res[1][3], [1])  # 5 to 2 is room 1's edge 2-5


if __name__ == '__main__':
    unittest.main()
