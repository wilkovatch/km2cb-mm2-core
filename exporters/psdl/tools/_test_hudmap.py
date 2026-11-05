"""Small synthetic checks for label previews and the native HUD/menu maps, without game assets."""
from pathlib import Path
import copy
import base64
import gzip
import importlib.util
import json
import sys
import struct
import tempfile
from types import SimpleNamespace
import unittest

from PIL import Image, ImageChops, JpegImagePlugin

CORE = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(CORE / 'exporters/psdl'), str(CORE.parents[1] / 'python')]
from hudmap_export import (HudmapExporter, Shapes, DEFAULT_COLORS, DEFAULT_LABEL_FONT, DEFAULT_LABEL_SIZE, LABEL_OPACITY,
                           LABEL_TRACKING, MARKER_CHECKPOINT, RACE_MAP_RECT)
from output_layout import OutputLayout
from ar_packer import ArPacker
from MigrationHelper import MigrationHelper

spec = importlib.util.spec_from_file_location('map_label_migration', CORE / 'migrations/5.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def label(text, maps=0, **kwargs):
    return dict(text=text, maps=maps, point=dict(localPosition=dict(x=100, y=15, z=-100)), **kwargs)


def exporter(folder, labels, **settings):
    props = dict(mapLabels=labels, circuitRaces=[{}], **settings)
    return HudmapExporter(SimpleNamespace(data=dict(cityProperties=props)), OutputLayout(str(Path(folder) / 'test.psdl')), {}, folder, False)


def shapes():
    result = Shapes()
    result.add('ground', [(-400, -400), (400, -400), (-400, 400)])
    result.add('ground', [(400, -400), (400, 400), (-400, 400)])
    return result


class HudmapTests(unittest.TestCase):
    def test_road_outline_on_uncovered_background(self):
        road = Shapes()
        road.add('road', [(30, 20), (70, 20), (70, 80)])
        road.add('road', [(30, 20), (70, 80), (30, 80)])
        for settings in ({}, dict(hudmapColorBackground='#204060', hudmapColorOutline='#123456')):
            e = exporter('.', [], hudmapOutlineWidth=2, **settings)
            for outline in (True, False):
                with self.subTest(settings=settings, outline=outline):
                    image = e.render(road, (0, 0, 100, 100), (100, 100), outline=outline)
                    self.assertEqual(image.getpixel((28, 50)), e.colors['outline' if outline else 'background'])
                    self.assertEqual(image.getpixel((27, 50)), e.colors['background'])
                    self.assertEqual(image.getpixel((50, 50)), e.colors['road'])
            e.outline_width = 0
            image = e.render(road, (0, 0, 100, 100), (100, 100))
            self.assertEqual(image.getpixel((28, 50)), e.colors['background'])

    def test_road_outline_keeps_surface_category_rules(self):
        e = exporter('.', [], hudmapOutlineWidth=2)
        for category in ('ground', 'building', 'grass', 'water', 'landmark'):
            with self.subTest(category=category):
                surface = Shapes()
                surface.add(category, [(0, 0), (100, 0), (100, 100)])
                surface.add(category, [(0, 0), (100, 100), (0, 100)])
                surface.add('road', [(30, 20), (70, 20), (70, 80)])
                surface.add('road', [(30, 20), (70, 80), (30, 80)])
                image = e.render(surface, (0, 0, 100, 100), (100, 100))
                expected = e.colors['outline' if category in ('ground', 'building') else category]
                self.assertEqual(image.getpixel((28, 50)), expected)
                self.assertEqual(image.getpixel((27, 50)), e.colors[category])
                self.assertEqual(image.getpixel((50, 50)), e.colors['road'])

    def test_isolated_road_outline_exports_to_native_hud_tiles(self):
        road = Shapes()
        road.add('road', [(-20, -60), (20, -60), (20, 60)])
        road.add('road', [(-20, -60), (20, 60), (-20, 60)])
        with tempfile.TemporaryDirectory() as folder:
            e = exporter(folder, [], hudmapMetersPerPixel=1, hudmapOutlineWidth=2, hudmapMargin=20)
            self.assertTrue(e.export_hudmap(road))
            with Image.open(Path(folder) / 'test_hudmap_preview.png') as image:
                preview = image.convert('RGB')
            self.assertEqual(preview.getpixel((106, 128)), e.colors['outline'])
            self.assertEqual(preview.getpixel((105, 128)), e.colors['background'])
            self.assertEqual(preview.getpixel((128, 128)), e.colors['road'])
            texture = (Path(folder) / 'texture/test_hudmap0.tex').read_bytes()
            width, height, kind, *_ = struct.unpack('<5HI', texture[:14])
            self.assertEqual((width, height, kind), (256, 256, 17))
            native = Image.frombytes('RGB', (width, height), texture[14:14 + width * height * 3]).transpose(Image.FLIP_TOP_BOTTOM)
            self.assertIsNone(ImageChops.difference(native, preview).getbbox())
            self.assertEqual(texture, (Path(folder) / 'texture/test_hudmap0_ni.tex').read_bytes())

    def test_background_falls_back_to_water(self):
        for water in ('', '#123456'):
            expected = (18, 52, 86) if water else DEFAULT_COLORS['water']
            for background in (None, '', '  ', 'invalid', '#%02x%02x%02x' % expected):
                with self.subTest(water=water, background=background):
                    e = exporter('.', [], hudmapColorWater=water, hudmapColorBackground=background)
                    image = e.render(Shapes(), (0, 0, 10, 10), (10, 10))
                    self.assertEqual(image.getpixel((5, 5)), expected)
            # Existing cities have no background property at all.
            e = exporter('.', [], hudmapColorWater=water)
            self.assertEqual(e.render(Shapes(), (0, 0, 10, 10), (10, 10)).getpixel((5, 5)), expected)

    def test_background_keeps_surface_colors(self):
        e = exporter('.', [], hudmapColorBackground='#204060', hudmapColorWater='#123456')
        surface = Shapes()
        surface.add('water', [(-20, -20), (20, -20), (-20, 20)])
        surface.add('ground', [(40, -20), (80, -20), (80, 20)])
        image = e.render(surface, (-100, -100, 100, 100), (200, 200))
        self.assertEqual(image.getpixel((10, 10)), (32, 64, 96))
        self.assertEqual(image.getpixel((90, 90)), (18, 52, 86))
        self.assertEqual(image.getpixel((170, 90)), DEFAULT_COLORS['ground'])

    def test_background_exports_water_tiles_tuning_and_menu_maps(self):
        surface = Shapes()
        surface.add('water', [(-400, -400), (400, -400), (-400, 400)])
        surface.add('water', [(400, -400), (400, 400), (-400, 400)])
        with tempfile.TemporaryDirectory() as folder:
            e = exporter(folder, [], hudmapColorBackground='#204060', hudmapColorWater='#123456')
            self.assertTrue(e.export_hudmap(surface))
            with Image.open(Path(folder) / 'test_hudmap_preview.png') as image:
                preview = image.convert('RGB')
            self.assertEqual(preview.getpixel((0, 0)), (32, 64, 96))
            self.assertEqual(preview.getpixel((128, 128)), (18, 52, 86))
            # Water-only tiles must now exist; the game draws the tuning background where there is no tile.
            texture = (Path(folder) / 'texture/test_hudmap0.tex').read_bytes()
            width, height, kind, *_ = struct.unpack('<5HI', texture[:14])
            self.assertEqual((width, height, kind), (256, 256, 17))
            native = Image.frombytes('RGB', (width, height), texture[14:14 + width * height * 3]).transpose(Image.FLIP_TOP_BOTTOM)
            self.assertIsNone(ImageChops.difference(native, preview).getbbox())
            self.assertEqual(texture, (Path(folder) / 'texture/test_hudmap0_ni.tex').read_bytes())
            tuning = (Path(folder) / 'tune/test.mmHudMap').read_text()
            ocean = next(line for line in tuning.splitlines() if 'Ocean Color' in line).split()[2:]
            for actual, expected in zip(ocean, (32, 64, 96)):
                self.assertAlmostEqual(float(actual), expected / 255, delta=0.0005)
            e.export_race_maps(surface)
            for name in ('roam', 'circuit0'):
                with Image.open(Path(folder) / ('jpg/test_map' + name + '.jpg')) as image:
                    for actual, expected in zip(image.getpixel((20, 90)), (32, 64, 96)):
                        self.assertAlmostEqual(actual, expected, delta=3)
                    for actual, expected in zip(image.getpixel((120, 90)), (18, 52, 86)):
                        self.assertAlmostEqual(actual, expected, delta=3)

    def test_water_only_tiles_stay_omitted_with_matching_background(self):
        surface = Shapes()
        surface.add('water', [(-400, -400), (400, -400), (-400, 400)])
        with tempfile.TemporaryDirectory() as folder:
            e = exporter(folder, [], hudmapColorWater='#123456')
            self.assertTrue(e.export_hudmap(surface))
            self.assertFalse((Path(folder) / 'texture').exists())
            with Image.open(Path(folder) / 'test_hudmap_preview.png') as image:
                self.assertEqual(image.getextrema(), ((18, 18), (52, 52), (86, 86)))

    def test_default_font_and_small_roam_labels(self):
        e = exporter('.', [])
        self.assertEqual(e.get_font(32).getname(), ('Liberation Sans', 'Bold'))
        images = []
        for scale in (1, 0.75):
            image = Image.new('RGB', (100, 24), (231, 219, 195))
            e.draw_labels(image, (-50, -12, 50, 12), [(0, 0, 'NORTH BEACH', 8, 0)], scale)
            images.append(ImageChops.difference(image, Image.new('RGB', image.size, (231, 219, 195))).getbbox())
        self.assertLess(images[1][2] - images[1][0], images[0][2] - images[0][0])

    def test_label_ink_is_translucent_black_on_any_background(self):
        e = exporter('.', [])
        for color in (DEFAULT_COLORS['water'], DEFAULT_COLORS['grass'], DEFAULT_COLORS['ground'], DEFAULT_COLORS['landmark']):
            image = Image.new('RGB', (40, 40), color)
            # the stem of a big letter, wider than the resampling of the label
            e.draw_labels(image, (-20, -20, 20, 20), [(0, 0, 'I', 40, 0)])
            ink = image.getpixel((20, 20))
            for channel, base in zip(ink, color):
                self.assertAlmostEqual(channel, base * (1 - LABEL_OPACITY), delta=1.5)

    def test_touching_letters_do_not_add_up_their_opacity(self):
        e = exporter('.', [])
        image = Image.new('RGB', (120, 40), (200, 200, 200))
        e.draw_labels(image, (-60, -20, 60, 20), [(0, 0, 'AVAVAV', 30, 0)])
        self.assertGreaterEqual(image.convert('L').getextrema()[0], round(200 * (1 - LABEL_OPACITY)) - 2)

    def test_label_tracking_is_proportional_to_the_size(self):
        e = exporter('.', [])
        for size in (DEFAULT_LABEL_SIZE, 12):
            expected = e.get_font(size * 4).getlength('NORTH BEACH') / 4 + LABEL_TRACKING * size * 10
            ink = Image.new('RGB', (240, 40), (231, 219, 195))
            e.draw_labels(ink, (-120, -20, 120, 20), [(0, 0, 'NORTH BEACH', size, 0)])
            bbox = ImageChops.difference(ink, Image.new('RGB', ink.size, (231, 219, 195))).getbbox()
            self.assertAlmostEqual(bbox[2] - bbox[0], expected, delta=3)

    def test_rotated_label_clipped_at_the_edge(self):
        e = exporter('.', [])
        image = Image.new('RGB', (60, 30), (231, 219, 195))
        e.draw_labels(image, (0, 0, 60, 30), [(0, 15, 'WESTMINSTER', 8, 20), (60, 15, 'EMBARCADERO', 8, 0)])
        self.assertIsNotNone(ImageChops.difference(image, Image.new('RGB', image.size, (231, 219, 195))).getbbox())

    def test_race_map_markers_over_labels_and_stock_jpeg_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            race = dict(checkpoints=[dict(checkpoint=dict(localPosition=dict(x=-100, y=0, z=100))),
                                     dict(checkpoint=dict(localPosition=dict(x=100, y=0, z=-100)))])
            e = exporter(folder, [label('MMMMMMMMMMMMMMMM', size=14)])
            e.props['circuitRaces'] = [race]
            e.export_race_maps(shapes())
            with Image.open(Path(folder) / 'jpg/test_mapcircuit0.jpg') as image:
                self.assertEqual(JpegImagePlugin.get_sampling(image), 0)
                image = image.convert('RGB')
                rect = e.fit_rect((-100, -100, 100, 100), 0.25, 300.0)
                x = RACE_MAP_RECT[0] + (-100 - rect[0]) * (RACE_MAP_RECT[2] - RACE_MAP_RECT[0]) / (rect[2] - rect[0])
                y = RACE_MAP_RECT[1] + (-100 - rect[1]) * (RACE_MAP_RECT[3] - RACE_MAP_RECT[1]) / (rect[3] - rect[1])
                # the green ring of the checkpoint on the label stays clean, no ink over it
                ring = image.getpixel((round(x) - 3, round(y)))
                for channel, expected in zip(ring, MARKER_CHECKPOINT):
                    self.assertAlmostEqual(channel, expected, delta=24)

    def test_stock_label_style(self):
        if '--stock-archive' not in sys.argv:
            self.skipTest('optional stock MM2TEX.AR not supplied')
        archive = sys.argv[sys.argv.index('--stock-archive') + 1]
        sys.path.insert(0, str(CORE / 'scripts/importGameAssets'))
        from _import_assets import DaveArchive
        import io
        # Only three known words, from two stock cities; no game images are kept in the repository.
        # The roam label scale is a fixed 0.75 while the stock London roam map is at about 0.66, so London is checked on a race map.
        # Inside the map (no frame) and on the ground (the end of KENSINGTON is on a landmark).
        samples = [('jpg/sf_maprace0.jpg', (170, 42, 236, 53), 'NORTH BEACH', DEFAULT_LABEL_SIZE, 1),
                   ('jpg/sf_maproam.jpg', (153, 25, 205, 35), 'NORTH BEACH', DEFAULT_LABEL_SIZE, 0.75),
                   ('jpg/london_maprace0.jpg', (14, 104, 58, 115), 'KENSING', DEFAULT_LABEL_SIZE, 1)]
        def ink(image):
            # darker than the ground in all the channels: the other surfaces of the map keep at least one channel high
            ground = DEFAULT_COLORS['ground']
            points = [(x,y) for y in range(image.height) for x in range(image.width)
                      if all(c < 0.8 * g for c, g in zip(image.getpixel((x,y)), ground))]
            return max(x for x,y in points)-min(x for x,y in points)+1, max(y for x,y in points)-min(y for x,y in points)+1
        e = exporter('.', [])
        with DaveArchive(archive) as ar:
            entries = {entry.name: entry for entry in ar.entries}
            for name, rect, text, size, scale in samples:
                original = Image.open(io.BytesIO(ar.read(entries[name]))).convert('RGB').crop(rect)
                rendered = Image.new('RGB', (120, 24), (231, 219, 195))
                e.draw_labels(rendered, (-60, -12, 60, 12), [(0, 0, text, size, 0)], scale)
                actual, expected = ink(rendered), ink(original)
                self.assertAlmostEqual(actual[0], expected[0], delta=4, msg=name + ' word width')
                self.assertAlmostEqual(actual[1], expected[1], delta=1, msg=name + ' cap height')

    def test_migration_preserves_labels_points_and_existing_ids(self):
        original = dict(cityProperties=dict(_elementContainerId='hudmap', mapLabels=[label('Città', 1, size=13, angle=30), label('Race', 2)]),
                        terrainPoints=[dict(id=100, position=dict(x=1, y=2, z=3))], customElements=[dict(id=20, state=dict(type='room'))])
        before = copy.deepcopy(original)
        result = migration.migrate_city(original)
        self.assertEqual(original, before)
        self.assertEqual(result['terrainPoints'][0], original['terrainPoints'][0])
        self.assertEqual(result['customElements'][0], original['customElements'][0])
        self.assertEqual([e['id'] for e in result['customElements']], [20, 21, 22])
        self.assertEqual([p['id'] for p in result['terrainPoints']], [100, 101, 102])
        labels = result['customElements'][1:]
        self.assertEqual(labels[0]['points'], dict(center=101))
        self.assertEqual(labels[0]['state'], dict(type='mapLabel', text='Città', maps=1, size=13, angle=30, _propertyContainerId='hudmap'))
        self.assertNotIn('mapLabels', result['cityProperties'])
        self.assertEqual(migration.migrate_city(result), result)

    def test_normal_migration_creates_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = dict(cityProperties=dict(mapLabels=[label('District')]))
            with gzip.open(root / 'city.json.gz', 'wt', encoding='utf-8') as stream:
                json.dump(original, stream)
            (root / 'preferences.json').write_text(json.dumps(dict(coreVersion=4)))
            (root / 'presets.json').write_text(json.dumps(dict(presets={})))
            migration.process_folder(MigrationHelper(folder + '/'))
            self.assertEqual(json.loads((root / 'preferences.json').read_text())['coreVersion'], 5)
            with gzip.open(root / 'city.json.gz.v4.bak', 'rt') as stream:
                self.assertEqual(json.load(stream), original)
            self.assertTrue((root / 'preferences.json.v4.bak').is_file())

    def test_owned_labels_match_legacy_export(self):
        old = [label('Città', size=11, angle=25), label('Race', 2), label('Roam', 1)]
        e = exporter('.', old)
        modern = copy.deepcopy(e.data)
        modern['cityProperties'].pop('mapLabels')
        modern['customElements'] = []
        for source in old:
            state = {k: v for k, v in source.items() if k != 'point'}
            modern['customElements'].append(dict(type='mapLabel', data=dict(fields=dict(state=state)),
                                                points=dict(center=dict(position=[100,15,-100]))))
        new = HudmapExporter(SimpleNamespace(data=modern), None, {}, '.', False)
        self.assertEqual(new.get_labels(True), e.get_labels(True))
        self.assertEqual(new.get_labels(False), e.get_labels(False))

    def test_label_coordinates_defaults_and_map_filters(self):
        e = exporter('.', [label(' district '), label('Roam', 1, size=12, angle=30), label('Race', 2),
                           label(' '), dict(text='Not placed', point='@handle')])
        self.assertEqual(e.get_labels(True), [(-100, -100, 'DISTRICT', DEFAULT_LABEL_SIZE, 0), (-100, -100, 'ROAM', 12, 30)])
        self.assertEqual(e.get_labels(False), [(-100, -100, 'DISTRICT', DEFAULT_LABEL_SIZE, 0), (-100, -100, 'RACE', DEFAULT_LABEL_SIZE, 0)])

    def test_annotated_preview_leaves_native_hud_outputs_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            plain = Path(folder) / 'plain'
            annotated = Path(folder) / 'annotated'
            for root, labels in ((plain, []), (annotated, [label('District', size=14, angle=20)])):
                root.mkdir()
                e = exporter(root, labels)
                self.assertTrue(e.export_hudmap(shapes()))
                e.export_race_maps(shapes())
            # This includes the label-free preview, HUD tiles, PKG and tuning. Only the new preview and JPGs differ.
            for file in plain.rglob('*'):
                if file.is_file() and file.suffix != '.jpg' and file.name != 'test_hudmap_labels_preview.png':
                    self.assertEqual(file.read_bytes(), (annotated / file.relative_to(plain)).read_bytes(), str(file))
            original = Image.open(annotated / 'test_hudmap_preview.png')
            preview = Image.open(annotated / 'test_hudmap_labels_preview.png')
            diff = ImageChops.difference(original, preview).getbbox()
            self.assertIsNotNone(diff)
            self.assertAlmostEqual((diff[0] + diff[2]) / 2, preview.width / 2 - 100 / 5.5, delta=2)
            self.assertAlmostEqual((diff[1] + diff[3]) / 2, preview.height / 2 - 100 / 5.5, delta=2)
            self.assertNotEqual((plain / 'jpg/test_maproam.jpg').read_bytes(), (annotated / 'jpg/test_maproam.jpg').read_bytes())
            self.assertNotEqual((plain / 'jpg/test_mapcircuit0.jpg').read_bytes(), (annotated / 'jpg/test_mapcircuit0.jpg').read_bytes())
            packed = ArPacker(exporter(annotated, []).layout, str(plain), False).get_entries()
            self.assertFalse(any('preview' in name for name in packed))

    def test_preview_uses_roam_label_visibility(self):
        with tempfile.TemporaryDirectory() as folder:
            e = exporter(folder, [label('Race only', 2)])
            e.export_hudmap(shapes())
            original = Image.open(Path(folder) / 'test_hudmap_preview.png')
            preview = Image.open(Path(folder) / 'test_hudmap_labels_preview.png')
            self.assertIsNone(ImageChops.difference(original, preview).getbbox())

    # One-way arrows

    def arrow_exporter(self, roads, chains=None, hudmap_mpp=1, **props):
        # roads: {key: (forward lanes, backward lanes, [center points], state)}, with the exported x (the game mirrors it)
        records = {}
        for key, (forward, backward, center, state) in roads.items():
            state = dict(state, forwardLanes=forward, backwardLanes=backward)
            sections = [[(x - 4, 0, z), (x - 3, 0, z), (x + 3, 0, z), (x + 4, 0, z)] for x, z in center]
            records[key] = dict(road=dict(data=dict(fields=dict(state=state), mesh=dict(submeshes=[dict(materialId=-1)]))), sections=sections)

        def bai_sections(rec, reverse):
            return [list(reversed(s)) for s in reversed(rec['sections'])] if reverse else rec['sections']

        def lane_counts(state):
            return (0, 0) if state.get('disableTraffic') else (state['forwardLanes'], state['backwardLanes'])

        jp = SimpleNamespace(data=dict(cityProperties=dict(hudmapMetersPerPixel=hudmap_mpp, **props)), exported_roads=records,
                             get_bai_sections=bai_sections, get_bai_lane_counts=lane_counts)
        if chains is not None:
            jp.bai_chains = chains
        return HudmapExporter(jp, None, {}, '.', False)

    def blue(self, pixel):
        return pixel[2] > 200 and pixel[0] < 60 and pixel[1] < 60

    def pale(self, pixel):
        return pixel[0] < 240 and pixel[1] < 240 and pixel[2] > 240

    def road_shapes(self, e):
        shapes = Shapes()
        shapes.add('road', [(-5000, -5000), (5000, -5000), (-5000, 5000)])
        shapes.add('road', [(5000, -5000), (5000, 5000), (-5000, 5000)])
        shapes.arrows = e.get_arrows()
        return shapes

    def test_arrow_head_points_with_the_traffic(self):
        # going +z in the export: south on the map (north is -z), the x of the export isn't mirrored at x = 0
        line = [(0, -40), (0, 40)]
        for lanes, head_south in (((2, 0), True), ((0, 2), False)):
            with self.subTest(lanes=lanes):
                e = self.arrow_exporter({'r': (lanes[0], lanes[1], line, {})})
                image = e.render(self.road_shapes(e), (-50, -50, 50, 50), (100, 100), outline=False)
                # 14 pixels from the middle of the road, the head in the last 4, widest at its back
                self.assertTrue(self.blue(image.getpixel((50, 54 if head_south else 45))))
                self.assertFalse(self.blue(image.getpixel((50, 45 if head_south else 54))))
                # the shaft, pale on the other side of the head
                self.assertTrue(self.pale(image.getpixel((50, 45 if head_south else 54))))
                self.assertEqual(image.getpixel((50, 41 if head_south else 58)), e.colors['road'])
                self.assertEqual(image.getpixel((53, 50)), e.colors['road'])

    def test_arrow_x_is_mirrored_as_the_game(self):
        # going +x in the export goes -x in the game: west, on the left of the map
        e = self.arrow_exporter({'r': (1, 0, [(-40, 0), (40, 0)], {})})
        image = e.render(self.road_shapes(e), (-50, -50, 50, 50), (100, 100), outline=False)
        self.assertTrue(self.blue(image.getpixel((45, 50))))
        self.assertFalse(self.blue(image.getpixel((54, 50))))

    def test_arrows_only_on_one_way_roads_with_traffic(self):
        far = [(-40, 0), (40, 0)]
        for name, lanes, state, expected in (('one way', (1, 0), {}, 1), ('two way', (1, 1), {}, 0), ('no lanes', (0, 0), {}, 0),
                                             ('no traffic', (1, 0), dict(disableTraffic=True), 0), ('pedestrian', (1, 0), dict(pedestrianStreet=True), 0),
                                             ('hidden', (1, 0), dict(hudmapCategory=7), 0), ('ground', (1, 0), dict(hudmapCategory=1), 0),
                                             ('road category', (1, 0), dict(hudmapCategory=6), 1)):
            with self.subTest(name):
                e = self.arrow_exporter({'r': (lanes[0], lanes[1], far, state)})
                self.assertEqual(len(e.get_arrows()), expected)

    def test_arrows_setting_and_color(self):
        e = self.arrow_exporter({'r': (1, 0, [(-40, 0), (40, 0)], {})}, hudmapHideArrows=True)
        self.assertEqual(e.get_arrows(), [])
        e = self.arrow_exporter({'r': (1, 0, [(0, -40), (0, 40)], {})}, hudmapColorArrow='#ff0000')
        image = e.render(self.road_shapes(e), (-50, -50, 50, 50), (100, 100), outline=False)
        self.assertEqual(image.getpixel((50, 54)), (255, 0, 0))

    def test_arrows_keep_their_distance_preferring_the_longest_road(self):
        e = self.arrow_exporter({'short': (1, 0, [(-10, 0), (10, 0)], {}), 'long': (1, 0, [(-30, 15), (30, 15)], {}),
                                 'far': (1, 0, [(-10, 200), (10, 200)], {}), 'tiny': (1, 0, [(-4, 400), (4, 400)], {})}, hudmap_mpp=1)
        arrows = e.get_arrows()
        # the distance is in pixels of the hudmap (20), the tiny road is below the minimum (10)
        self.assertEqual([round(a[1][-1]) for a in arrows], [60, 20])
        self.assertEqual(sorted(a[0][0][1] for a in arrows), [15, 200])

    def test_arrows_of_a_row_of_roads_go_through_it(self):
        # two short roads meeting at a seamless joint, the second one drawn the other way: one way as a whole
        roads = {'a': (1, 0, [(0, -8), (0, 0)], {}), 'b': (0, 1, [(0, 8), (0, 0)], {})}
        e = self.arrow_exporter(roads, chains=[[('a', False), ('b', True)]], hudmap_mpp=1)
        arrows = e.get_arrows()
        self.assertEqual(len(arrows), 1)
        self.assertEqual(arrows[0][0], [(-0.0, -8.0), (-0.0, 0.0), (-0.0, 8.0)])
        # not one way, as a whole
        roads['b'] = (1, 0, [(0, 8), (0, 0)], {})
        self.assertEqual(self.arrow_exporter(roads, chains=[[('a', False), ('b', True)]], hudmap_mpp=1).get_arrows(), [])

    def test_arrow_follows_the_road_and_stays_on_a_short_one(self):
        e = self.arrow_exporter({'r': (1, 0, [(-6, 0), (6, 0)], {})}, hudmap_mpp=1)
        image = e.render(self.road_shapes(e), (-50, -50, 50, 50), (100, 100), outline=False)
        # 12 m of road: the arrow ends at the end of the road (x -6 in the export, 6 in the game)
        self.assertEqual(image.getpixel((58, 50)), e.colors['road'])
        self.assertEqual(image.getpixel((42, 50)), e.colors['road'])
        # around a bend
        e = self.arrow_exporter({'r': (1, 0, [(0, -20), (0, 0), (20, 0)], {})}, hudmap_mpp=1)
        image = e.render(self.road_shapes(e), (-50, -50, 50, 50), (100, 100), outline=False)
        self.assertNotEqual(image.getpixel((50, 47)), e.colors['road'])
        self.assertTrue(self.blue(image.getpixel((46, 50))))

    def test_menu_maps_scale_the_arrows_between_limits(self):
        e = self.arrow_exporter({'r': (1, 0, [(0, -400), (0, 400)], {})}, hudmap_mpp=5.5)
        shapes = self.road_shapes(e)

        def arrow_rows(meters_per_pixel):
            size = 100
            half = size * meters_per_pixel / 2
            image = e.render(shapes, (-half, -half, half, half), (size, size), outline=False)
            return sum(1 for y in range(size) if image.getpixel((50, y)) != e.colors['road'])

        self.assertAlmostEqual(arrow_rows(5.5), 14, delta=1)  # as on the hudmap
        self.assertAlmostEqual(arrow_rows(1), 14, delta=1)  # a zoomed race map: not bigger in pixels
        self.assertAlmostEqual(arrow_rows(8), 14 * 5.5 / 8, delta=1)  # follows the map when it is smaller
        self.assertAlmostEqual(arrow_rows(50), 7, delta=1)  # but not too small

    def test_arrows_are_seamless_across_tiles(self):
        e = self.arrow_exporter({'r': (1, 0, [(0, -60), (0, 60)], {})})
        shapes = self.road_shapes(e)
        whole = e.render(shapes, (-20, -20, 20, 20), (40, 40), outline=False)
        tile = e.render(shapes, (-20, -20, 20, 2), (40, 22), outline=False)
        self.assertIsNone(ImageChops.difference(whole.crop((0, 0, 40, 22)), tile).getbbox())

    # Movable bridges

    def bridge_element(self, id=1, start=(0, 0, -50), finish=(0, 0, 50), **state):
        return dict(id=id, type='bridge', data=dict(name='Bridge', fields=dict(state=state)),
                    points=dict(start=dict(position=list(start)), finish=dict(position=list(finish))))

    def bridge_exporter(self, elements, roads=(), folder='.', **props):
        data = dict(cityProperties=dict(props), customElements=elements, roads=list(roads), intersections=[], terrainPatches=[], buildingLines=[], meshInstances=[])
        jp = SimpleNamespace(data=data, custom_elements=SimpleNamespace(hudmap_meshes=lambda: []), exported_roads={})
        return HudmapExporter(jp, None, {}, folder, False)

    def test_bridge_is_drawn_as_a_road_by_default(self):
        e = self.bridge_exporter([self.bridge_element()])
        shapes = e.get_shapes().with_bridges()
        self.assertEqual(len(shapes.triangles['road']), 2)
        image = e.render(shapes, (-50, -50, 50, 50), (100, 100), outline=False)
        self.assertEqual(image.getpixel((50, 50)), e.colors['road'])
        # the default width, along +z, across x
        half = 18.5 / 2
        self.assertEqual(image.getpixel((round(50 + half - 1), 50)), e.colors['road'])
        self.assertEqual(image.getpixel((round(50 + half + 1), 50)), e.colors['background'])
        self.assertEqual(image.getpixel((50, 1)), e.colors['road'])

    def test_bridge_category(self):
        for index, expected in ((5, 'landmark'), (6, 'road'), (1, 'ground')):
            shapes = self.bridge_exporter([self.bridge_element(hudmapCategory=index)]).get_shapes().with_bridges()
            self.assertEqual(len(shapes.triangles[expected]), 2)
        shapes = self.bridge_exporter([self.bridge_element(hudmapCategory=7)]).get_shapes().with_bridges()
        self.assertIsNone(shapes.bounds())

    def test_bridge_incomplete_is_left_out(self):
        same = self.bridge_element(start=(5, 0, 5), finish=(5, 0, 5))
        missing = self.bridge_element()
        del missing['points']['finish']
        self.assertIsNone(self.bridge_exporter([same, missing]).get_shapes().with_bridges().bounds())

    def test_bridge_width_comes_from_the_attached_roads_at_their_angle(self):
        road = dict(id=7, data=dict(fields=dict(state=dict(totalWidth=30))))
        element = self.bridge_element()
        # the ends of the roads at 45 degrees: the deck is a parallelogram, without bow ties whichever way the roads go
        element['points']['start']['anchor'] = dict(kind='road', id=7, insideDirection=[1, 0, -1])
        element['points']['finish']['anchor'] = dict(kind='road', id=7, insideDirection=[-1, 0, 1])
        e = self.bridge_exporter([element], [road])
        triangles = e.get_shapes().with_bridges().triangles['road']
        area = sum(abs((t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) - (t[2][0] - t[0][0]) * (t[1][1] - t[0][1])) / 2 for t in triangles)
        # the corners are on the end sections of the roads, 30 m long at 45 degrees from the 100 m between the hinges
        self.assertAlmostEqual(area, 30 / 2 ** 0.5 * 100, delta=1e-6)
        xs = [p[0] for t in triangles for p in t]
        self.assertAlmostEqual(max(xs), 15 / 2 ** 0.5, delta=1e-6)

    def test_bridge_width_comes_from_the_model_when_not_attached(self):
        with tempfile.TemporaryDirectory() as folder:
            geometry = Path(folder) / 'geometry'
            geometry.mkdir()
            sys.path.insert(0, str(CORE / 'exporters/psdl/tools'))
            from _test_bridges import write_pkg
            write_pkg(geometry / 'wide_bridge.pkg', [(-20, 0, -15), (20, 1, 15)])
            e = self.bridge_exporter([self.bridge_element(mesh='geometry/wide_bridge.pkg')], folder=folder)
            xs = [p[0] for t in e.get_shapes().with_bridges().triangles['road'] for p in t]
            self.assertAlmostEqual(max(xs), 20, delta=1e-5)
            self.assertAlmostEqual(min(xs), -20, delta=1e-5)

    def test_race_bridges_are_only_on_the_maps_of_their_race(self):
        city = self.bridge_element(1, (0, 0, -50), (0, 0, 50))
        other = self.bridge_element(2, (300, 0, -50), (300, 0, 50))
        added = self.bridge_element(3, (-300, 0, -50), (-300, 0, 50), _propertyContainerId='race-a')
        replacement = self.bridge_element(4, (0, 0, -50), (0, 0, 50), _propertyContainerId='race-a', hudmapCategory=5, replaces=dict(kind='customElement', id=1))
        foreign = self.bridge_element(5, (600, 0, -50), (600, 0, 50), _propertyContainerId='race-b')
        shapes = self.bridge_exporter([city, other, added, replacement, foreign]).get_shapes()
        base = shapes.with_bridges()
        self.assertEqual((len(base.triangles['road']), len(base.triangles['landmark'])), (4, 0))
        race = shapes.with_bridges('race-a')
        # the other city bridge and the one it adds as roads, the replacement with its own category instead of the city one
        self.assertEqual((len(race.triangles['road']), len(race.triangles['landmark'])), (4, 2))
        self.assertLess(race.bounds()[0], -200 - 90)
        self.assertEqual(shapes.with_bridges('race-b').bounds()[0], -600 - 18.5 / 2)

    def test_exports_include_the_bridges(self):
        with tempfile.TemporaryDirectory() as folder:
            race = dict(_elementContainerId='race-a', checkpoints=[dict(checkpoint=dict(localPosition=dict(x=0, y=0, z=0)))])
            bridge = self.bridge_element(1, (-200, 0, 0), (200, 0, 0), _propertyContainerId='race-a')
            city = self.bridge_element(2, (0, 0, -300), (0, 0, 300))
            e = self.bridge_exporter([bridge, city], folder=folder, circuitRaces=[race])
            e.layout = OutputLayout(str(Path(folder) / 'test.psdl'))
            e.margin = 20
            e.export()
            with Image.open(Path(folder) / 'test_hudmap_preview.png') as image:
                preview = image.convert('RGB')
            # only the city bridge on the HUD: north of the center, and nothing east of it where the bridge of the race is
            center = preview.width // 2
            self.assertEqual(preview.getpixel((center, center - 40)), e.colors['road'])
            self.assertEqual(preview.getpixel((center + 20, center)), e.colors['background'])
            with Image.open(Path(folder) / 'jpg/test_mapcircuit0.jpg') as image:
                race_map = image.convert('RGB')
            with Image.open(Path(folder) / 'jpg/test_maproam.jpg') as image:
                roam_map = image.convert('RGB')

            # along the middle of the maps: the bridge of the race crosses all of it, on the roam map there is only the city one
            def whites(image):
                y = (RACE_MAP_RECT[1] + RACE_MAP_RECT[3]) // 2
                return sum(1 for x in range(RACE_MAP_RECT[0], RACE_MAP_RECT[2]) if min(image.getpixel((x, y))) > 240)
            self.assertGreater(whites(race_map), 150)
            self.assertLess(whites(roam_map), 20)

    def test_builder_export_json(self):
        if len(sys.argv) < 2 or not Path(sys.argv[1]).is_file():
            self.skipTest('optional builder export JSON not supplied')
        data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        e = HudmapExporter(SimpleNamespace(data=data), None, {}, '.', False)
        self.assertEqual(e.get_labels(True), [(-20, 30, 'DOWNTOWN', DEFAULT_LABEL_SIZE, 0), (-300, 30, 'HARBOUR', DEFAULT_LABEL_SIZE, 0)])
        # Compare the independently generated Lua mesh with FreeType's metrics of the export font.
        from PIL import ImageFont
        label = next(item for item in data['customElements'] if item['type'] == 'mapLabel')
        raw = base64.b64decode(label['data']['mesh']['b64v3a_vertices'])
        points = list(struct.iter_unpack('<fff', raw[4:]))
        width = max(p[0] for p in points) - min(p[0] for p in points)
        height = max(p[2] for p in points) - min(p[2] for p in points)
        bounds = ImageFont.truetype(str(DEFAULT_LABEL_FONT), 4096).getmask('DOWNTOWN').getbbox()
        self.assertAlmostEqual(width / (DEFAULT_LABEL_SIZE * 5.5), (bounds[2] - bounds[0]) / 4096 + 7 * LABEL_TRACKING, delta=0.002)
        self.assertAlmostEqual(height / (DEFAULT_LABEL_SIZE * 5.5), (bounds[3] - bounds[1]) / 4096, delta=0.002)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
