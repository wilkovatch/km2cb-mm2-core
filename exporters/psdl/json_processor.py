import copy
import math
import os
import numpy as np
from utils import state_val, state_bool, state_int, state_vector, placed_props, PARKED_CARS_TYPES
from writers.inst_writer import INST_LANDMARK, INST_BANGER, INST_SIMPLE_COLLISION, INST_MULTIROOM, inst_modifiers
from writers import report
from psdl_parts import ExportedCityElement, get_tex
from traffic.network import BaiNetworkBuilder, is_seamless
from traffic.rooms import RoomFinder
from decals import export_decals

# The game draws a road room of many sections broken (no road texture, missing divider walls; seen in game on a
# 110-section room, while 57 sections looked right; stock rooms have at most 15). Longer PSDL roads are exported as
# several rooms (JsonProcessor.split_long_road)
MAX_ROAD_SECTIONS = 40


def get_inst_modifiers(mesh, state):
    # the modifiers of the INST record of a mesh instance, warning about the combinations that don't work
    if mesh.get('type') is None:
        return inst_modifiers(0, INST_LANDMARK)  # the parametric objects have no parameters for them
    landmark, banger = state_bool(state, 'instLandmark'), state_bool(state, 'instBanger')
    simple_collision, multiroom = state_bool(state, 'instSimpleCollision'), state_bool(state, 'instMultiroom')
    paint_job = int(state_int(state, 'instPaintJob'))
    name = mesh['name']

    def warn(text):
        report.warning('the INST mesh ' + name + ' ' + text, element=name, kind='meshInstance')
    if simple_collision and not landmark and not banger:
        warn('has No wheel collision without Landmark: the game ignores it')
    if banger and (landmark or simple_collision):
        warn('is a Banger with Landmark or No wheel collision: the game creates a banger, and the original cities never combine them')
    if multiroom and landmark:
        warn('has Multiroom with Landmark: the game places it in a single block')
    if not 0 <= paint_job <= 255:
        warn('has the paint job ' + str(paint_job) + ', outside of the range from 0 to 255')
        paint_job = max(0, min(255, paint_job))
    flags = (INST_LANDMARK if landmark else 0) | (INST_BANGER if banger else 0)
    flags |= (INST_SIMPLE_COLLISION if simple_collision else 0) | (INST_MULTIROOM if multiroom else 0)
    return inst_modifiers(paint_job, flags)


class JsonProcessor:
    # ignore_blocks: the parts outside of every block go in block 1 instead of being skipped (the converters, which
    # process elements without the city around them)
    def __init__(self, data, verbose, ignore_blocks=False):
        self.data = data
        self.ignore_blocks = ignore_blocks
        self.cur_facade_index = 0
        self.prop_rules = []
        self.verbose = verbose
        self.cur_mesh_idx = 0
        self.out_res = None
        self.network = None  # the BAI (see traffic/), built after the elements

    def get_manual_block_number(self, state):
        if 'blockNumber' in state:
            return int(state['blockNumber'])
        else:
            return 0

    def get_manual_blocks(self):
        res = []
        data = self.data
        # detect the manually assigned blocks
        for elem in data['roads']:
            block_number = self.get_manual_block_number(elem['data']['fields']['state'])
            if block_number > 0 and block_number not in res: res.append(block_number)

        for elem in data['intersections']:
            block_number = self.get_manual_block_number(elem['data']['fields']['state'])
            if block_number > 0 and block_number not in res: res.append(block_number)

        for elem in data['terrainPatches']:
            block_number = self.get_manual_block_number(elem['data']['fields']['state'])
            if block_number > 0 and block_number not in res: res.append(block_number)

        return res

    def update_perimeter_bounds(self, index):
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')
        blocks = self.block_perimeters[index][0]
        for block in blocks:
            for v in block:
                if v[0] < min_x: min_x = v[0]
                if v[2] < min_y: min_y = v[2]
                if v[0] > max_x: max_x = v[0]
                if v[2] > max_y: max_y = v[2]
        self.block_perimeters_bounds[index] = [[min_x, min_y], [max_x, max_y]]

    def add_block_perimeter_multi(self, block, typ):
        self.block_perimeters.append([block, typ])
        self.block_perimeters_bounds.append(None)
        self.update_perimeter_bounds(len(self.block_perimeters) - 1)

    def add_block_perimeter(self, block, typ):
        self.block_perimeters.append([[block], typ])
        self.block_perimeters_bounds.append(None)
        self.update_perimeter_bounds(len(self.block_perimeters) - 1)

    def extend_block_perimeter(self, perimeter_index, block):
        self.block_perimeters[perimeter_index][0].append(block)
        self.update_perimeter_bounds(perimeter_index)

    def get_tex(self, tex):
        return get_tex(tex)

    def road_has_divider(self, state):
        return state_bool(state, 'isDouble') and state_int(state, 'divider') > 0

    def road_has_sidewalks(self, state, runtime_state):
        has_sidewalks_i = state_bool(state, 'hasSidewalks') and not state_bool(runtime_state, 'throughIntersection')
        return has_sidewalks_i and state_bool(state, 'isDouble')

    def road_section_count(self, road, mesh, state, vps):
        # the sections of the mesh of a road: the cap vertices of its components (divider ends, wall ends) come after
        # them, so their count is the one of the section vertices of the road when it has them
        fields = road['data']['fields']
        per_section = fields.get('sectionVertexCount') or 0
        section_vertices = fields.get('sectionVertices') or []
        if per_section > 0 and len(section_vertices) >= 2 * per_section and len(section_vertices) // per_section * vps <= len(mesh['vertices']):
            return len(section_vertices) // per_section
        has_no_caps = (not self.road_has_divider(state)) or state['divider'] == 1
        return (len(mesh['vertices']) - (0 if has_no_caps else 8)) // vps

    def road_has_rail(self, state):
        return state_int(state, 'rail_type') > 0 and (state_bool(state, 'rail_hasLeft') or state_bool(state, 'rail_hasRight'))

    def get_section_indices(self, i, n, section_index = 0):
        i += section_index * n
        return [i, i+1, i+1+n, i, i+1+n, i+n]

    def get_section_indices_rev(self, i, n, section_index = 0):
        i += section_index * n
        return [i+n, i+1+n, i, i+1+n, i+1, i]

    def get_mesh_mat(self, mat_id):
        return self.get_tex(self.data['materialDict'][mat_id]['data']['texture']) if mat_id >= 0 else "NONE"

    def get_mesh(self, mesh, cur_block, elem_name, original_name, mesh_idx = -1):
        indices = [m['indices'] for m in mesh['submeshes']]
        materials = [self.get_mesh_mat(m['materialId']) for m in mesh['submeshes']]
        elem = ExportedCityElement()
        elem.is_mesh = True
        elem.indices = indices
        elem.normals = mesh['normals']
        elem.uvs = mesh['uvs']
        if (len(elem.uvs) != len(elem.normals)):
            elem.uvs = [(0, 0) for i in range(len(elem.normals))] #if missing
        elem.vertices = mesh['vertices']
        elem.mat = ','.join(materials)
        elem.name = str(cur_block) + '_PKG'
        elem.properties['original_name'] = original_name
        idx = self.cur_mesh_idx
        if mesh_idx >= 0:
            idx = mesh_idx
        elem.properties['pkg_name'] = "mesh" + str(idx)
        elem.properties['lod_name'] = elem_name
        if mesh_idx < 0:
            self.cur_mesh_idx += 1
        return elem

    def get_road_sections_layout(self, state, runtime_state):
        # the vertices of each mesh section used by the psdl road (and by the BAI), and the psdl road kind
        section_verts = []
        cur_v = 0
        sw_skip = 3 if self.road_has_sidewalks(state, runtime_state) else 0
        div_skip = 0
        num_tex = 0
        div_type = None
        div_caps = None
        div_param = None
        if self.road_has_divider(state):
            div_caps = '3'
            if state['divider'] == 1:
                div_skip = 2
                div_type = 'F'
                div_param = str(int(state['dividerParam'] * 256))
            elif state['divider'] == 2:
                div_skip = 10
                div_type = 'E'
                div_param = str(int(state['dividerParam'] * 256))
            elif state['divider'] == 3:
                div_skip = 6
                div_type = 'W'
        if state['isDouble']:
            if div_skip > 0:
                elem_name = 'ROADD' if sw_skip == 3 else 'ROADDN'
                num_tex = 7
            else:
                elem_name = 'ROADS' if sw_skip == 3 else 'ROADSN'
                num_tex = 3
            if sw_skip == 3:
                section_verts.append(cur_v)
                cur_v += 1
            cur_v += sw_skip
            section_verts.append(cur_v)
            cur_v += 1
            if div_skip > 0:
                section_verts.append(cur_v)
            cur_v += 1 #+ div_skip
            if div_skip > 0:
                section_verts.append(cur_v)
                cur_v += 1
            section_verts.append(cur_v)
            cur_v += 1 + sw_skip
            if sw_skip == 3:
                section_verts.append(cur_v)
                cur_v += 1
        else:
            elem_name = 'ROADN'
            num_tex = 1
            section_verts.append(cur_v)
            section_verts.append(cur_v + 1)
            cur_v += 2
        section_verts.reverse() #they're reversed compared to the psdl requirements
        return {
            'section_verts': section_verts,
            'elem_name': elem_name,
            'num_tex': num_tex,
            'div_type': div_type,
            'div_caps': div_caps,
            'div_param': div_param
        }

    def get_geometryless_bai_sections(self, fields):
        # the sections of the BAI of a road without geometry (the bai road type), as get_road_sections_layout gives them
        # from the mesh of a psdl road, from its section vertices: the ones of the type (v0 to v6, as in the psdl type:
        # outer edge, curb and divider of the right side, centre, then the left side), from the left of the road to its
        # right (without the sidewalk height of a psdl road: the curbs are at the height of the outer edges)
        state = fields['state']
        n = fields.get('sectionVertexCount', 0) or 0
        vertices = fields.get('sectionVertices') or []
        if n < 7:
            return []
        if self.road_has_sidewalks(state, fields['runtimeState']):
            order = [6, 5] + ([4, 2] if self.road_has_divider(state) else []) + [1, 0]
        else:
            order = [5] + ([4, 2] if self.road_has_divider(state) else []) + [1]
        return [[vertices[i * n + j] for j in order] for i in range(len(vertices) // n)]

    def get_geometryless_road(self, road):
        # a road without geometry (only its traffic): no parts and no room of its own, its rooms are the ones it lies
        # over (found once all the rooms are known, see resolve_traffic_rooms)
        self.exported_roads[road['id']] = {'elem': None, 'road': road, 'block': None, 'rooms': None,
                                           'bai_sections': self.get_geometryless_bai_sections(road['data']['fields'])}

    def resolve_traffic_rooms(self):
        # the rooms of the roads and intersections without geometry, the ones they lie over: a road in the rooms of its
        # sections, an intersection in the one of its centre (one already used by another BAI intersection gets a
        # warning: the game finds the first intersection of a room, before its roads); one over no room is left out of
        # the BAI, with a warning
        rooms = RoomFinder(self)
        for road_id in list(self.exported_roads):
            rec = self.exported_roads[road_id]
            if rec['block'] is not None:
                continue
            road_rooms = []
            for section in rec['bai_sections']:
                room = rooms.room_of(np.mean(np.array(section, dtype=float), axis=0))
                if room > 0 and room not in road_rooms:
                    road_rooms.append(room)
            name = rec['road']['data']['name']
            if len(road_rooms) == 0:
                if len(rec['bai_sections']) > 0:
                    report.warning('the road ' + name + ' has no geometry and is not over any room, it is left out of the BAI',
                                   element=name, kind='road')
                del self.exported_roads[road_id]
                continue
            rec['block'] = road_rooms[0]
            rec['rooms'] = road_rooms
        used = set(obj[2] for obj in self.traffic_intersections if obj[2] is not None)
        resolved = []
        for obj in self.traffic_intersections:
            surface, intersection, block = obj
            if block is not None:
                resolved.append(obj)
                continue
            name = intersection['data']['name']
            room = rooms.room_of(intersection['center'])
            if room == 0:
                report.warning('the intersection ' + name + ' has no geometry and is not over any room, it is left out of the BAI',
                               element=name, kind='intersection')
                continue
            if room in used:
                report.warning('the intersection ' + name + ' has no geometry and is over a room with another BAI intersection: '
                               'the game finds only the first one of a room', element=name, kind='intersection')
            used.add(room)
            resolved.append([surface, intersection, room])
        self.traffic_intersections[:] = resolved

    def has_psdl_props(self, prop_rule):
        # whether a road prop rule has psdl props containers on its sides
        if type(prop_rule) is not dict:
            return False
        return any(state_val(state_val(prop_rule, side), 'type') == 'psdl' for side in ('left', 'right'))

    def get_psdl_prop_rule(self, prop_rule):
        # the number of the psdl prop rule of a road (its psdl props containers), None if it has none
        if type(prop_rule) is not dict:
            return None
        left_rule = state_val(prop_rule, 'left')
        if state_val(left_rule, 'type') != 'psdl':
            left_rule = None
        right_rule = state_val(prop_rule, 'right')
        if state_val(right_rule, 'type') != 'psdl':
            right_rule = None
        if left_rule is None and right_rule is None:
            return None
        rule = (left_rule, right_rule)
        if rule not in self.prop_rules:
            self.prop_rules.append(rule)
        return str(self.prop_rules.index(rule) + 1)

    def get_psdl_road(self,
                      mesh,
                      num_segments,
                      parent_intersection,
                      runtime_state,
                      state,
                      vps,
                      cur_block,
                      og_name,
                      prop_rule,
                      instance_state,
                      has_start_intersection,
                      has_end_intersection,
                      res,
                      open_start=False,
                      open_end=False):
        # open_start/open_end: the start/end of the part is a joint with another part of the same road (split_long_road),
        # without caps on the divider and the rails
        layout = self.get_road_sections_layout(state, runtime_state)
        section_verts = layout['section_verts']
        elem_name = layout['elem_name']
        num_tex = layout['num_tex']
        div_type = layout['div_type']
        div_caps = layout['div_caps']
        div_param = layout['div_param']
        textures = ''
        if num_tex == 1:
            textures = self.get_tex(state['texture1'])
        elif num_tex >= 3:
            textures = self.get_tex(state['texture1']) + ',' + self.get_tex(state['texture0']) + ',' + self.get_tex(state['textureLOD'])
            if num_tex == 7:
                textures += ','
                for i in range(2, 6):
                    comma = ',' if i < 5 else ''
                    textures += self.get_tex(state['texture' + str(i)]) + comma
        vertices = []
        indices = []
        for i in range(num_segments):
            # the road mesh
            for j in section_verts:
                vertices.append(mesh['vertices'][i * vps + j])
            if i < num_segments - 1:
                for j in range(len(section_verts) - 1):
                    sec_indices = self.get_section_indices_rev(j, len(section_verts), i)
                    indices.extend(sec_indices)
        elem = ExportedCityElement()
        elem.indices = indices
        elem.vertices = vertices
        elem.name = str(cur_block) + '_' + elem_name
        elem.properties['original_name'] = og_name

        # psdl prop rules
        if parent_intersection is None and self.road_has_sidewalks(state, runtime_state):
            rule = self.get_psdl_prop_rule(prop_rule)
            if rule is not None:
                elem.properties['prop_rule'] = rule
        elif parent_intersection is None and self.has_psdl_props(prop_rule):
            # the game places the props of a prop rule along the sidewalks of a room only
            report.warning('the road ' + og_name + ' has PSDL props but no sidewalks, where the game places them: they '
                           'are not exported (use another props type, such as Custom line)', element=og_name, kind='road')

        if state['echo']: elem.properties['echo'] = '1'
        if state_bool(instance_state, 'warp'): elem.properties['warp'] = '1'
        if div_type is not None: elem.properties['divider_type'] = str(div_type)
        if div_caps is not None:
            # 1 = start cap, 2 = end cap, 3 = both
            div_caps = str((0 if open_start else 1) + (0 if open_end else 2))
            elem.properties['caps'] = div_caps
        if div_param is not None: elem.properties['divider_param'] = str(div_param)
        elem.mat = textures
        self.cur_road_key += 1
        elem.properties['original_id'] = 'r' + str(self.cur_road_key)
        res.append(elem)

        if parent_intersection is not None:
            pass  # a piece of road through an intersection has no rails (rail_typeI of the road type)
        elif self.road_has_rail(state):
            def rail_val(state, name, default):
                return state_val(state, 'rail_' + name, default)
            def rail_bool(state, name, extra_condition = True):
                val = rail_val(state, name, False)
                return '1' if val and extra_condition else '0'
            def rail_bool_inv(state, name, extra_condition = True):
                val = rail_val(state, name, False)
                return '0' if val and extra_condition else '1'
            def rail_equals(state, name, value):
                val = rail_val(state, name, -1)
                return '1' if val == value else '0'
            rl_elem = ExportedCityElement()
            rl_elem.vertices = []
            rl_elem.indices = []
            rl_elem.name = str(cur_block) + '_RAIL'
            rl_elem.properties['has_left'] = rail_bool(state, 'hasLeft')
            rl_elem.properties['has_right'] = rail_bool(state, 'hasRight')
            rl_elem.properties['is_wall'] = rail_equals(state, 'type', 2)
            rl_elem.properties['is_flat_gallery'] = rail_equals(state, 'type', 3)
            rl_elem.properties['cap_start_left'] = '0' if open_start else rail_bool_inv(instance_state, 'continueLeftOnStartIntersection', has_start_intersection)
            rl_elem.properties['cap_end_left'] = '0' if open_end else rail_bool_inv(instance_state, 'continueLeftOnEndIntersection', has_end_intersection)
            rl_elem.properties['cap_start_right'] = '0' if open_start else rail_bool_inv(instance_state, 'continueRightOnStartIntersection', has_start_intersection)
            rl_elem.properties['cap_end_right'] = '0' if open_end else rail_bool_inv(instance_state, 'continueRightOnEndIntersection', has_end_intersection)
            rl_elem.properties['is_curved_gallery'] = rail_equals(state, 'type', 4)
            rl_elem.properties['offset_start_left'] = '0' if open_start else rail_bool(state, 'offsetStartLeft')
            rl_elem.properties['offset_end_left'] = '0' if open_end else rail_bool(state, 'offsetEndLeft')
            rl_elem.properties['offset_start_right'] = '0' if open_start else rail_bool(state, 'offsetStartRight')
            rl_elem.properties['offset_end_right'] = '0' if open_end else rail_bool(state, 'offsetEndRight')
            rl_elem.properties['curved_sides'] = '0' #todo
            rl_elem.properties['is_rail'] = rail_equals(state, 'type', 1)
            rl_elem.properties['height'] = str(int(rail_val(state, 'height', 0.0) * 256.0))
            rl_elem.properties['original_name'] = og_name + ' [rail]'
            rl_elem.properties['road_name'] = elem.properties['original_id']
            rl_elem.mat = ''
            for i in range(6):
                comma = ',' if i < 5 else ''
                rl_elem.mat += self.get_tex(rail_val(state, 'texture' + str(i), '')) + comma
            res.append(rl_elem)
        return elem

    def get_pkg_road(self,
                     mesh,
                     road,
                     runtime_state,
                     state,
                     num_segments,
                     cur_block,
                     og_name,
                     vps,
                     res):
        # empty block to contain the pkg
        psdl_block = []
        indices = []
        if vps <= 2:
            for i in range(num_segments):
                psdl_block.append(mesh['vertices'][i * vps])
                psdl_block.append(mesh['vertices'][(i + 1) * vps - 1])
            for i in range(num_segments - 1):
                # triangle 1
                indices.append(2 * i)
                indices.append(2 * i + 1)
                indices.append(2 * i + 2)
                # triangle 2
                indices.append(2 * i + 1)
                indices.append(2 * i + 3)
                indices.append(2 * i + 2)
        else:
            sw_skip = 3 if self.road_has_sidewalks(state, runtime_state) else 0
            for i in range(num_segments):
                psdl_block.append(mesh['vertices'][i * vps])
                psdl_block.append(mesh['vertices'][i * vps + sw_skip])
                psdl_block.append(mesh['vertices'][(i + 1) * vps - 1 - sw_skip])
                psdl_block.append(mesh['vertices'][(i + 1) * vps - 1])
            for i in range(num_segments - 1):
                for j in range(3):
                    # triangle 1
                    indices.append(4 * i + j)
                    indices.append(4 * i + j + 1)
                    indices.append(4 * i + j + 4)
                    # triangle 2
                    indices.append(4 * i + j + 1)
                    indices.append(4 * i + j + 5)
                    indices.append(4 * i + j + 4)
        elem_pkg = self.get_mesh(road['data']['mesh'], cur_block, 'VL', og_name)
        if res is not None:
            elem = ExportedCityElement()
            elem.indices = indices
            elem.vertices = psdl_block
            elem.name = str(cur_block) + '_NUL'
            elem.properties['original_name'] = og_name
            res.append(elem)
            res.append(elem_pkg)
            return elem
        else:
            return {"nul": {"indices": indices, "vertices": psdl_block}, "pkg": elem_pkg}

    def forced_bottom(self, res, mesh, state, vps, num_segments, sections, cur_block, og_name):
        # the bottom wall of a road with "Force bottom wall" (rail_forceBottom) where the PSDL tunnel doesn't draw it
        # (it does only for walls on both sides), as a PKG mesh in the room of the road (sections: the first and last
        # section of the room for a road exported as several rooms, None for the whole road). Its triangles are the last
        # submesh of the road: the one of the last texture slot (rail_texture5), used only by the bottom wall
        if not state_bool(state, 'rail_forceBottom'):
            return
        if state_int(state, 'rail_type') == 2 and state_bool(state, 'rail_hasLeft') and state_bool(state, 'rail_hasRight'):
            return
        submeshes = mesh.get('submeshes') or []
        if not submeshes:
            return
        bottom = submeshes[-1]
        texture = state_val(state, 'rail_texture5', None)
        if not texture or self.get_mesh_mat(bottom['materialId']) != self.get_tex(texture):
            report.warning('the bottom wall of the road ' + og_name + ' was not exported: it has no ground texture',
                           element=og_name, kind='road')
            return
        first, last = sections if sections is not None else (0, num_segments - 1)
        indices = bottom['indices']
        kept = []
        for t in range(0, len(indices) - 2, 3):
            tri = indices[t:t + 3]
            if all(i < num_segments * vps and first <= i // vps <= last for i in tri):
                kept.extend(tri)
        if not kept:
            return
        used = sorted(set(kept))
        remap = {old: new for new, old in enumerate(used)}

        def pick(values):
            return [values[i] for i in used] if values is not None and len(values) == len(mesh['vertices']) else None
        part = {'vertices': pick(mesh['vertices']), 'normals': pick(mesh.get('normals')),
                'uvs': pick(mesh.get('uvs')) or [(0, 0)] * len(used),
                'submeshes': [{'materialId': bottom['materialId'], 'indices': [remap[i] for i in kept]}]}
        if part['normals'] is None:
            part['normals'] = [(0.0, 1.0, 0.0)] * len(used)
        elem = self.get_mesh(part, cur_block, 'VL', og_name + ' [bottom]')
        elem.properties['unlit'] = '1'  # lit as if facing up (see PKGWriter)
        res.append(elem)

    def split_long_road(self, res, road, mesh, num_segments, runtime_state, state, vps, og_name, prop_rule,
                        instance_state, has_start_intersection, has_end_intersection):
        # a PSDL road with more than MAX_ROAD_SECTIONS sections, exported as consecutive rooms of at most that many
        # sections, sharing the section at each joint (the game draws a long road room broken, see MAX_ROAD_SECTIONS);
        # the BAI keeps a single road through all the rooms. Returns the part of the first room
        pieces = math.ceil((num_segments - 1) / (MAX_ROAD_SECTIONS - 1))
        bounds = [round(k * (num_segments - 1) / pieces) for k in range(pieces + 1)]
        report.warning('the road ' + og_name + ' has ' + str(num_segments) + ' sections: it is exported as ' + str(pieces)
                       + ' rooms of at most ' + str(MAX_ROAD_SECTIONS) + ' sections (the game draws longer road rooms '
                       'broken); split the road to choose where', element=og_name, kind='road')
        rooms = []
        first = None
        for k in range(pieces):
            a, b = bounds[k], bounds[k + 1]
            n = b - a + 1
            piece_mesh = {'vertices': mesh['vertices'][a * vps:(b + 1) * vps]}
            block = len(self.block_perimeters) + 1
            elem = self.get_psdl_road(piece_mesh, n, None, runtime_state, state, vps, block, og_name, prop_rule,
                                      instance_state, has_start_intersection, has_end_intersection, res,
                                      open_start=k > 0, open_end=k < pieces - 1)
            self.forced_bottom(res, mesh, state, vps, num_segments, (a, b), block, og_name)
            first = first or elem
            perimeter = [piece_mesh['vertices'][i * vps] for i in range(n)]
            perimeter += [piece_mesh['vertices'][(i + 1) * vps - 1] for i in range(n - 1, -1, -1)]
            self.add_block_perimeter(perimeter, 0)
            rooms.append(block)
        self.element_rooms[('road', road['id'])] = rooms
        return first

    def get_road(self,
                 res,
                 road,
                 instance_state,
                 has_start_intersection,
                 has_end_intersection,
                 in_block,
                 cur_block,
                 manual_blocks,
                 parent_intersection = None):
        if state_bool(instance_state, 'doNotExport'):
            return
        if road['data']['fields'].get('geometryless') and parent_intersection is None:
            self.get_geometryless_road(road)
            return
        state = road['data']['fields']['state']
        runtime_state = road['data']['fields']['runtimeState']
        block_perimeters = self.block_perimeters
        mesh = road['data']['mesh']
        og_name = road['data']['name'] if parent_intersection == None else parent_intersection['data']['name']
        if cur_block == -1:
            cur_block = len(block_perimeters) + 1
            block_number = self.get_manual_block_number(state)
            if block_number > 0 and block_number in manual_blocks:
                cur_block = manual_blocks.index(block_number) + 1
        if parent_intersection is None:
            self.element_blocks[('road', road['id'])] = cur_block
        vps = road['data']['fields']['vertsPerSection']
        num_segments = self.road_section_count(road, mesh, state, vps)
        prop_rule = state_val(state, 'propRule')

        #get the block
        block = []
        for i in range(num_segments):
            # one block side (road forward, from start to end)
            block.append(mesh['vertices'][i * vps])
        for i in range(num_segments - 1, -1, -1): # the order is important to obtain a valid polygon
            # the other block side (road backward, from end to start)
            block.append(mesh['vertices'][(i + 1) * vps - 1])

        is_psdl = state['type'] == 'psdl' and not state_bool(instance_state, 'exportToPKG')
        split = (is_psdl and parent_intersection is None and in_block is None and num_segments > MAX_ROAD_SECTIONS
                 and cur_block == len(block_perimeters) + 1)
        if split:
            elem = self.split_long_road(res, road, mesh, num_segments, runtime_state, state, vps, og_name, prop_rule,
                                        instance_state, has_start_intersection, has_end_intersection)
        elif is_psdl:
            elem = self.get_psdl_road(mesh,
                                      num_segments,
                                      parent_intersection,
                                      runtime_state,
                                      state,
                                      vps,
                                      cur_block,
                                      og_name,
                                      prop_rule,
                                      instance_state,
                                      has_start_intersection,
                                      has_end_intersection,
                                      res)
            if parent_intersection is None:
                self.forced_bottom(res, mesh, state, vps, num_segments, None, cur_block, og_name)
        else: #non psdl road, export to pkg
            elem = self.get_pkg_road(mesh,
                                     road,
                                     runtime_state,
                                     state,
                                     num_segments,
                                     cur_block,
                                     og_name,
                                     vps,
                                     res)

        # non-psdl props
        self.get_road_props(res, road, prop_rule, og_name)

        if parent_intersection is None:
            # the BAI uses the vertices of the psdl road sections (also for the roads exported to pkg)
            bai_verts = self.get_road_sections_layout(state, runtime_state)['section_verts']
            bai_sections = [[mesh['vertices'][i * vps + j] for j in bai_verts] for i in range(num_segments)]
            self.exported_roads[road['id']] = {'elem': elem, 'road': road, 'block': cur_block,
                                               'rooms': self.element_rooms.get(('road', road['id'])),
                                               'bai_sections': bai_sections}

        if split:
            pass  # the rooms of the parts are already added
        elif in_block is None:
            if cur_block == len(block_perimeters) + 1:
                self.add_block_perimeter(block, 0)
            else:
                self.extend_block_perimeter(cur_block - 1, block)
        else:
            in_block.append(block)

    def get_road_props(self, res, road, prop_rule, og_name):
        # the props of the containers of the prop rule that are not psdl (instances along the road)
        prop_lines = road['data']['propLines'] if 'propLines' in road['data'] else None
        if prop_lines is not None and type(prop_rule) is dict:
            for key in prop_rule:
                value = prop_rule[key]
                if isinstance(value, dict) and value['type'] not in ('psdl', *PARKED_CARS_TYPES):
                    for value2 in prop_lines:
                        if value2['name'] == key:
                            # TODO: prop lines
                            for prop in placed_props(value2):
                                dict_mesh = self.data['meshDict'][int(prop['meshId'])]
                                prop_elem = ExportedCityElement()
                                cube = self.get_cube(1)
                                prop_elem.vertices = cube['vertices']
                                prop_elem.indices = cube['indices']
                                mesh_name_parts = dict_mesh['name'].replace('\\', '/').split('/')
                                mesh_name = mesh_name_parts[-1].split('.')[0]
                                no_transf = prop['rotation'] == (0, 0, 0, 1) and prop['scale'] == (1, 1, 1)
                                flags = '0' if no_transf else '1'
                                prop_elem.name = '0_PTH'
                                prop_elem.properties['original_name'] = og_name + ' [prop]'
                                prop_elem.properties['object'] = mesh_name
                                prop_elem.properties['flags'] = flags
                                prop_elem.translation = prop['position']
                                prop_elem.rotation = prop['rotation']
                                prop_elem.scale = prop['scale']
                                prop_elem.mat = 'NONE'
                                res.append(prop_elem)
                            break

    def get_split_submeshes(self, mesh):
        res = []
        for i in range(len(mesh['submeshes'])):
            sm = mesh['submeshes'][i]
            vertices = []
            indices = []
            p = {}
            inds = []
            for ind in sm['indices']:
                if ind not in inds: inds.append(ind)
            inds.sort()
            for ind in inds:
                vertices.append(mesh['vertices'][ind])
            for ind in sm['indices']:
                indices.append(inds.index(ind))
            p['vertices'] = vertices
            p['indices'] = indices
            res.append(p)
        return res

    def get_junction_rail(self, res, rs, vertices, indices, cur_block, parent):
        def rail_val(state, name, default):
            return state_val(state, 'rail_' + name, default)
        rs_t = rs['rail_type']
        rl_elem = ExportedCityElement()
        rl_elem.vertices = vertices
        rl_elem.indices = indices
        rl_elem.name = str(cur_block) + '_RAILC'
        rl_elem.properties['is_wall'] = '1' if rs_t == 2 else '0'
        rl_elem.properties['is_flat_gallery'] = '1' if rs_t == 3 else '0'
        rl_elem.properties['cap_start_left'] = '1' #all sides closed
        rl_elem.properties['cap_end_left'] = '1'
        rl_elem.properties['cap_start_right'] = '1'
        rl_elem.properties['cap_end_right'] = '1'
        rl_elem.properties['is_curved_gallery'] = '1' if rs_t == 4 else '0'
        rl_elem.properties['offset_start_left'] = '0' #no offsets
        rl_elem.properties['offset_end_left'] = '0'
        rl_elem.properties['offset_start_right'] = '0'
        rl_elem.properties['offset_end_right'] = '0'
        rl_elem.properties['curved_sides'] = '0' #todo
        rl_elem.properties['is_rail'] = '1' if rs_t == 1 else '0'
        rl_elem.properties['height'] = str((int)(rs['rail_height'] * 256.0))
        rl_elem.properties['original_name'] = parent['data']['name'] + ' [rail]'
        rl_elem.mat = ''
        for i in range(6):
            comma = ',' if i < 5 else ''
            rl_elem.mat += self.get_tex(rail_val(rs, 'texture' + str(i), '')) + comma
        res.append(rl_elem)

    def road_has_any_rail(self, road, intersection, sw_start):
        state = road['data']['fields']['state']
        i_state = road['data']['fields']['instanceState']
        end_int = road['endIntersectionId']
        int_id = intersection['id']
        is_end = end_int == int_id
        has_left = state_bool(state, 'rail_hasLeft')
        has_right = state_bool(state, 'rail_hasRight')
        cont_end_left = state_bool(i_state, 'rail_continueLeftOnEndIntersection')
        cont_end_right = state_bool(i_state, 'rail_continueRightOnEndIntersection')
        cont_start_left = state_bool(i_state, 'rail_continueLeftOnStartIntersection')
        cont_start_right = state_bool(i_state, 'rail_continueRightOnStartIntersection')
        if sw_start:
            return (is_end and cont_end_left and has_left) or (not is_end and cont_start_left and has_left)
        else:
            return (is_end and cont_end_right and has_right) or (not is_end and cont_start_right and has_right)

    def road_has_rail_type(self, typ, road, intersection, sw_start):
        state = road['data']['fields']['state']
        return state['rail_type'] == typ and self.road_has_any_rail(road, intersection, sw_start)

    def get_junction_rail_type_owner(self, typ, road0, road1, intersection):
        a_has_rail = self.road_has_rail_type(typ, road0, intersection, True)
        b_has_rail = self.road_has_rail_type(typ, road1, intersection, False)
        a_has_any_rail = self.road_has_any_rail(road0, intersection, True)
        if a_has_rail:
            return 0
        elif b_has_rail and not a_has_any_rail:
            return 1
        else:
            return -1

    def get_junction_rail_state(self, road0, road1, intersection):
        res1 = self.get_junction_rail_type_owner(1, road0, road1, intersection)
        res2 = self.get_junction_rail_type_owner(2, road0, road1, intersection)
        res3 = self.get_junction_rail_type_owner(3, road0, road1, intersection)
        res4 = self.get_junction_rail_type_owner(4, road0, road1, intersection)
        owner_id = max(res1, res2, res3, res4)
        if owner_id == 0:
            return road0['data']['fields']['state']
        elif owner_id == 1:
            return road1['data']['fields']['state']
        else:
            return None

    def get_psdl_intersection(self, res, intersection, manual_blocks, state, block, mesh, cur_block):
        roads = intersection['roadsThrough']
        for road in roads:
            self.get_road(res, road, [], False, False, block, cur_block, manual_blocks, intersection)
        submeshes = self.get_split_submeshes(mesh)
        traffic_added = False
        cur_part_types = intersection['data']['fields']['partsInfo']
        roadsJ = intersection['roads']
        # the junctions are between the roads with geometry (the ones without it are left out of the surface)
        geometry_order = intersection['data']['fields'].get('geometrySortOrder')
        if geometry_order is None:
            geometry_order = intersection['data']['fields']['sortOrder']
        for i in range(len(submeshes)):
            p = submeshes[i]
            mat_id = mesh['submeshes'][i]['materialId']
            mat_tex = self.data['materialDict'][mat_id]['data']['texture'] if mat_id >= 0 else None
            if '.' in cur_part_types[i]:
                typ_parts = cur_part_types[i].split('.')
                typ = typ_parts[0]
                cur_junction = int(typ_parts[1])
            else:
                typ = cur_part_types[i]
                cur_junction = -1
            if typ == 'junction_1': #rail
                road1I = geometry_order[cur_junction]
                road0I = geometry_order[(cur_junction + 1) if (cur_junction + 1) < len(geometry_order) else 0]
                road0 = self.data['roads'][roadsJ[road0I]]
                road1 = self.data['roads'][roadsJ[road1I]]
                rs = self.get_junction_rail_state(road0, road1, intersection)
                # a corner of no length (the mouths of the two roads meet at a point, as between roads diverging
                # without crosswalks) has no edge to put a rail on
                flat = [(vx[0], vx[2]) for vx in p['vertices']]
                degenerate = len(flat) == 0 or max(math.dist(flat[0], q) for q in flat) < 0.01
                if rs is not None and not degenerate:
                    self.get_junction_rail(res, rs, p['vertices'], p['indices'], cur_block, intersection)
            elif typ == 'junction_0': #sidewalk
                elem = ExportedCityElement()
                sw_indices = []
                sw_vertices = []
                if state_bool(state, 'fixSidewalksUV'):
                    for j in range(len(p['vertices']) - 4, -1, -4):
                        for n in range(3):
                            sw_vertices.append(p['vertices'][j])
                        sw_vertices.append(p['vertices'][j + 3])
                        if j < len(p['vertices']) - 4:
                            sw_indices.extend(self.get_section_indices_rev(2, 4, j // 4))
                else:
                    for j in range(len(p['vertices']) - 4, -1, -4):
                        sw_vertices.append(p['vertices'][j + 3])
                        sw_vertices.append(p['vertices'][j])
                        if j < len(p['vertices']) - 4:
                            sw_indices.extend(self.get_section_indices(0, 2, j // 4))
                elem.indices = sw_indices
                elem.vertices = sw_vertices
                elem.properties['original_name'] = intersection['data']['name']
                if state_bool(state, 'fixSidewalksUV'):
                    elem.name = str(cur_block) + '_ROADS'
                    tex0 = self.get_tex(state_val(state, 'texture0'))
                    elem.mat = tex0 + ',' + tex0 + ',' + tex0
                else:
                    elem.name = str(cur_block) + '_SW'
                    elem.mat = ''
                    # the sidewalk texture first: the writer takes it as the sidewalk texture of the intersection
                    # (the one after its road texture, used by the sidewalk strips), the others are unused
                    for i in ['0', '1', '2']:
                        comma = ',' if i != '2' else ''
                        elem.mat += self.get_tex(state_val(state, 'texture' + i)) + comma
                res.append(elem)
                block.append(sw_vertices)
            elif typ == 'terrain' or typ == 'crosswalk':
                name = '_CW' if typ == 'crosswalk' else '_IS'
                elem = ExportedCityElement()
                elem.indices = p['indices']
                elem.vertices = p['vertices']
                elem.name = str(cur_block) + name
                elem.properties['original_name'] = intersection['data']['name']
                if state_bool(state, 'echo'):
                    elem.properties['echo'] = '1'
                if state_bool(intersection['data']['fields']['instanceState'], 'warp'): elem.properties['warp'] = '1'
                elem.mat = self.get_tex(mat_tex) + ','
                for i in ['0', '2']:
                    comma = ',' if i != '2' else ''
                    elem.mat += self.get_tex(state_val(state, 'texture' + i)) + comma
                res.append(elem)
                block.append(p['vertices'])
                if not traffic_added and typ == 'terrain' and len(roadsJ) > 0:
                    self.traffic_intersections.append([elem, intersection, cur_block])
                    traffic_added = True

    def get_pkg_road_through(self,
                             road,
                             cur_block,
                             parent_intersection):
        state = road['data']['fields']['state']
        mesh = road['data']['mesh']
        og_name = parent_intersection['data']['name']
        vps = road['data']['fields']['vertsPerSection']
        num_segments = self.road_section_count(road, mesh, state, vps)
        return self.get_pkg_road(mesh,
                                 road,
                                 road['data']['fields']['runtimeState'],
                                 state,
                                 num_segments,
                                 cur_block,
                                 og_name,
                                 vps,
                                 None)

    def get_pkg_intersection(self, res, intersection, state, block, mesh, cur_block):
        nul_block = []
        roads = intersection['roadsThrough']
        for road in roads:
            subroad = self.get_pkg_road_through(road, cur_block, intersection)
            nul_block.append(subroad["nul"])
            res.append(subroad["pkg"])
        submeshes = self.get_split_submeshes(mesh)
        cur_part_types = intersection['data']['fields']['partsInfo']
        for i in range(len(submeshes)):
            p = submeshes[i]
            if '.' in cur_part_types[i]:
                typ_parts = cur_part_types[i].split('.')
                typ = typ_parts[0]
            else:
                typ = cur_part_types[i]
            if typ == 'junction_0': #sidewalk
                sw_indices = []
                sw_vertices = []
                for j in range(len(p['vertices']) - 4, -1, -4):
                    sw_vertices.append(p['vertices'][j + 3])
                    sw_vertices.append(p['vertices'][j])
                    if j < len(p['vertices']) - 4:
                        sw_indices.extend(self.get_section_indices(0, 2, j // 4))
                nul_block.append({"indices": sw_indices, "vertices": sw_vertices})
            elif typ == 'terrain' or typ == 'crosswalk':
                nul_block.append({"indices": p['indices'], "vertices": p['vertices']})
        traf_elem = None
        for elem0 in nul_block:
            nul_elem = ExportedCityElement()
            nul_elem.indices = elem0['indices']
            nul_elem.vertices = elem0['vertices']
            nul_elem.name = str(cur_block) + "_NUL"
            nul_elem.properties['original_name'] = intersection['data']['name']
            res.append(nul_elem)
            traf_elem = nul_elem
        elem = self.get_mesh(intersection['data']['mesh'], cur_block, 'VL', intersection['data']['name'])
        res.append(elem)
        if len(intersection['roads']) > 0:
            self.traffic_intersections.append([traf_elem, intersection, cur_block])

    def get_intersection(self, res, intersection, manual_blocks):
        state = intersection['data']['fields']['state']
        instance_state = intersection['data']['fields']['instanceState']
        if state['type'] != 'psdl' or is_seamless(intersection):
            return
        if intersection['data']['fields'].get('geometryless'):
            # only roads without geometry: no parts, in the room it lies over (see resolve_traffic_rooms)
            if len(intersection['roads']) > 0:
                self.traffic_intersections.append([None, intersection, None])
            return
        block_perimeters = self.block_perimeters
        mesh = intersection['data']['mesh']
        cur_block = len(block_perimeters) + 1
        block_number = self.get_manual_block_number(state)
        if block_number > 0 and block_number in manual_blocks:
            cur_block = manual_blocks.index(block_number) + 1
        self.element_blocks[('intersection', intersection['id'])] = cur_block
        block = []
        if not state_bool(instance_state, 'exportToPKG'):
            self.get_psdl_intersection(res, intersection, manual_blocks, state, block, mesh, cur_block)
        else:
            self.get_pkg_intersection(res, intersection, state, block, mesh, cur_block)
        if cur_block == len(block_perimeters) + 1:
            self.add_block_perimeter_multi(block, 0)
        else:
            self.extend_block_perimeter(cur_block - 1, block)

    def find_vector(self, lst, item):
        for i in range(len(lst)):
            if lst[i] == item:
                return i
        return -1

    def is_point_in_block_perimeter(self, block, p):
        for perimeter in block:
            if self.find_vector(perimeter, p) != -1:
                return True
        return False

    def get_real_patch_block(self, patch):
        state = patch['data']['fields']['state']
        if not state_bool(state, 'mergeWithConnected'):
            return 0
        block_perimeters = self.block_perimeters
        p = patch['perimeterPoints']
        for i in range(len(block_perimeters)):
            block = block_perimeters[i]
            if block[1] == 1:
                for j in range(len(p)):
                    v0 = p[j]
                    v1 = p[0 if (j == len(p) - 1) else (j + 1)]
                    if self.is_point_in_block_perimeter(block[0], v0) and self.is_point_in_block_perimeter(block[0], v1):
                        return i + 1
        return 0

    def get_patch(self, res, patch, manual_blocks):
        state = patch['data']['fields']['state']
        if state['type'] != 'psdl':
            return
        block_perimeters = self.block_perimeters
        cur_block = len(block_perimeters) + 1
        detected_block = self.get_real_patch_block(patch)
        if detected_block != 0:
            cur_block = detected_block
        block_number = self.get_manual_block_number(state)
        if block_number > 0 and block_number in manual_blocks:
            cur_block = manual_blocks.index(block_number) + 1
        self.element_blocks[('terrainPatch', patch['id'])] = cur_block
        split_parts = self.get_split_submeshes(patch['data']['mesh'])
        elem = ExportedCityElement()
        elem.indices = split_parts[0]['indices']
        elem.vertices = split_parts[0]['vertices']
        to_pkg = state_bool(state, 'exportToPKG')
        is_nul = state_bool(state, 'invisible') or to_pkg
        elem.name = str(cur_block) + ('_NUL' if is_nul else '_BLOCK')
        if state_bool(state, 'echo'):
            elem.properties['echo'] = '1'
        if state.get('warp', False): elem.properties['warp'] = '1'

        elem.mat = self.get_tex(state_val(state, 'texture', None))
        res.append(elem)
        if detected_block == 0:
            if cur_block == len(block_perimeters) + 1:
                self.add_block_perimeter(patch['perimeterPoints'], 1 if state_bool(state, 'mergeWithConnected') else 0)
            else:
                self.extend_block_perimeter(cur_block - 1, patch['perimeterPoints'])
        else:
            self.extend_block_perimeter(detected_block - 1, patch['perimeterPoints'])

        if to_pkg:
            res.append(self.get_mesh(patch['data']['mesh'], cur_block, 'VL', patch['data']['name']))
            self.pkg_blocks.add(cur_block)  # no rails (see get_rail)
        elif state_bool(state, 'forceBottom') and state_val(state, 'bottomTexture', None):
            # the bottom wall under the patch (made by the geometry script of the patch type: the last submesh of its mesh), which the
            # PSDL can't draw: an unlit PKG mesh in the room of the patch
            mesh = patch['data']['mesh']
            if len(mesh.get('submeshes') or []) >= 2:
                bottom = mesh['submeshes'][-1]
                part = {'vertices': mesh['vertices'], 'normals': mesh.get('normals'), 'uvs': mesh.get('uvs'),
                        'submeshes': [bottom]}
                elem = self.get_mesh(part, cur_block, 'VL', patch['data']['name'] + ' [bottom]')
                elem.properties['unlit'] = '1'
                res.append(elem)

    # Rails: the RAILC attributes of the rooms, from the rail custom elements. A rail is a spline through perimeter points
    # of its room (the terrain patch, road or intersection of its "room" reference), and goes in the room of that element.
    # Without a room (e.g. the room deleted), each of its edges goes to the room whose perimeter has it; an edge shared by
    # two rooms (e.g. between a patch and a road) goes to the one on the side of the rail: seen from above, a rail goes
    # clockwise around its room (as the editor draws it, on the outside)

    RAIL_TOLERANCE = 0.01

    def rail_point_index(self, perimeter, p):
        for i, v in enumerate(perimeter):
            if abs(v[0] - p[0]) < self.RAIL_TOLERANCE and abs(v[1] - p[1]) < self.RAIL_TOLERANCE and abs(v[2] - p[2]) < self.RAIL_TOLERANCE:
                return i
        return -1

    def rail_edge_block(self, a, b):
        # the index of the room of the edge from a to b, -1 if no room has it
        candidates = [i for i in range(len(self.block_perimeters)) if self.rail_edge_in_block(i, a, b)]
        if len(candidates) <= 1:
            return candidates[0] if candidates else -1
        dx, dz = b[0] - a[0], b[2] - a[2]
        length = math.hypot(dx, dz)
        if length > 1e-6:
            # the room is on the right of the direction (the opposite of the localRight of the components)
            probe = ((a[0] + b[0]) * 0.5 + dz / length * 0.1, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5 - dx / length * 0.1)
            for i in candidates:
                if self.is_point_in_block(self.block_perimeters[i][0], probe, self.block_perimeters_bounds[i]):
                    return i
        return candidates[0]

    def rail_edge_in_block(self, index, a, b):
        # the edge from a to b is on the perimeter of the room at the index
        for perimeter in self.block_perimeters[index][0]:
            ia = self.rail_point_index(perimeter, a)
            ib = self.rail_point_index(perimeter, b) if ia != -1 else -1
            if ib != -1 and (abs(ia - ib) == 1 or abs(ia - ib) == len(perimeter) - 1):
                return True
        return False

    def rail_rooms(self, state):
        # the rooms of the element of the "room" reference of a rail (several for a long road, see split_long_road),
        # [] if none
        room = state.get('room')
        if not isinstance(room, dict):
            return []
        key = (room.get('kind'), room.get('id'))
        if key in self.element_rooms:
            return self.element_rooms[key]
        block = self.element_blocks.get(key, 0)
        return [block] if block > 0 else []

    def get_rail(self, res, element):
        data = element.get('data') or {}
        state = (data.get('fields') or {}).get('state') or {}
        name = data.get('name', 'rail')
        if state_int(state, 'rail_type') <= 0:
            return
        rail_state = dict(state)
        rail_state.setdefault('rail_height', 0.0)
        points = [tuple(section['center']) for section in (element.get('spline') or {}).get('sections') or []]
        if len(points) < 2:
            report.warning('the rail ' + name + ' has less than two points, it is not exported', element=report.element_name(name))
            return
        # the runs of consecutive edges in the same room
        runs = []
        outside = 0
        rooms = self.rail_rooms(state)
        for a, b in zip(points, points[1:]):
            if rooms:
                block = next((room for room in rooms if self.rail_edge_in_block(room - 1, a, b)), 0)
            else:
                block = self.rail_edge_block(a, b) + 1
            if block <= 0:
                outside += 1
                continue
            if block in self.pkg_blocks:
                continue
            if runs and runs[-1][0] == block and runs[-1][1][-1] == a:
                runs[-1][1].append(b)
            else:
                runs.append((block, [a, b]))
        if outside > 0:
            report.warning(str(outside) + ' edges of the rail ' + name + ' are not on the perimeter of a room, they are not exported',
                           element=report.element_name(name))
        for block, run in runs:
            vertices = []
            indices = []
            for j, p in enumerate(run):
                vertices.append(np.array(p))
                vertices.append(np.add(p, (0.0, 1.0, 0.0)))
                if j < len(run) - 1:
                    indices.extend(self.get_section_indices_rev(0, 2, j))
            self.get_junction_rail(res, rail_state, vertices, indices, block, element)

    def get_roof(self, res, submesh, cur_block, tex, obj_name):
        if len(submesh['submeshes']) > 0 and len(submesh['submeshes'][0]['indices']) > 0:
            indices = submesh['submeshes'][0]['indices']
            elem = ExportedCityElement()
            elem.vertices = submesh['vertices']
            elem.indices = indices
            elem.name = str(cur_block) + '_ROOF'
            elem.properties['original_name'] = obj_name
            elem.mat = self.get_tex(tex)
            res.append(elem)
        else:
            report.warning('roof on object ' + obj_name + ' has invalid geometry', element=report.element_name(obj_name))

    def get_building_side(self, res, block, both_sides, side, obj_name):
        mat_dict = self.data['materialDict']

        # facade bounds
        coll_verts = side['data']['collider']['vertices']
        num_bounds = (len(coll_verts) // 2) - 1
        bound_indices = [0, 2, 1, 1, 2, 3]
        cur_geo_facade_index = self.cur_facade_index
        for i in range(num_bounds):
            cv = coll_verts
            nb = num_bounds
            bound_verts = [cv[i], cv[i + 1], cv[i + nb + 1], cv[i + nb + 2]]
            elem = ExportedCityElement()
            elem.vertices = bound_verts
            elem.indices = bound_indices
            elem.name = 'f' + str(self.cur_facade_index) + '*' + ',' + str(block) + '_FACB'
            elem.mat = 'NONE'
            elem.properties['original_name'] = obj_name + ' [facade bound]'
            res.append(elem)
            if both_sides:
                mid_front = np.add(bound_verts[0], bound_verts[1]) * 0.5
                mid_dir = np.cross(np.subtract(bound_verts[1], bound_verts[0]), [0, 1, 0])
                mid_dir /= np.linalg.norm(mid_dir)
                center_point = mid_front - 5 * mid_dir
                block2 = self.find_block(center_point) + 1
                if block2 > 0 and block2 != block:
                    elem2 = copy.deepcopy(elem)
                    elem2.name = 'f' + str(self.cur_facade_index) + 'z*' + ',' + str(block2) + '_FACB'
                    res.append(elem2)
            self.cur_facade_index += 1

        # facades
        for facade in side['facades']:
            for key in facade['instances']:
                mesh = side['meshDict'][int(key)]
                sstate = side['data']['fields']['state']
                entry = facade['instances'][key]
                for batch in entry:
                    for i in range(len(mesh['submeshes'])):
                        sm = mesh['submeshes'][i]
                        if sm['materialId'] != -1:
                            for j in range(len(batch)):
                                if len(mesh['vertices']) == 4 and len(mesh['submeshes']) == 1: #TODO: this makes the outer loop useless
                                    vertices_t = []
                                    for vi in range(len(mesh['vertices'])):
                                        v = mesh['vertices'][vi]
                                        v = np.reshape((v[0], v[1], v[2], 1), (1,4))
                                        m = np.reshape(batch[j], (4, 4))
                                        vertices_t.append(np.dot(v, m).reshape(4)[:3])
                                    elem = ExportedCityElement()
                                    elem.vertices = vertices_t
                                    elem.indices = sm['indices']
                                    elem.name = 'f' + str(cur_geo_facade_index) + '+' + ',' + str(block) + '_FAC'
                                    elem.properties['u_tiling'] = str(-int(mesh['uvs'][0][0]))
                                    elem.properties['v_tiling'] = str(int(mesh['uvs'][0][1]))
                                    elem.properties['original_name'] = obj_name + ' [facade]'
                                    mat_id = sm['materialId']
                                    mat_tex = mat_dict[mat_id]['data']['texture']
                                    elem.mat = self.get_tex(mat_tex)
                                    res.append(elem)
            cur_geo_facade_index += 1

        # slivers
        for sliver in side['paramMeshes']:
            elem = ExportedCityElement()
            elem.vertices = sliver['vertices']
            elem.indices = sliver['submeshes'][0]['indices']
            elem.name = str(block) + '_SLIVER'
            elem.properties['tiling'] = str(int(round(self.get_sliver_texture_scale(sliver) * 100)))
            elem.properties['original_name'] = obj_name + ' [sliver]'
            mat_id = sliver['submeshes'][0]['materialId']
            mat_tex = mat_dict[mat_id]['data']['texture']
            elem.mat = self.get_tex(mat_tex)
            res.append(elem)

    def get_sliver_texture_scale(self, sliver):
        # the texture scale of a sliver (repeats per meter, MM2 uses it across the sliver and down from its top
        # edge): v at the bottom over the height, on the taller side (vertices: bottom left, bottom right, top left,
        # top right)
        v = sliver['vertices']
        uvs = sliver['uvs']
        side = max((0, 1), key=lambda i: v[i + 2][1] - v[i][1])
        height = v[side + 2][1] - v[side][1]
        return abs(uvs[side][1] - uvs[side + 2][1]) / height if height > 1e-4 else 1.0

    def closest_point(self, point, line_start, line_end):
        p_m_s = np.subtract(point, line_start)
        e_m_s = np.subtract(line_end, line_start)
        val = np.dot(p_m_s, e_m_s) / (np.linalg.norm(e_m_s)**2)
        t = np.clip(val, 0, 1)
        return np.add(line_start, np.multiply(t, np.subtract(line_end, line_start)))

    def closest_point_to_curve(self, point, curve_points):
        min_dist = float('inf')
        min_p = (0.0, 0.0, 0.0)
        min_i = -1
        for i in range(len(curve_points) - 1):
            p0 = curve_points[i]
            p1 = curve_points[i + 1]
            p = self.closest_point(point, p0, p1)
            d = np.linalg.norm(np.subtract(point, p))
            if d < min_dist:
                min_i = i
                min_dist = d
                min_p = p
        return (min_p, min_i)

    def get_building(self, res, building, obj_name, front_only, both_sides_parent):
        state = building['data']['fields']['state']
        block_perimeters = self.block_perimeters
        curve = building['spline']
        curve_n = building['splineActualNormals']

        #find the block(s)
        both_sides = (front_only and both_sides_parent) or state_bool(state, 'fixBound')
        primary_both_sides = both_sides
        fallback_point = None
        depth = 1 if front_only else state['depth']
        if front_only and len(curve) > 2:
            center_point = [0,0,0]
            for point in curve:
                center_point = np.add(center_point, point)
            center_point /= len(curve)
            block = self.find_block(center_point)
        else:
            mid_front = np.add(curve[0], curve[-1]) * 0.5
            mid_front_2, min_i = self.closest_point_to_curve(mid_front, curve)
            if min_i >= 0:
                mid_front = mid_front_2
            mid_dir = np.add(curve_n[0], curve_n[-1])
            mid_dir /= np.linalg.norm(mid_dir)
            center_point = mid_front + 0.5 * depth * mid_dir
            block = self.find_block(center_point)
            # for the converters: where the block is looked for first, and from where the front one (see below)
            fallback_point = mid_front - mid_dir
            if block < 0: # try front instead of back (e.g. on road without terrain behind)
                both_sides = False
                center_point = mid_front - mid_dir
                block = self.find_block(center_point)
        if block < 0 and self.ignore_blocks:
            block = 0
        primary_point = center_point if fallback_point is None else mid_front + 0.5 * depth * mid_dir
        if block >= 0:
            block += 1
            n_res = len(res)
            for side in ['front', 'left', 'right', 'back']:
                if building[side] is not None:
                    self.get_building_side(res, block, both_sides, building[side], obj_name)
            if building['roof'] is not None:
                self.get_roof(res, building['roof'], block, state['topTexture'], obj_name)
            # where the block of the building is found (for the converters, as without the fallback, which depends on
            # the blocks around it)
            for part in res[n_res:]:
                part.properties['locate'] = ','.join(str(float(c)) for c in primary_point)
                if fallback_point is not None:
                    part.properties['locate_front'] = ','.join(str(float(c)) for c in fallback_point)
                if primary_both_sides and part.part_type() == 'FACB':
                    part.properties['both_sides'] = '1'


    def get_block_from_line_points(self, line):
        if len(line['linePoints']) == 0 and not self.ignore_blocks:
            return -1
        point_sum = (0.0, 0.0, 0.0)
        for point in line['linePoints']:
            point_sum = np.add(point_sum, point)
        point_sum = np.divide(point_sum, len(line['linePoints']))
        return self.find_block(point_sum)

    def get_building_line(self, res, line):
        state = line['data']['fields']['state']
        instance_state = line['data']['fields']['instanceState']
        to_pkg = state_bool(instance_state, "exportToPKG")
        if state['type'] != 'psdl' or to_pkg:
            if line['data']['mesh'] is None or line['data']['collider'] is None:
                # no geometry generated (e.g. a line without points), so no collider either
                report.warning('building line ' + line['data']['name'] + ' has no mesh, skipped', element=line['data']['name'], kind='buildingLine')
                return
            block = self.get_block_from_line_points(line) + 1
            if block <= 0 and self.ignore_blocks:
                block = 1
            if block <= 0:
                report.warning('building line ' + line['data']['name'] + ' is outside of every block, skipped', element=line['data']['name'], kind='buildingLine')
                return
            elem = self.get_mesh(line['data']['mesh'], block, 'VL', line['data']['name'])
            bnd = self.get_mesh(line['data']['collider'], block, 'BND', line['data']['name'], self.cur_mesh_idx - 1)
            res.append(elem)
            res.append(bnd)
        else:
            if line['roof'] is not None:
                block = self.get_block_from_line_points(line)
                if block < 0 and self.ignore_blocks:
                    block = 0
                if block >= 0 and 'roof' in line:
                    roof_tex = state_val(state, 'roofTex', '')
                    n_res = len(res)
                    self.get_roof(res, line['roof'], block + 1, roof_tex, line['data']['name'])
                    if len(line['linePoints']) > 0:
                        center = np.mean(np.array(line['linePoints'], dtype=float), axis=0)
                        for part in res[n_res:]:
                            part.properties['locate'] = ','.join(str(float(c)) for c in center)
            for building in line['buildings']:
                self.get_building(res, building, line['data']['name'], state_bool(state, 'frontOnly'), state_bool(state, 'fixBound'))

    def does_ray_intersect_segment(self, point, direction, p1, p2):
        v1 = np.subtract(point, p1)
        v2 = np.subtract(p2, p1)
        v3 = (-direction[1], direction[0])
        dot = np.dot(v2, v3)
        if abs(dot) < 0.0001:
            return False
        t1 = (v2[0] * v1[1] - v2[1] * v1[0]) / np.dot(v2, v3) # 2D cross product (np.cross only takes 3D vectors)
        t2 = np.dot(v1, v3) / np.dot(v2, v3)
        return t1 >= 0 and t2 >= 0 and t2 < 1 # exclude ==1 because we are testing consecutive segments

    def is_point_inside_polygon(self, point, polygon):
        count = 0
        pointb = (point[0], point[2])
        for i in range(len(polygon)):
            p1 = polygon[i]
            p2 = polygon[(i + 1) if (i < len(polygon) - 1) else 0]
            p1b = (p1[0], p1[2])
            p2b = (p2[0], p2[2])
            count += 1 if self.does_ray_intersect_segment(pointb, (1.0, 0.0), p1b, p2b) else 0
        return count % 2 != 0

    def is_point_in_bounds(self, point, bounds):
        return point[0] >= bounds[0][0] and \
               point[0] <= bounds[1][0] and \
               point[2] >= bounds[0][1] and \
               point[2] <= bounds[1][1]

    def is_point_in_block(self, block, point, bounds):
        if not self.is_point_in_bounds(point, bounds):
            return False
        for polygon in block:
            if self.is_point_inside_polygon(point, polygon):
                return True
        return False

    def get_block_height(self, block):
        h = 0.0
        for polygon in block:
            h_b = 0.0
            for point in polygon:
                h_b += point[1]
            h_b /= len(polygon)
            h += h_b
        h /= len(block)
        return h

    def find_block(self, pos):
        block_perimeters = self.block_perimeters
        block = -1
        blocks = []
        heights = []
        for i in range(len(block_perimeters)):
            if self.is_point_in_block(block_perimeters[i][0], pos, self.block_perimeters_bounds[i]):
                blocks.append(i)
                heights.append(self.get_block_height(block_perimeters[i][0]))
        if len(blocks) > 0:
            block = blocks[0]
            dist = abs(pos[1] - heights[0])
            for i in range(1, len(blocks)):
                dist2 = abs(pos[1] - heights[i])
                if dist2 < dist:
                    dist = dist2
                    block = blocks[i]
        return block

    def get_cube(self, scale):
        def get_face(a, b, c, d):
            return [a, b, c, a, c, d]
        pivot = np.multiply((0.0, 0.5, 0.0), scale)
        vertices = []
        vertices.append(np.add(pivot, np.multiply((0.5, 0.5, 0.5), scale)))
        vertices.append(np.add(pivot, np.multiply((0.5, 0.5, -0.5), scale)))
        vertices.append(np.add(pivot, np.multiply((-0.5, 0.5, -0.5), scale)))
        vertices.append(np.add(pivot, np.multiply((-0.5, 0.5, 0.5), scale)))
        vertices.append(np.add(pivot, np.multiply((0.5, -0.5, 0.5), scale)))
        vertices.append(np.add(pivot, np.multiply((0.5, -0.5, -0.5), scale)))
        vertices.append(np.add(pivot, np.multiply((-0.5, -0.5, -0.5), scale)))
        vertices.append(np.add(pivot, np.multiply((-0.5, -0.5, 0.5), scale)))
        indices = []
        indices.extend(get_face(0, 1, 2, 3))
        indices.extend(get_face(7, 6, 5, 4))
        indices.extend(get_face(4, 5, 1, 0))
        indices.extend(get_face(6, 7, 3, 2))
        indices.extend(get_face(5, 6, 2, 1))
        indices.extend(get_face(7, 4, 0, 3))
        return {'vertices': vertices, 'indices': indices}

    def get_mesh_instance(self, res, mesh, index):
        def get_instance_mesh_name(dict):
            mesh_name_parts = dict['name'].replace('\\', '/').split('/')
            mesh_name = mesh_name_parts[-1].split('.')[0]
            return mesh_name
        mref = mesh['reference']
        dict_mesh = self.data['meshDict'][mref['meshId']]
        state = mesh['settings']
        parameter_name = state_val(state, '_parameterName')
        if parameter_name in ("startTrafficLight", "endTrafficLight"):
            # a traffic light of a road end: in the BAI, not an object of its own
            road_id = state_val(state, '_parentObjectId', -1)
            self.traffic.attach_traffic_light(road_id, parameter_name == "startTrafficLight", mref['position'], mref['rotation'])
        else:
            block = 0
            is_prop = mesh.get('type') == 'individualProp' # the other mesh instances (and the parametric objects) are INST meshes
            if not is_prop:
                block = self.find_block(np.add(mref['position'], (0.0, dict_mesh['boundsMin'][1], 0.0)))
            if block >= 0 or is_prop:
                cur_block = block + 1
                elem = ExportedCityElement()
                cube = self.get_cube(1 if is_prop else 10)
                elem.vertices = cube['vertices']
                elem.indices = cube['indices']
                if is_prop:
                    no_transf = mref['rotation'] == (0, 0, 0, 1) and mref['scale'] == (1, 1, 1)
                    flags = '0' if no_transf else '1'
                    elem.name = str(index) + ',' + '0_PTH'
                else:
                    elem.name = str(index) + ',' + str(cur_block) + '_INST'
                    flags = str(get_inst_modifiers(mesh, state))
                    # the box of the mesh (local, in the space of the program), for the CPVS
                    if dict_mesh.get('boundsMin') is not None and dict_mesh.get('boundsMax') is not None:
                        elem.properties['bounds'] = ','.join(str(float(c)) for c in list(dict_mesh['boundsMin']) + list(dict_mesh['boundsMax']))
                elem.properties['original_name'] = mesh['name']
                elem.properties['object'] = get_instance_mesh_name(dict_mesh)
                elem.properties['flags'] = flags
                owner = state_val(state, '_propertyContainerId', '')
                if is_prop and owner:
                    elem.properties['race'] = owner
                elem.translation = mref['position']
                elem.rotation = mref['rotation']
                elem.scale = mref['scale']
                elem.mat = 'NONE'
                res.append(elem)

    # exports an element (function adds its parts to res); with the errors collected (see report.collecting), a failure is
    # reported and what the element added is removed, so that the other elements are still exported
    def guarded_element(self, res, name, kind, function, element_id=None):
        n_res = len(res)
        roads = set(self.exported_roads)
        n_traffic = len(self.traffic_intersections)
        try:
            function()
            for part in res[n_res:]:
                part.source = (kind, element_id)
        except Exception:
            if not report.collecting():
                raise
            del res[n_res:]
            for road_id in set(self.exported_roads) - roads:
                del self.exported_roads[road_id]
            del self.traffic_intersections[n_traffic:]
            report.exception(name + " not exported", element=name, kind=kind)

    def reset(self):
        # the state before processing the elements (the blocks given by the user come first), returns the manual blocks
        manual_blocks = self.get_manual_blocks()
        self.block_perimeters = []
        self.block_perimeters_bounds = []
        for num in manual_blocks:
            self.block_perimeters.append([[], 0])
            self.block_perimeters_bounds.append([[float('-inf'), float('-inf')], [float('inf'), float('inf')]])

        self.cur_road_key = 0
        # the roads and intersections exported, for the BAI: {road id: {'elem': ExportedCityElement, 'road': road,
        # 'block': int, 'bai_sections': the sections of its mesh used by the BAI}}, [(ExportedCityElement surface,
        # intersection, int block)]
        self.exported_roads = {}
        self.traffic_intersections = []
        self.pkg_blocks = set()  # the rooms of the terrain patches exported to PKG
        self.element_blocks = {}  # {(kind, id): room} of the roads, intersections and terrain patches (the rooms of the rails)
        self.element_rooms = {}  # {(kind, id): [rooms]} of the roads exported as several rooms (split_long_road)
        self.traffic = BaiNetworkBuilder(self.data, self.exported_roads, self.traffic_intersections, self.road_has_sidewalks, self.road_has_divider)
        return manual_blocks

    def get_element_parts(self, kind, element, manual_blocks):
        # the parts of a single element (without the traffic), used by the converters
        res = []
        if kind == 'road':
            self.get_road(res, element, element['data']['fields']['instanceState'], element['startIntersectionId'] != -1,
                          element['endIntersectionId'] != -1, None, -1, manual_blocks)
        elif kind == 'intersection':
            self.get_intersection(res, element, manual_blocks)
        elif kind == 'terrainPatch':
            self.get_patch(res, element, manual_blocks)
        elif kind == 'buildingLine':
            self.get_building_line(res, element)
        for part in res:
            part.source = (kind, element['id'])
        return res

    def get_objects(self, traffic_only=False):
        # traffic_only: stops after the traffic (the parts of the roads, intersections, terrain patches, building lines
        # and rails, and the network), for the checks that need only those (not kept as the result)
        if self.out_res is not None:
            return self.out_res

        res = []
        data = self.data
        manual_blocks = self.reset()

        # process the elements (with the errors collected, an element failing is left out, see guarded_element)
        print("processing roads...")
        for road in data['roads']:
            if self.verbose: print("exporting " + road['data']['name'])
            instance_state = road['data']['fields']['instanceState']
            has_start_int = road['startIntersectionId'] != -1
            has_end_int = road['endIntersectionId'] != -1
            self.guarded_element(res, road['data']['name'], 'road',
                                 lambda: self.get_road(res, road, instance_state, has_start_int, has_end_int, None, -1, manual_blocks), road['id'])

        print("processing intersections...")
        for intersection in data['intersections']:
            if self.verbose: print("exporting " + intersection['data']['name'])
            self.guarded_element(res, intersection['data']['name'], 'intersection',
                                 lambda: self.get_intersection(res, intersection, manual_blocks), intersection['id'])

        print("processing terrain patches...")
        for patch in data['terrainPatches']:
            if self.verbose: print("exporting " + patch['data']['name'])
            self.guarded_element(res, patch['data']['name'], 'terrainPatch', lambda: self.get_patch(res, patch, manual_blocks), patch['id'])

        print("processing building lines...")
        for line in data['buildingLines']:
            if self.verbose: print("exporting " + line['data']['name'])
            self.guarded_element(res, line['data']['name'], 'buildingLine', lambda: self.get_building_line(res, line), line['id'])

        print("processing rails...")
        for element in data.get('customElements') or []:
            if element.get('type') == 'rail':
                self.guarded_element(res, (element.get('data') or {}).get('name', 'rail'), 'customElement',
                                     lambda e=element: self.get_rail(res, e), element['id'])

        print("processing traffic...")
        with report.guarded("the traffic was not exported"):
            self.resolve_traffic_rooms()
            self.network = self.traffic.build()
        if traffic_only:
            return res

        print("processing decals...")
        with report.guarded("the decals were not exported"):
            export_decals(self, res)

        # Sort order of INST meshes can matter for rendering when transparent objects are involved, here the current order gets preserved
        sorted_meshes = sorted(data['meshInstances'], key=lambda mesh: mesh['name'])
        print("processing meshes...") #done at the end to access traffic info (for traffic lights)
        for i in range(len(sorted_meshes)):
            if self.verbose: print("exporting " + sorted_meshes[i]['name'])
            self.guarded_element(res, sorted_meshes[i]['name'], 'meshInstance', lambda: self.get_mesh_instance(res, sorted_meshes[i], i), sorted_meshes[i]['id'])

        from prop_placers import export_prop_placer
        for element in data.get('customElements') or []:
            if element.get('type') in ('propLine', 'propPolygon'):
                self.guarded_element(res, element['data']['name'], 'customElement',
                                     lambda e=element: export_prop_placer(self, e, res), element['id'])

        self.out_res = res

        return self.out_res
