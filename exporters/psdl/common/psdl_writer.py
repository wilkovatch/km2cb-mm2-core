import math
import numpy as np
import sys

from .scene_input import SceneInput
from .file_io import BinaryFileHelper
from .utils import Utils
from . import report
from collections import namedtuple, Counter


class Attribute:
    def __init__(self, geo, mat_id):
        self.geo = geo
        self.mat_id = mat_id
        self.div_mat_id = 0  # divided roads: the reference of the divider textures (stored in a byte)


class BlockFlag:
    def __init__(self):
        self.f1 = 0
        self.f2 = 0
        self.f3 = 0
        self.f4 = 0
        self.f5 = 0
        self.f6 = 0
        self.f7 = 0
        self.f8 = 0


class PerimeterVert:
    def __init__(self, ID, blocks):
        self.ID = ID
        self.blocks = blocks


PROP_BLOCK_MAX_MAT_ID = 255  # the texture references of the blocks with props need subtype 0 (see process_materials)

SectVert = namedtuple("SectVert", "pos ID")
VertWSects = namedtuple("VertWSects", "pos sects bloc")


def runs_overlap(a, b):
    # the length of the longest end of a that is also the start of b (shorter than b)
    for k in range(min(len(a), len(b) - 1), 0, -1):
        if tuple(a[len(a) - k:]) == b[:k]:
            return k
    return 0


def run_contains(a, b):
    n = len(b)
    return any(a[i:i + n] == b for i in range(len(a) - n + 1))


def merge_runs(runs):
    # greedy shortest common superstring: drops the runs contained in others, then joins the two runs with the longest
    # overlap until none overlap (the order of the runs is kept otherwise)
    res = []
    for r in sorted(runs, key=len, reverse=True):
        if not any(run_contains(m, r) for m in res):
            res.append(r)
    res.sort(key=runs.index)
    while True:
        best = (0, -1, -1)
        for i in range(len(res)):
            for j in range(len(res)):
                if i != j:
                    k = runs_overlap(res[i], res[j])
                    if k > best[0]:
                        best = (k, i, j)
        k, i, j = best
        if k == 0:
            return res
        res[i] = res[i] + res[j][k:]
        del res[j]


class TexturePacker:
    # The texture list of the PSDL. A texture reference points to the first texture of a run and the attributes after it
    # also use the next ones (n + 1, n + 2...), so each run must be whole in the list, but the runs can overlap and a run
    # can be found inside another one (e.g. the single textures).
    def __init__(self):
        self.textures = []
        self.first = {}  # texture -> its first index in the list

    def find(self, run, limit=None):
        # the reference of the first copy of the run in the list (index + 1), None if missing or above the limit
        res = None
        i = self.first.get(run[0])
        if i is not None:
            n = len(run)
            for j in range(i, len(self.textures) - n + 1):
                if tuple(self.textures[j:j + n]) == run:
                    res = j + 1
                    break
        if res is not None and limit is not None and res > limit:
            return None
        return res

    def append(self, run):
        k = runs_overlap(self.textures, run)
        for t in run[k:]:
            if t not in self.first:
                self.first[t] = len(self.textures)
            self.textures.append(t)

    def add(self, runs, uses, limit=None):
        # adds the missing runs, the most used first (above 511 the references are not rendered properly by stock MM2)
        missing = [r for r in sorted(dict.fromkeys(runs), key=lambda r: -uses[r]) if self.find(r, limit) is None]
        merged = merge_runs([r for r in missing if len(r) > 1])
        in_merged = {t for m in merged for t in m}
        items = [(m, max(uses[r] for r in missing if run_contains(m, r))) for m in merged]
        items += [(r, uses[r]) for r in missing if len(r) == 1 and r[0] not in in_merged]
        items.sort(key=lambda x: -x[1])
        for run, _ in items:
            if self.find(run, limit) is None:
                self.append(run)


class PSDLWriter:
    def __init__(self, scene_input: SceneInput, filepath, split_non_coplanar_roads, cap_materials):
        self.scene_input = scene_input
        self.filepath = filepath
        self.split_non_coplanar_roads = split_non_coplanar_roads
        self.cap_materials = cap_materials
        self.utils = Utils(self.scene_input)

    def get_vertex_2(self, bm, index):
        return self.scene_input.get_vertex(bm, index)

    def get_max_v(self, obj):
        bname = self.utils.get_object_type(obj)
        max_v = 0
        if bname in ["FACB", "FAC", "SLIVER"]:
            max_v = 2
        elif bname in ["RAIL", "RAILC", "INST", "BAI", "PTH", "PKG", "TRAFL"]:
            max_v = 0
        else:
            max_v = self.scene_input.get_vertices_num(obj)
        return max_v

    def initialize_variables(self):
        self.vertices_blocks = []
        self.min_pos = [float('inf'), float('inf'), float('inf')]
        self.max_pos = [float('-inf'), float('-inf'), float('-inf')]
        self.sects_x = 0
        self.sects_y = 0
        self.sects = []
        self.textures = []
        self.n_mats = 1
        self.blocks = []
        self.vertices = []
        self.heights = []
        self.tot_verts = []
        self.tot_heights = []
        self.block_flags = []
        self.prop_blocks = []
        self.prop_rules = {}
        self.no_prop_blocks = set()  # blocks with props that are not exported (see check_prop_blocks_materials)
        self.already_rotated = {}
        self.epsilon = 0.03
        self.spike_width = 0.1  # thinner spikes in the perimeters are removed (see remove_spikes)
        self.height_epsilon = 0.001
        self.tex_warning = 0
        self.tex_warning_2 = 0
        self.ct_warning = False

    def read_blocks(self):
        print("counting blocks...")
        blocks_temp = []
        n_blocks = 0
        for obj in self.scene_input.get_object_list():
            n = self.utils.get_block_number(obj)
            if n > n_blocks:
                n_blocks = n

        for i in range(n_blocks):
            blocks_temp.append([])

        print("reading blocks...")
        for obj in self.scene_input.get_object_list():
            bname = self.utils.get_object_type(obj)
            vert_num = self.scene_input.get_vertices_num(obj)
            poly_num = self.scene_input.get_polygons_num(obj)
            # PERIM: the perimeter of the block set manually (its vertices in the order of the file, no faces)
            has_geometry = bname not in ["INST", "BAI", "PTH", "PKG", "TRAFL"] and (bname == "RAIL" or (vert_num > 0 and poly_num > 0)
                                                                                  or (bname == "PERIM" and vert_num > 0))
            if has_geometry:
                n = self.utils.get_block_number(obj)
                blocks_temp[n-1].append(Attribute(geo=obj, mat_id=0))

        for b in blocks_temp:
            if len(b) > 0:
                self.blocks.append(b)
        print("Found " + str(len(self.blocks)) + " blocks")

    def calc_boundaries(self):
        print("calculating boundaries...")
        for obj in self.scene_input.get_object_list():
            max_v = self.get_max_v(obj)
            for i in range(max_v):
                v = self.scene_input.get_vertex(obj, i)
                for j in range(3):
                    if v[j] > self.max_pos[j]:
                        self.max_pos[j] = v[j]
                    if v[j] < self.min_pos[j]:
                        self.min_pos[j] = v[j]
        size_x = self.max_pos[0] - self.min_pos[0]
        size_y = self.max_pos[1] - self.min_pos[1]
        self.sects_x = math.ceil(size_x / 10)
        self.sects_y = math.ceil(size_y / 10)
        for i in range(self.sects_x * self.sects_y):
            self.sects.append([])
        print("Calculated boundaries: " + str(self.min_pos) + ", " + str(self.max_pos))
        print("Number of sections: " + str(self.sects_x) + " x " + str(self.sects_y))

    def vert_lookup_sections(self, v):
        v2 = np.subtract(v, (self.min_pos[0], self.min_pos[1], 0))
        sx = math.ceil(v2[0]/10)
        if sx == 0:
            sx = 1
        sy = math.ceil(v2[1]/10)
        if sy == 0:
            sy = 1
        px = int(v2[0] % 10)
        py = int(v2[1] % 10)
        s5 = sx + self.sects_x * (sy - 1)
        if py < 2:
            s2 = sx + self.sects_x * (sy - 2)
        else:
            s2 = -1
        if py == 9:
            s8 = sx + self.sects_x * sy
        else:
            s8 = -1
        if px < 2:
            s4 = sx + self.sects_x * (sy - 1) - 1
            if py < 2:
                s1 = sx + self.sects_x * (sy - 2) - 1
                s7 = -1
            elif py == 9:
                s1 = -1
                s7 = sx + self.sects_x * sy - 1
            else:
                s1 = -1
                s7 = -1
        else:
            s1 = -1
            s4 = -1
            s7 = -1
        if px == 9:
            s6 = sx + self.sects_x * (sy - 2) + 1
            if py < 2:
                s3 = sx + self.sects_x * (sy - 2) + 1
                s9 = -1
            elif py == 9:
                s3 = -1
                s9 = sx + self.sects_x * sy + 1
            else:
                s3 = -1
                s9 = -1
        else:
            s3 = -1
            s6 = -1
            s9 = -1
        this_sects = [s1, s2, s3, s4, s5, s6, s7, s8, s9]
        this_sects_2 = []
        for s in this_sects:
            if s > 0 and s <= len(self.sects):
                this_sects_2.append(s - 1) # calculated s (from original maxscript version) is base 1, we need base 0 in python
        return this_sects_2

    def verts_are_same(self, v1, v2):
        if abs(v1[0] - v2[0]) < self.epsilon:
            if abs(v1[1] - v2[1]) < self.epsilon:
                if abs(v1[2] - v2[2]) < self.epsilon:
                    return True
        return False

    def get_vert_index(self, bv):
        ind = -1
        this_sects_2 = self.vert_lookup_sections(bv)
        other_verts = []
        for s in this_sects_2:
            for v2 in self.sects[s]:
                if v2 not in other_verts:
                    other_verts.append(v2)
        for v2 in other_verts:
            if self.verts_are_same(bv, v2.pos):
                ind = v2.ID
                break
        return ind + 1

    def process_vertices(self):
        print("processing vertices...")
        for bi in range(len(self.blocks)):
            for b in self.blocks[bi]:
                obj = b.geo
                max_v = self.get_max_v(obj)
                for i in range(max_v):
                    v = self.scene_input.get_vertex(obj, i)
                    this_sects_2 = self.vert_lookup_sections(v)
                    self.tot_verts.append(VertWSects(pos=v, sects=this_sects_2, bloc=bi))
                    bname = self.utils.get_object_type(obj)
                    if bname in ["FACB", "ROOF", "SLIVER"]:
                        if i == 1:
                            self.tot_heights.append(self.scene_input.get_vertex(obj, 2)[2])
                    elif bname == "FAC":
                        self.tot_heights.append(self.scene_input.get_vertex(obj, 0)[2])
                        self.tot_heights.append(self.scene_input.get_vertex(obj, 2)[2])
        print("found " + str(len(self.tot_verts)) + " vertices")

    def search_duplicate_vertices(self):
        print("searching for duplicate vertices...")
        for v in self.tot_verts:
            v_sects = v.sects
            other_verts = []
            other_is = []
            for s in v_sects:
                for iv2 in range(len(self.sects[s])):
                    this_pos = self.sects[s][iv2].pos
                    this_id = self.sects[s][iv2].ID
                    if this_pos not in other_verts:
                        other_verts.append(this_pos)
                    if this_id not in other_is:
                        other_is.append(this_id)
            bv = v.pos
            alr = False
            ialr = 0
            for iv2 in range(len(other_verts)):
                if self.verts_are_same(bv, other_verts[iv2]):
                    alr = True
                    ialr = other_is[iv2]
                    break
            if not alr:
                self.vertices.append(bv)
                self.vertices_blocks.append([v.bloc])
                for s in v_sects:
                    self.sects[s].append(SectVert(pos=bv, ID=len(self.vertices)-1))
            else:
                self.vertices_blocks[ialr].append(v.bloc)
        for v in self.tot_heights:
            if self.get_height_index(v) == -1:
                self.heights.append(v)
        # sliver texture heights
        for obj in self.scene_input.get_object_list():
            typ = self.utils.get_object_type(obj)
            prop = self.scene_input.get_property_container(obj)
            if typ == "SLIVER":
                sh = int(prop["tiling"])/100.0
                if self.get_height_index(sh) == -1:
                    self.heights.append(sh)
        print("Vertices after deduplication: " + str(len(self.vertices)) + " (heights: " + str(len(self.heights)) + ")")

    def get_mat_list(self, obj):
        prop = self.scene_input.get_property_container(obj)
        keys = [k for k in prop.keys() if k.startswith("texture")]
        mat = [prop[k] for k in keys]
        matlst = []
        for m in mat:
            matlst.append(m.split(".")[0].lower())
        return matlst

    def get_prop_rule(self, bp):
        # the prop rule of a road part (None if it has none), only roads with sidewalks have props
        prop = self.scene_input.get_property_container(bp.geo)
        prop_rule = prop.get("prop_rule", None)
        if prop_rule is None or self.utils.get_object_type(bp.geo) not in ["ROADS", "ROADD"]:
            return None
        return int(prop_rule)

    def has_prop_rule(self, b):
        return any(self.get_prop_rule(bp) is not None for bp in b)

    def get_part_runs(self, b):
        # the texture runs of the parts of a block that have a texture reference: (part, run, divider run), the divider
        # run is not None for the divided roads
        ist = []
        swt = []
        cwt = []
        for pb in b:
            if int(self.scene_input.get_property_container(pb.geo).get("disable", "0")):
                continue
            pname = self.utils.get_object_type(pb.geo)
            if pname in ["IS", "CW", "SW"]:
                mat = self.get_mat_list(pb.geo)[0]
            if pname == "IS":
                if mat not in ist:
                    ist.append(mat)
            elif pname == "CW":
                if mat not in cwt:
                    cwt.append(mat)
            elif pname == "SW":
                if mat not in swt:
                    swt.append(mat)
        is_runs = {}
        for t in ist:
            mats = [t]
            if len(swt) == 0 and len(cwt) > 0:
                mats.append(t)
                mats.append(cwt[0])
            elif len(swt) > 0 and len(cwt) == 0:
                mats.append(swt[0])
            elif len(swt) > 0 and len(cwt) > 0:
                mats.append(swt[0])
                mats.append(cwt[0])
            is_runs[t] = tuple(mats)
        res = []
        for pb in b:
            if int(self.scene_input.get_property_container(pb.geo).get("disable", "0")):
                continue
            pname = self.utils.get_object_type(pb.geo)
            if pname in ["ROADS", "ROADSN", "FAC", "SLIVER", "BLOCK", "ROOF", "RAIL", "RAILC"]:
                res.append((pb, tuple(self.get_mat_list(pb.geo)), None))
            elif pname == "ROADN":
                res.append((pb, (self.get_mat_list(pb.geo)[0],) * 3, None))
            elif pname == "IS":
                res.append((pb, is_runs[self.get_mat_list(pb.geo)[0]], None))
            elif pname in ["ROADD", "ROADDN"]:
                # the road (n: road, n + 1: sidewalk, n + 2: LOD) and the divider (its own reference stored in a byte,
                # 4 textures) are independent runs, as in the stock cities
                mats = tuple(self.get_mat_list(pb.geo))
                if len(mats) >= 7:
                    res.append((pb, mats[:3], mats[3:7]))
                else:
                    res.append((pb, mats, ()))
        return [r for r in res if len(r[1]) > 0 and not int(self.scene_input.get_property_container(r[0].geo).get("disable", "0"))]

    def process_materials(self):
        print("processing materials...")
        packer = TexturePacker()
        runs = []  # (part, attribute to set, run, needs a reference < 256)
        div_after_road = []  # divided roads with less than 7 textures: the divider follows the road
        for b in self.blocks:
            prop_block = self.has_prop_rule(b)
            for pb, run, div_run in self.get_part_runs(b):
                runs.append((pb, "mat_id", run, prop_block or div_run == ()))
                if div_run:
                    runs.append((pb, "div_mat_id", div_run, True))
                elif div_run == ():
                    div_after_road.append(pb)
        uses = Counter(run for _, _, run, _ in runs)
        # first the runs that need a reference < 256: the dividers (stored in a byte) and the blocks with props (the game
        # reads the texture references with an index >= 255 wrongly while placing the props along the roads,
        # lvlSDL::Enumerate does not skip the data of a texture reference with subtype > 0, and quits with "Invalid
        # command" or crashes with MM2Hook)
        packer.add([run for _, _, run, low in runs if low], uses, PROP_BLOCK_MAX_MAT_ID)
        packer.add([run for _, _, run, low in runs if not low], uses)
        refs = {}
        for pb, attr, run, low in runs:
            key = (run, low)
            if key not in refs:
                ref = packer.find(run, PROP_BLOCK_MAX_MAT_ID) if low else None
                refs[key] = ref if ref is not None else packer.find(run)
            setattr(pb, attr, refs[key])
        for pb in div_after_road:
            pb.div_mat_id = pb.mat_id + 3
        self.textures = packer.textures
        self.n_mats = len(self.textures) + 1
        print("Materials found: " + str(len(self.textures)) + " textures (" + str(len(set(refs.values()))) +
              " texture references, " + str(len(set(self.textures))) + " different textures)")
        self.check_prop_blocks_materials()

    def check_prop_blocks_materials(self):
        # the blocks with props must only have texture references with an index < 255 (see process_materials),
        # the props of the others are not exported
        self.no_prop_blocks = set()
        for bi in range(len(self.blocks)):
            b = self.blocks[bi]
            if self.has_prop_rule(b) and any(bp.mat_id > PROP_BLOCK_MAX_MAT_ID for bp in b):
                self.no_prop_blocks.add(bi)
        if len(self.no_prop_blocks) > 0:
            report.warning(str(len(self.no_prop_blocks)) + " blocks with props use a texture with an index >= " +
                  str(PROP_BLOCK_MAX_MAT_ID) + " (too many textures in the blocks with props and in the divided roads), " +
                  "their props are not exported, otherwise MM2 would quit or crash while loading the city (blocks " +
                  ", ".join(str(bi + 1) for bi in sorted(self.no_prop_blocks)) + ")")

    def get_face_array(self, obj, f, is_bmesh):
        return self.scene_input.get_polygon(obj, f)

    def get_triangle_area(self, p0, p1, p2):
        return 0.5 * abs((p0[0] - p2[0]) * (p1[1] - p0[1]) - (p0[0] - p1[0]) * (p2[1]-p0[1]))

    def get_verts_on_isolated_edges(self, obj, vert):
        num_faces = self.scene_input.get_polygons_num(obj)  # bmesh
        return self.get_verts_on_isolated_edges_2(obj, vert, range(num_faces))

    def get_verts_on_isolated_edges_2(self, obj, vert, faces, is_bmesh=True):
        res = []
        assoc_faces = []
        for f in faces:
            ff = self.get_face_array(obj, f, is_bmesh)
            for v in ff:
                if v == vert:
                    if is_bmesh:
                        p0 = self.get_vertex_2(obj, ff[0])
                        p1 = self.get_vertex_2(obj, ff[1])
                        p2 = self.get_vertex_2(obj, ff[2])
                        if self.get_triangle_area(p0, p1, p2) > 0.00001:
                            assoc_faces.append(f)
                    else:
                        assoc_faces.append(f)
        assoc_verts = []
        for f in assoc_faces:
            ff = self.get_face_array(obj, f, is_bmesh)
            for v in ff:
                if v != vert:
                    assoc_verts.append(v)
        for v2 in assoc_verts:
            n = 0
            for f in assoc_faces:
                ff = self.get_face_array(obj, f, is_bmesh)
                for v in ff:
                    if v == v2:
                        n += 1
            if n == 1:
                res.append(v2)
        return res

    def get_next_or_prev_verts(self, obj, vert, vertlist, prev, is_bmesh=True):
        assoc_faces = []
        num_faces = self.scene_input.get_polygons_num(obj)  # bmesh
        for f in range(num_faces):
            ff = self.get_face_array(obj, f, is_bmesh)
            for v in ff:
                if v == vert:
                    assoc_faces.append(f)
        return self.get_next_or_prev_verts_2(obj, vert, vertlist, assoc_faces, prev, is_bmesh)

    def get_next_or_prev_verts_2(self, obj, vert, vertlist, faces, prev, is_bmesh=True):
        res = []
        for v in vertlist:
            for f in faces:
                ff = self.get_face_array(obj, f, is_bmesh)
                vA = vert if prev else v
                vB = v if prev else vert
                if (ff[0] == vA and ff[2] == vB) or (ff[1] == vA and ff[0] == vB) or (ff[2] == vA and ff[1] == vB):
                    res.append(v)
        return res

    def get_angle(self, O, A, B):
        pos_a = [A[0]-O[0], A[1]-O[1], A[2]-O[2]]
        pos_b = [B[0]-O[0], B[1]-O[1], B[2]-O[2]]
        ang_a = 0
        if pos_a[0] != 0:
            ang_a = math.degrees(math.atan(pos_a[1] / pos_a[0]))
            if pos_a[0] < 0:
                if pos_a[1] < 0:
                    ang_a = -180.0 + ang_a
                else:
                    ang_a = 180.0 + ang_a
        else:
            if pos_a[1] < 0:
                ang_a = -90.0
            else:
                ang_a = 90.0
        ang_b = 0
        if pos_b[0] != 0:
            ang_b = math.degrees(math.atan(pos_b[1] / pos_b[0]))
            if pos_b[0] < 0:
                if pos_b[1] < 0:
                    ang_b = -180.0 + ang_b
                else:
                    ang_b = 180.0 + ang_b
        else:
            if pos_b[1] < 0:
                ang_b = -90.0
            else:
                ang_b = 90.0
        ang = ang_a - ang_b
        if ang <= 0:
            finang = -(180.0 + ang)
        else:
            finang = -(ang - 180.0)
        return finang

    def bmesh_center_xy(self, bm):
        bm_verts_num = self.scene_input.get_vertices_num(bm) #bmesh
        verts = [self.get_vertex_2(bm, v) for v in range(bm_verts_num)]
        if len(verts) == 0:
            return None
        max_x = max(v[0] for v in verts)
        max_y = max(v[1] for v in verts)
        min_x = min(v[0] for v in verts)
        min_y = min(v[1] for v in verts)
        return [(max_x + min_x) / 2.0, (max_y + min_y) / 2.0]

    def point_line_dist_3d(self, l0, l1, p):
        return np.linalg.norm(np.cross(np.subtract(l0, p), np.subtract(l1, l0)))/np.linalg.norm(np.subtract(l1, l0))

    def is_spike(self, a, x, b):
        # x is the tip of a spike (the perimeter goes to x and comes back along almost the same line) when b is
        # within spike_width of the line from x to a, or a of the one from x to b, on the same side of x (2D)
        u = [a[0] - x[0], a[1] - x[1]]
        w = [b[0] - x[0], b[1] - x[1]]
        lu = math.hypot(u[0], u[1])
        lw = math.hypot(w[0], w[1])
        if lu < self.epsilon or lw < self.epsilon or u[0] * w[0] + u[1] * w[1] <= 0:
            return False
        far, near, l_far = (u, w, lu) if lu >= lw else (w, u, lw)
        return abs(far[0] * near[1] - far[1] * near[0]) / l_far < self.spike_width

    def remove_spikes(self, perimeter, positions):
        # Removes the tips of the spikes that lead to no neighbour: the game takes them as edges out of the city, the
        # cars that cross them are lost ("PHYS.DeclareMover : mover not even in city"). They come from the faces
        # skipped by the area threshold of get_verts_on_isolated_edges_2 (e.g. a sidewalk corner collapsed on a line
        # with its curb point at a right angle: the perimeter goes to the curb point and back) and from intersection
        # corners pinched between two road ends
        changed = True
        while changed and len(perimeter) > 3:
            changed = False
            for i in range(len(perimeter)):
                i1 = (i + 1) % len(perimeter)
                if len(perimeter[i].blocks) == 0 and self.is_spike(positions[i - 1], positions[i], positions[i1]):
                    del perimeter[i]
                    del positions[i]
                    changed = True
                    break

    # the original_name of the first part of the block, if any
    def block_name(self, the_block):
        try:
            return self.scene_input.get_property_container(the_block[0].geo).get("original_name", None)
        except Exception:
            return None

    def get_perimeter(self, the_block, bi, precise):
        perimeter, positions = self.trace_perimeter(the_block, bi, precise)
        if perimeter is None:
            return None
        return self.simplify_perimeter(perimeter, positions, bi)

    def trace_perimeter(self, the_block, bi, precise):
        # the perimeter followed around the faces of the block (the inner vertices of the divided road ends excluded),
        # with its positions: (None, None) if the block has no faces
        perimeter = []
        perimeter_v = []
        perimeter0 = []
        excl_v = []
        block_index = self.utils.get_block_number(the_block[0].geo)
        prop = self.scene_input.get_property_container(the_block[0].geo)
        orig_obj_name = prop.get("original_name", None)
        orig_obj_msg = ''
        if orig_obj_name is not None:
            orig_obj_msg = ' (object ' +  orig_obj_name + ')'
        new_block = self.scene_input.create_composed_mesh()
        for b in the_block:
            not_on_perimeter = bool(int(b.geo.get("not_on_perimeter", "0")))
            thisbname = self.utils.get_object_type(b.geo)
            if not not_on_perimeter:
                if thisbname not in ["FACB", "FAC", "RAIL", "RAILC", "SLIVER", "ROOF"]:
                    newb = self.scene_input.create_and_add_composed_mesh_from_object(b.geo, new_block)
                    if thisbname in ["ROADDN", "ROADD"]:
                        newb_verts_num = self.scene_input.get_vertices_num(newb) #bmesh
                        if thisbname == "ROADDN":
                            excl_v.append(self.get_vert_index(self.get_vertex_2(newb, 1)))
                            excl_v.append(self.get_vert_index(self.get_vertex_2(newb, 2)))
                            excl_v.append(self.get_vert_index(self.get_vertex_2(newb, newb_verts_num - 2)))
                            excl_v.append(self.get_vert_index(self.get_vertex_2(newb, newb_verts_num - 3)))
                        elif thisbname == "ROADD":
                            excl_v.append(self.get_vert_index(self.get_vertex_2(newb, 2)))
                            excl_v.append(self.get_vert_index(self.get_vertex_2(newb, 3)))
                            excl_v.append(self.get_vert_index(self.get_vertex_2(newb, newb_verts_num - 3)))
                            excl_v.append(self.get_vert_index(self.get_vertex_2(newb, newb_verts_num - 4)))
                    self.scene_input.destroy_composed_mesh(newb)
        self.scene_input.remove_doubles(new_block, self.epsilon)
        max_per_verts = []
        new_block_verts_2 = []
        new_block_verts_num = self.scene_input.get_vertices_num(new_block) #bmesh
        for v in range(new_block_verts_num):
            new_block_verts_2.append(self.get_vertex_2(new_block, v))
        bm_center = self.bmesh_center_xy(new_block)
        if bm_center is None:
            return None, None
        cx = bm_center[0]
        cy = bm_center[1]
        if precise:
            for i in range(1, 721):
                i2 = math.radians(i * 0.5)
                sin_i = math.sin(i2)
                cos_i = math.cos(i2)
                maxx = float('-inf')
                for v in range(len(new_block_verts_2)):
                    if new_block_verts_2[v][0] > maxx:
                        maxx = new_block_verts_2[v][0]
                for v in range(len(new_block_verts_2)):
                    if abs(maxx - new_block_verts_2[v][0]) < 0.1:
                        if v not in max_per_verts:
                            max_per_verts.append(v)
                    a1mp1 = new_block_verts_2[v][0] - cx
                    a2mp2 = new_block_verts_2[v][1] - cy
                    new_block_verts_2[v] = [(cos_i * a1mp1 - sin_i * a2mp2 + cx),
                                            (sin_i * a1mp1 + cos_i * a2mp2 + cy),
                                            new_block_verts_2[v][2]]
        else:
            maxx = float('-inf')
            for v in range(len(new_block_verts_2)):
                if new_block_verts_2[v][0] > maxx:
                    maxx = new_block_verts_2[v][0]
            for v in range(len(new_block_verts_2)):
                if abs(maxx - new_block_verts_2[v][0]) < 0.1:
                    if v not in max_per_verts:
                        max_per_verts.append(v)
        first = 0
        second = -1
        for i in range(len(max_per_verts)):
            assoc_verts = self.get_verts_on_isolated_edges(new_block, max_per_verts[i])
            prev_verts = self.get_next_or_prev_verts(new_block, max_per_verts[i], assoc_verts, True)
            if len(prev_verts) == 1:
                first = max_per_verts[i]
                second = prev_verts[0]
            else:
                next_verts = self.get_next_or_prev_verts(new_block, max_per_verts[i], assoc_verts, False)
                if len(next_verts) == 1:
                    second = max_per_verts[i]
                    first = next_verts[0]
            if second != -1:
                break
        if second == -1:
            raise Exception("Perimeter error on block " + str(block_index) + orig_obj_msg)
        perimeter0.append(first)
        perimeter0.append(second)
        loop_index = 0
        while perimeter0[0] != perimeter0[-1]:
            loop_index += 1
            if loop_index > 65536:
                raise Exception("Perimeter error: infinite loop on block " + str(block_index) + orig_obj_msg)
            assoc_verts = self.get_verts_on_isolated_edges(new_block, perimeter0[-1])
            prev_verts = self.get_next_or_prev_verts(new_block, perimeter0[-1], assoc_verts, True)
            if len(prev_verts) == 0:
                raise Exception("Perimeter error: dead end on block " + str(block_index) + orig_obj_msg)
            if len(prev_verts) == 1:
                perimeter0.append(prev_verts[0])
            else:
                perim_v = 0
                max_ang = -180
                for i in range(len(prev_verts)):
                    O = self.get_vertex_2(new_block, perimeter0[-1])
                    A = self.get_vertex_2(new_block, perimeter0[-2])
                    B = self.get_vertex_2(new_block, prev_verts[i])
                    ang = self.get_angle(O, A, B)
                    if ang > max_ang:
                        perim_v = prev_verts[i]
                        max_ang = ang
                perimeter0.append(perim_v)
        perimeter0.pop()
        for v in perimeter0:
            vpos = self.get_vertex_2(new_block, v)
            vid = self.get_vert_index(vpos)
            perimeter.append(PerimeterVert(vid, []))
            perimeter_v.append(vpos)
        for pv in perimeter:
            pv.blocks = self.vertices_blocks[pv.ID - 1]
        self.scene_input.destroy_composed_mesh(new_block)
        perimeter_clean = []
        perimeter_v_clean = []
        for i in range(len(perimeter)):
            pv = perimeter[i]
            pos = perimeter_v[i]
            if not pv.ID in excl_v:
                perimeter_clean.append(pv)
                perimeter_v_clean.append(pos)
        return perimeter_clean, perimeter_v_clean

    def simplify_perimeter(self, perimeter_clean, perimeter_v_clean, bi):
        # the points of the perimeter that lead to other blocks, and the others where it turns (the spikes removed)
        perimeter_f = []
        perimeter_v_f = []
        for i in range(len(perimeter_clean)):
            pv = perimeter_clean[i]
            i0 = i - 1
            i1 = i + 1
            if i0 < 0:
                i0 = len(perimeter_clean) - 1
            if i1 >= len(perimeter_clean):
                i1 = 0
            # clean blocks (since the block itself is included, possibly more than once)
            p_blocks = []
            for pb in pv.blocks:
                if pb != bi:
                    if pb not in p_blocks:
                        p_blocks.append(pb)
            pv.blocks = p_blocks
            if len(pv.blocks) > 0 or self.point_line_dist_3d(perimeter_v_clean[i0], perimeter_v_clean[i1], perimeter_v_clean[i]) > self.epsilon:
                perimeter_f.append(pv)
                perimeter_v_f.append(perimeter_v_clean[i])
        self.remove_spikes(perimeter_f, perimeter_v_f)
        return perimeter_f

    def get_manual_perimeter(self, perim_part, bi):
        # the perimeter set manually (a PERIM part): its points in the order of the file, the blocks sharing them as
        # neighbours; with the property "simplify" the points are dropped as for the perimeter found from the faces (it
        # is then the traced perimeter, in the order of the file)
        geo = perim_part.geo
        positions = [self.scene_input.get_vertex(geo, i) for i in range(self.scene_input.get_vertices_num(geo))]
        perimeter = []
        for pos in positions:
            vid = self.get_vert_index(pos)
            perimeter.append(PerimeterVert(vid, list(self.vertices_blocks[vid - 1])))
        simplify = bool(int(self.scene_input.get_property_container(geo).get("simplify", "0")))
        if simplify:
            perimeter.reverse()
            positions.reverse()
            res = self.simplify_perimeter(perimeter, positions, bi)
            res.reverse()
            return res
        for pv in perimeter:
            p_blocks = []
            for pb in pv.blocks:
                if pb != bi and pb not in p_blocks:
                    p_blocks.append(pb)
            pv.blocks = p_blocks
        return perimeter

    def check_point_plane_dist(self, x1, x2, x3, x4, y1, y2, y3, y4, z1, z2, z3, z4):
        a = (y3-y2)*(z4-z2)-(y4-y2)*(z3-z2)
        b = (z3-z2)*(x4-x2)-(z4-z2)*(x3-x2)
        c = (x3-x2)*(y4-y2)-(x4-x2)*(y3-y2)
        d = -(a*x2+b*y2+c*z2)
        dist = abs(a*x1+b*y1+c*z1+d)/math.sqrt(a*a+b*b+c*c)
        return dist

    def convert_to_attr(self, last, typ, subtype):
        bits = []
        bits.append(last)
        typebits = self.get_bits(typ, 4)
        for b in typebits:
            bits.append(b)
        subtypebits = self.get_bits(subtype, 3)
        for b in subtypebits:
            bits.append(b)
        return self.bits_to_byte(bits)

    def get_n_assoc_polys(self, obj, vert):
        n = 0
        num_polys = self.scene_input.get_polygons_num(obj)
        for f in range(num_polys):
            ff = self.scene_input.get_polygon(obj, f)
            for v in ff:
                if v == vert:
                    n += 1
        return n

    def get_assoc_polys(self, obj, vert, excl_list):
        assoc_polys = []
        n = []
        num_polys = self.scene_input.get_polygons_num(obj)
        for f in range(num_polys):
            ff = self.scene_input.get_polygon(obj, f)
            for v in ff:
                if v == vert:
                    n.append(f)
        for f in n:
            excluded = False
            for excl in excl_list:
                if excl == f:
                    excluded = True
                    break
            if not excluded:
                assoc_polys.append(f)
        return assoc_polys

    def get_n_assoc_verts_2(self, obj, vert, faces):
        n = []
        ps = []
        for f in faces:
            ff = self.scene_input.get_polygon(obj, f)
            for v in ff:
                if v == vert:
                    ps.append(f)
        for f in ps:
            ff = self.scene_input.get_polygon(obj, f)
            for v in ff:
                if v != vert:
                    if not v in n:
                        n.append(v)
        return len(n)

    def get_height_index(self, v):
        other_verts = []
        for iv2 in range(len(self.heights)):
            if abs(v - self.heights[iv2]) < self.height_epsilon:
                return iv2
        return -1

    def convert_div_road_vals(self, end_close, start_close, typ, mat_id):
        bits = []
        mbits = self.get_bits(mat_id, 8)
        for i in range(8):
            bits.append(mbits[i])
        bits.append(end_close)
        bits.append(start_close)
        for i in range(4):
            bits.append(0)
        typebits = self.get_bits(typ, 2)
        for b in typebits:
            bits.append(b)
        return self.bits_to_byte(bits)

    def get_triangle_fans(self, obj):
        triangle_fans = []
        max_links = -1
        maxv = -1
        polys_done = []
        while max_links != 0:
            max_links = 0
            assoc_polys = []
            num_verts = self.scene_input.get_vertices_num(obj)
            for v in range(num_verts):
                t_assoc_polys = self.get_assoc_polys(obj, v, polys_done)
                n_assoc_verts = self.get_n_assoc_verts_2(obj, v, t_assoc_polys)
                if abs(len(t_assoc_polys) - n_assoc_verts) < 2 and len(t_assoc_polys) > max_links:
                    max_links = len(t_assoc_polys)
                    assoc_polys = list(t_assoc_polys)  # deepcopy
                    maxv = v
            if max_links != 0:
                for p in assoc_polys:
                    polys_done.append(p)
                tri_fan = []
                tri_fan.append(self.get_vert_index(self.scene_input.get_vertex(obj, maxv)))
                end_vertices = self.get_verts_on_isolated_edges_2(obj, maxv, assoc_polys, False)
                v2 = -1
                if len(end_vertices) == 0:
                    ff = self.scene_input.get_polygon(obj, assoc_polys[0])
                    for v in ff:
                        if v != maxv:
                            v2 = v
                            break
                else:
                    v2 = self.get_next_or_prev_verts_2(obj, maxv, end_vertices, assoc_polys, False, False)[0]
                tri_fan.append(self.get_vert_index(self.scene_input.get_vertex(obj, v2)))
                lastv = v2
                started = False
                while (lastv != v2 and self.get_n_assoc_verts_2(obj, lastv, assoc_polys) == 3) or not started:
                    started = True
                    next_vertices = self.get_verts_on_isolated_edges_2(obj, lastv, assoc_polys, False)
                    lastv = self.get_next_or_prev_verts_2(obj, lastv, next_vertices, assoc_polys, False, False)[0]
                    tri_fan.append(self.get_vert_index(self.scene_input.get_vertex(obj, lastv)))
                triangle_fans.append(tri_fan)
        return triangle_fans

    # ==== PART TYPES BEGIN ====

    def process_part_block_is(self, b, bi, bp, bpi, last):
        # Generic block and intersection
        sl = self.temp_shorts_list
        trifansflag = 6
        if self.block_flags[bi].f4 == 0:
            if self.utils.get_object_type(bp.geo) == "IS":
                self.block_flags[bi].f5 = 1
                trifansflag = 5
            else:
                self.block_flags[bi].f3 = 1
        blockminy = float('inf')
        blockmaxy = float('-inf')
        vert_num = self.scene_input.get_vertices_num(bp.geo)
        for v in range(vert_num):
            vpos = self.scene_input.get_vertex(bp.geo, v)
            if vpos[1] < blockminy:
                blockminy = vpos[1]
            if vpos[1] > blockmaxy:
                blockmaxy = vpos[1]
        if abs(blockminy-blockmaxy) > 0.05:
            trifansflag = 6  # road triangle fan can only be flat, so use standard fans if this road is not flat
        tri_fans = self.get_triangle_fans(bp.geo)
        fi = 0
        for f in tri_fans:
            fi += 1
            last2 = 1 if fi == len(tri_fans) and last == 1 else 0
            n_triangles = len(f) - 2
            if n_triangles > 7:
                sl.append(self.convert_to_attr(last2, trifansflag, 0))
                sl.append(n_triangles)
            else:
                sl.append(self.convert_to_attr(last2, trifansflag, n_triangles))
            for v in f:
                sl.append(v)

    def process_part_roof(self, b, bi, bp, bpi, last):
        # Roof
        sl = self.temp_shorts_list
        tri_fans = self.get_triangle_fans(bp.geo)
        fi = 0
        for f in tri_fans:
            fi += 1
            last2 = 0
            if fi == len(tri_fans):
                if last == 1:
                    last2 = 1
            n_triangles = len(f) - 1
            if n_triangles > 7:
                sl.append(self.convert_to_attr(last2, 12, 0))
                sl.append(n_triangles)
            else:
                sl.append(self.convert_to_attr(last2, 12, n_triangles))
            sl.append(self.get_height_index(self.scene_input.get_vertex(bp.geo, 2)[2]))
            for v in f:
                sl.append(v)

    def process_part_cw(self, b, bi, bp, bpi, last):
        # Crosswalk
        sl = self.temp_shorts_list
        vert_count = self.scene_input.get_vertices_num(bp.geo)
        if vert_count != 4:
            raise Exception("Error in block " + str(bi) + ": CW vertex count is not 4")
        sl.append(self.convert_to_attr(last, 4, 4))
        for i in range(vert_count):
            v = self.scene_input.get_vertex(bp.geo, i)
            sl.append(self.get_vert_index(v))

    def process_part_sw_cap(self, b, bi, bp, bpi, last, uniq_vert_idxs):
        sl = self.temp_shorts_list
        # the "cap" property tells which end piece (start: references 0, end: references 1), otherwise both are
        # written to avoid having to detect the case
        prop = self.scene_input.get_property_container(bp.geo)
        cap = prop.get("cap", "both")
        ends = [0] if cap == "start" else [1] if cap == "end" else [0, 1]
        for i, end in enumerate(ends):
            sl.append(self.convert_to_attr(last if i == len(ends) - 1 else 0, 1, 4//2))
            sl.append(end)
            sl.append(end)
            sl.append(uniq_vert_idxs[1])
            sl.append(uniq_vert_idxs[0])

    def process_part_sw(self, b, bi, bp, bpi, last):
        # Sidewalk
        sl = self.temp_shorts_list
        vert_count = self.scene_input.get_vertices_num(bp.geo)

        if (vert_count % 2) != 0:
            raise Exception("Error in block " + str(bi) + ": SW vertex count is not multiple of 2")

        # Check if it's a cap
        vert_idxs = [self.get_vert_index(self.scene_input.get_vertex(bp.geo, i)) for i in range(vert_count)]
        uniq_vert_idxs = list(dict.fromkeys(vert_idxs))
        if len(uniq_vert_idxs) == 2:
            return self.process_part_sw_cap(b, bi, bp, bpi, last, uniq_vert_idxs)

        if vert_count > 14:
            sl.append(self.convert_to_attr(last, 1, 0))
            sl.append(vert_count//2)
        else:
            sl.append(self.convert_to_attr(last, 1, vert_count//2))
        for i in range(vert_count):
            if (i + 1) % 2 == 0:
                v = i - 1
            else:
                v = i + 1
            sl.append(self.get_vert_index(self.scene_input.get_vertex(bp.geo, v)))

    def add_prop_rule(self, bi, bp):
        prop_rule = self.get_prop_rule(bp)
        if prop_rule is not None and bi not in self.no_prop_blocks:
            self.prop_blocks.append(bi)
            self.prop_rules[bi] = prop_rule

    def process_part_roads(self, b, bi, bp, bpi, last):
        # Road with sidewalk
        prop = self.scene_input.get_property_container(bp.geo)
        self.add_prop_rule(bi, bp)
        sl = self.temp_shorts_list
        self.block_flags[bi].f4 = 1
        self.block_flags[bi].f5 = 0
        n_verts = self.scene_input.get_vertices_num(bp.geo)
        if (n_verts % 4) != 0:
            raise Exception("Error in block " + str(bi) + ": ROADS vertex count is not multiple of 4")
        the_sections = []
        a_section = []
        for v in range(n_verts):
            a_section.append(v)
        ended = False
        sectsdone = 0
        do_not_split = bool(int(prop.get("no_coplanar_fix", "0")))
        coplanar_fix_reverse = bool(int(prop.get("coplanar_fix_reverse", "0")))
        if self.split_non_coplanar_roads and not do_not_split:
            # Split non-coplanar roads in two triangular pieces to avoid bounding problems
            while not ended:
                for i in range(4 * sectsdone, len(a_section)):
                    if (i % 4) == 0 and (i + 5) < len(a_section):
                        v2 = self.scene_input.get_vertex(bp.geo, a_section[i + 2])
                        v1 = self.scene_input.get_vertex(bp.geo, a_section[i + 1])
                        v6 = self.scene_input.get_vertex(bp.geo, a_section[i + 6])
                        v5 = self.scene_input.get_vertex(bp.geo, a_section[i + 5])
                        x3 = v2[0]
                        x2 = v1[0]
                        x7 = v6[0]
                        x6 = v5[0]
                        y3 = v2[1]
                        y2 = v1[1]
                        y7 = v6[1]
                        y6 = v5[1]
                        z3 = v2[2]
                        z2 = v1[2]
                        z7 = v6[2]
                        z6 = v5[2]
                        if self.check_point_plane_dist(x3, x2, x7, x6, y3, y2, y7, y6, z3, z2, z7, z6) > 0.1:
                            # Non-coplanar, split
                            a_section_0 = []
                            a_section_1 = []
                            a_section_2 = []
                            for i2 in range(i + 4 * sectsdone):
                                a_section_0.append(a_section[i2])
                            if coplanar_fix_reverse:
                                list_a = a_section_2
                                list_b = a_section_1
                            else:
                                list_a = a_section_1
                                list_b = a_section_2
                            list_a.append(a_section[i + 7])
                            list_a.append(a_section[i + 6])
                            list_a.append(a_section[i + 1])
                            list_a.append(a_section[i])
                            list_a.append(a_section[i + 3])
                            list_a.append(a_section[i + 2])
                            list_a.append(a_section[i + 1])
                            list_a.append(a_section[i])
                            list_b.append(a_section[i])
                            list_b.append(a_section[i + 1])
                            list_b.append(a_section[i + 6])
                            list_b.append(a_section[i + 7])
                            list_b.append(a_section[i + 4])
                            list_b.append(a_section[i + 5])
                            list_b.append(a_section[i + 6])
                            list_b.append(a_section[i + 7])
                            for i2 in range(i + 8, len(a_section)):
                                a_section_2.append(a_section[i2])
                            a_section = list(a_section_2)  # deepcopy
                            if len(a_section_0) > 0:
                                the_sections.append(a_section_0)
                            if len(a_section_1) > 0:
                                the_sections.append(a_section_1)
                            sectsdone = 1
                            break
                        else:
                            sectsdone += 1
                if (1 + 4 + 4 * sectsdone) >= len(a_section):
                    ended = True
                    the_sections.append(a_section)
        else:
            the_sections.append(a_section)
        last2 = 0
        testi = 0
        for s in the_sections:
            testi += 1
            if testi == len(the_sections) and last == 1:
                last2 = 1
            if len(s) > 28:
                sl.append(self.convert_to_attr(last2, 0, 0))
                sl.append(len(s)//4)
            else:
                sl.append(self.convert_to_attr(last2, 0, (len(s)//4)))
            for v in s:
                vpos = self.scene_input.get_vertex(bp.geo, v)
                vidx = self.get_vert_index(vpos)
                sl.append(vidx)

    def process_part_roadsn_roadn(self, b, bi, bp, bpi, last):
        # Road without sidewalk
        # ROADSN is textured like this: [\]
        # ROADN: is textured like this: [\/]
        prop = self.scene_input.get_property_container(bp.geo)
        sl = self.temp_shorts_list
        if self.utils.get_object_type(bp.geo) == "ROADN":
            roadn = True
            self.block_flags[bi].f4 = 1
            self.block_flags[bi].f5 = 0
            s_str = ""
        else:
            roadn = False
            s_str = "S"
        n_verts = self.scene_input.get_vertices_num(bp.geo)
        if (n_verts % 2) != 0:
            raise Exception("Error in block " + str(bi) + ": ROAD" + s_str + "N vertex count is not multiple of 2")
        the_sections = []
        a_section = []
        for v in range(n_verts):
            a_section.append(v)
        ended = False
        sectsdone = 0
        do_not_split = bool(int(prop.get("no_coplanar_fix", "0")))
        if self.split_non_coplanar_roads and not do_not_split:
            # Split non-coplanar roads in two triangular pieces to avoid bounding problems
            while not ended:
                for i in range(2 * sectsdone, len(a_section)):
                    if (i % 2) == 0 and (i + 3) < len(a_section):
                        v0 = self.scene_input.get_vertex(bp.geo, a_section[i])
                        v1 = self.scene_input.get_vertex(bp.geo, a_section[i + 1])
                        v2 = self.scene_input.get_vertex(bp.geo, a_section[i + 2])
                        v3 = self.scene_input.get_vertex(bp.geo, a_section[i + 3])
                        x3 = v1[0]
                        x2 = v0[0]
                        x7 = v3[0]
                        x6 = v2[0]
                        y3 = v1[1]
                        y2 = v0[1]
                        y7 = v3[1]
                        y6 = v2[1]
                        z3 = v1[2]
                        z2 = v0[2]
                        z7 = v3[2]
                        z6 = v2[2]
                        if self.check_point_plane_dist(x3, x2, x7, x6, y3, y2, y7, y6, z3, z2, z7, z6) > 0.1:
                            # Non-coplanar, split
                            a_section_0 = []
                            a_section_1 = []
                            for i2 in range(i + 2 * sectsdone):
                                a_section_0.append(a_section[i2])
                            a_section_1.append(a_section[i + 3])
                            a_section_1.append(a_section[i])
                            a_section_1.append(a_section[i + 1])
                            a_section_1.append(a_section[i])
                            a_section_2 = []
                            a_section_2.append(a_section[i])
                            a_section_2.append(a_section[i + 3])
                            a_section_2.append(a_section[i + 2])
                            a_section_2.append(a_section[i + 3])
                            for i2 in range(i + 4, len(a_section)):
                                a_section_2.append(a_section[i2])
                            a_section = list(a_section_2)  # deepcopy
                            if len(a_section_0) > 0:
                                the_sections.append(a_section_0)
                            if len(a_section_1) > 0:
                                the_sections.append(a_section_1)
                            sectsdone = 1
                            break
                        else:
                            sectsdone += 1
                if (1 + 2 + 2 * sectsdone) >= len(a_section):
                    ended = True
                    the_sections.append(a_section)
        else:
            the_sections.append(a_section)
        last2 = 0
        testi = 0
        for s in the_sections:
            testi += 1
            if testi == len(the_sections) and last == 1:
                last2 = 1
            bit = 2 if roadn else 0
            if len(s) > 14:
                sl.append(self.convert_to_attr(last2, bit, 0))
                sl.append(len(s)//2)
            else:
                sl.append(self.convert_to_attr(last2, bit, (len(s)//2)))
            for v in s:
                vpos = self.scene_input.get_vertex(bp.geo, v)
                vidx = self.get_vert_index(vpos)
                sl.append(vidx)
                if not roadn:
                    sl.append(vidx)

    def process_part_roadd_roaddn(self, b, bi, bp, bpi, last):
        # Divided road with and without sidewalk
        prop = self.scene_input.get_property_container(bp.geo)
        typ = self.utils.get_object_type(bp.geo)
        self.add_prop_rule(bi, bp)
        sl = self.temp_shorts_list
        n_road_verts = 6 if typ == "ROADD" else 4
        count_max = 42 if typ == "ROADD" else 24
        n_str = "n" if typ == "ROADDN" else ""
        n_verts = self.scene_input.get_vertices_num(bp.geo)
        self.block_flags[bi].f4 = 1
        self.block_flags[bi].f5 = 0
        if (n_verts % n_road_verts) != 0:
            raise Exception("Error in block " + str(bi) + ": ROADD" + n_str + " vertex count is not multiple of " + str(n_road_verts))
        if n_verts > count_max:
            sl.append(self.convert_to_attr(last, 8, 0))
            sl.append(n_verts//n_road_verts)
        else:
            sl.append(self.convert_to_attr(last, 8, (n_verts//n_road_verts)))
        div_type = 0
        div_value = 0
        div_property = prop["divider_type"]
        if div_property == "W":
            div_type = 3
            div_value = 256
        elif div_property == "E":
            div_type = 2
            div_value = int(prop["divider_param"])
        elif div_property == "F":
            div_type = 1
            div_value = int(prop["divider_param"])
        end_close = 0
        start_close = 0
        caps = int(prop["caps"])
        if caps == 1:
            start_close = 1
        elif caps == 2:
            end_close = 1
        elif caps == 3:
            end_close = 1
            start_close = 1
        if bp.div_mat_id > 255:
            raise Exception("Error in block " + str(bi) + ": ROADD" + n_str + " divider texture index > 255")
        sl.append(self.convert_div_road_vals(end_close, start_close, div_type, bp.div_mat_id))
        sl.append(div_value)
        if typ == "ROADD":
            for i in range(n_verts):
                v = self.scene_input.get_vertex(bp.geo, i)
                sl.append(self.get_vert_index(v))
        else:
            for i in range(n_verts):
                if (i + 4) % 4 == 0:
                    v0 = self.scene_input.get_vertex(bp.geo, i)
                    v1 = self.scene_input.get_vertex(bp.geo, i + 1)
                    v2 = self.scene_input.get_vertex(bp.geo, i + 2)
                    v3 = self.scene_input.get_vertex(bp.geo, i + 3)
                    sl.append(self.get_vert_index(v0))
                    sl.append(self.get_vert_index(v0))
                    sl.append(self.get_vert_index(v1))
                    sl.append(self.get_vert_index(v2))
                    sl.append(self.get_vert_index(v3))
                    sl.append(self.get_vert_index(v3))

    def process_part_rail(self, b, bi, bp, bpi, last):
        # Road tunnel/railing
        prop = self.scene_input.get_property_container(bp.geo)
        sl = self.temp_shorts_list
        sl.append(self.convert_to_attr(last, 9, 3))
        bits = []
        bits.append(0)
        bits.append(int(prop["is_rail"]))  # Enables outer faces if railings are used
        bits.append(int(prop["curved_sides"]))  # curvedSides
        bits.append(int(prop["offset_end_right"]))  # offsetEndRight
        bits.append(int(prop["offset_start_right"]))  # offsetStartRight
        bits.append(int(prop["offset_end_left"]))  # offsetEndLeft
        bits.append(int(prop["offset_start_left"]))  # offsetStartLeft
        bits.append(int(prop["is_curved_gallery"]))  # curvedCeiling
        bits.append(int(prop["cap_end_right"]))  # closedEndRight
        bits.append(int(prop["cap_start_right"]))  # closedStartRight
        bits.append(int(prop["cap_end_left"]))  # closedEndLeft
        bits.append(int(prop["cap_start_left"]))  # closedStartLeft
        bits.append(int(prop["is_flat_gallery"]))  # flatCeiling
        bits.append(int(prop["is_wall"]))  # style (0=rail, 1=wall)
        bits.append(int(prop["has_right"]))  # enable right side
        bits.append(int(prop["has_left"]))  # enable left side
        sl.append(self.bits_to_byte(bits))
        sl.append(int(prop["height"]))  # height
        sl.append(0)

    def rotate_array(self, a, i):
        return a[i:] + a[:i]

    def get_connected_vertices(self, obj, v1):
        verts = []
        num_polys = self.scene_input.get_polygons_num(obj)
        for i in range(num_polys):
            face = self.get_face_array(obj, i, False)
            if v1 in face:
                for v2 in face:
                    if v1 != v2 and v2 not in verts:
                        verts.append(v2)
        return verts

    def check_if_same_railc_face(self, obj, v1, v2):
        # return True
        num_polys = self.scene_input.get_polygons_num(obj)
        for i in range(num_polys):
            face = self.get_face_array(obj, i, False)
            if v1 in face and v2 in face:
                return True
        # simple search failed, check if they belong to the same pieces
        s = []
        found = []
        s.append(v1)
        while len(s) > 0:
            v = s.pop()
            if v not in found:
                found.append(v)
                for w in self.get_connected_vertices(obj, v):
                    s.append(w)
        return v2 in found

    def preprocess_part_railc(self, bi, bp):
        # Junction tunnel/railing
        sl = self.temp_shorts_list
        verts0 = []
        reverse_indices = {}
        vert_count = self.scene_input.get_vertices_num(bp.geo)
        for i in range(vert_count):
            v = self.scene_input.get_vertex(bp.geo, i)
            vi = self.get_vert_index(v)
            if vi > -1:
                verts0.append(vi)
                reverse_indices[vi] = i

        # if the first perimeter point has a railing then the railing is extended to the previous point for some reason
        # so to avoid problems we have to avoid that
        if not bi in self.already_rotated:
            self.already_rotated[bi] = False
        p1 = self.perim_points[0].ID
        p2 = self.perim_points[-1].ID
        v1 = -1
        v2 = -1
        OK1 = False
        OK2 = False
        for vi in verts0:
            if p1 == vi:
                OK1 = True
                v1 = reverse_indices[vi]
            if p2 == vi:
                OK2 = True
                v2 = reverse_indices[vi]
        if OK1 and OK2 and self.check_if_same_railc_face(bp.geo, v1, v2):
            if not self.already_rotated[bi]:
                self.perim_points = self.rotate_array(self.perim_points, -1)
                self.already_rotated[bi] = True
            else:
                report.warning("a railing on block " + str(bi) + "is on perimeter vertex 0, and the perimeter cannot be rotated automatically, the ingame result will be wrong")

    def process_part_railc(self, b, bi, bp, bpi, last):
        # Junction tunnel/railing
        prop = self.scene_input.get_property_container(bp.geo)
        sl = self.temp_shorts_list
        verts0 = []
        reverse_indices = {}
        vert_count = self.scene_input.get_vertices_num(bp.geo)
        for i in range(vert_count):
            v = self.scene_input.get_vertex(bp.geo, i)
            vi = self.get_vert_index(v)
            if vi > -1:
                verts0.append(vi)
                reverse_indices[vi] = i

        verts1 = []
        rail_empty = True
        for ip in range(len(self.perim_points)):
            p1 = self.perim_points[ip].ID
            p2 = self.perim_points[ip - 1].ID
            v1 = -1
            v2 = -1
            OK1 = False
            OK2 = False
            for vi in verts0:
                if p1 == vi:
                    OK1 = True
                    v1 = reverse_indices[vi]
                if p2 == vi:
                    OK2 = True
                    v2 = reverse_indices[vi]
            if OK1 and OK2 and self.check_if_same_railc_face(bp.geo, v1, v2):
                verts1.append(1)
                rail_empty = False
            else:
                verts1.append(0)
            for bb in range(1, len(self.perim_points[ip].blocks)):
                verts1.append(0)
        remain = len(verts1) % 16
        if rail_empty:
            report.warning("railc is empty")
        if len(verts1) > 96:
            raise Exception("Error in block " + str(bi) + ": Too many perimeter edges to use RAILC (max is 96, current is " + str(len(verts1)) + ")")
        for i in range(remain):
            verts1.append(0)
        sl.append(self.convert_to_attr(last, 9, 0))
        sl.append(10)
        bits = []
        bits.append(0)
        bits.append(int(prop["is_rail"]))  # Enables outer faces if railings are used
        bits.append(int(prop["curved_sides"]))  # curvedSides
        bits.append(int(prop["offset_end_right"]))  # offsetEndRight
        bits.append(int(prop["offset_start_right"]))  # offsetStartRight
        bits.append(int(prop["offset_end_left"]))  # offsetEndLeft
        bits.append(int(prop["offset_start_left"]))  # offsetStartLeft
        bits.append(int(prop["is_curved_gallery"]))  # curvedCeiling
        bits.append(int(prop["cap_end_right"]))  # closedEndRight
        bits.append(int(prop["cap_start_right"]))  # closedStartRight
        bits.append(int(prop["cap_end_left"]))  # closedEndLeft
        bits.append(int(prop["cap_start_left"]))  # closedStartLeft
        bits.append(int(prop["is_flat_gallery"]))  # flatCeiling
        bits.append(int(prop["is_wall"]))  # style (0=rail, 1=wall)
        bits.append(1)
        bits.append(1)
        sl.append(self.bits_to_byte(bits))
        sl.append(int(prop["height"]))  # height
        sl.append(0)
        sl.append(0)
        bits = []
        lengthcheck = 0
        sl2 = []
        for i in range(len(verts1)):
            bits.append(verts1[i])
            if (len(bits) % 16) == 0 or i == (len(verts1) - 1):
                bits.reverse()
                sl.append(self.bits_to_byte(bits))
                lengthcheck += 1
                bits = []
        for i in range(6 - lengthcheck):
            sl.append(0)

    def get_light_angle(self, normal):
        direction = (0.0, -1.0, 0.0)
        v1 = normal / np.linalg.norm(normal)
        v2 = direction / np.linalg.norm(direction)
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        det = v1[0] * v2[1] - v1[1] * v2[0]
        angle = np.rad2deg(np.arctan2(det, dot)) + 180.0
        return (angle / 360.0) * 63.0

    def process_part_facb(self, b, bi, bp, bpi, last):
        # Facade bound
        sl = self.temp_shorts_list
        sl.append(self.convert_to_attr(last, 7, 4))
        v0 = self.scene_input.get_vertex(bp.geo, 0)
        v1 = self.scene_input.get_vertex(bp.geo, 1)
        v3 = self.scene_input.get_vertex(bp.geo, 3)
        normal = np.cross(np.subtract(v0, v1), np.subtract(v3, v1))
        sl.append(self.get_light_angle(normal))
        sl.append(self.get_height_index(self.scene_input.get_vertex(bp.geo, 2)[2]))
        sl.append(self.get_vert_index(self.scene_input.get_vertex(bp.geo, 0)))
        sl.append(self.get_vert_index(self.scene_input.get_vertex(bp.geo, 1)))

    def process_part_fac(self, b, bi, bp, bpi, last):
        # Facade
        prop = self.scene_input.get_property_container(bp.geo)
        sl = self.temp_shorts_list
        sl.append(self.convert_to_attr(last, 11, 6))
        sl.append(self.get_height_index(self.scene_input.get_vertex(bp.geo, 0)[2]))
        sl.append(self.get_height_index(self.scene_input.get_vertex(bp.geo, 2)[2]))
        sl.append(int(prop["u_tiling"]))
        sl.append(int(prop["v_tiling"]))
        sl.append(self.get_vert_index(self.scene_input.get_vertex(bp.geo, 0)))
        sl.append(self.get_vert_index(self.scene_input.get_vertex(bp.geo, 1)))

    def process_part_sliver(self, b, bi, bp, bpi, last):
        # Sliver
        prop = self.scene_input.get_property_container(bp.geo)
        sl = self.temp_shorts_list
        sl.append(self.convert_to_attr(last, 3, 4))
        sl.append(self.get_height_index(self.scene_input.get_vertex(bp.geo, 2)[2]))

        # texture scale
        sh = int(prop["tiling"])/100.0

        sl.append(self.get_height_index(sh))
        sl.append(self.get_vert_index(self.scene_input.get_vertex(bp.geo, 0)))
        sl.append(self.get_vert_index(self.scene_input.get_vertex(bp.geo, 1)))

    # ==== PART TYPES END ====

    def process_block_parts(self, b, bi):
        for bpi in range(len(b)):
            bp = b[bpi]
            typ = self.utils.get_object_type(bp.geo)
            if typ == "RAILC":
                self.preprocess_part_railc(bi, bp)
        for bpi in range(len(b)):
            bp = b[bpi]
            prop = self.scene_input.get_property_container(bp.geo)
            last = 0
            if bpi == (len(b) - 1):
                last = 1
            typ = self.utils.get_object_type(bp.geo)
            if bool(int(prop.get("echo", "0"))):
                self.block_flags[bi].f2 = 1
            if bool(int(prop.get("warp", "0"))):
                self.block_flags[bi].f7 = 1
            if bool(int(prop.get("disable", "0"))):
                bp.mat_id = -1
            if bp.mat_id != 0:
                ml = []
                if bp.mat_id == -1:
                    ml.append(self.convert_to_attr(0, 10, 0))
                    ml.append(0)
                    self.shorts_lists.append(ml)
                else:
                    max_mat_mult = 7
                    if self.cap_materials:
                        max_mat_mult = 1
                        if bp.mat_id > 511:
                            self.tex_warning += 1
                    else:
                        if bp.mat_id > 511:
                            self.ct_warning = True
                        elif bp.mat_id > 2047:
                            self.tex_warning_2 += 1
                    ml.append(self.convert_to_attr(0, 10, min(bp.mat_id//256, max_mat_mult)))
                    ml.append(bp.mat_id - 256 * min(bp.mat_id//256, max_mat_mult))
                    self.shorts_lists.append(ml)
            self.temp_shorts_list = []
            if typ in ["BLOCK", "IS"]:
                self.process_part_block_is(b, bi, bp, bpi, last)
            elif typ == "ROOF":
                self.process_part_roof(b, bi, bp, bpi, last)
            elif typ == "CW":
                self.process_part_cw(b, bi, bp, bpi, last)
            elif typ == "SW":
                self.process_part_sw(b, bi, bp, bpi, last)
            elif typ == "ROADS":
                self.process_part_roads(b, bi, bp, bpi, last)
            elif typ in ["ROADSN", "ROADN"]:
                self.process_part_roadsn_roadn(b, bi, bp, bpi, last)
            elif typ in ["ROADD", "ROADDN"]:
                self.process_part_roadd_roaddn(b, bi, bp, bpi, last)
            elif typ == "RAIL":
                self.process_part_rail(b, bi, bp, bpi, last)
            elif typ == "RAILC":
                self.process_part_railc(b, bi, bp, bpi, last)
            elif typ == "FACB":
                self.process_part_facb(b, bi, bp, bpi, last)
            elif typ == "FAC":
                self.process_part_fac(b, bi, bp, bpi, last)
            elif typ == "SLIVER":
                self.process_part_sliver(b, bi, bp, bpi, last)
            self.shorts_lists.append(self.temp_shorts_list)

    def block_sorted_by_type(self, order, b):
        b2 = []
        for typ in order:
            for bp in b:
                pname = self.utils.get_object_type(bp.geo)
                match = False
                if type(typ) is list:
                    match = pname in typ
                else:
                    match = typ == "" or pname == typ
                if (bp not in b2) and match:
                    b2.append(bp)
        return self.order_rails(b2)

    def order_rails(self, b):
        # a road tunnel/railing applies to the road attribute after it: a RAIL with the property "road_name" goes right
        # before the road whose property "original_id" has that value (the others stay where they are)
        roads = {}
        for bp in b:
            key = self.scene_input.get_property_container(bp.geo).get("original_id", None)
            if key is not None and self.utils.get_object_type(bp.geo) in ["ROADS", "ROADSN", "ROADN", "ROADD", "ROADDN"]:
                roads[key] = bp
        rails = [bp for bp in b if self.utils.get_object_type(bp.geo) == "RAIL"
                 and self.scene_input.get_property_container(bp.geo).get("road_name", None) in roads]
        if len(rails) == 0:
            return b
        res = [bp for bp in b if bp not in rails]
        for rail in rails:
            road = roads[self.scene_input.get_property_container(rail.geo)["road_name"]]
            res.insert(res.index(road), rail)
        return res

    def process_blocks_loop(self):
        for bi in range(len(self.blocks)):
            self.scene_input.set_progress_bar(round((bi+1)/len(self.blocks) * 100) * 0.01)
            print("Processing block " + str(bi+1) + " of " + str(len(self.blocks)) + "...")
            b = self.block_sorted_by_type(["NUL",
                                           "RAIL", "RAILC",
                                           "ROADS", "ROADSN", "ROADN", "ROADD", "ROADDN",
                                           "BLOCK",
                                           "IS", "SW", "CW",
                                           "SLIVER", ["FAC", "FACB"], "ROOF",
                                           ""], self.blocks[bi])
            # the manual perimeter is not an attribute
            perim_parts = [bp for bp in b if self.utils.get_object_type(bp.geo) == "PERIM"]
            b = [bp for bp in b if self.utils.get_object_type(bp.geo) != "PERIM"]
            self.block_flags.append(BlockFlag())
            self.perim_points = []
            self.shorts_lists = []
            # when the errors are collected (see report.collecting), a block that fails is written empty (the other
            # blocks keep their index) and the export goes on, so that every error is reported at once
            try:
                if len(perim_parts) > 0:
                    self.perim_points = self.get_manual_perimeter(perim_parts[0], bi)
                else:
                    try:
                        self.perim_points = self.get_perimeter(b, bi, False)
                    except Exception:
                        print("Perimeter Error, retrying with more precision...")
                        self.perim_points = self.get_perimeter(b, bi, True)

                    if self.perim_points is None:
                        raise Exception("Perimeter error on block " + str(bi+1))
                    self.perim_points.reverse()  # Picked it clockwise, as said in the wiki, but it's counterclockwise actually
                self.process_block_parts(b, bi)
            except Exception:
                if not report.collecting():
                    raise
                report.exception("Block " + str(bi + 1) + " not exported", element=report.element_name(self.block_name(b)))
                self.perim_points = []
                self.shorts_lists = []

            n_perim_points = 0

            for p in self.perim_points:
                if len(p.blocks) == 0:
                    n_perim_points += 1
                else:
                    n_perim_points += len(p.blocks)
            n_shorts = 0
            for a in self.shorts_lists:
                for s in a:
                    n_shorts += 1
            file = self.file
            file.write_uint32(n_perim_points)
            file.write_uint32(n_shorts)
            for p in self.perim_points:
                if len(p.blocks) == 0:
                    file.write_uint16(p.ID)  # unsigned
                    file.write_uint16(0)
                else:
                    for bID in p.blocks:
                        file.write_uint16(p.ID)  # unsigned
                        file.write_uint16(bID + 1)
            for a in self.shorts_lists:
                for s in a:
                    file.write_uint16(s)  # unsigned

    def get_bits(self, val, l):
        bits = []
        div = 2 ** l
        for i in range(l):
            div //= 2
            if val >= div:
                bits.append(1)
                val -= div
            else:
                bits.append(0)
        return bits

    def bits_to_byte(self, bits):
        byte = 0
        div = 2 ** len(bits)
        for i in range(len(bits)):
            div //= 2
            byte += div * bits[i]
        return byte

    def process_blocks(self):
        print("processing blocks...")
        for b in self.blocks:
            cur_is = 0
            for i in range(len(b)):
                pname = self.utils.get_object_type(b[i].geo)
                if i != cur_is and pname == "IS":
                    b1 = b[cur_is]
                    bi = b[i]
                    b[cur_is] = bi
                    b[i] = b1
                    cur_is += 1
        self.file = BinaryFileHelper(self.filepath, 'wb')
        file = self.file
        file.write_raw_string("PSD0")
        file.write_uint32(2)

        # Write vertices
        if len(self.vertices) > 65536:
            raise Exception("Error: too many unique vertices (max. is 65536, count is " + str(len(self.vertices)) + ")")
        file.write_uint32(len(self.vertices) + 1)
        # The first vertex is not really used
        file.write_float(0.0)
        file.write_float(-0.15)
        file.write_float(0.0)
        for i in range(len(self.vertices)):
            v = self.vertices[i]
            file.write_vec3(v)

        # Write heights
        file.write_uint32(len(self.heights))
        for h in self.heights:
            file.write_float(h)

        # Write materials
        file.write_uint32(self.n_mats)
        for t in self.textures:
            file.write_string(t)

        # Write blocks
        file.write_uint32(len(self.blocks) + 1)
        file.write_uint32(0)  # Number of junctions?
        self.process_blocks_loop()
        file.write_byte(0)
        for flags in self.block_flags:
            bits = []
            bits.append(flags.f8)
            bits.append(flags.f7)
            bits.append(flags.f6)
            bits.append(flags.f5)
            bits.append(flags.f4)
            bits.append(flags.f3)
            bits.append(flags.f2)
            bits.append(flags.f1)
            flagval = self.bits_to_byte(bits)
            file.write_byte(flagval)
        file.write_byte(205)
        bi = 0
        for b in self.blocks:
            if bi in self.prop_rules:
                file.write_byte(self.prop_rules[bi])
            else:
                file.write_byte(0)
            bi += 1

        # City bounds
        psdl_center = [(self.min_pos[0] + self.max_pos[0]) / 2,
                       (self.min_pos[1] + self.max_pos[1]) / 2,
                       (self.min_pos[2] + self.max_pos[2]) / 2]
        psdl_radius = math.sqrt((self.max_pos[0] - psdl_center[0]) ** 2 +
                                (self.max_pos[1] - psdl_center[1]) ** 2 +
                                (self.max_pos[2] - psdl_center[2]) ** 2)
        file.write_vec3(self.min_pos)
        file.write_vec3(self.max_pos)
        file.write_vec3(psdl_center)
        file.write_float(psdl_radius)
        file.write_uint32(len(self.prop_blocks))
        for i in range(len(self.prop_blocks)):
            file.write_uint16(1089)
            file.write_uint16(1)
            file.write_byte(0)
            file.write_byte(0)
            file.write_uint16(1)

            file.write_uint16(0)
            file.write_uint16(0)
            file.write_uint16(0)
            file.write_uint16(0)

            file.write_uint16(0)
            file.write_uint16(0)
            file.write_uint16(0)
            file.write_uint16(0)

            file.write_byte(1)
            file.write_uint16(self.prop_blocks[i] + 1)
        file.close()

    def write(self):
        self.scene_input.init_progress_bar()
        self.initialize_variables()
        self.read_blocks()
        self.calc_boundaries()
        self.process_vertices()
        self.search_duplicate_vertices()
        self.process_materials()
        self.process_blocks()
        self.scene_input.end_progress_bar()
        if self.ct_warning:
            report.warning("the city contains more than 511 texture references, " \
                  "it will work ingame while using MM2Hook but tools like MM2 " \
                  "City Toolkit will not be able to open it. " \
                  "Furthermore, stock MM2 (without MM2Hook) will not be able to load it if there "\
                  "are more than 767 materials (you can check the counter at the beginning of this log)")
        if self.tex_warning > 0:
            report.warning("the city contains more than 511 texture references, " \
                  "in stock MM2 (without MM2Hook) some will not be rendered properly " \
                  "(affects " + str(self.tex_warning) + " objects)")
        if self.tex_warning_2 > 0:
            report.warning("the city contains more than 2047 texture references, " \
            "some will not be rendered properly ingame (affects " + str(self.tex_warning) + " objects)")
        print("PSDL Exported!")
