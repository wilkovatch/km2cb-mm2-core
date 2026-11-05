"""Generates the model of a movable bridge from the roads its controls are attached to, and assigns it to the bridge.

The top of the leaf is the cross section of the road (with its textures), the rest is made as the stock giz_bridge01_l
and giz_waterloo_l: a railing on each side (a 0.25 m wide box, 1.5 m high), and below the level of the hinge a truss
1.8 m deep on the sides and the ends, with a plate under the road and a bottom seen through the cutouts of the truss,
with the same texture coordinates, so that other textures should be laid out as the stock ones.

The game draws both leaves of a pair with the same model (one path has one model name), turned by 180 degrees: so the
model has one cross section, the widest one when two roads differ, and is sheared by one angle, the mean of the two.
The files are named after their contents, as the low LOD textures: a change gives a new model, so the editor loads it.
"""
import hashlib
import math
import os
from pathlib import Path
import struct
import sys

CORE = Path(__file__).resolve().parents[2]
sys.path.append(str(CORE / 'exporters' / 'psdl'))
import custom_element_conversion as cec
from bridge_export import generated_tuning, DEFAULT_TRUSS_TEXTURE, DEFAULT_BOTTOM_TEXTURE, DEFAULT_RAIL_TEXTURE
from common.pkg_writer import PKGWriter
from utils import state_bool, state_int, state_val

# gizBridge::UpdateMatrix (577620) adds a world offset of -0.3: the hinge height is at this height in the model, as the top
# of the sidewalks in the stock models. It's also where the curve of a road is (with the road 0.15 m below it, see hVal)
HINGE_HEIGHT = 0.3
CURB_HEIGHT = 0.15  # hVal of the road type
RAIL_WIDTH = 0.25
RAIL_HEIGHT = 1.5
BOTTOM = HINGE_HEIGHT - 1.8
WEDGE_HEIGHT, WEDGE_SIDE = 1.0, 0.5  # divider_wedged of the road type
MIN_LENGTH = 1.0
MAX_ANGLE = 60.0  # degrees between a road and the bridge: past this it's a mistake, and the model would be very narrow

# The meters per tile and the texture coordinates of the stock models
SIDE_TILE, SIDE_V_TOP, SIDE_V_BOTTOM = 5.0, -0.145, 0.994
END_TILE, END_V_TOP, END_V_BOTTOM = 3.7, 0.999, 0.001
BOTTOM_TILE, BOTTOM_ACROSS_TILE = 5.0, 4.625
PLATE_TILE, PLATE_ACROSS_TILE = 6.0, 6.167
RAIL_TILE, RAIL_V_BOTTOM, RAIL_V_TOP = 2.5, 0.461, 0.961
RAIL_TOP_V = (0.927, 0.945)
RAIL_END_U, RAIL_END_V = (0.91, 1.058), (0.452, 0.99)
CURB_V = (0.986, 0.948)


class Strip:
    # a piece of the top of the road across it: from (s0, y0) to (s1, y1), s along the section from left to right,
    # y from the hinge height, with the texture coordinate across it and the meters along the road for a tile
    def __init__(self, s0, y0, s1, y1, texture, v0, v1, tile):
        self.s0, self.y0, self.s1, self.y1 = s0, y0, s1, y1
        self.texture, self.v0, self.v1, self.tile = texture, v0, v1, tile


def texture_name(path):
    # the name in a PKG: without folder and extension
    return Path(str(path).replace('\\', '/')).stem.lower() if path else ''


def divider_strips(state, road_y, half, road):
    # see the divider components of the road type
    divider = state_int(state, 'divider')
    param = float(state_val(state, 'dividerParam', 0) or 0)

    def texture(key):
        return texture_name(state_val(state, key)) or road
    if divider == 1:
        return [Strip(-half, road_y, half, road_y, texture('texture3'), 1, 1 - param, 1.0)]
    if divider == 2:
        side = min(max(param, 0), half)
        top = road_y + side
        return [Strip(-half, road_y, -half, top, texture('texture2'), 0, 1, 1.0),
                Strip(-half, top, -half + side, top, texture('texture3'), 0, 1, 1.0),
                Strip(-half + side, top, half - side, top, texture('texture4'), 0, 1, 1.0),
                Strip(half - side, top, half, top, texture('texture3'), 1, 0, 1.0),
                Strip(half, top, half, road_y, texture('texture2'), 1, 0, 1.0)]
    side = min(WEDGE_SIDE, half)
    top = road_y + WEDGE_HEIGHT
    return [Strip(-half, road_y, -half + side, top, texture('texture3'), 0, 1, 1.0),
            Strip(-half + side, top, half - side, top, texture('texture4'), 0, 1, 1.0),
            Strip(half - side, top, half, road_y, texture('texture3'), 1, 0, 1.0)]


def road_profile(state):
    """The top of the road from left to right, as its type builds it: (strips, half of the total width, height of its edges)."""
    double = state_bool(state, 'isDouble')
    flat = state_bool(state, 'flatSidewalk')
    with_sides = double and state_bool(state, 'hasSidewalks')
    sidewalks = with_sides and not flat
    shoulders = with_sides and flat
    apply_height = state_bool(state, 'applyHeightAnyway')
    raised = apply_height if shoulders else state_bool(state, 'hasSidewalks') or apply_height
    road_y = -CURB_HEIGHT if raised else 0.0
    edge_y = 0.0 if sidewalks else road_y
    total = float(state_val(state, 'totalWidth', 0) or 0)
    width = float(state_val(state, 'roadWidth', 0) or 0) if with_sides else total
    if total <= 0 or width <= 0 or width > total:
        raise cec.ConversionError('BRIDGE_MESH_ERROR_WIDTHS')
    road = texture_name(state_val(state, 'texture1'))
    side = texture_name(state_val(state, 'texture0'))
    half_total, half_road = total * 0.5, width * 0.5
    side_width = half_total - half_road
    divider = state_int(state, 'divider') if double else 0
    half_divider = float(state_val(state, 'dividerWidth', 0) or 0) * 0.5 if divider > 0 else 0
    if half_divider >= half_road:
        raise cec.ConversionError('BRIDGE_MESH_ERROR_WIDTHS')
    strips = []
    if side_width > 0:
        # the stock sidewalks have their texture coordinate from 0 inside to 1 outside
        strips.append(Strip(-half_total, edge_y, -half_road, edge_y, side, 1, 0, side_width))
        if sidewalks:
            strips.append(Strip(-half_road, 0, -half_road, road_y, side, CURB_V[0], CURB_V[1], side_width))
    # as the road type: the texture of a double road has the center in its top row, the one of a single road is across all of it
    if not double:
        strips.append(Strip(-half_road, road_y, half_road, road_y, road, 1, 0, width))
    else:
        strips.append(Strip(-half_road, road_y, -half_divider, road_y, road, 1, 0, half_road))
        if divider > 0 and half_divider > 0:
            strips += divider_strips(state, road_y, half_divider, road)
        strips.append(Strip(half_divider, road_y, half_road, road_y, road, 0, 1, half_road))
    if side_width > 0:
        if sidewalks:
            strips.append(Strip(half_road, road_y, half_road, 0, side, CURB_V[1], CURB_V[0], side_width))
        strips.append(Strip(half_road, edge_y, half_total, edge_y, side, 0, 1, side_width))
    return strips, half_total, edge_y


def tiles(length, tile):
    # a whole number of tiles, as along the roads
    return max(1, round(length / tile))


def game_vector(v):
    # the X mirror of the exported coordinates, in the horizontal plane, with unit length
    length = math.hypot(v[0], v[2])
    return (-v[0] / length, v[2] / length) if length > 1e-6 else None


def road_angle(direction, start, finish):
    """The signed angle (radians) of the end of a road from the frame of the leaf at the start (577d10): Z from the other hinge, X = up x Z."""
    road = game_vector(direction)
    z = game_vector([start[i] - finish[i] for i in range(3)])
    if road is None or z is None:
        return 0.0
    across = (road[1], -road[0])  # up x the direction of the road
    x = (z[1], -z[0])
    sin = across[0] * z[0] + across[1] * z[1]
    cos = across[0] * x[0] + across[1] * x[1]
    if cos < 0:
        sin, cos = -sin, -cos  # the road can go either way
    return math.atan2(sin, cos)


class Mesh:
    # the sections of a model: one per texture, in the order they are added
    def __init__(self):
        self.sections = {}
        self.solids = []

    def face(self, texture, points, uvs, solid=True):
        # triangles counterclockwise from the visible side (right handed coordinates of the game), with a flat normal
        a, b, c = points[0], points[1], points[2]
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        length = math.sqrt(sum(n * n for n in normal))
        if length < 1e-9:
            return
        normal = tuple(n / length for n in normal)
        section = self.sections.setdefault(texture, dict(vertices=[], indices=[]))
        first = len(section['vertices'])
        section['vertices'] += [(tuple(p), normal, tuple(uv)) for p, uv in zip(points, uvs)]
        for i in range(1, len(points) - 1):
            section['indices'] += [first, first + i, first + i + 1]
            if solid:
                self.solids.append((points[0], points[i], points[i + 1]))


class Leaf:
    # the shape of the model: s along the section of the road, t = 1 at the hinge and -1 at the tip
    def __init__(self, length, angle):
        self.length = length
        self.cos, self.sin = math.cos(angle), math.sin(angle)

    def at(self, s, y, t):
        return (s * self.cos, y + HINGE_HEIGHT, t * self.length * 0.5 + s * self.sin)

    def along(self, tile):
        return tiles(self.length, tile)

    def strip(self, mesh, strip):
        u = self.along(strip.tile)
        mesh.face(strip.texture, [self.at(strip.s0, strip.y0, 1), self.at(strip.s1, strip.y1, 1),
                                  self.at(strip.s1, strip.y1, -1), self.at(strip.s0, strip.y0, -1)],
                  [(0, strip.v0), (0, strip.v1), (u, strip.v1), (u, strip.v0)])

    def wall(self, mesh, texture, s, y0, y1, facing, v0, v1, tile):
        # along the leaf, its visible side towards the positive (facing 1) or negative (-1) s
        u = self.along(tile)
        points = [(self.at(s, y0, 1), (0, v0)), (self.at(s, y0, -1), (u, v0)), (self.at(s, y1, -1), (u, v1)), (self.at(s, y1, 1), (0, v1))]
        if facing < 0:
            points = [points[1], points[0], points[3], points[2]]
        mesh.face(texture, [p[0] for p in points], [p[1] for p in points])

    def rail(self, mesh, texture, inner, outer, y):
        side = 1 if outer > inner else -1
        top = y + RAIL_HEIGHT
        u = self.along(RAIL_TILE)
        self.wall(mesh, texture, outer, y, top, side, RAIL_V_BOTTOM, RAIL_V_TOP, RAIL_TILE)
        self.wall(mesh, texture, inner, y, top, -side, RAIL_V_BOTTOM, RAIL_V_TOP, RAIL_TILE)
        left, right = min(inner, outer), max(inner, outer)
        v_left, v_right = (RAIL_TOP_V[1], RAIL_TOP_V[0]) if side < 0 else RAIL_TOP_V
        mesh.face(texture, [self.at(left, top, 1), self.at(right, top, 1), self.at(right, top, -1), self.at(left, top, -1)],
                  [(1, v_left), (1, v_right), (0, v_right), (0, v_left)])
        # the ends, with the part of the texture on the side of the stock models
        u_left, u_right = (RAIL_END_U[1], RAIL_END_U[0]) if side < 0 else RAIL_END_U
        mesh.face(texture, [self.at(left, y, 1), self.at(right, y, 1), self.at(right, top, 1), self.at(left, top, 1)],
                  [(u_left, RAIL_END_V[0]), (u_right, RAIL_END_V[0]), (u_right, RAIL_END_V[1]), (u_left, RAIL_END_V[1])])
        mesh.face(texture, [self.at(right, y, -1), self.at(left, y, -1), self.at(left, top, -1), self.at(right, top, -1)],
                  [(u_right, RAIL_END_V[0]), (u_left, RAIL_END_V[0]), (u_left, RAIL_END_V[1]), (u_right, RAIL_END_V[1])])

    def under(self, mesh, texture, half, y, tile, across, solid=True):
        # facing down: the plate under the road and the bottom
        u, v = self.along(tile), max(1, round(2 * half / across))
        mesh.face(texture, [self.at(half, y, -1), self.at(half, y, 1), self.at(-half, y, 1), self.at(-half, y, -1)],
                  [(u, 0), (0, 0), (0, v), (u, v)], solid)

    def end_faces(self, mesh, texture, outline, half):
        # at the hinge and at the tip, from the bottom to the top of the road
        per_meter = max(1, round(2 * half / END_TILE)) / (2 * half)
        bottom = BOTTOM - HINGE_HEIGHT

        def v(y):
            return END_V_BOTTOM + (y - bottom) / -bottom * (END_V_TOP - END_V_BOTTOM)

        def u(s):
            return (s + half) * per_meter
        for (s0, y0), (s1, y1) in zip(outline, outline[1:]):
            if s1 <= s0:
                continue
            mesh.face(texture, [self.at(s0, bottom, 1), self.at(s1, bottom, 1), self.at(s1, y1, 1), self.at(s0, y0, 1)],
                      [(u(s0), END_V_BOTTOM), (u(s1), END_V_BOTTOM), (u(s1), v(y1)), (u(s0), v(y0))])
            mesh.face(texture, [self.at(s1, bottom, -1), self.at(s0, bottom, -1), self.at(s0, y0, -1), self.at(s1, y1, -1)],
                      [(u(s1), END_V_BOTTOM), (u(s0), END_V_BOTTOM), (u(s0), v(y0)), (u(s1), v(y1))])


def build_lods(state, truss, bottom, rail, length, angle):
    """The meshes of the model: {part: Mesh} as the stock models, the last one (VL) without railings and with the low LOD texture of the road."""
    strips, half_road, edge_y = road_profile(state)
    half = half_road + RAIL_WIDTH
    leaf = Leaf(length, angle)
    bottom_y = BOTTOM - HINGE_HEIGHT
    outline = [(-half, edge_y), (-half_road, edge_y)]
    for strip in strips:
        outline += [(strip.s0, strip.y0), (strip.s1, strip.y1)]
    outline += [(half_road, edge_y), (half, edge_y)]
    plate_y = min(strip.y0 for strip in strips)

    def under_and_truss(mesh):
        leaf.wall(mesh, truss, half, bottom_y, edge_y, 1, SIDE_V_BOTTOM, SIDE_V_TOP, SIDE_TILE)
        leaf.wall(mesh, truss, -half, bottom_y, edge_y, -1, SIDE_V_BOTTOM, SIDE_V_TOP, SIDE_TILE)
        leaf.under(mesh, truss, half, bottom_y, BOTTOM_TILE, BOTTOM_ACROSS_TILE)

    full = Mesh()
    # the order of the sections of the stock models: the textures with a cutout at the end
    for side in (-1, 1):
        leaf.rail(full, rail, side * half_road, side * half, edge_y)
    leaf.under(full, bottom, half, plate_y, PLATE_TILE, PLATE_ACROSS_TILE, solid=False)
    for strip in strips:
        leaf.strip(full, strip)
    under_and_truss(full)
    leaf.end_faces(full, truss, outline, half)

    far = Mesh()
    leaf.under(far, bottom, half, plate_y, PLATE_TILE, PLATE_ACROSS_TILE, solid=False)
    low = texture_name(state_val(state, 'textureLOD'))
    if low:
        far.face(low, [leaf.at(-half, edge_y, 1), leaf.at(half, edge_y, 1), leaf.at(half, edge_y, -1), leaf.at(-half, edge_y, -1)],
                 [(0, 0), (0, 1), (leaf.along(2 * half), 1), (leaf.along(2 * half), 0)])
    else:
        for strip in strips:
            leaf.strip(far, strip)
    under_and_truss(far)
    return dict(H=full, M=full, L=full, VL=far)


def pkg_string(text):
    # as the strings of the PKG files: the length with the terminator, then the terminator
    data = text.encode('ascii')
    return (bytes([len(data) + 1]) + data if data else b'') + b'\0'


def chunk(name, data):
    return b'FILE' + pkg_string(name) + struct.pack('<I', len(data)) + data


def pkg_bytes(lods):
    shaders = []
    for mesh in lods.values():
        for texture in mesh.sections:
            if texture not in shaders:
                shaders.append(texture)
    res = b'PKG3'
    for name, mesh in lods.items():
        sections = list(mesh.sections.items())
        total_vertices = sum(len(s['vertices']) for _, s in sections)
        total_indices = sum(len(s['indices']) for _, s in sections)
        data = struct.pack('<5I', len(sections), total_vertices, total_indices, len(sections), 0x112)  # position, normal, uv
        for texture, section in sections:
            data += struct.pack('<2H3I', 1, 0, shaders.index(texture), 3, len(section['vertices']))  # one list of triangles
            for position, normal, uv in section['vertices']:
                data += struct.pack('<8f', *position, *normal, *uv)
            data += struct.pack('<I', len(section['indices'])) + struct.pack('<' + str(len(section['indices'])) + 'H', *section['indices'])
        res += chunk(name, data)
    # one paintjob of byte shaders, with the values of the stock bridges
    data = struct.pack('<2I', 0x80 | 1, len(shaders))
    for texture in shaders:
        data += pkg_string(texture) + bytes((255, 255, 255, 255, 229, 229, 229, 255, 0, 0, 0, 255)) + struct.pack('<f', 0.25)
    res += chunk('shaders', data)
    return res + chunk('offset', struct.pack('<3f', 0, 0, 0))


def bound(mesh):
    # welded vertices and triangles, as the PKG writer
    vertices, indices, triangles = [], {}, []
    for triangle in mesh.solids:
        ids = []
        for point in triangle:
            key = tuple(round(c, 4) for c in point)
            if key not in indices:
                indices[key] = len(vertices)
                vertices.append(point)
            ids.append(indices[key])
        if len(set(ids)) == 3:
            triangles.append((ids[0], ids[1], ids[2], 0))
    return vertices, triangles


def write_model(city_folder, state, truss, bottom, rail, length, angle):
    """Writes the files of the model in the folders of the city, returns its path relative to the city."""
    lods = build_lods(state, truss, bottom, rail, length, angle)
    data = pkg_bytes(lods)
    name = 'bridge_' + hashlib.sha1(data).hexdigest()[:8]  # short: the game has a limit for the name with the behavior
    folders = {key: os.path.join(city_folder, *key.split('/')) for key in ('geometry', 'bound', 'tune/banger')}
    for folder in folders.values():
        os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folders['geometry'], name + '.pkg'), 'wb') as f:
        f.write(data)
    vertices, triangles = bound(lods['H'])
    PKGWriter.write_bnd(None, os.path.join(folders['bound'], name + '_BOUND.bnd'), vertices, triangles, ['default'])
    points = [v[0] for mesh in lods.values() for s in mesh.sections.values() for v in s['vertices']]
    # the game uses Size.z as the distance of the two ends of the leaf: the mesh is longer at an angle
    size = [max(p[0] for p in points) - min(p[0] for p in points), max(p[1] for p in points) - min(p[1] for p in points), length]
    with open(os.path.join(folders['tune/banger'], name + '.dgBangerData'), 'w', encoding='ascii', newline='\n') as f:
        f.write(generated_tuning(size))
    return 'geometry/' + name + '.pkg'


def attached_road(point, data):
    anchor = point.get('anchor')
    if not anchor or anchor.get('kind') != 'road':
        return None
    road = next((r for r in data['roads'] if r['id'] == anchor['id']), None)
    return (road, anchor.get('insideDirection')) if road else None


def generate(element, data):
    state = element['data']['fields']['state']
    start, finish = element['points']['start'], element['points']['finish']
    attached = [item for item in (attached_road(start, data), attached_road(finish, data)) if item]
    if not attached:
        raise cec.ConversionError('BRIDGE_MESH_ERROR_NO_ROADS')
    a, b = start['position'], finish['position']
    distance = math.hypot(a[0] - b[0], a[2] - b[2])
    length = distance * 0.5 if state_val(state, 'paired', True) else distance
    if length < MIN_LENGTH:
        raise cec.ConversionError('BRIDGE_MESH_ERROR_LENGTH')
    angle = sum(road_angle(direction, a, b) for _, direction in attached) / len(attached)
    if abs(angle) > math.radians(MAX_ANGLE):
        raise cec.ConversionError('BRIDGE_MESH_ERROR_ANGLE')
    road_state = max((road['data']['fields']['state'] for road, _ in attached), key=lambda s: float(state_val(s, 'totalWidth', 0) or 0))
    textures = [texture_name(state_val(state, key) or default) for key, default in (
        ('trussTexture', DEFAULT_TRUSS_TEXTURE), ('bottomTexture', DEFAULT_BOTTOM_TEXTURE), ('railTexture', DEFAULT_RAIL_TEXTURE))]
    return write_model(data['cityFolder'], road_state, *textures, length, angle), length


def convert(data):
    out = cec.Output()
    for target in data['convert']:
        element = next((e for e in data['customElements'] if e['id'] == target['id']), None)
        if element is None:
            raise cec.ConversionError('CONVERSION_ERROR_MISSING')
        path, length = generate(element, data)
        out.updates.append({'element': {'kind': 'customElement', 'id': target['id']},
                            'state': {'mesh': path, 'generatedMesh': path, 'generatedLength': length}})
    return out, False


if __name__ == '__main__':
    cec.run(sys.argv, convert)
