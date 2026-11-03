"""Regenerate the core's smooth glyph meshes from its bundled OFL font.

Development only: fonttools, shapely, mapbox-earcut and numpy. No runtime dependency on these tools.
The generated outline data is OFL font software; see fonts/LICENSE.
"""
from pathlib import Path
import math

from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
import mapbox_earcut
import numpy as np
from shapely import make_valid
from shapely.geometry import Polygon, GeometryCollection

CORE = Path(__file__).resolve().parents[1]
FONT = CORE / 'fonts/LiberationSans-Bold.ttf'
OUT = CORE / 'lua/map_label_font.lua'


class Flatten(BasePen):
    def __init__(self, glyph_set, tolerance):
        super().__init__(glyph_set)
        self.tolerance = tolerance
        self.contours = []
        self.current = []

    def _moveTo(self, point):
        self.current = [point]

    def _lineTo(self, point):
        self.current.append(point)

    def _closePath(self):
        if len(self.current) > 2:
            self.contours.append(self.current)
        self.current = []

    _endPath = _closePath

    def _qCurveToOne(self, control, end):
        start = self.current[-1]
        length = math.dist(start, control) + math.dist(control, end)
        steps = max(2, math.ceil(math.sqrt(length / self.tolerance)))
        for i in range(1, steps + 1):
            t = i / steps
            self.current.append(tuple((1-t)**2*start[a] + 2*(1-t)*t*control[a] + t*t*end[a] for a in (0, 1)))

    def _curveToOne(self, a, b, end):
        start = self.current[-1]
        length = math.dist(start, a) + math.dist(a, b) + math.dist(b, end)
        steps = max(3, math.ceil(math.sqrt(length / self.tolerance)))
        for i in range(1, steps + 1):
            t = i / steps
            self.current.append(tuple((1-t)**3*start[k]+3*(1-t)**2*t*a[k]+3*(1-t)*t*t*b[k]+t**3*end[k] for k in (0, 1)))


def polygons(shape):
    if shape.geom_type == 'Polygon':
        yield shape
    elif hasattr(shape, 'geoms'):
        for child in shape.geoms:
            yield from polygons(child)


def mesh(shape, units):
    vertices, triangles = [], []
    for poly in polygons(shape):
        rings = [list(poly.exterior.coords)[:-1]] + [list(r.coords)[:-1] for r in poly.interiors]
        coords = np.array([point for ring in rings for point in ring], dtype=np.float64)
        ends = np.cumsum([len(r) for r in rings], dtype=np.uint32)
        indices = mapbox_earcut.triangulate_float64(coords, ends)
        for i in range(0, len(indices), 3):
            a, b, c = (coords[indices[i+k]] for k in (0, 1, 2))
            if (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]) > 0:
                indices[i+1], indices[i+2] = indices[i+2], indices[i+1]
        offset = len(vertices) // 2
        vertices.extend(float(n) / units for point in coords for n in point)
        triangles.extend(int(n) + offset for n in indices)
    return vertices, triangles


def number(value):
    return format(value, '.6f').rstrip('0').rstrip('.') or '0'


def generate():
    font = TTFont(FONT)
    units = font['head'].unitsPerEm
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    # Latin, Latin Extended A and common punctuation. Unknown characters use the font's missing-glyph box.
    codes = [0] + [n for n in range(32, 384) if n in cmap] + [n for n in range(0x2000, 0x2070) if n in cmap]
    by_name = {}
    for code in codes:
        by_name.setdefault(cmap.get(code, '.notdef'), []).append(code)
    lines = ['-- KM2 Map Labels: generated outline data, licensed under SIL OFL 1.1 (../fonts/LICENSE).',
             '-- Source: unmodified Liberation Sans Bold 2.1.5. Regenerate with tools/_generate_map_label_font.py.',
             'local F = { glyphs = {}, upper = {}, kern = {} }']
    for code in codes:
        name = cmap.get(code, '.notdef')
        pen = Flatten(glyph_set, units / 512)
        glyph_set[name].draw(pen)
        shape = GeometryCollection()
        for contour in pen.contours:
            shape = make_valid(shape.symmetric_difference(make_valid(Polygon(contour))))
        vertices, triangles = mesh(shape, units)
        advance = font['hmtx'][name][0] / units
        lines.append(f'F.glyphs[{code}]=' + '{a=' + number(advance) + ',v={' + ','.join(map(number, vertices)) + '},t={' + ','.join(map(str, triangles)) + '}}')
        upper = [ord(c) for c in chr(code).upper()]
        if upper != [code]:
            lines.append(f'F.upper[{code}]={{{",".join(map(str, upper))}}}')
    for table in font['kern'].kernTables if 'kern' in font else []:
        for (left, right), value in sorted(table.kernTable.items()):
            for a in by_name.get(left, []):
                for b in by_name.get(right, []):
                    lines.append(f'F.kern["{a}:{b}"]={number(value / units)}')
    lines.append('return F')
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'{len(codes)} glyphs, {OUT.stat().st_size} bytes: {OUT}')


if __name__ == '__main__':
    generate()
