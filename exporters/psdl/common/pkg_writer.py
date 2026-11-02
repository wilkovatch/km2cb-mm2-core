import math
import os
import struct

from .scene_input import SceneInput
from .file_io import BinaryFileHelper
from .utils import Utils
from . import report

# Writer for the objects exported to PKG (formats described at
# https://github.com/Dummiesman/angel-file-formats/tree/master/Midtown%20Madness%202):
# each group of PKG objects (same pkg_name) becomes <city>_geometry/<city>_<pkg_name>.pkg (VL only)
# and <city>_bound/<city>_<pkg_name>_BOUND.bnd/.bbnd/.ter, placed in the city by the INST writer.
# Coordinates are the ones of the scene input (index 2 is the height), relative to the group pivot.

MAX_U16 = 65535
TER_SECTION_SIZE = 10.0
TER_SECTION_MARGIN = 0.1
BOUND_WELD_EPSILON = 0.0001


def get_city_basename(filepath):
    return filepath.replace('\\', '/').split('/')[-1].replace('.psdl', '')


def get_texture_name(texture):
    if texture is None or texture == "NONE":
        return ""
    return texture.split(".")[0].lower()


def to_game_space(v):
    # same mapping as BinaryFileHelper.write_vec3
    return (-v[0], v[2], v[1])


class PKGGroup:
    def __init__(self, pkg_name, stem):
        self.pkg_name = pkg_name
        self.stem = stem
        self.lods = {}
        self.block = 0
        self.pivot = (0.0, 0.0, 0.0)
        self.mesh = None
        self.bound_mesh = None


class PKGGroups:
    # Groups the PKG objects by pkg_name (each object is one LOD or the collider of the group)
    def __init__(self, scene_input: SceneInput, filepath):
        self.scene_input = scene_input
        self.utils = Utils(scene_input)
        self.basename = get_city_basename(filepath)
        self.groups = []
        self.read()

    def read(self):
        groups = {}
        for obj in self.scene_input.get_object_list():
            if self.utils.get_object_type(obj) != "PKG":
                continue
            pr = self.scene_input.get_property_container(obj)
            name = pr.get("original_name", self.scene_input.get_object_name(obj))
            pkg_name = pr.get("pkg_name", None)
            part = pr.get("lod_name", None)
            if pkg_name is None:
                report.warning("object " + name + " has no pkg name, skipped", element=report.element_name(name))
                continue
            if part not in ["H", "M", "L", "VL", "BND"]:
                report.warning("object " + name + " has an invalid LOD: " + str(part), element=report.element_name(name))
                continue
            if pkg_name not in groups:
                groups[pkg_name] = PKGGroup(pkg_name, self.basename + "_" + pkg_name)
                self.groups.append(groups[pkg_name])
            group = groups[pkg_name]
            group.lods[part] = obj
            if part != "BND":
                group.block = self.utils.get_block_number(obj)
        valid_groups = []
        for group in self.groups:
            visible = [group.lods[k] for k in ["VL", "L", "M", "H"] if k in group.lods]
            if len(visible) == 0 or group.block <= 0:
                report.warning("pkg " + group.stem + " has no visible mesh or no block, skipped")
                continue
            group.mesh = self.scene_input.get_mesh_data(visible[0])
            if sum(len(s[0]) for s in group.mesh["submeshes"]) == 0:
                report.warning("pkg " + group.stem + " has no polygons, skipped")
                continue
            if "BND" in group.lods:
                group.bound_mesh = self.scene_input.get_mesh_data(group.lods["BND"])
            else:
                group.bound_mesh = group.mesh
            group.pivot = self.get_pivot(group.mesh)
            valid_groups.append(group)
        self.groups = valid_groups

    def get_pivot(self, mesh):
        # center of the bounding box, at the lowest point
        verts = mesh["vertices"]
        min_v = [min(v[i] for v in verts) for i in range(3)]
        max_v = [max(v[i] for v in verts) for i in range(3)]
        return ((min_v[0] + max_v[0]) * 0.5, (min_v[1] + max_v[1]) * 0.5, min_v[2])


class PKGWriter:
    def __init__(self, scene_input: SceneInput, filepath, physics_map=None, geometry_path=None, bound_path=None):
        # geometry_path and bound_path: the folders of the PKG and bound files,
        # <city>_geometry and <city>_bound next to the PSDL file if not given
        self.scene_input = scene_input
        self.filepath = filepath
        self.physics_map = physics_map if physics_map is not None else {}
        out_dir = os.path.dirname(filepath)
        basename = get_city_basename(filepath)
        self.geometry_path = geometry_path or os.path.join(out_dir, basename + "_geometry")
        self.bound_path = bound_path or os.path.join(out_dir, basename + "_bound")

    # PKG

    def get_sections(self, group):
        # one section per texture, split if over the u16 index limit
        mesh = group.mesh
        pivot = group.pivot
        shaders = []
        sections = []
        for indices, texture in mesh["submeshes"]:
            if len(indices) < 3:
                continue
            tex = get_texture_name(texture)
            if tex not in shaders:
                shaders.append(tex)
            section = None
            for t in range(0, len(indices) - 2, 3):
                tri = indices[t:t + 3]
                if section is None or len(section["vertices"]) + 3 > MAX_U16:
                    section = {"shader": shaders.index(tex), "vertices": [], "normals": [], "uvs": [], "indices": [], "map": {}}
                    sections.append(section)
                for i in tri:
                    if i not in section["map"]:
                        v = mesh["vertices"][i]
                        section["map"][i] = len(section["vertices"])
                        section["vertices"].append((v[0] - pivot[0], v[1] - pivot[1], v[2] - pivot[2]))
                        section["normals"].append(mesh["normals"][i])
                        section["uvs"].append(mesh["uvs"][i])
                    section["indices"].append(section["map"][i])
        return shaders, sections

    def begin_chunk(self, file, name):
        file.write_raw_string("FILE")
        file.write_string(name)
        length_pos = file.tell()
        file.write_uint32(0)
        return length_pos

    def end_chunk(self, file, length_pos):
        end = file.tell()
        file.seek(length_pos)
        file.write_uint32(end - length_pos - 4)
        file.seek(end)

    def write_pkg(self, group):
        shaders, sections = self.get_sections(group)
        file = BinaryFileHelper(os.path.join(self.geometry_path, group.stem + ".pkg"), 'wb')
        file.write_raw_string("PKG3")

        # geometry (VL only, the game uses it for every distance)
        chunk = self.begin_chunk(file, "VL")
        file.write_uint32(len(sections))
        file.write_uint32(sum(len(s["vertices"]) for s in sections))
        file.write_uint32(sum(len(s["indices"]) for s in sections))
        file.write_uint32(len(sections))
        file.write_uint32(0x112)  # FVF: position, normal, uv
        for s in sections:
            file.write_uint16(1)  # strips
            file.write_uint16(0)  # flags
            file.write_uint32(s["shader"])
            file.write_uint32(3)  # primitive type: triangles
            file.write_uint32(len(s["vertices"]))
            for i in range(len(s["vertices"])):
                file.write_vec3(s["vertices"][i])
                file.write_vec3(s["normals"][i])
                uv = s["uvs"][i]
                file.write_float(uv[0])
                file.write_float(1.0 - uv[1])
            file.write_uint32(len(s["indices"]))
            for i in s["indices"]:
                file.write_uint16(i)
        self.end_chunk(file, chunk)

        # shaders (one paintjob of byte shaders, values of the stock city objects)
        chunk = self.begin_chunk(file, "shaders")
        file.write_uint32(0x80 | 1)
        file.write_uint32(len(shaders))
        for tex in shaders:
            file.write_string(tex)
            for color in [(229, 229, 229, 255), (229, 229, 229, 255), (0, 0, 0, 255)]:
                for c in color:
                    file.write_byte(c)
            file.write_float(0.25)
        self.end_chunk(file, chunk)

        chunk = self.begin_chunk(file, "offset")
        file.write_float(0.0)
        file.write_float(0.0)
        file.write_float(0.0)
        self.end_chunk(file, chunk)
        file.close()

    # Bound

    def get_bound(self, group):
        # welded vertices (game space, relative to the pivot), triangles with material index, material names
        mesh = group.bound_mesh
        pivot = group.pivot
        verts = []
        vert_map = {}
        tris = []
        materials = ["default"]
        for indices, texture in mesh["submeshes"]:
            physics = self.physics_map.get(get_texture_name(texture), "none")
            mtl = "default" if physics in ["", "none"] else physics
            if mtl not in materials:
                materials.append(mtl)
            mtl_index = materials.index(mtl)
            for t in range(0, len(indices) - 2, 3):
                tri = []
                for i in indices[t:t + 3]:
                    v = mesh["vertices"][i]
                    gv = to_game_space((v[0] - pivot[0], v[1] - pivot[1], v[2] - pivot[2]))
                    key = tuple(round(c / BOUND_WELD_EPSILON) for c in gv)
                    if key not in vert_map:
                        vert_map[key] = len(verts)
                        verts.append(gv)
                    tri.append(vert_map[key])
                if tri[0] != tri[1] and tri[1] != tri[2] and tri[2] != tri[0]:
                    tris.append((tri[0], tri[1], tri[2], mtl_index))
        # drop the materials not used by any polygon (except default)
        used = sorted(set([0] + [t[3] for t in tris]))
        remap = {old: new for new, old in enumerate(used)}
        materials = [materials[i] for i in used]
        tris = [(t[0], t[1], t[2], remap[t[3]]) for t in tris]
        return verts, tris, materials

    def write_bnd(self, path, verts, tris, materials):
        with open(path, 'w', newline='\r\n') as f:
            f.write("version: 1.01\n")
            f.write("verts: " + str(len(verts)) + "\n")
            f.write("materials: " + str(len(materials)) + "\n")
            f.write("edges: 0\n")
            f.write("polys: " + str(len(tris)) + "\n\n")
            for v in verts:
                f.write("v\t%f\t%f\t%f\n" % v)
            f.write("\n")
            for m in materials:
                f.write("mtl " + m + " {\n")
                f.write("\telasticity: 0.100000\n")
                f.write("\tfriction: 0.500000\n")
                f.write("\teffect: none\n")
                f.write("\tsound: none\n")
                f.write("}\n")
            f.write("\n")
            for t in tris:
                f.write("tri %d %d %d %d\n" % t)

    def write_char32(self, f, string):
        data = string.encode('ascii')[:31]
        f.write(data + bytes(32 - len(data)))

    def write_bbnd(self, path, verts, tris, materials):
        with open(path, 'wb') as f:
            f.write(struct.pack('<BIII', 1, len(verts), len(materials), len(tris)))
            for v in verts:
                f.write(struct.pack('<3f', *v))
            for m in materials:
                self.write_char32(f, m)
                f.write(struct.pack('<2f', 0.1, 0.5))
                self.write_char32(f, "none")
                self.write_char32(f, "none")
            for t in tris:
                f.write(struct.pack('<5H', t[0], t[1], t[2], 0, t[3]))

    def triangle_overlaps_box(self, tri, box_min, box_max):
        # 2D separating axis test on the x/z plane (game space), works for vertical (degenerate) polygons too
        pts = [(p[0], p[2]) for p in tri]
        if max(p[0] for p in pts) < box_min[0] or min(p[0] for p in pts) > box_max[0]:
            return False
        if max(p[1] for p in pts) < box_min[1] or min(p[1] for p in pts) > box_max[1]:
            return False
        corners = [(box_min[0], box_min[1]), (box_max[0], box_min[1]), (box_max[0], box_max[1]), (box_min[0], box_max[1])]
        for i in range(3):
            a = pts[i]
            b = pts[(i + 1) % 3]
            axis = (b[1] - a[1], a[0] - b[0])
            if abs(axis[0]) < 1e-9 and abs(axis[1]) < 1e-9:
                continue
            tri_proj = [axis[0] * p[0] + axis[1] * p[1] for p in pts]
            box_proj = [axis[0] * c[0] + axis[1] * c[1] for c in corners]
            if max(tri_proj) < min(box_proj) or min(tri_proj) > max(box_proj):
                return False
        return True

    def write_ter(self, path, verts, tris):
        min_v = [min(v[i] for v in verts) for i in range(3)]
        max_v = [max(v[i] for v in verts) for i in range(3)]
        size = [max_v[i] - min_v[i] for i in range(3)]
        width_sections = max(1, math.ceil(size[0] / TER_SECTION_SIZE))
        depth_sections = max(1, math.ceil(size[2] / TER_SECTION_SIZE))
        cell_w = size[0] / width_sections
        cell_d = size[2] / depth_sections

        # sections: depth (z) outer, width (x) inner, as in the stock files
        groups = [[] for i in range(width_sections * depth_sections)]
        def cell_range(lo, hi, origin, cell, count):
            if cell <= 0:
                return range(count)
            first = int(math.floor((lo - origin - TER_SECTION_MARGIN) / cell))
            last = int(math.floor((hi - origin + TER_SECTION_MARGIN) / cell))
            return range(max(0, first), min(count - 1, last) + 1)
        for ti in range(len(tris)):
            t = tris[ti]
            tri = [verts[t[0]], verts[t[1]], verts[t[2]]]
            w_range = cell_range(min(p[0] for p in tri), max(p[0] for p in tri), min_v[0], cell_w, width_sections)
            d_range = cell_range(min(p[2] for p in tri), max(p[2] for p in tri), min_v[2], cell_d, depth_sections)
            for d in d_range:
                for w in w_range:
                    box_min = (min_v[0] + w * cell_w - TER_SECTION_MARGIN, min_v[2] + d * cell_d - TER_SECTION_MARGIN)
                    box_max = (min_v[0] + (w + 1) * cell_w + TER_SECTION_MARGIN, min_v[2] + (d + 1) * cell_d + TER_SECTION_MARGIN)
                    if self.triangle_overlaps_box(tri, box_min, box_max):
                        groups[d * width_sections + w].append(ti)
        poly_indices = sum(len(g) for g in groups)
        if poly_indices > MAX_U16:
            report.warning("too many polygon references in " + path + ", terrain bound skipped")
            return

        with open(path, 'wb') as f:
            f.write(struct.pack('<f', 1.1))
            f.write(struct.pack('<IIB', len(tris), 0, 0))
            f.write(struct.pack('<3f', *size))
            f.write(struct.pack('<4I', width_sections, 1, depth_sections, len(groups)))
            f.write(struct.pack('<I', poly_indices))
            f.write(struct.pack('<f', width_sections / size[0] if size[0] > 0 else float('inf')))
            f.write(struct.pack('<f', 1.0))
            f.write(struct.pack('<f', depth_sections / size[2] if size[2] > 0 else float('inf')))
            f.write(struct.pack('<6f', *min_v, *max_v))
            start = 0
            for g in groups:
                f.write(struct.pack('<H', start))
                start += len(g)
            for g in groups:
                f.write(struct.pack('<H', len(g)))
            for g in groups:
                for ti in g:
                    f.write(struct.pack('<H', ti))

    def write_bound(self, group):
        verts, tris, materials = self.get_bound(group)
        if len(tris) == 0:
            report.warning("pkg " + group.stem + " has an empty bound, skipped")
            return
        if len(verts) > MAX_U16 or len(tris) > MAX_U16:
            report.warning("bound of pkg " + group.stem + " is too big (" + str(len(verts)) + " vertices, " + str(len(tris)) + " polygons, max " + str(MAX_U16) + "), skipped")
            return
        path = os.path.join(self.bound_path, group.stem + "_BOUND")
        self.write_bnd(path + ".bnd", verts, tris, materials)
        self.write_bbnd(path + ".bbnd", verts, tris, materials)
        self.write_ter(path + ".ter", verts, tris)

    def write(self):
        groups = PKGGroups(self.scene_input, self.filepath).groups
        if len(groups) == 0:
            return
        for path in [self.geometry_path, self.bound_path]:
            if not os.path.exists(path):
                os.makedirs(path)
        for group in groups:
            self.write_pkg(group)
            self.write_bound(group)
        print("PKGs exported! (" + str(len(groups)) + ")")
