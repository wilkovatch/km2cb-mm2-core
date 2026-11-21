"""Bounded synthetic checks of the walk along the boundary of a room (PSDLWriter.walk_perimeter), no stock data."""
from pathlib import Path
import sys
import unittest

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python')]
from scene import Mesh
from writers.psdl_writer import PSDLWriter


def walk(vertices, triangles):
    # vertices: (x, y) positions seen from above (z up); triangles: counterclockwise
    writer = PSDLWriter(None, 'x.psdl', False, False)
    mesh = Mesh([(x, y, 0.0) for x, y in vertices], [i for t in triangles for i in t])
    maxx = max(x for x, _ in vertices)
    return writer.walk_perimeter(mesh, [i for i, (x, _) in enumerate(vertices) if abs(x - maxx) < 0.1], 'test')


# a fan around B whose boundary goes from A down to B and back up to C, on the same line (as a road end line between
# an intersection surface and a sidewalk): A, W, S, E, C around B; vertex 0 is not used, as in the cities a vertex
# that isn't on the boundary
B, A, W, S, E, C = 1, 2, 3, 4, 5, 6
VERTICES = [(-10, -10), (0, 0), (0, 5), (-3, 0), (0, -3), (3, 0), (0, 5.8)]
FAN = [(B, A, W), (B, W, S), (B, S, E), (B, E, C)]


class Walk(unittest.TestCase):
    def test_square(self):
        self.assertEqual(sorted(walk([(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 1, 2), (0, 2, 3)])), [0, 1, 2, 3])

    def test_slit(self):
        res = walk(VERTICES, FAN)
        self.assertEqual(sorted(res), [B, A, W, S, E, C])
        self.assertEqual(res[(res.index(A) + 1) % len(res)], B)  # A, B, C
        self.assertEqual(res[(res.index(B) + 1) % len(res)], C)

    def test_slit_with_a_face_without_area(self):
        # the sliver A, B, C along the slit has no area seen from above: it isn't part of the boundary, and its edge
        # A-B doesn't make A a way on from B (both go back along the same line, the walk used to jump to vertex 0)
        self.assertEqual(walk(VERTICES, FAN + [(A, B, C)]), walk(VERTICES, FAN))


if __name__ == '__main__':
    unittest.main()
