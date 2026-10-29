# The conversion of the elements of the city to low-level elements (the converters of the core, see the converters
# folder): the elements are processed by the exporter (json_processor.py) and the parts it would write in the PSDL are
# turned into the low-level elements of the same attributes (low_level.py does the opposite), so that converting an
# element doesn't change what is exported. The converters get the elements in the format of the export JSON and write
# the low-level elements in the format of the city save (see the Core Low-Level Elements page of the wiki).

import json
import os
import shutil
import tempfile
import numpy as np
from collections import defaultdict
from json_processor import JsonProcessor
from psdl_parts import get_tex
from bin_export import BINExporter
from scene_input import StandaloneSceneInput
from common.psdl_writer import PSDLWriter
from utils import state_val, state_bool, state_int

FLAT_EPSILON = 0.05  # as the PSDL writer: road triangle fans that are not flat are written as triangle fans
ROAD_PARTS = ["ROADS", "ROADSN", "ROADN", "ROADD", "ROADDN"]
BUILDING_PARTS = ["FAC", "FACB", "SLIVER", "ROOF"]
NOT_IN_WRITER = ("PTH", "INST", "TRAFL", "BAI", "DECAL", "PKG", "PERIM")  # the parts left out when the writer runs on a room
# the roles of the parts in the names of their elements ("<element> [<role>]"), unless the exporter gives one already
# (e.g. "Road 3 [shoulder]"); the tunnels are always named as such (the exporter calls them rails)
PART_ROLES = {"ROADS": "road", "ROADSN": "road", "ROADN": "road", "ROADD": "road", "ROADDN": "road", "RAIL": "tunnel",
              "RAILC": "tunnel", "SW": "sidewalk", "CW": "crosswalk", "IS": "road surface", "BLOCK": "terrain",
              "NUL": "invisible surface", "ROOF": "roof", "FAC": "facade", "FACB": "facade bound", "SLIVER": "sliver"}
FORCED_ROLES = ("RAIL", "RAILC")
FAN_ROLES = {"roadTriangleFan": "road surface", "roofTriangleFan": "roof", "triangleFan": "surface"}
BLOCK_ORDER = ["NUL", "RAIL", "RAILC", "ROADS", "ROADSN", "ROADN", "ROADD", "ROADDN", "BLOCK", "IS", "SW", "CW", "SLIVER", ["FAC", "FACB"], "ROOF", ""]


class ConversionError(Exception):
    # its message is a string key shown to the user
    pass


class Output:
    # the low-level elements (and their points) in the format read by the program (see Operations.Conversion)
    def __init__(self):
        self.points = []
        self.point_ids = {}
        self.elements = []
        self.updates = []

    def point(self, position, weld=True):
        # the same position is the same point (shared by the elements, as the vertices of the PSDL)
        key = tuple(round(float(c), 3) for c in position)
        if key in self.point_ids:
            return self.point_ids[key]
        pid = "p" + str(len(self.points))
        self.points.append({"id": pid, "position": [float(c) for c in position], "weld": weld})
        self.point_ids[key] = pid
        return pid

    def element(self, typ, name, state=None, points=None, mesh=None, container=None, source=None):
        eid = "e" + str(len(self.elements))
        e = {"id": eid, "type": typ, "name": name, "state": state or {}}
        if points is not None:
            e["points"] = points
        if mesh is not None:
            e["mesh"] = mesh
        if container is not None:
            e["container"] = container
        if source is not None:
            e["source"] = source
        self.elements.append(e)
        return eid

    def anchor(self, pid, line=None, column=None):
        # the point follows the line between two points (line: their ids) or the vertical line of a point (column: its id)
        p = self.points[int(pid[1:])]
        if line is not None:
            p["anchor"] = {"line": list(line)}
        elif column is not None:
            p["anchor"] = {"column": column}

    def update(self, element, points=None, state=None):
        # changes of an existing element (element: its reference, {"kind": "lowLevel", "id": id}): the points given
        # replace its points of the same names, the state given is merged into its state
        u = {"element": element}
        if points is not None:
            u["points"] = points
        if state is not None:
            u["state"] = state
        self.updates.append(u)

    def find(self, eid):
        for e in self.elements:
            if e["id"] == eid:
                return e
        return None

    def write(self, path, replace=None):
        res = {"points": self.points, "elements": self.elements}
        if len(self.updates) > 0:
            res["updates"] = self.updates
        if replace is not None:
            res["replace"] = replace
        with open(path, 'w') as f:
            json.dump(res, f)


class TextureNames:
    # the paths of the textures from their names in the PSDL (the parts only have the names): the relative paths
    # stored in the states of the elements, otherwise the paths of the materials, relative to the folder of the city or
    # to the common folder of the core
    def __init__(self, data):
        self.paths = {}

        def collect(value):
            if isinstance(value, str):
                self.add(value)
            elif isinstance(value, dict):
                for v in value.values():
                    collect(v)
            elif isinstance(value, list):
                for v in value:
                    collect(v)
        for kind in ('roads', 'intersections', 'terrainPatches', 'buildingLines', 'lowLevelElements'):
            for e in data.get(kind) or []:
                collect(e)
        folders = []
        city = data.get('cityFolder')
        if city:
            folders.append(city)
        folders.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
                                    'common', 'MidtownMadness2'))
        folders = [f.replace('\\', '/').rstrip('/') + '/' for f in folders]
        for m in data.get('materialDict') or []:
            path = state_val(m.get('data'), 'texture')
            if not isinstance(path, str):
                continue
            norm = path.replace('\\', '/')
            for f in folders:
                if norm.lower().startswith(f.lower()):
                    norm = norm[len(f):]
                    break
            self.add(norm)

    def add(self, path):
        if path is None or path == '' or path in ('NONE',) or '.' not in path:
            return
        name = get_tex(path)
        if name not in self.paths:
            self.paths[name] = path

    def path(self, name):
        if name is None or name == '' or name == 'NONE':
            return ''
        return self.paths.get(name, name)

    def list(self, mat):
        return [self.path(t) for t in mat.split(',')] if mat else []


class PartsShim:
    # a json processor that only has the given parts (for BINExporter)
    def __init__(self, parts):
        self.parts = parts

    def get_objects(self):
        return self.parts


def flatten(v):
    return (float(v[0]), float(v[1]), float(v[2]))


class Converter:
    def __init__(self, data):
        self.data = data
        self.out = Output()
        self.textures = TextureNames(data)
        self.prepare()
        self.jp = JsonProcessor(data, False, ignore_blocks=True)
        self.manual_blocks = self.jp.reset()

    # The ids of the input are the ones of the program: they become the indices of the lists (as in the export JSON,
    # which the exporter expects), the references of the output use the ones of the program again

    def prepare(self):
        data = self.data
        self.original_ids = {}
        maps = {}
        for kind in ('roads', 'intersections', 'terrainPatches', 'buildingLines'):
            maps[kind] = {}
            for i, e in enumerate(data.get(kind) or []):
                maps[kind][e['id']] = i
                self.original_ids[(kind, i)] = e['id']
                e['id'] = i
        rmap, imap = maps['roads'], maps['intersections']
        for r in data.get('roads') or []:
            r['startIntersectionId'] = imap.get(r['startIntersectionId'], -1)
            r['endIntersectionId'] = imap.get(r['endIntersectionId'], -1)
        for i in data.get('intersections') or []:
            i['roads'] = [rmap.get(r, -1) for r in i['roads']]
        self.maps = maps

    def original_id(self, kind, index):
        return self.original_ids.get((kind, index))

    def find(self, kind, original_id):
        index = self.maps[kind].get(original_id)
        return None if index is None else self.data[kind][index]

    # Conversion

    def convert(self, targets):
        lists = {'road': 'roads', 'intersection': 'intersections', 'terrainPatch': 'terrainPatches', 'buildingLine': 'buildingLines'}
        for t in targets:
            kind = t['kind']
            if kind not in lists:
                raise ConversionError("CONVERSION_ERROR_KIND")
            element = self.find(lists[kind], t['id'])
            if element is None:
                raise ConversionError("CONVERSION_ERROR_MISSING")
            self.check(kind, element)
            source = {"kind": kind, "id": t['id']}
            start = len(self.out.elements)
            self.source_name = element['data']['name']
            parts = self.jp.get_element_parts(kind, element, self.manual_blocks)
            if kind == 'buildingLine':
                self.map_buildings(parts, element, source)
            else:
                rooms = self.map_rooms(parts, element, source)
                if kind == 'road':
                    self.bai_road(element, rooms, source)
                elif kind == 'intersection':
                    self.bai_intersection(element, rooms, source)
            number_names(self.out.elements[start:])
        return self.out

    def map_buildings(self, parts, element, source):
        # a group of building parts for each building (and the roof of the line), placed where the exporter looks for
        # the block of the building
        groups = defaultdict(list)
        for p in parts:
            groups[(p.properties.get('locate'), p.properties.get('locate_front'))].append(p)
        name = element['data']['name']
        for i, ((locate, front), group_parts) in enumerate(sorted(groups.items(), key=lambda x: str(x[0]))):
            if locate is not None:
                location = tuple(float(c) for c in locate.split(','))
            else:
                location = tuple(np.mean(np.array([v for p in group_parts for v in p.vertices], dtype=float), axis=0))
            front_location = tuple(float(c) for c in front.split(',')) if front is not None else location
            points = {"location": self.out.point(location, False), "frontLocation": self.out.point(front_location, False)}
            group = self.out.element("buildingGroup", name + (" building " + str(i + 1) if len(groups) > 1 else " building"),
                                     points=points, source=source)
            self.map_parts(group_parts, group, source)
            self.building_anchors(group_parts)

    def building_anchors(self, parts):
        # the points of a building keep their places when one is moved: the points above another one (at the same x and
        # z) follow it (the lowest one), and those of them lying inside the top or bottom edge of a sliver or of a facade
        # bound follow that edge (the corners of the facades between the ends of a side)
        out = self.out
        corners = []  # (position, edges): the corners, and the horizontal edges of the slivers and bounds as pairs
        edges = []
        for p in parts:
            typ = p.part_type()
            if typ in ("FAC", "FACB", "SLIVER"):
                v = p.vertices
                top = float(v[2][1])
                c = [tuple(float(x) for x in v[0]), tuple(float(x) for x in v[1]), (float(v[0][0]), top, float(v[0][2])), (float(v[1][0]), top, float(v[1][2]))]
                corners.extend(c)
                if typ != "FAC":
                    # the slivers first: the facades stand on them where the ground slopes
                    edges.append((0 if typ == "SLIVER" else 1, (c[2], c[3])))
                    edges.append((0 if typ == "SLIVER" else 1, (c[0], c[1])))
            elif typ == "ROOF":
                corners.extend(tuple(float(x) for x in v) for v in p.vertices)
        edges = [e for _, e in sorted(edges, key=lambda x: x[0])]
        columns = defaultdict(dict)
        for c in corners:
            columns[(round(c[0], 3), round(c[2], 3))][out.point(c)] = c
        masters = []
        for points in columns.values():
            ordered = sorted(points.items(), key=lambda x: x[1][1])
            master, position = ordered[0]
            masters.append((master, position))
            for pid, _ in ordered[1:]:
                out.anchor(pid, column=master)
        for master, position in masters:
            pos = np.array(position, dtype=float)
            for a, b in edges:
                pa, pb = np.array(a, dtype=float), np.array(b, dtype=float)
                d = pb - pa
                length = np.linalg.norm(d)
                if length < 1e-3:
                    continue
                t = np.dot(pos - pa, d) / (length * length)
                if t * length <= 1e-3 or (1 - t) * length <= 1e-3:
                    continue  # not strictly inside the edge
                if np.linalg.norm(pa + d * t - pos) <= 1e-3:
                    ida, idb = out.point(a), out.point(b)
                    if master not in (ida, idb):
                        out.anchor(master, line=(ida, idb))
                    break

    def check(self, kind, element):
        state = element['data']['fields']['state']
        instance_state = element['data']['fields'].get('instanceState')
        if element.get('ghost', False):
            raise ConversionError("CONVERSION_ERROR_GHOST")
        if state_val(state, 'type') != 'psdl':
            raise ConversionError("CONVERSION_ERROR_NOT_PSDL")
        if state_bool(instance_state, 'exportToPKG') or state_bool(state, 'exportToPKG'):
            raise ConversionError("CONVERSION_ERROR_PKG")
        if kind == 'road' and state_bool(instance_state, 'doNotExport'):
            raise ConversionError("CONVERSION_ERROR_NOT_EXPORTED")
        if kind == 'intersection' and self.jp.is_seamless(element):
            raise ConversionError("CONVERSION_ERROR_SEAMLESS")

    def map_rooms(self, parts, element, source):
        # a room for each block of the parts (the props stay with the ghost of the road)
        by_block = defaultdict(list)
        for p in parts:
            if p.part_type() in ("PTH", "INST", "TRAFL", "BAI", "DECAL"):
                continue
            by_block[p.block()].append(p)
        state = element['data']['fields']['state']
        rooms = {}
        for block in sorted(by_block):
            block_parts = by_block[block]
            props = {}
            for p in block_parts:
                props.update(p.properties)
            room_state = {
                "echo": props.get('echo', '0') == '1',
                "warp": props.get('warp', '0') == '1',
                "hudmapCategory": state_int(state, 'hudmapCategory'),
            }
            name = element['data']['name'] + (" room" if len(by_block) == 1 else " room " + str(len(rooms) + 1))
            room = self.out.element("room", name, room_state, source=source)
            self.map_parts(block_parts, room, source)
            # the perimeter the writer finds (simplified by the export as the perimeters it finds itself, which then
            # also knows the neighbours of the room), so that it can be edited
            perimeter = traced_perimeter(block_parts)
            if perimeter is not None:
                r = self.out.find(room)
                r["points"] = {"perimeter": [self.out.point(v) for v in perimeter]}
                r["state"]["simplifyPerimeter"] = True
            rooms[block] = room
        return rooms

    def mesh(self, part):
        return {"vertices": [self.out.point(v) for v in part.vertices], "triangles": [int(i) for i in part.indices]}

    def sections(self, part, names):
        n = len(names)
        res = []
        for i in range(0, len(part.vertices) - n + 1, n):
            res.append({names[j]: self.out.point(part.vertices[i + j]) for j in range(n)})
        return res

    def map_parts(self, parts, container, source):
        out = self.out
        roads = {}  # original_id -> element (for the rails)
        bounds = {}  # facade index -> facade bound
        tunnels = []
        railc = [p for p in parts if p.part_type() == "RAILC"]
        walls = self.junction_walls(parts, railc) if len(railc) > 0 else {}
        ordered = sorted(parts, key=lambda p: 0 if p.part_type() == "FACB" else 1)
        for p in ordered:
            typ = p.part_type()
            mats = self.textures.list(p.mat)
            name = part_name(p, "sidewalk" if typ in ROAD_PARTS and source['kind'] == 'intersection' else None, self.source_name)

            def tex(i):
                return mats[i] if i < len(mats) else ''
            if typ == "ROADS":
                e = out.element("roadWithSidewalks", name, {
                    "texture": tex(0), "sidewalkTexture": tex(1), "lodTexture": tex(2),
                    "noCoplanarFix": p.properties.get('no_coplanar_fix', '0') == '1'
                }, {"sections": self.sections(p, ["leftSidewalk", "leftRoad", "rightRoad", "rightSidewalk"])}, container=container, source=source)
                self.road_extras(p, e, source)
                roads[p.properties.get('original_id')] = e
            elif typ in ("ROADN", "ROADSN"):
                e = out.element("roadWithoutSidewalks", name, {
                    "style": 1 if typ == "ROADSN" else 0, "texture": tex(0), "sidewalkTexture": tex(1), "lodTexture": tex(2),
                    "noCoplanarFix": p.properties.get('no_coplanar_fix', '0') == '1'
                }, {"sections": self.sections(p, ["left", "right"])}, container=container, source=source)
                roads[p.properties.get('original_id')] = e
            elif typ in ("ROADD", "ROADDN"):
                no_sidewalks = typ == "ROADDN"
                names = ["leftRoad", "leftDivider", "rightDivider", "rightRoad"]
                if not no_sidewalks:
                    names = ["leftSidewalk"] + names + ["rightSidewalk"]
                secs = self.sections(p, names)
                if no_sidewalks:
                    for s in secs:
                        s["leftSidewalk"] = s["leftRoad"]
                        s["rightSidewalk"] = s["rightRoad"]
                # the dividers at the ends follow the road edges there (shared with the intersections, which have no
                # points where the dividers are), keeping their places across the road
                for s in (secs[0], secs[-1]) if len(secs) > 0 else ():
                    for d in ("leftDivider", "rightDivider"):
                        if s[d] not in (s["leftRoad"], s["rightRoad"]):
                            out.anchor(s[d], line=(s["leftRoad"], s["rightRoad"]))
                caps = int(p.properties.get('caps', '0'))
                e = out.element("dividedRoad", name, {
                    "noSidewalks": no_sidewalks,
                    "dividerType": {'F': 1, 'E': 2, 'W': 3}.get(p.properties.get('divider_type'), 0),
                    "dividerValue": int(p.properties.get('divider_param', '0') or 0) / 256.0,
                    "closeStart": caps in (1, 3), "closeEnd": caps in (2, 3),
                    "texture": tex(0), "sidewalkTexture": tex(1), "lodTexture": tex(2), "dividerSideTexture": tex(3),
                    "dividerFlatTexture": tex(4), "dividerTopTexture": tex(5), "dividerCapTexture": tex(6)
                }, {"sections": secs}, container=container, source=source)
                self.road_extras(p, e, source)
                roads[p.properties.get('original_id')] = e
            elif typ == "RAIL":
                tunnels.append(p)
            elif typ == "RAILC":
                state = self.tunnel_state(p, mats)
                lines = walls.get(id(p), [])
                if len(lines) == 0:
                    continue
                out.element("junctionTunnel", name, state, {"walls": [{"points": [out.point(v) for v in line]} for line in lines]},
                            container=container, source=source)
            elif typ == "SW":
                unique = []
                for v in p.vertices:
                    if not any(np.linalg.norm(np.subtract(v, u)) < 0.03 for u in unique):
                        unique.append(v)
                if len(unique) == 2:
                    out.element("sidewalkCap", part_name(p, "sidewalk cap", self.source_name), {"which": 0, "texture": tex(0)},
                                {"a": out.point(p.vertices[1]), "b": out.point(p.vertices[0])}, container=container, source=source)
                else:
                    out.element("sidewalkStrip", name, {"texture": tex(0)}, {"sections": self.sections(p, ["outer", "inner"])},
                                container=container, source=source)
            elif typ == "CW":
                out.element("crosswalk", name, {"texture": tex(0)},
                            {"p" + str(i + 1): out.point(p.vertices[i]) for i in range(4)}, container=container, source=source)
            elif typ in ("IS", "BLOCK", "NUL"):
                ys = [v[1] for v in p.vertices]
                flat = len(ys) > 0 and max(ys) - min(ys) <= FLAT_EPSILON
                if typ == "IS" and flat:
                    out.element("roadTriangleFan", name, {"texture": tex(0)}, mesh=self.mesh(p), container=container, source=source)
                else:
                    out.element("triangleFan", name, {"texture": tex(0), "perimeterOnly": typ == "NUL"}, mesh=self.mesh(p),
                                container=container, source=source)
            elif typ == "ROOF":
                out.element("roofTriangleFan", name, {"texture": tex(0)}, mesh=self.mesh(p), container=container, source=source)
            elif typ in ("FAC", "FACB", "SLIVER"):
                v = p.vertices
                top = float(v[2][1])
                corners = {
                    "bottomLeft": out.point(v[0]), "bottomRight": out.point(v[1]),
                    "topLeft": out.point((v[0][0], top, v[0][2])), "topRight": out.point((v[1][0], top, v[1][2]))
                }
                index = p.name.split(',')[0][1:].rstrip('*+z') if ',' in p.name else None
                if typ == "FACB":
                    bounds[index] = out.element("facadeBound", name, {"bothSides": p.properties.get('both_sides', '0') == '1'}, corners,
                                                container=container, source=source)
                elif typ == "FAC":
                    state = {"texture": tex(0), "uRepeat": abs(int(p.properties.get('u_tiling', '1'))), "vRepeat": abs(int(p.properties.get('v_tiling', '1')))}
                    if index in bounds:
                        state["bound"] = {"kind": "lowLevel", "id": bounds[index]}
                    out.element("facade", name, state, corners, container=container, source=source)
                else:
                    out.element("sliver", name, {"texture": tex(0), "textureScale": int(p.properties.get('tiling', '0')) / 100.0}, corners,
                                container=container, source=source)
        for p in tunnels:
            mats = self.textures.list(p.mat)
            state = self.tunnel_state(p, mats)
            state["leftSide"] = p.properties.get('has_left', '0') == '1'
            state["rightSide"] = p.properties.get('has_right', '0') == '1'
            road = roads.get(p.properties.get('road_name'))
            if road is not None:
                state["road"] = {"kind": "lowLevel", "id": road}
            out.element("roadTunnel", part_name(p, None, self.source_name), state, container=container, source=source)

    def road_extras(self, part, e, source):
        # the psdl props along the road (its prop rule): only its psdl props containers, the ghost of the road keeps
        # exporting the others (instances along it)
        if 'prop_rule' not in part.properties:
            return
        element = None
        if source['kind'] == 'road':
            element = self.find('roads', source['id'])
        if element is None:
            return
        rule = state_val(element['data']['fields']['state'], 'propRule')
        if isinstance(rule, dict):
            rule = {k: v for k, v in rule.items() if not isinstance(v, dict) or v.get('type') == 'psdl'}
        self.out.find(e)["state"]["propRule"] = rule

    @staticmethod
    def tunnel_state(p, mats):
        def flag(name):
            return p.properties.get(name, '0') == '1'
        state = {
            "wall": flag('is_wall'), "flatCeiling": flag('is_flat_gallery'), "curvedCeiling": flag('is_curved_gallery'),
            "curvedSides": flag('curved_sides'), "culled": flag('is_rail'),
            "closedStartLeft": flag('cap_start_left'), "closedEndLeft": flag('cap_end_left'),
            "closedStartRight": flag('cap_start_right'), "closedEndRight": flag('cap_end_right'),
            "offsetStartLeft": flag('offset_start_left'), "offsetEndLeft": flag('offset_end_left'),
            "offsetStartRight": flag('offset_start_right'), "offsetEndRight": flag('offset_end_right'),
            "height": int(p.properties.get('height', '0') or 0) / 256.0
        }
        for i in range(6):
            state["texture" + str(i)] = mats[i] if i < len(mats) else ''
        return state

    # Junction tunnels: the walls are on the edges of the perimeter of the room, found by the PSDL writer

    def junction_walls(self, parts, railc_parts):
        # the walls of each junction tunnel: the runs of consecutive edges of the perimeter that have a wall
        res = {}
        writer = room_writer(parts)
        if writer is None:
            return res
        w, b, scene = writer
        try:
            perimeter = w.get_perimeter(b, 0, False)
        except Exception:
            perimeter = w.get_perimeter(b, 0, True)
        if perimeter is None:
            return res
        perimeter.reverse()
        w.perim_points = perimeter
        for bp in b:
            if w.utils.get_object_type(bp.geo) != "RAILC":
                continue
            index = int(scene.get_object_name(bp.geo).split(',')[0][1:])
            original = parts_by_index(parts, index)
            edges = self.wall_edges(w, bp)
            res[id(original)] = self.wall_lines(w, perimeter, edges)
        return res

    @staticmethod
    def wall_edges(w, bp):
        # as PSDLWriter.process_part_railc: the edge from perimeter point ip - 1 to ip has a wall
        verts0 = []
        reverse_indices = {}
        for i in range(w.scene_input.get_vertices_num(bp.geo)):
            vi = w.get_vert_index(w.scene_input.get_vertex(bp.geo, i))
            if vi > -1:
                verts0.append(vi)
                reverse_indices[vi] = i
        res = []
        for ip in range(len(w.perim_points)):
            p1 = w.perim_points[ip].ID
            p2 = w.perim_points[ip - 1].ID
            if p1 in reverse_indices and p2 in reverse_indices and w.check_if_same_railc_face(bp.geo, reverse_indices[p1], reverse_indices[p2]):
                res.append(ip)
        return res

    @staticmethod
    def wall_lines(w, perimeter, edges):
        # the polylines of the consecutive edges with a wall (positions in the coordinates of the program)
        n = len(perimeter)
        has = set(edges)

        def pos(i):
            v = w.vertices[perimeter[i % n].ID - 1]
            return (float(v[0]), float(v[2]), float(v[1]))  # the writer has the coordinates of the .bin (x, z, y)
        if len(has) == n:
            return [[pos(i) for i in range(n + 1)]]
        lines = []
        for ip in range(n):
            if ip not in has or (ip - 1) % n in has:
                continue
            # a run starting with the edge ip (from ip - 1 to ip)
            line = [pos(ip - 1), pos(ip)]
            j = ip + 1
            while j % n in has and len(line) <= n:
                line.append(pos(j))
                j += 1
            lines.append(line)
        return lines

    # Traffic

    def bai_road(self, element, rooms, source):
        # the BAI road of a road (in its room), from its start to its end
        rec = self.jp.exported_roads.get(element['id'])
        if rec is None or len(rooms) == 0:
            return
        sections = self.jp.get_bai_cross_sections(rec)
        if len(sections) < 2:
            return
        state = element['data']['fields']['state']
        instance_state = element['data']['fields']['instanceState']
        f_lanes, b_lanes = self.jp.get_bai_lane_counts(state)
        secs = []
        for s in sections:
            secs.append({
                "rightEdge": self.out.point(s[0]), "rightCurb": self.out.point(s[1]),
                "backwardLanes": [self.out.point(v) for v in s[2:2 + b_lanes]],
                "forwardLanes": [self.out.point(v) for v in s[2 + b_lanes:2 + b_lanes + f_lanes]],
                "leftCurb": self.out.point(s[-2]), "leftEdge": self.out.point(s[-1])
            })
        bai_state = {
            "startRule": state_int(instance_state, 'start_rule'), "endRule": state_int(instance_state, 'end_rule'),
            "noLeftPedestrians": state_bool(state, 'disableLeftPedestrians'), "noRightPedestrians": state_bool(state, 'disableRightPedestrians'),
            "geoSidewalks": bool(self.jp.road_has_sidewalks(state, element['data']['fields']['runtimeState'])),
            "divided": bool(self.jp.road_has_divider(state)), "freeway": state_bool(state, 'freeway'),
            "alley": state_bool(state, 'pedestrianStreet'), "cableCar": state_bool(state, 'cableCarLine'),
            "cableCarOffset": float(state_val(state, 'cableCarOffset', 0) or 0),
            "autoCalculated": True  # recomputed from the road attributes when they're edited (psdl.baiRoadPoints)
        }
        for key, end in (("startIntersection", 'startIntersectionId'), ("endIntersection", 'endIntersectionId')):
            if element[end] >= 0:
                bai_state[key] = {"kind": "intersection", "id": self.original_id('intersections', element[end])}
        room = rooms[sorted(rooms)[0]]
        self.out.element("baiRoad", element['data']['name'] + " [BAI]", bai_state, {"sections": secs}, container=room, source=source)

    def bai_intersection(self, element, rooms, source):
        if len(rooms) == 0 or len(element['roads']) == 0:
            return
        room = rooms[sorted(rooms)[0]]
        self.out.element("baiIntersection", element['data']['name'] + " [BAI]", {}, {"center": self.out.point(element['center'])},
                         container=room, source=source)


def convert_fans(data, target):
    # triangle fans, road triangle fans and roof triangle fans to the target type: the same mesh (the vertices of a roof
    # all get the height of the highest one)
    out = Output()
    elements = {e['id']: e for e in data.get('lowLevelElements') or []}
    for t in data['convert']:
        e = elements.get(t['id'])
        if e is None:
            raise ConversionError("CONVERSION_ERROR_MISSING")
        vertices = [tuple(v['position']) for v in e.get('vertices') or []]
        if target == "roofTriangleFan" and len(vertices) > 0:
            top = max(v[1] for v in vertices)
            vertices = [(v[0], top, v[2]) for v in vertices]
        state = {"texture": state_val(e['data']['fields']['state'], 'texture', '')}
        out.element(target, fan_name(e['data']['name'], target), state, mesh={"vertices": [out.point(v) for v in vertices], "triangles": e.get('triangles') or []})
    return out


def split_role(name):
    # the name without its role and the role, if it has one: "Road 3 [shoulder]" -> ("Road 3", "shoulder")
    if name.endswith("]") and " [" in name:
        i = name.rindex(" [")
        return name[:i], name[i + 2:-1]
    return name, ''


def part_name(p, role=None, default=''):
    # the name of the element of a part: the name of the element it comes from (default: if the part has none) and its
    # role (see PART_ROLES)
    base, given = split_role(p.properties.get('original_name', '') or '')
    base = base or default
    typ = p.part_type()
    if role is None:
        role = given if given != '' and typ not in FORCED_ROLES else PART_ROLES.get(typ, typ.lower())
    return (base + " [" + role + "]").strip()


def number_names(elements):
    # the elements of the same name (from the same element) numbered in their order: "Intersection 2 [crosswalk 3]"
    counts = defaultdict(int)
    for e in elements:
        counts[e["name"]] += 1
    seen = defaultdict(int)
    for e in elements:
        name = e["name"]
        if counts[name] < 2:
            continue
        seen[name] += 1
        if name.endswith("]"):
            e["name"] = name[:-1] + " " + str(seen[name]) + "]"
        else:
            e["name"] = name + " " + str(seen[name])


def fan_name(name, target):
    # the name of a triangle fan converted to another type: its role replaced, if it's the one of a triangle fan
    roles = set(FAN_ROLES.values()) | {PART_ROLES[t] for t in ("IS", "BLOCK", "NUL")}
    base, role = split_role(name)
    words = role.rsplit(' ', 1)
    number = ''
    if len(words) == 2 and words[1].isdigit():
        role, number = words[0], ' ' + words[1]
    if role not in roles:
        return name
    return base + " [" + FAN_ROLES[target] + number + "]"


def parts_by_index(parts, index):
    # the original part of a copy written for the writer (see room_writer)
    copies = [p for p in parts if p.part_type() not in NOT_IN_WRITER]
    return copies[index]


def room_writer(parts):
    # the PSDL writer on copies of the parts as block 1 (with unique names in their order: the scene input sorts them by
    # name), up to the perimeter: (writer, its block sorted as for the export, scene input), None if nothing has a surface
    tmp = tempfile.mkdtemp(prefix='km2_ll_')
    try:
        order = []
        for p in parts:
            if p.part_type() in NOT_IN_WRITER:
                continue
            c = type(p)()
            c.__dict__.update(p.__dict__)
            c.properties = dict(p.properties)
            c.set_block(1)
            c.name = 'k' + str(len(order)).zfill(6) + ',' + c.name.split(',')[-1]
            order.append(c)
        if len(order) == 0:
            return None
        bin_file = os.path.join(tmp, 'room.bin')
        BINExporter(PartsShim(order), False).export_bin_file(bin_file)
        scene = StandaloneSceneInput(bin_file)
        w = PSDLWriter(scene, os.path.join(tmp, 'room.psdl'), False, False)
        w.initialize_variables()
        w.read_blocks()
        if len(w.blocks) == 0:
            return None
        w.calc_boundaries()
        w.process_vertices()
        w.search_duplicate_vertices()
        w.process_materials()
        return w, w.block_sorted_by_type(BLOCK_ORDER, w.blocks[0]), scene
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def traced_perimeter(parts):
    # the perimeter of the parts (as one room) as the writer follows it around their faces, before it drops the points
    # leading nowhere (which depends on the neighbours), in the order of the file: the positions of the vertices of the
    # parts; None if there is none
    writer = room_writer(parts)
    if writer is None:
        return None
    w, b, _ = writer
    try:
        perimeter, _ = w.trace_perimeter(b, 0, False)
    except Exception:
        try:
            perimeter, _ = w.trace_perimeter(b, 0, True)
        except Exception:
            return None
    if perimeter is None or len(perimeter) < 3:
        return None
    perimeter.reverse()
    vertices = [tuple(float(c) for c in v) for p in parts if p.part_type() not in NOT_IN_WRITER for v in p.vertices]
    array = np.array(vertices, dtype=float)
    res = []
    for pv in perimeter:
        v = w.vertices[pv.ID - 1]
        pos = np.array((v[0], v[2], v[1]), dtype=float)  # the writer has the coordinates of the .bin (x, z, y)
        res.append(vertices[int(np.argmin(np.sum((array - pos) ** 2, axis=1)))])
    return res


def room_perimeter(data):
    # the perimeter of rooms computed from their attributes (as the export does without one), set as their perimeter
    from low_level import LowLevelExporter
    out = Output()
    jp = JsonProcessor(data, False, ignore_blocks=True)
    jp.reset()
    exporter = LowLevelExporter(jp)
    for t in data['convert']:
        room = exporter.elements.get(t['id'])
        if room is None:
            raise ConversionError("CONVERSION_ERROR_MISSING")
        parts = [p for p in exporter.room_parts(room, 1) if p.part_type() != "PERIM"]
        perimeter = traced_perimeter(parts)
        if perimeter is None:
            raise ConversionError("CONVERSION_ERROR_NO_PERIMETER")
        out.update({"kind": "lowLevel", "id": t['id']}, {"perimeter": [out.point(v) for v in perimeter]}, {"simplifyPerimeter": True})
    return out


def run(argv, convert):
    # argv: the Files/python folder, the input JSON, the output JSON; convert(data) returns (Output, replace)
    import sys
    sys.path.append(argv[1])
    import DecodeExportedJson
    data = DecodeExportedJson.DecodeExportedJson().decode_json(argv[2])
    try:
        out, replace = convert(data)
    except ConversionError as e:
        sys.exit(str(e))
    out.write(argv[3], replace)
