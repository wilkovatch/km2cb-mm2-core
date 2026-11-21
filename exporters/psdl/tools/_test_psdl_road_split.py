"""Bounded synthetic checks of the split of the non-coplanar road quads (psdl_splitNonCoplanarRoads), no stock data.

The PSDL writer splits a road strip (ROADS, ROADN, ROADSN) at each quad whose four road vertices are not coplanar: the
strip before it, the quad as two triangles, the strip after it. Each other quad must be written once, and the
non-coplanar ones never as a quad."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python')]
from writers.psdl_writer import PSDLWriter, BlockFlag

WIDTH = {'ROADS': 4, 'ROADSN': 2, 'ROADN': 2}  # vertices of a section
ROAD = {'ROADS': (1, 2), 'ROADSN': (0, 1), 'ROADN': (0, 1)}  # the road vertices of a section, checked for coplanarity


def road(typ, n_sections, twisted):
    # the vertices of a straight road along y (1 m sections), with the last road vertex of the sections in twisted raised
    width = WIDTH[typ]
    vertices = []
    for s in range(n_sections):
        for k in range(width):
            z = 1.0 if s in twisted and k == ROAD[typ][1] else 0.0
            vertices.append((float(k), float(s), z))
    return vertices


def written_strips(typ, vertices):
    # the strips written for the part, as lists of sections (tuples of vertex indices from 0)
    writer = PSDLWriter(None, 'x.psdl', True, False)
    writer.initialize_variables()
    writer.block_flags = [BlockFlag()]
    writer.temp_shorts_list = []
    writer.get_vert_index = lambda pos: vertices.index(tuple(pos)) + 1
    writer.add_prop_rule = lambda bi, bp: None
    part = SimpleNamespace(geo=SimpleNamespace(type=typ, vertices=vertices, properties={}))
    if typ == 'ROADS':
        writer.process_part_roads(None, 0, part, 0, 1)
    else:
        writer.process_part_roadsn_roadn(None, 0, part, 0, 1)
    words = writer.temp_shorts_list
    per_vertex = 2 if typ == 'ROADSN' else 1  # ROADSN writes each vertex twice
    width = 2 if typ != 'ROADS' else 4
    strips = []
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        count = word & 7
        if count == 0:
            count = words[i]
            i += 1
        indices = words[i:i + count * width * per_vertex:per_vertex]
        i += count * width * per_vertex
        strips.append([tuple(v - 1 for v in indices[k:k + width]) for k in range(0, len(indices), width)])
        if word & 0x80:
            break
    return strips


def quads(strips):
    # the quads of the strips: pairs of consecutive sections
    return [(s[k], s[k + 1]) for s in strips for k in range(len(s) - 1)]


class RoadSplit(unittest.TestCase):
    def check(self, typ, n_sections, twisted):
        vertices = road(typ, n_sections, twisted)
        width = WIDTH[typ]
        sections = [tuple(range(s * width, (s + 1) * width)) for s in range(n_sections)]
        written = quads(written_strips(typ, vertices))
        for s in range(n_sections - 1):
            # a raised vertex makes the quads before and after it non-coplanar
            flat = s not in twisted and s + 1 not in twisted
            self.assertEqual(written.count((sections[s], sections[s + 1])), 1 if flat else 0,
                             '%s, %d sections, raised %s: quad %d' % (typ, n_sections, sorted(twisted), s))

    def test_flat_road_is_one_strip(self):
        for typ in WIDTH:
            vertices = road(typ, 5, set())
            self.assertEqual(len(written_strips(typ, vertices)), 1)

    def test_every_position(self):
        # a raised section anywhere, the last one included (past the middle of the road the first strip took more
        # sections than the road had: IndexError until 2026-11-21, before it, sections written twice)
        for typ in WIDTH:
            for n in (3, 4, 7):
                for s in range(n):
                    self.check(typ, n, {s})

    def test_two_raised_sections(self):
        for typ in WIDTH:
            self.check(typ, 8, {2, 5})
            self.check(typ, 8, {1, 6})


if __name__ == '__main__':
    unittest.main()
