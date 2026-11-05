"""Small synthetic checks of the bridge model generator (converters/generateBridgeMesh); no original game assets."""
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python'), str(CORE / 'server')]
import custom_element_conversion as cec
import mesh_formats
from bridge_export import export_bridges

spec = importlib.util.spec_from_file_location('bridge_mesh', CORE / 'converters/generateBridgeMesh/convert.py')
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

# as the road of giz_bridge01_l
ROAD = dict(isDouble=True, hasSidewalks=True, totalWidth=18.0, roadWidth=8.0, texture0='texture/walk.tex', texture1='texture/road.tex', textureLOD='texture/road_lo.tex')
TEXTURES = ('truss', 'plate', 'rail')


def read_pkg(path):
    objects, materials = [], []
    f = mesh_formats.BinaryFileHelper(str(path), 'rb')
    header = f.read_bytes(4)
    length = os.path.getsize(path)
    while not mesh_formats.reached_end(f, length):
        mesh_formats.read_pkg_file(f, header, materials, objects)
    f.close()
    return {o['name']: o for o in objects}, [m['name'] for m in materials]


def bounds(part):
    return [(round(min(v[i] for v in part['vertices']), 3), round(max(v[i] for v in part['vertices']), 3)) for i in range(3)]


def road(identity, **state):
    return dict(id=identity, data=dict(name='Road', fields=dict(state=dict(ROAD, **state))))


def anchored(position, road_id=None, direction=(0, 0, 1)):
    point = dict(id=1, position=list(position))
    if road_id is not None:
        point['anchor'] = dict(kind='road', id=road_id, index=0, roadEnd=True, insideDirection=list(direction))
    return point


def bridge_element(start, finish, **state):
    return dict(id=5, type='bridge', data=dict(name='Bridge', fields=dict(state=dict(dict(paired=True), **state))), points=dict(start=start, finish=finish))


class Generator(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def model(self, state=ROAD, length=30.0, angle=0.0, textures=TEXTURES):
        path = gen.write_model(self.folder.name, state, *textures, length, angle)
        return path, Path(self.folder.name)

    def test_the_stock_proportions(self):
        path, city = self.model()
        parts, shaders = read_pkg(city / path)
        self.assertEqual(sorted(parts), ['H', 'L', 'M', 'VL'])
        # giz_bridge01_l: 18.5 wide, 30 long, from -1.5 to 1.8 with the railings; the mirrored X of the reader doesn't matter
        self.assertEqual(bounds(parts['H']), [(-9.25, 9.25), (-1.5, 1.8), (-15.0, 15.0)])
        self.assertEqual(bounds(parts['VL'])[1], (-1.5, 0.3))
        self.assertEqual(set(shaders), {'rail', 'plate', 'walk', 'road', 'truss', 'road_lo'})
        self.assertEqual(shaders[-2:], ['truss', 'road_lo'], 'the textures with a cutout after the others, then the one only in the last part')

    def test_the_levels_of_the_road(self):
        strips, half, edge = gen.road_profile(ROAD)
        self.assertEqual((half, edge), (9.0, 0.0), 'the sidewalks at the height of the curve of the road')
        self.assertEqual(sorted({s.y0 for s in strips}), [-0.15, 0.0], 'and the road 0.15 below it')
        road_strips = [s for s in strips if s.texture == 'road']
        self.assertEqual([(s.s0, s.s1, s.v0, s.v1) for s in road_strips], [(-4.0, 0.0, 1, 0), (0.0, 4.0, 0, 1)], 'the center in the top row of the texture')
        self.assertEqual(gen.road_profile(dict(ROAD, flatSidewalk=True))[2], 0.0)
        self.assertEqual(gen.road_profile(dict(ROAD, flatSidewalk=True, applyHeightAnyway=True))[2], -0.15)
        strips, half, edge = gen.road_profile(dict(ROAD, isDouble=False, hasSidewalks=False, totalWidth=7.0))
        self.assertEqual(([(s.s0, s.s1, s.v0, s.v1) for s in strips], half, edge), ([(-3.5, 3.5, 1, 0)], 3.5, 0.0))

    def test_dividers(self):
        for divider, count, top in ((1, 1, -0.15), (2, 5, 0.35), (3, 3, 0.85)):
            strips, _, _ = gen.road_profile(dict(ROAD, divider=divider, dividerWidth=2.0, dividerParam=0.5, texture2='texture/d2.tex', texture3='texture/d3.tex', texture4='texture/d4.tex'))
            middle = [s for s in strips if s.texture.startswith('d')]
            self.assertEqual(len(middle), count)
            self.assertAlmostEqual(max(s.y1 for s in middle), top)
            self.assertEqual((middle[0].s0, middle[-1].s1), (-1.0, 1.0))
        self.assertEqual(gen.road_profile(dict(ROAD, divider=1, dividerWidth=2.0))[0][3].texture, 'road', 'without its texture, the one of the road')

    def test_the_faces_are_visible_from_the_outside(self):
        leaf = gen.Leaf(30.0, 0.0)
        mesh = gen.Mesh()
        strips, _, _ = gen.road_profile(ROAD)
        for strip in strips:
            leaf.strip(mesh, strip)
        for section in mesh.sections.values():
            for position, normal, _ in section['vertices']:
                self.assertGreaterEqual(normal[1], 0, 'the top of the road faces up')
        # the curbs of the road face the road
        walls = [v for v in mesh.sections['walk']['vertices'] if abs(v[1][0]) > 0.5]
        self.assertTrue(walls and all(v[1][0] * v[0][0] < 0 for v in walls))
        below, ends = gen.Mesh(), gen.Mesh()
        leaf.under(below, 'x', 9.25, -1.8, 5.0, 4.625)
        self.assertLess(below.sections['x']['vertices'][0][1][1], 0)
        leaf.end_faces(ends, 'x', [(-9.25, 0.0), (9.25, 0.0)], 9.25)
        for position, normal, _ in ends.sections['x']['vertices']:
            self.assertGreater(normal[2] * position[2], 0)

    def test_the_texture_coordinates_of_the_stock_ends(self):
        leaf, ends = gen.Leaf(30.0, 0.0), gen.Mesh()
        leaf.end_faces(ends, 'x', [(-9.25, 0.0), (9.25, 0.0)], 9.25)
        uvs = ends.sections['x']['vertices']
        self.assertEqual(sorted({round(v[2][1], 3) for v in uvs}), [0.001, 0.999])
        self.assertEqual(sorted({round(v[2][0], 3) for v in uvs}), [0, 5])

    def test_a_road_at_an_angle(self):
        # the road goes 45 degrees from the bridge: the end of the road is across it
        angle = gen.road_angle((1, 0, 1), (0, 0, 0), (0, 0, 60))
        self.assertAlmostEqual(abs(angle), math.pi / 4, places=4)
        self.assertAlmostEqual(angle, gen.road_angle((-1, 0, -1), (0, 0, 0), (0, 0, 60)), msg='either way along the road')
        self.assertAlmostEqual(gen.road_angle((0, 0, 1), (0, 0, 0), (0, 0, 60)), 0)
        self.assertAlmostEqual(gen.road_angle((1, 0, 0), (0, 0, 0), (60, 0, 0)), 0)
        self.assertAlmostEqual(gen.road_angle((-1, 0, 1), (0, 0, 0), (0, 0, 60)), -angle, msg='the other side')
        path, city = self.model(length=30.0, angle=math.pi / 4)
        parts, _ = read_pkg(city / path)
        x, _, z = bounds(parts['H'])
        half = 9.25 * math.sin(math.pi / 4)
        self.assertAlmostEqual(z[1], 15 + half, places=2)
        self.assertAlmostEqual(x[1], half, places=2)
        tuning = (city / 'tune/banger' / (Path(path).stem + '.dgBangerData')).read_text()
        self.assertIn('Size ' + format(2 * half, 'f')[:6], tuning)
        self.assertIn('\t30.000000', tuning, 'the distance of its ends, not of the bounds')

    def test_the_model_turned_by_180_degrees_fits_itself(self):
        # the tips of the two leaves of a pair are along the same line
        leaf = gen.Leaf(30.0, 0.5)
        hinge_distance = 60.0
        for s in (-9.0, 3.0):
            tip = leaf.at(s, 0, -1)
            # the world along the bridge, with the leaf at the hinge at +30 and the other one turned
            world = (tip[0], tip[2] - 15.0 + hinge_distance / 2)
            other_tip = leaf.at(-s, 0, -1)
            other = (-other_tip[0], -(other_tip[2] - 15.0 + hinge_distance / 2))
            self.assertAlmostEqual(world[0], other[0], places=5)
            self.assertAlmostEqual(world[1], other[1], places=5)

    def test_the_files(self):
        path, city = self.model()
        name = Path(path).stem
        self.assertTrue(name.startswith('bridge_'))
        self.assertLessEqual(len('inactive:' + name), 32)
        self.assertEqual(self.model()[0], path, 'the same model has the same name')
        self.assertNotEqual(self.model(length=20.0)[0], path)
        self.assertNotEqual(self.model(textures=('other', 'plate', 'rail'))[0], path)
        bnd = (city / 'bound' / (name + '_BOUND.bnd')).read_text()
        self.assertIn('version: 1.01', bnd)
        self.assertIn('tri 0 ', bnd)
        polys = int(next(line for line in bnd.splitlines() if line.startswith('polys:')).split()[1])
        self.assertGreater(polys, 30)
        heights = {round(float(line.split()[2]), 3) for line in bnd.splitlines() if line.startswith('v\t')}
        self.assertEqual(heights, {-1.5, 0.15, 0.3, 1.8}, 'the road, the sidewalks, the railings and the bottom')
        tuning = (city / 'tune/banger' / (name + '.dgBangerData')).read_text()
        self.assertIn('Size 18.500000\t3.300000\t30.000000', tuning)
        self.assertIn('CG 0.000000', tuning)

    def data(self, element, *roads):
        return dict(convert=[dict(kind='customElement', id=element['id'])], customElements=[element], roads=list(roads), cityFolder=self.folder.name)

    def test_the_conversion(self):
        element = bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80), 2), trussTexture='texture/my_truss.tex')
        out, replace = gen.convert(self.data(element, road(1), road(2, totalWidth=24.0)))
        self.assertFalse(replace)
        update = out.updates[0]
        self.assertEqual(update['element'], dict(kind='customElement', id=5))
        state = update['state']
        self.assertEqual(state['mesh'], state['generatedMesh'])
        self.assertEqual(state['generatedLength'], 40.0)
        parts, shaders = read_pkg(Path(self.folder.name) / state['mesh'])
        self.assertIn('my_truss', shaders)
        self.assertEqual(bounds(parts['H'])[0], (-12.25, 12.25), 'the widest road')
        self.assertEqual(bounds(parts['H'])[2], (-20.0, 20.0))
        single = bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80)), paired=False)
        state = gen.convert(self.data(single, road(1)))[0].updates[0]['state']
        self.assertEqual(state['generatedLength'], 80.0, 'one leaf covers all of it; one road is enough')
        parts, shaders = read_pkg(Path(self.folder.name) / state['mesh'])
        self.assertIn('tl_bridgetruss_side_l', shaders, 'the stock textures by default')

    def test_the_refusals(self):
        def error(element, *roads):
            with self.assertRaises(cec.ConversionError) as context:
                gen.convert(self.data(element, *roads))
            return str(context.exception)
        self.assertEqual(error(bridge_element(anchored((0, 0, 0)), anchored((0, 0, 80)))), 'BRIDGE_MESH_ERROR_NO_ROADS')
        self.assertEqual(error(bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 1))), road(1)), 'BRIDGE_MESH_ERROR_LENGTH')
        self.assertEqual(error(bridge_element(anchored((0, 0, 0), 1, (1, 0, 0)), anchored((0, 0, 80))), road(1)), 'BRIDGE_MESH_ERROR_ANGLE')
        self.assertEqual(error(bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80))), road(1, roadWidth=30.0)), 'BRIDGE_MESH_ERROR_WIDTHS')

    def test_the_export(self):
        element = bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80), 1))
        state = gen.convert(self.data(element, road(1)))[0].updates[0]['state']
        element['data']['fields']['state'].update(state)
        name = Path(state['mesh']).stem
        with tempfile.TemporaryDirectory() as out:
            root = Path(out)
            folder = root / 'race' / 'x'
            folder.mkdir(parents=True)
            data = dict(customElements=[element], cityFolder=self.folder.name, cityProperties={})
            export_bridges(data, str(folder), 'x', None)
            for file in ('geometry/' + name + '.pkg', 'bound/' + name + '_BOUND.bnd', 'tune/banger/' + name + '.dgBangerData'):
                self.assertTrue((root / file).exists(), file)
            self.assertIn(b'time:' + name.encode(), (folder / 'x_bridge.pathset').read_bytes())
            self.assertFalse((root / 'tune/banger/.km2-bridge-tuning.json').exists(), 'the tuning of the city, not a generated one')
            # again, to the folder of the city
            inside = Path(self.folder.name) / 'race' / 'x'
            inside.mkdir(parents=True)
            export_bridges(dict(data), str(inside), 'x', None)
            self.assertTrue((inside / 'x_bridge.pathset').exists())


class Staleness(unittest.TestCase):
    def test_a_warning_when_the_hinges_moved(self):
        from unittest.mock import patch
        from bridge_export import get_bridges
        element = bridge_element(anchored((0, 0, 0)), anchored((0, 0, 80)), mesh='geometry/bridge_x.pkg', generatedMesh='geometry/bridge_x.pkg', generatedLength=40.0)
        with patch('bridge_export.report.warning') as warning:
            get_bridges(dict(customElements=[element], cityProperties={}))
            warning.assert_not_called()
            element['points']['finish']['position'] = [0, 0, 90]
            get_bridges(dict(customElements=[element], cityProperties={}))
            self.assertIn('generated for another distance', warning.call_args[0][0])
            warning.reset_mock()
            element['data']['fields']['state']['mesh'] = 'geometry/other.pkg'
            get_bridges(dict(customElements=[element], cityProperties={}))
            warning.assert_not_called()


if __name__ == '__main__':
    unittest.main()
