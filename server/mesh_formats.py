# Decoder for Angel Studios PKG format, as described here: http://mm2kiwi.apan.is-a-geek.com/index.php?title=PKG
import sys
import math
import struct
import os

from file_io import BinaryFileHelper

def read_color_4d(f):
    r = f.read_byte()
    g = f.read_byte()
    b = f.read_byte()
    a = f.read_byte()
    return [r, g, b, a]

def read_color_4f(f):
    r = f.read_float()
    g = f.read_float()
    b = f.read_float()
    a = f.read_float()
    return [int(r * 255.0), int(g * 255.0), int(b * 255.0), int(a * 255.0)]

def read_c_vec2(f):
    x = (float(f.read_byte()) - 128.0) / 128.0
    y = 1 - ((float(f.read_byte()) - 128.0) / 128.0)
    return [x, y]

def read_c_vec3(f):
    x = -(float(f.read_byte()) - 128.0) / 127.0
    y = (float(f.read_byte()) - 128.0) / 127.0
    z = (float(f.read_byte()) - 128.0) / 127.0
    return [x, y, z]

def read_vec2(f):
    vec = f.read_vec2()
    return [vec[0], 1 - vec[1]]

def read_vec3(f):
    vec = f.read_vec3()
    return [-vec[0], vec[1], vec[2]]

def read_geometry(f, objects, name, material_i0):
    n_sections = f.read_uint32()
    n_vertices_tot = f.read_uint32()
    n_indices_tot = f.read_uint32()
    n_sections_2 = f.read_uint32()
    fvf = f.read_uint32()
    has_normal = (fvf & 0x10) > 0
    has_tex = (fvf & 0x100) > 0
    has_color = (fvf & 0x40) > 0 or (fvf & 0x80) > 0
    
    vertices = []
    normals = []
    uvs = []
    indices_dict = {}
    max_shader_count = 0
    
    for i in range(n_sections):
        n_strips = f.read_uint16()
        flags = f.read_uint16()
        compact_strips = (flags & (1 << 8)) != 0
        def read_var_int():
            return f.read_uint16() if compact_strips else f.read_uint32()
        def read_var_vec2():
            return read_c_vec2(f) if compact_strips else read_vec2(f)
        def read_var_vec3():
            return read_c_vec3(f) if compact_strips else read_vec3(f)
        shader_offset = read_var_int()
        if shader_offset > max_shader_count:
            max_shader_count = shader_offset
        for j in range(n_strips):
            vert_count_0 = len(vertices)
            prim_type = read_var_int()
            n_vertices = read_var_int()
            for k in range(n_vertices):
                vertices.append(read_vec3(f))
                normals.append(read_var_vec3() if has_normal else [0, 0, 0])
                if has_color:
                    read_color_4d(f)
                uvs.append(read_var_vec2() if has_tex else [0, 0])
            n_indices = read_var_int()
            if shader_offset not in indices_dict:
                indices_dict[shader_offset] = []
            for k in range(n_indices): # TODO: primType == 4
                indices_dict[shader_offset].append(vert_count_0 + f.read_uint16())
    mesh = {'name': name}
    mesh['vertices'] = vertices
    mesh['normals'] = normals
    mesh['uvs'] = uvs
    mesh['indices'] = indices_dict
    mesh['material0'] = material_i0
    true_name = name.replace('BODY_', '')
    if true_name in ['H', 'M', 'L', 'VL']:
        objects.append(mesh)

def read_xref(f):
    x_axis = read_vec3(f)
    y_axis = read_vec3(f)
    z_axis = read_vec3(f)
    origin = read_vec3(f)
    name = f.read_bytes(32).decode('ascii') 
    #TODO

def read_material(f, full):
    # read properties
    texture_name = f.read_string()[:-1]
    if full:
        diffuse = read_color_4f(f)
        ambient = read_color_4f(f)
        specular = read_color_4f(f)
        emissive = read_color_4f(f)
    else:
        diffuse = read_color_4d(f)
        ambient = read_color_4d(f)
        specular = [0, 0, 0, 255]
        emissive = read_color_4d(f)
    shininess = f.read_float()
    
    # create material
    mat = {'applyBlendModeOnlyIfTexIsTransparent': True, 'colors': [], 'floats': [], 'textures': []}
    mat['shader'] = 'Standard (Specular setup)' if full else 'Standard'
    mat['colors'].append({'key': '_Color', 'color': diffuse})
    if emissive[0] > 0 or emissive[1] > 0 or emissive[2] > 0:
        mat['colors'].append({'keyword': '_EMISSION', 'key': '_EmissionColor', 'color': emissive})
    else:
        # bug: if not specified emission is de facto
        # enabled with gray color until selected in inspector,
        # this is a quick and dirty fix
        mat['colors'].append({'keyword': '_EMISSION', 'key': '_EmissionColor', 'color': [0, 0, 0, 1]})
    if full:
        mat['colors'].append({'key': '_SpecColor', 'color': specular})
    mat['floats'].append({'key': '_Glossiness', 'value': shininess})
    
    # set texture name
    mat['textures'].append({'key': '_MainTex', 'filename': texture_name})
    mat['name'] = texture_name
    
    return mat

def read_pkg_file(f, header, materials, objects):
    file_header = f.read_bytes(4)
    if file_header != b'FILE':
        return
    name = f.read_string()[:-1]
    material_i0 = len(materials)
    if header == b'PKG3':
        f.read_bytes(4)
    if name == 'shaders':
        shader_type_and_paintjobs = f.read_uint32()
        shader_type = shader_type_and_paintjobs & 0x80
        shader_is_full = shader_type == 0
        num_paintjobs = shader_type_and_paintjobs & 0x7F
        shaders_per_paintjob = f.read_uint32()
        for i in range(num_paintjobs):
            for j in range(shaders_per_paintjob):
                materials.append(read_material(f, shader_is_full))
    elif name == 'offset':
        read_vec3(f)
    elif name == 'xref' or name == 'xrefs':
        num_refs = f.read_uint32()
        for i in range(num_refs):
            read_xref(f)
    else:
        read_geometry(f, objects, name, material_i0)

def add_uint8(res, num):
    res += num.to_bytes(1, 'little')

def add_uint16(res, num):
    res += num.to_bytes(2, 'little')

def add_uint32(res, num):
    res += num.to_bytes(4, 'little')

def add_float(res, num):
    float_value = float(num)
    res += struct.pack('<f', float_value)

def add_string(res, string):
    res += len(string).to_bytes(2, 'little')
    res += string.encode('ascii')

def add_vec2(res, vec):
    add_float(res, vec[0])
    add_float(res, vec[1])

def add_vec3(res, vec):
    add_float(res, vec[0])
    add_float(res, vec[1])
    add_float(res, vec[2])

def add_mat_col(res, col):
    add_string(res, col['key'])
    add_string(res, col['keyword'] if 'keyword' in col else '')
    for i in range(4):
        add_uint8(res, col['color'][i])

def add_mat_float(res, num):
    add_string(res, num['key'])
    add_string(res, num['keyword'] if 'keyword' in num else '')
    add_float(res, num['value'])

def add_mat_texture(res, tex, directory):
    add_string(res, tex['key'])
    add_string(res, tex['keyword'] if 'keyword' in tex else '')
    add_string(res, directory + '/../texture/')
    add_string(res, tex['filename'])

def add_material(res, material, directory):
    add_string(res, material['name'])
    add_uint32(res, 1)
    add_uint8(res, 1)
    add_string(res, material['shader'])
    add_uint32(res, len(material['colors']))
    for i in range(len(material['colors'])):
        add_mat_col(res, material['colors'][i])
    add_uint32(res, len(material['floats']))
    for i in range(len(material['floats'])):
        add_mat_float(res, material['floats'][i])
    add_uint32(res, len(material['textures']))
    for i in range(len(material['textures'])):
        add_mat_texture(res, material['textures'][i], directory)

def add_mesh(res, mesh):
    add_string(res, mesh['name'])
    add_uint32(res, len(mesh['lods']))
    for lod in mesh['lods']:
        add_string(res, lod)
    add_uint32(res, len(mesh['vertices']))
    add_uint8(res, 0)
    for v in mesh['vertices']:
        add_vec3(res, v)
    for v in mesh['normals']:
        add_vec3(res, v)
    add_uint32(res, 1)
    for v in mesh['uvs']:
        add_vec2(res, v)
    add_uint32(res, len(mesh['indices']))
    for key in mesh['indices']:
        arr = mesh['indices'][key]
        arr.reverse()
        add_uint32(res, mesh['material0'] + key)
        add_uint32(res, len(arr))
        for i in arr:
            add_uint32(res, i)

def add_object(res, obj, children):
    max_h = get_max_height(obj['lods'][0]) if len(obj['lods']) > 0 else 10
    mult = min(1.0, max_h / 10.0)
    add_string(res, obj['name'])
    add_uint32(res, 4)
    add_string(res, 'H')
    add_string(res, 'M')
    add_string(res, 'L')
    add_string(res, 'VL')
    add_float(res, 0.25 * mult)
    add_float(res, 0.05 * mult)
    add_float(res, 0.01 * mult)
    add_float(res, 0.0)
    add_uint32(res, len(obj['lods']))
    for lod in obj['lods']:
        add_mesh(res, lod)
    add_vec3(res, [0, 0, 0])
    add_vec3(res, [1, 1, 1])
    add_vec3(res, [0, 0, 0])
    add_float(res, 1)
    add_uint32(res, len(children))
    for child in children:
        add_object(res, child, [])

def get_max_height(obj):
    max_y = 0
    for v in obj['vertices']:
        if v[1] > max_y:
            max_y = v[1]
    return max_y

def reached_end(f, f_len):
    return f.tell() >= f_len

def read_file(path):
    f_len = os.path.getsize(path)
    f = BinaryFileHelper(path, 'rb')
    materials = []
    objects = []
    header = f.read_bytes(4)
    if header == b'PKG2' or header == b'PKG3':
        while not reached_end(f, f_len):
            read_pkg_file(f, header, materials, objects)
        f.close()
        res = bytearray(4)
        res += len(materials).to_bytes(4, 'little')
        directory = os.path.dirname(path)
        for material in materials:
            add_material(res, material, directory)
        
        # sort the objects as needed
        obj0 = {'name': '', 'lods': []}
        obj_dict = {}
        children_dict = {}
        for obj in objects:
            obj['lods'] = []
            name_parts = obj['name'].split('_')
            lod_name = name_parts[-1]
            obj_name = name_parts[0] if len(name_parts) > 1 else ''
            if obj_name not in obj_dict:
                obj_dict[obj_name] = []
                children_dict[obj_name] = {'name': obj_name, 'lods': []}
            obj_dict[obj_name].append(lod_name)
            children_dict[obj_name]['lods'].append(obj)
        for obj in objects:
            name_parts = obj['name'].split('_')
            lod_name = name_parts[-1]
            obj_name = name_parts[0] if len(name_parts) > 1 else ''
            d = obj_dict[obj_name]
            obj['lods'] = []
            def check_lod(lod):
                return lod not in d and ('BODY_'+lod) not in d
            if lod_name in ['H', 'BODY_H']:
                obj['lods'].append('H')
            elif lod_name in ['M', 'BODY_M']:
                if check_lod('H'):
                    obj['lods'].append('H')
                obj['lods'].append('M')
            elif lod_name in ['L', 'BODY_L']:
                if check_lod('H') and check_lod('M'):
                    obj['lods'].append('H')
                if check_lod('M'):
                    obj['lods'].append('M')
                obj['lods'].append('L')
            elif lod_name in ['VL', 'BODY_VL']:
                if check_lod('H') and check_lod('M') and check_lod('L'):
                    obj['lods'].append('H')
                if check_lod('M') and check_lod('L'):
                    obj['lods'].append('M')
                if check_lod('L'):
                    obj['lods'].append('L')
                obj['lods'].append('VL')
        children = []
        for k in children_dict:
            children.append(children_dict[k])
        add_object(res, obj0, children)
    else:
        res = bytearray(4+58) #empty mesh
    return res
