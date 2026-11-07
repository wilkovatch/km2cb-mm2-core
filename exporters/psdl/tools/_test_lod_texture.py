"""Small synthetic checks of the low LOD texture generator (generated/lod_texture.py) and of its export."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

CORE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(CORE / 'exporters/psdl'))

from generated import lod_texture as lod, OutputRoot, GenerationError
from generated_export import GeneratedExport, MANIFEST

ROAD = (10, 20, 30)
CENTER = (250, 220, 0)
SIDEWALK = (200, 200, 180)
DIVIDER = (0, 150, 0)


def road_image(color=ROAD):
    # a road texture: the color of the road, with the center line in its bottom row
    image = np.full((32, 32, 3), color, np.uint8)
    image[-1] = CENTER
    return image


def read_tex(path):
    data = Path(path).read_bytes()
    width, height, typ, mips = struct.unpack_from('<4H', data, 0)
    assert typ == 17
    return width, height, mips, np.frombuffer(data, np.uint8, width * height * 3, 14).reshape(height, width, 3)


class LodTexture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        (self.folder / 'city').mkdir()
        (self.folder / 'common' / 'Texture').mkdir(parents=True)
        Image.fromarray(road_image()).save(self.folder / 'common' / 'Texture' / 'Road.png')
        Image.fromarray(np.full((8, 8, 3), SIDEWALK, np.uint8)).save(self.folder / 'common' / 'Texture' / 'walk.png')
        Image.fromarray(np.full((8, 8, 3), DIVIDER, np.uint8)).save(self.folder / 'common' / 'Texture' / 'grass.png')
        self.state = {'isDouble': True, 'hasSidewalks': True, 'flatSidewalk': False, 'totalWidth': 40.0, 'roadWidth': 30.0,
                      'divider': 0, 'texture0': 'texture/walk.png', 'texture1': 'texture/road.png'}

    def tearDown(self):
        self.tmp.cleanup()

    def folders(self):
        return [str(self.folder / 'city'), str(self.folder / 'common')]

    def generate(self):
        # in the folder of an export (each time a new one, which computes it again)
        return lod.generate(self.state, OutputRoot(self.folder / 'out'), self.folders())

    def image(self):
        # the texture written, from its top row
        return read_tex(self.folder / 'out' / self.generate())[3][::-1]

    def test_bands_in_proportion_and_mirrored(self):
        pixels = self.image()
        self.assertEqual(pixels.shape, (64, 64, 3))
        self.assertTrue((pixels == pixels[::-1]).all())
        column = pixels[:, 0]
        # 40 m: 5 m of sidewalk are 8 pixels, the center line is between the two halves of the road
        self.assertTrue((column[:8] == SIDEWALK).all())
        self.assertTrue((column[9:30] == ROAD).all())
        self.assertGreater(column[31][0], column[29][0])
        self.assertTrue((column[56:] == SIDEWALK).all())

    def test_format_as_the_stock_ones(self):
        path = self.folder / 'out' / self.generate()
        self.assertEqual(read_tex(path)[:3], (64, 64, 1))
        self.assertEqual(path.parent.name, 'texture')

    def test_widths_change_the_texture(self):
        first = self.generate()
        self.assertEqual(first, self.generate())
        self.state['totalWidth'] = 46.0
        second = self.generate()
        self.assertNotEqual(first, second)
        self.assertLessEqual(len(Path(second).stem) + len('_fa'), 31)
        pixels = read_tex(self.folder / 'out' / second)[3]
        # 8 of 46 m of sidewalk are about 11 pixels instead of 8
        self.assertTrue((pixels[:10, 0] == SIDEWALK).all())

    def test_tiles_are_whole(self):
        self.state['texture1'] = 'texture/dashes.png'
        dashes = np.zeros((16, 16, 3), np.uint8)
        dashes[:, :8] = 255
        Image.fromarray(dashes).save(self.folder / 'common' / 'Texture' / 'dashes.png')
        self.state['roadWidth'] = 20.0
        self.state['totalWidth'] = 30.0
        row = self.image()[20, :, 0].astype(float)
        # 30 m with tiles of 10 m: three tiles along the texture
        self.assertEqual(np.abs(np.fft.rfft(row - row.mean())).argmax(), 3)
        # 32 m would be 3.2 tiles, it stays three whole ones so that the texture repeats without a seam
        self.state['totalWidth'] = 32.0
        row = self.image()[20, :, 0].astype(float)
        self.assertEqual(np.abs(np.fft.rfft(row - row.mean())).argmax(), 3)

    def test_flat_divider(self):
        self.state.update({'divider': 1, 'dividerWidth': 10.0, 'dividerParam': 2.0, 'texture3': 'texture/grass.png'})
        column = self.image()[:, 0]
        # 10 of 40 m in the middle
        self.assertTrue((column[25:39] == DIVIDER).all())
        self.assertFalse((column[20] == DIVIDER).all())

    def test_elevated_divider_bands(self):
        bands = lod.divider_bands(2, 4.0, 0.5)
        self.assertEqual([(b[0], b[1]) for b in bands], [(0.5, 'texture3'), (3.0, 'texture4'), (0.5, 'texture3')])
        self.assertTrue(bands[2][4])

    def test_divider_without_texture_takes_the_road_color(self):
        self.state.update({'divider': 3, 'dividerWidth': 4.0})
        column = self.image()[:, 0]
        self.assertLess(abs(int(column[32][0]) - ROAD[0]), 30)

    def test_no_sidewalks(self):
        self.state.update({'hasSidewalks': False, 'totalWidth': 30.0})
        del self.state['texture0']
        self.assertFalse((self.image() == SIDEWALK).all(axis=2).any())

    def test_shoulders_are_not_part_of_it(self):
        self.state['flatSidewalk'] = True
        self.assertFalse((self.image() == SIDEWALK).all(axis=2).any())

    def test_variant(self):
        self.assertFalse((self.folder / 'out' / (self.generate()[:-4] + '_fa.tex')).exists())
        Image.fromarray(road_image((1, 2, 3))).save(self.folder / 'common' / 'Texture' / 'road_fa.png')
        name = self.generate()
        pixels = read_tex(self.folder / 'out' / (name[:-4] + '_fa.tex'))[3][::-1]
        self.assertTrue((pixels[20, 0] == (1, 2, 3)).all())
        # the sidewalk has no such version
        self.assertTrue((pixels[2, 0] == SIDEWALK).all())

    def test_errors(self):
        self.state['texture0'] = 'texture/none.png'
        with self.assertRaisesRegex(GenerationError, 'LOD_TEXTURE_ERROR_MISSING'):
            self.generate()
        self.state['texture0'] = 'texture/walk.png'
        self.state['roadWidth'] = 50.0
        with self.assertRaisesRegex(GenerationError, 'LOD_TEXTURE_ERROR_WIDTHS'):
            self.generate()

    def test_tex_source(self):
        # through the reader of the editor, with the rows of the .tex format (from the bottom)
        sys.path.insert(0, str(CORE / 'exporters/psdl'))
        from writers.tex_writer import write_image
        write_image(str(self.folder / 'common' / 'Texture' / 'road.tex'), Image.fromarray(road_image()).transpose(Image.FLIP_TOP_BOTTOM))
        self.state['texture1'] = 'texture/road.tex'
        column = self.image()[:, 0]
        self.assertTrue((column[9:30] == ROAD).all())
        self.assertGreater(column[31][0], column[29][0])

    def test_the_results_are_shared(self):
        out = OutputRoot(self.folder / 'out')
        first = lod.generate(self.state, out, self.folders())
        self.assertEqual(lod.generate(dict(self.state, echo=True), out, self.folders()), first, 'what the texture does not depend on')
        self.assertEqual(list(out.files), [first])
        self.assertFalse(out.files[first], 'it was not there before')

    def test_only_double_roads_with_the_flag(self):
        self.assertFalse(lod.enabled(self.state))
        self.assertTrue(lod.enabled(dict(self.state, generateLodTexture=True)))
        self.assertFalse(lod.enabled(dict(self.state, generateLodTexture=True, isDouble=False)))
        self.assertFalse(lod.enabled(dict(self.state, generateLodTexture=True, texture1='')))

    def export(self, *states):
        roads = [{'id': i, 'data': {'name': 'Road' + str(i), 'fields': {'state': state}}} for i, state in enumerate(states)]
        data = {'roads': roads, 'cityFolder': str(self.folder / 'city'), 'searchFolders': self.folders()}
        generated = GeneratedExport(self.folder / 'export', data, None)
        generated.lod_textures()
        generated.finish()
        return [road['data']['fields']['state'].get('textureLOD') for road in roads]

    def test_the_export(self):
        # in the export folder, never in the one of the city; the road gets its path, as if chosen in the editor
        flagged = dict(self.state, generateLodTexture=True, textureLOD='texture/chosen.tex')
        other = dict(self.state, textureLOD='texture/chosen.tex')
        first, kept = self.export(flagged, other)
        self.assertTrue(first.startswith('texture/road_lod_'))
        self.assertEqual(kept, 'texture/chosen.tex')
        self.assertTrue((self.folder / 'export' / first).is_file())
        self.assertEqual(list((self.folder / 'city').iterdir()), [])
        self.assertEqual(json.loads((self.folder / 'export' / MANIFEST).read_text()), [first])
        # another width: the old file stays, as the bridge models weren't exported (they can use it, see _test_bridge_mesh)
        second, = self.export(dict(flagged, totalWidth=46.0))
        self.assertNotEqual(first, second)
        self.assertTrue((self.folder / 'export' / first).is_file())
        self.assertEqual(sorted(json.loads((self.folder / 'export' / MANIFEST).read_text())), sorted([first, second]))

    def test_a_failure_is_a_warning(self):
        with patch('generated_export.report.warning') as warning:
            path, = self.export(dict(self.state, generateLodTexture=True, texture0='texture/none.png', textureLOD='texture/chosen.tex'))
        self.assertEqual(path, 'texture/chosen.tex')
        self.assertIn('not found', warning.call_args[0][0], 'the text of the string key')


if __name__ == '__main__':
    unittest.main()
