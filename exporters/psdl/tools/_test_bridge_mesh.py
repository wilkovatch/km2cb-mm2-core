"""Small synthetic checks of the bridge model generator (generated/bridge_mesh.py) and of its export; no original game assets."""
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python'), str(CORE / 'server')]
import mesh_formats
from bridge_export import export_bridges, get_bridges
from generated import bridge_mesh as gen, OutputRoot, GenerationError
from generated_export import GeneratedExport, MANIFEST

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
        path = gen.write_model(OutputRoot(self.folder.name), state, *textures, length, angle)
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
        return dict(customElements=[element], roads=list(roads), cityFolder=self.folder.name, cityProperties={})

    def generate(self, element, *roads):
        return gen.generate(element, self.data(element, *roads), OutputRoot(self.folder.name), [self.folder.name])

    def test_the_generation(self):
        element = bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80), 2), trussTexture='texture/my_truss.tex')
        path, length = self.generate(element, road(1), road(2, totalWidth=24.0))
        self.assertEqual(length, 40.0)
        parts, shaders = read_pkg(Path(self.folder.name) / path)
        self.assertIn('my_truss', shaders)
        self.assertEqual(bounds(parts['H'])[0], (-12.25, 12.25), 'the widest road')
        self.assertEqual(bounds(parts['H'])[2], (-20.0, 20.0))
        single = bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80)), paired=False)
        path, length = self.generate(single, road(1))
        self.assertEqual(length, 80.0, 'one leaf covers all of it; one road is enough')
        parts, shaders = read_pkg(Path(self.folder.name) / path)
        self.assertIn('tl_bridgetruss_side_l', shaders, 'the stock textures by default')

    def test_the_generated_low_lod_texture_of_the_road(self):
        # the VL part has the low LOD texture generated for the road, written with the model
        from PIL import Image
        texture = Path(self.folder.name) / 'texture'
        texture.mkdir()
        for name, color in (('road', (10, 20, 30)), ('walk', (200, 200, 180))):
            Image.new('RGB', (8, 8), color).save(texture / (name + '.png'))
        lod_road = road(1, texture0='texture/walk.png', texture1='texture/road.png', generateLodTexture=True)
        element = bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80)))
        out = OutputRoot(Path(self.folder.name) / 'out')
        path, _ = gen.generate(element, self.data(element, lod_road), out, [self.folder.name])
        lod = next(f for f in out.files if f.startswith('texture/'))
        self.assertTrue(Path(lod).stem.startswith('road_lod_'))
        self.assertIn(Path(lod).stem, read_pkg(Path(out.root) / path)[1])
        # when it can't be made, the VL part has the textures of the top
        missing = road(1, texture0='texture/none.png', texture1='texture/road.png', generateLodTexture=True)
        path, _ = gen.generate(element, self.data(element, missing), out, [self.folder.name])
        self.assertFalse(any('_lod_' in shader for shader in read_pkg(Path(out.root) / path)[1]))

    def test_the_refusals(self):
        def error(element, *roads):
            with self.assertRaises(GenerationError) as context:
                self.generate(element, *roads)
            return str(context.exception)
        self.assertEqual(error(bridge_element(anchored((0, 0, 0)), anchored((0, 0, 80)))), 'BRIDGE_MESH_ERROR_NO_ROADS')
        self.assertEqual(error(bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 1))), road(1)), 'BRIDGE_MESH_ERROR_LENGTH')
        self.assertEqual(error(bridge_element(anchored((0, 0, 0), 1, (1, 0, 0)), anchored((0, 0, 80))), road(1)), 'BRIDGE_MESH_ERROR_ANGLE')
        self.assertEqual(error(bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80))), road(1, roadWidth=30.0)), 'BRIDGE_MESH_ERROR_WIDTHS')

    def export(self, root, element, *roads):
        # as export.py: the generated files first, the bridges, then the list of the generated files
        folder = root / 'race' / 'x'
        folder.mkdir(parents=True, exist_ok=True)
        data = self.data(element, *roads)
        generated = GeneratedExport(root, data, None)
        generated.lod_textures()
        generated.bridge_models()
        export_bridges(data, str(folder), 'x', None)
        generated.finish()
        return element['data']['fields']['state'].get('mesh'), folder

    def test_the_export(self):
        element = bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80), 1), generateMesh=True, mesh='geometry/chosen.pkg')
        with tempfile.TemporaryDirectory() as out:
            root = Path(out)
            mesh, folder = self.export(root, element, road(1))
            name = Path(mesh).stem
            self.assertTrue(name.startswith('bridge_'), 'the generated model, not the one chosen')
            files = ['bound/' + name + '_BOUND.bnd', 'geometry/' + name + '.pkg', 'tune/banger/' + name + '.dgBangerData']
            for file in files:
                self.assertTrue((root / file).exists(), file)
            self.assertIn(b'time:' + name.encode(), (folder / 'x_bridge.pathset').read_bytes())
            self.assertEqual(json.loads((root / MANIFEST).read_text()), files)
            self.assertFalse((root / 'tune/banger/.km2-bridge-tuning.json').exists(), 'its banger data is a generated file')
            self.assertEqual(list(Path(self.folder.name).iterdir()), [], 'nothing in the folder of the city')
            # a file that was there before is never removed
            (root / 'geometry' / 'bridge_00000000.pkg').write_bytes(b'mine')
            # the hinges moved: a new model, and the files of the old one are removed
            element['points']['finish']['position'] = [0, 0, 90]
            element['data']['fields']['state']['mesh'] = ''
            second, _ = self.export(root, element, road(1))
            self.assertNotEqual(second, mesh)
            for file in files:
                self.assertFalse((root / file).exists(), file)
            self.assertTrue((root / second).exists())
            self.assertTrue((root / 'geometry' / 'bridge_00000000.pkg').exists())

    def test_the_generator_of_the_editor(self):
        # generators/bridgeMesh, as the program runs it: the values for each element, the errors as string keys
        import subprocess
        good = bridge_element(anchored((0, 0, 0), 1), anchored((0, 0, 80), 1), generateMesh=True)
        bad = dict(bridge_element(anchored((0, 0, 0)), anchored((0, 0, 80)), generateMesh=True), id=6)
        cache = Path(self.folder.name) / 'cache'
        data = dict(self.data(good, road(1)), customElements=[good, bad], outputFolder=str(cache),
                    generate=[dict(kind='customElement', id=5), dict(kind='customElement', id=6), dict(kind='customElement', id=7)])
        source, output = Path(self.folder.name) / 'input.json', Path(self.folder.name) / 'output.json'
        source.write_text(json.dumps(data))
        subprocess.run([sys.executable, str(CORE / 'generators/bridgeMesh/generate.py'), str(CORE.parents[1] / 'python'), str(source), str(output)], check=True)
        results = json.loads(output.read_text())['results']
        self.assertEqual([r['element']['id'] for r in results], [5, 6, 7])
        values = results[0]['values']
        self.assertTrue(Path(values['mesh']).is_absolute() and Path(values['mesh']).is_file())
        self.assertEqual(Path(values['mesh']).parent, cache / 'geometry')
        self.assertEqual(values['length'], 40.0)
        self.assertEqual([r.get('error') for r in results[1:]], ['BRIDGE_MESH_ERROR_NO_ROADS', 'GENERATION_ERROR_MISSING'])

    def test_a_bridge_without_its_model_is_not_exported(self):
        with patch('bridge_export.report.error') as error:
            element = bridge_element(anchored((0, 0, 0)), anchored((0, 0, 80)), generateMesh=True)
            with tempfile.TemporaryDirectory() as out:
                self.export(Path(out), element)
            self.assertIn('Attach a control of the bridge', error.call_args[0][0], 'the reason, as the string of the core')
            error.reset_mock()
            # not generated at all (get_bridges without the generation before it)
            self.assertEqual(get_bridges(dict(customElements=[bridge_element(anchored((0, 0, 0)), anchored((0, 0, 80)), generateMesh=True)])), [])
            self.assertIn('not generated', error.call_args[0][0])

if __name__ == '__main__':
    unittest.main()
