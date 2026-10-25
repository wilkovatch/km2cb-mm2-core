import math
import os
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from common.file_io import BinaryFileHelper
from common.tex_writer import write_image
from utils import state_val, state_vector

# The map of the city drawn from its geometry, seen from above with the north (-z in the game) up:
# - the hudmap, the map of the HUD in the game (no labels): tiles in texture/<city>_hudmap<n>.tex (and the _ni
#   copies for the night), placed in the city by geometry/hudmap_<city>.pkg (a quad for each tile, as in
#   hudmap_sf.pkg), and tune/<city>.mmHudMap (position and zoom of the HUD map, color of the ocean around it)
# - the race maps of the menus, with the labels: jpg/<city>_maproam.jpg (the whole city) and
#   jpg/<city>_map<race>.jpg (the area of each race, with the start and the checkpoints)
# All the coordinates are the ones of the game (x mirrored: game x = -x of the export)

# hudmapCategory enum of the elements (index 0 is auto)
CATEGORIES = ['auto', 'ground', 'grass', 'water', 'building', 'landmark', 'road', 'hidden']
# drawing order of the categories (road includes its outline, hidden is never drawn)
DRAW_ORDER = ['ground', 'grass', 'water', 'building', 'landmark', 'road']
# the categories the road outline is drawn over (as in the stock San Francisco hudmap, none against grass)
OUTLINED = ['ground', 'building']

# the colors of the stock San Francisco hudmap
DEFAULT_COLORS = {
    'road': (255, 255, 255),
    'outline': (197, 191, 181),
    'ground': (231, 219, 195),
    'building': (231, 219, 195),
    'grass': (162, 219, 138),
    'water': (8, 174, 235),
    'landmark': (215, 130, 134),
    'label': (112, 112, 112),
}
LABEL_HALO = (242, 237, 228)
MARKER_START = (224, 32, 110)
MARKER_CHECKPOINT = (124, 224, 0)
MARKER_CENTER = (255, 255, 0)
MARKER_OUTLINE = (0, 0, 0)

# the physics materials of materials.csv (and the texture names) that make a surface grass or water
PHYSICS_CATEGORIES = {'grass': 'grass', 'mud': 'grass', 'water': 'water', 'deepwater': 'water'}
NAME_CATEGORIES = [(re.compile('grass|park|lawn'), 'grass'), (re.compile('water|pond|river|sea'), 'water')]

DEFAULT_METERS_PER_PIXEL = 5.5  # as the stock hudmaps
DEFAULT_MARGIN = 100.0
DEFAULT_OUTLINE_WIDTH = 1.0
TILE_SIZES = [256, 512]
MAX_TILES = 16
SUPERSAMPLING = 4

# the race maps: the size of the images, the rectangle of the map in them (the rest is the frame,
# Files/common/MidtownMadness2/jpg/mapframe.jpg if present, e.g. a copy of a stock map, else FRAME_COLOR)
RACE_MAP_SIZE = (242, 184)
RACE_MAP_RECT = (8, 5, 237, 180)
FRAME_COLOR = (61, 54, 95)
RACE_MAP_MARGIN = 0.25
RACE_MAP_MIN_SIZE = 300.0
DEFAULT_LABEL_SIZE = 8.0
MARKER_RADIUS = 5.0

# mmHudMap values of the stock San Francisco
MMHUDMAP = """type: a
mmHudMap {{
  Size 0.210000	0.250000
  Pos 0.780000	0.750000
  ZoomIn 0
  Approach Rate 1.200000
  ZoomInDist 577.000000
  ZoomOutDist 1195.000000
  IconScaleMin 34.090019
  IconScaleMax 52.399994
  ZoomInDistFS 786.000000
  ZoomOutDistFS 1581.000000
  IconScaleMinFS 15.070000
  IconScaleMaxFS 18.000000
  Ocean Color {:.3f} {:.3f} {:.3f}
}}
"""


def parse_color(value, default, name):
    # #RRGGBB (or RRGGBB), the default if empty or invalid
    if not isinstance(value, str) or value.strip() == '':
        return default
    v = value.strip().lstrip('#')
    if re.fullmatch('[0-9a-fA-F]{6}', v) is None:
        print("Warning: the hudmap color " + name + " (" + value + ") is not a #RRGGBB color, the default is used")
        return default
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def positive(value, default, allow_zero=False):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 or (allow_zero and value == 0) else default


def enum_index(state, key):
    try:
        return int(round(float(state_val(state, key, 0) or 0)))
    except (TypeError, ValueError):
        return 0


def element_category(state):
    i = enum_index(state, 'hudmapCategory')
    return CATEGORIES[i] if 0 < i < len(CATEGORIES) else 'auto'


def texture_name(texture):
    if texture is None:
        return ''
    return texture.replace('\\', '/').split('/')[-1].split('.')[0].lower()


def game_xz(v):
    return (-v[0], v[2])


def rotate(q, v):
    # rotation of the vector v by the quaternion q (x, y, z, w)
    x, y, z, w = q
    tx = 2 * (y * v[2] - z * v[1])
    ty = 2 * (z * v[0] - x * v[2])
    tz = 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty),
            v[1] + w * ty + (z * tx - x * tz),
            v[2] + w * tz + (x * ty - y * tx))


class Shapes:
    # the triangles (in game x, z) of each category
    def __init__(self):
        self.triangles = {c: [] for c in DRAW_ORDER}

    def add(self, category, tri):
        if category in self.triangles:
            self.triangles[category].append(tri)

    def bounds(self, categories=None):
        res = None
        for c in categories or DRAW_ORDER:
            for tri in self.triangles[c]:
                for x, z in tri:
                    if res is None:
                        res = [x, z, x, z]
                    else:
                        res = [min(res[0], x), min(res[1], z), max(res[2], x), max(res[3], z)]
        return res

    def in_rect(self, category, rect):
        # the triangles of the category overlapping the rectangle (x0, z0, x1, z1)
        x0, z0, x1, z1 = rect
        return [t for t in self.triangles[category]
                if max(p[0] for p in t) >= x0 and min(p[0] for p in t) <= x1
                and max(p[1] for p in t) >= z0 and min(p[1] for p in t) <= z1]


class HudmapExporter:
    def __init__(self, json_processor, layout, physics_map, common_dir, verbose):
        self.data = json_processor.data
        self.layout = layout
        self.physics_map = physics_map or {}
        self.common_dir = common_dir
        self.verbose = verbose
        self.props = self.data.get('cityProperties') or {}
        p = self.props
        self.colors = {k: parse_color(state_val(p, 'hudmapColor' + k[0].upper() + k[1:], ''), v, k)
                       for k, v in DEFAULT_COLORS.items()}
        self.meters_per_pixel = positive(state_val(p, 'hudmapMetersPerPixel'), DEFAULT_METERS_PER_PIXEL)
        self.margin = positive(state_val(p, 'hudmapMargin'), DEFAULT_MARGIN)
        self.outline_width = positive(state_val(p, 'hudmapOutlineWidth'), DEFAULT_OUTLINE_WIDTH, True)
        tile_index = enum_index(p, 'hudmapTileSize')
        self.tile_size = TILE_SIZES[tile_index] if 0 <= tile_index < len(TILE_SIZES) else TILE_SIZES[0]
        self.fonts = {}

    # Shapes

    def texture_category(self, texture, default):
        name = texture_name(texture)
        if name == '':
            return default
        physics = self.physics_map.get(name)
        if physics in PHYSICS_CATEGORIES:
            return PHYSICS_CATEGORIES[physics]
        if physics is None:
            for regex, category in NAME_CATEGORIES:
                if regex.search(name):
                    return category
        return default

    def material_texture(self, material_id):
        if material_id is None or material_id < 0:
            return None
        return state_val(self.data['materialDict'][material_id].get('data'), 'texture')

    def add_mesh(self, shapes, mesh, category, default, by_texture=True):
        # the triangles of a mesh, each submesh with the category (if not auto), else the one of its texture
        if mesh is None or category == 'hidden':
            return
        vertices = [game_xz(v) for v in mesh['vertices']]
        for submesh in mesh['submeshes']:
            c = category
            if c == 'auto':
                c = self.texture_category(self.material_texture(submesh['materialId']), default) if by_texture else default
            indices = submesh['indices']
            for t in range(0, len(indices) - 2, 3):
                shapes.add(c, (vertices[indices[t]], vertices[indices[t + 1]], vertices[indices[t + 2]]))

    def add_mesh_instance(self, shapes, instance):
        category = element_category(instance.get('settings'))
        if category in ('auto', 'hidden'):
            return
        ref = instance['reference']
        dict_mesh = self.data['meshDict'][ref['meshId']]
        bmin, bmax = dict_mesh['boundsMin'], dict_mesh['boundsMax']
        corners = []
        for x, z in [(bmin[0], bmin[2]), (bmax[0], bmin[2]), (bmax[0], bmax[2]), (bmin[0], bmax[2])]:
            v = (x * ref['scale'][0], 0.0, z * ref['scale'][2])
            v = rotate(ref['rotation'], v)
            corners.append(game_xz((v[0] + ref['position'][0], 0.0, v[2] + ref['position'][2])))
        shapes.add(category, (corners[0], corners[1], corners[2]))
        shapes.add(category, (corners[0], corners[2], corners[3]))

    def get_shapes(self):
        shapes = Shapes()
        for road in self.data.get('roads') or []:
            self.add_mesh(shapes, road['data'].get('mesh'), 'auto', 'road')
        for intersection in self.data.get('intersections') or []:
            self.add_mesh(shapes, intersection['data'].get('mesh'), 'auto', 'road')
            for road in intersection.get('roadsThrough') or []:
                self.add_mesh(shapes, road['data'].get('mesh'), 'auto', 'road')
        for patch in self.data.get('terrainPatches') or []:
            state = patch['data']['fields']['state']
            if not state_val(state, 'invisible', False):
                self.add_mesh(shapes, patch['data'].get('mesh'), element_category(state), 'ground')
        for line in self.data.get('buildingLines') or []:
            line_category = element_category(line['data']['fields']['state'])
            self.add_mesh(shapes, line.get('roof'), line_category, 'building', False)
            for building in line.get('buildings') or []:
                category = element_category(building['data']['fields']['state'])
                self.add_mesh(shapes, building.get('roof'), line_category if category == 'auto' else category, 'building', False)
        for instance in self.data.get('meshInstances') or []:
            self.add_mesh_instance(shapes, instance)
        return shapes

    # Rendering

    def render(self, shapes, rect, size, markers=None, outline=True):
        # the image (size in pixels) of the area rect (x0, z0, x1, z1), with the markers ([(x, z, color)]),
        # the roads with an outline if requested (only the hudmap, the stock race maps have none)
        w, h = size
        ss = SUPERSAMPLING
        sx = w * ss / (rect[2] - rect[0])
        sz = h * ss / (rect[3] - rect[1])
        outline = int(round(self.outline_width * ss)) if outline else 0
        pad = outline / min(sx, sz)
        cull = (rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad)

        def to_px(p):
            return ((p[0] - rect[0]) * sx, (p[1] - rect[1]) * sz)

        image = Image.new('RGB', (w * ss, h * ss), self.colors['water'])
        draw = ImageDraw.Draw(image)
        # where the outline can be drawn (the pixels of the OUTLINED categories)
        outlined = Image.new('L', image.size, 0) if outline > 0 else None
        outlined_draw = ImageDraw.Draw(outlined) if outline > 0 else None
        for category in DRAW_ORDER:
            triangles = shapes.in_rect(category, cull)
            if len(triangles) == 0:
                continue
            if category == 'road' and outline > 0:
                # the outline: the roads grown by its width, under them
                mask = Image.new('L', image.size, 0)
                mask_draw = ImageDraw.Draw(mask)
                for tri in triangles:
                    mask_draw.polygon([to_px(p) for p in tri], fill=255)
                grown = ImageChops.multiply(mask.filter(ImageFilter.MaxFilter(2 * outline + 1)), outlined)
                image.paste(self.colors['outline'], (0, 0) + image.size, grown)
                image.paste(self.colors['road'], (0, 0) + image.size, mask)
            else:
                color = self.colors[category]
                for tri in triangles:
                    draw.polygon([to_px(p) for p in tri], fill=color)
                    if outlined_draw is not None:
                        outlined_draw.polygon([to_px(p) for p in tri], fill=255 if category in OUTLINED else 0)
        for x, z, color in markers or []:
            cx, cy = to_px((x, z))
            r = MARKER_RADIUS * ss
            draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=MARKER_OUTLINE)
            r -= ss
            draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=color)
            if color == MARKER_CHECKPOINT:
                r *= 0.45
                draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=MARKER_CENTER)
        return image.resize((w, h), Image.BOX)

    def get_font(self, size):
        size = max(4, int(round(size)))
        if size not in self.fonts:
            path = state_val(self.props, 'hudmapLabelFont', '') or ''
            font = None
            if path.strip() != '':
                if not os.path.isabs(path):
                    path = os.path.join(self.common_dir, path)
                try:
                    font = ImageFont.truetype(path, size)
                except OSError:
                    print("Warning: the label font " + path + " could not be loaded, the default one is used")
            self.fonts[size] = font or ImageFont.load_default(size)
        return self.fonts[size]

    def draw_labels(self, image, rect, labels):
        # labels: [(x, z, text, size, angle)], centered on their point
        w, h = image.size
        for x, z, text, size, angle in labels:
            px = (x - rect[0]) * w / (rect[2] - rect[0])
            py = (z - rect[1]) * h / (rect[3] - rect[1])
            font = self.get_font(size)
            halo = max(1, int(round(size / 8)))
            box = font.getbbox(text, stroke_width=halo)
            layer = Image.new('RGBA', (box[2] - box[0] + 2, box[3] - box[1] + 2), (0, 0, 0, 0))
            layer_draw = ImageDraw.Draw(layer)
            origin = (1 - box[0], 1 - box[1])
            layer_draw.text(origin, text, font=font, fill=LABEL_HALO + (255,), stroke_width=halo, stroke_fill=LABEL_HALO + (255,))
            layer_draw.text(origin, text, font=font, fill=self.colors['label'] + (255,))
            if angle != 0:
                layer = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
            image.paste(layer, (int(round(px - layer.size[0] / 2)), int(round(py - layer.size[1] / 2))), layer)

    def get_labels(self, roam):
        res = []
        for label in state_val(self.props, 'mapLabels', []) or []:
            text = (state_val(label, 'text', '') or '').strip().upper()
            point = state_val(label, 'point', None)
            maps = enum_index(label, 'maps')  # 0: all the maps, 1: roam map only, 2: race maps only
            if text == '' or not isinstance(point, dict) or maps == (2 if roam else 1):
                continue
            pos = state_vector(point, 'localPosition')
            size = positive(state_val(label, 'size'), DEFAULT_LABEL_SIZE)
            angle = float(state_val(label, 'angle', 0) or 0)
            res.append((-pos['x'], pos['z'], text, size, angle))
        return res

    # Hudmap

    def write_pkg(self, path, tiles):
        # tiles: [(texture, x0, z0, x1, z1)], a quad for each one (same layout as hudmap_sf.pkg)
        file = BinaryFileHelper(path, 'wb')
        file.write_raw_string("PKG3")

        def begin_chunk(name):
            file.write_raw_string("FILE")
            file.write_string(name)
            pos = file.tell()
            file.write_uint32(0)
            return pos

        def end_chunk(pos):
            end = file.tell()
            file.seek(pos)
            file.write_uint32(end - pos - 4)
            file.seek(end)

        inset = 1.0 / self.tile_size
        chunk = begin_chunk("H")
        file.write_uint32(len(tiles))
        file.write_uint32(4 * len(tiles))
        file.write_uint32(6 * len(tiles))
        file.write_uint32(len(tiles))
        file.write_uint32(0x102)  # FVF: position, uv
        for i, (texture, x0, z0, x1, z1) in enumerate(tiles):
            file.write_uint16(1)  # strips
            file.write_uint16(0)  # flags
            file.write_uint32(i)  # shader
            file.write_uint32(3)  # primitive type: triangles
            file.write_uint32(4)
            # u grows with x, v with the north (-z), as in hudmap_sf.pkg
            for x, z, u, v in [(x0, z0, inset, 1 - inset), (x0, z1, inset, inset),
                               (x1, z0, 1 - inset, 1 - inset), (x1, z1, 1 - inset, inset)]:
                file.write_float(x)
                file.write_float(0.0)
                file.write_float(z)
                file.write_float(u)
                file.write_float(v)
            file.write_uint32(6)
            for index in (0, 1, 2, 3, 2, 1):
                file.write_uint16(index)
        end_chunk(chunk)

        chunk = begin_chunk("shaders")
        file.write_uint32(0x80 | 1)
        file.write_uint32(len(tiles))
        for texture, *_ in tiles:
            file.write_string(texture)
            for color in [(255, 255, 255, 255), (229, 229, 229, 255), (0, 0, 0, 255)]:
                for c in color:
                    file.write_byte(c)
            file.write_float(0.25)
        end_chunk(chunk)

        chunk = begin_chunk("offset")
        for i in range(3):
            file.write_float(0.0)
        end_chunk(chunk)
        file.close()

    def export_hudmap(self, shapes):
        bounds = shapes.bounds()
        if bounds is None:
            print("Warning: the city has nothing to draw, no hudmap exported")
            return False
        city = self.layout.city_name
        span = self.tile_size * self.meters_per_pixel
        cx, cz = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
        nx = max(1, math.ceil((bounds[2] - bounds[0] + 2 * self.margin) / span))
        nz = max(1, math.ceil((bounds[3] - bounds[1] + 2 * self.margin) / span))
        if nx * nz > MAX_TILES:
            print("Warning: the hudmap has " + str(nx) + "x" + str(nz) + " tiles of " + str(self.tile_size)
                  + " pixels, increase its meters per pixel or the tile size to have at most " + str(MAX_TILES))
        x0, z0 = cx - nx * span / 2, cz - nz * span / 2

        preview = Image.new('RGB', (nx * self.tile_size, nz * self.tile_size), self.colors['water'])
        drawn = [c for c in DRAW_ORDER if c != 'water']
        tiles = []
        texture_dir = None
        for iz in range(nz):
            for ix in range(nx):
                rect = (x0 + ix * span, z0 + iz * span, x0 + (ix + 1) * span, z0 + (iz + 1) * span)
                if all(len(shapes.in_rect(c, rect)) == 0 for c in drawn):
                    continue  # only water: the ocean color of the HUD
                image = self.render(shapes, rect, (self.tile_size, self.tile_size))
                preview.paste(image, (ix * self.tile_size, iz * self.tile_size))
                texture = (city + "_hudmap" + str(len(tiles))).lower()
                texture_dir = texture_dir or self.layout.dir('texture')
                # the rows of .tex files go from the bottom of the image (v = 0) to the top (the north, v = 1)
                stored = image.transpose(Image.FLIP_TOP_BOTTOM)
                write_image(os.path.join(texture_dir, texture + ".tex"), stored)
                write_image(os.path.join(texture_dir, texture + "_ni.tex"), stored)
                tiles.append((texture,) + rect)
        self.write_pkg(os.path.join(self.layout.dir('geometry'), "hudmap_" + city + ".pkg"), tiles)
        water = self.colors['water']
        with open(os.path.join(self.layout.dir('tune'), city + ".mmHudMap"), 'w', newline='\r\n') as f:
            f.write(MMHUDMAP.format(water[0] / 255, water[1] / 255, water[2] / 255))
        preview.save(os.path.join(self.layout.root, city + "_hudmap_preview.png"))
        print("Hudmap exported! (" + str(len(tiles)) + " tiles of " + str(self.tile_size) + " pixels, "
              + str(self.meters_per_pixel) + " m per pixel)")
        return True

    # Race maps

    def fit_rect(self, bounds, margin, min_size):
        # the rectangle around the bounds with the aspect of the map in the race map images
        w = max(bounds[2] - bounds[0], min_size) * (1 + margin)
        h = max(bounds[3] - bounds[1], min_size) * (1 + margin)
        aspect = (RACE_MAP_RECT[2] - RACE_MAP_RECT[0]) / (RACE_MAP_RECT[3] - RACE_MAP_RECT[1])
        if w / h > aspect:
            h = w / aspect
        else:
            w = h * aspect
        cx, cz = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
        return (cx - w / 2, cz - h / 2, cx + w / 2, cz + h / 2)

    def get_frame(self):
        path = os.path.join(self.common_dir, 'jpg', 'mapframe.jpg')
        if os.path.exists(path):
            try:
                return Image.open(path).convert('RGB').resize(RACE_MAP_SIZE)
            except OSError:
                print("Warning: " + path + " could not be read, the race maps have a plain frame")
        return Image.new('RGB', RACE_MAP_SIZE, FRAME_COLOR)

    def write_race_map(self, shapes, rect, name, labels, markers=None):
        size = (RACE_MAP_RECT[2] - RACE_MAP_RECT[0], RACE_MAP_RECT[3] - RACE_MAP_RECT[1])
        image = self.render(shapes, rect, size, markers, outline=False)
        self.draw_labels(image, rect, labels)
        res = self.get_frame()
        res.paste(image, RACE_MAP_RECT[:2])
        res.save(os.path.join(self.layout.dir('jpg'), self.layout.city_name + "_map" + name + ".jpg"), quality=90)

    def get_races(self):
        # (race id, start and checkpoint positions), with the ids of the race folder (see cinfo_aimap_export.py)
        res = []
        for key, prefix in [('blitzRaces', 'blitz'), ('circuitRaces', 'circuit'), ('checkpointRaces', 'race')]:
            for i, race in enumerate(state_val(self.props, key, []) or []):
                points = []
                for c in state_val(race, 'checkpoints', []) or []:
                    pos = state_vector(state_val(c, 'checkpoint', {}), 'localPosition')
                    points.append((-pos['x'], pos['z']))
                res.append((prefix + str(i), points))
        return res

    def export_race_maps(self, shapes):
        bounds = shapes.bounds()
        if bounds is None:
            return
        self.write_race_map(shapes, self.fit_rect(bounds, 0.02, 0), "roam", self.get_labels(True))
        races = self.get_races()
        labels = self.get_labels(False)
        for race_id, points in races:
            if len(points) == 0:
                print("Warning: the race " + race_id + " has no checkpoints, its map shows the whole city")
                rect = self.fit_rect(bounds, 0.02, 0)
            else:
                xs, zs = [p[0] for p in points], [p[1] for p in points]
                rect = self.fit_rect((min(xs), min(zs), max(xs), max(zs)), RACE_MAP_MARGIN, RACE_MAP_MIN_SIZE)
            # the start over the checkpoints
            markers = [(x, z, MARKER_CHECKPOINT) for x, z in points[1:]] + [(x, z, MARKER_START) for x, z in points[:1]]
            self.write_race_map(shapes, rect, race_id, labels, markers)
        print("Race maps exported! (roam and " + str(len(races)) + " races)")

    def export(self):
        shapes = self.get_shapes()
        if self.verbose:
            print("Hudmap triangles: " + ", ".join(c + " " + str(len(t)) for c, t in shapes.triangles.items()))
        if self.export_hudmap(shapes):
            self.export_race_maps(shapes)
