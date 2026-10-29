# The low-level elements of the city (elements/lowLevel of the core): the PSDL room attributes, the rooms containing
# them and the BAI roads and intersections. They are turned into the parts the PSDL writer reads (see psdl_parts.py),
# like the procedural elements in json_processor.py: each room is a block, the parts outside of a room (or in a group
# of building parts) go in the block found where they are, as the procedural buildings.

import math
import numpy as np
from collections import defaultdict
from psdl_parts import ExportedCityElement, get_tex, strip_indices, section_indices, texture_list
from utils import state_val, state_bool, state_int
from common import report

# the types of the PSDL attributes, the containers and the traffic
ATTRIBUTE_TYPES = ["roadWithSidewalks", "roadWithoutSidewalks", "dividedRoad", "roadTunnel", "junctionTunnel", "sidewalkStrip",
                   "sidewalkCap", "crosswalk", "roadTriangleFan", "triangleFan", "roofTriangleFan", "facade", "facadeBound", "sliver"]
ROOM = "room"
BUILDING_GROUP = "buildingGroup"
BAI_ROAD = "baiRoad"
BAI_INTERSECTION = "baiIntersection"

# the parts with a surface (used for the perimeter of a block and to find the block of a position)
SURFACE_PARTS = ["ROADS", "ROADSN", "ROADN", "ROADD", "ROADDN", "SW", "CW", "IS", "BLOCK", "NUL"]

TUNNEL_FLAGS = ["wall", "flatCeiling", "curvedCeiling", "curvedSides", "culled", "closedStartLeft", "closedEndLeft", "closedStartRight",
                "closedEndRight", "offsetStartLeft", "offsetEndLeft", "offsetStartRight", "offsetEndRight"]


def position(point):
    return tuple(point['position'])


def element_type(e):
    return e.get('type')


def element_state(e):
    return e['data']['fields']['state']


def element_name(e):
    return e['data']['name']


def leaves(tree):
    # the points of a tree of control points, in order
    if isinstance(tree, dict):
        if 'position' in tree and 'id' in tree:
            return [tree]
        res = []
        for v in tree.values():
            res.extend(leaves(v))
        return res
    if isinstance(tree, list):
        res = []
        for v in tree:
            res.extend(leaves(v))
        return res
    return []


def center(e):
    points = [position(p) for p in leaves(e.get('points'))] + [position(v) for v in e.get('vertices') or []]
    if len(points) == 0:
        return None
    return tuple(np.mean(np.array(points, dtype=float), axis=0))


def up_triangles(vertices, indices):
    # the triangles facing up, as the meshes of the program (clockwise seen from above): the writer follows the
    # perimeter of a block with the winding of its triangles
    res = []
    for i in range(0, len(indices) - 2, 3):
        a, b, c = (np.array(vertices[indices[i + j]], dtype=float) for j in range(3))
        if np.cross(b - a, c - a)[1] >= 0:
            res.extend([indices[i], indices[i + 1], indices[i + 2]])
        else:
            res.extend([indices[i], indices[i + 2], indices[i + 1]])
    return res


def outline_loops(vertices, indices):
    # the closed outlines of a mesh (its edges used by a single triangle, the vertices at the same place merged); the
    # triangles themselves if the outline isn't made of simple loops
    keys = {}
    ids = []
    for v in vertices:
        k = (round(v[0], 3), round(v[1], 3), round(v[2], 3))
        if k not in keys:
            keys[k] = len(keys)
        ids.append(keys[k])
    positions = [None] * len(keys)
    for v, i in zip(vertices, ids):
        positions[i] = v
    count = defaultdict(int)
    directed = []
    tris = []
    for t in range(0, len(indices) - 2, 3):
        tri = [ids[indices[t]], ids[indices[t + 1]], ids[indices[t + 2]]]
        if len(set(tri)) < 3:
            continue
        tris.append(tri)
        for j in range(3):
            a, b = tri[j], tri[(j + 1) % 3]
            count[(min(a, b), max(a, b))] += 1
            directed.append((a, b))
    following = {}
    simple = True
    for a, b in directed:
        if count[(min(a, b), max(a, b))] == 1:
            if a in following:
                simple = False
            following[a] = b
    loops = []
    if simple:
        done = set()
        for start in following:
            if start in done:
                continue
            loop = []
            cur = start
            while cur not in done:
                done.add(cur)
                loop.append(positions[cur])
                cur = following.get(cur)
                if cur is None:
                    simple = False
                    break
            if not simple:
                break
            if len(loop) >= 3:
                loops.append(loop)
    if not simple:
        return [[positions[i] for i in tri] for tri in tris]
    return loops


def reference(state, name):
    r = state_val(state, name)
    if isinstance(r, dict) and r.get('id', -1) is not None and r.get('id', -1) >= 0:
        return (r.get('kind'), r.get('id'))
    return None


class LowLevelExporter:
    def __init__(self, json_processor):
        self.jp = json_processor
        self.data = json_processor.data
        self.elements = {}
        for e in self.data.get('lowLevelElements') or []:
            self.elements[e['id']] = e
        self.children = defaultdict(list)
        for e in self.elements.values():
            if e.get('containerId', -1) >= 0:
                self.children[e['containerId']].append(e)
        self.room_blocks = {}  # room id -> block
        self.bound_indices = {}  # facade bound id -> the index shared with its facades in the names of the parts
        self.ll_traffic = []  # the BAI intersections, as traffic intersections (see json_processor.get_traffic)
        self.pending_copies = []  # the facade bounds of the rooms to copy in the block in front of them

    def of_type(self, *types):
        return [e for e in sorted(self.elements.values(), key=lambda x: x['id']) if element_type(e) in types]

    def container(self, e):
        return self.elements.get(e.get('containerId', -1))

    def room_of(self, e):
        c = self.container(e)
        return c if c is not None and element_type(c) == ROOM else None

    # Parts

    def parts(self, e, block):
        # the parts of the PSDL writer for an attribute in the block
        typ = element_type(e)
        state = element_state(e)
        name = element_name(e)
        points = e.get('points') or {}
        res = []

        def part(kind, vertices, indices, mat, prefix=''):
            p = ExportedCityElement()
            p.name = prefix + str(block) + '_' + kind
            p.vertices = vertices
            p.indices = indices
            p.mat = mat
            p.properties['original_name'] = name
            if state_bool(state, 'invisible'):
                p.properties['disable'] = '1'
            p.source = ('lowLevel', e['id'])
            res.append(p)
            return p

        def sections(names):
            secs = points.get('sections') or []
            return [[position(s[n]) for n in names] for s in secs]

        if typ == "roadWithSidewalks":
            secs = sections(["leftSidewalk", "leftRoad", "rightRoad", "rightSidewalk"])
            p = part("ROADS", [v for s in secs for v in s], strip_indices(len(secs), 4),
                     texture_list(state_val(state, 'texture'), state_val(state, 'sidewalkTexture'), state_val(state, 'lodTexture')))
            self.road_properties(p, state)
            self.road_props(res, e)
        elif typ == "roadWithoutSidewalks":
            secs = sections(["left", "right"])
            road = state_int(state, 'style') == 1
            if road:
                mat = texture_list(state_val(state, 'texture'), state_val(state, 'sidewalkTexture'), state_val(state, 'lodTexture'))
            else:
                mat = texture_list(state_val(state, 'texture'))
            p = part("ROADSN" if road else "ROADN", [v for s in secs for v in s], strip_indices(len(secs), 2), mat)
            self.road_properties(p, state)
        elif typ == "dividedRoad":
            no_sidewalks = state_bool(state, 'noSidewalks')
            names = ["leftRoad", "leftDivider", "rightDivider", "rightRoad"]
            if not no_sidewalks:
                names = ["leftSidewalk"] + names + ["rightSidewalk"]
            secs = sections(names)
            mat = texture_list(state_val(state, 'texture'), state_val(state, 'sidewalkTexture'), state_val(state, 'lodTexture'),
                               state_val(state, 'dividerSideTexture'), state_val(state, 'dividerFlatTexture'),
                               state_val(state, 'dividerTopTexture'), state_val(state, 'dividerCapTexture'))
            p = part("ROADDN" if no_sidewalks else "ROADD", [v for s in secs for v in s], strip_indices(len(secs), len(names)), mat)
            divider = state_int(state, 'dividerType')
            p.properties['divider_type'] = {1: 'F', 2: 'E', 3: 'W'}.get(divider, 'I')
            p.properties['divider_param'] = str(int(float(state_val(state, 'dividerValue', 0) or 0) * 256))
            caps = (1 if state_bool(state, 'closeStart') else 0) + (2 if state_bool(state, 'closeEnd') else 0)
            p.properties['caps'] = str(caps)
            self.road_properties(p, state)
            self.road_props(res, e)
        elif typ == "roadTunnel":
            road = reference(state, 'road')
            p = part("RAIL", [], [], self.tunnel_textures(state))
            self.tunnel_properties(p, state)
            p.properties['has_left'] = '1' if state_bool(state, 'leftSide') else '0'
            p.properties['has_right'] = '1' if state_bool(state, 'rightSide') else '0'
            if road is not None:
                p.properties['road_name'] = 'll' + str(road[1])  # see order_rails
        elif typ == "junctionTunnel":
            vertices = []
            indices = []
            for wall in points.get('walls') or []:
                line = [position(q) for q in wall.get('points') or []]
                start = len(vertices)
                # a vertical strip along the wall: consecutive points are in the same faces, the writer puts a wall
                # on the edges of the perimeter between them
                for v in line:
                    vertices.append(v)
                    vertices.append((v[0], v[1] + 1.0, v[2]))
                for j in range(len(line) - 1):
                    indices.extend(start + i for i in section_indices(0, 2, j))
            p = part("RAILC", vertices, indices, self.tunnel_textures(state))
            self.tunnel_properties(p, state)
        elif typ == "sidewalkStrip":
            secs = sections(["outer", "inner"])
            part("SW", [v for s in secs for v in s], strip_indices(len(secs), 2, False), texture_list(state_val(state, 'texture')))
        elif typ == "sidewalkCap":
            a, b = position(points['a']), position(points['b'])
            p = part("SW", [b, a, b, a], [0, 1, 2], texture_list(state_val(state, 'texture')))
            p.properties['cap'] = {1: 'start', 2: 'end'}.get(state_int(state, 'which'), 'both')
        elif typ == "crosswalk":
            # the PSDL keeps the order of the corners, the triangles (for the perimeter) follow them around the rectangle
            vertices = [position(points[k]) for k in ["p1", "p2", "p3", "p4"]]
            c = np.mean(np.array(vertices, dtype=float), axis=0)
            around = sorted(range(4), key=lambda i: math.atan2(vertices[i][2] - c[2], vertices[i][0] - c[0]))
            fan = [around[0], around[1], around[2], around[0], around[2], around[3]]
            part("CW", vertices, up_triangles(vertices, fan), texture_list(state_val(state, 'texture')))
        elif typ in ("triangleFan", "roadTriangleFan", "roofTriangleFan"):
            vertices = [position(v) for v in e.get('vertices') or []]
            kind = {"triangleFan": "BLOCK", "roadTriangleFan": "IS", "roofTriangleFan": "ROOF"}[typ]
            if typ == "triangleFan" and state_bool(state, 'perimeterOnly'):
                kind = "NUL"
            part(kind, vertices, list(e.get('triangles') or []), texture_list(state_val(state, 'texture')))
        elif typ in ("facade", "facadeBound", "sliver"):
            corners = [position(points[k]) for k in ["bottomLeft", "bottomRight", "topLeft", "topRight"]]
            if typ == "facadeBound":
                index = self.facade_index(e['id'])
                part("FACB", corners, [0, 2, 1, 1, 2, 3], 'NONE', 'f' + str(index) + '*,')
            elif typ == "facade":
                bound = reference(state, 'bound')
                index = self.facade_index(bound[1]) if bound is not None and bound[0] == 'lowLevel' else self.facade_index(None)
                p = part("FAC", corners, [0, 2, 1, 1, 2, 3], texture_list(state_val(state, 'texture')), 'f' + str(index) + '+,')
                p.properties['u_tiling'] = str(max(1, state_int(state, 'uRepeat')))
                p.properties['v_tiling'] = str(max(1, state_int(state, 'vRepeat')))
            else:
                p = part("SLIVER", corners, [0, 2, 1, 1, 2, 3], texture_list(state_val(state, 'texture')))
                # as drawn in the editor (lua/psdl.lua): 1 if the scale is not positive
                scale = float(state_val(state, 'textureScale', 0) or 0)
                p.properties['tiling'] = str(int(round((scale if scale > 0 else 1) * 100)))
        return res

    def facade_index(self, bound_id):
        # the index naming a facade bound and its facades (the bound comes first, then its facades, see psdl_parts.py)
        if bound_id is not None and bound_id in self.bound_indices:
            return self.bound_indices[bound_id]
        index = self.jp.cur_facade_index
        self.jp.cur_facade_index += 1
        if bound_id is not None:
            self.bound_indices[bound_id] = index
        return index

    def road_properties(self, p, state):
        p.properties['original_id'] = 'll' + str(p.source[1])
        if state_bool(state, 'noCoplanarFix'):
            p.properties['no_coplanar_fix'] = '1'
        rule = self.jp.get_psdl_prop_rule(state_val(state, 'propRule'))
        if rule is not None:
            p.properties['prop_rule'] = rule

    def road_props(self, res, e):
        # the props of the containers of the prop rule that are not psdl, as placed in the editor along the prop lines of
        # the geometry (the psdl ones are the prop rule of the attribute, see road_properties)
        self.jp.get_road_props(res, e, state_val(element_state(e), 'propRule'), element_name(e))

    def tunnel_textures(self, state):
        return texture_list(*[state_val(state, 'texture' + str(i)) for i in range(6)])

    def tunnel_properties(self, p, state):
        def flag(name):
            return '1' if state_bool(state, name) else '0'
        p.properties['is_wall'] = flag('wall')
        p.properties['is_flat_gallery'] = flag('flatCeiling')
        p.properties['is_curved_gallery'] = flag('curvedCeiling')
        p.properties['curved_sides'] = flag('curvedSides')
        p.properties['is_rail'] = flag('culled')
        p.properties['cap_start_left'] = flag('closedStartLeft')
        p.properties['cap_end_left'] = flag('closedEndLeft')
        p.properties['cap_start_right'] = flag('closedStartRight')
        p.properties['cap_end_right'] = flag('closedEndRight')
        p.properties['offset_start_left'] = flag('offsetStartLeft')
        p.properties['offset_end_left'] = flag('offsetEndLeft')
        p.properties['offset_start_right'] = flag('offsetStartRight')
        p.properties['offset_end_right'] = flag('offsetEndRight')
        p.properties['height'] = str(int(float(state_val(state, 'height', 0) or 0) * 256.0))

    @staticmethod
    def order_attributes(elements):
        # the facade bounds first, so that their facades get the same index
        return sorted(elements, key=lambda e: (0 if element_type(e) == "facadeBound" else 1, e['id']))

    @staticmethod
    def surface_polygons(parts):
        # the outlines of the parts with a surface (as the polygons of the blocks of the procedural elements), to find
        # the block of a position
        res = []
        for p in parts:
            if p.part_type() not in SURFACE_PARTS:
                continue
            res.extend(outline_loops(p.vertices, p.indices))
        return res

    # Rooms and blocks

    def guarded(self, res, e, function):
        # an element failing is reported and left out (see json_processor.guarded_element)
        n = len(res)
        try:
            function()
        except Exception:
            if not report.collecting():
                raise
            del res[n:]
            report.exception(element_name(e) + " not exported", element=element_name(e), kind='lowLevel')

    def room_parts(self, room, block):
        # the parts of the attributes of a room in the block, its manual perimeter last (see perimeter_part)
        parts = []
        for child in self.order_attributes(self.children[room['id']]):
            if element_type(child) in ATTRIBUTE_TYPES:
                self.guarded(parts, child, lambda: parts.extend(self.parts(child, block)))
        perimeter = self.perimeter_part(room, block)
        if perimeter is not None:
            parts.append(perimeter)
        return parts

    @staticmethod
    def manual_perimeter(room):
        # the positions of the perimeter of a room set manually (in the order of the file), None if it is automatic
        perimeter = [position(p) for p in leaves((room.get('points') or {}).get('perimeter'))]
        return perimeter if len(perimeter) >= 3 else None

    def perimeter_part(self, room, block):
        # the manual perimeter of a room as a PERIM part (only vertices), None if it is computed from the attributes
        perimeter = self.manual_perimeter(room)
        if perimeter is None:
            return None
        p = ExportedCityElement()
        p.name = str(block) + '_PERIM'
        p.vertices = perimeter
        p.indices = []
        p.mat = 'NONE'
        p.properties['original_name'] = element_name(room)
        p.properties['simplify'] = '1' if state_bool(element_state(room), 'simplifyPerimeter') else '0'
        p.source = ('lowLevel', room['id'])
        return p

    def process_rooms(self, res):
        # each room is a new block with its attributes
        for room in self.of_type(ROOM):
            block = len(self.jp.block_perimeters) + 1
            parts = self.room_parts(room, block)
            if len(parts) == 0:
                continue
            state = element_state(room)
            for p in parts:
                if state_bool(state, 'echo'):
                    p.properties['echo'] = '1'
                if state_bool(state, 'warp'):
                    p.properties['warp'] = '1'
                p.properties['room'] = element_name(room)
            res.extend(parts)
            manual = self.manual_perimeter(room)
            self.jp.add_block_perimeter_multi([manual] if manual is not None else self.surface_polygons(parts), 0)
            self.room_blocks[room['id']] = block
            # the copies of the facade bounds on both sides, once every block is known (see process_unassigned)
            self.pending_copies.extend(p for p in parts if p.part_type() == "FACB"
                                       and state_bool(element_state(self.elements[p.source[1]]), 'bothSides'))

    def process_unassigned(self, res):
        for bound in self.pending_copies:
            res.extend(self.bound_copy(bound))
        self.pending_copies = []
        # the groups of building parts go in the block found at their location (or in front of it, then without the
        # copies of the facade bounds, as the procedural buildings), the attributes in no container in the block found
        # where they are
        for group in self.of_type(BUILDING_GROUP):
            pts = group.get('points') or {}
            both_sides = True
            block = self.jp.find_block(position(pts['location'])) + 1 if 'location' in pts else 0
            if block <= 0 and 'frontLocation' in pts:
                block = self.jp.find_block(position(pts['frontLocation'])) + 1
                both_sides = False
            if block <= 0 and self.jp.ignore_blocks:
                block = 1
            if block <= 0:
                report.warning("the building parts " + element_name(group) + " are outside of every block, skipped", element=element_name(group), kind='lowLevel')
                continue
            for e in self.order_attributes(self.children[group['id']]):
                if element_type(e) in ATTRIBUTE_TYPES:
                    self.guarded(res, e, lambda: res.extend(self.parts_with_copies(e, block, both_sides)))
        for e in self.order_attributes(self.elements.values()):
            if element_type(e) not in ATTRIBUTE_TYPES or self.container(e) is not None:
                continue
            c = center(e)
            if element_type(e) in ("facade", "facadeBound", "sliver"):
                # the center of the bottom edge, a bit inside the building (as for the procedural facades)
                pts = e.get('points') or {}
                if 'bottomLeft' in pts and 'bottomRight' in pts:
                    a, b = np.array(position(pts['bottomLeft'])), np.array(position(pts['bottomRight']))
                    mid = (a + b) * 0.5
                    d = np.cross(b - a, (0, 1, 0))
                    n = np.linalg.norm(d)
                    c = tuple(mid + (d / n) * 0.5) if n > 1e-6 else tuple(mid)
            block = self.jp.find_block(c) + 1 if c is not None else 0
            if block <= 0:
                if self.jp.ignore_blocks:
                    block = 1
                else:
                    report.warning(element_name(e) + " is not in a room and outside of every block, skipped", element=element_name(e), kind='lowLevel')
                    continue
            self.guarded(res, e, lambda: res.extend(self.parts_with_copies(e, block, True)))

    def parts_with_copies(self, e, block, both_sides):
        # the parts, with the copy of a facade bound in the block in front of it if it is on both sides (as
        # json_processor.get_building_side)
        res = self.parts(e, block)
        if not both_sides or element_type(e) != "facadeBound" or not state_bool(element_state(e), 'bothSides'):
            return res
        return res + self.bound_copy(res[0])

    def bound_copy(self, bound):
        # the copy of a facade bound in the block in front of it, if it is another one
        res = []
        block = bound.block()
        v = [np.array(x, dtype=float) for x in bound.vertices]
        mid_front = (v[0] + v[1]) * 0.5
        mid_dir = np.cross(v[1] - v[0], [0, 1, 0])
        n = np.linalg.norm(mid_dir)
        if n < 1e-9:
            return res
        block2 = self.jp.find_block(mid_front - 5 * (mid_dir / n)) + 1
        if block2 > 0 and block2 != block:
            copy = ExportedCityElement()
            copy.__dict__.update(bound.__dict__)
            copy.properties = dict(bound.properties)
            copy.name = bound.name.split(',')[0].rstrip('*') + 'z*,' + str(block2) + '_FACB'
            res.append(copy)
        return res

    # Traffic

    def block_of(self, e):
        room = self.room_of(e)
        if room is not None and room['id'] in self.room_blocks:
            return self.room_blocks[room['id']]
        c = center(e)
        return self.jp.find_block(c) + 1 if c is not None else 0

    def ghost_source(self, e, kind):
        # the id of the road or intersection an element replaces, None if it has none or it isn't a ghost (brought back)
        source = e.get('source')
        if source is None or source.get('kind') != kind:
            return None
        elements = self.data.get('roads' if kind == 'road' else 'intersections') or []
        i = source.get('id', -1)
        return i if 0 <= i < len(elements) and elements[i].get('ghost', False) else None

    def traffic_intersections(self):
        # the BAI intersections as traffic intersections: [element, intersection, block] (the intersection being the
        # ghost they replace, if any, so that the roads ending on it end on them)
        res = []
        for e in self.of_type(BAI_INTERSECTION):
            pts = e.get('points') or {}
            if 'center' not in pts:
                continue
            block = self.block_of(e)
            if block <= 0:
                report.warning("the BAI intersection " + element_name(e) + " is not in a room", element=element_name(e), kind='lowLevel')
                continue
            elem = ExportedCityElement()
            elem.vertices = [position(pts['center'])]
            elem.properties['original_name'] = element_name(e)
            source = self.ghost_source(e, 'intersection')
            intersection_id = source if source is not None else ('ll', e['id'])
            pseudo = {'id': intersection_id, 'lowLevel': e, 'center': position(pts['center']), 'data': e['data'], 'roads': []}
            res.append([elem, pseudo, block])
        self.ll_traffic = res
        return res

    def traffic_roads(self):
        # the BAI roads as exported roads (see json_processor.exported_roads): their key, record
        res = []
        for e in self.of_type(BAI_ROAD):
            secs = (e.get('points') or {}).get('sections') or []
            if len(secs) < 2:
                continue
            block = self.block_of(e)
            if block <= 0:
                report.warning("the BAI road " + element_name(e) + " is not in a room", element=element_name(e), kind='lowLevel')
                continue
            state = element_state(e)
            cross = []
            for s in secs:
                cross.append([position(s['rightEdge']), position(s['rightCurb'])] + [position(p) for p in s.get('backwardLanes') or []]
                             + [position(p) for p in s.get('forwardLanes') or []] + [position(s['leftCurb']), position(s['leftEdge'])])
            f_lanes = len(secs[0].get('forwardLanes') or [])
            b_lanes = len(secs[0].get('backwardLanes') or [])
            if state_bool(state, 'noTraffic'):
                f_lanes, b_lanes = 0, 0
            elem = ExportedCityElement()
            elem.properties['original_name'] = element_name(e)
            rec = {
                'lowLevel': e, 'elem': elem, 'block': block, 'bai_cross_sections': cross,
                'forward_lanes': f_lanes, 'backward_lanes': b_lanes, 'source_road': self.ghost_source(e, 'road'),
            }
            res.append((('ll', e['id']), rec))
        return res

    def end_intersection_key(self, rec, at_start):
        # the intersection a BAI road end refers to: a BAI intersection, or a procedural intersection (the BAI
        # intersection replacing it if it is a ghost)
        r = reference(element_state(rec['lowLevel']), 'startIntersection' if at_start else 'endIntersection')
        if r is None:
            return "0"
        kind, i = r
        if kind == 'lowLevel':
            for obj in self.ll_traffic:
                if obj[1]['lowLevel']['id'] == i:
                    return str(obj[2])
            return "0"
        index = self.jp.intersection_map.get(i)
        if index is None:
            return "0"
        try:
            # in a ring of intersections (see json_processor.get_split_intersection)
            return self.jp.get_bai_intersection_key(i, ('ll', rec['lowLevel']['id']), at_start)
        except KeyError:
            return str(self.jp.traffic_intersections[index][2])

    def procedural_intersection_ends(self, intersection_id):
        # the ends of the BAI roads on a procedural intersection (see json_processor.get_bai_entries): (key, at start)
        res = []
        for key, rec in sorted(((k, r) for k, r in self.jp.exported_roads.items() if 'lowLevel' in r), key=lambda x: x[0][1]):
            state = element_state(rec['lowLevel'])
            for at_start in (True, False):
                if reference(state, 'startIntersection' if at_start else 'endIntersection') == ('intersection', intersection_id):
                    res.append((key, at_start))
        return res

    def traffic_road(self, res, chain_index, rec):
        e = rec['lowLevel']
        state = element_state(e)
        f_lanes, b_lanes = rec['forward_lanes'], rec['backward_lanes']
        left_ped = not state_bool(state, 'noLeftPedestrians')
        right_ped = not state_bool(state, 'noRightPedestrians')
        with_peds = left_ped or right_ped
        with_traffic = (f_lanes > 0 or b_lanes > 0) and not state_bool(state, 'alley')
        traffic_type = '0' if with_peds and with_traffic else ('1' if with_peds else ('2' if with_traffic else '3'))
        cross = rec['bai_cross_sections']
        elem = rec['elem']
        elem.vertices = [v for s in cross for v in s]
        elem.name = '0_BAI'
        elem.properties['is_road'] = '1'
        elem.properties['id'] = str(chain_index)
        elem.properties['right_lanes'] = str(f_lanes)
        elem.properties['left_lanes'] = str(b_lanes)
        elem.properties['has_sidewalks'] = ('1' if right_ped else '0') + ':' + ('1' if left_ped else '0')
        elem.properties['has_geo_sidewalks'] = '1' if state_bool(state, 'geoSidewalks') else '0'
        elem.properties['traffic_type'] = traffic_type
        elem.properties['bai_layout'] = '2'
        elem.properties['vertices_per_section'] = str(len(cross[0]))
        elem.properties['divided'] = '1' if state_bool(state, 'divided') else '0'
        elem.properties['freeway'] = '1' if state_bool(state, 'freeway') else '0'
        elem.properties['alley'] = '1' if state_bool(state, 'alley') else '0'
        if state_bool(state, 'cableCar'):
            elem.properties['cable_car'] = '1'
            offset = float(state_val(state, 'cableCarOffset', 0) or 0)
            elem.properties['cable_car_offset'] = str(offset if offset > 0 else 2.5)
        elem.properties['start_rule'] = str(state_int(state, 'startRule')) if b_lanes > 0 else "0"
        elem.properties['end_rule'] = str(state_int(state, 'endRule')) if f_lanes > 0 else "0"
        elem.properties['start_intersection'] = self.end_intersection_key(rec, True)
        elem.properties['end_intersection'] = self.end_intersection_key(rec, False)
        elem.properties['blocks'] = str(rec['block'])
        elem.mat = 'NONE'
        res.append(elem)

    def chain_end(self, chain, at_start):
        # the intersection id (as in intersection_map) and the BAI section at an end of a chain of roads
        jp = self.jp
        road_id, rev = chain[0] if at_start else chain[-1]
        rec = jp.exported_roads[road_id]
        if 'lowLevel' in rec:
            r = reference(element_state(rec['lowLevel']), 'startIntersection' if at_start else 'endIntersection')
            cross = rec['bai_cross_sections']
            section = cross[0] if at_start else cross[-1]
            if r is None:
                return None, section
            if r[0] == 'lowLevel':
                return ('ll', r[1]), section
            return r[1], section
        sections = jp.get_bai_sections(rec, rev)
        section = sections[0] if at_start else sections[-1]
        intersection = jp.get_near_intersection(road_id, rev) if at_start else jp.get_far_intersection(road_id, rev)
        return intersection, section

    def traffic_intersection(self, res, obj):
        # a BAI intersection with the roads ending on it, counterclockwise as the procedural ones
        jp = self.jp
        elem, pseudo, block = obj
        c = pseudo['center']
        ids = {pseudo['id'], ('ll', pseudo['lowLevel']['id'])}
        ends = []
        for i, chain in enumerate(jp.bai_chains):
            for at_start in (True, False):
                intersection, section = self.chain_end(chain, at_start)
                if intersection in ids:
                    mid = np.mean(np.array(section, dtype=float), axis=0)
                    ends.append((math.atan2(mid[2] - c[2], mid[0] - c[0]), i))
        ends.sort()
        # replacing an intersection: its first road last, as in its own list (see json_processor.get_traffic_intersection)
        if not isinstance(pseudo['id'], tuple) and 0 <= pseudo['id'] < len(self.data.get('intersections') or []):
            roads = self.data['intersections'][pseudo['id']]['roads']
            first = jp.road_map.get(roads[0]) if len(roads) > 0 else None
            indices = [i for _, i in ends]
            if first in indices:
                k = indices.index(first)
                ends = ends[k + 1:] + ends[:k + 1]
        traffic_elem = ExportedCityElement()
        traffic_elem.vertices = [c]
        traffic_elem.name = '0_BAI'
        traffic_elem.properties['original_name'] = elem.properties['original_name'] + ' [BAI]'
        traffic_elem.properties['is_road'] = '0'
        traffic_elem.properties['block'] = str(block)
        traffic_elem.properties['roads'] = ';'.join(str(i) for _, i in ends)
        traffic_elem.mat = 'NONE'
        res.append(traffic_elem)

    # Hudmap

    def hudmap_meshes(self):
        # the meshes of the attributes with the category of their room: (mesh, category, default category)
        defaults = {"roadWithSidewalks": "road", "roadWithoutSidewalks": "road", "dividedRoad": "road", "roadTriangleFan": "road",
                    "sidewalkStrip": "road", "crosswalk": "road", "triangleFan": "ground", "roofTriangleFan": "building"}
        res = []
        for e in self.elements.values():
            typ = element_type(e)
            if typ not in defaults:
                continue
            room = self.room_of(e)
            res.append((e['data'].get('mesh'), element_state(room) if room is not None else None, defaults[typ]))
        return res
