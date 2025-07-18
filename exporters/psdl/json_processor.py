import copy
import numpy as np
from utils import state_val, state_bool, state_int


class ExportedCityElement:
    def __init__(self):
        self.is_mesh = False
        self.name = ''
        self.mat = ''
        self.properties = {}
        self.vertices = []
        self.indices = []
        self.normals = []
        self.uvs = []
        self.translation = (0,0,0)
        self.rotation = (0,0,0,1)
        self.scale = (1,1,1)

class JsonProcessor:
    def __init__(self, data, verbose):
        self.data = data
        self.cur_facade_index = 0
        self.prop_rules = []
        self.verbose = verbose
        self.cur_mesh_idx = 0
        self.out_res = None

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
        if tex is None or tex == '': return 'NONE'
        parts = tex.split('/')
        return parts[-1]

    def road_has_divider(self, state):
        return state_bool(state, 'isDouble') and state_int(state, 'divider') > 0

    def road_has_sidewalks_or_shoulders(self, state, runtime_state):
        has_sidewalks_i = state_bool(state, 'hasSidewalks') and not state_bool(runtime_state, 'throughIntersection')
        return has_sidewalks_i and state_bool(state, 'isDouble')

    def road_has_sidewalks(self, state, runtime_state):
        return self.road_has_sidewalks_or_shoulders(state, runtime_state) and not state_bool(state, 'flatSidewalk')

    def road_has_shoulders(self, state, runtime_state):
        return self.road_has_sidewalks_or_shoulders(state, runtime_state) and state_bool(state, 'flatSidewalk')

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
                      res):
        section_verts = []
        shoulder_1_section_verts = []
        shoulder_2_section_verts = []
        cur_v = 0
        sw_skip = (2 if self.road_has_shoulders(state, runtime_state) else 3) if self.road_has_sidewalks(state, runtime_state) else 0
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
            elif sw_skip == 2:
                shoulder_1_section_verts.append(cur_v)
                shoulder_1_section_verts.append(cur_v + 1)
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
            elif sw_skip == 2:
                shoulder_2_section_verts.append(cur_v - 2)
                shoulder_2_section_verts.append(cur_v - 1)
        else:
            elem_name = 'ROADN'
            num_tex = 1
            section_verts.append(cur_v)
            section_verts.append(cur_v + 1)
            cur_v += 2
        section_verts.reverse() #they're reversed compared to the psdl requirements
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
        shoulder_1_vertices = []
        shoulder_2_vertices = []
        indices = []
        shoulder_1_indices = []
        shoulder_2_indices = []
        for i in range(num_segments):
            # the road mesh
            for j in section_verts:
                vertices.append(mesh['vertices'][i * vps + j])
            if i < num_segments - 1:
                for j in range(len(section_verts) - 1):
                    sec_indices = self.get_section_indices_rev(j, len(section_verts), i)
                    indices.extend(sec_indices)
            # the shoulders (if present)
            for j in shoulder_1_section_verts:
                shoulder_1_vertices.append(mesh['vertices'][i * vps + j])
            if i < num_segments - 1:
                for j in range(len(shoulder_1_section_verts) - 1):
                    sec_indices = self.get_section_indices(j, len(shoulder_1_section_verts), i)
                    shoulder_1_indices.extend(sec_indices)
            for j in shoulder_2_section_verts:
                shoulder_2_vertices.append(mesh['vertices'][i * vps + j])
            if i < num_segments - 1:
                for j in range(len(shoulder_2_section_verts) - 1):
                    sec_indices = self.get_section_indices(j, len(shoulder_2_section_verts), i)
                    shoulder_2_indices.extend(sec_indices)
        elem = ExportedCityElement()
        elem.indices = indices
        elem.vertices = vertices
        elem.name = str(cur_block) + '_' + elem_name
        elem.properties['original_name'] = og_name
        elem.properties['bai_vps'] = str(len(section_verts))

        # psdl prop rules
        if parent_intersection is None and type(prop_rule) is dict and self.road_has_sidewalks(state, runtime_state):
            left_rule = state_val(prop_rule, 'left')
            if state_val(left_rule, 'type') != 'psdl':
                left_rule = None
            right_rule = state_val(prop_rule, 'right')
            if state_val(right_rule, 'type') != 'psdl':
                right_rule = None
            if left_rule is not None or right_rule is not None:
                rule = (left_rule, right_rule)
                if rule not in self.prop_rules:
                    self.prop_rules.append(rule)
                index = self.prop_rules.index(rule)
                elem.properties['prop_rule'] = str(index + 1)

        if state['echo']: elem.properties['echo'] = '1'
        if state.get('warp', False): elem.properties['warp'] = '1'
        if div_type is not None: elem.properties['divider_type'] = str(div_type)
        if div_caps is not None: elem.properties['caps'] = str(div_caps)
        if div_param is not None: elem.properties['divider_param'] = str(div_param)
        elem.mat = textures
        res.append(elem)

        if len(shoulder_1_vertices) > 0:
            s_elem = ExportedCityElement()
            s_elem.indices = shoulder_1_indices
            s_elem.vertices = shoulder_1_vertices
            s_elem.name = str(cur_block) + '_BLOCK'
            s_elem.mat = self.get_tex(state['texture0'])
            s_elem.properties['original_name'] = og_name + ' [shoulder]'
            res.append(s_elem)

        if len(shoulder_2_vertices) > 0:
            s_elem = ExportedCityElement()
            s_elem.indices = shoulder_2_indices
            s_elem.vertices = shoulder_2_vertices
            s_elem.name = str(cur_block) + '_BLOCK'
            s_elem.mat = self.get_tex(state['texture0'])
            s_elem.properties['original_name'] = og_name + ' [shoulder]'
            res.append(s_elem)

        if self.road_has_rail(state):
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
            rl_elem.properties['cap_start_left'] = rail_bool_inv(instance_state, 'continueLeftOnStartIntersection', has_start_intersection)
            rl_elem.properties['cap_end_left'] = rail_bool_inv(instance_state, 'continueLeftOnEndIntersection', has_end_intersection)
            rl_elem.properties['cap_start_right'] = rail_bool_inv(instance_state, 'continueRightOnStartIntersection', has_start_intersection)
            rl_elem.properties['cap_end_right'] = rail_bool_inv(instance_state, 'continueRightOnEndIntersection', has_end_intersection)
            rl_elem.properties['is_curved_gallery'] = rail_equals(state, 'type', 4)
            rl_elem.properties['offset_start_left'] = rail_bool(state, 'offsetStartLeft')
            rl_elem.properties['offset_end_left'] = rail_bool(state, 'offsetEndLeft')
            rl_elem.properties['offset_start_right'] = rail_bool(state, 'offsetStartRight')
            rl_elem.properties['offset_end_right'] = rail_bool(state, 'offsetEndRight')
            rl_elem.properties['curved_sides'] = '0' #todo
            rl_elem.properties['is_rail'] = rail_equals(state, 'type', 1)
            rl_elem.properties['height'] = str(int(rail_val(state, 'height', 0.0) * 256.0))
            rl_elem.properties['original_name'] = og_name + ' [rail]'
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
        bai_vps = 0
        if vps <= 2:
            for i in range(num_segments):
                psdl_block.append(mesh['vertices'][i * vps])
                psdl_block.append(mesh['vertices'][(i + 1) * vps - 1])
                bai_vps = 2
            for i in range(num_segments - 1):
                # triangle 1
                indices.append(i)
                indices.append(i + 1)
                indices.append(i + 2)
                # triangle 2
                indices.append(i + 1)
                indices.append(i + 3)
                indices.append(i + 2)
        else:
            sw_skip = (2 if self.road_has_shoulders(state, runtime_state) else 3) if self.road_has_sidewalks(state, runtime_state) else 0
            for i in range(num_segments):
                psdl_block.append(mesh['vertices'][i * vps])
                psdl_block.append(mesh['vertices'][i * vps + sw_skip])
                psdl_block.append(mesh['vertices'][(i + 1) * vps - 1 - sw_skip])
                psdl_block.append(mesh['vertices'][(i + 1) * vps - 1])
                bai_vps = 4
            for i in range(num_segments - 1):
                for j in range(3):
                    # triangle 1
                    indices.append(i + j)
                    indices.append(i + j + 1)
                    indices.append(i + j + 4)
                    # triangle 2
                    indices.append(i + j + 1)
                    indices.append(i + j + 5)
                    indices.append(i + j + 4)
        elem_pkg = self.get_mesh(road['data']['mesh'], cur_block, 'VL', og_name)
        if (res):
            elem = ExportedCityElement()
            elem.indices = indices
            elem.vertices = psdl_block
            elem.name = str(cur_block) + '_NUL'
            elem.properties['original_name'] = og_name
            elem.properties['bai_vps'] = str(bai_vps)
            res.append(elem)
            res.append(elem_pkg)
            return elem
        else:
            return {"nul": {"indices": indices, "vertices": psdl_block}, "pkg": elem_pkg}

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
        has_no_caps = (not self.road_has_divider(state)) or state['divider'] == 1 #todo: change if non psdl roads will be introduced
        vps = road['data']['fields']['vertsPerSection']
        num_segments = (len(mesh['vertices']) - (0 if has_no_caps else 8)) // vps
        prop_rule = state_val(state, 'propRule')

        #get the block
        block = []
        for i in range(num_segments):
            # one block side (road forward, from start to end)
            block.append(mesh['vertices'][i * vps])
        for i in range(num_segments - 1, -1, -1): # the order is important to obtain a valid polygon
            # the other block side (road backward, from end to start)
            block.append(mesh['vertices'][(i + 1) * vps - 1])

        if state['type'] == 'psdl' and not state_bool(instance_state, 'exportToPKG'):
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
        prop_lines = road['data']['propLines'] if 'propLines' in road['data'] else None
        if prop_lines is not None and type(prop_rule) is dict:
            for key in prop_rule:
                value = prop_rule[key]
                if isinstance(value, dict) and value['type'] != 'psdl':
                    for value2 in prop_lines:
                        if value2['name'] == key:
                            # TODO: prop lines
                            for prop in value2['props']:
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
                                prop_elem.translation = list(np.add(prop['position'], (0, dict_mesh['boundsMin'][1], 0)))
                                prop_elem.rotation = prop['rotation']
                                prop_elem.scale = prop['scale']
                                prop_elem.mat = 'NONE'
                                res.append(prop_elem)
                            break

        if road['data']['fields']['hasStartIntersection'] and road['data']['fields']['hasEndIntersection']:
            self.traffic_roads.append([elem, road, instance_state, len(self.traffic_roads), [cur_block]])

        if in_block is None:
            if cur_block == len(block_perimeters) + 1:
                self.add_block_perimeter(block, 0)
            else:
                self.extend_block_perimeter(cur_block - 1, block)
        else:
            in_block.append(block)

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
        sortOrder = intersection['data']['fields']['sortOrder']
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
                road1I = sortOrder[cur_junction]
                road0I = sortOrder[(cur_junction + 1) if (cur_junction + 1) < len(roadsJ) else 0]
                road0 = self.data['roads'][roadsJ[road0I]]
                road1 = self.data['roads'][roadsJ[road1I]]
                rs = self.get_junction_rail_state(road0, road1, intersection)
                if rs is not None:
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
                    for i in ['1', '0', '2']:
                        comma = ',' if i != '2' else ''
                        elem.mat += self.get_tex(state_val(state, 'texture' + i)) + comma #unused actually
                res.append(elem)
                block.append(sw_vertices)
            elif typ == 'terrain' or typ == 'crosswalk':
                name = '_CW' if typ == 'crosswalk' else '_BLOCK'
                elem = ExportedCityElement()
                elem.indices = p['indices']
                elem.vertices = p['vertices']
                elem.name = str(cur_block) + name
                elem.properties['original_name'] = intersection['data']['name']
                if state_bool(state, 'echo'):
                    elem.properties['echo'] = '1'
                if state.get('warp', False): elem.properties['warp'] = '1'
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
        has_no_caps = (not self.road_has_divider(state)) or state['divider'] == 1 #todo: change if non psdl roads will be introduced
        vps = road['data']['fields']['vertsPerSection']
        num_segments = (len(mesh['vertices']) - (0 if has_no_caps else 8)) // vps
        return self.get_pkg_road(mesh,
                                 road,
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
        if state['type'] != 'psdl':
            return
        block_perimeters = self.block_perimeters
        mesh = intersection['data']['mesh']
        cur_block = len(block_perimeters) + 1
        block_number = self.get_manual_block_number(state)
        if block_number > 0 and block_number in manual_blocks:
            cur_block = manual_blocks.index(block_number) + 1
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
        if not to_pkg:
            # rails
            rails = patch['borderMeshes']
            if len(rails) > 0:
                for i in range(len(rails)):
                    r = rails[i]
                    r_vertices = []
                    r_indices = []
                    for j in range(len(r['segment'])):
                        r_vertices.append(r['segment'][j])
                        r_vertices.append(np.add(r['segment'][j], (0.0, 1.0, 0.0)))
                        if j < len(r['segment']) - 1:
                            r_indices.extend(self.get_section_indices_rev(0, 2, j))
                    self.get_junction_rail(res, r['fields']['state'], r_vertices, r_indices, cur_block, patch)

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
            print('Warning: roof on object ' + obj_name + ' has invalid geometry')

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
                                        vertices_t.append(np.dot(v, m).reshape(4,1)[:3])
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
            elem.properties['tiling'] = str(int(sliver['uvs'][0][0] * 100))
            elem.properties['original_name'] = obj_name + ' [sliver]'
            mat_id = sliver['submeshes'][0]['materialId']
            mat_tex = mat_dict[mat_id]['data']['texture']
            elem.mat = self.get_tex(mat_tex)
            res.append(elem)

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
            if block < 0: # try front instead of back (e.g. on road without terrain behind)
                both_sides = False
                center_point = mid_front - mid_dir
                block = self.find_block(center_point)
        if block >= 0:
            block += 1
            for side in ['front', 'left', 'right', 'back']:
                if building[side] is not None:
                    self.get_building_side(res, block, both_sides, building[side], obj_name)
            if building['roof'] is not None:
                self.get_roof(res, building['roof'], block, state['topTexture'], obj_name)

    def get_block_from_line_points(self, line):
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
            block = self.get_block_from_line_points(line) + 1
            elem = self.get_mesh(line['data']['mesh'], block, 'VL', line['data']['name'])
            bnd = self.get_mesh(line['data']['collider'], block, 'BND', line['data']['name'], self.cur_mesh_idx - 1)
            res.append(elem)
            res.append(bnd)
        else:
            if line['roof'] is not None:
                block = self.get_block_from_line_points(line)
                if block >= 0 and 'roof' in line:
                    roof_tex = state_val(state, 'roofTex', '')
                    self.get_roof(res, line['roof'], block + 1, roof_tex, line['data']['name'])
            for building in line['buildings']:
                self.get_building(res, building, line['data']['name'], state_bool(state, 'frontOnly'), state_bool(state, 'fixBound'))

    def does_ray_intersect_segment(self, point, direction, p1, p2):
        v1 = np.subtract(point, p1)
        v2 = np.subtract(p2, p1)
        v3 = (-direction[1], direction[0])
        dot = np.dot(v2, v3)
        if abs(dot) < 0.0001:
            return False
        t1 = np.cross(v2, v1) / np.dot(v2, v3)
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
            road_id = state_val(state, '_parentObjectId', -1)
            if road_id >= 0:
                elem = ExportedCityElement()
                cube = self.get_cube(1)
                elem.vertices = cube['vertices']
                elem.indices = cube['indices']
                elem.name = '0_TRAFL'
                elem.properties['is_start_intersection_light'] = "1" if parameter_name == "startTrafficLight" else "0"
                elem.properties['road_id'] = str(self.road_map[road_id])
                elem.properties['original_name'] = mesh['name']
                elem.properties['object'] = get_instance_mesh_name(dict_mesh)
                elem.translation = mref['position']
                elem.rotation = mref['rotation']
                elem.scale = mref['scale']
                elem.mat = 'NONE'
                res.append(elem)
        else:
            block = 0
            is_prop = state_bool(state, 'prop')
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
                    flags = '256' # 256 is for inst objects visible from every angle (0 is for front only)
                elem.properties['original_name'] = mesh['name']
                elem.properties['object'] = get_instance_mesh_name(dict_mesh)
                elem.properties['flags'] = flags
                elem.translation = mref['position']
                elem.rotation = mref['rotation']
                elem.scale = mref['scale']
                elem.mat = 'NONE'
                res.append(elem)

    def get_traffic_road(self, res, obj):
        #obj: (ExportedCityElement elem, RoadGenerator road, State instanceState, int id, int[] blocks)
        road = obj[1]
        r_state = road['data']['fields']['state']
        r_inst_state = road['data']['fields']['instanceState']
        start_int = road['startIntersectionId']
        end_int = road['endIntersectionId']
        i_state = obj[2]
        traffic_elem = ExportedCityElement()
        traffic_elem.properties['original_name'] = obj[0].properties['original_name'] + ' [BAI]'
        traffic_elem.indices = obj[0].indices
        traffic_elem.vertices = obj[0].vertices
        traffic_id = self.road_map[road['id']]
        no_left_ped_b = state_bool(r_state, 'disableLeftPedestrians')
        no_right_ped_b = state_bool(r_state, 'disableRightPedestrians')
        left_ped = '0' if no_left_ped_b else '1'
        right_ped = '0' if no_right_ped_b else '1'
        with_peds = not no_left_ped_b or not no_right_ped_b
        f_lanes = state_int(r_state, 'forwardLanes')
        b_lanes = state_int(r_state, 'backwardLanes')
        disable_traffic = state_bool(r_state, 'disableTraffic')
        if disable_traffic:
            f_lanes = 0
            b_lanes = 0
        ped_street = state_bool(r_state, 'pedestrianStreet')
        with_traffic = (b_lanes > 0 or f_lanes > 0) and not ped_street
        with_both = with_peds and with_traffic
        traffic_type = '0' if with_both else ('1' if with_peds else ('2' if with_traffic else '3'))
        name_split_comma = obj[0].name.split(',')
        vps = obj[0].properties['bai_vps']
        if vps == '0':
            raise Exception('Invalid road while exporting traffic info on road: ' + obj[0].properties['original_name'])

        start_rule = str(int(state_int(r_inst_state, 'start_rule'))) if b_lanes > 0 else "0"
        end_rule = str(int(state_int(r_inst_state, 'end_rule'))) if f_lanes > 0 else "0"

        blocks = ''
        for i in range(len(obj[4])):
            b = obj[4][i]
            blocks += str(b)
            if b < len(obj[4]) - 1:
                blocks += ';'
        traffic_elem.name = '0_BAI'
        traffic_elem.properties['is_road'] = '1'
        traffic_elem.properties['id'] = str(traffic_id)
        traffic_elem.properties['right_lanes'] = str(f_lanes)
        traffic_elem.properties['left_lanes'] = str(b_lanes)
        traffic_elem.properties['has_sidewalks'] = right_ped + ':' + left_ped
        traffic_elem.properties['traffic_type'] = traffic_type
        traffic_elem.properties['speed'] = str(int(state_int(r_state, 'speedLimit')))
        traffic_elem.properties['vertices_per_section'] = vps
        traffic_elem.properties['start_rule'] = start_rule
        traffic_elem.properties['end_rule'] = end_rule
        ti = self.traffic_intersections
        imap = self.intersection_map
        traffic_elem.properties['start_intersection'] = str(ti[imap[start_int]][2])
        traffic_elem.properties['end_intersection'] = str(ti[imap[end_int]][2])

        traffic_elem.properties['blocks'] = blocks
        traffic_elem.mat = 'NONE'
        res.append(traffic_elem)

    def get_traffic_intersection(self, res, obj):
        #obj: (ExportedCityElement elem, Intersection intersection, int block)
        traffic_elem = ExportedCityElement()
        traffic_elem.indices = obj[0].indices
        traffic_elem.vertices = obj[0].vertices
        road_numbers = ''
        for i in range(len(obj[1]['roads'])):
            order = obj[1]['data']['fields']['sortOrder']
            j = order[-1 -i] # in the generator the roads are in clockwise order, but here must be counterclockwise
            r = obj[1]['roads'][j]
            if r in self.road_map:
                road_numbers += str(self.road_map[r])
                if i < len(obj[1]['roads']) - 1:
                    road_numbers += ';'
        traffic_elem.name = '0_BAI'
        traffic_elem.properties['original_name'] = obj[0].properties['original_name'] + ' [BAI]'
        traffic_elem.properties['is_road'] = '0'
        traffic_elem.properties['block'] = str(obj[2])
        traffic_elem.properties['roads'] = road_numbers
        traffic_elem.mat = 'NONE'
        res.append(traffic_elem)

    def get_objects(self):
        if self.out_res is not None:
            return self.out_res

        res = []
        data = self.data

        manual_blocks = self.get_manual_blocks()
        self.block_perimeters = []
        self.block_perimeters_bounds = []
        for num in manual_blocks:
            self.block_perimeters.append([[], 0])
            self.block_perimeters_bounds.append([[float('-inf'), float('-inf')], [float('inf'), float('inf')]])

        self.traffic_roads = []
        # traffic_roads: (ExportedCityElement elem, RoadGenerator road, State instanceState, int id, int[] blocks)[]
        self.traffic_intersections = []
        # traffic_intersections:  (ExportedCityElement elem, Intersection intersection, int block)[]

        # process the elements
        print("processing roads...")
        for road in data['roads']:
            if self.verbose: print("exporting " + road['data']['name'])
            instance_state = road['data']['fields']['instanceState']
            has_start_int = road['startIntersectionId'] != -1
            has_end_int = road['endIntersectionId'] != -1
            self.get_road(res, road, instance_state, has_start_int, has_end_int, None, -1, manual_blocks)

        print("processing intersections...")
        for intersection in data['intersections']:
            if self.verbose: print("exporting " + intersection['data']['name'])
            self.get_intersection(res, intersection, manual_blocks)

        print("processing terrain patches...")
        for patch in data['terrainPatches']:
            if self.verbose: print("exporting " + patch['data']['name'])
            self.get_patch(res, patch, manual_blocks)

        print("processing building lines...")
        for line in data['buildingLines']:
            if self.verbose: print("exporting " + line['data']['name'])
            self.get_building_line(res, line)

        # Traffic data

        # first create lookup tables
        self.road_map = {}
        for i in range(len(self.traffic_roads)):
            self.road_map[self.traffic_roads[i][1]['id']] = i

        self.intersection_map = {}
        for i in range(len(self.traffic_intersections)):
            self.intersection_map[self.traffic_intersections[i][1]['id']] = i

        # then process the elements
        for obj in self.traffic_roads:
            self.get_traffic_road(res, obj)

        for obj in self.traffic_intersections:
            self.get_traffic_intersection(res, obj)

        # Sort order of INST meshes can matter for rendering when transparent objects are involved, here the current order gets preserved
        sorted_meshes = sorted(data['meshInstances'], key=lambda mesh: mesh['name'])
        print("processing meshes...") #done at the end to access traffic info (for traffic lights)
        for i in range(len(sorted_meshes)):
            if self.verbose: print("exporting " + sorted_meshes[i]['name'])
            self.get_mesh_instance(res, sorted_meshes[i], i)

        self.out_res = res

        return self.out_res
